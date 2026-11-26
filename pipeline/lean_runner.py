"""Safe Lean 4 code generation, kernel-checked `decide` proof synthesis, and axiom guard."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
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


def _lean_usage_list(usages: list[dict[str, Any]]) -> str:
    if not usages:
        return "[]"
    items = [f'⟨.{u["source"]}, .{u["dimension"]}, "{escape_lean_str(u["unit"])}", {u["amount"]}⟩' for u in usages]
    return "[" + ", ".join(items) + "]"


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
    if kind == "effectivenessClaim":
        ctrl = "none" if cl["control_node"] is None else f"(some .{cl['control_node']})"
        ledger = "none" if cl["cost_ledger_node"] is None else f"(some .{cl['cost_ledger_node']})"
        mu = _lean_usage_list(cl["method_usage"])
        cu = _lean_usage_list(cl["control_usage"])
        return f".effectivenessClaim .{cl['method_node']} .{cl['evaluation_node']} {ctrl} {ledger} .{cl['cost_tag']} {mu} {cu}"
    return f".conditionalFlow .{cl['target']} {_lean_node_list(cl['declared_sources'])}"


def _render_base_module(spec: dict[str, Any], namespace: str) -> str:
    """Render Lean definitions with separate `Claims` and `Proofs` sub-namespaces so
    claim IDs can never collide with generated helper or theorem names."""
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
        '  | .missingCostAccounting methodNode costTag =>',
        '      "{\\"type\\":\\"missingCostAccounting\\",\\"method\\":" ++ jsonStr (nodeName methodNode) ++',
        '      ",\\"cost_tag\\":" ++ jsonStr (tagName costTag) ++ "}"',
        '  | .trivialCostLedger ledger armNode =>',
        '      "{\\"type\\":\\"trivialCostLedger\\",\\"ledger\\":" ++ jsonStr (nodeName ledger) ++',
        '      ",\\"arm\\":" ++ jsonStr (nodeName armNode) ++ "}"',
        '  | .unusedCostLedger ledger evalNode =>',
        '      "{\\"type\\":\\"unusedCostLedger\\",\\"ledger\\":" ++ jsonStr (nodeName ledger) ++',
        '      ",\\"evaluation\\":" ++ jsonStr (nodeName evalNode) ++ "}"',
        '  | .unaccountedCostSource costSrc ledger costTag =>',
        '      "{\\"type\\":\\"unaccountedCostSource\\",\\"cost_source\\":" ++ jsonStr (nodeName costSrc) ++',
        '      ",\\"ledger\\":" ++ jsonStr (nodeName ledger) ++ ",\\"cost_tag\\":" ++ jsonStr (tagName costTag) ++ "}"',
        '  | .unusedMethodNode methodNode evalNode =>',
        '      "{\\"type\\":\\"unusedMethodNode\\",\\"method\\":" ++ jsonStr (nodeName methodNode) ++',
        '      ",\\"evaluation\\":" ++ jsonStr (nodeName evalNode) ++ "}"',
        '  | .missingMatchedControl methodNode =>',
        '      "{\\"type\\":\\"missingMatchedControl\\",\\"method\\":" ++ jsonStr (nodeName methodNode) ++ "}"',
        '  | .trivialSelfControl methodNode =>',
        '      "{\\"type\\":\\"trivialSelfControl\\",\\"method\\":" ++ jsonStr (nodeName methodNode) ++ "}"',
        '  | .dependentControlArm methodNode ctrl =>',
        '      "{\\"type\\":\\"dependentControlArm\\",\\"method\\":" ++ jsonStr (nodeName methodNode) ++',
        '      ",\\"control\\":" ++ jsonStr (nodeName ctrl) ++ "}"',
        '  | .unusedControlNode ctrl evalNode =>',
        '      "{\\"type\\":\\"unusedControlNode\\",\\"control\\":" ++ jsonStr (nodeName ctrl) ++',
        '      ",\\"evaluation\\":" ++ jsonStr (nodeName evalNode) ++ "}"',
        '  | .unquantifiedBudget methodNode costTag =>',
        '      "{\\"type\\":\\"unquantifiedBudget\\",\\"method\\":" ++ jsonStr (nodeName methodNode) ++',
        '      ",\\"cost_tag\\":" ++ jsonStr (tagName costTag) ++ "}"',
        '  | .unboundUsageSource armNode srcNode costTag =>',
        '      "{\\"type\\":\\"unboundUsageSource\\",\\"arm\\":" ++ jsonStr (nodeName armNode) ++',
        '      ",\\"source\\":" ++ jsonStr (nodeName srcNode) ++ ",\\"cost_tag\\":" ++ jsonStr (tagName costTag) ++ "}"',
        '  | .unmatchedControlBudget methodNode ctrl costTag =>',
        '      "{\\"type\\":\\"unmatchedControlBudget\\",\\"method\\":" ++ jsonStr (nodeName methodNode) ++',
        '      ",\\"control\\":" ++ jsonStr (nodeName ctrl) ++ ",\\"cost_tag\\":" ++ jsonStr (tagName costTag) ++ "}"',
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
    lines += ["", "namespace Claims", ""]

    for cl in spec["claims"]:
        stmt_esc = escape_lean_str(cl["statement"])
        lines += [
            f"def {cl['id']} : FlowClaim Node Tag where",
            f'  statement := "{stmt_esc}"',
            "  graph := graph",
            f"  kind := {_lean_claim_kind(cl)}",
            "",
        ]
    lines += ["end Claims", ""]
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
    if ft == "missingCostAccounting":
        return f"FlowFinding.missingCostAccounting Node.{f['method']} Tag.{f['cost_tag']}"
    if ft == "trivialCostLedger":
        return f"FlowFinding.trivialCostLedger Node.{f['ledger']} Node.{f['arm']}"
    if ft == "unusedCostLedger":
        return f"FlowFinding.unusedCostLedger Node.{f['ledger']} Node.{f['evaluation']}"
    if ft == "unaccountedCostSource":
        return f"FlowFinding.unaccountedCostSource Node.{f['cost_source']} Node.{f['ledger']} Tag.{f['cost_tag']}"
    if ft == "unusedMethodNode":
        return f"FlowFinding.unusedMethodNode Node.{f['method']} Node.{f['evaluation']}"
    if ft == "missingMatchedControl":
        return f"FlowFinding.missingMatchedControl Node.{f['method']}"
    if ft == "trivialSelfControl":
        return f"FlowFinding.trivialSelfControl Node.{f['method']}"
    if ft == "dependentControlArm":
        return f"FlowFinding.dependentControlArm Node.{f['method']} Node.{f['control']}"
    if ft == "unusedControlNode":
        return f"FlowFinding.unusedControlNode Node.{f['control']} Node.{f['evaluation']}"
    if ft == "unquantifiedBudget":
        return f"FlowFinding.unquantifiedBudget Node.{f['method']} Tag.{f['cost_tag']}"
    if ft == "unboundUsageSource":
        return f"FlowFinding.unboundUsageSource Node.{f['arm']} Node.{f['source']} Tag.{f['cost_tag']}"
    if ft == "unmatchedControlBudget":
        return f"FlowFinding.unmatchedControlBudget Node.{f['method']} Node.{f['control']} Tag.{f['cost_tag']}"
    raise ValueError(f"Unknown finding type from Lean output: {ft!r}")


def ensure_operation_flow_built(repo_root: Path) -> None:
    """Ensure `EpistemicLedger.OperationFlow` is compiled and up to date with its source."""
    proc = subprocess.run(
        ["lake", "build", "EpistemicLedger.OperationFlow"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to build EpistemicLedger.OperationFlow (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
        )


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
    joined_lines: list[str] = []
    for raw_line in stdout.split("\n"):
        line = raw_line.rstrip("\r")
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
    0. Ensure `EpistemicLedger.OperationFlow` `.olean` is built & fresh (works on clean clones).
    1. Evaluate `flowVerdict` and `auditFlow` inside `lake env lean`.
    2. Synthesize standalone `decide` proof file in separate `Claims`/`Verdicts`/`Findings`
       sub-namespaces, verify with Lean kernel + axiom whitelist `{propext, Quot.sound}`,
       and atomically publish `out_lean_path` ONLY after all checks succeed.
    """
    ensure_operation_flow_built(repo_root)

    ns = namespace or f"EpistemicLedger.Generated.{spec['auditor']}"
    base = _render_base_module(spec, ns)

    # Pass 1: evaluate verdicts & findings as JSON lines (strict `\n` splitting)
    eval_lines = [base]
    for cl in spec["claims"]:
        cid = cl["id"]
        eval_lines.append(
            f'#eval IO.println ("EPISTEMIC_JSON:" ++ "{{\\"id\\":\\"{cid}\\",\\"verdict\\":" ++ '
            f'jsonStr (verdictName (flowVerdict Claims.{cid})) ++ ",\\"findings\\":" ++ '
            f'findingsToJson (auditFlow Claims.{cid}) ++ "}}")'
        )
    eval_lines.append(f"end {ns}")
    pass1_out = _run_lean(repo_root, "\n".join(eval_lines) + "\n")

    parsed_by_id: dict[str, dict[str, Any]] = {}
    for line in pass1_out.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("EPISTEMIC_JSON:"):
            payload = json.loads(line[len("EPISTEMIC_JSON:") :])
            parsed_by_id[payload["id"]] = payload

    missing_ids = [cl["id"] for cl in spec["claims"] if cl["id"] not in parsed_by_id]
    if missing_ids:
        raise RuntimeError(f"Lean pass 1 did not return results for claim(s): {missing_ids}")

    # Pass 2: synthesize standalone kernel-checked `decide` proof file in disjoint namespaces
    proof_lines = [base, "namespace Verdicts", ""]
    for cl in spec["claims"]:
        cid = cl["id"]
        verdict = parsed_by_id[cid]["verdict"]
        proof_lines.append(f"theorem {cid} : flowVerdict Claims.{cid} = .{verdict} := by decide")
    proof_lines += ["", "end Verdicts", "", "namespace Findings", ""]
    for cl in spec["claims"]:
        cid = cl["id"]
        findings = parsed_by_id[cid]["findings"]
        findings_lean = "[" + ", ".join(_finding_to_lean_expr(f) for f in findings) + "]"
        proof_lines.append(f"theorem {cid} : auditFlow Claims.{cid} = {findings_lean} := by decide")
    proof_lines += ["", "end Findings", "", f"end {ns}"]
    proof_source = "\n".join(proof_lines) + "\n"

    # Verify with Lean kernel + print axioms BEFORE publishing `out_lean_path`
    axiom_check_lines = [proof_source]
    for cl in spec["claims"]:
        cid = cl["id"]
        axiom_check_lines.append(f"#print axioms {ns}.Verdicts.{cid}")
        axiom_check_lines.append(f"#print axioms {ns}.Findings.{cid}")

    pass2_out = _run_lean(repo_root, "\n".join(axiom_check_lines) + "\n")
    axioms_map = _parse_axioms(pass2_out)

    claim_results: list[LeanClaimResult] = []
    for cl in spec["claims"]:
        cid = cl["id"]
        v_thm = f"{ns}.Verdicts.{cid}"
        f_thm = f"{ns}.Findings.{cid}"
        if v_thm not in axioms_map or f_thm not in axioms_map:
            raise RuntimeError(f"Missing axiom report for claim {cid!r}; got keys {sorted(axioms_map)}")
        used_axioms = sorted(set(axioms_map[v_thm]) | set(axioms_map[f_thm]))
        disallowed = [a for a in used_axioms if a not in ALLOWED_AXIOMS]
        if disallowed:
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

    # Exclusive temp file + atomic rename only after Pass 2 + axiom check succeed
    out_lean_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(out_lean_path.parent),
            prefix=f".{out_lean_path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as tf:
            tf.write(proof_source)
            tmp_path = Path(tf.name)
        os.replace(tmp_path, out_lean_path)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()

    return LeanVerificationResult(lean_file=out_lean_path, claims=claim_results, raw_axioms_ok=True)
