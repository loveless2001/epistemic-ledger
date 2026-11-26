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
        doc = ingest_document(str(SAMPLE_DOC))
        q = "Under Regime A, 3D geometry arises in the learned representation without 3D prediction targets in the training loss."
        q_num = "We investigate whether 3D spatial structure emerges in neural representations trained without 3D prediction targets across two experimental regimes."
        spec = {
            "schema_version": "epistemic-ledger/v2.3",
            "auditor": "CostAuditorV23",
            "paper_title": "Tier-2 v2.3 Cost & Control Test",
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
                "evalUnquantified",
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
                {"name": "e_unq", "inputs": ["methodCluster", "ctrlCluster", "meterCluster"], "output": "evalUnquantified", "kind": "transform", "introduces": [], "quote": q},
                {"name": "e_cloned_l", "inputs": ["methodCluster", "ctrlCluster", "clonedCtrlLedger"], "output": "evalClonedLedger", "kind": "transform", "introduces": [], "quote": q},
            ],
            "claims": [
                {
                    "id": "unevenSameCluster",
                    "statement": "3 vs 2 units on same cluster.",
                    "quote": q_num,
                    "provenance": "reviewerStressTest",
                    "kind": "effectivenessClaim",
                    "method_node": "methodCluster",
                    "evaluation_node": "evalUneven",
                    "control_node": "ctrlCluster",
                    "cost_ledger_node": "meterCluster",
                    "cost_tag": "resourceCost",
                    "method_usage": [{"source": "sharedCluster", "dimension": "resourceCost", "unit": "regimes", "amount": 3, "quote": q}],
                    "control_usage": [{"source": "sharedCluster", "dimension": "resourceCost", "unit": "regimes", "amount": 2, "quote": "purely 2D patch-matching loss objective"}],
                },
                {
                    "id": "equalSeparateAccountsPostHoc",
                    "statement": "Two separate accounts both spending 3 units, post-hoc metered.",
                    "quote": q,
                    "provenance": "authorClaimed",
                    "kind": "effectivenessClaim",
                    "method_node": "methodAccA",
                    "evaluation_node": "evalEqualSep",
                    "control_node": "ctrlAccB",
                    "cost_ledger_node": "postHocMeter",
                    "cost_tag": "resourceCost",
                    "method_usage": [{"source": "accountA", "dimension": "resourceCost", "unit": "units", "amount": 3, "quote": q}],
                    "control_usage": [{"source": "accountB", "dimension": "resourceCost", "unit": "units", "amount": 3, "quote": q}],
                },
                {
                    "id": "forgetCannotEraseSpentHours",
                    "statement": "Forget .shown cannot erase humanHours spent during run.",
                    "quote": q,
                    "kind": "effectivenessClaim",
                    "method_node": "methodForgetHours",
                    "evaluation_node": "evalForgotten",
                    "control_node": "ctrlCluster",
                    "cost_ledger_node": "meterCluster",
                    "cost_tag": "resourceCost",
                    "method_usage": [{"source": "sharedCluster", "dimension": "resourceCost", "unit": "units", "amount": 3, "quote": q}],
                    "control_usage": [{"source": "sharedCluster", "dimension": "resourceCost", "unit": "units", "amount": 3, "quote": q}],
                },
                {
                    "id": "dependentControlRejected",
                    "statement": "Control cloned from method output.",
                    "quote": q,
                    "kind": "effectivenessClaim",
                    "method_node": "methodCluster",
                    "evaluation_node": "evalDependent",
                    "control_node": "clonedCtrl",
                    "cost_ledger_node": "meterCluster",
                    "cost_tag": "resourceCost",
                    "method_usage": [{"source": "sharedCluster", "dimension": "resourceCost", "unit": "units", "amount": 3, "quote": q}],
                    "control_usage": [{"source": "sharedCluster", "dimension": "resourceCost", "unit": "units", "amount": 3, "quote": q}],
                },
                {
                    "id": "clonedControlLedgerRejected",
                    "statement": "Fake ledger cloned solely from control output.",
                    "quote": q,
                    "kind": "effectivenessClaim",
                    "method_node": "methodCluster",
                    "evaluation_node": "evalClonedLedger",
                    "control_node": "ctrlCluster",
                    "cost_ledger_node": "clonedCtrlLedger",
                    "cost_tag": "resourceCost",
                    "method_usage": [{"source": "sharedCluster", "dimension": "resourceCost", "unit": "units", "amount": 3, "quote": q}],
                    "control_usage": [{"source": "sharedCluster", "dimension": "resourceCost", "unit": "units", "amount": 3, "quote": q}],
                },
                {
                    "id": "unquantifiedBudgetRejected",
                    "statement": "Missing usage numbers cannot certify matched budget.",
                    "quote": q,
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

        with tempfile.TemporaryDirectory() as tmp:
            sp = Path(tmp) / "v23.json"
            out = Path(tmp) / "out"
            sp.write_text(json.dumps(spec), encoding="utf-8")
            rc = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(sp), "--out", str(out)])
            self.assertEqual(rc, 0)
            rep = json.loads((out / "CostAuditorV23_report.json").read_text(encoding="utf-8"))
            md = (out / "CostAuditorV23_report.md").read_text(encoding="utf-8")
            self.assertIn("`reviewerStressTest`", md)
            by_id = {c["id"]: c for c in rep["lean_verification"]["claims"]}

            self.assertEqual(by_id["unevenSameCluster"]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in by_id["unevenSameCluster"]["findings"]], ["unmatchedControlBudget"])
            self.assertEqual(by_id["equalSeparateAccountsPostHoc"]["verdict"], "admissible")
            self.assertEqual(by_id["equalSeparateAccountsPostHoc"]["findings"], [])
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
            s_cmp_b["claims"][0]["method_usage"][0]["unit"] = "other_units"
            s_cmp_b["claims"][0]["control_usage"][0]["unit"] = "other_units"
            pa, pb = Path(tmp) / "ca.json", Path(tmp) / "cb.json"
            pa.write_text(json.dumps(s_cmp_a), encoding="utf-8")
            pb.write_text(json.dumps(s_cmp_b), encoding="utf-8")
            out_cmp = Path(tmp) / "cmp_v23"
            rc_cmp = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(pa), "--spec", str(pb), "--out", str(out_cmp)])
            self.assertEqual(rc_cmp, 0)
            comp = json.loads((out_cmp / "comparison.json").read_text(encoding="utf-8"))
            row = comp["claim_comparison"][0]
            self.assertTrue(row["verdicts_agree"])
            self.assertFalse(row["same_provenance"])
            self.assertFalse(row["same_usage"])
            cmp_md = (out_cmp / "comparison.md").read_text(encoding="utf-8")
            self.assertIn("provenance/usage differs", cmp_md)

    def test_numeric_boundary_grounding_and_explicit_out_of_scope_notice(self) -> None:
        """Clean scope boundary:
        1. `500` MUST NOT match inside `1,500` (`ungrounded_usage_amount`).
        2. Slicing `500 GPU-hours...` out of `1,500 GPU-hours...` MUST fail (`truncated_numeric_quote`).
        3. Bookkeeping/accounting semantics (invoices, periods, prose restatements) are explicitly
           reported as OUT OF SCOPE in both JSON and Markdown reports rather than guessed via regex.
        """
        doc_text = (
            "Compute Comparison Study.\n"
            "1,500 GPU-hours were charged to the method.\n"
            "The control used 500 GPU-hours.\n"
        )
        q_hdr = "Compute Comparison Study."
        q_m1500 = "1,500 GPU-hours were charged to the method."
        q_m500_sliced = "500 GPU-hours were charged to the method."
        q_c500 = "The control used 500 GPU-hours."

        def make_spec(m_amt: int, m_quote: str) -> dict:
            return {
                "schema_version": "epistemic-ledger/v2.3",
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
                "claims": [
                    {
                        "id": "budgetCheck",
                        "statement": "Method and control have matched GPU-hour budgets.",
                        "quote": q_hdr,
                        "provenance": "authorClaimed",
                        "kind": "effectivenessClaim",
                        "method_node": "methodRun",
                        "evaluation_node": "evalNode",
                        "control_node": "controlRun",
                        "cost_ledger_node": "ledger",
                        "cost_tag": "resourceCost",
                        "method_usage": [{"source": "accountA", "dimension": "resourceCost", "unit": "GPU-hours", "amount": m_amt, "quote": m_quote}],
                        "control_usage": [{"source": "accountB", "dimension": "resourceCost", "unit": "GPU-hours", "amount": 500, "quote": q_c500}],
                    }
                ],
            }

        with tempfile.TemporaryDirectory() as tmp:
            doc_path = Path(tmp) / "study.md"
            doc_path.write_text(doc_text, encoding="utf-8")
            doc = ingest_document(str(doc_path))

            # 1. `500` inside `1,500` fails grounding
            e1, _ = validate_spec(make_spec(500, q_m1500), doc=doc)
            self.assertTrue(any(e.code == "ungrounded_usage_amount" for e in e1))

            # 2. Sliced quote `500 GPU-hours...` out of `1,500 GPU-hours...` fails grounding
            e2, _ = validate_spec(make_spec(500, q_m500_sliced), doc=doc)
            self.assertTrue(any(e.code == "truncated_numeric_quote" for e in e2))

            # 3. Valid 1500 vs 500 runs cleanly and explicitly reports accounting/bookkeeping as out of scope
            sp = Path(tmp) / "valid.json"
            sp.write_text(json.dumps(make_spec(1500, q_m1500)), encoding="utf-8")
            out = Path(tmp) / "out"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp), "--out", str(out)]), 0)
            rep = json.loads((out / "ScopeAuditor_report.json").read_text(encoding="utf-8"))
            md = (out / "ScopeAuditor_report.md").read_text(encoding="utf-8")
            self.assertEqual(rep["lean_verification"]["claims"][0]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in rep["lean_verification"]["claims"][0]["findings"]], ["unmatchedControlBudget"])
            self.assertTrue(any("out of scope" in s.lower() and "invoice" in s.lower() for s in rep["out_of_scope"]))
            self.assertIn("## Out of Scope", md)
            self.assertIn("Out of scope (accounting/bookkeeping)", md)

            # 4. Codex #27331-1: Markdown MUST render `## Out of Scope` even when usage lists are empty AND on failed grounding reports!
            s_empty_usage = make_spec(1500, q_m1500)
            s_empty_usage["claims"][0]["method_usage"] = []
            s_empty_usage["claims"][0]["control_usage"] = []
            sp_empty = Path(tmp) / "empty_usage.json"
            sp_empty.write_text(json.dumps(s_empty_usage), encoding="utf-8")
            out_empty = Path(tmp) / "out_empty"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_empty), "--out", str(out_empty)]), 0)
            md_empty = (out_empty / "ScopeAuditor_report.md").read_text(encoding="utf-8")
            self.assertIn("## Out of Scope", md_empty)
            self.assertIn("invoice reconciliation", md_empty)

            sp_fail = Path(tmp) / "fail_sliced.json"
            sp_fail.write_text(json.dumps(make_spec(500, q_m500_sliced)), encoding="utf-8")
            out_fail = Path(tmp) / "out_fail"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_fail), "--out", str(out_fail)]), 2)
            md_fail = (out_fail / "ScopeAuditor_report.md").read_text(encoding="utf-8")
            self.assertIn("## Out of Scope", md_fail)
            self.assertIn("invoice reconciliation", md_fail)

            # 5. Codex #27331-2: Known out-of-scope accounting keys (`reconciliations`, `arm`, `receipt`, `charge_event`, `quantity_kind`)
            # MUST NOT abort structural Lean verification, and MUST be reported as ignored/out of scope; unknown keys still fail!
            s_legacy = make_spec(1500, q_m1500)
            s_legacy["claims"][0]["method_usage"][0].update(
                {"arm": "methodRun", "receipt": "TXN-M1", "charge_event": "TXN-M1", "quantity_kind": "actualSpend"}
            )
            s_legacy["claims"][0]["control_usage"][0].update({"arm": "controlRun", "receipt": "JOB-C1"})
            s_legacy["claims"][0]["reconciliations"] = [{"arm": "methodRun", "reconciled_total": 1500}]
            sp_legacy = Path(tmp) / "legacy.json"
            sp_legacy.write_text(json.dumps(s_legacy), encoding="utf-8")
            out_legacy = Path(tmp) / "out_legacy"
            self.assertEqual(cli_main(["run", "--doc", str(doc_path), "--spec", str(sp_legacy), "--out", str(out_legacy)]), 0)
            rep_legacy = json.loads((out_legacy / "ScopeAuditor_report.json").read_text(encoding="utf-8"))
            md_legacy = (out_legacy / "ScopeAuditor_report.md").read_text(encoding="utf-8")
            self.assertEqual(rep_legacy["lean_verification"]["claims"][0]["verdict"], "rejected")
            self.assertEqual([f["type"] for f in rep_legacy["lean_verification"]["claims"][0]["findings"]], ["unmatchedControlBudget"])
            self.assertTrue(any("Ignored out-of-scope accounting/bookkeeping fields" in s and "reconciliations" in s for s in rep_legacy["out_of_scope"]))
            self.assertIn("Ignored out-of-scope accounting/bookkeeping fields", md_legacy)

            s_bogus = copy.deepcopy(s_legacy)
            s_bogus["claims"][0]["bogus_extra"] = 123
            e_bogus, _ = validate_spec(s_bogus, doc=doc)
            self.assertTrue(any(e.code == "unknown_key" for e in e_bogus))

            # 6. Codex #27335: `compare` MUST also propagate `out_of_scope` into comparison.json & comparison.md!
            out_cmp_oos = Path(tmp) / "out_cmp_oos"
            self.assertEqual(
                cli_main(["compare", "--doc", str(doc_path), "--spec", str(sp), "--spec", str(sp_legacy), "--out", str(out_cmp_oos)]),
                0,
            )
            comp_oos = json.loads((out_cmp_oos / "comparison.json").read_text(encoding="utf-8"))
            comp_oos_md = (out_cmp_oos / "comparison.md").read_text(encoding="utf-8")
            self.assertTrue(any("invoice reconciliation" in s for s in comp_oos["out_of_scope"]))
            self.assertTrue(any("Ignored out-of-scope accounting/bookkeeping fields" in s for s in comp_oos["out_of_scope"]))
            self.assertIn("## Out of Scope", comp_oos_md)
            self.assertIn("Ignored out-of-scope accounting/bookkeeping fields", comp_oos_md)


if __name__ == "__main__":
    unittest.main()
