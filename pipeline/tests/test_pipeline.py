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

    def test_multi_auditor_compare_agrees_despite_measured_rgb_tagging_difference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cmp"
            rc = cli_main(
                [
                    "compare",
                    "--doc",
                    str(SAMPLE_DOC),
                    "--spec",
                    str(SPEC_A),
                    "--spec",
                    str(SPEC_B),
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(rc, 0)
            comp = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
            self.assertTrue(comp["all_grounding_ok"])
            self.assertEqual(len(comp["claim_comparison"]), 4)
            for row in comp["claim_comparison"]:
                self.assertTrue(row["verdicts_agree"], f"Unexpected disagreement on {row['claim_quote']}")
                self.assertEqual(row["status"], "AGREE")

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

            # Also block invalid --auditor in `extract` and `prompt` before any file write
            rc_ext = cli_main(
                [
                    "extract",
                    "--doc",
                    str(SAMPLE_DOC),
                    "--extractor-cmd",
                    f"cat {SPEC_A}",
                    "--auditor",
                    "../pwn",
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(rc_ext, 2)
            self.assertFalse((base / "nested" / "pwn_prompt.txt").exists())

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

    def test_p1_compare_matches_by_quote_not_claim_id_and_handles_failures(self) -> None:
        """Codex P1-3:
        (a) Same quote with DIFFERENT claim IDs must align and AGREE.
        (b) Different quotes with SAME claim ID must NOT produce false AGREE.
        (c) Duplicate auditor names must NOT overwrite each other.
        (d) Failed grounding on both specs must NOT print 'identical Lean-verified verdicts'.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # (a) Same quote, different IDs + duplicate auditor name "AuditorA"
            spec_b_mod = json.loads(SPEC_B.read_text(encoding="utf-8"))
            spec_b_mod["auditor"] = "AuditorA"
            for i, cl in enumerate(spec_b_mod["claims"]):
                cl["id"] = f"renamed_{i}"
            p_b = base / "b_renamed.json"
            p_b.write_text(json.dumps(spec_b_mod), encoding="utf-8")

            out1 = base / "cmp1"
            rc1 = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(SPEC_A), "--spec", str(p_b), "--out", str(out1)])
            self.assertEqual(rc1, 0)
            comp1 = json.loads((out1 / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(comp1["auditors"], ["AuditorA_1", "AuditorA_2"])
            self.assertEqual(len(comp1["claim_comparison"]), 4)
            self.assertTrue(all(r["status"] == "AGREE" for r in comp1["claim_comparison"]))
            self.assertTrue((out1 / "AuditorA_1_Verified.lean").is_file())
            self.assertTrue((out1 / "AuditorA_2_Verified.lean").is_file())

            # (b) Different quotes sharing the same claim ID "sameId" -> 2 separate UNMATCHED rows
            s_one = json.loads(SPEC_A.read_text(encoding="utf-8"))
            s_one["claims"] = [copy.deepcopy(s_one["claims"][0])]
            s_one["claims"][0]["id"] = "sameId"
            s_two = json.loads(SPEC_B.read_text(encoding="utf-8"))
            s_two["claims"] = [copy.deepcopy(s_two["claims"][1])]
            s_two["claims"][0]["id"] = "sameId"
            p1, p2 = base / "diff1.json", base / "diff2.json"
            p1.write_text(json.dumps(s_one), encoding="utf-8")
            p2.write_text(json.dumps(s_two), encoding="utf-8")

            out2 = base / "cmp2"
            rc2 = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(p1), "--spec", str(p2), "--out", str(out2)])
            self.assertEqual(rc2, 0)
            comp2 = json.loads((out2 / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(len(comp2["claim_comparison"]), 2)
            self.assertTrue(all(r["status"] == "UNVERIFIED_OR_UNMATCHED" for r in comp2["claim_comparison"]))

            # (d) Both fail grounding -> report must say UNVERIFIED, never "identical Lean-verified verdicts"
            bad1 = json.loads(SPEC_A.read_text(encoding="utf-8"))
            bad1["sources"][0]["quote"] = "fabricated hallucinated quote number one"
            bad2 = json.loads(SPEC_B.read_text(encoding="utf-8"))
            bad2["sources"][0]["quote"] = "fabricated hallucinated quote number two"
            pb1, pb2 = base / "bad1.json", base / "bad2.json"
            pb1.write_text(json.dumps(bad1), encoding="utf-8")
            pb2.write_text(json.dumps(bad2), encoding="utf-8")

            out3 = base / "cmp3"
            rc3 = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(pb1), "--spec", str(pb2), "--out", str(out3)])
            self.assertEqual(rc3, 2)
            md3 = (out3 / "comparison.md").read_text(encoding="utf-8")
            self.assertIn("UNVERIFIED", md3)
            self.assertNotIn("identical Lean-verified verdicts", md3)

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
            self.assertEqual(by_id["claimA_clean_measured"].verdict, "rejected")
            self.assertTrue(
                any(
                    f["type"] == "danglingInput" and f["missing"] == "measuredRgbFrames"
                    for f in by_id["claimA_clean_measured"].findings
                )
            )

    def test_extract_cli_hook_end_to_end_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ext"
            rc = cli_main(
                [
                    "extract",
                    "--doc",
                    str(SAMPLE_DOC),
                    "--extractor-cmd",
                    f"cat {SPEC_A}",
                    "--auditor",
                    "AuditorA",
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue((out / "AuditorA_prompt.txt").is_file())
            self.assertTrue((out / "AuditorA_Verified.lean").is_file())
            self.assertTrue((out / "AuditorA_report.md").is_file())

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

    def test_codex_r2_p1_multi_claim_same_quote_not_dropped_and_signature_diff_flagged(self) -> None:
        """Codex R2 P1-1:
        (a) Auditor A has TWO claims (1 rejected, 1 admissible) on the same quote while Auditor B
            has 1 admissible claim -> must NOT drop the rejected claim or report AGREE; must flag AMBIGUOUS.
        (b) Same verdict on same quote with different `excluded_channel` or `tag` must flag signature diff.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # (a) Multi-claim on same quote
            s_a = json.loads(SPEC_A.read_text(encoding="utf-8"))
            clean_c = copy.deepcopy(s_a["claims"][0])
            rejected_same_quote = copy.deepcopy(s_a["claims"][0])
            rejected_same_quote["id"] = "claimA_strict_also_checked"
            rejected_same_quote["kind"] = "emergesWithout"
            del rejected_same_quote["excluded_channel"]
            s_a["claims"] = [rejected_same_quote, clean_c]

            s_b = json.loads(SPEC_B.read_text(encoding="utf-8"))
            s_b["claims"] = [copy.deepcopy(s_b["claims"][0])]

            pa, pb = base / "a.json", base / "b.json"
            pa.write_text(json.dumps(s_a), encoding="utf-8")
            pb.write_text(json.dumps(s_b), encoding="utf-8")

            out1 = base / "cmp_ambig"
            rc1 = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(pa), "--spec", str(pb), "--out", str(out1)])
            self.assertEqual(rc1, 0)
            comp1 = json.loads((out1 / "comparison.json").read_text(encoding="utf-8"))
            row = comp1["claim_comparison"][0]
            self.assertEqual(row["status"], "AMBIGUOUS")
            self.assertFalse(row["verdicts_agree"])
            self.assertEqual(len(row["by_auditor"]["AuditorA"]["claims"]), 2)
            verdicts_a = {c["verdict"] for c in row["by_auditor"]["AuditorA"]["claims"]}
            self.assertEqual(verdicts_a, {"rejected", "admissible"})

            # (b) Same verdict (rejected) on same quote, different excluded_channel -> flag diff
            s_c1 = json.loads(SPEC_A.read_text(encoding="utf-8"))
            s_c1["claims"] = [copy.deepcopy(s_c1["claims"][2])]  # claimC: excluded_channel = lossWithDepth
            s_c2 = json.loads(SPEC_B.read_text(encoding="utf-8"))
            c2 = copy.deepcopy(s_c2["claims"][2])
            c2["excluded_channel"] = "modelRegimeC"  # different excluded_channel, still rejected
            s_c2["claims"] = [c2]
            pc1, pc2 = base / "c1.json", base / "c2.json"
            pc1.write_text(json.dumps(s_c1), encoding="utf-8")
            pc2.write_text(json.dumps(s_c2), encoding="utf-8")

            out2 = base / "cmp_sig"
            rc2 = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(pc1), "--spec", str(pc2), "--out", str(out2)])
            self.assertEqual(rc2, 0)
            comp2 = json.loads((out2 / "comparison.json").read_text(encoding="utf-8"))
            row2 = comp2["claim_comparison"][0]
            self.assertTrue(row2["verdicts_agree"])
            self.assertFalse(row2["same_excluded_channel"])
            self.assertIn("excluded_channel differs", (out2 / "comparison.md").read_text(encoding="utf-8"))

    def test_codex_r2_p1_three_way_auditor_collision_AuditorA_AuditorA_AuditorA_1(self) -> None:
        """Codex R2 P1-2: `AuditorA, AuditorA, AuditorA_1` must produce 3 distinct report & proof files."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            s1 = json.loads(SPEC_A.read_text(encoding="utf-8"))
            s1["auditor"] = "AuditorA"
            s1["claims"] = [s1["claims"][0]]
            s2 = copy.deepcopy(s1)
            s3 = copy.deepcopy(s1)
            s3["auditor"] = "AuditorA_1"

            p1, p2, p3 = base / "s1.json", base / "s2.json", base / "s3.json"
            p1.write_text(json.dumps(s1), encoding="utf-8")
            p2.write_text(json.dumps(s2), encoding="utf-8")
            p3.write_text(json.dumps(s3), encoding="utf-8")

            out = base / "cmp3way"
            rc = cli_main(
                ["compare", "--doc", str(SAMPLE_DOC), "--spec", str(p1), "--spec", str(p2), "--spec", str(p3), "--out", str(out)]
            )
            self.assertEqual(rc, 0)
            comp = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(len(set(comp["auditors"])), 3)
            for aud in comp["auditors"]:
                self.assertTrue((out / f"{aud}_report.json").is_file())
                self.assertTrue((out / f"{aud}_Verified.lean").is_file())

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

    def test_codex_r3_extract_failure_clears_stale_artifacts_and_conditional_declared_diff_flagged(self) -> None:
        """Codex R3 polish:
        (a) Rerunning `extract` with a failing extractor (exit 3) clears prior spec/proof/reports.
        (b) Two `conditionalFlow` claims with identical verdicts but different `declared_sources`
            must flag `same_declared_sources = False` and not claim identical full signatures.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out_ext = base / "ext"
            rc_ok = cli_main(
                [
                    "extract",
                    "--doc",
                    str(SAMPLE_DOC),
                    "--extractor-cmd",
                    f"cat {SPEC_A}",
                    "--auditor",
                    "AuditorA",
                    "--out",
                    str(out_ext),
                ]
            )
            self.assertEqual(rc_ok, 0)
            self.assertTrue((out_ext / "AuditorA_spec.json").is_file())
            self.assertTrue((out_ext / "AuditorA_Verified.lean").is_file())

            rc_fail = cli_main(
                [
                    "extract",
                    "--doc",
                    str(SAMPLE_DOC),
                    "--extractor-cmd",
                    "python3 -c 'import sys; sys.exit(1)'",
                    "--auditor",
                    "AuditorA",
                    "--out",
                    str(out_ext),
                ]
            )
            self.assertEqual(rc_fail, 3)
            self.assertFalse((out_ext / "AuditorA_spec.json").exists())
            self.assertFalse((out_ext / "AuditorA_Verified.lean").exists())
            self.assertFalse((out_ext / "AuditorA_report.json").exists())
            self.assertFalse((out_ext / "AuditorA_report.md").exists())

            # (b) Two conditionalFlow claims: both admissible on modelRegimeA, different declared_sources
            s1 = json.loads(SPEC_A.read_text(encoding="utf-8"))
            s1["claims"] = [
                {
                    "id": "cond1",
                    "statement": "Under Regime A, 3D geometry arises.",
                    "quote": "Under Regime A, 3D geometry arises in the learned representation without 3D prediction targets in the training loss.",
                    "kind": "conditionalFlow",
                    "target": "modelRegimeA",
                    "declared_sources": ["trueSceneState", "measuredRgbFrames"],
                }
            ]
            s2 = json.loads(SPEC_B.read_text(encoding="utf-8"))
            s2["claims"] = [
                {
                    "id": "cond2",
                    "statement": "Under Regime A, 3D geometry arises.",
                    "quote": "Under Regime A, 3D geometry arises in the learned representation without 3D prediction targets in the training loss.",
                    "kind": "conditionalFlow",
                    "target": "modelRegimeA",
                    "declared_sources": ["trueSceneState", "measuredRgbFrames", "lidarDepthMaps"],
                }
            ]
            p1, p2 = base / "cond1.json", base / "cond2.json"
            p1.write_text(json.dumps(s1), encoding="utf-8")
            p2.write_text(json.dumps(s2), encoding="utf-8")
            out_cmp = base / "cmp_cond"
            rc_cmp = cli_main(
                ["compare", "--doc", str(SAMPLE_DOC), "--spec", str(p1), "--spec", str(p2), "--out", str(out_cmp)]
            )
            self.assertEqual(rc_cmp, 0)
            comp = json.loads((out_cmp / "comparison.json").read_text(encoding="utf-8"))
            row = comp["claim_comparison"][0]
            self.assertTrue(row["verdicts_agree"])
            self.assertFalse(row["same_declared_sources"])
            md = (out_cmp / "comparison.md").read_text(encoding="utf-8")
            self.assertIn("declared_sources differs", md)
            self.assertNotIn("identical Lean-verified verdicts and full claim signatures", md)

    def test_v23_effectiveness_claim_numeric_budgets_forget_proof_and_arm_independence(self) -> None:
        """Tier 2 (v2.3): end-to-end JSON -> Lean 4 kernel tests fixing all Codex R1 v2.2 counterexamples:
        (1) 100 vs 1 GPU-hr on same cluster -> unmatchedControlBudget,
        (2) separate accounts both spending 500 USD with post-hoc metering -> admissible,
        (3) `forget .shown` CANNOT erase physically spent human hours -> unaccountedCostSource,
        (4) control derived from method -> dependentControlArm,
        (5) empty usage lists -> unquantifiedBudget,
        (6) reviewerStressTest provenance recorded cleanly in report."""
        cost_doc_text = (
            "Compute Accounting Evaluation Study.\n"
            "TXN-M1500: The method used 1,500 GPU-hours on accountA during evaluation.\n"
            "TXN-C500: The control used 500 GPU-hours on accountB during evaluation.\n"
            "TXN-CLM1: On the shared cluster, the method used 1,500 GPU-hours.\n"
            "TXN-CLC1: On the shared cluster, the control used 500 GPU-hours.\n"
            "TXN-CLM2: On the shared cluster, the method used 500 GPU-hours.\n"
            "TXN-CLC2: On the shared cluster, the baseline control used 500 GPU-hours.\n"
            "TXN-M500: Specifically, the method used 500 GPU-hours on accountA.\n"
            "TXN-C500B: Separately, the control used 500 GPU-hours on accountB.\n"
            "TXN-S1: For multi-stage billing, stage 1 of the method used 500 GPU-hours.\n"
            "TXN-S2: Stage 2 of the method used 1,000 GPU-hours.\n"
            "TXN-C1500: The control baseline used 1,500 GPU-hours in total.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            cost_doc_path = Path(tmp) / "cost_study.md"
            cost_doc_path.write_text(cost_doc_text, encoding="utf-8")
            doc = ingest_document(str(cost_doc_path))
            q_hdr = "Compute Accounting Evaluation Study."
            q_m1500 = "TXN-M1500: The method used 1,500 GPU-hours on accountA during evaluation."
            q_c500 = "TXN-C500: The control used 500 GPU-hours on accountB during evaluation."
            q_cl_m1500 = "TXN-CLM1: On the shared cluster, the method used 1,500 GPU-hours."
            q_cl_c500 = "TXN-CLC1: On the shared cluster, the control used 500 GPU-hours."
            q_cl_m500 = "TXN-CLM2: On the shared cluster, the method used 500 GPU-hours."
            q_cl_c500_2 = "TXN-CLC2: On the shared cluster, the baseline control used 500 GPU-hours."
            q_m500 = "TXN-M500: Specifically, the method used 500 GPU-hours on accountA."
            q_c500_b = "TXN-C500B: Separately, the control used 500 GPU-hours on accountB."
            q_m_s1 = "TXN-S1: For multi-stage billing, stage 1 of the method used 500 GPU-hours."
            q_m_s2 = "TXN-S2: Stage 2 of the method used 1,000 GPU-hours."
            q_c1500 = "TXN-C1500: The control baseline used 1,500 GPU-hours in total."

            spec = {
                "schema_version": "epistemic-ledger/v2.3",
                "auditor": "CostAuditorV23",
                "paper_title": "Tier-2 v2.3.2 Cost & Control Test",
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
                    "evalMultiStage",
                    "evalForgotten",
                    "evalDependent",
                    "evalUnquantified",
                    "evalClonedLedger",
                ],
                "tags": ["resourceCost"],
                "sources": [
                    {"node": "sharedCluster", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_hdr},
                    {"node": "accountA", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_m1500},
                    {"node": "accountB", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_c500},
                    {"node": "humanHours", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_hdr},
                ],
                "ops": [
                    {"name": "run_m_cluster", "inputs": ["sharedCluster"], "output": "methodCluster", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "run_c_cluster", "inputs": ["sharedCluster"], "output": "ctrlCluster", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "forget_hours", "inputs": ["humanHours"], "output": "forgottenHours", "kind": "forget", "tag": "resourceCost", "evidence": "shown", "quote": q_hdr},
                    {"name": "run_m_forgot", "inputs": ["sharedCluster", "forgottenHours"], "output": "methodForgetHours", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "clone_ctrl", "inputs": ["methodCluster"], "output": "clonedCtrl", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "run_m_accA", "inputs": ["accountA"], "output": "methodAccA", "kind": "transform", "introduces": [], "quote": q_m1500},
                    {"name": "run_c_accB", "inputs": ["accountB"], "output": "ctrlAccB", "kind": "transform", "introduces": [], "quote": q_c500},
                    {"name": "bill_cluster", "inputs": ["sharedCluster"], "output": "meterCluster", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "post_hoc_bill", "inputs": ["accountA", "accountB", "methodAccA", "ctrlAccB"], "output": "postHocMeter", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "clone_ctrl_ledger", "inputs": ["ctrlCluster"], "output": "clonedCtrlLedger", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "e_uneven", "inputs": ["methodCluster", "ctrlCluster", "meterCluster"], "output": "evalUneven", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "e_equal", "inputs": ["methodAccA", "ctrlAccB", "postHocMeter"], "output": "evalEqualSep", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "e_multi", "inputs": ["methodAccA", "ctrlAccB", "postHocMeter"], "output": "evalMultiStage", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "e_forgot", "inputs": ["methodForgetHours", "ctrlCluster", "meterCluster"], "output": "evalForgotten", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "e_dep", "inputs": ["methodCluster", "clonedCtrl", "meterCluster"], "output": "evalDependent", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "e_unq", "inputs": ["methodCluster", "ctrlCluster", "meterCluster"], "output": "evalUnquantified", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "e_cloned_l", "inputs": ["methodCluster", "ctrlCluster", "clonedCtrlLedger"], "output": "evalClonedLedger", "kind": "transform", "introduces": [], "quote": q_hdr},
                ],
                "claims": [
                    {
                        "id": "unevenSameCluster",
                        "statement": "1,500 vs 500 GPU-hours on same cluster.",
                        "quote": q_m1500,
                        "provenance": "reviewerStressTest",
                        "kind": "effectivenessClaim",
                        "method_node": "methodCluster",
                        "evaluation_node": "evalUneven",
                        "control_node": "ctrlCluster",
                        "cost_ledger_node": "meterCluster",
                        "cost_tag": "resourceCost",
                        "method_usage": [
                            {"arm": "methodCluster", "source": "sharedCluster", "receipt": "TXN-CLM1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1500, "quote": q_cl_m1500}
                        ],
                        "control_usage": [
                            {"arm": "ctrlCluster", "source": "sharedCluster", "receipt": "TXN-CLC1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_cl_c500}
                        ],
                    },
                    {
                        "id": "equalSeparateAccountsPostHoc",
                        "statement": "Two separate accounts both spending 500 GPU-hours, post-hoc metered.",
                        "quote": q_m500,
                        "provenance": "authorClaimed",
                        "kind": "effectivenessClaim",
                        "method_node": "methodAccA",
                        "evaluation_node": "evalEqualSep",
                        "control_node": "ctrlAccB",
                        "cost_ledger_node": "postHocMeter",
                        "cost_tag": "resourceCost",
                        "method_usage": [
                            {"arm": "methodAccA", "source": "accountA", "receipt": "TXN-M500", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_m500}
                        ],
                        "control_usage": [
                            {"arm": "ctrlAccB", "source": "accountB", "receipt": "TXN-C500B", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500_b}
                        ],
                    },
                    {
                        "id": "distinctMultiStageSumAdmissible",
                        "statement": "Two distinct verified method receipts (500 + 1,000) match 1,500 control GPU-hours.",
                        "quote": q_c1500,
                        "provenance": "authorClaimed",
                        "kind": "effectivenessClaim",
                        "method_node": "methodAccA",
                        "evaluation_node": "evalMultiStage",
                        "control_node": "ctrlAccB",
                        "cost_ledger_node": "postHocMeter",
                        "cost_tag": "resourceCost",
                        "method_usage": [
                            {"arm": "methodAccA", "source": "accountA", "receipt": "TXN-S1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_m_s1},
                            {"arm": "methodAccA", "source": "accountA", "receipt": "TXN-S2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1000, "quote": q_m_s2},
                        ],
                        "control_usage": [
                            {"arm": "ctrlAccB", "source": "accountB", "receipt": "TXN-C1500", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1500, "quote": q_c1500}
                        ],
                    },
                    {
                        "id": "forgetCannotEraseSpentHours",
                        "statement": "Forget .shown cannot erase humanHours spent during run.",
                        "quote": q_hdr,
                        "kind": "effectivenessClaim",
                        "method_node": "methodForgetHours",
                        "evaluation_node": "evalForgotten",
                        "control_node": "ctrlCluster",
                        "cost_ledger_node": "meterCluster",
                        "cost_tag": "resourceCost",
                        "method_usage": [
                            {"arm": "methodForgetHours", "source": "sharedCluster", "receipt": "TXN-CLM2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_cl_m500}
                        ],
                        "control_usage": [
                            {"arm": "ctrlCluster", "source": "sharedCluster", "receipt": "TXN-CLC2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_cl_c500_2}
                        ],
                    },
                    {
                        "id": "dependentControlRejected",
                        "statement": "Control cloned from method output.",
                        "quote": q_hdr,
                        "kind": "effectivenessClaim",
                        "method_node": "methodCluster",
                        "evaluation_node": "evalDependent",
                        "control_node": "clonedCtrl",
                        "cost_ledger_node": "meterCluster",
                        "cost_tag": "resourceCost",
                        "method_usage": [
                            {"arm": "methodCluster", "source": "sharedCluster", "receipt": "TXN-CLM2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_cl_m500}
                        ],
                        "control_usage": [
                            {"arm": "clonedCtrl", "source": "sharedCluster", "receipt": "TXN-CLC2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_cl_c500_2}
                        ],
                    },
                    {
                        "id": "clonedControlLedgerRejected",
                        "statement": "Fake ledger cloned solely from control output.",
                        "quote": q_hdr,
                        "kind": "effectivenessClaim",
                        "method_node": "methodCluster",
                        "evaluation_node": "evalClonedLedger",
                        "control_node": "ctrlCluster",
                        "cost_ledger_node": "clonedCtrlLedger",
                        "cost_tag": "resourceCost",
                        "method_usage": [
                            {"arm": "methodCluster", "source": "sharedCluster", "receipt": "TXN-CLM2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_cl_m500}
                        ],
                        "control_usage": [
                            {"arm": "ctrlCluster", "source": "sharedCluster", "receipt": "TXN-CLC2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_cl_c500_2}
                        ],
                    },
                    {
                        "id": "unquantifiedBudgetRejected",
                        "statement": "Missing usage numbers cannot certify matched budget.",
                        "quote": q_hdr,
                        "kind": "effectivenessClaim",
                        "method_node": "methodCluster",
                        "evaluation_node": "evalUnquantified",
                        "control_node": "ctrlCluster",
                        "cost_ledger_node": "meterCluster",
                        "cost_tag": "resourceCost",
                        "method_usage": [],
                        "control_usage": [],
                    },
                ],
            }
            self.assertEqual(validate_spec(spec, doc=doc)[0], [])

            # Codex R2 P1-1: fabricated amount 1234567 not in verbatim quote MUST fail grounding!
            fab = copy.deepcopy(spec)
            fab["claims"][1]["method_usage"][0]["amount"] = 1234567
            fab_errs, _ = validate_spec(fab, doc=doc)
            self.assertTrue(any(e.code == "ungrounded_usage_amount" for e in fab_errs))

            sp = Path(tmp) / "v23.json"
            out = Path(tmp) / "out"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            rc = cli_main(["run", "--doc", str(cost_doc_path), "--spec", str(sp), "--out", str(out)])
            self.assertEqual(rc, 0)
            rep = json.loads((out / "CostAuditorV23_report.json").read_text(encoding="utf-8"))
            md = (out / "CostAuditorV23_report.md").read_text(encoding="utf-8")
            self.assertIn("`reviewerStressTest`", md)
            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}

            self.assertEqual(by_id["unevenSameCluster"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["unevenSameCluster"]["findings"]], ["unmatchedControlBudget"])
            self.assertEqual(by_id["equalSeparateAccountsPostHoc"]["verdict"], "admissible")
            self.assertEqual(by_id["equalSeparateAccountsPostHoc"]["findings"], [])
            self.assertEqual(by_id["distinctMultiStageSumAdmissible"]["verdict"], "admissible")
            self.assertEqual(by_id["distinctMultiStageSumAdmissible"]["findings"], [])
            self.assertEqual(by_id["forgetCannotEraseSpentHours"]["verdict"], "rejected")
            self.assertIn("unaccountedCostSource", [f["type"] for f in by_id["forgetCannotEraseSpentHours"]["findings"]])
            self.assertEqual(by_id["dependentControlRejected"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["dependentControlRejected"]["findings"]], ["dependentControlArm"])
            self.assertEqual(by_id["clonedControlLedgerRejected"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["clonedControlLedgerRejected"]["findings"]], ["unaccountedCostSource"])
            self.assertEqual(by_id["unquantifiedBudgetRejected"]["verdict"], "rejected")
            self.assertIn("unquantifiedBudget", [f["type"] for f in by_id["unquantifiedBudgetRejected"]["findings"]])

            # Codex R2 P2-3: `compare` must flag provenance & usage differences even when verdicts agree!
            s_cmp_a = copy.deepcopy(spec)
            s_cmp_a["auditor"] = "CmpA"
            s_cmp_a["claims"] = [copy.deepcopy(spec["claims"][1])]
            s_cmp_b = copy.deepcopy(s_cmp_a)
            s_cmp_b["auditor"] = "CmpB"
            s_cmp_b["claims"][0]["provenance"] = "reviewerStressTest"
            s_cmp_b["claims"][0]["method_usage"][0]["unit"] = "gpu_hours"
            s_cmp_b["claims"][0]["control_usage"][0]["unit"] = "gpu_hours"
            pa, pb = Path(tmp) / "ca.json", Path(tmp) / "cb.json"
            pa.write_text(json.dumps(s_cmp_a), encoding="utf-8")
            pb.write_text(json.dumps(s_cmp_b), encoding="utf-8")
            out_cmp = Path(tmp) / "cmp_v23"
            rc_cmp = cli_main(["compare", "--doc", str(cost_doc_path), "--spec", str(pa), "--spec", str(pb), "--out", str(out_cmp)])
            self.assertEqual(rc_cmp, 0)
            comp = json.loads((out_cmp / "comparison.json").read_text(encoding="utf-8"))
            row = comp["claim_comparison"][0]
            self.assertTrue(row["verdicts_agree"])
            self.assertFalse(row["same_provenance"])
            self.assertFalse(row["same_usage"])
            cmp_md = (out_cmp / "comparison.md").read_text(encoding="utf-8")
            self.assertIn("provenance/usage differs", cmp_md)

    def test_codex_27315_budget_attribution_grouped_int_and_triple_counting(self) -> None:
        """Codex #27315 exact counterexamples:
        1. `500` MUST NOT match inside `1,500` (`ungrounded_usage_amount`).
        2. Method citing a quote about control (`The control used 500 GPU-hours.`) MUST NOT pass
           (blocked by `duplicate_usage_quote_span` when reused, and by Lean
           `unverifiedUsageAttribution(contradicted)` even when control cites another quote).
        3. Repeating the control's 500 entry 3x to equal 1,500 MUST NOT pass (`duplicate_usage_receipt`
           and `duplicate_usage_quote_span` even with 3 different receipt IDs or trimmed substrings).
        4. Ambiguous free-text quote (no arm attribution) MUST report unverified attribution
           (`unverifiedUsageAttribution(unverified)`), NEVER `admissible`.
        5. Wrong unit (`500 seconds` claimed as `GPU-hours`) MUST fail grounding (`ungrounded_usage_unit`).
        """
        doc_text = (
            "Budget Verification Benchmark.\n"
            "TXN-M1: The method used 1,500 GPU-hours.\n"
            "TXN-C1: The control used 500 GPU-hours.\n"
            "TXN-B1: The baseline used 500 GPU-hours in a separate replication.\n"
            "An anonymous log records 500 GPU-hours billed on Tuesday.\n"
            "Another anonymous log records 500 GPU-hours billed on Wednesday.\n"
            "The method ran for 500 seconds during warmup.\n"
        )
        q_hdr = "Budget Verification Benchmark."
        q_m1500 = "TXN-M1: The method used 1,500 GPU-hours."
        q_c500 = "TXN-C1: The control used 500 GPU-hours."
        q_b500 = "TXN-B1: The baseline used 500 GPU-hours in a separate replication."
        q_anon1 = "An anonymous log records 500 GPU-hours billed on Tuesday."
        q_anon2 = "Another anonymous log records 500 GPU-hours billed on Wednesday."
        q_sec = "The method ran for 500 seconds during warmup."

        def make_base_spec(auditor: str, m_usage: list[dict], c_usage: list[dict]) -> dict:
            return {
                "schema_version": "epistemic-ledger/v2.3",
                "auditor": auditor,
                "paper_title": "Codex 27315 Counterexamples",
                "nodes": ["accountA", "accountB", "methodRun", "controlRun", "costLedger", "evalNode"],
                "tags": ["resourceCost"],
                "sources": [
                    {"node": "accountA", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_m1500},
                    {"node": "accountB", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_c500},
                ],
                "ops": [
                    {"name": "run_method", "inputs": ["accountA"], "output": "methodRun", "kind": "transform", "introduces": [], "quote": q_m1500},
                    {"name": "run_control", "inputs": ["accountB"], "output": "controlRun", "kind": "transform", "introduces": [], "quote": q_c500},
                    {"name": "meter_all", "inputs": ["accountA", "accountB"], "output": "costLedger", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "eval_both", "inputs": ["methodRun", "controlRun", "costLedger"], "output": "evalNode", "kind": "transform", "introduces": [], "quote": q_hdr},
                ],
                "claims": [
                    {
                        "id": "budgetClaim",
                        "statement": "Method and control have matched GPU-hour budgets.",
                        "quote": q_hdr,
                        "provenance": "authorClaimed",
                        "kind": "effectivenessClaim",
                        "method_node": "methodRun",
                        "evaluation_node": "evalNode",
                        "control_node": "controlRun",
                        "cost_ledger_node": "costLedger",
                        "cost_tag": "resourceCost",
                        "method_usage": m_usage,
                        "control_usage": c_usage,
                    }
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            doc_path = Path(tmp) / "codex_27315.md"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            # 0. Honest 1500 vs 500 -> rejected: unmatchedControlBudget
            s_honest = make_base_spec(
                "HonestAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1500, "quote": q_m1500}],
                [{"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500}],
            )
            p0 = Path(tmp) / "honest.json"
            p0.write_text(json.dumps(s_honest), encoding="utf-8")
            rc0 = cli_main(["run", "--doc", str(doc_path), "--spec", str(p0), "--out", str(Path(tmp) / "o0")])
            self.assertEqual(rc0, 0)
            rep0 = json.loads((Path(tmp) / "o0" / "HonestAuditor_report.json").read_text(encoding="utf-8"))
            self.assertEqual(rep0["lean_verification"]["claims"][0]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in rep0["lean_verification"]["claims"][0]["findings"]], ["unmatchedControlBudget"])

            # 1. Bug 1: `500` inside `1,500` MUST fail grounding!
            s_bug1 = make_base_spec(
                "Bug1Auditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_m1500}],
                [{"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500}],
            )
            errs1, _ = validate_spec(s_bug1, doc=doc)
            self.assertTrue(any(e.code == "ungrounded_usage_amount" for e in errs1))

            # 2a. Bug 2 (shared quote): method steals control's exact quote -> duplicate_usage_quote_span!
            s_bug2a = make_base_spec(
                "Bug2aAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500}],
                [{"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500}],
            )
            errs2a, _ = validate_spec(s_bug2a, doc=doc)
            self.assertTrue(any(e.code == "duplicate_usage_quote_span" for e in errs2a))

            # 2b. Bug 2 (distinct quotes): method cites control quote while control cites baseline quote -> Lean rejects as contradicted attribution!
            s_bug2b = make_base_spec(
                "Bug2bAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500}],
                [{"arm": "controlRun", "source": "accountB", "receipt": "TXN-B1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_b500}],
            )
            p2b = Path(tmp) / "bug2b.json"
            p2b.write_text(json.dumps(s_bug2b), encoding="utf-8")
            rc2b = cli_main(["run", "--doc", str(doc_path), "--spec", str(p2b), "--out", str(Path(tmp) / "o2b")])
            self.assertEqual(rc2b, 0)
            rep2b = json.loads((Path(tmp) / "o2b" / "Bug2bAuditor_report.json").read_text(encoding="utf-8"))
            cl2b = rep2b["lean_verification"]["claims"][0]
            self.assertEqual(cl2b["verdict"], "rejected")
            self.assertEqual(cl2b["findings"][0]["type"], "unverifiedUsageAttribution")
            self.assertEqual(cl2b["findings"][0]["status"], "contradicted")

            # 3a. Bug 3 (same receipt x3) -> duplicate_usage_receipt + duplicate_usage_quote_span!
            s_bug3a = make_base_spec(
                "Bug3aAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1500, "quote": q_m1500}],
                [
                    {"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500},
                    {"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500},
                    {"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500},
                ],
            )
            errs3a, _ = validate_spec(s_bug3a, doc=doc)
            self.assertTrue(any(e.code == "duplicate_usage_receipt" for e in errs3a))
            self.assertTrue(any(e.code == "duplicate_usage_quote_span" for e in errs3a))

            # 3b. Bug 3 (3 fake distinct receipts + trimmed substrings of the same sentence) -> duplicate_usage_quote_span!
            s_bug3b = make_base_spec(
                "Bug3bAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1500, "quote": q_m1500}],
                [
                    {"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": "TXN-C1: The control used 500 GPU-hours."},
                    {"arm": "controlRun", "source": "accountB", "receipt": "TXN-C2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": "The control used 500 GPU-hours."},
                    {"arm": "controlRun", "source": "accountB", "receipt": "TXN-C3", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": "used 500 GPU-hours."},
                ],
            )
            errs3b, _ = validate_spec(s_bug3b, doc=doc)
            self.assertTrue(any(e.code == "duplicate_usage_quote_span" for e in errs3b))

            # 4. Unattributed free-text quotes -> Lean reports unverifiedUsageAttribution(unverifiedProse), NEVER admissible!
            s_unv = make_base_spec(
                "UnverifiedAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "m1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_anon1}],
                [{"arm": "controlRun", "source": "accountB", "receipt": "c1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_anon2}],
            )
            p_unv = Path(tmp) / "unv.json"
            p_unv.write_text(json.dumps(s_unv), encoding="utf-8")
            rc_unv = cli_main(["run", "--doc", str(doc_path), "--spec", str(p_unv), "--out", str(Path(tmp) / "o_unv")])
            self.assertEqual(rc_unv, 0)
            rep_unv = json.loads((Path(tmp) / "o_unv" / "UnverifiedAuditor_report.json").read_text(encoding="utf-8"))
            cl_unv = rep_unv["lean_verification"]["claims"][0]
            self.assertEqual(cl_unv["verdict"], "rejected")
            self.assertTrue(all(f["type"] == "unverifiedUsageAttribution" and f["status"] == "unverifiedProse" for f in cl_unv["findings"]))
            md_unv = (Path(tmp) / "o_unv" / "UnverifiedAuditor_report.md").read_text(encoding="utf-8")
            self.assertIn("Unverified Prose Budget", md_unv)
            self.assertIn("Declared figures sum to equal totals, but actual budget parity is **UNVERIFIED**", md_unv)

            # 5. Wrong unit (`500 seconds` claimed as `GPU-hours`) -> ungrounded_usage_unit!
            s_unit = make_base_spec(
                "WrongUnitAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_sec}],
                [{"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500}],
            )
            errs_u, _ = validate_spec(s_unit, doc=doc)
            self.assertTrue(any(e.code == "ungrounded_usage_unit" for e in errs_u))

    def test_codex_27317_sliced_number_requested_quantity_and_prose_restatements(self) -> None:
        """Codex #27317 exact counterexamples:
        1. Quote sliced mid-number (`500 GPU-hours were charged to the method under TXN-M1.`
           sliced out of `1,500 GPU-hours were charged to the method under TXN-M1.`) MUST fail
           grounding (`truncated_numeric_quote`).
        2. `The method requested 500 GPU-hours before the experiment.` claimed as actual spend
           MUST be rejected (`nonActualUsageQuantity(requestedOrAllocated)` + `contradicted`).
        3. Three disjoint prose sentences mentioning the same control 500 GPU-hours (including
           `as previously reported` and `is restated here`), OR three clean prose mentions with
           auditor-invented IDs (`c1`, `c2`, `c3`), MUST NEVER certify `admissible`.
        """
        doc_text = (
            "Codex 27317 Counterexample Study.\n"
            "1,500 GPU-hours were charged to the method under TXN-M1.\n"
            "TXN-REQ1: The method requested 500 GPU-hours before the experiment.\n"
            "TXN-C1: The control was charged 500 GPU-hours.\n"
            "In Section 2, the control used 500 GPU-hours.\n"
            "In Section 4, as previously reported, the control used 500 GPU-hours.\n"
            "In Appendix A, the control total of 500 GPU-hours is restated here.\n"
            "In Section 5, the control spent 500 GPU-hours.\n"
            "In Section 6, the control consumed 500 GPU-hours.\n"
        )
        q_hdr = "Codex 27317 Counterexample Study."
        q_m1500_full = "1,500 GPU-hours were charged to the method under TXN-M1."
        q_m500_sliced = "500 GPU-hours were charged to the method under TXN-M1."
        q_req = "TXN-REQ1: The method requested 500 GPU-hours before the experiment."
        q_c500_txn = "TXN-C1: The control was charged 500 GPU-hours."
        q_prose1 = "In Section 2, the control used 500 GPU-hours."
        q_prose_prev = "In Section 4, as previously reported, the control used 500 GPU-hours."
        q_prose_restated = "In Appendix A, the control total of 500 GPU-hours is restated here."
        q_prose2 = "In Section 5, the control spent 500 GPU-hours."
        q_prose3 = "In Section 6, the control consumed 500 GPU-hours."

        def make_spec(auditor: str, m_usage: list[dict], c_usage: list[dict]) -> dict:
            return {
                "schema_version": "epistemic-ledger/v2.3",
                "auditor": auditor,
                "paper_title": "Codex 27317",
                "nodes": ["accountA", "accountB", "methodRun", "controlRun", "costLedger", "evalNode"],
                "tags": ["resourceCost"],
                "sources": [
                    {"node": "accountA", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_m1500_full},
                    {"node": "accountB", "origin": "setByExperimenter", "carries": ["resourceCost"], "quote": q_c500_txn},
                ],
                "ops": [
                    {"name": "run_m", "inputs": ["accountA"], "output": "methodRun", "kind": "transform", "introduces": [], "quote": q_m1500_full},
                    {"name": "run_c", "inputs": ["accountB"], "output": "controlRun", "kind": "transform", "introduces": [], "quote": q_c500_txn},
                    {"name": "bill", "inputs": ["accountA", "accountB"], "output": "costLedger", "kind": "transform", "introduces": [], "quote": q_hdr},
                    {"name": "eval", "inputs": ["methodRun", "controlRun", "costLedger"], "output": "evalNode", "kind": "transform", "introduces": [], "quote": q_hdr},
                ],
                "claims": [
                    {
                        "id": "claimBudget",
                        "statement": "Method and control spent equal GPU-hours.",
                        "quote": q_hdr,
                        "provenance": "authorClaimed",
                        "kind": "effectivenessClaim",
                        "method_node": "methodRun",
                        "evaluation_node": "evalNode",
                        "control_node": "controlRun",
                        "cost_ledger_node": "costLedger",
                        "cost_tag": "resourceCost",
                        "method_usage": m_usage,
                        "control_usage": c_usage,
                    }
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            doc_path = Path(tmp) / "codex_27317.md"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            # Attack 1: Sliced quote `500 GPU-hours...` from `1,500 GPU-hours...` -> truncated_numeric_quote!
            s1 = make_spec(
                "SlicedNumAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_m500_sliced}],
                [{"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500_txn}],
            )
            errs1, _ = validate_spec(s1, doc=doc)
            self.assertTrue(any(e.code == "truncated_numeric_quote" for e in errs1))

            # Attack 2: Requested quota (`requested 500 GPU-hours`) claimed as actual spend -> rejected!
            s2 = make_spec(
                "RequestedAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-REQ1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quantity_kind": "actualSpend", "quote": q_req}],
                [{"arm": "controlRun", "source": "accountB", "receipt": "TXN-C1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quantity_kind": "actualSpend", "quote": q_c500_txn}],
            )
            p2 = Path(tmp) / "req.json"
            p2.write_text(json.dumps(s2), encoding="utf-8")
            rc2 = cli_main(["run", "--doc", str(doc_path), "--spec", str(p2), "--out", str(Path(tmp) / "o2")])
            self.assertEqual(rc2, 0)
            rep2 = json.loads((Path(tmp) / "o2" / "RequestedAuditor_report.json").read_text(encoding="utf-8"))
            cl2 = rep2["lean_verification"]["claims"][0]
            self.assertEqual(cl2["verdict"], "rejected")
            ftypes2 = {f["type"] for f in cl2["findings"]}
            self.assertIn("nonActualUsageQuantity", ftypes2)
            self.assertIn("unverifiedUsageAttribution", ftypes2)

            # Attack 3a: 3 disjoint prose mentions with restatement cues ("as previously reported", "is restated here") -> rejected!
            s3a = make_spec(
                "RestatedAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1500, "quote": q_m1500_full}],
                [
                    {"arm": "controlRun", "source": "accountB", "receipt": "c1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_prose1},
                    {"arm": "controlRun", "source": "accountB", "receipt": "c2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_prose_prev},
                    {"arm": "controlRun", "source": "accountB", "receipt": "c3", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_prose_restated},
                ],
            )
            p3a = Path(tmp) / "restated.json"
            p3a.write_text(json.dumps(s3a), encoding="utf-8")
            rc3a = cli_main(["run", "--doc", str(doc_path), "--spec", str(p3a), "--out", str(Path(tmp) / "o3a")])
            self.assertEqual(rc3a, 0)
            rep3a = json.loads((Path(tmp) / "o3a" / "RestatedAuditor_report.json").read_text(encoding="utf-8"))
            cl3a = rep3a["lean_verification"]["claims"][0]
            self.assertEqual(cl3a["verdict"], "rejected")
            statuses3a = [f["status"] for f in cl3a["findings"] if f["type"] == "unverifiedUsageAttribution"]
            self.assertIn("contradicted", statuses3a)
            self.assertIn("unverifiedProse", statuses3a)

            # Attack 3b: 3 clean disjoint prose mentions WITHOUT restatement cues, auditor-invented IDs -> STILL unverifiedProse (never admissible)!
            s3b = make_spec(
                "ProseOnlyAuditor",
                [{"arm": "methodRun", "source": "accountA", "receipt": "TXN-M1", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 1500, "quote": q_m1500_full}],
                [
                    {"arm": "controlRun", "source": "accountB", "receipt": "Section 2", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_prose1},
                    {"arm": "controlRun", "source": "accountB", "receipt": "Section 5", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_prose2},
                    {"arm": "controlRun", "source": "accountB", "receipt": "Section 6", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_prose3},
                ],
            )
            p3b = Path(tmp) / "prose3.json"
            p3b.write_text(json.dumps(s3b), encoding="utf-8")
            rc3b = cli_main(["run", "--doc", str(doc_path), "--spec", str(p3b), "--out", str(Path(tmp) / "o3b")])
            self.assertEqual(rc3b, 0)
            rep3b = json.loads((Path(tmp) / "o3b" / "ProseOnlyAuditor_report.json").read_text(encoding="utf-8"))
            cl3b = rep3b["lean_verification"]["claims"][0]
            self.assertEqual(cl3b["verdict"], "rejected")
            self.assertTrue(all(f["type"] == "unverifiedUsageAttribution" and f["status"] == "unverifiedProse" for f in cl3b["findings"]))
            md3b = (Path(tmp) / "o3b" / "ProseOnlyAuditor_report.md").read_text(encoding="utf-8")
            self.assertIn("Declared figures sum to equal totals, but actual budget parity is **UNVERIFIED**", md3b)


if __name__ == "__main__":
    unittest.main()
