"""Pre-formalization NMF + IPOD exploration and Pre-Gate module.

Stage 1 of the Epistemic Ledger two-stage workflow (Pre -> Gate -> Post):
  - Optional, bidirectional NMF + IPOD exploration between a domain concept graph
    and an ingested document snapshot (sharing `pipeline.ingest` and `pipeline.schema`
    quote normalization with Stage 2).
  - Surfaces untouched graph frontier and `measures` frame-shift losses as open
    pre-formalization questions (never paper-validity verdicts).
  - Validates agent epistemic independence: `proposed_new_nodes` (what the graph
    missed/collapsed) and `challenged_graph_items` (pushback against wrong,
    collapsed, or foreign graph items).
  - Enforces the Pre-Gate (`stop_at_pre` vs `proceed_to_post`):
      * `stop_at_pre`: purges any stale Post handoff files in `out_dir`, writes
        `pre_gate_report.md`, and stops before Lean / Post formalization.
      * `proceed_to_post`: emits `post_brief.md` + `questions_seed.json`
        (schema-validated against `pipeline/schema.py`'s `questions` contract)
        for Stage 2 (`audit_cli prompt --pre-brief` + `audit_cli run --pre-gate`).

All graph traversals sort adjacency lists so output is 100% deterministic
regardless of PYTHONHASHSEED.
"""

from __future__ import annotations

import json
import os
import re
from collections import deque
from pathlib import Path
from typing import Any

from pipeline.ingest import IngestedDocument, ingest_document
from pipeline.schema import (
    VALID_QUESTION_ASKERS,
    VALID_QUESTION_STATUSES,
    dehyphenate_and_normalize,
    normalize_whitespace,
)

VALID_ROLES = {"actor", "process_state", "measure"}
VALID_EDGE_KINDS = {"generates", "regulates", "measures"}
VALID_CHALLENGE_KINDS = {
    "wrong_direction",
    "collapsed_step",
    "wrong_frame",
    "irrelevant_to_domain",
    "single_report_bias",
    "missing_distinction",
    "other",
}
VALID_GATE_DECISIONS = {"stop_at_pre", "proceed_to_post"}
MIN_QUOTE_NONSPACE = 12


def _norm(s: Any) -> str:
    return normalize_whitespace(s if isinstance(s, str) else "")


def _dehy(s: Any) -> str:
    return dehyphenate_and_normalize(s if isinstance(s, str) else "")


def _match_quote(quote: Any, doc: IngestedDocument) -> bool:
    if not isinstance(quote, str):
        return False
    q = _norm(quote)
    if len(re.sub(r"\s+", "", q)) < MIN_QUOTE_NONSPACE:
        return False
    if q in doc.normalized_text:
        return True
    return _dehy(quote) in doc.dehyphenated_text


def _unlink_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _atomic_write_text(dest: Path, content: str) -> None:
    import tempfile

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


def _load_graph(path: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[str, list[str]], dict[str, list[str]]]:
    with path.open(encoding="utf-8") as f:
        g = json.load(f)
    nodes = g.get("nodes", {})
    edges_list = g.get("edges", [])
    E: dict[tuple[str, str], dict[str, Any]] = {}
    succ: dict[str, set[str]] = {}
    pred: dict[str, set[str]] = {}
    for e in edges_list:
        u, v = e["from"], e["to"]
        E[(u, v)] = e
        succ.setdefault(u, set()).add(v)
        pred.setdefault(v, set()).add(u)
    succ_sorted = {k: sorted(vs) for k, vs in succ.items()}
    pred_sorted = {k: sorted(vs) for k, vs in pred.items()}
    return g, nodes, edges_list, E, succ_sorted, pred_sorted


def _bfs_reachable(starts: set[str], adj: dict[str, list[str]], avoid: frozenset[str] = frozenset()) -> set[str]:
    seen: set[str] = set()
    q: deque[str] = deque()
    for s in sorted(starts):
        if s not in avoid and s not in seen:
            seen.add(s)
            q.append(s)
    while q:
        x = q.popleft()
        for y in adj.get(x, ()):
            if y not in seen and y not in avoid:
                seen.add(y)
                q.append(y)
    return seen


def _shortest(
    s: str,
    t: str,
    adj: dict[str, list[str]],
    avoid: frozenset[str] = frozenset(),
    max_hops: int | None = None,
    forbid_edges: frozenset[tuple[str, str]] = frozenset(),
) -> list[str] | None:
    if s == t:
        return None
    prev: dict[str, str | None] = {s: None}
    q: deque[tuple[str, int]] = deque([(s, 0)])
    while q:
        x, d = q.popleft()
        if max_hops is not None and d >= max_hops:
            continue
        for y in adj.get(x, ()):
            if y in avoid or (x, y) in forbid_edges:
                continue
            if y == t:
                p = [y]
                cur: str | None = x
                while cur is not None:
                    p.append(cur)
                    cur = prev[cur]
                return p[::-1]
            if y not in prev:
                prev[y] = x
                q.append((y, d + 1))
    return None


def _show_node(n: str, nodes: dict[str, Any]) -> str:
    nd = nodes.get(n, {})
    ps = "; ".join(
        f"{k}: {' / '.join(v for v in vs if v != 'other')}"
        for k, vs in sorted(nd.get("params", {}).items())
    )
    nm = nd.get("names", [n])[0] if nd.get("names") else n
    return f"{n} «{nm}»" + (f" ({ps})" if ps else "")


def validate_open_question(qitem: Any, doc: IngestedDocument) -> list[str]:
    """Validate a question item against `pipeline/schema.py`'s exact `questions` contract."""
    errs: list[str] = []
    allowed = {
        "about_quote", "phrase", "question", "asked_by", "status",
        "answer_quotes", "answer", "stays_open", "searched", "claim_id",
    }
    req = {"about_quote", "phrase", "question", "asked_by", "status"}
    if not isinstance(qitem, dict):
        return ["question item must be a JSON object"]
    extra = sorted(set(qitem) - allowed)
    missing = sorted(req - set(qitem))
    if extra:
        errs.append(f"unexpected keys: {extra}")
    if missing:
        errs.append(f"missing required keys: {missing}")
        return errs

    about_q = qitem.get("about_quote", "")
    if not _match_quote(about_q, doc):
        errs.append("about_quote not found verbatim in document (or <12 non-space chars)")
    phrase = qitem.get("phrase", "")
    if not isinstance(phrase, str) or not phrase.strip():
        errs.append("phrase must be a non-empty string")
    elif isinstance(about_q, str):
        if (
            phrase not in about_q
            and _norm(phrase) not in _norm(about_q)
            and _dehy(phrase) not in _dehy(about_q)
        ):
            errs.append("phrase must appear verbatim inside about_quote")
    if not isinstance(qitem.get("question"), str) or not qitem["question"].strip():
        errs.append("question must be non-empty")
    if qitem.get("asked_by") not in VALID_QUESTION_ASKERS:
        errs.append(f"asked_by must be in {sorted(VALID_QUESTION_ASKERS)}")

    st = qitem.get("status")
    if st not in VALID_QUESTION_STATUSES:
        errs.append(f"status must be in {sorted(VALID_QUESTION_STATUSES)}")
    elif st in ("answered", "partly"):
        aqs = qitem.get("answer_quotes")
        if not isinstance(aqs, list) or len(aqs) == 0:
            errs.append(f"status '{st}' requires non-empty answer_quotes")
        else:
            for i, aq in enumerate(aqs):
                if not _match_quote(aq, doc):
                    errs.append(f"answer_quotes[{i}] not found verbatim in document")
        if not isinstance(qitem.get("answer"), str) or not qitem["answer"].strip():
            errs.append(f"status '{st}' requires non-empty answer")
        if st == "partly" and (not isinstance(qitem.get("stays_open"), str) or not qitem["stays_open"].strip()):
            errs.append("status 'partly' requires non-empty stays_open")
    else:  # not_in_document
        aqs = qitem.get("answer_quotes")
        if aqs is not None and (not isinstance(aqs, list) or len(aqs) > 0):
            errs.append("status 'not_in_document' must not include non-empty answer_quotes")
        if not isinstance(qitem.get("searched"), str) or not qitem["searched"].strip():
            errs.append("status 'not_in_document' requires non-empty searched")
    return errs


def compute_probe(graph_path: Path, trace_path: Path, doc: IngestedDocument) -> dict[str, Any]:
    _, nodes, _, E, succ, pred = _load_graph(graph_path)
    with trace_path.open(encoding="utf-8") as f:
        trace = json.load(f)

    role = {n: nd.get("role", "process_state") for n, nd in nodes.items()}
    measure_nodes = {n for n, r in role.items() if r == "measure"}
    actor_nodes = {n for n, r in role.items() if r == "actor"}
    family_of = {n: nd["family"] for n, nd in nodes.items() if nd.get("family")}
    measure_edges = frozenset(k for k, e in E.items() if e.get("kind") == "measures")

    touched_nodes: set[str] = set()
    touched_families: set[str] = set()
    anchor_results = []

    for item in trace.get("document_anchors", []):
        qs = []
        path = item.get("path", [])
        if not _match_quote(item.get("quote"), doc):
            qs.append(("QUOTE_MISSING", "anchor quote not found verbatim in document"))
        for n in path:
            if n not in nodes:
                qs.append(("UNKNOWN_NODE", f"{n} is not in concept-graph.json (if new, put in proposed_new_nodes)"))
            else:
                touched_nodes.add(n)
                if n in family_of:
                    touched_families.add(family_of[n])

        for u, v in zip(path, path[1:]):
            if u not in nodes or v not in nodes or u == v:
                continue
            edge = E.get((u, v))
            if edge is None:
                r = _shortest(u, v, succ)
                if r:
                    qs.append((
                        "SKIPPED_STEPS",
                        f"{u} -> {v}: graph passes through {' -> '.join(r)}; what happens at the intermediate steps?",
                    ))
                else:
                    qs.append((
                        "UNMAPPED_TRANSITION",
                        f"{u} -> {v}: no route in graph — consider proposing a new node/edge if the document has a mechanism here.",
                    ))
            else:
                loses = edge.get("loses") or []
                if edge.get("kind") == "measures" and loses:
                    qs.append((
                        "FRAME_SHIFT_LOSS",
                        f"{u} -> {v} [measures]: frame shift drops [{'; '.join(loses)}] — open question: how does this loss affect the framing?",
                    ))

            if u not in measure_nodes and v not in measure_nodes:
                rev = _shortest(v, u, succ, avoid=frozenset(measure_nodes), max_hops=3, forbid_edges=measure_edges)
                if rev:
                    qs.append((
                        "REVERSE_ROUTE",
                        f"{v} can feed back to {u} via {' -> '.join(rev)} — open question on causal direction.",
                    ))

            if v not in measure_nodes:
                exclude_cc = measure_nodes | actor_nodes | set(path)
                commons = sorted(
                    w for w in pred.get(u, ())
                    if w not in exclude_cc
                    and _shortest(w, v, succ, avoid=frozenset(measure_nodes | {u}), forbid_edges=measure_edges) is not None
                )
                if commons:
                    qs.append((
                        "COMMON_CAUSE",
                        f"{u} -> {v}: shared upstream factor(s) " + "; ".join(_show_node(w, nodes) for w in commons),
                    ))

        for v in path[1:]:
            if v in measure_nodes or v not in nodes:
                continue
            rivals = sorted(w for w in pred.get(v, ()) if w not in path and w not in measure_nodes and w not in actor_nodes)
            if rivals:
                qs.append((
                    "PARALLEL_INPUTS",
                    f"{v} also receives " + "; ".join(_show_node(w, nodes) for w in rivals) + " — open exploration branches.",
                ))

        if path and path[-1] in family_of:
            fam = family_of[path[-1]]
            sibs = sorted(n for n, fn in family_of.items() if fn == fam and n != path[-1] and n not in path)
            if sibs:
                qs.append((
                    "SIBLING_FRAMES",
                    f"{path[-1]} is one frame of family '{fam}'; other frame(s): " + "; ".join(_show_node(s, nodes) for s in sibs),
                ))

        anchor_results.append({
            "id": item.get("id"),
            "quote": item.get("quote"),
            "path": path,
            "questions": [{"kind": k, "text": t} for k, t in qs],
        })

    upstream_all = _bfs_reachable(touched_nodes, pred) - touched_nodes
    downstream_all = _bfs_reachable(touched_nodes, succ) - touched_nodes
    untouched: dict[str, list[dict[str, Any]]] = {
        "sibling_frame": [],
        "upstream": [],
        "downstream": [],
        "other_branch": [],
    }
    for n in sorted(nodes):
        if n in touched_nodes or n in actor_nodes:
            continue
        entry = {
            "id": n,
            "display": _show_node(n, nodes),
            "role": role[n],
            "family": family_of.get(n),
        }
        if family_of.get(n) in touched_families:
            untouched["sibling_frame"].append(entry)
        elif n in upstream_all:
            untouched["upstream"].append(entry)
        elif n in downstream_all:
            untouched["downstream"].append(entry)
        else:
            untouched["other_branch"].append(entry)

    proposal_audit = []
    for p in trace.get("proposed_new_nodes", []):
        errs = []
        pid = p.get("id", "")
        if not isinstance(pid, str) or not re.match(r"^[A-Z][A-Z0-9_]+$", pid):
            errs.append("id must be UPPER_SNAKE")
        if pid in nodes:
            errs.append("id already exists in graph (use challenged_graph_items to split/revise)")
        name = p.get("name", "")
        if not isinstance(name, str) or "[" not in name or "]" not in name:
            errs.append("name must include explicit [frame] per NMF")
        if p.get("role") not in VALID_ROLES:
            errs.append(f"role must be one of {sorted(VALID_ROLES)}")
        params = p.get("params", {})
        if not isinstance(params, dict):
            errs.append("params must be an object")
        else:
            for pk, pvs in params.items():
                if not isinstance(pvs, list) or "other" not in pvs:
                    errs.append(f"param '{pk}' must be a list including 'other'")
        if p.get("source") == "document" and not _match_quote(p.get("doc_quote"), doc):
            errs.append("source='document' requires verbatim doc_quote found in document")
        for edge_spec in p.get("proposed_edges", []):
            if edge_spec.get("kind") not in VALID_EDGE_KINDS:
                errs.append(f"invalid edge kind '{edge_spec.get('kind')}'")
            if edge_spec.get("kind") == "measures" and not edge_spec.get("loses"):
                errs.append("measures edge must declare non-empty loses")
        proposal_audit.append({"id": pid, "valid": not errs, "errors": errs})

    challenge_audit = []
    for ch in trace.get("challenged_graph_items", []):
        errs = []
        target_type = ch.get("target_type")
        if target_type == "node":
            if ch.get("target") not in nodes:
                errs.append(f"target node '{ch.get('target')}' not in graph")
        elif target_type == "edge":
            t = ch.get("target")
            if not (isinstance(t, list) and len(t) == 2 and (t[0], t[1]) in E):
                errs.append(f"target edge '{t}' not in graph")
        else:
            errs.append("target_type must be 'node' or 'edge'")
        if ch.get("challenge_kind") not in VALID_CHALLENGE_KINDS:
            errs.append(f"challenge_kind must be one of {sorted(VALID_CHALLENGE_KINDS)}")
        if ch.get("doc_quote") and not _match_quote(ch.get("doc_quote"), doc):
            errs.append("doc_quote not found verbatim in document")
        if not _norm(ch.get("reason")):
            errs.append("reason must be non-empty")
        challenge_audit.append({
            "target": ch.get("target"),
            "challenge_kind": ch.get("challenge_kind"),
            "valid": not errs,
            "errors": errs,
        })

    gate_audit: dict[str, Any] = {"present": False, "valid": True, "decision": None, "errors": []}
    if "pre_gate" in trace:
        gate_audit["present"] = True
        pg = trace["pre_gate"]
        gerrs = []
        if not isinstance(pg, dict):
            gerrs.append("pre_gate must be an object")
        else:
            dec = pg.get("decision")
            gate_audit["decision"] = dec
            if dec not in VALID_GATE_DECISIONS:
                gerrs.append(f"pre_gate.decision must be one of {sorted(VALID_GATE_DECISIONS)}")
            if not _norm(pg.get("reason")):
                gerrs.append("pre_gate.reason must be non-empty")
            if dec == "stop_at_pre":
                bg = pg.get("blocking_gaps")
                if not isinstance(bg, list) or len(bg) == 0 or not all(isinstance(x, str) and x.strip() for x in bg):
                    gerrs.append("stop_at_pre requires non-empty string list blocking_gaps")
            elif dec == "proceed_to_post":
                cands = pg.get("post_candidate_claims")
                if not isinstance(cands, list) or len(cands) == 0:
                    gerrs.append("proceed_to_post requires non-empty post_candidate_claims")
                else:
                    for ci, cand in enumerate(cands):
                        if not isinstance(cand, dict):
                            gerrs.append(f"post_candidate_claims[{ci}] must be an object")
                            continue
                        if not _match_quote(cand.get("quote"), doc):
                            gerrs.append(f"post_candidate_claims[{ci}].quote not found verbatim in document")
                        if not _norm(cand.get("target_mechanism")):
                            gerrs.append(f"post_candidate_claims[{ci}].target_mechanism must be non-empty")
            oqs = pg.get("open_questions_for_post", [])
            if not isinstance(oqs, list):
                gerrs.append("open_questions_for_post must be a list")
            else:
                for qi, qitem in enumerate(oqs):
                    for qe in validate_open_question(qitem, doc):
                        gerrs.append(f"open_questions_for_post[{qi}]: {qe}")
        gate_audit["errors"] = gerrs
        gate_audit["valid"] = not gerrs

    return {
        "document_sha256": doc.sha256,
        "document_source": doc.source_ref,
        "summary": {
            "graph_nodes": len(nodes),
            "touched_nodes": len(touched_nodes),
            "untouched_non_actor_nodes": sum(len(v) for v in untouched.values()),
            "anchors": len(anchor_results),
            "anchor_questions": sum(len(a["questions"]) for a in anchor_results),
            "proposed_new_nodes_total": len(proposal_audit),
            "proposed_new_nodes_valid": sum(1 for x in proposal_audit if x["valid"]),
            "challenged_items_total": len(challenge_audit),
            "challenged_items_valid": sum(1 for x in challenge_audit if x["valid"]),
            "pre_gate_decision": gate_audit["decision"],
            "pre_gate_valid": gate_audit["valid"],
        },
        "untouched_frontier": untouched,
        "anchor_probes": anchor_results,
        "proposal_audit": proposal_audit,
        "challenge_audit": challenge_audit,
        "pre_gate_audit": gate_audit,
    }


def merge_patch_graph(graph_path: Path, trace_path: Path, out_graph_path: Path) -> tuple[int, int]:
    with graph_path.open(encoding="utf-8") as f:
        g = json.load(f)
    with trace_path.open(encoding="utf-8") as f:
        trace = json.load(f)

    nodes = dict(g.get("nodes", {}))
    edges = [dict(e) for e in g.get("edges", [])]

    for p in trace.get("proposed_new_nodes", []):
        pid = p.get("id")
        if pid and pid not in nodes:
            nd: dict[str, Any] = {
                "names": [p["name"]],
                "role": p.get("role", "process_state"),
                "provenance": f"agent_proposed:{p.get('source', 'exploration')}",
                "status": "proposed",
                "params": p.get("params", {}),
            }
            if p.get("family"):
                nd["family"] = p["family"]
            nodes[pid] = nd
        for e in p.get("proposed_edges", []):
            edges.append({
                "from": e["from"],
                "to": e["to"],
                "kind": e["kind"],
                "steps": [e.get("step", "")],
                "loses": e.get("loses", []),
                "status": "proposed",
            })

    challenged_nodes: dict[str, list[dict[str, Any]]] = {}
    challenged_edges: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for ch in trace.get("challenged_graph_items", []):
        if ch.get("target_type") == "node":
            challenged_nodes.setdefault(ch["target"], []).append(
                {"challenge_kind": ch["challenge_kind"], "reason": ch["reason"]}
            )
        elif ch.get("target_type") == "edge" and isinstance(ch.get("target"), list) and len(ch.get("target")) == 2:
            challenged_edges.setdefault((ch["target"][0], ch["target"][1]), []).append(
                {"challenge_kind": ch["challenge_kind"], "reason": ch["reason"]}
            )

    for nid, notes in challenged_nodes.items():
        if nid in nodes:
            nodes[nid] = dict(nodes[nid])
            nodes[nid]["challenges"] = notes
    for e in edges:
        key = (e["from"], e["to"])
        if key in challenged_edges:
            e["challenges"] = challenged_edges[key]

    patched = {**g, "nodes": nodes, "edges": edges}
    _atomic_write_text(out_graph_path, json.dumps(patched, ensure_ascii=False, indent=1))
    return len(nodes), len(edges)


PRE_HANDOFF_FILENAMES = (
    "explore.json",
    "explored-graph.json",
    "pre_gate_report.md",
    "post_brief.md",
    "questions_seed.json",
)


def invalidate_pre_handoff_artifacts(out_dir: Path, preserve_paths: set[Path] | None = None) -> None:
    """Remove prior Pre handoff/gate artifacts in `out_dir`, preserving any listed input paths."""
    if not out_dir.exists():
        return
    preserved = {p.resolve() for p in (preserve_paths or set())}
    for fname in PRE_HANDOFF_FILENAMES:
        candidate = out_dir / fname
        if candidate.resolve() in preserved:
            continue
        _unlink_if_exists(candidate)


def check_pre_input_output_aliasing(
    out_dir: Path,
    graph_path: Path,
    trace_path: Path,
    doc_ref: str,
) -> str | None:
    """Return an error message if any input path resolves to a managed output file in `out_dir`."""
    managed = {(out_dir / fname).resolve(): fname for fname in PRE_HANDOFF_FILENAMES}
    inputs = [("graph", graph_path), ("trace", trace_path)]
    doc_p = Path(doc_ref)
    if not doc_ref.startswith("arxiv:") and doc_p.exists():
        inputs.append(("doc", doc_p))
    for label, p in inputs:
        rp = p.resolve()
        if rp in managed:
            return (
                f"Refusing in-place overwrite: --{label} ({p}) resolves to output artifact "
                f"'{managed[rp]}' inside --out ({out_dir}); use a distinct --out directory."
            )
    return None


def run_pre_handoff(
    graph_path: Path,
    trace_path: Path,
    doc: IngestedDocument,
    out_dir: Path,
) -> tuple[dict[str, Any], int, str]:
    """Execute Pre probe + non-destructive merge-patch + Pre-Gate handoff.

    Invalidates ALL prior Pre artifacts (including `explore.json`) up front so
    a crash, malformed trace, `stop_at_pre`, or invalid gate rerun in the same
    directory can never leave a stale `proceed_to_post` pass or stale Post
    handoff files behind. Refuses in-place aliasing of input files with output
    artifacts before touching the input graph. Publishes `explore.json`
    atomically LAST, only after all handoff artifacts have been written.
    Returns `(probe_result, exit_code, status_line)`.
    """
    preserve = {graph_path.resolve(), trace_path.resolve()}
    invalidate_pre_handoff_artifacts(out_dir, preserve_paths=preserve)
    alias_err = check_pre_input_output_aliasing(out_dir, graph_path, trace_path, doc.source_ref)
    if alias_err:
        return {}, 2, alias_err

    out_dir.mkdir(parents=True, exist_ok=True)
    explore_path = out_dir / "explore.json"
    patched_path = out_dir / "explored-graph.json"
    report_path = out_dir / "pre_gate_report.md"
    brief_path = out_dir / "post_brief.md"
    qseed_path = out_dir / "questions_seed.json"

    result = compute_probe(graph_path, trace_path, doc)
    with trace_path.open(encoding="utf-8") as f:
        trace = json.load(f)

    merge_patch_graph(graph_path, trace_path, patched_path)

    ga = result["pre_gate_audit"]
    if not ga["present"]:
        _atomic_write_text(explore_path, json.dumps(result, ensure_ascii=False, indent=1))
        return result, 2, "pre_gate error: trace.json is missing required 'pre_gate' section"
    if not ga["valid"]:
        _atomic_write_text(explore_path, json.dumps(result, ensure_ascii=False, indent=1))
        return result, 2, "pre_gate error: validation failed:\n  - " + "\n  - ".join(ga["errors"])

    pg = trace["pre_gate"]
    dec = pg["decision"]
    s = result["summary"]

    lines = [
        f"# Pre-Formalization Gate Report (`{dec}`)",
        "",
        f"- **Document:** `{doc.source_ref}` (SHA-256 `{doc.sha256[:16]}`)",
        f"- **Decision:** `{dec}`",
        f"- **Reason:** {pg['reason']}",
        f"- **Graph coverage:** {s['touched_nodes']}/{s['graph_nodes']} nodes touched; {s['untouched_non_actor_nodes']} untouched non-actor frontier nodes",
        f"- **Epistemic independence:** {s['proposed_new_nodes_valid']}/{s['proposed_new_nodes_total']} valid new node proposals; {s['challenged_items_valid']}/{s['challenged_items_total']} valid graph challenges",
        "",
    ]

    if dec == "stop_at_pre":
        lines.append("## Blocking Pre-Formalization Gaps (Stopped Before Post/Lean)")
        for b in pg.get("blocking_gaps", []):
            lines.append(f"- {b}")
        lines.append("")
        lines.append("## Untouched Graph Frontier (Open Questions)")
        for bucket in ("sibling_frame", "upstream", "downstream", "other_branch"):
            items = result["untouched_frontier"][bucket]
            if items:
                lines.append(f"- **{bucket}:** " + "; ".join(x["display"] for x in items))
        _atomic_write_text(report_path, "\n".join(lines) + "\n")
        _atomic_write_text(explore_path, json.dumps(result, ensure_ascii=False, indent=1))
        return result, 0, f"GATE=stop_at_pre (stopped cleanly; no Post handoff emitted) -> {report_path}"

    lines.append("## Candidate Claims Cleared for Post-Formalization (Lean `OperationFlow`)")
    for idx, c in enumerate(pg.get("post_candidate_claims", []), 1):
        lines.append(f"{idx}. **{c['target_mechanism']}** — `\"{c['quote']}\"`")
    _atomic_write_text(report_path, "\n".join(lines) + "\n")

    brief = [
        "# Pre -> Post Handoff Brief (for `pipeline.audit_cli run`)",
        "",
        f"Document: `{doc.source_ref}` (SHA-256 `{doc.sha256[:16]}`).",
        "Pre-formalization passed. Use the concrete mechanisms and frame cuts below when building the Post `AuditSpec` JSON for Lean `OperationFlow` verification (evaluate them independently; push back on Pre wherever the document differs):",
        "",
        "## 1. Candidate Claims to Formalize",
    ]
    for idx, c in enumerate(pg.get("post_candidate_claims", []), 1):
        brief.append(f"{idx}. **{c['target_mechanism']}**\n   - Quote: `{c['quote']}`")

    brief.append("")
    brief.append("## 2. Concrete Mechanisms Discovered in Pre (Do Not Collapse)")
    for p in trace.get("proposed_new_nodes", []):
        brief.append(f"- **`{p['id']}`** — {p['name']} (`{p.get('role')}`, source=`{p.get('source')}`): {p.get('why_missing', '')}")

    brief.append("")
    brief.append("## 3. Graph Pushbacks Recorded in Pre")
    for ch in trace.get("challenged_graph_items", []):
        brief.append(f"- **`{ch['target']}`** (`{ch['challenge_kind']}`): {ch['reason']}")

    brief.append("")
    brief.append("## 4. Open Pre-Formalization Questions (`questions_seed.json`, `verified_by_lean: false`)")
    oqs = pg.get("open_questions_for_post", [])
    if oqs:
        for qi, q in enumerate(oqs, 1):
            brief.append(f"{qi}. [{q['status']}] `{q['phrase']}` — {q['question']}")
    else:
        brief.append("- (None carried forward)")

    _atomic_write_text(brief_path, "\n".join(brief) + "\n")
    _atomic_write_text(qseed_path, json.dumps({"questions": oqs}, ensure_ascii=False, indent=1))
    # Publish explore.json LAST so a `proceed_to_post` pass only appears after handoff completes.
    _atomic_write_text(explore_path, json.dumps(result, ensure_ascii=False, indent=1))
    return result, 0, f"GATE=proceed_to_post -> {brief_path} + {qseed_path} ({len(oqs)} questions)"


def check_pre_gate_for_post(explore_json_path: Path, doc: IngestedDocument) -> tuple[bool, str]:
    """Verify a Pre `explore.json` cleared `proceed_to_post` for this exact document snapshot."""
    try:
        with explore_json_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return False, f"Cannot read --pre-gate file {explore_json_path}: {exc}"

    gate = data.get("pre_gate_audit") if isinstance(data, dict) else None
    if not isinstance(gate, dict) or not gate.get("present"):
        return False, f"--pre-gate file {explore_json_path} has no pre_gate_audit; run `audit_cli pre` first."
    if not gate.get("valid"):
        return False, f"--pre-gate validation failed ({gate.get('errors')}); Post/Lean skipped."

    pre_sha = data.get("document_sha256")
    if not isinstance(pre_sha, str) or not pre_sha:
        return False, f"--pre-gate file {explore_json_path} is missing document_sha256; Post/Lean skipped."
    if pre_sha != doc.sha256:
        return (
            False,
            f"--pre-gate document SHA-256 ({pre_sha[:16]}) does not match --doc ({doc.sha256[:16]}); Post/Lean skipped.",
        )

    dec = gate.get("decision")
    if dec == "stop_at_pre":
        return False, f"Pre-Gate decision is `stop_at_pre` ({explore_json_path}); Post/Lean verification skipped."
    if dec != "proceed_to_post":
        return False, f"Unknown Pre-Gate decision {dec!r}; Post/Lean skipped."
    return True, "Pre-Gate cleared (`proceed_to_post`)."


def build_preform_prompt(doc: IngestedDocument, graph_ref: str = "concept-graph.json") -> str:
    """Emit the bidirectional NMF + IPOD Pre-Formalization & Pre-Gate prompt."""
    return f"""PRE-FORMALIZATION EXPLORATION & PRE-GATE TASK (Bidirectional NMF + IPOD)

Inputs:
- Source document below (`{doc.source_ref}`, SHA-256 `{doc.sha256[:16]}`). Read it completely.
- Concept graph (`{graph_ref}`): an OPTIONAL typed NMF + IPOD process graph built before seeing this document.
  IMPORTANT: This graph is an OPTIONAL EXPLORATION TOOL, NOT ground truth and NOT a mandatory policy.
  It WILL miss mechanisms, collapse distinct steps into vague nodes, or contain mis-framed / foreign nodes.

GOAL:
1. **Pre-formalization exploration (NOT paper validity grading):** ask open questions, surface hidden frames
   and process cuts, propose NEW NMF+IPOD nodes/edges, and push back against the graph wherever it is wrong,
   over-collapsed, or foreign. Do NOT score the paper or force every untouched node to "catch an error".
2. **Epistemic independence:** NEVER cram a concrete mechanism from the document into a vague existing graph
   node just to make a path fit. Propose a new node and challenge the collapsed node instead.
3. **Pre-Gate decision (`pre_gate`):** decide honestly whether formalizing this document into Stage 2 Post
   (`python3 -m pipeline.audit_cli run` + Lean `OperationFlow`) is warranted right now:
   - `stop_at_pre`: use when the document's core argument has no concrete operational mechanism/data to
     formalize, or collapses incompatible measurement frames before any structural proof can even be stated
     (stopping at Pre saves wasted Post/Lean formalization).
   - `proceed_to_post`: use when the document states concrete operational steps/methods/claims worth verifying
     structurally in Lean `OperationFlow`; list candidate claims and carry open Pre questions cleanly into
     `open_questions_for_post` (matching `pipeline/schema.py`'s `questions` contract).

Step 1. Write `trace.json`:
{{
  "document_anchors": [
    {{
      "id": "A1",
      "quote": "<verbatim sentence from document, >=12 non-space chars>",
      "path": ["<existing node IDs that genuinely fit — omit steps the graph lacks>"]
    }}
  ],
  "proposed_new_nodes": [
    {{
      "id": "NEW_NODE_UPPER_SNAKE",
      "name": "Concrete Process or Concept Name [explicit frame]",
      "role": "actor | process_state | measure",
      "family": "<optional shared family>",
      "params": {{ "<param_name>": ["<value1>", "<value2>", "other"] }},
      "source": "document | outside_both",
      "doc_quote": "<verbatim quote if source=='document', else omit>",
      "why_missing": "<what the blind graph missed or collapsed>",
      "proposed_edges": [
        {{
          "from": "<node_id>",
          "to": "<node_id>",
          "kind": "generates | regulates | measures",
          "step": "<concrete mechanism>",
          "loses": ["<required if kind=='measures'>"]
        }}
      ]
    }}
  ],
  "challenged_graph_items": [
    {{
      "target_type": "node | edge",
      "target": "<NODE_ID> or [\"FROM_ID\", \"TO_ID\"]",
      "challenge_kind": "wrong_direction | collapsed_step | wrong_frame | irrelevant_to_domain | single_report_bias | missing_distinction | other",
      "doc_quote": "<optional verbatim quote if grounded in doc>",
      "reason": "<epistemic pushback explaining why this graph node/edge is wrong, collapsed, or foreign>"
    }}
  ],
  "pre_gate": {{
    "decision": "stop_at_pre | proceed_to_post",
    "reason": "<clear justification>",
    "blocking_gaps": ["<required non-empty list if stop_at_pre>"],
    "post_candidate_claims": [
      {{
        "quote": "<verbatim claim sentence in document, required if proceed_to_post>",
        "target_mechanism": "<concrete operational claim to formalize in Lean>"
      }}
    ],
    "open_questions_for_post": [
      {{
        "about_quote": "<verbatim sentence in document>",
        "phrase": "<exact substring inside about_quote>",
        "question": "<open pre-formalization question>",
        "asked_by": "reader",
        "status": "not_in_document | partly | answered",
        "searched": "<required if not_in_document: where in the document you checked>",
        "answer_quotes": ["<required non-empty verbatim quotes if answered/partly; OMIT if not_in_document>"],
        "answer": "<required if answered/partly>",
        "stays_open": "<required if partly>"
      }}
    ]
  }}
}}

Step 2. Run the unified CLI to validate and execute the Pre-Gate:
  python3 -m pipeline.audit_cli pre --graph {graph_ref} --trace trace.json --doc <doc> --out pre-out
Fix any quote, NMF schema, or `pre_gate` validation errors reported.

Step 3. Write `exploration.md` (concise, 5 sections):
1. Pre-Gate decision (`stop_at_pre` / `proceed_to_post`) and reason.
2. Untouched frontier & open questions (Graph -> Document).
3. Proposed new NMF+IPOD nodes/edges (Document -> Graph).
4. Pushback against the graph (wrong frame, collapsed step, foreign bias).
5. Free exploration beyond both graph and document (optional).

SOURCE DOCUMENT ({doc.source_ref}, SHA-256 {doc.sha256[:16]}):
--- BEGIN DOCUMENT ---
{doc.raw_text}
--- END DOCUMENT ---
"""
