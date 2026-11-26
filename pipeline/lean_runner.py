"""Safe Lean 4 code generation, kernel-checked `decide` proof synthesis, and axiom guard."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_AXIOMS = frozenset({"propext", "Quot.sound"})
AXIOM_LINE_RE = re.compile(r"^'([^']+)' depends on axioms: \[([^\]]*)\]$")
NO_AXIOM_LINE_RE = re.compile(r"^'([^']+)' does not depend on any axioms$")


@dataclass(frozen=True)
class LeanClaimResult:
    claim_id: str
    verdict: str
    findings: list[dict[str, Any]]
    axioms: list[str]
    kernel_verified: bool


@dataclass(frozen=True)
class LeanVerificationResult:
    lean_file: Path
    claims: list[LeanClaimResult]
    raw_axioms_ok: bool


def escape_lean_str(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _lean_tag_list(tags: list[str]) -> str:
    if not tags:
        return "[]"
    return "[" + ", ".join(f".{t}" for t in tags) + "]"


def _lean_node_list(nodes: list[str]) -> str:
    if not nodes:
        return "[]"
    return "[" + ", ".join(f".{n}" for n in nodes) + "]"


def _lean_op_kind(op: dict[str, Any]) -> str:
    kind = op["kind"]
    if kind == "forget":
        return f".forget .{op['tag']} .{op['evidence']}"
    return f".{kind} {_lean_tag_list(op['introduces'])}"


def _lean_claim_kind(cl: dict[str, Any]) -> str:
    kind = cl["kind"]
    if kind == "emergesWithout":
        return f".emergesWithout .{cl['target']} .{cl['tag']}"
    if kind == "emergesWithExclusion":
        return f".emergesWithExclusion .{cl['target']} .{cl['excluded_channel']} .{cl['tag']}"
    if kind == "independentConvergence":
        return f".independentConvergence .{cl['branch_a']} .{cl['branch_b']} .{cl['tag']}"
    if kind == "uniqueRecovery":
        return f".uniqueRecovery .{cl['target']} .{cl['tag']}"
    return f".conditionalFlow .{cl['target']} {_lean_node_list(cl['declared_sources'])}"


def _render_base_module(spec: dict[str, Any], namespace: str) -> str:
    lines: list[str] = [
        "import EpistemicLedger.OperationFlow",
        "",
        f"namespace {namespace}",
        "",
        "open EpistemicLedger",
        "open EpistemicLedger.OperationFlow",
        "",
        "inductive Node where",
    ]
    for n in spec["nodes"]:
        lines.append(f"  | {n}")
    lines += ["  deriving DecidableEq, Repr", "", "inductive Tag where"]
    for t in spec["tags"]:
        lines.append(f"  | {t}")
    lines += ["  deriving DecidableEq, Repr", ""]

    # Node/Tag JSON helpers for deterministic Stage-1 extraction
    lines += ["def nodeName : Node → String"]
    for n in spec["nodes"]:
        lines.append(f'  | .{n} => "{n}"')
    lines += ["", "def tagName : Tag → String"]
    for t in spec["tags"]:
        lines.append(f'  | .{t} => "{t}"')
    lines += [
        "",
        "def invName : Invariance → String",
        '  | .shown => "shown"',
        '  | .notShown => "notShown"',
        '  | .contradicted => "contradicted"',
        "",
        "def verdictName : FlowVerdict → String",
        '  | .admissible => "admissible"',
        '  | .rejected => "rejected"',
        "",
        "def jsonEscape (s : String) : String :=",
        '  s.foldl (fun acc c => acc ++ match c with',
        "    | '\\\\' => \"\\\\\\\\\"",
        "    | '\"' => \"\\\\\\\"\"",
        "    | '\\n' => \"\\\\n\"",
        "    | '\\r' => \"\\\\r\"",
        "    | '\\t' => \"\\\\t\"",
        "    | _ => String.singleton c) \"\"",
        "",
        "def jsonStr (s : String) : String := \"\\\"\" ++ jsonEscape s ++ \"\\\"\"",
        "",
        "def jsonNodeList (ns : List Node) : String :=",
        '  "[" ++ String.intercalate "," (ns.map (fun n => jsonStr (nodeName n))) ++ "]"',
        "",
        "def findingToJson : FlowFinding Node Tag → String",
        '  | .smuggledStructure tag origin path =>',
        '      "{\\"type\\":\\"smuggledStructure\\",\\"tag\\":" ++ jsonStr (tagName tag) ++',
        '      ",\\"origin\\":" ++ jsonStr (nodeName origin) ++ ",\\"path\\":" ++ jsonNodeList path ++ "}"',
        '  | .excludedChannelLeak tag origin path =>',
        '      "{\\"type\\":\\"excludedChannelLeak\\",\\"tag\\":" ++ jsonStr (tagName tag) ++',
        '      ",\\"origin\\":" ++ jsonStr (nodeName origin) ++ ",\\"path\\":" ++ jsonNodeList path ++ "}"',
        '  | .authorSuppliedStructure tag origin path =>',
        '      "{\\"type\\":\\"authorSuppliedStructure\\",\\"tag\\":" ++ jsonStr (tagName tag) ++',
        '      ",\\"origin\\":" ++ jsonStr (nodeName origin) ++ ",\\"path\\":" ++ jsonNodeList path ++ "}"',
        '  | .failedForgetOnPath opName tag ev =>',
        '      "{\\"type\\":\\"failedForgetOnPath\\",\\"op\\":" ++ jsonStr opName ++',
        '      ",\\"tag\\":" ++ jsonStr (tagName tag) ++ ",\\"evidence\\":" ++ jsonStr (invName ev) ++ "}"',
        '  | .sharedUpstreamStructure shared tag =>',
        '      "{\\"type\\":\\"sharedUpstreamStructure\\",\\"shared\\":" ++ jsonStr (nodeName shared) ++',
        '      ",\\"tag\\":" ++ jsonStr (tagName tag) ++ "}"',
        '  | .sharedExperimenterSource shared =>',
        '      "{\\"type\\":\\"sharedExperimenterSource\\",\\"shared\\":" ++ jsonStr (nodeName shared) ++ "}"',
        '  | .lossyChannelOnPath opName output =>',
        '      "{\\"type\\":\\"lossyChannelOnPath\\",\\"op\\":" ++ jsonStr opName ++',
        '      ",\\"output\\":" ++ jsonStr (nodeName output) ++ "}"',
        '  | .unaccessedTargetStructure target tag =>',
        '      "{\\"type\\":\\"unaccessedTargetStructure\\",\\"target\\":" ++ jsonStr (nodeName target) ++',
        '      ",\\"tag\\":" ++ jsonStr (tagName tag) ++ "}"',
        '  | .undeclaredUpstreamSource src =>',
        '      "{\\"type\\":\\"undeclaredUpstreamSource\\",\\"source\\":" ++ jsonStr (nodeName src) ++ "}"',
        '  | .danglingInput opName missing =>',
        '      "{\\"type\\":\\"danglingInput\\",\\"op\\":" ++ jsonStr opName ++',
        '      ",\\"missing\\":" ++ jsonStr (nodeName missing) ++ "}"',
        "",
        "def findingsToJson (fs : List (FlowFinding Node Tag)) : String :=",
        '  "[" ++ String.intercalate "," (fs.map findingToJson) ++ "]"',
        "",
        "def graph : FlowGraph Node Tag where",
        "  sources :=",
    ]
    if not spec["sources"]:
        lines.append("    []")
    else:
        for idx, src in enumerate(spec["sources"]):
            prefix = "    [ " if idx == 0 else "    , "
            lines.append(f"{prefix}⟨.{src['node']}, .{src['origin']}, {_lean_tag_list(src['carries'])}⟩")
        lines.append("    ]")

    lines.append("  ops :=")
    if not spec["ops"]:
        lines.append("    []")
    else:
        for idx, op in enumerate(spec["ops"]):
            prefix = "    [ " if idx == 0 else "    , "
            name_esc = escape_lean_str(op["name"])
            lines.append(
                f'{prefix}⟨"{name_esc}", {_lean_node_list(op["inputs"])}, .{op["output"]}, {_lean_op_kind(op)}⟩'
            )
        lines.append("    ]")
    lines.append("")

    for cl in spec["claims"]:
        stmt_esc = escape_lean_str(cl["statement"])
        lines += [
            f"def claim_{cl['id']} : FlowClaim Node Tag where",
            f'  statement := "{stmt_esc}"',
            "  graph := graph",
            f"  kind := {_lean_claim_kind(cl)}",
            "",
        ]
    return "\n".join(lines)


def _finding_to_lean_expr(f: dict[str, Any]) -> str:
    ft = f["type"]
    if ft == "smuggledStructure":
        return f"FlowFinding.smuggledStructure Tag.{f['tag']} Node.{f['origin']} {_lean_node_list(f['path'])}"
    if ft == "excludedChannelLeak":
        return f"FlowFinding.excludedChannelLeak Tag.{f['tag']} Node.{f['origin']} {_lean_node_list(f['path'])}"
    if ft == "authorSuppliedStructure":
        return f"FlowFinding.authorSuppliedStructure Tag.{f['tag']} Node.{f['origin']} {_lean_node_list(f['path'])}"
    if ft == "failedForgetOnPath":
        return f'FlowFinding.failedForgetOnPath "{escape_lean_str(f["op"])}" Tag.{f["tag"]} Invariance.{f["evidence"]}'
    if ft == "sharedUpstreamStructure":
        return f"FlowFinding.sharedUpstreamStructure Node.{f['shared']} Tag.{f['tag']}"
    if ft == "sharedExperimenterSource":
        return f"FlowFinding.sharedExperimenterSource Node.{f['shared']}"
    if ft == "lossyChannelOnPath":
        return f'FlowFinding.lossyChannelOnPath "{escape_lean_str(f["op"])}" Node.{f["output"]}'
    if ft == "unaccessedTargetStructure":
        return f"FlowFinding.unaccessedTargetStructure Node.{f['target']} Tag.{f['tag']}"
    if ft == "undeclaredUpstreamSource":
        return f"FlowFinding.undeclaredUpstreamSource Node.{f['source']}"
    if ft == "danglingInput":
        return f'FlowFinding.danglingInput "{escape_lean_str(f["op"])}" Node.{f["missing"]}'
    raise ValueError(f"Unknown finding type from Lean output: {ft!r}")


def _run_lean(repo_root: Path, lean_source: str) -> str:
    proc = subprocess.run(
        ["lake", "env", "lean", "--stdin"],
        cwd=str(repo_root),
        input=lean_source,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Lean kernel check failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def _parse_axioms(stdout: str) -> dict[str, list[str]]:
    axioms_map: dict[str, list[str]] = {}
    # Join wrapped axiom lines if Lean wraps long outputs across lines
    joined_lines: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        if line.startswith(" ") and joined_lines:
            joined_lines[-1] = joined_lines[-1] + " " + line.strip()
        else:
            joined_lines.append(line)

    for line in joined_lines:
        m = AXIOM_LINE_RE.match(line)
        if m:
            thm = m.group(1)
            raw_list = [a.strip() for a in m.group(2).split(",") if a.strip()]
            axioms_map[thm] = raw_list
            continue
        m2 = NO_AXIOM_LINE_RE.match(line)
        if m2:
            axioms_map[m2.group(1)] = []
    return axioms_map


def run_lean_verification(
    spec: dict[str, Any], repo_root: Path, out_lean_path: Path, namespace: str | None = None
) -> LeanVerificationResult:
    """Two-pass Lean 4 kernel verification:
    Pass 1: Evaluate `flowVerdict` and `auditFlow` inside `lake env lean`.
    Pass 2: Synthesize standalone `decide` proof file certifying exact verdicts & finding lists,
            compile it with `lake env lean`, and enforce axiom whitelist `{propext, Quot.sound}`.
    """
    ns = namespace or f"EpistemicLedger.Generated.{spec['auditor']}"
    base = _render_base_module(spec, ns)

    # Pass 1: evaluate verdicts & findings as JSON lines
    eval_lines = [base]
    for cl in spec["claims"]:
        cid = cl["id"]
        eval_lines.append(
            f'#eval IO.println ("EPISTEMIC_JSON:" ++ "{{\\"id\\":\\"{cid}\\",\\"verdict\\":" ++ '
            f'jsonStr (verdictName (flowVerdict claim_{cid})) ++ ",\\"findings\\":" ++ '
            f'findingsToJson (auditFlow claim_{cid}) ++ "}}")'
        )
    eval_lines.append(f"end {ns}")
    pass1_out = _run_lean(repo_root, "\n".join(eval_lines) + "\n")

    parsed_by_id: dict[str, dict[str, Any]] = {}
    for line in pass1_out.splitlines():
        if line.startswith("EPISTEMIC_JSON:"):
            payload = json.loads(line[len("EPISTEMIC_JSON:") :])
            parsed_by_id[payload["id"]] = payload

    missing_ids = [cl["id"] for cl in spec["claims"] if cl["id"] not in parsed_by_id]
    if missing_ids:
        raise RuntimeError(f"Lean pass 1 did not return results for claim(s): {missing_ids}")

    # Pass 2: synthesize standalone kernel-checked `decide` proof file + #print axioms
    proof_lines = [base]
    for cl in spec["claims"]:
        cid = cl["id"]
        verdict = parsed_by_id[cid]["verdict"]
        findings = parsed_by_id[cid]["findings"]
        findings_lean = "[" + ", ".join(_finding_to_lean_expr(f) for f in findings) + "]"
        proof_lines += [
            f"theorem claim_{cid}_verdict : flowVerdict claim_{cid} = .{verdict} := by decide",
            f"theorem claim_{cid}_findings : auditFlow claim_{cid} = {findings_lean} := by decide",
            "",
        ]
    proof_lines.append(f"end {ns}")
    proof_source = "\n".join(proof_lines) + "\n"

    out_lean_path.parent.mkdir(parents=True, exist_ok=True)
    out_lean_path.write_text(proof_source, encoding="utf-8")

    # Verify the written proof file + print axioms for every theorem
    axiom_check_lines = [proof_source]
    for cl in spec["claims"]:
        cid = cl["id"]
        axiom_check_lines.append(f"#print axioms {ns}.claim_{cid}_verdict")
        axiom_check_lines.append(f"#print axioms {ns}.claim_{cid}_findings")

    pass2_out = _run_lean(repo_root, "\n".join(axiom_check_lines) + "\n")
    axioms_map = _parse_axioms(pass2_out)

    claim_results: list[LeanClaimResult] = []
    all_axioms_ok = True
    for cl in spec["claims"]:
        cid = cl["id"]
        v_thm = f"{ns}.claim_{cid}_verdict"
        f_thm = f"{ns}.claim_{cid}_findings"
        if v_thm not in axioms_map or f_thm not in axioms_map:
            raise RuntimeError(f"Missing axiom report for claim {cid!r}; got keys {sorted(axioms_map)}")
        used_axioms = sorted(set(axioms_map[v_thm]) | set(axioms_map[f_thm]))
        disallowed = [a for a in used_axioms if a not in ALLOWED_AXIOMS]
        if disallowed:
            all_axioms_ok = False
            raise RuntimeError(
                f"Disallowed axioms detected for claim {cid!r}: {disallowed} (allowed: {sorted(ALLOWED_AXIOMS)})"
            )
        claim_results.append(
            LeanClaimResult(
                claim_id=cid,
                verdict=parsed_by_id[cid]["verdict"],
                findings=parsed_by_id[cid]["findings"],
                axioms=used_axioms,
                kernel_verified=True,
            )
        )

    return LeanVerificationResult(lean_file=out_lean_path, claims=claim_results, raw_axioms_ok=all_axioms_ok)
