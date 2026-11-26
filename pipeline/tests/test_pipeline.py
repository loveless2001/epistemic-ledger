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
            self.assertEqual(by_id["claimA_clean_measured"].verdict, "unestablished")
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
            ftypes = [f["type"] for f in by_id["noControlNoLedgerUnestablished"]["findings"]]
            self.assertIn("missingCostAccounting", ftypes)
            self.assertIn("missingMatchedControl", ftypes)

            # `compare` flags provenance & nature differences even when verdicts agree!
            s_cmp_a = copy.deepcopy(spec)
            s_cmp_a["auditor"] = "CmpA"
            s_cmp_a["claims"] = [copy.deepcopy(spec["claims"][1])]
            s_cmp_b = copy.deepcopy(s_cmp_a)
            s_cmp_b["auditor"] = "CmpB"
            s_cmp_b["claims"][0]["provenance"] = "reviewerStressTest"
            s_cmp_b["claims"][0]["quantitative_kind"] = "threshold"
            pa, pb = Path(tmp) / "ca.json", Path(tmp) / "cb.json"
            pa.write_text(json.dumps(s_cmp_a), encoding="utf-8")
            pb.write_text(json.dumps(s_cmp_b), encoding="utf-8")
            out_cmp = Path(tmp) / "cmp_v24"
            rc_cmp = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(pa), "--spec", str(pb), "--out", str(out_cmp)])
            self.assertEqual(rc_cmp, 0)
            comp = json.loads((out_cmp / "comparison.json").read_text(encoding="utf-8"))
            row = comp["claim_comparison"][0]
            self.assertTrue(row["verdicts_agree"])
            self.assertEqual(row["strictest_verdict"], "admissible")
            self.assertFalse(row["same_provenance"])
            self.assertFalse(row["same_nature"])
            cmp_md = (out_cmp / "comparison.md").read_text(encoding="utf-8")
            self.assertIn("provenance/nature differs", cmp_md)

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

            # 6. `compare` propagates `out_of_scope` into comparison.json & comparison.md
            out_cmp_oos = Path(tmp) / "out_cmp_oos"
            self.assertEqual(
                cli_main(["compare", "--doc", str(doc_path), "--spec", str(sp), "--spec", str(sp_legacy), "--out", str(out_cmp_oos)]),
                0,
            )
            comp_oos = json.loads((out_cmp_oos / "comparison.json").read_text(encoding="utf-8"))
            comp_oos_md = (out_cmp_oos / "comparison.md").read_text(encoding="utf-8")
            self.assertTrue(any("without reading or comparing numbers" in s for s in comp_oos["out_of_scope"]))
            self.assertTrue(any("Ignored out-of-scope numeric/accounting fields" in s for s in comp_oos["out_of_scope"]))
            self.assertIn("## Out of Scope", comp_oos_md)
            self.assertIn("Ignored out-of-scope numeric/accounting fields", comp_oos_md)

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
            self.assertIn("admissible (consistent within declared slice)", md)
            self.assertIn("UNESTABLISHED (data/design stops at map edge)", md)
            self.assertIn("OUT OF SCOPE", md)
            self.assertIn("**[Out of Scope]** Normative policy/ethics balancing", md)
            self.assertIn("Explicitly out-of-scope claim(s) (claimNormativeOutOfScope)", md)

            # `compare` aligns all 4 verdict states cleanly
            out_cmp = Path(tmp) / "cmp_out"
            rc_cmp = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(sp_a), "--spec", str(sp_b), "--out", str(out_cmp)])
            self.assertEqual(rc_cmp, 0)
            comp = json.loads((out_cmp / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(len(comp["claim_comparison"]), 4)
            self.assertTrue(all(r["status"] == "AGREE" for r in comp["claim_comparison"]))

    def test_codex_notShown_sole_path_lossy_side_branch_and_claude_span_overlap_compare(self) -> None:
        """Regression tests for Codex `#27358` and Claude `#27361`:
        1. Sole path through `.forget tag .notShown` -> `unestablished` (no false `smuggledStructure`),
           while adding an un-attempted bypass -> `rejected`.
        2. `uniqueRecovery` with `.lossy` ONLY on an unrelated noise branch -> `admissible`;
           missing upstream `SourceNode` access (`unaccessedTargetStructure`) -> `unestablished`.
        3. `compare` aligns claims with minor quote boundary differences (e.g., trailing period
           omitted by Auditor A, included by Auditor B -> `span_overlap`, `AGREE`), while still
           NOT merging two disjoint sentences.
        """
        doc = ingest_document(str(SAMPLE_DOC))
        q_a_with_dot = "Under Regime A, 3D geometry arises in the learned representation without 3D prediction targets in the training loss."
        q_a_no_dot = q_a_with_dot.rstrip(".")
        q_b = "Under Regime B, 3D geometry emerges purely from 2D relational learning without 3D prediction targets."
        q_d = "The encoder uniquely recovers the true underlying 3D world state from a single monocular photograph."

        spec_a = {
            "schema_version": "epistemic-ledger/v2.3",
            "auditor": "SpanA",
            "paper_title": "Codex & Claude Regression",
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
                    "quote": q_a_no_dot,  # intentionally omits trailing period
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
        spec_b = copy.deepcopy(spec_a)
        spec_b["auditor"] = "SpanB"
        spec_b["claims"][0]["quote"] = q_a_with_dot  # includes trailing period!

        self.assertEqual(validate_spec(spec_a, doc=doc)[0], [])
        self.assertEqual(validate_spec(spec_b, doc=doc)[0], [])

        with tempfile.TemporaryDirectory() as tmp:
            pa, pb = Path(tmp) / "a.json", Path(tmp) / "b.json"
            pa.write_text(json.dumps(spec_a), encoding="utf-8")
            pb.write_text(json.dumps(spec_b), encoding="utf-8")
            out = Path(tmp) / "cmp"
            rc = cli_main(["compare", "--doc", str(SAMPLE_DOC), "--spec", str(pa), "--spec", str(pb), "--out", str(out)])
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

            comp = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(len(comp["claim_comparison"]), 4)
            self.assertTrue(all(r["status"] == "AGREE" for r in comp["claim_comparison"]))
            by_cid = {r["by_auditor"]["SpanA"]["claim_id"]: r for r in comp["claim_comparison"]}
            self.assertEqual(by_cid["soleNotShown"]["quote_match_mode"], "span_overlap")
            self.assertGreater(by_cid["soleNotShown"]["min_span_iou"], 0.95)
            self.assertEqual(by_cid["notShownPlusBypass"]["quote_match_mode"], "exact")
            comp_md = (out / "comparison.md").read_text(encoding="utf-8")
            self.assertIn("pairwise min IoU=", comp_md)

    def test_codex_27370_order_independent_compare_unique_recovery_and_rule3_theorem_application(self) -> None:
        """Regression tests for Codex `#27370` + Rule 3 (`theoremApplication`) end-to-end:
        1. Order-independent `compare`: 3-sentence doc where M bridges L and R (`IoU(M,L)=IoU(M,R)>0.5`,
           `IoU(L,R)<=0.5`) yields identical `AMBIGUOUS` (`ambiguous_span_chain`, true pairwise `min_span_iou`)
           under both `[M, L, R]` and `[L, R, M]` `--spec` orderings.
        2. `uniqueRecovery`:
           - `(x, round(x))` with direct lossless path -> `admissible`,
           - sole access through `.forget x .notShown` -> `unestablished` (`failedForgetOnPath`).
        3. Rule 3 (`theoremApplication`):
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

            def make_bridge_spec(aud: str, quote: str) -> dict:
                return {
                    "schema_version": "epistemic-ledger/v2.3",
                    "auditor": aud,
                    "paper_title": "Bridge Order Test",
                    "nodes": ["x", "out"],
                    "tags": ["sig"],
                    "sources": [{"node": "x", "origin": "measured", "carries": ["sig"], "quote": quote}],
                    "ops": [{"name": "pass", "inputs": ["x"], "output": "out", "kind": "transform", "introduces": [], "quote": quote}],
                    "claims": [
                        {
                            "id": "c1",
                            "statement": "Conditional on x.",
                            "quote": quote,
                            "kind": "conditionalFlow",
                            "target": "out",
                            "declared_sources": ["x"],
                        }
                    ],
                }

            pm, pl, pr = base / "m.json", base / "l.json", base / "r.json"
            pm.write_text(json.dumps(make_bridge_spec("AudM", q_m)), encoding="utf-8")
            pl.write_text(json.dumps(make_bridge_spec("AudL", q_l)), encoding="utf-8")
            pr.write_text(json.dumps(make_bridge_spec("AudR", q_r)), encoding="utf-8")

            out_mlr, out_lrm = base / "cmp_mlr", base / "cmp_lrm"
            self.assertEqual(
                cli_main(["compare", "--doc", str(doc_path), "--spec", str(pm), "--spec", str(pl), "--spec", str(pr), "--out", str(out_mlr)]),
                0,
            )
            self.assertEqual(
                cli_main(["compare", "--doc", str(doc_path), "--spec", str(pl), "--spec", str(pr), "--spec", str(pm), "--out", str(out_lrm)]),
                0,
            )
            c_mlr = json.loads((out_mlr / "comparison.json").read_text(encoding="utf-8"))["claim_comparison"]
            c_lrm = json.loads((out_lrm / "comparison.json").read_text(encoding="utf-8"))["claim_comparison"]
            self.assertEqual(len(c_mlr), 1)
            self.assertEqual(len(c_lrm), 1)
            for row in (c_mlr[0], c_lrm[0]):
                self.assertEqual(row["status"], "AMBIGUOUS")
                self.assertFalse(row["verdicts_agree"])
                self.assertEqual(row["quote_match_mode"], "ambiguous_span_chain")
                self.assertLess(row["min_span_iou"], 0.4)
            self.assertEqual(c_mlr[0]["char_offset"], c_lrm[0]["char_offset"])
            self.assertEqual(c_mlr[0]["min_span_iou"], c_lrm[0]["min_span_iou"])
            self.assertIn("ambiguous span chain", (out_mlr / "comparison.md").read_text(encoding="utf-8"))

            # 2 & 3: uniqueRecovery `(x, round(x))` + `.notShown` access + Rule 3 (`theoremApplication`)
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

            # Prompt check: includes v2.4 nature/quantitative_kind/decomposition/hedging rules
            # AND never leaks graded evaluation sentences into the prompt instructions (Claude #27435)
            from pipeline.report import build_extraction_prompt

            prompt_txt = build_extraction_prompt(ep_doc, auditor_name="BlindPromptCheck")
            prompt_header = prompt_txt.split("--- BEGIN DOCUMENT ---", 1)[0]
            for needle in (
                "epistemic-ledger/v2.4",
                "quantitative_kind",
                "specificValue",
                "derivedComparison",
                "Decompose compound",
                "hedged",
                "hedge_quote",
                "display-only",
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

            # Hedged schema negative controls
            bad_h1 = copy.deepcopy(spec_ep_a)
            del bad_h1["claims"][2]["hedge_quote"]
            self.assertTrue(any(e.code == "missing_hedge_quote" for e in validate_spec(bad_h1, doc=ep_doc)[0]))
            bad_h2 = copy.deepcopy(spec_ep_a)
            bad_h2["claims"][1]["hedge_quote"] = "Within this task, spacetime geometry"
            self.assertTrue(any(e.code == "unexpected_hedge_quote" for e in validate_spec(bad_h2, doc=ep_doc)[0]))
            bad_h3 = copy.deepcopy(spec_ep_a)
            bad_h3["claims"][2]["hedge_quote"] = "Hallucinated hedge phrase not in text"
            self.assertTrue(any(e.code == "ungrounded_quote" for e in validate_spec(bad_h3, doc=ep_doc)[0]))
            # Codex #27436 Part C: hedge_quote from clause 2 attached to clause 1 MUST fail (`hedge_quote_outside_claim`)!
            bad_h4 = copy.deepcopy(spec_ep_a)
            bad_h4["claims"][2]["quote"] = "Within this task, spacetime geometry is obtained from an agent's successful predictions and actions"
            bad_h4["claims"][2]["hedge_quote"] = "providing a first step toward emergent spacetime"
            self.assertTrue(any(e.code == "hedge_quote_outside_claim" for e in validate_spec(bad_h4, doc=ep_doc)[0]))

            # Auditor B:
            # - omits extra unchecked bet on Q4 -> `admissible` (DISAGREE: A=unestablished, B=admissible -> Strictest=unestablished)
            # - picks a DIFFERENT `hedge_quote` on Q7 -> `compare` flags `hedge_quote differs` and renders both quotes!
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
                if cl["id"] == "spacetimeQ7Hedged":
                    cl["hedge_quote"] = "Within this task, spacetime geometry"

            sp_ep_full = base / "ep_full.json"
            sp_ep_full.write_text(json.dumps(spec_ep_a), encoding="utf-8")
            out_ep = base / "out_ep"
            self.assertEqual(cli_main(["run", "--doc", str(ep_doc_path), "--spec", str(sp_ep_full), "--out", str(out_ep)]), 0)
            rep_ep = json.loads((out_ep / "EpistemicA_report.json").read_text(encoding="utf-8"))
            md_ep = (out_ep / "EpistemicA_report.md").read_text(encoding="utf-8")
            ep_by_id = {c["id"]: c for c in rep_ep["lean_verification"]["claims"]}
            self.assertEqual(ep_by_id["barontiniF2UnverifiedForget"]["verdict"], "rejected")
            self.assertEqual(ep_by_id["spacetimeQ6Unhedged"]["verdict"], "rejected")
            # Amended Part C (#27432): hedge marker is display-only and does NOT alter verdict
            self.assertEqual(ep_by_id["spacetimeQ7Hedged"]["verdict"], "rejected")
            self.assertTrue(ep_by_id["spacetimeQ7Hedged"]["hedged"])
            self.assertEqual(ep_by_id["spacetimeQ7Hedged"]["hedge_quote"], "providing a first step toward emergent spacetime")
            self.assertEqual(ep_by_id["cleanHedgedEmergence"]["verdict"], "admissible")
            self.assertEqual(ep_by_id["genuineConditional"]["verdict"], "admissible")
            self.assertEqual(ep_by_id["barontiniQ4Setting"]["verdict"], "unestablished")
            self.assertEqual(ep_by_id["jepaNeedNecessityHyp"]["verdict"], "admissible")
            self.assertEqual(ep_by_id["jepaNeedNecessityHyp"]["declared_bet_count"], 1)
            self.assertEqual(ep_by_id["jepaRatio42OutOfScope"]["verdict"], "outOfScope")
            self.assertIn("Hedge quote:", md_ep)

            sp_ep_a = base / "ep_a.json"
            sp_ep_b = base / "ep_b.json"
            sp_ep_a.write_text(json.dumps(spec_ep_a_cmp), encoding="utf-8")
            sp_ep_b.write_text(json.dumps(spec_ep_b), encoding="utf-8")
            out_ep_cmp = base / "out_ep_cmp"
            self.assertEqual(
                cli_main(["compare", "--doc", str(ep_doc_path), "--spec", str(sp_ep_a), "--spec", str(sp_ep_b), "--out", str(out_ep_cmp)]),
                0,
            )
            comp_ep = json.loads((out_ep_cmp / "comparison.json").read_text(encoding="utf-8"))
            comp_ep_md = (out_ep_cmp / "comparison.md").read_text(encoding="utf-8")
            self.assertIn("| Strictest |", comp_ep_md)
            rows_by_cid = {r["by_auditor"]["EpistemicA"]["claim_id"]: r for r in comp_ep["claim_comparison"]}
            self.assertEqual(rows_by_cid["barontiniQ4Setting"]["status"], "DISAGREE")
            self.assertEqual(rows_by_cid["barontiniQ4Setting"]["strictest_verdict"], "unestablished")
            self.assertEqual(rows_by_cid["spacetimeQ6Unhedged"]["strictest_verdict"], "rejected")
            self.assertEqual(rows_by_cid["spacetimeQ7Hedged"]["strictest_verdict"], "rejected")
            self.assertFalse(rows_by_cid["spacetimeQ7Hedged"]["same_hedge_quote"])
            self.assertIn("hedge_quote differs", comp_ep_md)
            self.assertIn('hedged="providing a first step toward emergent spacetime"', comp_ep_md)
            self.assertIn('hedged="Within this task, spacetime geometry"', comp_ep_md)
            self.assertEqual(rows_by_cid["genuineConditional"]["strictest_verdict"], "admissible")
            # Codex #27436 Part D: unmatched single-auditor claim MUST leave `strictest_verdict` empty (`None` / `*—*`)!
            self.assertEqual(rows_by_cid["jepaNeedNecessityHyp"]["status"], "UNVERIFIED_OR_UNMATCHED")
            self.assertIsNone(rows_by_cid["jepaNeedNecessityHyp"]["strictest_verdict"])
            self.assertIn("| *—* |", comp_ep_md)

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

            self.assertIn("rests on 2 declared bets", md_dl)
            self.assertIn("declared in claim sentence", md_dl)
            self.assertIn("declared in document body (offset @", md_dl)


if __name__ == "__main__":
    unittest.main()
