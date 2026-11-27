"""Automated unit, integration, and adversarial regression tests for the Epistemic Ledger pipeline."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.audit_cli import main as cli_main
from pipeline.ingest import ingest_document
from pipeline.lean_runner import run_lean_verification
from pipeline.schema import validate_spec

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_DOC = REPO_ROOT / "pipeline" / "examples" / "sample_framework.md"
SPEC_A = REPO_ROOT / "pipeline" / "examples" / "sample_framework_auditor_a.json"
SPEC_B = REPO_ROOT / "pipeline" / "examples" / "sample_framework_auditor_b.json"


class PipelineTests(unittest.TestCase):
    def test_end_to_end_run_sample_framework(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            rc = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(SPEC_A), "--out", str(out)])
            self.assertEqual(rc, 0)

            rep = json.loads((out / "AuditorA_report.json").read_text(encoding="utf-8"))
            self.assertTrue(rep["grounding_and_schema_ok"])
            self.assertTrue(rep["lean_verification"]["axioms_ok"])
            self.assertTrue((out / "AuditorA_Verified.lean").is_file())
            self.assertTrue((out / "AuditorA_report.md").is_file())

            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}
            self.assertEqual(by_id["claimA_clean_measured"]["verdict"], "admissible")
            self.assertEqual(by_id["claimA_clean_measured"]["findings"], [])
            self.assertEqual(by_id["claimB_pretrained_backbone"]["verdict"], "rejected")
            self.assertEqual(
                [f["type"] for f in by_id["claimB_pretrained_backbone"]["findings"]],
                ["authorSuppliedStructure"],
            )
            self.assertEqual(by_id["claimC_depth_in_loss"]["verdict"], "rejected")
            self.assertEqual(
                [f["type"] for f in by_id["claimC_depth_in_loss"]["findings"]],
                ["excludedChannelLeak"],
            )
            self.assertEqual(by_id["claimD_unique_recovery"]["verdict"], "rejected")
            self.assertEqual(
                [f["type"] for f in by_id["claimD_unique_recovery"]["findings"]],
                ["lossyChannelOnPath"],
            )

    def test_p1_path_traversal_auditor_cannot_escape_out_dir(self) -> None:
        """Codex P1-1: malicious `auditor` field like `../../escaped` must never write outside `out`."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / "nested" / "out"
            spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
            spec["auditor"] = "../../escaped"
            bad_spec = base / "evil.json"
            bad_spec.write_text(json.dumps(spec), encoding="utf-8")

            rc = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(bad_spec), "--out", str(out)])
            self.assertEqual(rc, 2)
            self.assertFalse((base / "escaped_report.md").exists())
            self.assertFalse((base / "escaped_report.json").exists())
            self.assertTrue((out / "invalid_auditor_report.json").is_file())
            self.assertFalse((out / "invalid_auditor_Verified.lean").exists())

            # Also block invalid --auditor in `prompt` before any file write
            rc_prompt = cli_main(
                [
                    "prompt",
                    "--doc",
                    str(SAMPLE_DOC),
                    "--auditor",
                    "../pwn",
                    "--out",
                    str(out / "pwn_prompt.txt"),
                ]
            )
            self.assertEqual(rc_prompt, 2)
            self.assertFalse((out / "pwn_prompt.txt").exists())

    def test_p1_undefined_claim_endpoint_rejected(self) -> None:
        """Codex P1-2: claim target or excluded_channel not defined as a source or op output must fail."""
        doc = ingest_document(str(SAMPLE_DOC))
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        spec["nodes"].append("ghostTarget")
        spec["nodes"].append("ghostChannel")
        spec["claims"] = [
            {
                "id": "ghostClaim",
                "statement": "Under Regime A, 3D geometry arises without 3D prediction targets.",
                "quote": "Under Regime A, 3D geometry arises in the learned representation without 3D prediction targets in the training loss.",
                "kind": "emergesWithExclusion",
                "target": "ghostTarget",
                "excluded_channel": "ghostChannel",
                "tag": "geometry3D",
            }
        ]
        errors, _ = validate_spec(spec, doc=doc)
        codes = [e.code for e in errors]
        self.assertEqual(codes.count("undefined_claim_endpoint"), 2)

    def test_p2_claim_id_suffix_collision_safe_and_stale_proof_removed(self) -> None:
        """Codex P2: claim IDs like `c` and `c_verdict` must NOT collide; failed rerun removes stale proof."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / "out"
            spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
            spec["claims"][0]["id"] = "foo"
            spec["claims"][1]["id"] = "foo_verdict"
            sp = base / "collide.json"
            sp.write_text(json.dumps(spec), encoding="utf-8")

            rc_ok = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(sp), "--out", str(out)])
            self.assertEqual(rc_ok, 0)
            self.assertTrue((out / "AuditorA_Verified.lean").is_file())

            # Re-run into same dir with broken quote -> stale proof must be deleted
            spec["sources"][0]["quote"] = "hallucinated quote that breaks rerun"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            rc_fail = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(sp), "--out", str(out)])
            self.assertEqual(rc_fail, 2)
            self.assertFalse((out / "AuditorA_Verified.lean").exists())

    def test_p2_unicode_line_separator_rejected(self) -> None:
        """Codex P2: Unicode line separators (U+2028/U+2029/U+0085) rejected by schema."""
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        spec["ops"][0]["name"] = "bad\u2028name"
        errors, _ = validate_spec(spec, doc=None)
        self.assertTrue(any(e.code == "control_char" for e in errors))

    def test_adversarial_hallucinated_and_short_quotes_rejected(self) -> None:
        doc = ingest_document(str(SAMPLE_DOC))
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        spec["sources"][0]["quote"] = "this sentence does not appear anywhere in the paper at all"
        errors, _ = validate_spec(spec, doc=doc)
        self.assertTrue(any(e.code == "ungrounded_quote" for e in errors))

        spec["sources"][0]["quote"] = "the"
        errors2, _ = validate_spec(spec, doc=doc)
        self.assertTrue(any(e.code == "quote_too_short" for e in errors2))

    def test_adversarial_lean_injection_and_reserved_keyword_rejected(self) -> None:
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        s1 = copy.deepcopy(spec)
        s1["nodes"][0] = "badNode\naxiom evil : False"
        self.assertTrue(any(e.code == "invalid_identifier" for e in validate_spec(s1)[0]))

        s2 = copy.deepcopy(spec)
        s2["nodes"][0] = "theorem"
        self.assertTrue(any(e.code == "reserved_keyword" for e in validate_spec(s2)[0]))

        s3 = copy.deepcopy(spec)
        s3["sneaky_extra"] = 123
        self.assertTrue(any(e.code == "unknown_key" for e in validate_spec(s3)[0]))

    def test_dangling_input_caught_by_lean_through_pipeline(self) -> None:
        doc = ingest_document(str(SAMPLE_DOC))
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        spec["sources"] = [s for s in spec["sources"] if s["node"] != "measuredRgbFrames"]
        self.assertEqual(validate_spec(spec, doc=doc)[0], [])

        with tempfile.TemporaryDirectory() as tmp:
            res = run_lean_verification(spec, repo_root=REPO_ROOT, out_lean_path=Path(tmp) / "Dangling.lean")
            by_id = {c.claim_id: c for c in res.claims}
            self.assertEqual(by_id["claimA_clean_measured"].verdict, "unestablished")
            self.assertTrue(
                any(
                    f["type"] == "danglingInput" and f["missing"] == "measuredRgbFrames"
                    for f in by_id["claimA_clean_measured"].findings
                )
            )

    def test_string_escaping_with_quotes_and_backslashes_in_statement(self) -> None:
        doc = ingest_document(str(SAMPLE_DOC))
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        spec["claims"][0]["statement"] = 'Quoted "3D" claim with \\ backslash'
        spec["ops"][0]["name"] = 'op_"quoted"_\\slash'
        self.assertEqual(validate_spec(spec, doc=doc)[0], [])

        with tempfile.TemporaryDirectory() as tmp:
            res = run_lean_verification(spec, repo_root=REPO_ROOT, out_lean_path=Path(tmp) / "Escaped.lean")
            by_id = {c.claim_id: c for c in res.claims}
            self.assertEqual(by_id["claimA_clean_measured"].verdict, "admissible")
            self.assertEqual(by_id["claimD_unique_recovery"].verdict, "rejected")
            self.assertEqual(by_id["claimD_unique_recovery"].findings[0]["op"], 'op_"quoted"_\\slash')

    def test_codex_r2_p2_failed_lean_rerun_leaves_no_stale_proof_or_report(self) -> None:
        """Codex R2 P2-3: rerunning into an existing out dir with an unavailable Lean repo must clear
        stale `*_Verified.lean` and `*_report.json` (`axioms_ok: true`) rather than leaving them on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / "out"
            rc_ok = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(SPEC_A), "--out", str(out)])
            self.assertEqual(rc_ok, 0)
            self.assertTrue((out / "AuditorA_Verified.lean").is_file())
            self.assertTrue((out / "AuditorA_report.json").is_file())

            bad_repo = base / "broken_repo"
            bad_repo.mkdir()
            with self.assertRaises(RuntimeError):
                cli_main(
                    [
                        "run",
                        "--doc",
                        str(SAMPLE_DOC),
                        "--spec",
                        str(SPEC_A),
                        "--out",
                        str(out),
                        "--repo-root",
                        str(bad_repo),
                    ]
                )
            self.assertFalse((out / "AuditorA_Verified.lean").exists())
            self.assertFalse((out / "AuditorA_report.json").exists())
            self.assertFalse((out / "AuditorA_report.md").exists())

    def test_v23_effectiveness_claim_numeric_budgets_forget_proof_and_arm_independence(self) -> None:
        """Tier 2 (v2.4 — structural only): end-to-end JSON -> Lean 4 kernel tests:
        (1) quantitative `derivedComparison` claim -> `outOfScope` (no numeric verification),
        (2) separate independent accounts with post-hoc metering -> `admissible`,
        (3) `forget .shown` CANNOT erase physically spent human hours -> `unaccountedCostSource` (`rejected`),
        (4) control derived from method -> `dependentControlArm` (`rejected`),
        (5) fake ledger cloned from control -> `unaccountedCostSource` (`rejected`),
        (6) missing control & ledger -> `missingCostAccounting` + `missingMatchedControl` (`unestablished`),
        (7) reviewerStressTest provenance recorded cleanly in report & compare."""
        doc = ingest_document(str(SAMPLE_DOC))
        q = "Under Regime A, 3D geometry arises in the learned representation without 3D prediction targets in the training loss."
        q_num = "We investigate whether 3D spatial structure emerges in neural representations trained without 3D prediction targets across two experimental regimes."
        spec = {
            "schema_version": "epistemic-ledger/v2.4",
            "auditor": "CostAuditorV23",
            "paper_title": "Tier-2 v2.4 Structural Cost & Control Test",
            "nodes": [
                "sharedCluster",
                "accountA",
                "accountB",
                "humanHours",
                "forgottenHours",
                "methodCluster",
                "ctrlCluster",
                "methodForgetHours",
                "clonedCtrl",
                "methodAccA",
                "ctrlAccB",
                "meterCluster",
                "postHocMeter",
                "clonedCtrlLedger",
                "evalUneven",
                "evalEqualSep",
                "evalForgotten",
                "evalDependent",
                "evalNoControl",
                "evalClonedLedger",
            ],
            "tags": ["resourceCost"],
            "sources": [
                {"node": "sharedCluster", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q},
                {"node": "accountA", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q},
                {"node": "accountB", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q},
                {"node": "humanHours", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q},
            ],
            "ops": [
                {"name": "run_m_cluster", "inputs": ["sharedCluster"], "output": "methodCluster", "kind": "transform", "introduces": [], "quote": q},
                {"name": "run_c_cluster", "inputs": ["sharedCluster"], "output": "ctrlCluster", "kind": "transform", "introduces": [], "quote": q},
                {"name": "forget_hours", "inputs": ["humanHours"], "output": "forgottenHours", "kind": "forget", "tag": "resourceCost", "evidence": "shown", "quote": q},
                {"name": "run_m_forgot", "inputs": ["sharedCluster", "forgottenHours"], "output": "methodForgetHours", "kind": "transform", "introduces": [], "quote": q},
                {"name": "clone_ctrl", "inputs": ["methodCluster"], "output": "clonedCtrl", "kind": "transform", "introduces": [], "quote": q},
                {"name": "run_m_accA", "inputs": ["accountA"], "output": "methodAccA", "kind": "transform", "introduces": [], "quote": q},
                {"name": "run_c_accB", "inputs": ["accountB"], "output": "ctrlAccB", "kind": "transform", "introduces": [], "quote": q},
                {"name": "bill_cluster", "inputs": ["sharedCluster"], "output": "meterCluster", "kind": "transform", "introduces": [], "quote": q},
                {"name": "post_hoc_bill", "inputs": ["accountA", "accountB", "methodAccA", "ctrlAccB"], "output": "postHocMeter", "kind": "transform", "introduces": [], "quote": q},
                {"name": "clone_ctrl_ledger", "inputs": ["ctrlCluster"], "output": "clonedCtrlLedger", "kind": "transform", "introduces": [], "quote": q},
                {"name": "e_uneven", "inputs": ["methodCluster", "ctrlCluster", "meterCluster"], "output": "evalUneven", "kind": "transform", "introduces": [], "quote": q},
                {"name": "e_equal", "inputs": ["methodAccA", "ctrlAccB", "postHocMeter"], "output": "evalEqualSep", "kind": "transform", "introduces": [], "quote": q},
                {"name": "e_forgot", "inputs": ["methodForgetHours", "ctrlCluster", "meterCluster"], "output": "evalForgotten", "kind": "transform", "introduces": [], "quote": q},
                {"name": "e_dep", "inputs": ["methodCluster", "clonedCtrl", "meterCluster"], "output": "evalDependent", "kind": "transform", "introduces": [], "quote": q},
                {"name": "e_nocontrol", "inputs": ["methodCluster"], "output": "evalNoControl", "kind": "transform", "introduces": [], "quote": q},
                {"name": "e_cloned_l", "inputs": ["methodCluster", "ctrlCluster", "clonedCtrlLedger"], "output": "evalClonedLedger", "kind": "transform", "introduces": [], "quote": q},
            ],
            "claims": [
                {
                    "id": "derivedRatioOutOfScope",
                    "statement": "Specific numeric ratio 3/2 on same cluster.",
                    "quote": q_num,
                    "provenance": "reviewerStressTest",
                    "nature": "quantitative",
                    "quantitative_kind": "derivedComparison",
                    "kind": "outOfScope",
                },
                {
                    "id": "equalSeparateAccountsPostHoc",
                    "statement": "Two independent arms metered post-hoc from separate accounts.",
                    "quote": q,
                    "provenance": "authorClaimed",
                    "nature": "quantitative",
                    "quantitative_kind": "order",
                    "kind": "effectivenessClaim",
                    "method_node": "methodAccA",
                    "evaluation_node": "evalEqualSep",
                    "control_node": "ctrlAccB",
                    "cost_ledger_node": "postHocMeter",
                    "cost_tag": "resourceCost",
                    "method_measurement_quote": q,
                    "control_measurement_quote": q,
                },
                {
                    "id": "forgetCannotEraseSpentHours",
                    "statement": "Forget .shown cannot erase humanHours spent during run.",
                    "quote": q,
                    "nature": "quantitative",
                    "quantitative_kind": "order",
                    "kind": "effectivenessClaim",
                    "method_node": "methodForgetHours",
                    "evaluation_node": "evalForgotten",
                    "control_node": "ctrlCluster",
                    "cost_ledger_node": "meterCluster",
                    "cost_tag": "resourceCost",
                },
                {
                    "id": "dependentControlRejected",
                    "statement": "Control cloned from method output.",
                    "quote": q,
                    "nature": "quantitative",
                    "quantitative_kind": "order",
                    "kind": "effectivenessClaim",
                    "method_node": "methodCluster",
                    "evaluation_node": "evalDependent",
                    "control_node": "clonedCtrl",
                    "cost_ledger_node": "meterCluster",
                    "cost_tag": "resourceCost",
                },
                {
                    "id": "clonedControlLedgerRejected",
                    "statement": "Fake ledger cloned solely from control output.",
                    "quote": q,
                    "nature": "quantitative",
                    "quantitative_kind": "order",
                    "kind": "effectivenessClaim",
                    "method_node": "methodCluster",
                    "evaluation_node": "evalClonedLedger",
                    "control_node": "ctrlCluster",
                    "cost_ledger_node": "clonedCtrlLedger",
                    "cost_tag": "resourceCost",
                },
                {
                    "id": "noControlNoLedgerUnestablished",
                    "statement": "Method evaluated with no control arm and no cost ledger.",
                    "quote": q,
                    "nature": "quantitative",
                    "quantitative_kind": "order",
                    "kind": "effectivenessClaim",
                    "method_node": "methodCluster",
                    "evaluation_node": "evalNoControl",
                    "control_node": None,
                    "cost_ledger_node": None,
                    "cost_tag": "resourceCost",
                },
            ],
        }
        self.assertEqual(validate_spec(spec, doc=doc)[0], [])

        with tempfile.TemporaryDirectory() as tmp:
            sp = Path(tmp) / "v24.json"
            out = Path(tmp) / "out"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            rc = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(sp), "--out", str(out)])
            self.assertEqual(rc, 0)
            rep = json.loads((out / "CostAuditorV23_report.json").read_text(encoding="utf-8"))
            md = (out / "CostAuditorV23_report.md").read_text(encoding="utf-8")
            self.assertIn("`reviewerStressTest`", md)
            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}

            self.assertEqual(by_id["derivedRatioOutOfScope"]["verdict"], "outOfScope")
            self.assertEqual([f["type"] for f in by_id["derivedRatioOutOfScope"]["findings"]], ["claimOutOfScope"])
            self.assertEqual(by_id["equalSeparateAccountsPostHoc"]["verdict"], "admissible")
            self.assertEqual(by_id["equalSeparateAccountsPostHoc"]["findings"], [])
            self.assertEqual(by_id["forgetCannotEraseSpentHours"]["verdict"], "rejected")
            self.assertIn("unaccountedCostSource", [f["type"] for f in by_id["forgetCannotEraseSpentHours"]["findings"]])
            self.assertEqual(by_id["dependentControlRejected"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["dependentControlRejected"]["findings"]], ["dependentControlArm"])
            self.assertEqual(by_id["clonedControlLedgerRejected"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["clonedControlLedgerRejected"]["findings"]], ["unaccountedCostSource"])
            self.assertEqual(by_id["noControlNoLedgerUnestablished"]["verdict"], "unestablished")
            self.assertEqual(
                [f["type"] for f in by_id["noControlNoLedgerUnestablished"]["findings"]],
                ["missingMatchedControl"],
            )

    def test_numeric_boundary_grounding_and_explicit_out_of_scope_notice(self) -> None:
        """Clean v2.4 scope boundary (user #27429 + Claude #27430 Part A):
        1. `schema.py` contains NO numeric parser on the verdict path.
        2. `nature: "quantitative"` enforces `quantitative_kind` in `{order, threshold, specificValue, derivedComparison}`:
           - `order` / `threshold` verify structure only (independent arms, shared evaluation, forget-proof ledger).
           - `specificValue` / `derivedComparison` return `outOfScope` cleanly.
        3. Legacy `method_usage`, `control_usage`, and `reconciliations` fields on `effectivenessClaim` are
           recognized, ignored during Lean verification, and explicitly reported under `## Out of Scope`,
           while unknown keys still fail with `unknown_key`.
        4. `compare` propagates `out_of_scope` into `comparison.json` & `comparison.md`.
        """
        import pipeline.schema as schema_mod

        self.assertFalse(hasattr(schema_mod, "extract_quote_integers"))
        self.assertFalse(hasattr(schema_mod, "extract_doc_bounded_quote_integers"))

        doc_text = (
            "Compute Comparison Study.\n"
            "1,500 GPU-hours were charged to the method.\n"
            "The control used 500 GPU-hours.\n"
        )
        q_hdr = "Compute Comparison Study."
        q_m1500 = "1,500 GPU-hours were charged to the method."
        q_c500 = "The control used 500 GPU-hours."

        def make_spec(nature: str = "quantitative", qkind: str | None = "order") -> dict:
            claim: dict = {
                "id": "budgetCheck",
                "statement": "Method and control are structurally compared at evaluation.",
                "quote": q_hdr,
                "provenance": "authorClaimed",
                "nature": nature,
                "kind": "effectivenessClaim",
                "method_node": "methodRun",
                "evaluation_node": "evalNode",
                "control_node": "controlRun",
                "cost_ledger_node": "ledger",
                "cost_tag": "resourceCost",
                "method_measurement_quote": q_m1500,
                "control_measurement_quote": q_c500,
            }
            if qkind is not None:
                claim["quantitative_kind"] = qkind
            return {
                "schema_version": "epistemic-ledger/v2.4",
                "auditor": "ScopeAuditor",
                "paper_title": "Scope Boundary Check",
                "nodes": ["accountA", "accountB", "methodRun", "controlRun", "ledger", "evalNode"],
                "tags": ["resourceCost"],
                "sources": [
                    {"node": "accountA", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_m1500},
                    {"node": "accountB", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_c500},
                ],
                "ops": [
                    {"name": "run_m", "inputs": ["accountA"], "output": "methodRun", "kind": "transform", "introduces": [], "quote": q_m1500},
                    {"name": "run_c", "inputs": ["accountB"], "output": "controlRun", "kind": "transform", "introduces": [], "quote": q_c500},
                    {"name": "meter", "inputs": ["accountA", "accountB"], "output": "ledger", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "eval", "inputs": ["methodRun", "controlRun", "ledger"], "output": "evalNode", "kind": "transform", "introduces": [], "quote": q_hdr},
                ],
                "claims": [claim],
            }

        with tempfile.TemporaryDirectory() as tmp:
            doc_path = Path(tmp) / "study.md"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            # 1. v2.4 nature/kind invariants (Codex #27436 + Claude #27437):
            #    - missing `nature` on v2.4 fails (`missing_nature`), while legacy v2.3 without `nature` still passes
            #    - `quantitative` without `quantitative_kind` fails; `qualitative` with `quantitative_kind` fails
            #    - v2.4 `quantitative/order` with `kind: conditionalFlow` fails (`invalid_quantitative_claim_kind`)
            #    - v2.4 `quantitative/derivedComparison` with `kind: effectivenessClaim` fails (`invalid_quantitative_claim_kind`)
            s_no_nat = make_spec("quantitative", None)
            del s_no_nat["claims"][0]["nature"]
            self.assertTrue(any(e.code == "missing_nature" for e in validate_spec(s_no_nat, doc=doc)[0]))
            s_v23_legacy = copy.deepcopy(s_no_nat)
            s_v23_legacy["schema_version"] = "epistemic-ledger/v2.3"
            self.assertEqual(validate_spec(s_v23_legacy, doc=doc)[0], [])

            e_miss, _ = validate_spec(make_spec("quantitative", None), doc=doc)
            self.assertTrue(any(e.code == "missing_quantitative_kind" for e in e_miss))
            e_unexp, _ = validate_spec(make_spec("qualitative", "order"), doc=doc)
            self.assertTrue(any(e.code == "unexpected_quantitative_kind" for e in e_unexp))

            s_bypass_cond = make_spec("quantitative", "order")
            s_bypass_cond["claims"][0] = {
                "id": "bypassOrderAsCond",
                "statement": "Attempt to bypass control check using conditionalFlow.",
                "quote": q_hdr,
                "nature": "quantitative",
                "quantitative_kind": "order",
                "kind": "conditionalFlow",
                "target": "evalNode",
                "declared_sources": ["accountA", "accountB"],
            }
            self.assertTrue(
                any(e.code == "invalid_quantitative_claim_kind" for e in validate_spec(s_bypass_cond, doc=doc)[0])
            )
            self.assertTrue(
                any(
                    e.code == "invalid_quantitative_claim_kind"
                    for e in validate_spec(make_spec("quantitative", "derivedComparison"), doc=doc)[0]
                )
            )

            # 2. Structural `order` claim passes without reading numbers and renders `## Out of Scope`
            #    and clarifies "structural comparison only; numbers & necessity unchecked"
            sp = Path(tmp) / "valid_order.json"
            sp.write_text(json.dumps(make_spec("quantitative", "order")), encoding="utf-8")
            out = Path(tmp) / "out"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp), "--out", str(out)]), 0)
            rep = json.loads((out / "ScopeAuditor_report.json").read_text(encoding="utf-8"))
            md = (out / "ScopeAuditor_report.md").read_text(encoding="utf-8")
            self.assertEqual(rep["lean_verification"]["claims"][0]["verdict"], "admissible")
            self.assertEqual(rep["lean_verification"]["claims"][0]["nature"], "quantitative")
            self.assertEqual(rep["lean_verification"]["claims"][0]["quantitative_kind"], "order")
            self.assertIn("structural comparison only; numbers & necessity unchecked", md)
            self.assertTrue(any("out of scope" in s.lower() and "without reading or comparing numbers" in s.lower() for s in rep["out_of_scope"]))
            self.assertIn("## Out of Scope", md)

            # 3. `specificValue` and `derivedComparison` with `kind: outOfScope` return `outOfScope`
            for oos_qkind in ("specificValue", "derivedComparison"):
                s_oos = make_spec("quantitative", oos_qkind)
                s_oos["claims"][0] = {
                    "id": "budgetCheck",
                    "statement": f"Quantitative {oos_qkind} claim.",
                    "quote": q_hdr,
                    "nature": "quantitative",
                    "quantitative_kind": oos_qkind,
                    "kind": "outOfScope",
                }
                sp_oos = Path(tmp) / f"{oos_qkind}.json"
                sp_oos.write_text(json.dumps(s_oos), encoding="utf-8")
                out_oos = Path(tmp) / f"out_{oos_qkind}"
                self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_oos), "--out", str(out_oos)]), 0)
                rep_oos = json.loads((out_oos / "ScopeAuditor_report.json").read_text(encoding="utf-8"))
                self.assertEqual(rep_oos["lean_verification"]["claims"][0]["verdict"], "outOfScope")
                self.assertEqual([f["type"] for f in rep_oos["lean_verification"]["claims"][0]["findings"]], ["claimOutOfScope"])

            # 4. Failed grounding report still renders `## Out of Scope`
            s_fail = make_spec("quantitative", "order")
            s_fail["claims"][0]["method_measurement_quote"] = "Hallucinated measurement quote not in document."
            sp_fail = Path(tmp) / "fail_quote.json"
            sp_fail.write_text(json.dumps(s_fail), encoding="utf-8")
            out_fail = Path(tmp) / "out_fail"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_fail), "--out", str(out_fail)]), 2)
            md_fail = (out_fail / "ScopeAuditor_report.md").read_text(encoding="utf-8")
            self.assertIn("## Out of Scope", md_fail)

            # 5. Legacy out-of-scope numeric/accounting keys (`method_usage`, `control_usage`, `reconciliations`)
            # are accepted, ignored during Lean verification, and reported under `## Out of Scope`; unknown keys still fail!
            s_legacy = make_spec("quantitative", "order")
            s_legacy["claims"][0]["method_usage"] = [
                {"source": "accountA", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 999999, "quote": "ignored"}
            ]
            s_legacy["claims"][0]["control_usage"] = [
                {"source": "accountB", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1, "quote": "ignored"}
            ]
            s_legacy["claims"][0]["reconciliations"] = [{"arm": "methodRun", "reconciled_total": 1500}]
            sp_legacy = Path(tmp) / "legacy.json"
            sp_legacy.write_text(json.dumps(s_legacy), encoding="utf-8")
            out_legacy = Path(tmp) / "out_legacy"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_legacy), "--out", str(out_legacy)]), 0)
            rep_legacy = json.loads((out_legacy / "ScopeAuditor_report.json").read_text(encoding="utf-8"))
            md_legacy = (out_legacy / "ScopeAuditor_report.md").read_text(encoding="utf-8")
            self.assertEqual(rep_legacy["lean_verification"]["claims"][0]["verdict"], "admissible")
            self.assertTrue(
                any(
                    "Ignored out-of-scope numeric/accounting fields" in s
                    and "reconciliations" in s
                    and "method_usage" in s
                    for s in rep_legacy["out_of_scope"]
                )
            )
            self.assertIn("Ignored out-of-scope numeric/accounting fields", md_legacy)

            s_bogus = copy.deepcopy(s_legacy)
            s_bogus["claims"][0]["bogus_extra"] = 123
            e_bogus, _ = validate_spec(s_bogus, doc=doc)
            self.assertTrue(any(e.code == "unknown_key" for e in e_bogus))

    def test_four_state_verdicts_admissible_unestablished_rejected_out_of_scope(self) -> None:
        """4-state `EpistemicVerdict` end-to-end test:
        - `admissible` (rendered as `admissible (consistent within declared slice)` in Markdown)
        - `unestablished` (data/design stops at map edge: e.g. missing control + missing cost ledger)
        - `rejected` (direct structural contradiction: e.g. excludedChannelLeak)
        - `outOfScope` (explicit normative/legal-policy claim with required non-empty `reason`)
        """
        doc = ingest_document(str(SAMPLE_DOC))
        q_clean = "Under Regime A, 3D geometry arises in the learned representation without 3D prediction targets in the training loss."
        q_leak = "Under Regime C, 3D geometry emerges without 3D prediction targets in the training loss."
        q_header = "We investigate whether 3D spatial structure emerges in neural representations trained without 3D prediction targets across two experimental regimes."

        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        spec["auditor"] = "FourStateA"
        spec["claims"] = [
            copy.deepcopy(spec["claims"][0]),  # admissible
            {
                "id": "claimUnestablishedGap",
                "statement": "Regime A is more cost-effective without matched control or cost ledger.",
                "quote": q_header,
                "provenance": "reviewerStressTest",
                "kind": "effectivenessClaim",
                "method_node": "modelRegimeA",
                "evaluation_node": "modelRegimeA",
                "control_node": None,
                "cost_ledger_node": None,
                "cost_tag": "geometry3D",
                "method_usage": [],
                "control_usage": [],
            },
            copy.deepcopy(spec["claims"][2]),  # rejected (excludedChannelLeak)
            {
                "id": "claimNormativeOutOfScope",
                "statement": "Whether releasing 3D models is ethically justified outweighs privacy risk.",
                "quote": q_leak,
                "provenance": "authorClaimed",
                "kind": "outOfScope",
                "reason": (
                    "Normative policy/ethics balancing is outside structural operation-flow verification: "
                    "even when all parties agree on the exact causal graph and empirical facts, weighing "
                    "competing legal, moral, or institutional values requires human judgment rather than "
                    "formal graph auditing."
                ),
            },
        ]
        # Anchor outOfScope to a distinct verbatim quote from sample_framework.md
        spec["claims"][3]["quote"] = "Spatial Emergence Framework (Synthetic Benchmark Document)"

        self.assertEqual(validate_spec(spec, doc=doc)[0], [])

        # Missing or empty `reason` on `outOfScope` MUST fail schema validation
        bad_missing = copy.deepcopy(spec)
        del bad_missing["claims"][3]["reason"]
        self.assertTrue(any(e.code == "missing_key" for e in validate_spec(bad_missing, doc=doc)[0]))

        bad_empty = copy.deepcopy(spec)
        bad_empty["claims"][3]["reason"] = "   "
        self.assertTrue(any(e.code == "invalid_string" for e in validate_spec(bad_empty, doc=doc)[0]))

        with tempfile.TemporaryDirectory() as tmp:
            sp_a = Path(tmp) / "four_a.json"
            sp_b = Path(tmp) / "four_b.json"
            sp_a.write_text(json.dumps(spec), encoding="utf-8")
            spec_b = copy.deepcopy(spec)
            spec_b["auditor"] = "FourStateB"
            sp_b.write_text(json.dumps(spec_b), encoding="utf-8")

            out_run = Path(tmp) / "run_out"
            rc = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(sp_a), "--out", str(out_run)])
            self.assertEqual(rc, 0)

            rep = json.loads((out_run / "FourStateA_report.json").read_text(encoding="utf-8"))
            md = (out_run / "FourStateA_report.md").read_text(encoding="utf-8")
            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}

            self.assertEqual(by_id["claimA_clean_measured"]["verdict"], "admissible")
            self.assertEqual(by_id["claimUnestablishedGap"]["verdict"], "unestablished")
            self.assertEqual(by_id["claimC_depth_in_loss"]["verdict"], "rejected")
            self.assertEqual(by_id["claimNormativeOutOfScope"]["verdict"], "outOfScope")
            self.assertEqual(
                by_id["claimNormativeOutOfScope"]["findings"],
                [
                    {
                        "type": "claimOutOfScope",
                        "reason": (
                            "Normative policy/ethics balancing is outside structural operation-flow verification: "
                            "even when all parties agree on the exact causal graph and empirical facts, weighing "
                            "competing legal, moral, or institutional values requires human judgment rather than "
                            "formal graph auditing."
                        ),
                    }
                ],
            )
            self.assertEqual(by_id["claimA_clean_measured"]["display_state"], "noStructuralAlarm")
            self.assertIn("**no structural alarm**", md)
            self.assertIn("UNESTABLISHED (data/design stops at map edge)", md)
            self.assertIn("OUT OF SCOPE", md)
            self.assertIn("**[Out of Scope]** Normative policy/ethics balancing", md)
            self.assertIn("Explicitly out-of-scope claim(s) (claimNormativeOutOfScope)", md)

    def test_codex_notShown_sole_path_and_lossy_side_branch(self) -> None:
        """Regression tests for Codex `#27358`:
        1. Sole path through `.forget tag .notShown` -> `rejected` on emergence (Rule 2),
           while adding an un-attempted bypass -> `rejected` with `smuggledStructure`.
        2. `uniqueRecovery` with `.lossy` ONLY on an unrelated noise branch -> `admissible`;
           missing upstream `SourceNode` access (`unaccessedTargetStructure`) -> `unestablished`.
        """
        doc = ingest_document(str(SAMPLE_DOC))
        q_a_with_dot = "Under Regime A, 3D geometry arises in the learned representation without 3D prediction targets in the training loss."
        q_a_no_dot = q_a_with_dot.rstrip(".")
        q_b = "Under Regime B, 3D geometry emerges purely from 2D relational learning without 3D prediction targets."
        q_d = "The encoder uniquely recovers the true underlying 3D world state from a single monocular photograph."

        spec_a = {
            "schema_version": "epistemic-ledger/v2.3",
            "auditor": "SpanA",
            "paper_title": "Codex Regression",
            "nodes": ["srcTag", "bypassTag", "noise", "forgotten", "roundedNoise", "pairOut", "targetSole", "targetBypass"],
            "tags": ["geometry3D"],
            "sources": [
                {"node": "srcTag", "origin": "setByExperimenter", "carries": ["geometry3D"], "quote": q_a_with_dot},
                {"node": "bypassTag", "origin": "setByExperimenter", "carries": ["geometry3D"], "quote": q_b},
                {"node": "noise", "origin": "measured", "carries": [], "quote": q_d},
            ],
            "ops": [
                {"name": "unverified_forget", "inputs": ["srcTag"], "output": "forgotten", "kind": "forget", "tag": "geometry3D", "evidence": "notShown", "quote": q_a_with_dot},
                {"name": "read_sole", "inputs": ["forgotten"], "output": "targetSole", "kind": "transform", "introduces": [], "quote": q_a_with_dot},
                {"name": "read_bypass", "inputs": ["forgotten", "bypassTag"], "output": "targetBypass", "kind": "transform", "introduces": [], "quote": q_b},
                {"name": "round_noise", "inputs": ["noise"], "output": "roundedNoise", "kind": "lossy", "introduces": [], "quote": q_d},
                {"name": "make_pair", "inputs": ["srcTag", "roundedNoise"], "output": "pairOut", "kind": "transform", "introduces": [], "quote": q_d},
            ],
            "claims": [
                {
                    "id": "soleNotShown",
                    "statement": "Sole path passes through .notShown forget.",
                    "quote": q_a_no_dot,
                    "kind": "emergesWithout",
                    "target": "targetSole",
                    "tag": "geometry3D",
                },
                {
                    "id": "notShownPlusBypass",
                    "statement": "Unverified forget plus confirmed bypass.",
                    "quote": q_b,
                    "kind": "emergesWithout",
                    "target": "targetBypass",
                    "tag": "geometry3D",
                },
                {
                    "id": "losslessSignalLossyNoise",
                    "statement": "Signal preserved while unrelated noise branch is lossy.",
                    "quote": q_d,
                    "kind": "uniqueRecovery",
                    "target": "pairOut",
                    "tag": "geometry3D",
                },
                {
                    "id": "unaccessedRecovery",
                    "statement": "No SourceNode carrying geometry3D reaches roundedNoise.",
                    "quote": "Spatial Emergence Framework (Synthetic Benchmark Document)",
                    "kind": "uniqueRecovery",
                    "target": "roundedNoise",
                    "tag": "geometry3D",
                },
            ],
        }
        self.assertEqual(validate_spec(spec_a, doc=doc)[0], [])

        with tempfile.TemporaryDirectory() as tmp:
            pa = Path(tmp) / "a.json"
            pa.write_text(json.dumps(spec_a), encoding="utf-8")
            out = Path(tmp) / "run"
            rc = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(pa), "--out", str(out)])
            self.assertEqual(rc, 0)

            rep_a = json.loads((out / "SpanA_report.json").read_text(encoding="utf-8"))
            by_id = {c["id"]: c for c in rep_a["lean_verification"]["claims"]}
            self.assertEqual(by_id["soleNotShown"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["soleNotShown"]["findings"]], ["failedForgetOnPath"])
            self.assertEqual(by_id["notShownPlusBypass"]["verdict"], "rejected")
            self.assertIn("smuggledStructure", [f["type"] for f in by_id["notShownPlusBypass"]["findings"]])
            self.assertEqual(by_id["losslessSignalLossyNoise"]["verdict"], "admissible")
            self.assertEqual(by_id["unaccessedRecovery"]["verdict"], "unestablished")
            self.assertEqual([f["type"] for f in by_id["unaccessedRecovery"]["findings"]], ["unaccessedTargetStructure"])

    def test_codex_27370_unique_recovery_and_rule3_theorem_application(self) -> None:
        """Regression tests for Codex `#27370` + Rule 3 (`theoremApplication`) end-to-end:
        1. `uniqueRecovery`:
           - `(x, round(x))` with direct lossless path -> `admissible`,
           - sole access through `.forget x .notShown` -> `unestablished` (`failedForgetOnPath`).
        2. Rule 3 (`theoremApplication`):
           - `.knownFalse` hypothesis -> `rejected` (even if listed in `declared_bets`),
           - undeclared `.bet` -> `unestablished` (`undeclaredHypothesisBet`),
           - `.discharged` + declared `.bet` -> `admissible`,
           - empty `hypotheses` or duplicate hypothesis tag -> schema error.
        """
        doc_text = (
            "The first cohort improved. Both cohorts were measured. The second cohort declined.\n"
            "Theorem 1 assumes injective rendering and population minimizers, whereas real cameras are lossy.\n"
            "Assuming GRH, the bound holds for all n >= N0.\n"
        )
        q_m = "The first cohort improved. Both cohorts were measured. The second cohort declined."
        q_l = "The first cohort improved. Both cohorts were measured."
        q_r = "Both cohorts were measured. The second cohort declined."
        q_jepa = "Theorem 1 assumes injective rendering and population minimizers, whereas real cameras are lossy."
        q_grh = "Assuming GRH, the bound holds for all n >= N0."

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            doc_path = base / "doc.txt"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            # uniqueRecovery `(x, round(x))` + `.notShown` access + Rule 3 (`theoremApplication`)
            spec_r3 = {
                "schema_version": "epistemic-ledger/v2.3",
                "auditor": "Rule3Auditor",
                "paper_title": "UniqueRecovery & Rule 3 Test",
                "nodes": ["rawX", "roundedX", "pairRawRounded", "forgotX", "readForgot", "theoremOut"],
                "tags": ["signalX", "injectiveRendering", "populationMinimizers", "grh"],
                "sources": [
                    {"node": "rawX", "origin": "measured", "carries": ["signalX"], "quote": q_m},
                ],
                "ops": [
                    {"name": "round_x", "inputs": ["rawX"], "output": "roundedX", "kind": "lossy", "introduces": [], "quote": q_m},
                    {"name": "make_pair", "inputs": ["rawX", "roundedX"], "output": "pairRawRounded", "kind": "transform", "introduces": [], "quote": q_m},
                    {"name": "forget_x_unverified", "inputs": ["rawX"], "output": "forgotX", "kind": "forget", "tag": "signalX", "evidence": "notShown", "quote": q_m},
                    {"name": "read_forgot", "inputs": ["forgotX"], "output": "readForgot", "kind": "transform", "introduces": [], "quote": q_m},
                    {"name": "apply_thm", "inputs": ["rawX"], "output": "theoremOut", "kind": "transform", "introduces": [], "quote": q_jepa},
                ],
                "claims": [
                    {
                        "id": "pairRawAndRounded",
                        "statement": "Pair (x, round(x)) preserves x via lossless branch.",
                        "quote": q_l,
                        "kind": "uniqueRecovery",
                        "target": "pairRawRounded",
                        "tag": "signalX",
                    },
                    {
                        "id": "recoveryViaNotShown",
                        "statement": "Sole access passes through unverified forget.",
                        "quote": q_r,
                        "kind": "uniqueRecovery",
                        "target": "readForgot",
                        "tag": "signalX",
                    },
                    {
                        "id": "jepaKnownFalse",
                        "statement": "Theorem 1 applies to real lossy cameras.",
                        "quote": q_jepa,
                        "kind": "theoremApplication",
                        "target": "theoremOut",
                        "hypotheses": [
                            {"tag": "injectiveRendering", "status": "knownFalse", "quote": q_jepa},
                            {"tag": "populationMinimizers", "status": "bet", "quote": q_jepa},
                        ],
                        "declared_bets": ["injectiveRendering"],  # knownFalse cannot be excused!
                    },
                    {
                        "id": "mathUndeclaredBet",
                        "statement": "Bound holds unconditionally (silently omits GRH).",
                        "quote": q_grh,
                        "kind": "theoremApplication",
                        "target": "theoremOut",
                        "hypotheses": [
                            {"tag": "grh", "status": "bet", "quote": q_grh},
                        ],
                        "declared_bets": [],
                    },
                    {
                        "id": "mathDeclaredBet",
                        "statement": "Assuming GRH, the bound holds.",
                        "quote": q_m,
                        "kind": "theoremApplication",
                        "target": "theoremOut",
                        "hypotheses": [
                            {"tag": "grh", "status": "bet", "quote": q_grh},
                            {"tag": "signalX", "status": "discharged", "quote": q_m},
                        ],
                        "declared_bets": ["grh"],
                    },
                ],
            }
            self.assertEqual(validate_spec(spec_r3, doc=doc)[0], [])

            # Schema guards: empty hypotheses and duplicate hypothesis tag must fail
            bad_empty = copy.deepcopy(spec_r3)
            bad_empty["claims"][3]["hypotheses"] = []
            self.assertTrue(any(e.code == "empty_list" for e in validate_spec(bad_empty, doc=doc)[0]))

            bad_dup = copy.deepcopy(spec_r3)
            bad_dup["claims"][3]["hypotheses"].append({"tag": "grh", "status": "discharged", "quote": q_grh})
            self.assertTrue(any(e.code == "duplicate_hypothesis" for e in validate_spec(bad_dup, doc=doc)[0]))

            sp_r3 = base / "r3.json"
            sp_r3.write_text(json.dumps(spec_r3), encoding="utf-8")
            out_r3 = base / "out_r3"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_r3), "--out", str(out_r3)]), 0)
            rep_r3 = json.loads((out_r3 / "Rule3Auditor_report.json").read_text(encoding="utf-8"))
            by_id = {c["id"]: c for c in rep_r3["lean_verification"]["claims"]}

            self.assertEqual(by_id["pairRawAndRounded"]["verdict"], "admissible")
            self.assertEqual(by_id["recoveryViaNotShown"]["verdict"], "unestablished")
            self.assertEqual([f["type"] for f in by_id["recoveryViaNotShown"]["findings"]], ["failedForgetOnPath"])
            self.assertEqual(by_id["jepaKnownFalse"]["verdict"], "rejected")
            self.assertEqual(
                [f["type"] for f in by_id["jepaKnownFalse"]["findings"]],
                ["hypothesisKnownFalse", "undeclaredHypothesisBet"],
            )
            self.assertEqual(by_id["mathUndeclaredBet"]["verdict"], "unestablished")
            self.assertEqual([f["type"] for f in by_id["mathUndeclaredBet"]["findings"]], ["undeclaredHypothesisBet"])
            self.assertEqual(by_id["mathDeclaredBet"]["verdict"], "admissible")
            self.assertEqual(by_id["mathDeclaredBet"]["findings"], [])

    def test_codex_27373_orphan_declared_bet_and_parallel_lossy_qr_pair(self) -> None:
        """Regression tests for Codex `#27373`:
        1. `declared_bets` tag missing from `hypotheses` fails schema validation (`orphan_declared_bet`)
           AND is also rejected from `admissible` (`unestablished`) if called directly in Lean.
        2. Parallel lossy branches `(q = n div 2, r = n mod 2)` with no single lossy bottleneck ->
           `unestablished` (`parallelLossyBranches`), NOT falsely `rejected`; whereas a single lossy
           bottleneck `q = n div 2` alone -> `rejected` (`lossyChannelOnPath`).
        """
        doc_text = (
            "Let n be in {0,1,2,3}, q = n div 2, r = n mod 2, and pair = (q, r) which recovers n = 2q + r.\n"
            "Rolle theorem requires equal endpoint values f(0) = f(1) on [0, 1].\n"
        )
        q_qr = "Let n be in {0,1,2,3}, q = n div 2, r = n mod 2, and pair = (q, r) which recovers n = 2q + r."
        q_rolle = "Rolle theorem requires equal endpoint values f(0) = f(1) on [0, 1]."

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            doc_path = base / "qr.txt"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            spec = {
                "schema_version": "epistemic-ledger/v2.3",
                "auditor": "Codex27373",
                "paper_title": "Codex 27373 Parallel Lossy & Orphan Bet",
                "nodes": ["nVal", "qDiv2", "rMod2", "qrPair"],
                "tags": ["inputN", "equalEnds", "continuous"],
                "sources": [
                    {"node": "nVal", "origin": "measured", "carries": ["inputN"], "quote": q_qr},
                ],
                "ops": [
                    {"name": "div2", "inputs": ["nVal"], "output": "qDiv2", "kind": "lossy", "loses": ["inputN"], "introduces": [], "quote": q_qr},
                    {"name": "mod2", "inputs": ["nVal"], "output": "rMod2", "kind": "lossy", "loses": ["inputN"], "introduces": [], "quote": q_qr},
                    {"name": "pair_qr", "inputs": ["qDiv2", "rMod2"], "output": "qrPair", "kind": "transform", "introduces": [], "quote": q_qr},
                ],
                "claims": [
                    {
                        "id": "recoverFromQRPair",
                        "statement": "Recover n from parallel lossy projections (n div 2, n mod 2).",
                        "quote": q_qr,
                        "kind": "uniqueRecovery",
                        "target": "qrPair",
                        "tag": "inputN",
                    },
                    {
                        "id": "recoverFromQOnly",
                        "statement": "Recover n from q = n div 2 alone (single lossy bottleneck).",
                        "quote": q_rolle,
                        "kind": "uniqueRecovery",
                        "target": "qDiv2",
                        "tag": "inputN",
                    },
                ],
            }
            self.assertEqual(validate_spec(spec, doc=doc)[0], [])

            # Orphan declared_bet MUST fail schema validation
            bad_orphan = copy.deepcopy(spec)
            bad_orphan["claims"].append(
                {
                    "id": "orphanBet",
                    "statement": "Rolle theorem with equalEnds only in declared_bets, omitted from hypotheses.",
                    "quote": q_rolle,
                    "kind": "theoremApplication",
                    "target": "qrPair",
                    "hypotheses": [{"tag": "continuous", "status": "discharged", "quote": q_rolle}],
                    "declared_bets": ["equalEnds"],
                }
            )
            errs, _ = validate_spec(bad_orphan, doc=doc)
            self.assertTrue(any(e.code == "orphan_declared_bet" for e in errs))

            sp = base / "qr.json"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            out = base / "out"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp), "--out", str(out)]), 0)
            rep = json.loads((out / "Codex27373_report.json").read_text(encoding="utf-8"))
            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}

            self.assertEqual(by_id["recoverFromQRPair"]["verdict"], "unestablished")
            self.assertEqual([f["type"] for f in by_id["recoverFromQRPair"]["findings"]], ["parallelLossyBranches"])
            self.assertEqual(by_id["recoverFromQOnly"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["recoverFromQOnly"]["findings"]], ["lossyChannelOnPath"])

    def test_codex_27376_tag_specific_vs_untargeted_lossy_projection(self) -> None:
        """Regression test for Codex `#27376`:
        Projection `observed = signal` on two independent bits `(signal, noise)`:
        - With `loses: ["noise"]`: `signalRecovery` -> `admissible`, `noiseRecovery` -> `rejected` (`lossyChannelOnPath`).
        - With untagged `kind: "lossy"` (no `loses`): BOTH `signalRecovery` and `noiseRecovery` -> `unestablished`
          (`untargetedLossyChannel`) instead of falsely rejecting `signalRecovery`.
        """
        doc_text = "Given two independent bits (signal, noise), the projection stores observed = signal and discards noise.\n"
        q = doc_text.strip()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            doc_path = base / "proj.txt"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            spec = {
                "schema_version": "epistemic-ledger/v2.3",
                "auditor": "ProjAuditor",
                "paper_title": "Codex 27376 Projection Test",
                "nodes": ["jointState", "obsTagged", "obsUntagged"],
                "tags": ["signal", "noise"],
                "sources": [
                    {"node": "jointState", "origin": "measured", "carries": ["signal", "noise"], "quote": q},
                ],
                "ops": [
                    {"name": "project_first_tagged", "inputs": ["jointState"], "output": "obsTagged", "kind": "lossy", "loses": ["noise"], "introduces": [], "quote": q},
                    {"name": "project_first_untagged", "inputs": ["jointState"], "output": "obsUntagged", "kind": "lossy", "introduces": [], "quote": q},
                ],
                "claims": [
                    {"id": "taggedSignal", "statement": "Recover signal from tagged projection.", "quote": q, "kind": "uniqueRecovery", "target": "obsTagged", "tag": "signal"},
                    {"id": "taggedNoise", "statement": "Recover noise from tagged projection.", "quote": q, "kind": "uniqueRecovery", "target": "obsTagged", "tag": "noise"},
                    {"id": "untaggedSignal", "statement": "Recover signal from untagged lossy op.", "quote": q, "kind": "uniqueRecovery", "target": "obsUntagged", "tag": "signal"},
                    {"id": "untaggedNoise", "statement": "Recover noise from untagged lossy op.", "quote": q, "kind": "uniqueRecovery", "target": "obsUntagged", "tag": "noise"},
                ],
            }
            self.assertEqual(validate_spec(spec, doc=doc)[0], [])
            sp = base / "proj.json"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            out = base / "out"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp), "--out", str(out)]), 0)
            rep = json.loads((out / "ProjAuditor_report.json").read_text(encoding="utf-8"))
            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}

            self.assertEqual(by_id["taggedSignal"]["verdict"], "admissible")
            self.assertEqual(by_id["taggedNoise"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["taggedNoise"]["findings"]], ["lossyChannelOnPath"])
            self.assertEqual(by_id["untaggedSignal"]["verdict"], "unestablished")
            self.assertEqual([f["type"] for f in by_id["untaggedSignal"]["findings"]], ["untargetedLossyChannel"])
            self.assertEqual(by_id["untaggedNoise"]["verdict"], "unestablished")
            self.assertEqual([f["type"] for f in by_id["untaggedNoise"]["findings"]], ["untargetedLossyChannel"])

    def test_codex_27379_xor_side_information_bypass_and_prompt_loses_guidance(self) -> None:
        """Regression test for Codex `#27379`:
        Two independent bits `s` (`signal`) and `r` (`reference`) enter `p = s XOR r` (`loses: ["signal", "reference"]`):
        - Observing `p` alone (no side-information bypass) -> `rejected` (`lossyChannelOnPath`).
        - Observing `(p, r)` (`r` bypasses `measure_parity` into output) -> `unestablished` (`lossyWithSideInformation`).
        - `audit_cli prompt` documents the optional `"loses"` field on `kind: "lossy"` ops.
        """
        doc_text = "Independent bits s and r enter p = s XOR r; observing (p, r) recovers s = p XOR r, whereas p alone loses s.\n"
        q = doc_text.strip()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            doc_path = base / "xor.txt"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            # Prompt documents `loses`
            prompt_path = base / "prompt.txt"
            self.assertEqual(cli_main(["prompt", "--doc", str(doc_path), "--out", str(prompt_path)]), 0)
            self.assertIn('"loses"', prompt_path.read_text(encoding="utf-8"))

            spec = {
                "schema_version": "epistemic-ledger/v2.3",
                "auditor": "XorSideInfo",
                "paper_title": "Codex 27379 Side Information Test",
                "nodes": ["sBit", "rBit", "parityP", "pairPR"],
                "tags": ["signal", "reference"],
                "sources": [
                    {"node": "sBit", "origin": "measured", "carries": ["signal"], "quote": q},
                    {"node": "rBit", "origin": "measured", "carries": ["reference"], "quote": q},
                ],
                "ops": [
                    {"name": "measure_parity", "inputs": ["sBit", "rBit"], "output": "parityP", "kind": "lossy", "loses": ["signal", "reference"], "introduces": [], "quote": q},
                    {"name": "combine_pr", "inputs": ["parityP", "rBit"], "output": "pairPR", "kind": "transform", "introduces": [], "quote": q},
                ],
                "claims": [
                    {"id": "recoverFromPOnly", "statement": "Recover s from p alone.", "quote": q, "kind": "uniqueRecovery", "target": "parityP", "tag": "signal"},
                    {"id": "recoverFromPairPR", "statement": "Recover s from (p, r).", "quote": q, "kind": "uniqueRecovery", "target": "pairPR", "tag": "signal"},
                ],
            }
            self.assertEqual(validate_spec(spec, doc=doc)[0], [])
            sp = base / "xor.json"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            out = base / "out"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp), "--out", str(out)]), 0)
            rep = json.loads((out / "XorSideInfo_report.json").read_text(encoding="utf-8"))
            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}

            self.assertEqual(by_id["recoverFromPOnly"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["recoverFromPOnly"]["findings"]], ["lossyChannelOnPath"])
            self.assertEqual(by_id["recoverFromPairPR"]["verdict"], "unestablished")
            self.assertEqual([f["type"] for f in by_id["recoverFromPairPR"]["findings"]], ["lossyWithSideInformation"])
            self.assertEqual(by_id["recoverFromPairPR"]["findings"][0]["side_nodes"], ["rBit"])

            # Codex #27382: uniqueRecovery reports explicitly disclose DAG independent-source-support boundary,
            # and modeling coupled `(r, c)` (`c = r`) via a shared upstream SourceNode triggers `lossyWithSideInformation`.
            md_xor = (out / "XorSideInfo_report.md").read_text(encoding="utf-8")
            self.assertIn("Unmodeled joint support constraints across disconnected SourceNodes", md_xor)
            self.assertTrue(any("joint support constraints" in s for s in rep["out_of_scope"]))

            spec_coupled = copy.deepcopy(spec)
            spec_coupled["auditor"] = "XorCoupled"
            spec_coupled["nodes"] = ["sBit", "sharedR", "rCopy", "cCopy", "parityP", "pairPC"]
            spec_coupled["sources"] = [
                {"node": "sBit", "origin": "measured", "carries": ["signal"], "quote": q},
                {"node": "sharedR", "origin": "measured", "carries": ["reference"], "quote": q},
            ]
            spec_coupled["ops"] = [
                {"name": "emit_r", "inputs": ["sharedR"], "output": "rCopy", "kind": "transform", "introduces": [], "quote": q},
                {"name": "emit_c_eq_r", "inputs": ["sharedR"], "output": "cCopy", "kind": "transform", "introduces": [], "quote": q},
                {"name": "measure_parity", "inputs": ["sBit", "rCopy"], "output": "parityP", "kind": "lossy", "loses": ["signal", "reference"], "introduces": [], "quote": q},
                {"name": "combine_pc", "inputs": ["parityP", "cCopy"], "output": "pairPC", "kind": "transform", "introduces": [], "quote": q},
            ]
            spec_coupled["claims"] = [
                {"id": "recoverCoupledPC", "statement": "Recover s from (s XOR r, c) with c = r via sharedR.", "quote": q, "kind": "uniqueRecovery", "target": "pairPC", "tag": "signal"},
            ]
            sp_c = base / "xor_coupled.json"
            sp_c.write_text(json.dumps(spec_coupled), encoding="utf-8")
            out_c = base / "out_c"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_c), "--out", str(out_c)]), 0)
            rep_c = json.loads((out_c / "XorCoupled_report.json").read_text(encoding="utf-8"))
            c0 = rep_c["lean_verification"]["claims"][0]
            self.assertEqual(c0["verdict"], "unestablished")
            self.assertEqual([f["type"] for f in c0["findings"]], ["lossyWithSideInformation"])
            self.assertEqual(c0["findings"][0]["side_nodes"], ["sharedR"])

    def test_claude_27388_large_graph_no_max_rec_depth_and_scaled_usage_numbers(self) -> None:
        """Regression tests for Claude `#27388`:
        1. Large 25-node, 14-op graph verifies cleanly in Lean kernel via `by rfl` without hitting
           `maxRecDepth` / `sorryAx` (and negative control confirms kernel still rejects wrong verdicts).
        2. Exact scaled resource quantities (`21.6M`, `900M`, `1.5 billion`, `4.2K`) ground cleanly to
           exact integers (`21600000`, `900000000`, `1500000000`, `4200`), while slicing `900` out of
           `900M` or `900 million` fails with `truncated_numeric_quote`.
        """
        doc_text = (
            "Good views reached target accuracy after 21.6M samples, whereas next-token training ran for 900M samples.\n"
            "Auxiliary run used 1.5 billion tokens and 4.2K steps (100MB checkpoint).\n"
        )
        q_21m = "Good views reached target accuracy after 21.6M samples, whereas next-token training ran for 900M samples."
        q_aux = "Auxiliary run used 1.5 billion tokens and 4.2K steps (100MB checkpoint)."
        q_sliced_900 = "whereas next-token training ran for 900"

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            doc_path = base / "scale.txt"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            # Build a 25-node, 14-op graph (larger than Claude's 20-node, 11-op math spec that hit maxRecDepth)
            nodes = [f"src_{i}" for i in range(11)] + [f"step_{i}" for i in range(14)]
            sources = [
                {"node": f"src_{i}", "origin": "setByExperimenter", "carries": ["resourceCost"] if i < 2 else [], "quote": q_21m}
                for i in range(11)
            ]
            ops = [
                {"name": "op_0", "inputs": ["src_0", "src_2", "src_3"], "output": "step_0", "kind": "transform", "introduces": [], "quote": q_21m},
                {"name": "op_1", "inputs": ["src_1", "src_4", "src_5"], "output": "step_1", "kind": "transform", "introduces": [], "quote": q_21m},
            ]
            for i in range(2, 12):
                ops.append(
                    {
                        "name": f"op_{i}",
                        "inputs": [f"step_{i - 2}", f"src_{min(i + 4, 10)}"],
                        "output": f"step_{i}",
                        "kind": "transform",
                        "introduces": [],
                        "quote": q_aux,
                    }
                )
            ops.append({"name": "op_ledger", "inputs": ["src_0", "src_1"], "output": "step_12", "kind": "transform", "introduces": [], "quote": q_21m})
            ops.append({"name": "op_eval", "inputs": ["step_10", "step_11", "step_12"], "output": "step_13", "kind": "transform", "introduces": [], "quote": q_21m})

            spec = {
                "schema_version": "epistemic-ledger/v2.4",
                "auditor": "LargeGraphScale",
                "paper_title": "Large Graph & Epistemic v2.4",
                "nodes": nodes,
                "tags": ["resourceCost", "hypA"],
                "sources": sources,
                "ops": ops,
                "claims": [
                    {
                        "id": "scaledEfficiency",
                        "statement": "Compare good views vs next-token structurally on 25-node graph.",
                        "quote": q_21m,
                        "nature": "quantitative",
                        "quantitative_kind": "order",
                        "kind": "effectivenessClaim",
                        "method_node": "step_10",
                        "evaluation_node": "step_13",
                        "control_node": "step_11",
                        "cost_ledger_node": "step_12",
                        "cost_tag": "resourceCost",
                        "method_measurement_quote": q_21m,
                        "control_measurement_quote": q_21m,
                    },
                    {
                        "id": "deepConditional",
                        "statement": "Conditional on all 11 declared sources across 25-node graph.",
                        "quote": q_aux,
                        "nature": "qualitative",
                        "kind": "conditionalFlow",
                        "target": "step_13",
                        "declared_sources": [f"src_{i}" for i in range(11)],
                    },
                ],
            }
            self.assertEqual(validate_spec(spec, doc=doc)[0], [])

            sp = base / "large.json"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            out = base / "out"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp), "--out", str(out)]), 0)
            rep = json.loads((out / "LargeGraphScale_report.json").read_text(encoding="utf-8"))
            self.assertTrue(rep["lean_verification"]["axioms_ok"])
            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}
            self.assertEqual(by_id["scaledEfficiency"]["verdict"], "admissible")
            self.assertEqual(by_id["scaledEfficiency"]["findings"], [])
            self.assertEqual(by_id["deepConditional"]["verdict"], "admissible")

            # Epistemic v2.4 (Claude #27430 + #27432 amendment) on real-sentence patterns:
            # - Part A (JEPA `"need 42 times fewer"`): separate claims for observed order (`effectivenessClaim`),
            #   necessity hypothesis `"need"` (`theoremApplication`), and derived ratio `"42 times"` (`outOfScope`)
            # - Part B (Barontini F2): `emergesWithout` / `emergesWithExclusion` across `.forget ... .notShown` -> `rejected`
            # - Part C (Spacetime Q6 vs Q7): `hedged: true` + `hedge_quote` is grounded & displayed on the modified clause
            #   WITHOUT changing Lean verdicts; `"Given a supplied X, Y follows"` stays `conditionalFlow` (`admissible`)
            # - Part D (Barontini Q4): `compare` emits `strictest_verdict` column (`unestablished` vs `admissible` -> `unestablished`)
            ep_doc_text = (
                "The states are ordered using only internal degrees of freedom without laboratory time.\n"
                "Spacetime geometry can emerge from an agent's predictions alone.\n"
                "Within this task, spacetime geometry is obtained from an agent's successful predictions and actions, providing a first step toward emergent spacetime.\n"
                "Given a supplied coordinate grid, the learned map follows directly.\n"
                "These results establish a controlled experimental setting for entropic time.\n"
                "Good views need 42 times fewer training samples than next-token prediction; we scored no earlier next-token checkpoint.\n"
            )
            q_bar = "The states are ordered using only internal degrees of freedom without laboratory time."
            q_sp6 = "Spacetime geometry can emerge from an agent's predictions alone."
            q_sp7 = "Within this task, spacetime geometry is obtained from an agent's successful predictions and actions, providing a first step toward emergent spacetime."
            q_cond = "Given a supplied coordinate grid, the learned map follows directly."
            q_bar4 = "These results establish a controlled experimental setting for entropic time."
            q_jepa_need = "Good views need 42 times fewer training samples than next-token prediction; we scored no earlier next-token checkpoint."
            ep_doc_path = base / "epistemic_v24.txt"
            ep_doc_path.write_text(ep_doc_text, encoding="utf-8")
            ep_doc = ingest_document(str(ep_doc_path))

            # Prompt check: includes v2.5 ask-back/nature/quantitative_kind/decomposition/hedging rules
            # AND never leaks any of the 13 graded sentences into prompt instructions (Claude #27435 / v2 spec)
            from pipeline.report import build_extraction_prompt

            prompt_txt = build_extraction_prompt(ep_doc, auditor_name="BlindPromptCheck")
            prompt_header = prompt_txt.split("--- BEGIN DOCUMENT ---", 1)[0]
            for needle in (
                "epistemic-ledger/v2.5",
                "audit_cli ask",
                "ask_back",
                "exclusion_wording_quote",
                "excluded_object",
                "quantitative_kind",
                "specificValue",
                "derivedComparison",
                "Decompose compound",
                "Given a supplied X, Y follows",
            ):
                self.assertIn(needle, prompt_header)
            for forbidden in (
                "Good views need 42 times",
                "42 times fewer",
                "Within this task",
                "spacetime geometry",
                "first step toward",
                "internal degrees of freedom",
                "no longer a hypothesis",
                "controlled experimental setting",
                "JEPA with bad views",
                "Even that rotation needs no pair",
                "platonic representations",
                "effective Schrödinger equation",
                "characteristic null structure",
                "Minkowski metric",
                "scrambles that information",
            ):
                self.assertNotIn(forbidden, prompt_header)

            spec_ep_a = {
                "schema_version": "epistemic-ledger/v2.4",
                "auditor": "EpistemicA",
                "paper_title": "Epistemic v2.4 Regression",
                "nodes": [
                    "labTime", "internalOrder", "minkowskiGrid", "cleanObs",
                    "agentGeom", "cleanGeom", "condMap", "barSetting",
                ],
                "tags": ["externalTime", "spacetimeMetric", "noLabTimeOrder", "controlNeedsFullBudget"],
                "sources": [
                    {"node": "labTime", "origin": "setByExperimenter", "carries": ["externalTime"], "quote": q_bar},
                    {"node": "minkowskiGrid", "origin": "setByExperimenter", "carries": ["spacetimeMetric"], "quote": q_sp6},
                    {"node": "cleanObs", "origin": "measured", "carries": [], "quote": q_sp7},
                ],
                "ops": [
                    {"name": "drop_lab_time", "inputs": ["labTime"], "output": "internalOrder", "kind": "forget", "tag": "externalTime", "evidence": "notShown", "quote": q_bar},
                    {"name": "train_agent", "inputs": ["minkowskiGrid"], "output": "agentGeom", "kind": "transform", "introduces": [], "quote": q_sp6},
                    {"name": "clean_step", "inputs": ["cleanObs"], "output": "cleanGeom", "kind": "transform", "introduces": [], "quote": q_sp7},
                    {"name": "derive_cond", "inputs": ["minkowskiGrid"], "output": "condMap", "kind": "transform", "introduces": [], "quote": q_cond},
                    {"name": "run_exp", "inputs": ["internalOrder"], "output": "barSetting", "kind": "transform", "introduces": [], "quote": q_bar4},
                ],
                "claims": [
                    {
                        "id": "barontiniF2UnverifiedForget",
                        "statement": "States are ordered using only internal degrees of freedom.",
                        "quote": q_bar,
                        "nature": "qualitative",
                        "kind": "emergesWithout",
                        "target": "internalOrder",
                        "tag": "externalTime",
                    },
                    {
                        "id": "spacetimeQ6Unhedged",
                        "statement": "Spacetime geometry can emerge from predictions alone.",
                        "quote": q_sp6,
                        "nature": "qualitative",
                        "kind": "emergesWithExclusion",
                        "target": "agentGeom",
                        "excluded_channel": "agentGeom",
                        "tag": "spacetimeMetric",
                    },
                    {
                        "id": "spacetimeQ7Hedged",
                        "statement": "Providing a first step toward emergent spacetime (hedged clause — display-only, does not alter verdict).",
                        "quote": q_sp7,
                        "nature": "qualitative",
                        "hedged": True,
                        "hedge_quote": "providing a first step toward emergent spacetime",
                        "kind": "emergesWithExclusion",
                        "target": "agentGeom",
                        "excluded_channel": "agentGeom",
                        "tag": "spacetimeMetric",
                    },
                    {
                        "id": "cleanHedgedEmergence",
                        "statement": "Clean hedged emergence with no upstream metric leak stays admissible.",
                        "quote": q_sp7,
                        "nature": "qualitative",
                        "hedged": True,
                        "hedge_quote": "Within this task, spacetime geometry",
                        "kind": "emergesWithout",
                        "target": "cleanGeom",
                        "tag": "spacetimeMetric",
                    },
                    {
                        "id": "genuineConditional",
                        "statement": "Given a supplied coordinate grid, the learned map follows directly.",
                        "quote": q_cond,
                        "nature": "qualitative",
                        "kind": "conditionalFlow",
                        "target": "condMap",
                        "declared_sources": ["minkowskiGrid"],
                    },
                    {
                        "id": "barontiniQ4Setting",
                        "statement": "Controlled experimental setting for entropic time.",
                        "quote": q_bar4,
                        "nature": "qualitative",
                        "kind": "theoremApplication",
                        "target": "barSetting",
                        "hypotheses": [{"tag": "noLabTimeOrder", "status": "bet", "quote": q_bar}],
                        "declared_bets": [],
                    },
                    {
                        "id": "jepaNeedNecessityHyp",
                        "statement": "Control actually requires the full training budget (necessity proposition of 'need').",
                        "quote": q_jepa_need,
                        "nature": "qualitative",
                        "kind": "theoremApplication",
                        "target": "barSetting",
                        "hypotheses": [{"tag": "controlNeedsFullBudget", "status": "bet", "quote": "we scored no earlier next-token checkpoint"}],
                        "declared_bets": ["controlNeedsFullBudget"],
                    },
                    {
                        "id": "jepaRatio42OutOfScope",
                        "statement": "Derived ratio '42 times fewer' is out of scope.",
                        "quote": q_jepa_need,
                        "nature": "quantitative",
                        "quantitative_kind": "derivedComparison",
                        "kind": "outOfScope",
                    },
                ],
            }
            self.assertEqual(validate_spec(spec_ep_a, doc=ep_doc)[0], [])

            # Auditor B:
            # - omits extra unchecked bet on Q4 -> `admissible` (DISAGREE: A=unestablished, B=admissible -> Strictest=unestablished)
            # - omits `jepaNeedNecessityHyp` (only Auditor A reports it -> UNVERIFIED_OR_UNMATCHED -> Strictest MUST be None / `*—*`)!
            spec_ep_a_cmp = copy.deepcopy(spec_ep_a)
            spec_ep_a_cmp["claims"] = [
                c for c in spec_ep_a["claims"] if c["id"] not in ("cleanHedgedEmergence", "jepaRatio42OutOfScope")
            ]
            spec_ep_b = copy.deepcopy(spec_ep_a_cmp)
            spec_ep_b["auditor"] = "EpistemicB"
            spec_ep_b["claims"] = [c for c in spec_ep_b["claims"] if c["id"] != "jepaNeedNecessityHyp"]
            for cl in spec_ep_b["claims"]:
                if cl["id"] == "barontiniQ4Setting":
                    cl["hypotheses"][0]["status"] = "discharged"

            sp_ep_full = base / "ep_full.json"
            sp_ep_full.write_text(json.dumps(spec_ep_a), encoding="utf-8")
            out_ep = base / "out_ep"
            self.assertEqual(cli_main(["run", "--doc", str(ep_doc_path), "--spec", str(sp_ep_full), "--out", str(out_ep)]), 0)
            rep_ep = json.loads((out_ep / "EpistemicA_report.json").read_text(encoding="utf-8"))
            md_ep = (out_ep / "EpistemicA_report.md").read_text(encoding="utf-8")
            ep_by_id = {c["id"]: c for c in rep_ep["lean_verification"]["claims"]}
            self.assertEqual(ep_by_id["barontiniF2UnverifiedForget"]["verdict"], "rejected")
            self.assertEqual(ep_by_id["spacetimeQ6Unhedged"]["verdict"], "rejected")
            # Legacy hedge fields are ignored and never alter verdict or render in Markdown
            self.assertEqual(ep_by_id["spacetimeQ7Hedged"]["verdict"], "rejected")
            self.assertNotIn("hedged", ep_by_id["spacetimeQ7Hedged"])
            self.assertNotIn("hedge_quote", ep_by_id["spacetimeQ7Hedged"])
            self.assertNotIn("Hedge quote:", md_ep)
            self.assertEqual(ep_by_id["cleanHedgedEmergence"]["verdict"], "admissible")
            self.assertEqual(ep_by_id["genuineConditional"]["verdict"], "admissible")
            self.assertEqual(ep_by_id["barontiniQ4Setting"]["verdict"], "unestablished")
            self.assertEqual(ep_by_id["jepaNeedNecessityHyp"]["verdict"], "admissible")
            self.assertEqual(ep_by_id["jepaNeedNecessityHyp"]["declared_bet_count"], 1)
            self.assertEqual(ep_by_id["jepaRatio42OutOfScope"]["verdict"], "outOfScope")

            # Claude #27390: mechanical declaration_locations notes (`in_claim` vs `elsewhere_in_document`)
            # without altering verdicts!
            doc2_text = (
                "Abstract: Assuming GRH, the main circuit bound holds over every field.\n"
                "Section 3: The contracting case rests on Lean formalization and external axioms.\n"
            )
            q_abs = "Assuming GRH, the main circuit bound holds over every field."
            q_sec3 = "The contracting case rests on Lean formalization and external axioms."
            doc2_path = base / "decl_loc.txt"
            doc2_path.write_text(doc2_text, encoding="utf-8")
            spec_dl = {
                "schema_version": "epistemic-ledger/v2.3",
                "auditor": "DeclLocAuditor",
                "paper_title": "Declaration Location Test",
                "nodes": ["inClaimSrc", "bodySrc", "thmOut"],
                "tags": ["grh", "leanAx"],
                "sources": [
                    {"node": "inClaimSrc", "origin": "setByExperimenter", "carries": ["grh"], "quote": "Assuming GRH, the main circuit bound"},
                    {"node": "bodySrc", "origin": "setByExperimenter", "carries": ["leanAx"], "quote": q_sec3},
                ],
                "ops": [
                    {"name": "prove", "inputs": ["inClaimSrc", "bodySrc"], "output": "thmOut", "kind": "transform", "introduces": [], "quote": q_abs},
                ],
                "claims": [
                    {
                        "id": "thmWithMixedDeclLocs",
                        "statement": "Main circuit bound holds given GRH and Lean formalization.",
                        "quote": q_abs,
                        "kind": "theoremApplication",
                        "target": "thmOut",
                        "hypotheses": [
                            {"tag": "grh", "status": "bet", "quote": "Assuming GRH, the main circuit bound"},
                            {"tag": "leanAx", "status": "bet", "quote": q_sec3},
                        ],
                        "declared_bets": ["grh", "leanAx"],
                    },
                    {
                        "id": "condWithMixedDeclLocs",
                        "statement": "Conditional on both sources.",
                        "quote": q_abs,
                        "kind": "conditionalFlow",
                        "target": "thmOut",
                        "declared_sources": ["inClaimSrc", "bodySrc"],
                    },
                ],
            }
            sp_dl = base / "decl_loc.json"
            sp_dl.write_text(json.dumps(spec_dl), encoding="utf-8")
            out_dl = base / "out_dl"
            self.assertEqual(cli_main(["run", "--doc", str(doc2_path), "--spec", str(sp_dl), "--out", str(out_dl)]), 0)
            rep_dl = json.loads((out_dl / "DeclLocAuditor_report.json").read_text(encoding="utf-8"))
            md_dl = (out_dl / "DeclLocAuditor_report.md").read_text(encoding="utf-8")
            dl_by_id = {c["id"]: c for c in rep_dl["lean_verification"]["claims"]}

            self.assertEqual(dl_by_id["thmWithMixedDeclLocs"]["verdict"], "admissible")
            self.assertEqual(dl_by_id["thmWithMixedDeclLocs"]["declared_bet_count"], 2)
            thm_locs = {x["item"]: x["location"] for x in dl_by_id["thmWithMixedDeclLocs"]["declaration_locations"]}
            self.assertEqual(thm_locs, {"grh": "in_claim", "leanAx": "elsewhere_in_document"})

            self.assertEqual(dl_by_id["condWithMixedDeclLocs"]["verdict"], "admissible")
            self.assertEqual(dl_by_id["condWithMixedDeclLocs"]["declared_bet_count"], 0)
            cond_locs = {x["item"]: x["location"] for x in dl_by_id["condWithMixedDeclLocs"]["declaration_locations"]}
            self.assertEqual(cond_locs, {"inClaimSrc": "in_claim", "bodySrc": "elsewhere_in_document"})

            self.assertEqual(dl_by_id["thmWithMixedDeclLocs"]["display_state"], "conditional")
            self.assertEqual(dl_by_id["condWithMixedDeclLocs"]["display_state"], "noStructuralAlarm")
            self.assertIn("conditional on 2 declared, unchecked assumptions", md_dl)
            self.assertIn("declared in claim sentence", md_dl)
            self.assertIn("declared in document body (offset @", md_dl)

    def test_questions_slot_legacy_ask_back_ignored_and_display_states(self) -> None:
        """End-to-end tests for C4+D1 (`question-slot-spec.md`) + D1/D2 display states:
        1. `admissible` -> `display_state: noStructuralAlarm` (`no structural alarm`), or `conditional`
           (`conditional on N declared, unchecked assumption(s)`) when `declared_bet_count >= 1`;
           `"admissible"` appears ONLY in the enum legend.
        2. Legacy v2.5 record with `ask_back`, `exclusion_wording_quote`, `excluded_object` runs exit 0,
           silently ignores `ask_back`, and emits no stop-answer text or E2–E7 lines.
        3. Record-level `questions` slot supports `answered`, `partly` (including short 2-char phrase `"Có"`),
           `not_in_document`, `asked_by` in `{reader, human}`, optional `claim_id` (rendered under claim vs
           grouped by `about_quote` under `## Questions`), JSON under `questions` with `verified_by_lean: False`,
           and ZERO Lean verdict effect.
        4. Validation refuses: ungrounded `answer_quotes`, `phrase` not in `about_quote`, `not_in_document`
           with non-empty `answer_quotes`, `partly` without `stays_open`, `not_in_document` without `searched`,
           `answered` with empty `answer_quotes`, invalid `asked_by`, unknown `claim_id`.
        5. `ask` and `compare` are removed from `audit_cli`.
        """
        import contextlib
        import io
        import re

        doc_text = (
            "Abstract: The randomised trial shows treatment outperforms the independent control arm.\n"
            "Section 2: Assuming hypothesis H1 and hypothesis H2, the main structural bound holds.\n"
            "Section 3: Có, ở thời điểm sinh con đầu lòng; mẫu khảo sát chỉ gồm 120 người tại hai thành phố lớn.\n"
            "Section 4: The experiment only measured cohort A and did not measure long-term outcomes.\n"
            "Section 5: The randomised allocation was stratified by clinic and balanced across arms.\n"
        )
        q_rct = "The randomised trial shows treatment outperforms the independent control arm."
        q_thm = "Assuming hypothesis H1 and hypothesis H2, the main structural bound holds."
        q_vn = "Có, ở thời điểm sinh con đầu lòng; mẫu khảo sát chỉ gồm 120 người tại hai thành phố lớn."
        q_slice = "The experiment only measured cohort A and did not measure long-term outcomes."
        q_strat = "The randomised allocation was stratified by clinic and balanced across arms."

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            doc_path = base / "qslot.txt"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            # 5. `ask` and `compare` are gone from CLI
            for removed_cmd in ("ask", "compare", "extract"):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as cm:
                        cli_main([removed_cmd, "--doc", str(doc_path)])
                self.assertEqual(cm.exception.code, 2)

            # 1 & 2. Legacy v2.5 record carrying `ask_back` + `exclusion_wording_quote` + `excluded_object`
            spec_legacy_ab = {
                "schema_version": "epistemic-ledger/v2.5",
                "auditor": "DisplayAuditor",
                "paper_title": "Question Slot & Display Verification",
                "nodes": [
                    "treatIn",
                    "ctrlIn",
                    "treatArm",
                    "ctrlArm",
                    "rctEval",
                    "unusedLedger",
                    "thmOut",
                ],
                "tags": ["studyCost", "hyp1", "hyp2", "hyp3"],
                "sources": [
                    {"node": "treatIn", "origin": "setByExperimenter", "carries": [], "quote": q_rct},
                    {"node": "ctrlIn", "origin": "setByExperimenter", "carries": [], "quote": q_rct},
                    {"node": "unusedLedger", "origin": "setByExperimenter", "carries": ["studyCost"], "quote": q_rct},
                ],
                "ops": [
                    {"name": "run_treat", "inputs": ["treatIn"], "output": "treatArm", "kind": "transform", "introduces": [], "quote": q_rct},
                    {"name": "run_ctrl", "inputs": ["ctrlIn"], "output": "ctrlArm", "kind": "transform", "introduces": [], "quote": q_rct},
                    {"name": "eval_rct", "inputs": ["treatArm", "ctrlArm"], "output": "rctEval", "kind": "transform", "introduces": [], "quote": q_rct},
                    {"name": "derive_thm", "inputs": ["treatIn"], "output": "thmOut", "kind": "transform", "introduces": [], "quote": q_thm},
                ],
                "claims": [
                    {
                        "id": "rctNoCostLedger",
                        "statement": "Randomised trial shows treatment outperforms control without a declared cost ledger.",
                        "quote": q_rct,
                        "provenance": "authorClaimed",
                        "nature": "qualitative",
                        "kind": "effectivenessClaim",
                        "method_node": "treatArm",
                        "evaluation_node": "rctEval",
                        "control_node": "ctrlArm",
                        "cost_ledger_node": None,
                        "cost_tag": "studyCost",
                        "ask_back": {
                            "causal": {"status": "not_found", "searched_where": "Legacy ignored field."},
                            "slice": {"status": "answered", "quote": "legacy unverified quote ignored", "reading": "beyond"},
                        },
                    },
                    {
                        "id": "rctUnusedDeclaredLedger",
                        "statement": "Same RCT with an explicitly declared ledger that does not feed evaluation.",
                        "quote": q_rct,
                        "provenance": "reviewerStressTest",
                        "nature": "qualitative",
                        "kind": "effectivenessClaim",
                        "method_node": "treatArm",
                        "evaluation_node": "rctEval",
                        "control_node": "ctrlArm",
                        "cost_ledger_node": "unusedLedger",
                        "cost_tag": "studyCost",
                    },
                    {
                        "id": "thmConditionalTwoBets",
                        "statement": "Assuming H1 and H2, the structural bound holds.",
                        "quote": q_thm,
                        "provenance": "authorClaimed",
                        "nature": "qualitative",
                        "kind": "theoremApplication",
                        "target": "thmOut",
                        "hypotheses": [
                            {"tag": "hyp1", "status": "bet", "quote": q_thm},
                            {"tag": "hyp2", "status": "bet", "quote": q_thm},
                        ],
                        "declared_bets": ["hyp1", "hyp2"],
                        "exclusion_wording_quote": "legacy ignored",
                        "excluded_object": "legacy ignored",
                    },
                    {
                        "id": "thmUnestablishedWithOneDeclaredBet",
                        "statement": "Bound with one declared bet and one undeclared bet stays unestablished.",
                        "quote": q_thm,
                        "provenance": "reviewerStressTest",
                        "nature": "qualitative",
                        "kind": "theoremApplication",
                        "target": "thmOut",
                        "hypotheses": [
                            {"tag": "hyp1", "status": "bet", "quote": q_thm},
                            {"tag": "hyp3", "status": "bet", "quote": q_thm},
                        ],
                        "declared_bets": ["hyp1"],
                    },
                    {
                        "id": "condFlowClaim",
                        "statement": "Conditional on treatIn, thmOut follows.",
                        "quote": q_thm,
                        "provenance": "authorClaimed",
                        "nature": "qualitative",
                        "kind": "conditionalFlow",
                        "target": "thmOut",
                        "declared_sources": ["treatIn"],
                    },
                ],
            }
            self.assertEqual(validate_spec(spec_legacy_ab, doc=doc)[0], [])

            sp_leg = base / "legacy_ab.json"
            sp_leg.write_text(json.dumps(spec_legacy_ab), encoding="utf-8")
            out_leg = base / "out_leg"
            cli_buf = io.StringIO()
            with contextlib.redirect_stdout(cli_buf):
                rc = cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_leg), "--out", str(out_leg)])
            self.assertEqual(rc, 0)
            cli_out = cli_buf.getvalue()

            rep_leg = json.loads((out_leg / "DisplayAuditor_report.json").read_text(encoding="utf-8"))
            md_leg = (out_leg / "DisplayAuditor_report.md").read_text(encoding="utf-8")
            by_id_leg = {c["id"]: c for c in rep_leg["lean_verification"]["claims"]}

            self.assertEqual(by_id_leg["rctNoCostLedger"]["verdict"], "admissible")
            self.assertEqual(by_id_leg["rctNoCostLedger"]["display_state"], "noStructuralAlarm")
            self.assertEqual(by_id_leg["rctNoCostLedger"]["findings"], [])
            self.assertEqual(by_id_leg["rctUnusedDeclaredLedger"]["verdict"], "unestablished")
            self.assertEqual(by_id_leg["thmConditionalTwoBets"]["display_state"], "conditional")
            self.assertEqual(by_id_leg["thmUnestablishedWithOneDeclaredBet"]["display_state"], "unestablished")
            self.assertEqual(by_id_leg["condFlowClaim"]["display_state"], "noStructuralAlarm")
            self.assertIn("checks declared upstream sources", md_leg)

            # CLI & Markdown display legend check
            self.assertNotIn("admissible", cli_out.lower())
            self.assertIn("rctNoCostLedger: no structural alarm (0 finding(s),", cli_out)
            self.assertIn("thmConditionalTwoBets: conditional on 2 declared, unchecked assumptions", cli_out)
            non_legend_md = "\n".join(ln for ln in md_leg.splitlines() if "Display-state legend:" not in ln)
            self.assertIsNone(re.search(r"\badmissible\b", non_legend_md, flags=re.IGNORECASE))

            # Zero stop-answer or E2-E7 artifacts anywhere in JSON or Markdown
            self.assertNotIn("reader_ask_back", rep_leg)
            self.assertNotIn("ask_back_summary", rep_leg)
            self.assertFalse(rep_leg["questions"]["verified_by_lean"])
            self.assertEqual(rep_leg["questions"]["items"], [])
            for forbidden_txt in ("Stop answers", "Reader Stop Answers", "Ask-Back", "E2:", "E3:", "E4:", "E5:", "E6", "E7"):
                self.assertNotIn(forbidden_txt, md_leg)

            # 3. Attach record-level `questions` covering `answered`, `partly` (short phrase `"Có"`),
            #    `not_in_document`, `reader` + `human`, with and without `claim_id`
            spec_with_q = copy.deepcopy(spec_legacy_ab)
            spec_with_q["questions"] = [
                {
                    "about_quote": q_rct,
                    "phrase": "randomised trial",
                    "question": "How was randomisation carried out across clinics?",
                    "asked_by": "reader",
                    "status": "answered",
                    "answer_quotes": [q_strat],
                    "answer": "Allocation was stratified by clinic and balanced across arms.",
                    "claim_id": "rctNoCostLedger",
                },
                {
                    "about_quote": q_vn,
                    "phrase": "Có",
                    "question": "Does 'Có' rest on a nationally representative sample?",
                    "asked_by": "human",
                    "status": "partly",
                    "answer_quotes": [q_vn],
                    "answer": "The sentence reports a sample of 120 respondents in two major cities.",
                    "stays_open": "Whether the finding generalizes beyond those two cities is not answered.",
                },
                {
                    "about_quote": q_vn,
                    "phrase": "120 người",
                    "question": "What was the response rate for the 120 respondents?",
                    "asked_by": "reader",
                    "status": "not_in_document",
                    "answer": "No response rate is reported.",
                    "searched": "Checked Abstract and Sections 2-5; no response rate appears.",
                },
                {
                    "about_quote": q_thm,
                    "phrase": "main structural bound",
                    "question": "Were long-term outcomes measured?",
                    "asked_by": "human",
                    "status": "not_in_document",
                    "answer_quotes": [],
                    "searched": "Checked Sections 2-5; Section 4 states long-term outcomes were not measured.",
                    "claim_id": "thmConditionalTwoBets",
                },
            ]
            self.assertEqual(validate_spec(spec_with_q, doc=doc)[0], [])

            sp_q = base / "with_q.json"
            sp_q.write_text(json.dumps(spec_with_q, ensure_ascii=False), encoding="utf-8")
            out_q = base / "out_q"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_q), "--out", str(out_q)]), 0)
            rep_q = json.loads((out_q / "DisplayAuditor_report.json").read_text(encoding="utf-8"))
            md_q = (out_q / "DisplayAuditor_report.md").read_text(encoding="utf-8")

            # Lean block must be 100% identical (zero verdict effect!)
            self.assertEqual(
                [{k: v for k, v in c.items()} for c in rep_q["lean_verification"]["claims"]],
                [{k: v for k, v in c.items()} for c in rep_leg["lean_verification"]["claims"]],
            )
            self.assertFalse(rep_q["questions"]["verified_by_lean"])
            self.assertEqual(len(rep_q["questions"]["items"]), 4)
            for c in rep_q["lean_verification"]["claims"]:
                self.assertNotIn("questions", c)

            # Attached question appears under claim `rctNoCostLedger`; unattached grouped by `about_quote` under `## Questions`
            sec_rct = md_q[md_q.index("### `rctNoCostLedger`") : md_q.index("### `rctUnusedDeclaredLedger`")]
            self.assertIn('**"randomised trial"** (reader, `answered`)', sec_rct)
            self.assertIn(q_strat, sec_rct)
            self.assertIn("## Questions", md_q)
            q_sec = md_q[md_q.index("## Questions") :]
            # Both unattached questions share `q_vn`, so `> {q_vn}` appears once as group header
            self.assertEqual(q_sec.count(f"> {q_vn}"), 1)
            self.assertIn('**"Có"** (human, `partly`)', q_sec)
            self.assertIn('**"120 người"** (reader, `not_in_document`)', q_sec)

            # 4. Negative controls (spec Acceptance check 3)
            bad_ungrounded = copy.deepcopy(spec_with_q)
            bad_ungrounded["questions"][0]["answer_quotes"] = ["Fabricated quote not present in the source document."]
            self.assertTrue(any(e.code == "ungrounded_quote" for e in validate_spec(bad_ungrounded, doc=doc)[0]))

            bad_phrase = copy.deepcopy(spec_with_q)
            bad_phrase["questions"][1]["phrase"] = "not inside about quote"
            self.assertTrue(any(e.code == "phrase_not_in_about_quote" for e in validate_spec(bad_phrase, doc=doc)[0]))

            bad_nid_quotes = copy.deepcopy(spec_with_q)
            bad_nid_quotes["questions"][2]["answer_quotes"] = [q_slice]
            self.assertTrue(any(e.code == "unexpected_answer_quotes" for e in validate_spec(bad_nid_quotes, doc=doc)[0]))

            bad_partly = copy.deepcopy(spec_with_q)
            del bad_partly["questions"][1]["stays_open"]
            self.assertTrue(any(e.code == "missing_key" and e.path.endswith(".stays_open") for e in validate_spec(bad_partly, doc=doc)[0]))

            bad_nid_searched = copy.deepcopy(spec_with_q)
            del bad_nid_searched["questions"][2]["searched"]
            self.assertTrue(any(e.code == "missing_key" and e.path.endswith(".searched") for e in validate_spec(bad_nid_searched, doc=doc)[0]))

            bad_ans_empty = copy.deepcopy(spec_with_q)
            bad_ans_empty["questions"][0]["answer_quotes"] = []
            self.assertTrue(any(e.code == "empty_list" for e in validate_spec(bad_ans_empty, doc=doc)[0]))

            bad_asker = copy.deepcopy(spec_with_q)
            bad_asker["questions"][0]["asked_by"] = "bot"
            self.assertTrue(any(e.code == "invalid_enum" and e.path.endswith(".asked_by") for e in validate_spec(bad_asker, doc=doc)[0]))

            bad_cid = copy.deepcopy(spec_with_q)
            bad_cid["questions"][0]["claim_id"] = "noSuchClaim"
            self.assertTrue(any(e.code == "unknown_question_claim" for e in validate_spec(bad_cid, doc=doc)[0]))


if __name__ == "__main__":
    unittest.main()
