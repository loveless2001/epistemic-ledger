"""Reporting, quote-anchored multi-auditor reconciliation, and LLM extraction prompt generation."""

from __future__ import annotations

import json
from typing import Any

from pipeline.ingest import IngestedDocument
from pipeline.lean_runner import LeanVerificationResult
from pipeline.schema import QuoteMatch, ValidationErrorItem, verify_quote_in_document


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
        return f"**[Unaccessed Structure]** target `{f['target']}` has no upstream SourceNode granting access to `{f['tag']}`"
    if ft == "undeclaredUpstreamSource":
        return f"**[Undeclared Source]** upstream source `{f['source']}` omitted from conditional claim"
    if ft == "danglingInput":
        return f"**[Dangling Input]** op `{f['op']}` consumes undefined node `{f['missing']}`"
    return json.dumps(f)


def _claim_signature(meta: dict[str, Any]) -> dict[str, Any]:
    kind = meta.get("kind")
    sig: dict[str, Any] = {"kind": kind}
    for k in ("target", "excluded_channel", "branch_a", "branch_b", "tag", "declared_sources"):
        if k in meta:
            sig[k] = meta[k]
    return sig


def build_single_report_dict(
    doc: IngestedDocument,
    spec: dict[str, Any],
    errors: list[ValidationErrorItem],
    quotes: list[QuoteMatch],
    lean_result: LeanVerificationResult | None,
    auditor_label: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "epistemic-ledger-report/v2.1",
        "document": {
            "source_ref": doc.source_ref,
            "resolved_path": str(doc.resolved_path),
            "sha256": doc.sha256,
        },
        "auditor": auditor_label or (spec.get("auditor") if isinstance(spec, dict) else "invalid"),
        "paper_title": spec.get("paper_title", "") if isinstance(spec, dict) else "",
        "grounding_and_schema_ok": len(errors) == 0,
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
        return "\n".join(lines) + "\n"

    lv = report["lean_verification"]
    lines.append(f"- **Lean 4 Kernel Proof:** `{lv['lean_file']}` (axioms whitelist OK: `{lv['axioms_ok']}`)")
    lines.append(
        "- **Scope note:** Verbatim quote checks prove textual existence in the snapshot; whether a quote semantically justifies a tag or edge requires auditor/human review."
    )
    lines += ["", "## Claim Verdicts", "", "| Claim ID | Kind | Target / Channel | Verdict | Findings | Axioms |", "|---|---|---|---|---|---|"]

    claim_by_id = {c["id"]: c for c in spec["claims"]}
    for c in lv["claims"]:
        meta = claim_by_id[c["id"]]
        sig = _claim_signature(meta)
        endpoint = sig.get("target") or f"{sig.get('branch_a')}/{sig.get('branch_b')}"
        if "excluded_channel" in sig:
            endpoint = f"{endpoint} (excl: {sig['excluded_channel']})"
        lines.append(
            f"| `{c['id']}` | `{meta['kind']}` | `{endpoint}` | **{c['verdict']}** | {len(c['findings'])} | `{', '.join(c['axioms']) or 'none'}` |"
        )

    lines += ["", "## Detailed Findings & Verbatim Evidence", ""]
    source_quotes = {s["node"]: s["quote"] for s in spec["sources"]}
    op_quotes = {op["name"]: op["quote"] for op in spec["ops"]}

    for c in lv["claims"]:
        meta = claim_by_id[c["id"]]
        lines += [
            f"### `{c['id']}` — **{c['verdict'].upper()}**",
            f"- **Statement:** {meta['statement']}",
            f"- **Source quote:** > {meta['quote']}",
        ]
        if not c["findings"]:
            lines.append("- **Findings:** None (clean under checked rules).")
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

    Claims are matched by their verbatim quote position `(char_offset, normalized_quote)`
    in the shared document snapshot — NEVER by arbitrary `claim.id` strings.
    Each row also records claim kind, target, and excluded channel per auditor so
    target-level divergences (e.g. pre- vs post-decoder) are never hidden behind
    matching verdicts.
    """
    auditors = [r["auditor"] for r in reports]
    all_grounding_ok = all(r["grounding_and_schema_ok"] for r in reports)

    # Index verified claims per auditor by quote anchor
    anchor_order: list[tuple[int, str]] = []
    anchor_to_auditor_claims: dict[tuple[int, str], dict[str, dict[str, Any]]] = {}

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
            anchor_to_auditor_claims[anchor][aud] = {
                "claim_id": c["id"],
                "verdict": c["verdict"],
                "signature": _claim_signature(meta),
                "finding_types": [f["type"] for f in c["findings"]],
                "findings": c["findings"],
            }

    rows: list[dict[str, Any]] = []
    for idx, anchor in enumerate(anchor_order, 1):
        char_offset, norm_quote = anchor
        by_aud: dict[str, Any] = {}
        verdicts: set[str] = set()
        kinds: set[str] = set()
        targets: set[str] = set()
        missing_or_unverified = False

        for rep in reports:
            aud = rep["auditor"]
            if not rep["grounding_and_schema_ok"] or rep.get("lean_verification") is None:
                by_aud[aud] = {"status": "UNVERIFIED", "verdict": "UNVERIFIED", "findings": []}
                missing_or_unverified = True
            elif aud not in anchor_to_auditor_claims[anchor]:
                by_aud[aud] = {"status": "UNMATCHED", "verdict": "UNMATCHED", "findings": []}
                missing_or_unverified = True
            else:
                info = anchor_to_auditor_claims[anchor][aud]
                by_aud[aud] = {"status": "VERIFIED", **info}
                verdicts.add(info["verdict"])
                sig = info["signature"]
                kinds.add(str(sig.get("kind")))
                tgt = str(sig.get("target") or f"{sig.get('branch_a')}/{sig.get('branch_b')}")
                targets.add(tgt)

        if missing_or_unverified:
            status = "UNVERIFIED_OR_UNMATCHED"
            verdicts_agree = False
        elif len(verdicts) == 1:
            status = "AGREE"
            verdicts_agree = True
        else:
            status = "DISAGREE"
            verdicts_agree = False

        rows.append(
            {
                "anchor_index": idx,
                "char_offset": char_offset,
                "claim_quote": norm_quote,
                "status": status,
                "verdicts_agree": verdicts_agree,
                "same_claim_kind": (not missing_or_unverified) and len(kinds) == 1,
                "same_target_name": (not missing_or_unverified) and len(targets) == 1,
                "by_auditor": by_aud,
            }
        )

    source_summary = {}
    for rep, spec in zip(reports, specs):
        aud = rep["auditor"]
        if rep["grounding_and_schema_ok"] and isinstance(spec, dict):
            source_summary[aud] = {
                s["node"]: {"origin": s["origin"], "carries": s["carries"]} for s in spec.get("sources", [])
            }
        else:
            source_summary[aud] = {"error": "unverified"}

    comp_dict = {
        "schema_version": "epistemic-ledger-comparison/v2.1",
        "document": {"source_ref": doc.source_ref, "sha256": doc.sha256},
        "auditors": auditors,
        "all_grounding_ok": all_grounding_ok,
        "claim_comparison": rows,
        "sources_by_auditor": source_summary,
    }

    md: list[str] = [
        f"# Multi-Auditor Epistemic Comparison — `{doc.source_ref}`",
        "",
        f"- **Document SHA-256:** `{doc.sha256[:16]}...`",
        f"- **Auditors:** {', '.join(f'`{a}`' for a in auditors)}",
        f"- **All Grounding & Schema Checks Passed:** `{all_grounding_ok}`",
        "- **Matching Rule:** Claims are aligned strictly by verbatim quote location `(char_offset, normalized_quote)` in this snapshot, not by arbitrary `claim.id`.",
        "",
    ]

    if not all_grounding_ok:
        md += ["## Unverified Auditors (Grounding / Schema Failed)", ""]
        for rep in reports:
            if not rep["grounding_and_schema_ok"]:
                md.append(f"- **`{rep['auditor']}`:** UNVERIFIED ({len(rep['validation_errors'])} validation/grounding error(s))")
        md.append("")

    md += [
        "## Claim Verdict Reconciliation",
        "",
        "| # | Quote Anchor (offset) | Status | " + " | ".join(f"`{a}`" for a in auditors) + " |",
        "|---|---|---|" + "|".join("---" for _ in auditors) + "|",
    ]

    for row in rows:
        q_short = row["claim_quote"]
        if len(q_short) > 64:
            q_short = q_short[:61] + "..."
        q_short = q_short.replace("|", "\\|")
        status_cell = f"**{row['status']}**"
        if row["verdicts_agree"] and not row["same_claim_kind"]:
            status_cell += " (kind differs)"
        elif row["verdicts_agree"] and not row["same_target_name"]:
            status_cell += " (target name differs)"
        cells = []
        for a in auditors:
            info = row["by_auditor"][a]
            if info["status"] != "VERIFIED":
                cells.append(f"*{info['status']}*")
            else:
                sig = info["signature"]
                tgt = sig.get("target") or f"{sig.get('branch_a')}/{sig.get('branch_b')}"
                excl = f", excl={sig['excluded_channel']}" if "excluded_channel" in sig else ""
                ftypes = ", ".join(info["finding_types"]) or "clean"
                cells.append(
                    f"**{info['verdict']}** (`{info['claim_id']}`: `{sig['kind']}` on `{tgt}`{excl}; {ftypes})"
                )
        md.append(f"| {row['anchor_index']} | @{row['char_offset']}: \"{q_short}\" | {status_cell} | " + " | ".join(cells) + " |")

    md += ["", "## Disagreements & Unverified Items Requiring Human Review", ""]
    if not rows:
        md.append("- **UNVERIFIED:** No grounded claims were available to compare.")
    else:
        issues = [r for r in rows if not r["verdicts_agree"] or not r["same_claim_kind"] or not r["same_target_name"]]
        if not issues and all_grounding_ok:
            md.append("- None: all auditors passed grounding and reached identical Lean-verified verdicts, claim kinds, and targets on every matched claim.")
        else:
            for row in issues:
                md.append(f"- **Claim #{row['anchor_index']} (@{row['char_offset']} — {row['status']}):** \"{row['claim_quote']}\"")
                for a in auditors:
                    info = row["by_auditor"][a]
                    if info["status"] != "VERIFIED":
                        md.append(f"  - `{a}` → *{info['status']}*")
                    else:
                        sig = info["signature"]
                        md.append(f"  - `{a}` (`{info['claim_id']}`, `{sig}`) → **{info['verdict']}**")
                        for f in info.get("findings", []):
                            md.append(f"    - {format_finding_human(f)}")

    return comp_dict, "\n".join(md) + "\n"


def build_extraction_prompt(doc: IngestedDocument, auditor_name: str = "AuditorA") -> str:
    """Build a strict extraction prompt for any LLM/agent to produce a quote-grounded AuditSpec JSON."""
    return f"""You are an independent epistemological auditor.
Read the source document below and output ONLY a single valid JSON object conforming to schema `epistemic-ledger/v2.1`.

CRITICAL RULES:
1. Every `source`, `op`, and `claim` MUST include a `quote` copied VERBATIM from the document (>= 12 non-space characters). Do NOT paraphrase quotes — a deterministic script will reject any quote not found verbatim in the source text.
2. All `nodes`, `tags`, `claim.id`, and `auditor` names must be ASCII identifiers (`^[A-Za-z][A-Za-z0-9_]*$`) and NOT Lean 4 reserved keywords.
3. Every claim endpoint (`target`, `excluded_channel`, `branch_a`, `branch_b`) MUST be defined in the graph (either as a `SourceNode` or as the `output` of an `Op`).
4. For emergence claims under Policy 3, prefer `kind: "emergesWithExclusion"` with:
   - `target`: the node where the claimed property emerges
   - `excluded_channel`: the specific channel/node the claim asserts does NOT receive `tag` (e.g., loss target or direct input)
   - `tag`: the structural property claimed to emerge
5. Tag `origin` carefully: `"setByExperimenter"` for simulators, pretrained external backbones, manual barriers/cuts, engineered objectives; `"measured"` for raw sensor observations.
6. Only mark a `"forget"` op with `evidence: "shown"` if the paper actually runs an ablation/invariance check demonstrating the conclusion survives removing that dependency; otherwise use `"notShown"` or `"contradicted"`.

JSON TEMPLATE:
{{
  "schema_version": "epistemic-ledger/v2.1",
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
