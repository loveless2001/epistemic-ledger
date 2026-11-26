"""Reporting, multi-auditor reconciliation, and LLM extraction prompt generation."""

from __future__ import annotations

import json
from typing import Any

from pipeline.ingest import IngestedDocument
from pipeline.lean_runner import LeanVerificationResult
from pipeline.schema import QuoteMatch, ValidationErrorItem


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


def build_single_report_dict(
    doc: IngestedDocument,
    spec: dict[str, Any],
    errors: list[ValidationErrorItem],
    quotes: list[QuoteMatch],
    lean_result: LeanVerificationResult | None,
) -> dict[str, Any]:
    return {
        "schema_version": "epistemic-ledger-report/v2.1",
        "document": {
            "source_ref": doc.source_ref,
            "resolved_path": str(doc.resolved_path),
            "sha256": doc.sha256,
        },
        "auditor": spec.get("auditor"),
        "paper_title": spec.get("paper_title", ""),
        "grounding_and_schema_ok": len(errors) == 0,
        "validation_errors": [
            {"path": e.path, "code": e.code, "message": e.message} for e in errors
        ],
        "verified_quotes": [
            {"path": q.path, "matched": q.matched, "char_offset": q.char_offset, "mode": q.mode, "quote": q.quote}
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
    lines += ["", "## Claim Verdicts", "", "| Claim ID | Kind | Verdict | Findings | Axioms |", "|---|---|---|---|---|"]

    claim_by_id = {c["id"]: c for c in spec["claims"]}
    for c in lv["claims"]:
        meta = claim_by_id[c["id"]]
        lines.append(
            f"| `{c['id']}` | `{meta['kind']}` | **{c['verdict']}** | {len(c['findings'])} | `{', '.join(c['axioms']) or 'none'}` |"
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


def build_comparison_report(
    doc: IngestedDocument, reports: list[dict[str, Any]], specs: list[dict[str, Any]]
) -> tuple[dict[str, Any], str]:
    """Compare 2+ auditor reports on the same document."""
    auditors = [r["auditor"] for r in reports]
    claim_ids: list[str] = []
    for r in reports:
        if r["lean_verification"]:
            for c in r["lean_verification"]["claims"]:
                if c["id"] not in claim_ids:
                    claim_ids.append(c["id"])

    rows: list[dict[str, Any]] = []
    for cid in claim_ids:
        per_auditor: dict[str, Any] = {}
        verdicts: set[str] = set()
        for r in reports:
            aud = r["auditor"]
            lv = r["lean_verification"]
            match = None
            if lv:
                for c in lv["claims"]:
                    if c["id"] == cid:
                        match = c
                        break
            if match is None:
                per_auditor[aud] = {"verdict": "MISSING", "findings": []}
                verdicts.add("MISSING")
            else:
                per_auditor[aud] = {
                    "verdict": match["verdict"],
                    "finding_types": [f["type"] for f in match["findings"]],
                    "findings": match["findings"],
                }
                verdicts.add(match["verdict"])
        rows.append(
            {
                "claim_id": cid,
                "verdicts_agree": len(verdicts) == 1 and "MISSING" not in verdicts,
                "by_auditor": per_auditor,
            }
        )

    # Compare source nodes & carries across auditors
    source_summary = {}
    for spec in specs:
        aud = spec["auditor"]
        source_summary[aud] = {
            s["node"]: {"origin": s["origin"], "carries": s["carries"]} for s in spec["sources"]
        }

    comp_dict = {
        "schema_version": "epistemic-ledger-comparison/v2.1",
        "document": {"source_ref": doc.source_ref, "sha256": doc.sha256},
        "auditors": auditors,
        "all_grounding_ok": all(r["grounding_and_schema_ok"] for r in reports),
        "claim_comparison": rows,
        "sources_by_auditor": source_summary,
    }

    md: list[str] = [
        f"# Multi-Auditor Epistemic Comparison — `{doc.source_ref}`",
        "",
        f"- **Document SHA-256:** `{doc.sha256[:16]}...`",
        f"- **Auditors:** {', '.join(f'`{a}`' for a in auditors)}",
        f"- **All Grounding & Schema Checks Passed:** `{comp_dict['all_grounding_ok']}`",
        "",
        "## Claim Verdict Reconciliation",
        "",
        "| Claim ID | Agreement | " + " | ".join(f"`{a}`" for a in auditors) + " |",
        "|---|---|" + "|".join("---" for _ in auditors) + "|",
    ]

    for row in rows:
        agree_str = "AGREE" if row["verdicts_agree"] else "**DISAGREE**"
        cells = []
        for a in auditors:
            info = row["by_auditor"][a]
            ftypes = ", ".join(info.get("finding_types", [])) or "clean"
            cells.append(f"**{info['verdict']}** ({ftypes})")
        md.append(f"| `{row['claim_id']}` | {agree_str} | " + " | ".join(cells) + " |")

    md += ["", "## Disagreements Requiring Human Review", ""]
    disagreements = [r for r in rows if not r["verdicts_agree"]]
    if not disagreements:
        md.append("- None: all auditors reached identical Lean-verified verdicts on every shared claim.")
    else:
        for row in disagreements:
            md.append(f"- **`{row['claim_id']}`:**")
            for a in auditors:
                info = row["by_auditor"][a]
                md.append(f"  - `{a}` → **{info['verdict']}**")
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
3. For emergence claims under Policy 3, prefer `kind: "emergesWithExclusion"` with:
   - `target`: the node where the claimed property emerges
   - `excluded_channel`: the specific channel/node the claim asserts does NOT receive `tag` (e.g., loss target or direct input)
   - `tag`: the structural property claimed to emerge
4. Tag `origin` carefully: `"setByExperimenter"` for simulators, pretrained external backbones, manual barriers/cuts, engineered objectives; `"measured"` for raw sensor observations.
5. Only mark a `"forget"` op with `evidence: "shown"` if the paper actually runs an ablation/invariance check demonstrating the conclusion survives removing that dependency; otherwise use `"notShown"` or `"contradicted"`.

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
