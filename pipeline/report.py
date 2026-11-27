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
    if ft == "missingCostAccounting":
        return f"**[Missing Cost Accounting]** method `{f['method']}` lacks raw `{f['cost_tag']}` cost accounting / cost ledger"
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


def _format_verdict_table(verdict: str, declared_bet_count: int = 0, kind: str | None = None) -> str:
    if verdict == "admissible":
        if kind == "effectivenessClaim":
            return "admissible (structural comparison only; numbers & necessity unchecked)"
        if declared_bet_count > 0:
            noun = "bet" if declared_bet_count == 1 else "bets"
            return f"admissible (consistent within declared slice; rests on {declared_bet_count} declared {noun})"
        return "admissible (consistent within declared slice)"
    return verdict


def _format_verdict_heading(verdict: str, declared_bet_count: int = 0, kind: str | None = None) -> str:
    if verdict == "admissible":
        if kind == "effectivenessClaim":
            return "ADMISSIBLE (structural comparison only; numbers & necessity unchecked)"
        if declared_bet_count > 0:
            noun = "bet" if declared_bet_count == 1 else "bets"
            return f"ADMISSIBLE (consistent within declared slice; rests on {declared_bet_count} declared {noun})"
        return "ADMISSIBLE (consistent within declared slice)"
    if verdict == "unestablished":
        return "UNESTABLISHED (data/design stops at map edge)"
    if verdict == "outOfScope":
        return "OUT OF SCOPE"
    return verdict.upper()


VERDICT_STRICTNESS_RANK: dict[str, int] = {
    "rejected": 0,
    "unestablished": 1,
    "admissible": 2,
    "outOfScope": 3,
}


def strictest_verdict_of(verdicts: set[str]) -> str | None:
    """Return the strictest Lean epistemic verdict among `verdicts`
    (`rejected` > `unestablished` > `admissible` > `outOfScope`), or `None` if empty."""
    if not verdicts:
        return None
    return min(verdicts, key=lambda v: (VERDICT_STRICTNESS_RANK.get(v, 99), v))


def _claim_signature(meta: dict[str, Any]) -> dict[str, Any]:
    kind = meta.get("kind")
    sig: dict[str, Any] = {
        "kind": kind,
        "provenance": meta.get("provenance", "authorClaimed"),
        "nature": meta.get("nature", "qualitative"),
        "hedged": bool(meta.get("hedged", False)),
    }
    if meta.get("hedged") and isinstance(meta.get("hedge_quote"), str):
        sig["hedge_quote"] = normalize_whitespace(meta["hedge_quote"])
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
    ask_back_summary = evaluate_ask_back(spec)
    ask_by_cid = {c["claim_id"]: c for c in ask_back_summary.get("claims", [])}
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
            "claims": [
                {
                    "id": c.claim_id,
                    "verdict": c.verdict,
                    "findings": c.findings,
                    "axioms": c.axioms,
                    "kernel_verified": c.kernel_verified,
                    "nature": next(
                        (m.get("nature", "qualitative") for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id),
                        "qualitative",
                    ),
                    "quantitative_kind": next(
                        (m.get("quantitative_kind") for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id),
                        None,
                    ),
                    "hedged": bool(
                        next(
                            (m.get("hedged", False) for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id),
                            False,
                        )
                    ),
                    "hedge_quote": next(
                        (m.get("hedge_quote") for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id),
                        None,
                    ),
                    "exclusion_wording_quote": next(
                        (m.get("exclusion_wording_quote") for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id),
                        None,
                    ),
                    "excluded_object": next(
                        (m.get("excluded_object") for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id),
                        None,
                    ),
                    "ask_back": next(
                        (m.get("ask_back") for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id),
                        None,
                    ),
                    "ask_back_complete": bool(ask_by_cid.get(c.claim_id, {}).get("complete", True)),
                    "ask_back_unanswered": [
                        u["code"] for u in ask_by_cid.get(c.claim_id, {}).get("unanswered", [])
                    ],
                    "declared_bet_count": _count_declared_bets(
                        next((m for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id), {})
                    ),
                    "declaration_locations": _compute_declaration_locations(
                        doc,
                        spec,
                        next((m for m in spec.get("claims", []) if isinstance(m, dict) and m.get("id") == c.claim_id), {}),
                    ),
                }
                for c in lean_result.claims
            ],
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
    if ab_sum.get("applicable_v25"):
        if ab_sum.get("complete"):
            lines.append("- **Ask-Back Completeness:** COMPLETE (all E2–E7 questions answered; reader answers are quote-checked evidence, not Lean-verified)")
        else:
            lines.append(
                f"- **Ask-Back Completeness:** INCOMPLETE ({ab_sum['unanswered_count']} unanswered question(s); "
                f"structural Lean verdict still produced — run `audit_cli ask` to inspect open questions)"
            )
    if report.get("out_of_scope"):
        lines += ["", "## Out of Scope", ""]
        for item in report["out_of_scope"]:
            lines.append(f"- {item}")
    lines += ["", "## Claim Verdicts", "", "| Claim ID | Kind | Target / Channel | Verdict | Findings | Axioms |", "|---|---|---|---|---|---|"]

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
        lines.append(
            f"| `{c['id']}` | `{meta['kind']}` | `{endpoint}` | **{_format_verdict_table(c['verdict'], bet_count, meta['kind'])}** | {len(c['findings'])} | `{', '.join(c['axioms']) or 'none'}` |"
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
        hedged_suffix = ", hedged" if meta.get("hedged") else ""
        lines += [
            f"### `{c['id']}` — **{_format_verdict_heading(c['verdict'], bet_count, meta['kind'])}** (`{prov}`, `{nature_label}`{hedged_suffix})",
            f"- **Statement:** {meta['statement']}",
            f"- **Source quote:** > {meta['quote']}",
        ]
        if meta.get("hedged") and meta.get("hedge_quote"):
            lines.append(f"- **Hedge quote:** > {meta['hedge_quote']}")
        if meta.get("exclusion_wording_quote") or meta.get("excluded_object"):
            ewq_str = f'"{meta["exclusion_wording_quote"]}"' if meta.get("exclusion_wording_quote") else "*missing*"
            eobj_str = meta.get("excluded_object") or "*missing*"
            lines.append(f"- **Kind anchor (E7, reader quote-checked):** wording {ewq_str}; excluded object: {eobj_str}")
        elif isinstance(meta.get("ask_back"), dict) and isinstance(meta["ask_back"].get("kind_anchor"), dict):
            ka = meta["ask_back"]["kind_anchor"]
            if ka.get("status") == "not_found":
                lines.append(
                    f"- **Kind anchor (E7, `not_found` — unanchored emergence/exclusion reading):** "
                    f"no supporting exclusion wording quote found; searched: {ka.get('searched_where', '')}"
                )
                if ka.get("reason"):
                    lines.append(f"  - *Reason:* {ka['reason']}")
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
                    "- **Findings:** None (structural comparison checks passed: independent control, evaluation wiring, "
                    "and forget-proof cost-source coverage; does NOT certify numerical ratios/values or necessity claims such as 'need')."
                )
            else:
                lines.append("- **Findings:** None (consistent within the declared observation slice; does not certify unmodeled reality).")
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
        unans_codes = c.get("ask_back_unanswered") or []
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
                lines.append(f"  - **Unanswered ask-back items:** {', '.join(unans_codes)}")
        lines.append("")

    return "\n".join(lines)


SPAN_OVERLAP_IOU_THRESHOLD = 0.5


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


def _span_iou(span_a: tuple[int, int], span_b: tuple[int, int]) -> float:
    inter = max(0, min(span_a[1], span_b[1]) - max(span_a[0], span_b[0]))
    if inter <= 0:
        return 0.0
    union = max(span_a[1], span_b[1]) - min(span_a[0], span_b[0])
    return inter / union if union > 0 else 0.0


def build_comparison_report(
    doc: IngestedDocument, reports: list[dict[str, Any]], specs: list[dict[str, Any]]
) -> tuple[dict[str, Any], str]:
    """Compare 2+ auditor reports on the same document snapshot.

    Claims are aligned by an order-independent connected-component clustering of quote
    character spans where an undirected edge exists iff `IoU(span_a, span_b) > 0.5`.
    Within each component, true all-pairs `min_span_iou` is computed:
    - If every pair exceeds `0.5` (a complete clique), claims reconcile normally
      (`exact` when all quotes are identical, `span_overlap` otherwise).
    - If a spanning quote bridges two quotes whose pairwise `IoU <= 0.5`, the component is
      flagged `AMBIGUOUS` (`quote_match_mode = "ambiguous_span_chain"`, `verdicts_agree = False`)
      identically under every permutation of `--spec` order.
    Every claim emitted by an auditor in a component is preserved as a list (multiple claims
    from one auditor are also flagged `AMBIGUOUS`).
    """
    auditors = [r["auditor"] for r in reports]
    all_grounding_ok = all(r["grounding_and_schema_ok"] for r in reports)

    # Collect all verified claim items across auditors
    items: list[dict[str, Any]] = []
    for rep, spec in zip(reports, specs):
        aud = rep["auditor"]
        lv = rep.get("lean_verification")
        if not rep["grounding_and_schema_ok"] or lv is None:
            continue
        claim_meta_by_id = {c["id"]: c for c in spec["claims"]}
        for c in lv["claims"]:
            meta = claim_meta_by_id[c["id"]]
            anchor = _claim_anchor_span(doc, meta["quote"])
            if anchor is None:
                continue
            start, end, norm_quote = anchor
            items.append(
                {
                    "auditor": aud,
                    "span": (start, end),
                    "quote": norm_quote,
                    "claim": {
                        "claim_id": c["id"],
                        "verdict": c["verdict"],
                        "quote": norm_quote,
                        "span": [start, end],
                        "signature": _claim_signature(meta),
                        "finding_types": [f["type"] for f in c["findings"]],
                        "findings": c["findings"],
                    },
                }
            )

    # Order-independent connected components under undirected edge `IoU > 0.5`
    n = len(items)
    visited = [False] * n
    components: list[list[dict[str, Any]]] = []
    for i in range(n):
        if visited[i]:
            continue
        comp_indices: list[int] = []
        stack = [i]
        visited[i] = True
        while stack:
            cur = stack.pop()
            comp_indices.append(cur)
            for j in range(n):
                if not visited[j] and _span_iou(items[cur]["span"], items[j]["span"]) > SPAN_OVERLAP_IOU_THRESHOLD:
                    visited[j] = True
                    stack.append(j)
        components.append([items[k] for k in comp_indices])

    # Sort components deterministically by canonical (min_start, min_end, min_quote)
    def _comp_canon(comp: list[dict[str, Any]]) -> tuple[int, int, str]:
        best = min(comp, key=lambda it: (it["span"][0], it["span"][1], it["quote"]))
        return (best["span"][0], best["span"][1], best["quote"])

    components.sort(key=_comp_canon)

    rows: list[dict[str, Any]] = []
    for idx, comp in enumerate(components, 1):
        char_offset, char_end, norm_quote = _comp_canon(comp)
        quotes_seen = {it["quote"] for it in comp}
        if len(comp) <= 1:
            min_pairwise_iou = 1.0
        else:
            min_pairwise_iou = min(
                _span_iou(comp[a]["span"], comp[b]["span"])
                for a in range(len(comp))
                for b in range(a + 1, len(comp))
            )
        is_clique = min_pairwise_iou > SPAN_OVERLAP_IOU_THRESHOLD
        if len(quotes_seen) == 1:
            quote_match_mode = "exact"
        elif is_clique:
            quote_match_mode = "span_overlap"
        else:
            quote_match_mode = "ambiguous_span_chain"
        min_span_iou = round(min_pairwise_iou, 4)

        by_aud_claims: dict[str, list[dict[str, Any]]] = {}
        for it in comp:
            by_aud_claims.setdefault(it["auditor"], []).append(it["claim"])
        for aud_key in by_aud_claims:
            by_aud_claims[aud_key].sort(key=lambda c: (c["span"][0], c["span"][1], c["claim_id"], c["verdict"]))

        by_aud: dict[str, Any] = {}
        verdicts: set[str] = set()
        kinds: set[str] = set()
        targets: set[str] = set()
        tags: set[str] = set()
        excluded_channels: set[str] = set()
        declared_source_sets: set[tuple[str, ...]] = set()
        effectiveness_controls: set[tuple[str, str]] = set()
        provenances: set[str] = set()
        hedged_flags: set[bool] = set()
        hedge_quotes: set[str] = set()
        nature_signatures: set[tuple[str, str]] = set()
        hypothesis_signatures: set[str] = set()
        declared_bet_sets: set[tuple[str, ...]] = set()
        missing_or_unverified = False
        ambiguous_multi_claim = False

        for rep in reports:
            aud = rep["auditor"]
            if not rep["grounding_and_schema_ok"] or rep.get("lean_verification") is None:
                by_aud[aud] = {"status": "UNVERIFIED", "claims": []}
                missing_or_unverified = True
            elif aud not in by_aud_claims:
                by_aud[aud] = {"status": "UNMATCHED", "claims": []}
                missing_or_unverified = True
            else:
                clist = by_aud_claims[aud]
                if len(clist) > 1:
                    ambiguous_multi_claim = True
                    by_aud[aud] = {"status": "AMBIGUOUS_MULTI_CLAIM", "claims": clist}
                else:
                    info = clist[0]
                    by_aud[aud] = {"status": "VERIFIED", "claims": clist, **info}
                for info in clist:
                    verdicts.add(info["verdict"])
                    sig = info["signature"]
                    kinds.add(str(sig.get("kind")))
                    provenances.add(str(sig.get("provenance", "authorClaimed")))
                    hedged_flags.add(bool(sig.get("hedged", False)))
                    hedge_quotes.add(str(sig.get("hedge_quote", "")))
                    nature_signatures.add((str(sig.get("nature", "qualitative")), str(sig.get("quantitative_kind", ""))))
                    if sig.get("kind") == "effectivenessClaim":
                        tgt = f"{sig.get('method_node')}->{sig.get('evaluation_node')}"
                        tags.add(str(sig.get("cost_tag", "")))
                        effectiveness_controls.add((str(sig.get("control_node")), str(sig.get("cost_ledger_node"))))
                    elif sig.get("kind") == "theoremApplication":
                        tgt = str(sig.get("target"))
                        tags.add("")
                        effectiveness_controls.add(("", ""))
                    elif sig.get("kind") == "outOfScope":
                        tgt = "out-of-scope"
                        tags.add("")
                        effectiveness_controls.add(("", ""))
                    else:
                        tgt = str(sig.get("target") or f"{sig.get('branch_a')}/{sig.get('branch_b')}")
                        tags.add(str(sig.get("tag", "")))
                        effectiveness_controls.add(("", ""))
                    targets.add(tgt)
                    excluded_channels.add(str(sig.get("excluded_channel", "")))
                    declared_source_sets.add(tuple(sorted(set(sig.get("declared_sources", [])))))
                    hypothesis_signatures.add(json.dumps(sig.get("hypotheses", []), sort_keys=True))
                    declared_bet_sets.add(tuple(sorted(set(sig.get("declared_bets", [])))))

        if missing_or_unverified:
            status = "UNVERIFIED_OR_UNMATCHED"
            verdicts_agree = False
        elif ambiguous_multi_claim or not is_clique:
            status = "AMBIGUOUS"
            verdicts_agree = False
        elif len(verdicts) == 1:
            status = "AGREE"
            verdicts_agree = True
        else:
            status = "DISAGREE"
            verdicts_agree = False

        complete_1to1 = (not missing_or_unverified) and (not ambiguous_multi_claim) and is_clique
        strictest = strictest_verdict_of(verdicts) if complete_1to1 else None
        rows.append(
            {
                "anchor_index": idx,
                "char_offset": char_offset,
                "char_end": char_end,
                "claim_quote": norm_quote,
                "quote_match_mode": quote_match_mode,
                "min_span_iou": min_span_iou,
                "status": status,
                "strictest_verdict": strictest,
                "verdicts_agree": verdicts_agree,
                "same_claim_kind": complete_1to1 and len(kinds) == 1,
                "same_target_name": complete_1to1 and len(targets) == 1,
                "same_tag": complete_1to1 and len(tags) == 1,
                "same_excluded_channel": complete_1to1 and len(excluded_channels) == 1,
                "same_declared_sources": complete_1to1 and len(declared_source_sets) == 1,
                "same_control_and_ledger": complete_1to1 and len(effectiveness_controls) == 1,
                "same_provenance": complete_1to1 and len(provenances) == 1,
                "same_hedged": complete_1to1 and len(hedged_flags) == 1,
                "same_hedge_quote": complete_1to1 and len(hedge_quotes) == 1,
                "same_nature": complete_1to1 and len(nature_signatures) == 1,
                "same_hypotheses": complete_1to1 and len(hypothesis_signatures) == 1,
                "same_declared_bets": complete_1to1 and len(declared_bet_sets) == 1,
                "by_auditor": by_aud,
            }
        )

    source_summary = {}
    for rep, spec in zip(reports, specs):
        aud = rep["auditor"]
        if rep["grounding_and_schema_ok"] and isinstance(spec, dict):
            source_summary[aud] = {
                "declared_auditor": rep.get("declared_auditor"),
                "sources": {
                    s["node"]: {"origin": s["origin"], "carries": s["carries"]} for s in spec.get("sources", [])
                },
            }
        else:
            source_summary[aud] = {"declared_auditor": rep.get("declared_auditor"), "error": "unverified"}

    combined_out_of_scope: list[str] = []
    for rep in reports:
        for item in rep.get("out_of_scope", []):
            if item not in combined_out_of_scope:
                combined_out_of_scope.append(item)

    ask_back_by_auditor = {
        rep["auditor"]: rep.get("ask_back_summary", {"applicable_v25": False, "complete": True, "unanswered_count": 0})
        for rep in reports
    }
    comp_dict = {
        "schema_version": "epistemic-ledger-comparison/v2.2",
        "document": {"source_ref": doc.source_ref, "sha256": doc.sha256},
        "auditors": auditors,
        "all_grounding_ok": all_grounding_ok,
        "ask_back_by_auditor": ask_back_by_auditor,
        "out_of_scope": combined_out_of_scope,
        "claim_comparison": rows,
        "sources_by_auditor": source_summary,
    }

    md: list[str] = [
        f"# Multi-Auditor Epistemic Comparison — `{doc.source_ref}`",
        "",
        f"- **Document SHA-256:** `{doc.sha256[:16]}...`",
        f"- **Auditors:** {', '.join(f'`{a}`' for a in auditors)}",
        f"- **All Grounding & Schema Checks Passed:** `{all_grounding_ok}`",
        "- **Matching Rule:** Claims are aligned via order-independent connected components of verbatim quote spans (`IoU > 0.5`); cliques reconcile as `exact`/`span_overlap`, while non-clique bridged chains (`pairwise min IoU <= 0.5`) and multi-claim anchors are flagged `AMBIGUOUS`.",
        "",
    ]
    incomplete_auds = [
        f"`{a}` ({info['unanswered_count']} unanswered)"
        for a, info in ask_back_by_auditor.items()
        if info.get("applicable_v25") and not info.get("complete", True)
    ]
    if incomplete_auds:
        md.insert(
            5,
            f"- **Ask-Back Status:** INCOMPLETE for {', '.join(incomplete_auds)} "
            "(structural Lean comparison still produced; ask-back answers are reader evidence, not Lean-verified).",
        )

    if combined_out_of_scope:
        md += ["## Out of Scope", ""]
        for item in combined_out_of_scope:
            md.append(f"- {item}")
        md.append("")

    if not all_grounding_ok:
        md += ["## Unverified Auditors (Grounding / Schema Failed)", ""]
        for rep in reports:
            if not rep["grounding_and_schema_ok"]:
                md.append(
                    f"- **`{rep['auditor']}`:** UNVERIFIED ({len(rep['validation_errors'])} validation/grounding error(s))"
                )
        md.append("")

    md += [
        "## Claim Verdict Reconciliation",
        "",
        "| # | Quote Anchor (offset) | Status | Strictest | " + " | ".join(f"`{a}`" for a in auditors) + " |",
        "|---|---|---|---|" + "|".join("---" for _ in auditors) + "|",
    ]

    def _fmt_claim_cell(info: dict[str, Any]) -> str:
        sig = info["signature"]
        extras = []
        if sig.get("kind") == "effectivenessClaim":
            tgt = f"{sig.get('method_node')}→{sig.get('evaluation_node')}"
            extras.append(f"ctrl={sig.get('control_node')}")
            extras.append(f"ledger={sig.get('cost_ledger_node')}")
            extras.append(f"cost_tag={sig.get('cost_tag')}")
        elif sig.get("kind") == "theoremApplication":
            tgt = str(sig.get("target"))
            hyps_str = ", ".join(f"{h['tag']}={h['status']}" for h in sig.get("hypotheses", []))
            extras.append(f"hyps=[{hyps_str}]")
            if sig.get("declared_bets"):
                extras.append(f"bets={sorted(set(sig['declared_bets']))}")
        elif sig.get("kind") == "outOfScope":
            tgt = "out-of-scope"
        else:
            tgt = sig.get("target") or f"{sig.get('branch_a')}/{sig.get('branch_b')}"
            if "tag" in sig:
                extras.append(f"tag={sig['tag']}")
            if "excluded_channel" in sig:
                extras.append(f"excl={sig['excluded_channel']}")
            if "declared_sources" in sig:
                extras.append(f"declared={sorted(set(sig['declared_sources']))}")
        if sig.get("hedged") and sig.get("hedge_quote"):
            hq_short = sig["hedge_quote"].replace("|", "\\|")
            extras.append(f'hedged="{hq_short}"')
        extra_str = (", " + ", ".join(extras)) if extras else ""
        ftypes = ", ".join(info["finding_types"]) or "clean"
        bet_count = _count_declared_bets(sig)
        return f"**{_format_verdict_table(info['verdict'], bet_count, sig.get('kind'))}** (`{info['claim_id']}`: `{sig['kind']}` on `{tgt}`{extra_str}; {ftypes})"

    for row in rows:
        q_short = row["claim_quote"]
        if len(q_short) > 64:
            q_short = q_short[:61] + "..."
        q_short = q_short.replace("|", "\\|")
        status_cell = f"**{row['status']}**"
        if row["verdicts_agree"]:
            diffs = []
            if not row["same_claim_kind"]:
                diffs.append("kind")
            if not row["same_target_name"]:
                diffs.append("target")
            if not row["same_tag"]:
                diffs.append("tag")
            if not row["same_excluded_channel"]:
                diffs.append("excluded_channel")
            if not row["same_declared_sources"]:
                diffs.append("declared_sources")
            if not row["same_control_and_ledger"]:
                diffs.append("control/ledger")
            if not row["same_provenance"]:
                diffs.append("provenance")
            if not row.get("same_hedged", True):
                diffs.append("hedged")
            if not row.get("same_hedge_quote", True):
                diffs.append("hedge_quote")
            if not row.get("same_nature", True):
                diffs.append("nature")
            if not row.get("same_hypotheses", True):
                diffs.append("hypotheses")
            if not row.get("same_declared_bets", True):
                diffs.append("declared_bets")
            if diffs:
                status_cell += f" ({'/'.join(diffs)} differs)"
        strictest_cell = f"**{row['strictest_verdict']}**" if row.get("strictest_verdict") else "*—*"
        cells = []
        for a in auditors:
            entry = row["by_auditor"][a]
            if entry["status"] in ("UNVERIFIED", "UNMATCHED"):
                cells.append(f"*{entry['status']}*")
            else:
                cells.append("; ".join(_fmt_claim_cell(c) for c in entry["claims"]))
        anchor_label = f"@{row['char_offset']}: \"{q_short}\""
        if row.get("quote_match_mode") == "span_overlap":
            anchor_label += f" *(span overlap, pairwise min IoU={row['min_span_iou']:.2f})*"
        elif row.get("quote_match_mode") == "ambiguous_span_chain":
            anchor_label += f" *(ambiguous span chain, pairwise min IoU={row['min_span_iou']:.2f})*"
        md.append(
            f"| {row['anchor_index']} | {anchor_label} | {status_cell} | {strictest_cell} | "
            + " | ".join(cells)
            + " |"
        )

    md += ["", "## Disagreements & Unverified Items Requiring Human Review", ""]
    if not rows:
        md.append("- **UNVERIFIED:** No grounded claims were available to compare.")
    else:
        issues = [
            r
            for r in rows
            if not r["verdicts_agree"]
            or not r["same_claim_kind"]
            or not r["same_target_name"]
            or not r["same_tag"]
            or not r["same_excluded_channel"]
            or not r["same_declared_sources"]
            or not r["same_control_and_ledger"]
            or not r["same_provenance"]
            or not r.get("same_hedged", True)
            or not r.get("same_hedge_quote", True)
            or not r.get("same_nature", True)
            or not r.get("same_hypotheses", True)
            or not r.get("same_declared_bets", True)
        ]
        if not issues and all_grounding_ok:
            md.append(
                "- None: all auditors passed grounding and reached identical Lean-verified verdicts and full claim signatures on every matched claim."
            )
        else:
            for row in issues:
                md.append(
                    f"- **Claim #{row['anchor_index']} (@{row['char_offset']} — {row['status']}):** \"{row['claim_quote']}\""
                )
                for a in auditors:
                    entry = row["by_auditor"][a]
                    if entry["status"] in ("UNVERIFIED", "UNMATCHED"):
                        md.append(f"  - `{a}` → *{entry['status']}*")
                    else:
                        for info in entry["claims"]:
                            md.append(f"  - `{a}` (`{info['claim_id']}`, `{info['signature']}`) → **{info['verdict']}**")
                            for f in info.get("findings", []):
                                md.append(f"    - {format_finding_human(f)}")

    return comp_dict, "\n".join(md) + "\n"


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
1. Every `source`, `op`, `claim`, `hedge_quote`, `method_measurement_quote`/`control_measurement_quote`, and `ask_back` quote MUST be copied VERBATIM from the document (>= 12 non-space characters; `exclusion_wording_quote` may be a shorter verbatim substring >= 3 non-space characters inside the claim's own quote). Do NOT paraphrase or invent quotes.
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
   - Do NOT downgrade an emergence clause to `conditionalFlow` merely because of a framing or hedging phrase (such as `"in this setting"`, `"suggests"`, or `"an initial indication toward"`). Attach `"hedged": true` with verbatim `"hedge_quote"` (>= 12 non-space chars, inside the claim's own `quote`) ONLY to the specific clause that the hedge modifies (display-only metadata; does not alter Lean verdicts).
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
