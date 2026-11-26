"""Reporting, quote-anchored multi-auditor reconciliation, and LLM extraction prompt generation."""

from __future__ import annotations

import json
from typing import Any

from pipeline.ingest import IngestedDocument
from pipeline.lean_runner import LeanVerificationResult
from pipeline.schema import (
    QuoteMatch,
    ValidationErrorItem,
    collect_out_of_scope_spec_fields,
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
        return f"**[Lossy Channel]** many-to-one op `{f['op']}` at `{f['output']}` blocks unique recovery"
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
    if ft == "unquantifiedBudget":
        return f"**[Unquantified Budget]** `{f['method']}` lacks numeric `{f['cost_tag']}` resource usage quantities for both arms"
    if ft == "unboundUsageSource":
        return f"**[Unbound Usage Source]** usage entry for `{f['arm']}` fails to match raw `{f['cost_tag']}` source `{f['source']}`"
    if ft == "unmatchedControlBudget":
        return f"**[Unmatched Control Budget]** numeric `{f['cost_tag']}` budgets differ between `{f['method']}` and `{f['control']}`"
    if ft == "claimOutOfScope":
        return f"**[Out of Scope]** {f['reason']}"
    return json.dumps(f)


def _format_verdict_table(verdict: str) -> str:
    if verdict == "admissible":
        return "admissible (consistent within declared slice)"
    return verdict


def _format_verdict_heading(verdict: str) -> str:
    if verdict == "admissible":
        return "ADMISSIBLE (consistent within declared slice)"
    if verdict == "unestablished":
        return "UNESTABLISHED (data/design stops at map edge)"
    if verdict == "outOfScope":
        return "OUT OF SCOPE"
    return verdict.upper()


def _norm_usage_key(usages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "source": u.get("source"),
                "dimension": u.get("dimension"),
                "unit": u.get("unit"),
                "amount": u.get("amount"),
            }
            for u in usages
        ],
        key=lambda x: (str(x["source"]), str(x["dimension"]), str(x["unit"]), int(x["amount"] or 0)),
    )


def _claim_signature(meta: dict[str, Any]) -> dict[str, Any]:
    kind = meta.get("kind")
    sig: dict[str, Any] = {
        "kind": kind,
        "provenance": meta.get("provenance", "authorClaimed"),
    }
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
        "reason",
    ):
        if k in meta:
            sig[k] = meta[k]
    if "method_usage" in meta:
        sig["method_usage"] = _norm_usage_key(meta["method_usage"])
    if "control_usage" in meta:
        sig["control_usage"] = _norm_usage_key(meta["control_usage"])
    return sig


OUT_OF_SCOPE_CORE = (
    "Semantic interpretation of quotes (whether a quote justifies a tag, causal edge, or statistical test) "
    "is out of scope for Lean verification and requires auditor/human review."
)
OUT_OF_SCOPE_ACCOUNTING = (
    "Financial/bookkeeping verification (invoice reconciliation, billing-period completeness, "
    "actual-vs-requested prose semantics, and cross-document deduplication) is out of scope for "
    "EpistemicLedger; Lean checks structural control independence, forget-proof cost-source coverage, "
    "and arithmetic parity of declared (source, unit, amount) entries."
)


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
    oos_claim_ids = [
        str(c.get("id"))
        for c in (spec.get("claims", []) if isinstance(spec, dict) else [])
        if isinstance(c, dict) and c.get("kind") == "outOfScope" and c.get("id")
    ]
    out_of_scope = [OUT_OF_SCOPE_CORE]
    if has_effectiveness:
        out_of_scope.append(OUT_OF_SCOPE_ACCOUNTING)
    if oos_claim_ids:
        out_of_scope.append(
            f"Explicitly out-of-scope claim(s) ({', '.join(oos_claim_ids)}): "
            "declared outside structural operation-flow verification (e.g., normative, legal-policy, or value-balancing disputes)."
        )
    ignored_fields = collect_out_of_scope_spec_fields(spec)
    if ignored_fields:
        out_of_scope.append(
            f"Ignored out-of-scope accounting/bookkeeping fields in spec ({', '.join(ignored_fields)}): "
            "not evaluated by Lean; financial/bookkeeping checks require human review."
        )
    return {
        "schema_version": "epistemic-ledger-report/v2.1",
        "document": {
            "source_ref": doc.source_ref,
            "resolved_path": str(doc.resolved_path),
            "sha256": doc.sha256,
        },
        "auditor": auditor_label or declared_auditor,
        "declared_auditor": declared_auditor,
        "paper_title": spec.get("paper_title", "") if isinstance(spec, dict) else "",
        "grounding_and_schema_ok": len(errors) == 0,
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
    lines.append(f"- **Lean 4 Kernel Proof:** `{lv['lean_file']}` (axioms whitelist OK: `{lv['axioms_ok']}`)")
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
        elif sig.get("kind") == "outOfScope":
            endpoint = "out-of-scope"
        else:
            endpoint = sig.get("target") or f"{sig.get('branch_a')}/{sig.get('branch_b')}"
            if "excluded_channel" in sig:
                endpoint = f"{endpoint} (excl: {sig['excluded_channel']})"
        lines.append(
            f"| `{c['id']}` | `{meta['kind']}` | `{endpoint}` | **{_format_verdict_table(c['verdict'])}** | {len(c['findings'])} | `{', '.join(c['axioms']) or 'none'}` |"
        )

    lines += ["", "## Detailed Findings & Verbatim Evidence", ""]
    source_quotes = {s["node"]: s["quote"] for s in spec["sources"]}
    op_quotes = {op["name"]: op["quote"] for op in spec["ops"]}

    for c in lv["claims"]:
        meta = claim_by_id[c["id"]]
        prov = meta.get("provenance", "authorClaimed")
        lines += [
            f"### `{c['id']}` — **{_format_verdict_heading(c['verdict'])}** (`{prov}`)",
            f"- **Statement:** {meta['statement']}",
            f"- **Source quote:** > {meta['quote']}",
        ]
        if meta.get("kind") == "effectivenessClaim" and (meta.get("method_usage") or meta.get("control_usage")):
            lines.append(f"- **Out of scope (accounting/bookkeeping):** {OUT_OF_SCOPE_ACCOUNTING}")
        if not c["findings"]:
            lines.append("- **Findings:** None (consistent within the declared observation slice; does not certify unmodeled reality).")
        else:
            lines.append("- **Findings:**")
            for f in c["findings"]:
                lines.append(f"  - {format_finding_human(f)}")
                origin = f.get("origin") or f.get("shared") or f.get("source")
                if origin and origin in source_quotes:
                    lines.append(f"    - *Evidence (`{origin}`):* \"{source_quotes[origin]}\"")
                op_name = f.get("op")
                if op_name and op_name in op_quotes:
                    lines.append(f"    - *Evidence (`{op_name}`):* \"{op_quotes[op_name]}\"")
        lines.append("")

    return "\n".join(lines)


def _claim_anchor_key(doc: IngestedDocument, quote: str) -> tuple[int, str] | None:
    qm = verify_quote_in_document(doc, quote, path="claim_anchor")
    if not qm.matched or qm.char_offset is None:
        return None
    return (qm.char_offset, qm.normalized_quote)


def build_comparison_report(
    doc: IngestedDocument, reports: list[dict[str, Any]], specs: list[dict[str, Any]]
) -> tuple[dict[str, Any], str]:
    """Compare 2+ auditor reports on the same document snapshot.

    Claims are aligned by verbatim quote location `(char_offset, normalized_quote)`.
    Every claim emitted by an auditor for a given quote is preserved as a list (never
    overwritten): if any auditor attaches multiple claims to the same quote, the row is
    marked `AMBIGUOUS` (`verdicts_agree = False`) and all claims are shown.
    Full claim signatures (`kind`, `target`, `tag`, `excluded_channel`) are also compared.
    """
    auditors = [r["auditor"] for r in reports]
    all_grounding_ok = all(r["grounding_and_schema_ok"] for r in reports)

    # Index verified claims per (anchor, auditor) as a LIST so no claim is ever dropped
    anchor_order: list[tuple[int, str]] = []
    anchor_to_auditor_claims: dict[tuple[int, str], dict[str, list[dict[str, Any]]]] = {}

    for rep, spec in zip(reports, specs):
        aud = rep["auditor"]
        lv = rep.get("lean_verification")
        if not rep["grounding_and_schema_ok"] or lv is None:
            continue
        claim_meta_by_id = {c["id"]: c for c in spec["claims"]}
        for c in lv["claims"]:
            meta = claim_meta_by_id[c["id"]]
            anchor = _claim_anchor_key(doc, meta["quote"])
            if anchor is None:
                continue
            if anchor not in anchor_to_auditor_claims:
                anchor_order.append(anchor)
                anchor_to_auditor_claims[anchor] = {}
            anchor_to_auditor_claims[anchor].setdefault(aud, []).append(
                {
                    "claim_id": c["id"],
                    "verdict": c["verdict"],
                    "signature": _claim_signature(meta),
                    "finding_types": [f["type"] for f in c["findings"]],
                    "findings": c["findings"],
                }
            )

    rows: list[dict[str, Any]] = []
    for idx, anchor in enumerate(anchor_order, 1):
        char_offset, norm_quote = anchor
        by_aud: dict[str, Any] = {}
        verdicts: set[str] = set()
        kinds: set[str] = set()
        targets: set[str] = set()
        tags: set[str] = set()
        excluded_channels: set[str] = set()
        declared_source_sets: set[tuple[str, ...]] = set()
        effectiveness_controls: set[tuple[str, str]] = set()
        provenances: set[str] = set()
        usage_signatures: set[str] = set()
        missing_or_unverified = False
        ambiguous_multi_claim = False

        for rep in reports:
            aud = rep["auditor"]
            if not rep["grounding_and_schema_ok"] or rep.get("lean_verification") is None:
                by_aud[aud] = {"status": "UNVERIFIED", "claims": []}
                missing_or_unverified = True
            elif aud not in anchor_to_auditor_claims[anchor]:
                by_aud[aud] = {"status": "UNMATCHED", "claims": []}
                missing_or_unverified = True
            else:
                clist = anchor_to_auditor_claims[anchor][aud]
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
                    if sig.get("kind") == "effectivenessClaim":
                        tgt = f"{sig.get('method_node')}->{sig.get('evaluation_node')}"
                        tags.add(str(sig.get("cost_tag", "")))
                        effectiveness_controls.add((str(sig.get("control_node")), str(sig.get("cost_ledger_node"))))
                        usage_signatures.add(
                            json.dumps(
                                {"m": sig.get("method_usage", []), "c": sig.get("control_usage", [])},
                                sort_keys=True,
                            )
                        )
                    elif sig.get("kind") == "outOfScope":
                        tgt = "out-of-scope"
                        tags.add("")
                        effectiveness_controls.add(("", ""))
                        usage_signatures.add("")
                    else:
                        tgt = str(sig.get("target") or f"{sig.get('branch_a')}/{sig.get('branch_b')}")
                        tags.add(str(sig.get("tag", "")))
                        effectiveness_controls.add(("", ""))
                        usage_signatures.add("")
                    targets.add(tgt)
                    excluded_channels.add(str(sig.get("excluded_channel", "")))
                    declared_source_sets.add(tuple(sorted(set(sig.get("declared_sources", [])))))

        if missing_or_unverified:
            status = "UNVERIFIED_OR_UNMATCHED"
            verdicts_agree = False
        elif ambiguous_multi_claim:
            status = "AMBIGUOUS"
            verdicts_agree = False
        elif len(verdicts) == 1:
            status = "AGREE"
            verdicts_agree = True
        else:
            status = "DISAGREE"
            verdicts_agree = False

        complete_1to1 = (not missing_or_unverified) and (not ambiguous_multi_claim)
        rows.append(
            {
                "anchor_index": idx,
                "char_offset": char_offset,
                "claim_quote": norm_quote,
                "status": status,
                "verdicts_agree": verdicts_agree,
                "same_claim_kind": complete_1to1 and len(kinds) == 1,
                "same_target_name": complete_1to1 and len(targets) == 1,
                "same_tag": complete_1to1 and len(tags) == 1,
                "same_excluded_channel": complete_1to1 and len(excluded_channels) == 1,
                "same_declared_sources": complete_1to1 and len(declared_source_sets) == 1,
                "same_control_and_ledger": complete_1to1 and len(effectiveness_controls) == 1,
                "same_provenance": complete_1to1 and len(provenances) == 1,
                "same_usage": complete_1to1 and len(usage_signatures) == 1,
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

    comp_dict = {
        "schema_version": "epistemic-ledger-comparison/v2.1",
        "document": {"source_ref": doc.source_ref, "sha256": doc.sha256},
        "auditors": auditors,
        "all_grounding_ok": all_grounding_ok,
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
        "- **Matching Rule:** Claims are aligned strictly by verbatim quote location `(char_offset, normalized_quote)` in this snapshot, preserving all claims per quote (multiple claims on one quote are flagged `AMBIGUOUS`).",
        "",
    ]

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
        "| # | Quote Anchor (offset) | Status | " + " | ".join(f"`{a}`" for a in auditors) + " |",
        "|---|---|---|" + "|".join("---" for _ in auditors) + "|",
    ]

    def _fmt_claim_cell(info: dict[str, Any]) -> str:
        sig = info["signature"]
        extras = []
        if sig.get("kind") == "effectivenessClaim":
            tgt = f"{sig.get('method_node')}→{sig.get('evaluation_node')}"
            extras.append(f"ctrl={sig.get('control_node')}")
            extras.append(f"ledger={sig.get('cost_ledger_node')}")
            extras.append(f"cost_tag={sig.get('cost_tag')}")
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
        extra_str = (", " + ", ".join(extras)) if extras else ""
        ftypes = ", ".join(info["finding_types"]) or "clean"
        return f"**{_format_verdict_table(info['verdict'])}** (`{info['claim_id']}`: `{sig['kind']}` on `{tgt}`{extra_str}; {ftypes})"

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
            if not row["same_usage"]:
                diffs.append("usage")
            if diffs:
                status_cell += f" ({'/'.join(diffs)} differs)"
        cells = []
        for a in auditors:
            entry = row["by_auditor"][a]
            if entry["status"] in ("UNVERIFIED", "UNMATCHED"):
                cells.append(f"*{entry['status']}*")
            else:
                cells.append("; ".join(_fmt_claim_cell(c) for c in entry["claims"]))
        md.append(
            f"| {row['anchor_index']} | @{row['char_offset']}: \"{q_short}\" | {status_cell} | "
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
            or not r["same_usage"]
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
Read the source document below and output ONLY a single valid JSON object conforming to schema `epistemic-ledger/v2.3`.

CRITICAL RULES:
1. Every `source`, `op`, `claim`, and `ResourceUsage` entry MUST include a `quote` copied VERBATIM from the document (>= 12 non-space characters). For `ResourceUsage`, the exact numeric `amount` must appear inside its `quote`. Do NOT paraphrase or invent numbers.
2. All `nodes`, `tags`, `claim.id`, and `auditor` names must be ASCII identifiers (`^[A-Za-z][A-Za-z0-9_]*$`) and NOT Lean 4 reserved keywords.
3. Every claim endpoint (`target`, `excluded_channel`, `branch_a`, `branch_b`, `method_node`, `evaluation_node`, and non-null `control_node`/`cost_ledger_node`) MUST be defined in the graph (either as a `SourceNode` or as the `output` of an `Op`).
4. Set `"provenance"` on every claim: `"authorClaimed"` if explicitly claimed by the authors, or `"reviewerStressTest"` if testing a reviewer-posed counterfactual question.
5. For emergence claims under Policy 3, prefer `kind: "emergesWithExclusion"` (`target`, `excluded_channel`, `tag`).
6. For effectiveness / efficiency / productivity claims (Tier 2, v2.3), use `kind: "effectivenessClaim"` with:
   - `method_node`, `evaluation_node`, `control_node` (or `null`), `cost_ledger_node` (or `null`), `cost_tag`
   - `method_usage` and `control_usage`: lists of `{{"source": "<node>", "dimension": "<cost_tag>", "unit": "<str>", "amount": <int>, "quote": "<verbatim quote containing amount>"}}` (empty `[]` if unquantified in the paper).
7. Tag `origin` carefully: `"setByExperimenter"` for simulators, pretrained external backbones, manual barriers/cuts, engineered objectives; `"measured"` for raw sensor observations.
8. Only mark a `"forget"` op with `evidence: "shown"` if the paper actually runs an ablation/invariance check demonstrating the conclusion survives removing that dependency; otherwise use `"notShown"` or `"contradicted"`.
9. If a claim is a normative value judgment, legal-policy balancing dispute, or financial/bookkeeping question rather than a structural causal/experimental flow claim, do NOT force it into an emergence or effectiveness claim; instead emit `kind: "outOfScope"` with a concise `"reason"` string explaining why it lies outside structural operation-flow verification.

JSON TEMPLATE:
{{
  "schema_version": "epistemic-ledger/v2.3",
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
      "quote": "verbatim claim quote from text",
      "provenance": "authorClaimed",
      "kind": "emergesWithExclusion",
      "target": "nodeB",
      "excluded_channel": "nodeB",
      "tag": "tagX"
    }}
  ]
}}

SOURCE DOCUMENT ({doc.source_ref}, SHA-256 {doc.sha256[:16]}):
--- BEGIN DOCUMENT ---
{doc.raw_text}
--- END DOCUMENT ---
"""
