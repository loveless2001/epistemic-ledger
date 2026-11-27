"""CLI entrypoint for the Epistemic Ledger automated audit pipeline.

Commands:
  ask      Inspect an AuditSpec JSON against a document and list unanswered E2–E7 ask-back questions (prints no verdict)
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
from pipeline.schema import evaluate_ask_back, is_valid_ident, validate_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
# Distinct exit code for `audit_cli ask` when schema/grounding pass but ask-back questions remain unanswered
# (kept distinct from exit 2 validation error and exit 3 extractor crash so runners do not treat it as a fatal crash).
EXIT_ASK_INCOMPLETE = 4


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


def cmd_ask(args: argparse.Namespace) -> int:
    """List unanswered E2–E7 ask-back questions per claim. Never runs Lean or prints verdicts.

    Exit codes:
      0 — schema/grounding OK and all E2–E7 ask-back items finished (answered / not_found / not_applicable)
      4 — schema/grounding OK, but one or more ask-back questions remain unanswered (`EXIT_ASK_INCOMPLETE`)
      2 — schema or verbatim quote-grounding errors present
    """
    doc = ingest_document(args.doc, cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    errors, quotes = validate_spec(spec, doc=doc)
    ask_summary = evaluate_ask_back(spec)

    if args.json:
        payload = {
            "document": {"source_ref": doc.source_ref, "sha256": doc.sha256},
            "grounding_and_schema_ok": len(errors) == 0,
            "validation_errors": [{"path": e.path, "code": e.code, "message": e.message} for e in errors],
            "verified_quotes_count": sum(1 for q in quotes if q.matched),
            "ask_back": ask_summary,
        }
        print(json.dumps(payload, indent=2))
        if errors:
            return 2
        if not ask_summary["applicable_v25"]:
            return 0
        return 0 if ask_summary["complete"] else EXIT_ASK_INCOMPLETE

    if errors:
        print(f"Grounding/schema failed with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err.path} ({err.code}): {err.message}", file=sys.stderr)
        return 2

    if not ask_summary["applicable_v25"]:
        print(
            f"Ask-back loop does not apply to schema_version {ask_summary['schema_version']!r} "
            f"(v2.5+ only; no questions asked, no verdict printed)."
        )
        return 0

    if ask_summary["complete"]:
        print(
            f"Ask-back complete: 0 unanswered question(s) across {ask_summary['total_claims']} claim(s) "
            f"(no verdict printed by `ask`)."
        )
        return 0

    print(
        f"Ask-back incomplete: {ask_summary['unanswered_count']} unanswered question(s) across "
        f"{ask_summary['total_claims']} claim(s) (no verdict printed by `ask`):"
    )
    for cinfo in ask_summary["claims"]:
        if not cinfo["unanswered"]:
            continue
        print(f"\nClaim `{cinfo['claim_id']}` ({cinfo['kind']}): \"{cinfo['quote']}\"")
        for item in cinfo["unanswered"]:
            print(f"  - [{item['code']}] `{item['field']}`: {item['question']}")
    return EXIT_ASK_INCOMPLETE


def cmd_run(args: argparse.Namespace) -> int:
    doc = ingest_document(args.doc, cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    report, _, ok = _audit_one(doc, Path(args.spec), Path(args.out), Path(args.repo_root))
    print(f"Report written to {Path(args.out) / (str(report['auditor']) + '_report.md')}")
    if not ok:
        print(f"Grounding/schema failed with {len(report['validation_errors'])} error(s).", file=sys.stderr)
        return 2
    ab = report.get("ask_back_summary", {})
    if ab.get("applicable_v25") and not ab.get("complete", True):
        print(
            f"  Note: ask-back incomplete ({ab['unanswered_count']} unanswered question(s)); "
            f"structural Lean verdict produced without aborting."
        )
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

    p_ask = sub.add_parser(
        "ask",
        help="List unanswered E2–E7 ask-back questions per claim (prints no verdict; exit 0 complete, 4 incomplete, 2 error)",
    )
    p_ask.add_argument("--doc", "--document", dest="doc", required=True, help="Path to .pdf/.md/.txt or arxiv:<id>")
    p_ask.add_argument("--spec", required=True, help="Path to AuditSpec JSON")
    p_ask.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_ask.add_argument("--cache-dir", default="")
    p_ask.set_defaults(func=cmd_ask)

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
