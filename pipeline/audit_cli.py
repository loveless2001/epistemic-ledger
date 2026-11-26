"""CLI entrypoint for the Epistemic Ledger automated audit pipeline.

Commands:
  run      Verify one AuditSpec JSON against a document (quotes + Lean 4 kernel) -> report.md + report.json + .lean
  compare  Verify 2+ AuditSpec JSONs against a document and emit quote-anchored cross-auditor diff
  prompt   Ingest a document (.pdf/.md/.txt/arxiv:<id>) and emit a strict extraction prompt for any LLM/agent
  extract  End-to-end 1-command run using an external extractor command (reads prompt on stdin, emits JSON on stdout)
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from pipeline.ingest import IngestedDocument, ingest_document
from pipeline.lean_runner import run_lean_verification
from pipeline.report import (
    build_comparison_report,
    build_extraction_prompt,
    build_single_report_dict,
    render_single_report_markdown,
)
from pipeline.schema import is_valid_ident, validate_spec

REPO_ROOT = Path(__file__).resolve().parent.parent


def _extract_json_block(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


def _safe_out_path(out_dir: Path, filename: str) -> Path:
    resolved_out = out_dir.resolve()
    candidate = (resolved_out / filename).resolve()
    if not candidate.is_relative_to(resolved_out):
        raise ValueError(f"Refusing to write outside output directory: {filename!r}")
    return candidate


def _safe_stem(raw_auditor: Any, fallback: str) -> str:
    if is_valid_ident(raw_auditor):
        return str(raw_auditor)
    return fallback


def _audit_one(
    doc: IngestedDocument,
    spec_path: Path,
    out_dir: Path,
    repo_root: Path,
    file_stem_override: str | None = None,
    auditor_label_override: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    errors, quotes = validate_spec(spec, doc=doc)

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_auditor = spec.get("auditor") if isinstance(spec, dict) else None
    stem = file_stem_override or _safe_stem(raw_auditor, "invalid_auditor")
    label = auditor_label_override or stem

    lean_path = _safe_out_path(out_dir, f"{stem}_Verified.lean")
    lean_result = None
    if not errors:
        ns = f"EpistemicLedger.Generated.{stem}"
        lean_result = run_lean_verification(spec, repo_root=repo_root, out_lean_path=lean_path, namespace=ns)
    else:
        # Never leave a stale proof file behind on a failed audit!
        if lean_path.exists():
            lean_path.unlink()

    report = build_single_report_dict(doc, spec, errors, quotes, lean_result, auditor_label=label)
    md = render_single_report_markdown(report, spec)

    _safe_out_path(out_dir, f"{stem}_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _safe_out_path(out_dir, f"{stem}_report.md").write_text(md, encoding="utf-8")
    return report, spec, len(errors) == 0


def cmd_run(args: argparse.Namespace) -> int:
    doc = ingest_document(args.doc, cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    report, _, ok = _audit_one(doc, Path(args.spec), Path(args.out), Path(args.repo_root))
    print(f"Report written to {Path(args.out) / (str(report['auditor']) + '_report.md')}")
    if not ok:
        print(f"Grounding/schema failed with {len(report['validation_errors'])} error(s).", file=sys.stderr)
        return 2
    for c in report["lean_verification"]["claims"]:
        print(f"  - {c['id']}: {c['verdict']} ({len(c['findings'])} finding(s), axioms={c['axioms']})")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    if len(args.specs) < 2:
        print("compare requires at least 2 --spec files", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    # Single document snapshot shared across every auditor and the final comparison
    doc = ingest_document(args.doc, cache_dir=cache_dir)

    # Disambiguate file stems & auditor labels so duplicate/invalid names never overwrite
    raw_specs = [json.loads(Path(sp).read_text(encoding="utf-8")) for sp in args.specs]
    base_stems = [
        _safe_stem(s.get("auditor") if isinstance(s, dict) else None, f"spec_{idx + 1}")
        for idx, s in enumerate(raw_specs)
    ]
    counts: dict[str, int] = {}
    for st in base_stems:
        counts[st] = counts.get(st, 0) + 1

    seen_so_far: dict[str, int] = {}
    unique_stems: list[str] = []
    for st in base_stems:
        if counts[st] > 1:
            seen_so_far[st] = seen_so_far.get(st, 0) + 1
            unique_stems.append(f"{st}_{seen_so_far[st]}")
        else:
            unique_stems.append(st)

    reports: list[dict[str, Any]] = []
    specs: list[dict[str, Any]] = []
    all_ok = True
    for sp, stem in zip(args.specs, unique_stems):
        rep, spec, ok = _audit_one(
            doc,
            Path(sp),
            out_dir,
            Path(args.repo_root),
            file_stem_override=stem,
            auditor_label_override=stem,
        )
        reports.append(rep)
        specs.append(spec)
        all_ok = all_ok and ok

    comp_dict, comp_md = build_comparison_report(doc, reports, specs)
    _safe_out_path(out_dir, "comparison.json").write_text(json.dumps(comp_dict, indent=2), encoding="utf-8")
    _safe_out_path(out_dir, "comparison.md").write_text(comp_md, encoding="utf-8")
    print(f"Comparison written to {out_dir / 'comparison.md'}")
    for row in comp_dict["claim_comparison"]:
        print(f"  - claim #{row['anchor_index']} (@{row['char_offset']}): {row['status']}")
    return 0 if all_ok else 2


def cmd_prompt(args: argparse.Namespace) -> int:
    if not is_valid_ident(args.auditor):
        print(f"Invalid --auditor identifier: {args.auditor!r}", file=sys.stderr)
        return 2
    doc = ingest_document(args.doc, cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    prompt = build_extraction_prompt(doc, auditor_name=args.auditor)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(prompt, encoding="utf-8")
        print(f"Extraction prompt written to {args.out}")
    else:
        print(prompt)
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    if not is_valid_ident(args.auditor):
        print(f"Invalid --auditor identifier: {args.auditor!r}", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir) if args.cache_dir else None

    # Single document snapshot shared between extraction prompt and Lean verification
    doc = ingest_document(args.doc, cache_dir=cache_dir)
    prompt = build_extraction_prompt(doc, auditor_name=args.auditor)
    _safe_out_path(out_dir, f"{args.auditor}_prompt.txt").write_text(prompt, encoding="utf-8")

    argv_cmd = shlex.split(args.extractor_cmd)
    if not argv_cmd:
        print("Empty --extractor-cmd", file=sys.stderr)
        return 2

    proc = subprocess.run(
        argv_cmd,
        shell=False,
        input=prompt,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"Extractor command failed (exit {proc.returncode}):\n{proc.stderr}", file=sys.stderr)
        return 3

    spec = _extract_json_block(proc.stdout)
    spec_path = _safe_out_path(out_dir, f"{args.auditor}_spec.json")
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    report, _, ok = _audit_one(
        doc,
        spec_path,
        out_dir,
        Path(args.repo_root),
        file_stem_override=args.auditor,
        auditor_label_override=args.auditor,
    )
    print(f"End-to-end report written to {out_dir / (args.auditor + '_report.md')}")
    if not ok:
        print(f"Grounding/schema failed with {len(report['validation_errors'])} error(s).", file=sys.stderr)
        return 2
    for c in report["lean_verification"]["claims"]:
        print(f"  - {c['id']}: {c['verdict']} ({len(c['findings'])} finding(s), axioms={c['axioms']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Epistemic Ledger automated audit pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Verify one AuditSpec JSON against a document")
    p_run.add_argument("--doc", required=True, help="Path to .pdf/.md/.txt or arxiv:<id>")
    p_run.add_argument("--spec", required=True, help="Path to AuditSpec JSON")
    p_run.add_argument("--out", required=True, help="Output directory for .lean + report")
    p_run.add_argument("--repo-root", default=str(REPO_ROOT))
    p_run.add_argument("--cache-dir", default="")
    p_run.set_defaults(func=cmd_run)

    p_cmp = sub.add_parser("compare", help="Verify 2+ AuditSpec JSONs and emit quote-anchored cross-auditor diff")
    p_cmp.add_argument("--doc", required=True, help="Path to .pdf/.md/.txt or arxiv:<id>")
    p_cmp.add_argument("--spec", dest="specs", action="append", required=True, help="AuditSpec JSON (repeatable)")
    p_cmp.add_argument("--out", required=True, help="Output directory")
    p_cmp.add_argument("--repo-root", default=str(REPO_ROOT))
    p_cmp.add_argument("--cache-dir", default="")
    p_cmp.set_defaults(func=cmd_compare)

    p_prompt = sub.add_parser("prompt", help="Emit strict extraction prompt for any LLM/agent")
    p_prompt.add_argument("--doc", required=True)
    p_prompt.add_argument("--auditor", default="AuditorA")
    p_prompt.add_argument("--out", default="")
    p_prompt.add_argument("--cache-dir", default="")
    p_prompt.set_defaults(func=cmd_prompt)

    p_ext = sub.add_parser("extract", help="End-to-end extraction + Lean verification via argv extractor cmd")
    p_ext.add_argument("--doc", required=True)
    p_ext.add_argument("--extractor-cmd", required=True, help="Command (parsed via shlex, shell=False) reading prompt on stdin, printing JSON on stdout")
    p_ext.add_argument("--auditor", default="AutoAuditor")
    p_ext.add_argument("--out", required=True)
    p_ext.add_argument("--repo-root", default=str(REPO_ROOT))
    p_ext.add_argument("--cache-dir", default="")
    p_ext.set_defaults(func=cmd_extract)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
