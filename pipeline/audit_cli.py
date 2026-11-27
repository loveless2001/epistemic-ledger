"""CLI entrypoint for the Epistemic Ledger two-stage audit pipeline (Pre -> Gate -> Post).

Stage 1 (Pre-formalization — optional NMF + IPOD exploration & Pre-Gate):
  pre-prompt  Ingest a document and emit the bidirectional NMF + IPOD Pre-formalization prompt
  pre         Run deterministic Pre probe + non-destructive merge-patch + Pre-Gate handoff

Stage 2 (Post-formalization — Lean 4 OperationFlow verification):
  prompt      Ingest a document and emit the Post AuditSpec v2.5 extraction prompt (optionally with --pre-brief)
  run         Verify one AuditSpec JSON against a document (optional --pre-gate guard + quotes + Lean 4 kernel)
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
from pipeline.preform import (
    build_preform_prompt,
    check_pre_gate_for_post,
    check_pre_input_output_aliasing,
    compute_probe,
    invalidate_pre_handoff_artifacts,
    merge_patch_graph,
    run_pre_handoff,
)
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


def _purge_stale_post_artifacts(spec_path: Path, out_dir: Path) -> None:
    """Remove any prior Lean proof and reports for this spec's auditor in `out_dir` without creating files."""
    if not out_dir.exists():
        return
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception:
        return
    raw_auditor = spec.get("auditor") if isinstance(spec, dict) else None
    stem = _safe_stem(raw_auditor, "invalid_auditor")
    for fname in (f"{stem}_Verified.lean", f"{stem}_report.json", f"{stem}_report.md"):
        _unlink_if_exists(_safe_out_path(out_dir, fname))


def cmd_run(args: argparse.Namespace) -> int:
    doc = ingest_document(args.doc, cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    if args.pre_gate:
        cleared, msg = check_pre_gate_for_post(Path(args.pre_gate), doc)
        if not cleared:
            _purge_stale_post_artifacts(Path(args.spec), Path(args.out))
            print(msg, file=sys.stderr)
            return 3
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
    pre_brief = Path(args.pre_brief).read_text(encoding="utf-8") if args.pre_brief else None
    prompt = build_extraction_prompt(doc, auditor_name=args.auditor, pre_brief=pre_brief)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(prompt, encoding="utf-8")
        print(f"Extraction prompt written to {args.out}")
    else:
        print(prompt)
    return 0


def cmd_pre_prompt(args: argparse.Namespace) -> int:
    doc = ingest_document(args.doc, cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    prompt = build_preform_prompt(doc, graph_ref=args.graph or "concept-graph.json")
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(prompt, encoding="utf-8")
        print(f"Pre-formalization prompt written to {args.out}")
    else:
        print(prompt)
    return 0


def cmd_pre(args: argparse.Namespace) -> int:
    graph_path = Path(args.graph)
    trace_path = Path(args.trace)
    out_path = Path(args.out)

    if args.mode == "handoff":
        # Invalidate prior gate/handoff artifacts BEFORE ingest_document so an ingest failure
        # (e.g. corrupt UTF-8 or missing doc) cannot leave an old `explore.json` pass alive,
        # while preserving any input file that aliases an output path.
        preserve = {graph_path.resolve(), trace_path.resolve()}
        if not str(args.doc).startswith("arxiv:") and Path(args.doc).exists():
            preserve.add(Path(args.doc).resolve())
        invalidate_pre_handoff_artifacts(out_path, preserve_paths=preserve)
        alias_err = check_pre_input_output_aliasing(out_path, graph_path, trace_path, str(args.doc))
        if alias_err:
            print(alias_err, file=sys.stderr)
            return 2

    doc = ingest_document(args.doc, cache_dir=Path(args.cache_dir) if args.cache_dir else None)

    if args.mode == "probe":
        result = compute_probe(graph_path, trace_path, doc)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        s = result["summary"]
        print(
            f"TOUCHED={s['touched_nodes']}/{s['graph_nodes']} "
            f"UNTOUCHED_FRONTIER={s['untouched_non_actor_nodes']} "
            f"ANCHOR_QS={s['anchor_questions']} "
            f"NEW_NODES={s['proposed_new_nodes_valid']}/{s['proposed_new_nodes_total']} "
            f"CHALLENGES={s['challenged_items_valid']}/{s['challenged_items_total']} "
            f"GATE={s['pre_gate_decision'] or 'none'}({s['pre_gate_valid']})"
        )
        return 0

    if args.mode == "merge-patch":
        n_nodes, n_edges = merge_patch_graph(graph_path, trace_path, out_path)
        print(f"PATCHED_GRAPH: {n_nodes} nodes, {n_edges} edges -> {out_path}")
        return 0

    _, rc, msg = run_pre_handoff(graph_path, trace_path, doc, out_path)
    stream = sys.stdout if rc == 0 else sys.stderr
    print(msg, file=stream)
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Epistemic Ledger two-stage audit pipeline (Pre -> Gate -> Post)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pre_prompt = sub.add_parser("pre-prompt", help="Emit bidirectional NMF+IPOD Pre-formalization & Pre-Gate prompt")
    p_pre_prompt.add_argument("--doc", "--document", dest="doc", required=True)
    p_pre_prompt.add_argument("--graph", default="concept-graph.json", help="Concept graph path referenced in prompt")
    p_pre_prompt.add_argument("--out", default="")
    p_pre_prompt.add_argument("--cache-dir", default="")
    p_pre_prompt.set_defaults(func=cmd_pre_prompt)

    p_pre = sub.add_parser("pre", help="Run Pre-formalization probe, merge-patch, or Pre-Gate handoff")
    p_pre.add_argument("--graph", required=True, help="Path to concept-graph.json")
    p_pre.add_argument("--trace", required=True, help="Path to agent trace.json")
    p_pre.add_argument("--doc", "--document", dest="doc", required=True, help="Path to .pdf/.md/.txt or arxiv:<id>")
    p_pre.add_argument("--out", required=True, help="Output directory (handoff) or file (probe/merge-patch)")
    p_pre.add_argument("--mode", choices=("handoff", "probe", "merge-patch"), default="handoff")
    p_pre.add_argument("--cache-dir", default="")
    p_pre.set_defaults(func=cmd_pre)

    p_run = sub.add_parser("run", help="Verify one AuditSpec JSON against a document (Post / Lean 4)")
    p_run.add_argument("--doc", "--document", dest="doc", required=True, help="Path to .pdf/.md/.txt or arxiv:<id>")
    p_run.add_argument("--spec", required=True, help="Path to AuditSpec JSON")
    p_run.add_argument("--out", required=True, help="Output directory for .lean + report")
    p_run.add_argument("--pre-gate", default="", help="Optional Pre explore.json; blocks Post/Lean unless proceed_to_post")
    p_run.add_argument("--repo-root", default=str(REPO_ROOT))
    p_run.add_argument("--cache-dir", default="")
    p_run.set_defaults(func=cmd_run)

    p_prompt = sub.add_parser("prompt", help="Emit strict Post AuditSpec extraction prompt for any LLM/agent")
    p_prompt.add_argument("--doc", "--document", dest="doc", required=True)
    p_prompt.add_argument("--auditor", default="AuditorA")
    p_prompt.add_argument("--pre-brief", default="", help="Optional post_brief.md from `audit_cli pre`")
    p_prompt.add_argument("--out", default="")
    p_prompt.add_argument("--cache-dir", default="")
    p_prompt.set_defaults(func=cmd_prompt)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
