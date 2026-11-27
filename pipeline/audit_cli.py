"""CLI entrypoint for the Epistemic Ledger automated audit pipeline.

Commands:
  run      Verify one AuditSpec JSON against a document (quotes + Lean 4 kernel) -> report.md + report.json + .lean
  prompt   Ingest a document (.pdf/.md/.txt/arxiv:<id>) and emit a strict extraction prompt for any LLM/agent
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from pipeline.ingest import IngestedDocument, ingest_document
from pipeline.lean_runner import run_lean_verification
from pipeline.report import (
    build_extraction_prompt,
    build_single_report_dict,
    format_display_state_short,
    render_single_report_markdown,
)
from pipeline.schema import is_valid_ident, validate_spec

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def _atomic_write_text(dest: Path, content: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(dest.parent),
            prefix=f".{dest.stem}.",
            suffix=".tmp",
            delete=False,
        ) as tf:
            tf.write(content)
            tmp_path = Path(tf.name)
        os.replace(tmp_path, dest)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def _unlink_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


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
    report_json_path = _safe_out_path(out_dir, f"{stem}_report.json")
    report_md_path = _safe_out_path(out_dir, f"{stem}_report.md")

    # Clear any stale artifacts for this stem BEFORE running Lean so a failed rerun
    # (including a Lean/build crash) can never leave an old proof or old `axioms_ok: true` report behind.
    _unlink_if_exists(lean_path)
    _unlink_if_exists(report_json_path)
    _unlink_if_exists(report_md_path)

    lean_result = None
    if not errors:
        ns = f"EpistemicLedger.Generated.{stem}"
        lean_result = run_lean_verification(spec, repo_root=repo_root, out_lean_path=lean_path, namespace=ns)

    report = build_single_report_dict(doc, spec, errors, quotes, lean_result, auditor_label=label)
    md = render_single_report_markdown(report, spec)

    _atomic_write_text(report_json_path, json.dumps(report, indent=2))
    _atomic_write_text(report_md_path, md)
    return report, spec, len(errors) == 0


def cmd_run(args: argparse.Namespace) -> int:
    doc = ingest_document(args.doc, cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    report, _, ok = _audit_one(doc, Path(args.spec), Path(args.out), Path(args.repo_root))
    print(f"Report written to {Path(args.out) / (str(report['auditor']) + '_report.md')}")
    if not ok:
        print(f"Grounding/schema failed with {len(report['validation_errors'])} error(s).", file=sys.stderr)
        return 2
    for c in report["lean_verification"]["claims"]:
        label = format_display_state_short(c["verdict"], int(c.get("declared_bet_count", 0)))
        print(f"  - {c['id']}: {label} ({len(c['findings'])} finding(s), axioms={c['axioms']})")
    return 0


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Epistemic Ledger automated audit pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Verify one AuditSpec JSON against a document")
    p_run.add_argument("--doc", "--document", dest="doc", required=True, help="Path to .pdf/.md/.txt or arxiv:<id>")
    p_run.add_argument("--spec", required=True, help="Path to AuditSpec JSON")
    p_run.add_argument("--out", required=True, help="Output directory for .lean + report")
    p_run.add_argument("--repo-root", default=str(REPO_ROOT))
    p_run.add_argument("--cache-dir", default="")
    p_run.set_defaults(func=cmd_run)

    p_prompt = sub.add_parser("prompt", help="Emit strict extraction prompt for any LLM/agent")
    p_prompt.add_argument("--doc", required=True)
    p_prompt.add_argument("--auditor", default="AuditorA")
    p_prompt.add_argument("--out", default="")
    p_prompt.add_argument("--cache-dir", default="")
    p_prompt.set_defaults(func=cmd_prompt)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
