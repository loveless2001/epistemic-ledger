"""Automated unit, integration, and adversarial tests for the Epistemic Ledger pipeline."""

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
            # Claim A: measured RGB (even tagged geometry3D!) + depth only in eval -> ADMISSIBLE
            self.assertEqual(by_id["claimA_clean_measured"]["verdict"], "admissible")
            self.assertEqual(by_id["claimA_clean_measured"]["findings"], [])

            # Claim B: frozen 3D pretrained backbone -> REJECTED by Alarm 2 (authorSuppliedStructure)
            self.assertEqual(by_id["claimB_pretrained_backbone"]["verdict"], "rejected")
            self.assertEqual(
                [f["type"] for f in by_id["claimB_pretrained_backbone"]["findings"]],
                ["authorSuppliedStructure"],
            )

            # Claim C: measured LiDAR depth fed into loss -> REJECTED by Alarm 1 (excludedChannelLeak)
            self.assertEqual(by_id["claimC_depth_in_loss"]["verdict"], "rejected")
            self.assertEqual(
                [f["type"] for f in by_id["claimC_depth_in_loss"]["findings"]],
                ["excludedChannelLeak"],
            )

            # Claim D: lossy monocular projection -> REJECTED by lossyChannelOnPath
            self.assertEqual(by_id["claimD_unique_recovery"]["verdict"], "rejected")
            self.assertEqual(
                [f["type"] for f in by_id["claimD_unique_recovery"]["findings"]],
                ["lossyChannelOnPath"],
            )

    def test_multi_auditor_compare_agrees_despite_measured_rgb_tagging_difference(self) -> None:
        """AuditorA tags measuredRgbFrames with geometry3D; AuditorB leaves it [].
        Under Policy 3, both reach identical Lean-verified verdicts on all 4 claims!"""
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
                self.assertTrue(row["verdicts_agree"], f"Unexpected disagreement on {row['claim_id']}")
            self.assertTrue((out / "comparison.md").is_file())

    def test_adversarial_hallucinated_quote_rejected_before_lean(self) -> None:
        doc = ingest_document(str(SAMPLE_DOC))
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        spec["sources"][0]["quote"] = "this sentence does not appear anywhere in the paper at all"
        errors, _ = validate_spec(spec, doc=doc)
        self.assertTrue(any(e.code == "ungrounded_quote" for e in errors))

        with tempfile.TemporaryDirectory() as tmp:
            bad_spec = Path(tmp) / "bad.json"
            bad_spec.write_text(json.dumps(spec), encoding="utf-8")
            rc = cli_main(["run", "--doc", str(SAMPLE_DOC), "--spec", str(bad_spec), "--out", str(Path(tmp) / "out")])
            self.assertEqual(rc, 2)
            self.assertFalse((Path(tmp) / "out" / "AuditorA_Verified.lean").exists())

    def test_adversarial_short_quote_rejected(self) -> None:
        doc = ingest_document(str(SAMPLE_DOC))
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        spec["sources"][0]["quote"] = "the"
        errors, _ = validate_spec(spec, doc=doc)
        self.assertTrue(any(e.code == "quote_too_short" for e in errors))

    def test_adversarial_lean_injection_and_reserved_keyword_rejected(self) -> None:
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        # 1. Code injection in identifier
        s1 = copy.deepcopy(spec)
        s1["nodes"][0] = "badNode\naxiom evil : False"
        errs1, _ = validate_spec(s1, doc=None)
        self.assertTrue(any(e.code == "invalid_identifier" for e in errs1))

        # 2. Reserved Lean keyword as node name
        s2 = copy.deepcopy(spec)
        s2["nodes"][0] = "theorem"
        errs2, _ = validate_spec(s2, doc=None)
        self.assertTrue(any(e.code == "reserved_keyword" for e in errs2))

        # 3. Unknown top-level key rejected
        s3 = copy.deepcopy(spec)
        s3["sneaky_extra"] = 123
        errs3, _ = validate_spec(s3, doc=None)
        self.assertTrue(any(e.code == "unknown_key" for e in errs3))

    def test_dangling_input_caught_by_lean_through_pipeline(self) -> None:
        doc = ingest_document(str(SAMPLE_DOC))
        spec = json.loads(SPEC_A.read_text(encoding="utf-8"))
        # Remove measuredRgbFrames from sources while leaving it in monocular_camera_projection.inputs
        spec["sources"] = [s for s in spec["sources"] if s["node"] != "measuredRgbFrames"]
        errors, _ = validate_spec(spec, doc=doc)
        self.assertEqual(errors, [])

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

    def test_extract_cli_hook_end_to_end(self) -> None:
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
        errors, _ = validate_spec(spec, doc=doc)
        self.assertEqual(errors, [])

        with tempfile.TemporaryDirectory() as tmp:
            res = run_lean_verification(spec, repo_root=REPO_ROOT, out_lean_path=Path(tmp) / "Escaped.lean")
            by_id = {c.claim_id: c for c in res.claims}
            self.assertEqual(by_id["claimA_clean_measured"].verdict, "admissible")
            self.assertEqual(by_id["claimD_unique_recovery"].verdict, "rejected")
            self.assertEqual(by_id["claimD_unique_recovery"].findings[0]["op"], 'op_"quoted"_\\slash')


if __name__ == "__main__":
    unittest.main()
