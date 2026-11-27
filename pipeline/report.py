"""Reporting, quote-anchored multi-auditor reconciliation, and LLM extraction prompt generation."""

from __future__ import annotations

import json
from typing import Any

from pipeline.ingest import IngestedDocument, dehyphenate_and_normalize, normalize_whitespace
from pipeline.lean_runner import LeanVerificationResult
from pipeline.schema import (
    QuoteMatch,
    ValidationErrorItem,
    collect_out_of_scope_spec_fields,
    evaluate_ask_back,
    is_ask_back_entry_complete,
    verify_quote_in_document,
)


def format_finding_human(f: dict[str, Any]) -> str:
    ft = f["type"]
    if ft == "excludedChannelLeak":
        return f"**[Alarm 1 — Excluded Channel Leak]** `{f['tag']}` reaches excluded channel via `{' → '.join(f['path'])}`"
    if ft == "authorSuppliedStructure":
        return f"**[Alarm 2 — Author-Supplied Structure]** `{f['tag']}` injected by experimenter source `{f['origin']}` via `{' → '.join(f['path'])}`"
    if ft == "smuggledStructure":
        return f"**[Smuggled Structure]** `{f['tag']}` from `{f['origin']}` via `{' → '.join(f['path'])}`"
    if ft == "failedForgetOnPath":
        return f"**[Failed Forget]** op `{f['op']}` tried to drop `{f['tag']}` with evidence `{f['evidence']}`"
    if ft == "sharedUpstreamStructure":
        return f"**[Shared Upstream Structure]** branches share `{f['shared']}` carrying `{f['tag']}`"
    if ft == "sharedExperimenterSource":
        return f"**[Shared Experimenter Source]** branches share unforgotten experimenter input `{f['shared']}`"
    if ft == "lossyChannelOnPath":
        return (
            f"**[Lossy Channel Bottleneck]** many-to-one op `{f['op']}` at `{f['output']}` witnesses tag collision and "
            f"cuts all paths to target (assuming colliding inputs remain jointly valid while holding disconnected outside "
            f"sources fixed; if outside sources have unmodeled joint constraints, treat recovery on the constrained support as unestablished)"
        )
    if ft == "untargetedLossyChannel":
        return (
            f"**[Untargeted Lossy Channel]** op `{f['op']}` at `{f['output']}` is marked `lossy` without specifying "
            f"`loses` for `{f['tag']}`; cannot certify lossless recovery or prove collision on `{f['tag']}` specifically"
        )
    if ft == "lossyWithSideInformation":
        sides = ", ".join(f"`{s}`" for s in f.get("side_nodes", []))
        return (
            f"**[Lossy Channel with Side-Information Bypass — Undecidable from Graph Alone]** op `{f['op']}` at "
            f"`{f['output']}` collides on the target tag, but co-input/ancestor node(s) ({sides}) bypass `{f['output']}` "
            f"into the final observation (e.g. `r` in `(s XOR r, r)`); joint non-invertibility requires algebraic proof"
        )
    if ft == "parallelLossyBranches":
        outs = ", ".join(f"`{o}`" for o in f.get("lossy_outputs", []))
        return (
            f"**[Parallel Lossy Branches — Undecidable from Graph Alone]** every `{f['tag']}` path to `{f['target']}` "
            f"crosses a lossy op ({outs}) with no single lossy bottleneck; joint injectivity requires algebraic/domain proof"
        )
    if ft == "unaccessedTargetStructure":
        return (
            f"**[Unaccessed Structure]** target `{f['target']}` has no upstream SourceNode granting access to `{f['tag']}` "
            f"(absence of observation in the declared graph is not evidence of absence in reality)"
        )
    if ft == "undeclaredUpstreamSource":
        return f"**[Undeclared Source]** upstream source `{f['source']}` omitted from conditional claim"
    if ft == "danglingInput":
        return f"**[Dangling Input]** op `{f['op']}` consumes undefined node `{f['missing']}`"
    if ft == "trivialCostLedger":
        return f"**[Trivial Cost Ledger]** ledger `{f['ledger']}` is identical to arm `{f['arm']}`"
    if ft == "unusedCostLedger":
        return f"**[Unused Cost Ledger]** ledger `{f['ledger']}` does not feed evaluation `{f['evaluation']}`"
    if ft == "unaccountedCostSource":
        return f"**[Unaccounted Cost Source]** `{f['cost_source']}` (`{f['cost_tag']}`) feeds an arm (ignoring `.forget`) but is omitted from ledger `{f['ledger']}`"
    if ft == "unusedMethodNode":
        return f"**[Unused Method]** method `{f['method']}` does not feed evaluation `{f['evaluation']}`"
    if ft == "missingMatchedControl":
        return f"**[Missing Matched Control]** effectiveness claim on `{f['method']}` provides no control arm"
    if ft == "trivialSelfControl":
        return f"**[Trivial Self-Control]** `{f['method']}` is compared against itself"
    if ft == "dependentControlArm":
        return f"**[Dependent Control Arm]** `{f['method']}` and `{f['control']}` are causally dependent (not independent arms)"
    if ft == "unusedControlNode":
        return f"**[Unused Control]** control `{f['control']}` does not feed evaluation `{f['evaluation']}`"
    if ft == "hypothesisKnownFalse":
        return f"**[Rule 3 — Hypothesis Known False]** applied theorem at `{f['target']}` requires `{f['hypothesis']}`, which is known false in the declared setting"
    if ft == "undeclaredHypothesisBet":
        return f"**[Rule 3 — Undeclared Hypothesis Bet]** applied theorem at `{f['target']}` relies on unchecked hypothesis `{f['hypothesis']}` omitted from `declared_bets`"
    if ft == "orphanDeclaredBet":
        return f"**[Rule 3 — Orphan Declared Bet]** `declared_bets` at `{f['target']}` lists `{f['hypothesis']}` without a matching entry in `hypotheses`"
    if ft == "claimOutOfScope":
        return f"**[Out of Scope]** {f['reason']}"
    return json.dumps(f)


def _count_declared_bets(claim_meta: dict[str, Any]) -> int:
    """Count distinct unchecked (`status == 'bet'`) hypotheses declared in `declared_bets`."""
    if not isinstance(claim_meta, dict) or claim_meta.get("kind") != "theoremApplication":
        return 0
    declared = set(claim_meta.get("declared_bets", []))
    return sum(
        1
        for h in claim_meta.get("hypotheses", [])
        if isinstance(h, dict) and h.get("status") == "bet" and h.get("tag") in declared
    )


DISPLAY_STATE_LEGEND = (
    "*Display-state legend: `no structural alarm` and `conditional on N declared, unchecked assumption(s)` "
    "are display refinements of the Lean 4 `EpistemicVerdict.admissible` enum (zero verdict-bearing structural "
    "findings inside the modeled graph; never certifies unmodeled reality). `unestablished`, `rejected`, and "
    "`outOfScope` correspond directly to the remaining Lean enum states.*"
)

STOP_ANSWER_LABELS: dict[str, tuple[str, str]] = {
    "causal_test_not_found": (
        "E2: causal test not found",
        "no test found that separates the mechanism from another explanation",
    ),
    "sentence_stronger_than_own_wording": (
        "E3: sentence stronger",
        "sentence is stronger than the paper's own wording elsewhere",
    ),
    "speaks_beyond_slice": (
        "E4: beyond slice",
        "sentence speaks beyond the tested observation slice",
    ),
    "fitted_on_test_data": (
        "E5: fitted on test data",
        "test inputs were fitted on the test data",
    ),
}


def compute_display_state(verdict: str, declared_bet_count: int = 0) -> str:
    """Map Lean `EpistemicVerdict` + `declared_bet_count` to one of the 5 display states:
    `noStructuralAlarm`, `conditional`, `unestablished`, `rejected`, `outOfScope`."""
    if verdict == "admissible":
        return "conditional" if declared_bet_count >= 1 else "noStructuralAlarm"
    return verdict


def format_display_state_short(verdict: str, declared_bet_count: int = 0) -> str:
    if verdict == "admissible":
        if declared_bet_count >= 1:
            noun = "assumption" if declared_bet_count == 1 else "assumptions"
            return f"conditional on {declared_bet_count} declared, unchecked {noun}"
        return "no structural alarm"
    return verdict


def _format_dep_display_state(dep: dict[str, Any]) -> str:
    ds = dep.get("display_state")
    bets = int(dep.get("declared_bet_count", 0))
    if ds == "noStructuralAlarm":
        base = "no structural alarm"
    elif ds == "conditional":
        noun = "assumption" if bets == 1 else "assumptions"
        base = f"conditional on {bets} declared, unchecked {noun}" if bets >= 1 else "conditional"
    else:
        base = str(ds) if ds else "unknown"
    stop_count = int(dep.get("stop_answer_count", 0))
    if stop_count > 0:
        s_noun = "stop answer" if stop_count == 1 else "stop answers"
        return f"{base}; {stop_count} {s_noun}"
    return base


def _extract_stop_answers(claim_meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Extract canonical reader stop-answer codes (E2–E5) and E6 `rests_on` claim IDs from `ask_back`.

    Gates per individual question entry via `is_ask_back_entry_complete` so incomplete draft entries
    (e.g., E2 `not_found` missing `searched_where` or E4 `beyond` missing `quote`/`reason`) are never
    promoted under the 'quote-checked' label, while completed entries on the same claim still display.
    """
    ab = claim_meta.get("ask_back") if isinstance(claim_meta, dict) else None
    if not isinstance(ab, dict):
        return [], []
    stops: list[str] = []
    causal = ab.get("causal")
    if is_ask_back_entry_complete("causal", causal) and causal.get("status") == "not_found":
        stops.append("causal_test_not_found")
    own = ab.get("own_wording")
    if (
        is_ask_back_entry_complete("own_wording", own)
        and own.get("status") == "answered"
        and own.get("reading") == "sentence_stronger"
    ):
        stops.append("sentence_stronger_than_own_wording")
    sl = ab.get("slice")
    if (
        is_ask_back_entry_complete("slice", sl)
        and sl.get("status") == "answered"
        and sl.get("reading") == "beyond"
    ):
        stops.append("speaks_beyond_slice")
    ti = ab.get("test_inputs")
    if (
        is_ask_back_entry_complete("test_inputs", ti)
        and ti.get("status") == "answered"
        and ti.get("reading") == "fitted_on_test_data"
    ):
        stops.append("fitted_on_test_data")
    rests_on_ids: list[str] = []
    ro = ab.get("rests_on")
    if (
        is_ask_back_entry_complete("rests_on", ro)
        and ro.get("status") == "answered"
        and isinstance(ro.get("claim_ids"), list)
    ):
        rests_on_ids = [str(cid) for cid in ro["claim_ids"] if isinstance(cid, str)]
    return stops, rests_on_ids


def _format_verdict_table(verdict: str, declared_bet_count: int = 0, kind: str | None = None) -> str:
    if verdict == "admissible":
        if declared_bet_count >= 1:
            noun = "assumption" if declared_bet_count == 1 else "assumptions"
            return f"conditional on {declared_bet_count} declared, unchecked {noun}"
        if kind == "effectivenessClaim":
            return "no structural alarm (structural comparison only; numbers & necessity unchecked)"
        return "no structural alarm"
    return verdict


def _format_verdict_heading(verdict: str, declared_bet_count: int = 0, kind: str | None = None) -> str:
    if verdict == "admissible":
        if declared_bet_count >= 1:
            noun = "assumption" if declared_bet_count == 1 else "assumptions"
            return f"CONDITIONAL on {declared_bet_count} declared, unchecked {noun}"
        if kind == "effectivenessClaim":
            return "NO STRUCTURAL ALARM (structural comparison only; numbers & necessity unchecked)"
        return "NO STRUCTURAL ALARM"
    if verdict == "unestablished":
        return "UNESTABLISHED (data/design stops at map edge)"
    if verdict == "outOfScope":
        return "OUT OF SCOPE"
    return verdict.upper()


def _claim_signature(meta: dict[str, Any]) -> dict[str, Any]:
    kind = meta.get("kind")
    sig: dict[str, Any] = {
        "kind": kind,
        "provenance": meta.get("provenance", "authorClaimed"),
        "nature": meta.get("nature", "qualitative"),
    }
    if isinstance(meta.get("exclusion_wording_quote"), str):
        sig["exclusion_wording_quote"] = normalize_whitespace(meta["exclusion_wording_quote"])
    if isinstance(meta.get("excluded_object"), str):
        sig["excluded_object"] = meta["excluded_object"]
    if "quantitative_kind" in meta:
        sig["quantitative_kind"] = meta["quantitative_kind"]
    for k in (
        "target",
        "excluded_channel",
        "branch_a",
        "branch_b",
        "tag",
        "declared_sources",
        "method_node",
        "evaluation_node",
        "control_node",
        "cost_ledger_node",
        "cost_tag",
        "declared_bets",
        "reason",
    ):
        if k in meta:
            sig[k] = meta[k]
    if "hypotheses" in meta:
        sig["hypotheses"] = sorted(
            [{"tag": h.get("tag"), "status": h.get("status")} for h in meta["hypotheses"]],
            key=lambda x: (str(x["tag"]), str(x["status"])),
        )
    return sig


OUT_OF_SCOPE_CORE = (
    "Semantic interpretation of quotes (whether a quote justifies a tag, causal edge, or statistical test) "
    "is out of scope for Lean verification and requires auditor/human review."
)
OUT_OF_SCOPE_ACCOUNTING = (
    "Numeric arithmetic, specific reported values, derived ratios/differences, and financial/bookkeeping "
    "reconciliation are out of scope for EpistemicLedger; Lean checks structural control presence, arm "
    "independence, evaluation wiring, and forget-proof cost-source coverage without reading or comparing numbers."
)
OUT_OF_SCOPE_SOURCE_SUPPORT = (
    "Unmodeled joint support constraints across disconnected SourceNodes (e.g., an external coupling "
    "`c = r` not represented by a shared upstream SourceNode) are out of scope for pure DAG topology: "
    "`lossyChannelOnPath` certifies non-recoverability assuming both colliding inputs of the bottleneck op "
    "remain jointly valid while holding disconnected outside observations fixed."
)
OUT_OF_SCOPE_PDF_MATH = (
    "PDF text extraction (`pdftotext`) can drop superscripts, subscripts, and mathematical symbols; "
    "verbatim quote grounding verifies fidelity to the extracted text snapshot, not formula typography "
    "— prefer `.tex` / LaTeX source when auditing formula-heavy mathematical statements."
)


def _compute_declaration_locations(
    doc: IngestedDocument, spec: dict[str, Any], claim_meta: dict[str, Any]
) -> list[dict[str, Any]]:
    """Mechanically locate where each declared assumption (`declared_bets` on `theoremApplication`)
    or declared source (`declared_sources` on `conditionalFlow`) appears relative to the claim quote.

    Does NOT alter any verdict: annotates whether each declaration overlaps the claim sentence
    (`in_claim`) or appears elsewhere in the document body (`elsewhere_in_document` with `@offset`).
    """
    kind = claim_meta.get("kind")
    if kind not in ("theoremApplication", "conditionalFlow"):
        return []
    claim_quote = claim_meta.get("quote", "")
    claim_span = _claim_anchor_span(doc, claim_quote)
    if claim_span is None:
        return []
    c_start, c_end, _ = claim_span
    dehy_claim = dehyphenate_and_normalize(claim_quote)

    targets: list[tuple[str, str, str]] = []
    if kind == "theoremApplication":
        hyp_quotes = {h["tag"]: h["quote"] for h in claim_meta.get("hypotheses", []) if isinstance(h, dict) and "tag" in h and "quote" in h}
        for bet_tag in claim_meta.get("declared_bets", []):
            if bet_tag in hyp_quotes:
                targets.append(("declared_bet", str(bet_tag), hyp_quotes[bet_tag]))
    elif kind == "conditionalFlow":
        src_quotes = {s["node"]: s["quote"] for s in spec.get("sources", []) if isinstance(s, dict) and "node" in s and "quote" in s}
        for src_node in claim_meta.get("declared_sources", []):
            if src_node in src_quotes:
                targets.append(("declared_source", str(src_node), src_quotes[src_node]))

    entries: list[dict[str, Any]] = []
    for decl_kind, item_name, decl_quote in targets:
        d_span = _claim_anchor_span(doc, decl_quote)
        if d_span is None:
            continue
        d_start, d_end, _ = d_span
        dehy_decl = dehyphenate_and_normalize(decl_quote)
        overlaps = min(c_end, d_end) > max(c_start, d_start) or (dehy_decl in dehy_claim) or (dehy_claim in dehy_decl)
        entries.append(
            {
                "kind": decl_kind,
                "item": item_name,
                "location": "in_claim" if overlaps else "elsewhere_in_document",
                "char_offset": c_start if (overlaps and not (min(c_end, d_end) > max(c_start, d_start))) else d_start,
                "char_end": c_end if (overlaps and not (min(c_end, d_end) > max(c_start, d_start))) else d_end,
            }
        )
    return entries


def build_single_report_dict(
    doc: IngestedDocument,
    spec: dict[str, Any],
    errors: list[ValidationErrorItem],
    quotes: list[QuoteMatch],
    lean_result: LeanVerificationResult | None,
    auditor_label: str | None = None,
) -> dict[str, Any]:
    declared_auditor = spec.get("auditor") if isinstance(spec, dict) else "invalid"
    has_effectiveness = isinstance(spec, dict) and any(
        isinstance(c, dict) and c.get("kind") == "effectivenessClaim" for c in spec.get("claims", [])
    )
    has_unique_recovery = isinstance(spec, dict) and any(
        isinstance(c, dict) and c.get("kind") == "uniqueRecovery" for c in spec.get("claims", [])
    )
    oos_claim_ids = [
        str(c.get("id"))
        for c in (spec.get("claims", []) if isinstance(spec, dict) else [])
        if isinstance(c, dict)
        and c.get("id")
        and (
            c.get("kind") == "outOfScope"
            or (
                c.get("nature") == "quantitative"
                and c.get("quantitative_kind") in ("specificValue", "derivedComparison")
            )
        )
    ]
    out_of_scope = [OUT_OF_SCOPE_CORE]
    if doc.resolved_path.suffix.lower() == ".pdf":
        out_of_scope.append(OUT_OF_SCOPE_PDF_MATH)
    if has_effectiveness:
        out_of_scope.append(OUT_OF_SCOPE_ACCOUNTING)
    if has_unique_recovery:
        out_of_scope.append(OUT_OF_SCOPE_SOURCE_SUPPORT)
    if oos_claim_ids:
        out_of_scope.append(
            f"Explicitly out-of-scope claim(s) ({', '.join(oos_claim_ids)}): "
            "declared outside structural operation-flow verification (e.g., specific numerical values, derived comparisons, or normative/value-balancing disputes)."
        )
    ignored_fields = collect_out_of_scope_spec_fields(spec)
    if ignored_fields:
        out_of_scope.append(
            f"Ignored out-of-scope numeric/accounting fields in spec ({', '.join(ignored_fields)}): "
            "not evaluated by Lean; numerical tables and financial/bookkeeping checks require human review."
        )
    lean_claims_payload: list[dict[str, Any]] = []
    if lean_result is not None:
        for c in lean_result.claims:
            meta = next(
                (m for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id),
                {},
            )
            bet_count = _count_declared_bets(meta)
            lean_claims_payload.append(
                {
                    "id": c.claim_id,
                    "verdict": c.verdict,
                    "display_state": compute_display_state(c.verdict, bet_count),
                    "findings": c.findings,
                    "axioms": c.axioms,
                    "kernel_verified": c.kernel_verified,
                    "nature": meta.get("nature", "qualitative"),
                    "quantitative_kind": meta.get("quantitative_kind"),
                    "declared_bet_count": bet_count,
                    "declaration_locations": _compute_declaration_locations(doc, spec, meta),
                }
            )
    display_by_cid: dict[str, tuple[str, int]] = {
        c["id"]: (c["display_state"], int(c["declared_bet_count"])) for c in lean_claims_payload
    }
    verdict_by_cid: dict[str, str] = {c["id"]: c["verdict"] for c in lean_claims_payload}

    ask_back_summary = evaluate_ask_back(spec)
    applicable_v25 = bool(ask_back_summary.get("applicable_v25", False))
    ask_by_cid = {c["claim_id"]: c for c in ask_back_summary.get("claims", [])}
    reader_ask_back_by_claim: dict[str, Any] = {}
    in_scope_total = 0
    in_scope_with_stop = 0
    total_claims_count = 0
    total_with_stop = 0
    if isinstance(spec, dict) and isinstance(spec.get("claims"), list):
        extracted_by_cid: dict[str, tuple[list[str], list[str]]] = {
            str(cl["id"]): _extract_stop_answers(cl)
            for cl in spec["claims"]
            if isinstance(cl, dict) and cl.get("id")
        }
        for cl in spec["claims"]:
            if not isinstance(cl, dict) or not cl.get("id"):
                continue
            cid = str(cl["id"])
            total_claims_count += 1
            cinfo = ask_by_cid.get(cid, {})
            skipped_oos = bool(cinfo.get("skipped_out_of_scope", False))
            is_oos = (
                verdict_by_cid.get(cid) == "outOfScope"
                or cl.get("kind") == "outOfScope"
                or (
                    cl.get("nature") == "quantitative"
                    and cl.get("quantitative_kind") in ("specificValue", "derivedComparison")
                )
            )
            has_ab_dict = isinstance(cl.get("ask_back"), dict)
            stop_answers, rests_on_ids = extracted_by_cid[cid]
            rests_on_resolved: list[dict[str, Any]] = []
            for dep_id in rests_on_ids:
                dep_stop_count = len(extracted_by_cid.get(dep_id, ([], []))[0])
                if dep_id in display_by_cid:
                    dep_ds, dep_bets = display_by_cid[dep_id]
                    rests_on_resolved.append(
                        {
                            "claim_id": dep_id,
                            "display_state": dep_ds,
                            "declared_bet_count": dep_bets,
                            "stop_answer_count": dep_stop_count,
                        }
                    )
                else:
                    rests_on_resolved.append(
                        {
                            "claim_id": dep_id,
                            "display_state": None,
                            "declared_bet_count": 0,
                            "stop_answer_count": dep_stop_count,
                        }
                    )
            if not applicable_v25 and not has_ab_dict:
                stop_status = "not_asked"
            elif skipped_oos and not has_ab_dict:
                stop_status = "not_asked"
            elif stop_answers:
                stop_status = "recorded"
            else:
                stop_status = "none_recorded"
            if not is_oos:
                in_scope_total += 1
                if stop_answers:
                    in_scope_with_stop += 1
            if stop_answers:
                total_with_stop += 1
            reader_ask_back_by_claim[cid] = {
                "verified_by_lean": False,
                "complete": bool(cinfo.get("complete", True)),
                "skipped_out_of_scope": skipped_oos,
                "unanswered": [u["code"] for u in cinfo.get("unanswered", [])],
                "unanswered_details": cinfo.get("unanswered", []),
                "stop_answers_status": stop_status,
                "stop_answers": stop_answers,
                "rests_on": rests_on_resolved,
                "exclusion_wording_quote": cl.get("exclusion_wording_quote"),
                "excluded_object": cl.get("excluded_object"),
                "ask_back": cl.get("ask_back"),
            }
    return {
        "schema_version": "epistemic-ledger-report/v2.2",
        "document": {
            "source_ref": doc.source_ref,
            "resolved_path": str(doc.resolved_path),
            "sha256": doc.sha256,
        },
        "auditor": auditor_label or declared_auditor,
        "declared_auditor": declared_auditor,
        "paper_title": spec.get("paper_title", "") if isinstance(spec, dict) else "",
        "grounding_and_schema_ok": len(errors) == 0,
        "ask_back_summary": ask_back_summary,
        "reader_ask_back": {
            "verified_by_lean": False,
            "scope_note": (
                "Reader's quote-checked ask-back answers (E2–E7), stop answers, and kind anchors. "
                "NOT verified by the Lean 4 kernel (Lean proves structural flow verdicts in `lean_verification` only)."
            ),
            "summary": ask_back_summary,
            "stop_answers_summary": {
                "applicable_v25": applicable_v25,
                "in_scope_claims_total": in_scope_total,
                "in_scope_claims_with_stop_answers": in_scope_with_stop,
                "total_claims": total_claims_count,
                "claims_with_stop_answers": total_with_stop,
                "verified_by_lean": False,
            },
            "by_claim": reader_ask_back_by_claim,
        },
        "out_of_scope": out_of_scope,
        "validation_errors": [
            {"path": e.path, "code": e.code, "message": e.message} for e in errors
        ],
        "verified_quotes": [
            {
                "path": q.path,
                "matched": q.matched,
                "char_offset": q.char_offset,
                "mode": q.mode,
                "quote": q.quote,
            }
            for q in quotes
        ],
        "lean_verification": None
        if lean_result is None
        else {
            "lean_file": str(lean_result.lean_file),
            "axioms_ok": lean_result.raw_axioms_ok,
            "scope_note": "Lean 4 kernel proofs cover structural flow verdicts and findings only (not reader ask-back answers).",
            "claims": lean_claims_payload,
        },
    }


def render_single_report_markdown(report: dict[str, Any], spec: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# Epistemic Audit Report — {report.get('paper_title') or report['document']['source_ref']}",
        "",
        f"- **Source:** `{report['document']['source_ref']}` (SHA-256: `{report['document']['sha256'][:16]}...`)",
        f"- **Auditor:** `{report['auditor']}`",
        f"- **Schema & Quote Grounding:** {'PASS' if report['grounding_and_schema_ok'] else 'FAIL'} "
        f"({sum(1 for q in report['verified_quotes'] if q['matched'])}/{len(report['verified_quotes'])} verbatim quotes verified)",
    ]

    if not report["grounding_and_schema_ok"]:
        lines += ["", "## Validation / Grounding Errors", ""]
        for err in report["validation_errors"]:
            lines.append(f"- `{err['path']}` (`{err['code']}`): {err['message']}")
        if report.get("out_of_scope"):
            lines += ["", "## Out of Scope", ""]
            for item in report["out_of_scope"]:
                lines.append(f"- {item}")
        return "\n".join(lines) + "\n"

    lv = report["lean_verification"]
    lines.append(f"- **Lean 4 Kernel Proof (structural flow only):** `{lv['lean_file']}` (axioms whitelist OK: `{lv['axioms_ok']}`)")
    ab_sum = report.get("ask_back_summary", {})
    rab = report.get("reader_ask_back", {})
    rab_by_claim = rab.get("by_claim", {})
    stop_sum = rab.get("stop_answers_summary", {})
    if ab_sum.get("applicable_v25"):
        if ab_sum.get("complete"):
            lines.append("- **Ask-Back Completeness:** COMPLETE (all E2–E7 questions answered; reader answers are quote-checked evidence, not Lean-verified)")
        else:
            lines.append(
                f"- **Ask-Back Completeness:** INCOMPLETE ({ab_sum['unanswered_count']} unanswered question(s); "
                f"structural Lean verdict still produced — run `audit_cli ask` to inspect open questions)"
            )
        in_sc_with = int(stop_sum.get("in_scope_claims_with_stop_answers", 0))
        in_sc_tot = int(stop_sum.get("in_scope_claims_total", 0))
        tot_with = int(stop_sum.get("claims_with_stop_answers", in_sc_with))
        tot_all = int(stop_sum.get("total_claims", in_sc_tot))
        if tot_with == in_sc_with:
            lines.append(
                f"- **Reader Stop Answers (reader-recorded, quote-checked, not Lean-verified):** "
                f"{in_sc_with}/{in_sc_tot} in-scope claim(s) carry a stop answer"
            )
        else:
            extra_oos = tot_with - in_sc_with
            lines.append(
                f"- **Reader Stop Answers (reader-recorded, quote-checked, not Lean-verified):** "
                f"{in_sc_with}/{in_sc_tot} in-scope claim(s) carry a stop answer "
                f"({tot_with}/{tot_all} total claims including {extra_oos} out-of-scope)"
            )
    else:
        lines.append(
            "- **Reader Stop Answers (reader-recorded, quote-checked, not Lean-verified):** not asked (record older than v2.5)"
        )
    if report.get("out_of_scope"):
        lines += ["", "## Out of Scope", ""]
        for item in report["out_of_scope"]:
            lines.append(f"- {item}")
    lines += [
        "",
        "## Claim Verdicts",
        "",
        DISPLAY_STATE_LEGEND,
        "",
        "| Claim ID | Kind | Target / Channel | Display State (Lean) | Reader Stop Answers (reader-recorded, quote-checked, not Lean-verified) | Findings | Axioms |",
        "|---|---|---|---|---|---|---|",
    ]

    def _format_stop_table_cell(rab_c: dict[str, Any]) -> str:
        st_status = rab_c.get("stop_answers_status", "not_asked")
        stops = rab_c.get("stop_answers") or []
        rests_on = rab_c.get("rests_on") or []
        if st_status == "not_asked" and not stops and not rests_on:
            return "not asked"
        parts = [STOP_ANSWER_LABELS[s][0] for s in stops if s in STOP_ANSWER_LABELS]
        if rests_on:
            deps = ", ".join(f"`{d['claim_id']}` ({_format_dep_display_state(d)})" for d in rests_on)
            if parts:
                parts.append(f"E6 rests on: {deps}")
            else:
                return f"none recorded; E6 rests on: {deps}"
        if not parts:
            return "none recorded"
        return "; ".join(parts)

    claim_by_id = {c["id"]: c for c in spec["claims"]}
    for c in lv["claims"]:
        meta = claim_by_id[c["id"]]
        sig = _claim_signature(meta)
        if sig.get("kind") == "effectivenessClaim":
            endpoint = f"{sig.get('method_node')} → {sig.get('evaluation_node')} (ctrl={sig.get('control_node')}, ledger={sig.get('cost_ledger_node')})"
        elif sig.get("kind") == "theoremApplication":
            endpoint = f"{sig.get('target')} (hyps={len(sig.get('hypotheses', []))}, bets={len(sig.get('declared_bets', []))})"
        elif sig.get("kind") == "outOfScope":
            endpoint = "out-of-scope"
        else:
            endpoint = sig.get("target") or f"{sig.get('branch_a')}/{sig.get('branch_b')}"
            if "excluded_channel" in sig:
                endpoint = f"{endpoint} (excl: {sig['excluded_channel']})"
        bet_count = int(c.get("declared_bet_count", _count_declared_bets(meta)))
        stop_cell = _format_stop_table_cell(rab_by_claim.get(c["id"], {}))
        lines.append(
            f"| `{c['id']}` | `{meta['kind']}` | `{endpoint}` | **{_format_verdict_table(c['verdict'], bet_count, meta['kind'])}** | {stop_cell} | {len(c['findings'])} | `{', '.join(c['axioms']) or 'none'}` |"
        )

    lines += ["", "## Detailed Findings & Verbatim Evidence", ""]
    source_quotes = {s["node"]: s["quote"] for s in spec["sources"]}
    op_quotes = {op["name"]: op["quote"] for op in spec["ops"]}

    for c in lv["claims"]:
        meta = claim_by_id[c["id"]]
        prov = meta.get("provenance", "authorClaimed")
        bet_count = int(c.get("declared_bet_count", _count_declared_bets(meta)))
        nature_label = meta.get("nature", "qualitative")
        if nature_label == "quantitative" and meta.get("quantitative_kind"):
            nature_label = f"quantitative/{meta['quantitative_kind']}"
        lines.append(
            f"### `{c['id']}` — **{_format_verdict_heading(c['verdict'], bet_count, meta['kind'])}** (`{prov}`, `{nature_label}`)"
        )
        # D3: Reader stop answers directly under the claim heading (before findings)
        rab_claim = rab_by_claim.get(c["id"], {})
        st_status = rab_claim.get("stop_answers_status", "not_asked")
        stops = rab_claim.get("stop_answers") or []
        rests_on = rab_claim.get("rests_on") or []
        if st_status == "not_asked" and not stops and not rests_on:
            lines.append("- **Stop answers *(reader-recorded, quote-checked, not Lean-verified)*:** not asked")
        elif stops:
            lines.append("- **Stop answers *(reader-recorded, quote-checked, not Lean-verified)*:**")
            for scode in stops:
                short_lbl, desc = STOP_ANSWER_LABELS.get(scode, (scode, scode))
                lines.append(f"  - **{short_lbl} (`{scode}`):** {desc}")
            if rests_on:
                deps = ", ".join(f"`{d['claim_id']}` ({_format_dep_display_state(d)})" for d in rests_on)
                lines.append(f"  - **E6 (`rests_on`):** {deps}")
        else:
            lines.append("- **Stop answers *(reader-recorded, quote-checked, not Lean-verified)*:** none recorded")
            if rests_on:
                deps = ", ".join(f"`{d['claim_id']}` ({_format_dep_display_state(d)})" for d in rests_on)
                lines.append(f"- **Rests on (E6, *reader-recorded, quote-checked, not Lean-verified*):** {deps}")

        lines += [
            f"- **Statement:** {meta['statement']}",
            f"- **Source quote:** > {meta['quote']}",
        ]
        ka_entry = meta.get("ask_back", {}).get("kind_anchor") if isinstance(meta.get("ask_back"), dict) else None
        if isinstance(ka_entry, dict) and ka_entry.get("status") == "not_found" and not meta.get("exclusion_wording_quote"):
            cand_obj = f" (candidate excluded object: {meta['excluded_object']})" if meta.get("excluded_object") else ""
            lines.append(
                f"- **Kind anchor (E7, `not_found` — unanchored emergence/exclusion reading):** "
                f"no supporting exclusion wording quote found; searched: {ka_entry.get('searched_where', '')}{cand_obj}"
            )
            if ka_entry.get("reason"):
                lines.append(f"  - *Reason:* {ka_entry['reason']}")
        elif meta.get("exclusion_wording_quote") or meta.get("excluded_object"):
            ewq_str = f'"{meta["exclusion_wording_quote"]}"' if meta.get("exclusion_wording_quote") else "*missing*"
            eobj_str = meta.get("excluded_object") or "*missing*"
            lines.append(f"- **Kind anchor (E7, reader quote-checked):** wording {ewq_str}; excluded object: {eobj_str}")
        if meta.get("kind") == "effectivenessClaim":
            if meta.get("method_measurement_quote"):
                lines.append(f"- **Method measurement quote:** > {meta['method_measurement_quote']}")
            if meta.get("control_measurement_quote"):
                lines.append(f"- **Control measurement quote:** > {meta['control_measurement_quote']}")
            if meta.get("method_usage") or meta.get("control_usage"):
                lines.append(f"- **Out of scope (numeric/accounting):** {OUT_OF_SCOPE_ACCOUNTING}")
        decl_locs = c.get("declaration_locations") or []
        if decl_locs:
            lines.append("- **Declared assumptions / sources locations:**")
            for dl in decl_locs:
                if dl["location"] == "in_claim":
                    lines.append(
                        f"  - `{dl['item']}` (`{dl['kind']}`): declared in claim sentence (offset @{dl['char_offset']})"
                    )
                else:
                    lines.append(
                        f"  - `{dl['item']}` (`{dl['kind']}`): declared in document body (offset @{dl['char_offset']}, outside claim quote)"
                    )
        if not c["findings"]:
            if meta.get("kind") == "effectivenessClaim":
                lines.append(
                    "- **Findings:** None (structural comparison checks passed: independent control and evaluation wiring; "
                    "does NOT certify numerical ratios/values or necessity claims such as 'need')."
                )
            else:
                lines.append("- **Findings:** None (no structural alarm inside the declared observation slice; does not certify unmodeled reality).")
        else:
            lines.append("- **Findings:**")
            hyp_quotes = {h["tag"]: h["quote"] for h in meta.get("hypotheses", [])}
            for f in c["findings"]:
                lines.append(f"  - {format_finding_human(f)}")
                origin = f.get("origin") or f.get("shared") or f.get("source")
                if origin and origin in source_quotes:
                    lines.append(f"    - *Evidence (`{origin}`):* \"{source_quotes[origin]}\"")
                op_name = f.get("op")
                if op_name and op_name in op_quotes:
                    lines.append(f"    - *Evidence (`{op_name}`):* \"{op_quotes[op_name]}\"")
                hyp_tag = f.get("hypothesis")
                if hyp_tag and hyp_tag in hyp_quotes:
                    lines.append(f"    - *Evidence (`{hyp_tag}`):* \"{hyp_quotes[hyp_tag]}\"")
        ab_data = meta.get("ask_back")
        unans_details = rab_claim.get("unanswered_details") or []
        unans_codes = rab_claim.get("unanswered") or []
        if ab_data or (ab_sum.get("applicable_v25") and unans_codes):
            lines.append(
                "- **Reader's Quote-Checked Ask-Back Answers *(not Lean-verified; Lean proof covers structural flow verdict only)*:**"
            )
            if isinstance(ab_data, dict):
                ab_labels = [
                    ("causal", "E2 Causal"),
                    ("own_wording", "E3 Own wording"),
                    ("slice", "E4 Slice"),
                    ("test_inputs", "E5 Test inputs"),
                    ("rests_on", "E6 Rests on"),
                ]
                for key, label in ab_labels:
                    entry = ab_data.get(key)
                    if not isinstance(entry, dict):
                        continue
                    st = entry.get("status", "unknown")
                    if st == "not_found":
                        lines.append(f"  - **{label}** (`not_found`): searched: {entry.get('searched_where', '')}")
                        if entry.get("reason"):
                            lines.append(f"    - *Reason:* {entry['reason']}")
                    elif st == "not_applicable":
                        lines.append(f"  - **{label}** (`not_applicable`): {entry.get('reason', '')}")
                    elif st == "answered":
                        details: list[str] = []
                        if key == "causal":
                            details.append(f"rules out: {entry.get('rules_out', '')}")
                            if entry.get("supporting_ops"):
                                details.append(f"ops={entry['supporting_ops']}")
                            if entry.get("supporting_nodes"):
                                details.append(f"nodes={entry['supporting_nodes']}")
                        elif key == "own_wording":
                            details.append(f"reading=`{entry.get('reading', '')}`")
                            details.append(f"same proposition: {entry.get('same_proposition_reason', '')}")
                        elif key == "slice":
                            details.append(f"reading=`{entry.get('reading', '')}`")
                            details.append(f"reason: {entry.get('reason', '')}")
                        elif key == "test_inputs":
                            details.append(f"reading=`{entry.get('reading', '')}`")
                            details.append(f"claims_independent_test=`{entry.get('claims_independent_test')}`")
                            details.append(f"fitted: {entry.get('fitted_inputs', '')}")
                            details.append(f"compared: {entry.get('compared_output', '')}")
                            details.append(f"reason: {entry.get('reason', '')}")
                        elif key == "rests_on":
                            cids = entry.get("claim_ids", [])
                            details.append(f"claim_ids={cids}")
                            details.append(f"reason: {entry.get('reason', '')}")
                        lines.append(f"  - **{label}** (`answered`): {'; '.join(details)}")
                        if isinstance(entry.get("quote"), str):
                            lines.append(f"    - *Quote:* \"{entry['quote']}\"")
                        for q_item in entry.get("quotes", []) if isinstance(entry.get("quotes"), list) else []:
                            lines.append(f"    - *Quote:* \"{q_item}\"")
                        if key == "causal" and entry.get("reason"):
                            lines.append(f"    - *Reason:* {entry['reason']}")
            if ab_sum.get("applicable_v25") and unans_codes:
                unans_labels = [
                    f"{u['code']} ({u['field']})" if isinstance(u, dict) and u.get("field") else str(u)
                    for u in (unans_details or unans_codes)
                ]
                lines.append(f"  - **Unanswered / incomplete ask-back items:** {', '.join(unans_labels)}")
        lines.append("")

    return "\n".join(lines)


def _claim_anchor_span(doc: IngestedDocument, quote: str) -> tuple[int, int, str] | None:
    """Return `(char_start, char_end, normalized_quote)` in a single snapshot coordinate space.

    Uses `doc.dehyphenated_text` when the dehyphenated quote is found (which coincides with
    `doc.normalized_text` whenever no soft PDF line-break hyphens were joined) so exact-ws
    and dehyphenated quotes can be compared by character span overlap.
    """
    qm = verify_quote_in_document(doc, quote, path="claim_anchor")
    if not qm.matched or qm.char_offset is None:
        return None
    dehy_q = dehyphenate_and_normalize(quote)
    idx_dehy = doc.dehyphenated_text.find(dehy_q)
    if idx_dehy != -1:
        return (idx_dehy, idx_dehy + len(dehy_q), qm.normalized_quote)
    return (qm.char_offset, qm.char_offset + len(qm.normalized_quote), qm.normalized_quote)


def build_extraction_prompt(doc: IngestedDocument, auditor_name: str = "AuditorA") -> str:
    """Build a strict extraction prompt for any LLM/agent to produce a quote-grounded AuditSpec JSON."""
    return f"""You are an independent epistemological auditor.
Read the source document below and output ONLY a single valid JSON object conforming to schema `epistemic-ledger/v2.5`.

WORKFLOW (PROPOSE -> ASK -> ANSWER -> ASK AGAIN):
1. First propose claims and the operational flow graph in a `v2.5` JSON record.
2. Run `python3 -m pipeline.audit_cli ask --doc <doc> --spec <spec.json>`. It lists any unanswered ask-back questions (E2–E7) per claim without printing verdicts (exit 4 while unanswered, exit 0 when complete).
3. Answer every unanswered item using verbatim quotes from the document (or `status: "not_found"` with `searched_where`, or `status: "not_applicable"` with `reason`), and run `ask` again until exit 0.
4. Reader ask-back answers are quote-checked evidence displayed separately in the report; they are NOT labelled "Lean verified" (Lean proves only the structural flow verdict).

CRITICAL RULES:
1. Every `source`, `op`, `claim`, `method_measurement_quote`/`control_measurement_quote`, and `ask_back` quote MUST be copied VERBATIM from the document (>= 12 non-space characters; `exclusion_wording_quote` may be a shorter verbatim substring >= 3 non-space characters inside the claim's own quote). Do NOT paraphrase or invent quotes.
2. All `nodes`, `tags`, `claim.id`, and `auditor` names must be ASCII identifiers (`^[A-Za-z][A-Za-z0-9_]*$`) and NOT Lean 4 reserved keywords.
3. Every claim endpoint (`target`, `excluded_channel`, `branch_a`, `branch_b`, `method_node`, `evaluation_node`, and non-null `control_node`/`cost_ledger_node`) MUST be defined in the graph (either as a `SourceNode` or as the `output` of an `Op`).
4. Set `"provenance"` on every claim (`"authorClaimed"` or `"reviewerStressTest"`), AND declare `"nature"`: `"qualitative"` or `"quantitative"`.
   - When `"nature": "quantitative"`, you MUST also set `"quantitative_kind"` to one of:
     - `"order"` (A outperforms or uses fewer resources than B) or `"threshold"` (meets/exceeds threshold T): MUST use `kind: "effectivenessClaim"` (with optional `method_measurement_quote` / `control_measurement_quote`). Lean checks structural control presence, arm independence, evaluation wiring, and forget-proof cost-source coverage — **do NOT emit numeric `method_usage`/`control_usage`; the machine does not read or compare numbers.**
     - `"specificValue"` (a concrete numerical figure) or `"derivedComparison"` (ratios/differences computed from reported numbers, e.g. `"3x faster"` or `"12% higher"`): MUST use `kind: "outOfScope"` (an ordinary reviewer checks reported tables directly).
   - **Decompose compound quantitative/necessity sentences (e.g. `"Method A requires 5x fewer trials than Method B to pass the test"`):** record SEPARATE claims for (i) the observed order between the two evaluated runs (`effectivenessClaim`, `quantitative_kind: "order"`), (ii) any necessity assertion (`"requires"` / `"needs"` — whether the baseline genuinely cannot reach that outcome with less resource) as `theoremApplication` with an explicit hypothesis (`discharged` / `bet` / `knownFalse`), and (iii) the derived numerical ratio (`"5x fewer"`) as `outOfScope` (`quantitative_kind: "derivedComparison"`).
5. **Classify each clause by what it asserts, NOT by hedging phrases:**
   - Split multi-clause sentences into separate claims when one clause makes a direct claim and another adds a hedged generalization (e.g., `"In this setting, property P is recovered from raw signal S"` vs `"offering an initial indication that P arises spontaneously"`).
   - For emergence / `"only X"` clauses under Policy 3, prefer `kind: "emergesWithExclusion"` (`target`, `excluded_channel`, `tag`) or `kind: "emergesWithout"` (`target`, `tag`).
   - **E7 Kind Anchor (required by `ask` for `emergesWithout` / `emergesWithExclusion`):** supply `"exclusion_wording_quote"` (exact verbatim substring inside the claim's own `quote` saying a source is absent, excluded, not needed, or arises on its own, e.g. `"without external calibration"`) AND `"excluded_object"` (naming specifically what is excluded, e.g. `"external calibration inputs during inference, not during sensor manufacturing"`). If no exclusion wording exists in the claim, either reconsider the claim's `kind` or record `ask_back.kind_anchor: {{"status": "not_found", "searched_where": "..."}}` so the reading is kept and explicitly marked as having no supporting exclusion quote.
   - Do NOT downgrade an emergence clause to `conditionalFlow` merely because of a framing or hedging phrase (such as `"in this setting"`, `"suggests"`, or `"an initial indication toward"`).
   - Contrast: genuine conditional statements such as `"Given a supplied X, Y follows"` remain `kind: "conditionalFlow"`.
6. For structural effectiveness / comparison claims (`nature: "quantitative"` with `quantitative_kind: "order"` or `"threshold"`, or qualitative structural comparisons), use `kind: "effectivenessClaim"` with:
   - `method_node`, `evaluation_node`, `control_node` (or `null`), `cost_ledger_node` (or `null`), `cost_tag`
   - Optional verbatim `method_measurement_quote` and `control_measurement_quote` pointing to where each arm is evaluated/measured (no numeric parsing).
7. Tag `origin` carefully: `"setByExperimenter"` for simulators, pretrained external backbones, manual barriers/cuts, engineered objectives; `"measured"` for raw sensor observations.
8. Only mark a `"forget"` op with `evidence: "shown"` if the paper actually runs an ablation/invariance check demonstrating the conclusion survives removing that dependency; otherwise use `"notShown"` or `"contradicted"`. On `emergesWithout` and `emergesWithExclusion` claims, `"notShown"` rejects the claim (Rule 2: removing a dependency requires evidence).
9. If a claim is a normative value judgment, legal-policy balancing dispute, financial/bookkeeping question, specific numerical value, or derived numerical comparison rather than a structural causal/experimental flow claim, emit `kind: "outOfScope"` with a concise `"reason"` string explaining why it lies outside structural verification.
10. When a claim applies a mathematical theorem, formal model, or necessity condition (e.g., asserting a baseline *requires* a given resource level when only one operating point was tested) to a target object (Rule 3), use `kind: "theoremApplication"` with:
    - `target`: node receiving the theorem application
    - `hypotheses`: non-empty list of `{{"tag": "<tag>", "status": "discharged"|"bet"|"knownFalse", "quote": "<verbatim quote>"}}` (one entry per precondition)
    - `declared_bets`: list of unchecked (`"bet"`) hypothesis tags openly declared by the claim as assumptions (note: `"knownFalse"` is always rejected even if listed in `declared_bets`).
11. For `kind: "lossy"` ops, add optional `"loses": ["<tag>", ...]` ONLY when the document explicitly witnesses that distinct values of those specific tag(s) collide to identical outputs while remaining jointly valid with any outside observations; omit `"loses"` if the document only describes the step as lossy in general or if unmodeled joint constraints couple separate inputs (when two inputs share a coupling like `c = r`, derive both from one shared upstream `SourceNode` so side-information bypass is detected).
12. **Ask-back record (`ask_back`) per claim (checked by `audit_cli ask`):** every claim should answer five questions (`causal`, `own_wording`, `slice`, `test_inputs`, `rests_on`), each with `status: "answered" | "not_found" | "not_applicable"` (`rests_on` uses `"answered"` or `"not_applicable"`):
    - `causal` (E2): if answered, include `"quotes"` (or `"quote"`), `"rules_out"`, and optional `"supporting_ops"` / `"supporting_nodes"` reusing the graph.
    - `own_wording` (E3): if answered, include `"quote"` (MUST appear outside the claim's own sentence), `"same_proposition_reason"`, and `"reading": "same" | "sentence_stronger" | "sentence_weaker"`.
    - `slice` (E4): if answered, include `"quote"` (or `"quotes"`), `"reading": "within" | "beyond"`, and `"reason"`.
    - `test_inputs` (E5): answer applicability explicitly (`status: "not_applicable"` with `"reason"` if not claiming an empirical test, agreement, reproduction, or prediction); if answered, include `"quotes"` (or `"quote"`), `"fitted_inputs"`, `"compared_output"`, `"claims_independent_test"` (bool), `"reading": "independent" | "fitted_on_test_data" | "unclear"`, and `"reason"`.
    - `rests_on` (E6): `status: "answered"` with `"claim_ids"` (acyclic list of claim IDs in this record) and `"reason"` (plus optional `"quote"`), or `status: "not_applicable"` with `"reason"`.
    - For any `status: "not_found"`, provide `"searched_where"` naming the sections/appendices checked.

JSON TEMPLATE:
{{
  "schema_version": "epistemic-ledger/v2.5",
  "auditor": "{auditor_name}",
  "paper_title": "...",
  "nodes": ["nodeA", "nodeB"],
  "tags": ["tagX"],
  "sources": [
    {{"node": "nodeA", "origin": "setByExperimenter", "carries": ["tagX"], "quote": "verbatim quote from text"}}
  ],
  "ops": [
    {{"name": "step_1", "inputs": ["nodeA"], "output": "nodeB", "kind": "transform", "introduces": [], "quote": "verbatim quote from text"}}
  ],
  "claims": [
    {{
      "id": "claim1",
      "statement": "concise statement of claim",
      "quote": "Device D recovers property P without external calibration inputs.",
      "provenance": "authorClaimed",
      "nature": "qualitative",
      "kind": "emergesWithExclusion",
      "target": "nodeB",
      "excluded_channel": "nodeB",
      "tag": "tagX",
      "exclusion_wording_quote": "without external calibration",
      "excluded_object": "external calibration inputs during device readout",
      "ask_back": {{
        "causal": {{"status": "not_found", "searched_where": "Sections 2-4; no ablation isolating this mechanism was found."}},
        "own_wording": {{"status": "not_found", "searched_where": "Checked abstract and Section 5; no separate restatement found."}},
        "slice": {{"status": "answered", "quote": "verbatim slice quote from text", "reading": "within", "reason": "Claim stays within the tested synthetic benchmark."}},
        "test_inputs": {{"status": "not_applicable", "reason": "Conceptual architecture claim, not an empirical reproduction test."}},
        "rests_on": {{"status": "not_applicable", "reason": "Standalone claim."}}
      }}
    }}
  ]
}}

SOURCE DOCUMENT ({doc.source_ref}, SHA-256 {doc.sha256[:16]}):
--- BEGIN DOCUMENT ---
{doc.raw_text}
--- END DOCUMENT ---
"""
