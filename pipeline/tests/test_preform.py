import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from pipeline.audit_cli import main as cli_main
from pipeline.ingest import ingest_document
from pipeline.schema import validate_spec


SAMPLE_DOC = (
    "Patients underwent dynamic infrared thermography (DIRT) after a two-minute cold challenge.\n"
    "The optimal global assignment uses the Hungarian algorithm with a composite distance and brightness score.\n"
    "Of 46 CTA perforators, 39 were linked to a thermographic hotspot (sensitivity 84.8%).\n"
)

OTHER_DOC = (
    "A completely different document about marine salinity measurements in the North Atlantic.\n"
    "Measurements were collected by autonomous drifting buoys over a twelve-month period.\n"
)

SAMPLE_GRAPH = {
    "nodes": {
        "SURGEON": {"names": ["Reconstructive Surgeon [actor]"], "role": "actor", "params": {}},
        "COLD_CHALLENGE": {
            "names": ["Standardized Cold Challenge [thermal_protocol]"],
            "role": "process_state",
            "params": {"duration": ["2_min", "other"]},
        },
        "THERMAL_VIDEO": {
            "names": ["Infrared Thermal Sequence [imaging_frame]"],
            "role": "measure",
            "family": "PERFUSION",
            "params": {},
        },
        "DOPPLER_FLOW": {
            "names": ["Handheld Doppler Velocity [acoustic_frame]"],
            "role": "measure",
            "family": "PERFUSION",
            "params": {},
        },
        "MATCH_CRITERION": {
            "names": ["Nearest Hotspot Pair Rule [matching_frame]"],
            "role": "process_state",
            "params": {},
        },
        "FLAP_OUTCOME": {
            "names": ["Post-operative Flap Survival [clinical_outcome]"],
            "role": "measure",
            "params": {},
        },
    },
    "edges": [
        {
            "from": "COLD_CHALLENGE",
            "to": "THERMAL_VIDEO",
            "kind": "measures",
            "steps": ["IR camera records skin rewarming"],
            "loses": ["deep subcutaneous flow"],
        },
        {
            "from": "THERMAL_VIDEO",
            "to": "MATCH_CRITERION",
            "kind": "generates",
            "steps": ["pair nearest hotspot"],
            "loses": ["global assignment conflicts"],
        },
        {
            "from": "MATCH_CRITERION",
            "to": "FLAP_OUTCOME",
            "kind": "generates",
            "steps": ["selected perforator supplies flap"],
            "loses": [],
        },
    ],
}


def _make_proceed_trace():
    return {
        "document_anchors": [
            {
                "id": "A1",
                "quote": "Of 46 CTA perforators, 39 were linked to a thermographic hotspot (sensitivity 84.8%).",
                "path": ["THERMAL_VIDEO", "MATCH_CRITERION"],
            }
        ],
        "proposed_new_nodes": [
            {
                "id": "HUNGARIAN_ASSIGNMENT",
                "name": "Global One-to-One Hungarian Assignment [algorithmic_frame]",
                "role": "process_state",
                "params": {"score": ["distance_plus_brightness", "other"]},
                "source": "document",
                "doc_quote": "The optimal global assignment uses the Hungarian algorithm with a composite distance and brightness score.",
                "why_missing": "Graph collapsed global matching into a vague nearest-pair rule.",
                "proposed_edges": [
                    {
                        "from": "THERMAL_VIDEO",
                        "to": "HUNGARIAN_ASSIGNMENT",
                        "kind": "generates",
                        "step": "hotspot features enter linear sum assignment",
                        "loses": [],
                    }
                ],
            }
        ],
        "challenged_graph_items": [
            {
                "target_type": "edge",
                "target": ["THERMAL_VIDEO", "MATCH_CRITERION"],
                "challenge_kind": "collapsed_step",
                "doc_quote": "The optimal global assignment uses the Hungarian algorithm with a composite distance and brightness score.",
                "reason": "Graph says pair nearest, whereas the paper uses global 1-to-1 Hungarian optimization.",
            }
        ],
        "pre_gate": {
            "decision": "proceed_to_post",
            "reason": "Concrete Hungarian assignment and sensitivity claim are formalizable in OperationFlow.",
            "post_candidate_claims": [
                {
                    "quote": "Of 46 CTA perforators, 39 were linked to a thermographic hotspot (sensitivity 84.8%).",
                    "target_mechanism": "Test whether 84.8% linking has an independent random-matching control arm",
                }
            ],
            "open_questions_for_post": [
                {
                    "about_quote": "Of 46 CTA perforators, 39 were linked to a thermographic hotspot (sensitivity 84.8%).",
                    "phrase": "sensitivity 84.8%",
                    "question": "Does the paper validate linked perforators against intraoperative Doppler or flap survival?",
                    "asked_by": "reader",
                    "status": "not_in_document",
                    "searched": "Checked full document text; neither Doppler nor flap outcome is reported.",
                }
            ],
        },
    }


def _make_stop_trace():
    return {
        "document_anchors": [
            {
                "id": "A1",
                "quote": "Patients underwent dynamic infrared thermography (DIRT) after a two-minute cold challenge.",
                "path": ["COLD_CHALLENGE", "THERMAL_VIDEO"],
            }
        ],
        "proposed_new_nodes": [],
        "challenged_graph_items": [],
        "pre_gate": {
            "decision": "stop_at_pre",
            "reason": "No operational link from imaging to clinical flap survival is defined.",
            "blocking_gaps": ["Missing clinical flap outcome frame"],
        },
    }


def _make_valid_spec(questions):
    return {
        "schema_version": "epistemic-ledger/v2.5",
        "auditor": "PrePostUnified",
        "nodes": ["ThermalVideo", "MatchTable"],
        "tags": ["hotspotFlow"],
        "sources": [
            {
                "node": "ThermalVideo",
                "origin": "measured",
                "carries": ["hotspotFlow"],
                "quote": "Patients underwent dynamic infrared thermography (DIRT) after a two-minute cold challenge.",
            }
        ],
        "ops": [
            {
                "name": "HungarianMatch",
                "kind": "transform",
                "inputs": ["ThermalVideo"],
                "output": "MatchTable",
                "introduces": [],
                "quote": "The optimal global assignment uses the Hungarian algorithm with a composite distance and brightness score.",
            }
        ],
        "claims": [
            {
                "id": "C1",
                "statement": "Linked perforators follow from measured thermal sequence.",
                "nature": "qualitative",
                "kind": "conditionalFlow",
                "target": "MatchTable",
                "declared_sources": ["ThermalVideo"],
                "quote": "Of 46 CTA perforators, 39 were linked to a thermographic hotspot (sensitivity 84.8%).",
            }
        ],
        "questions": questions,
    }


class UnifiedPrePostTests(unittest.TestCase):
    def _write_inputs(self, td, trace, doc_text=SAMPLE_DOC):
        g_path = os.path.join(td, "graph.json")
        t_path = os.path.join(td, "trace.json")
        d_path = os.path.join(td, "doc.txt")
        with open(g_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_GRAPH, f)
        with open(t_path, "w", encoding="utf-8") as f:
            json.dump(trace, f)
        with open(d_path, "w", encoding="utf-8") as f:
            f.write(doc_text)
        return g_path, t_path, d_path

    def test_pre_probe_determinism_across_hash_seeds_and_measures_only_frame_shift(self):
        trace = {
            "document_anchors": [
                {
                    "id": "A1",
                    "quote": "Patients underwent dynamic infrared thermography (DIRT) after a two-minute cold challenge.",
                    "path": ["COLD_CHALLENGE", "THERMAL_VIDEO", "MATCH_CRITERION"],
                }
            ],
            "proposed_new_nodes": _make_proceed_trace()["proposed_new_nodes"],
            "challenged_graph_items": _make_proceed_trace()["challenged_graph_items"],
        }
        with tempfile.TemporaryDirectory() as td:
            g_path, t_path, d_path = self._write_inputs(td, trace)
            hashes = set()
            parsed = None
            for seed in ("1", "42", "999", "2026", "77777"):
                out = os.path.join(td, f"out-{seed}.json")
                env = dict(os.environ, PYTHONHASHSEED=seed)
                subprocess.run(
                    [
                        sys.executable, "-m", "pipeline.audit_cli", "pre",
                        "--mode", "probe",
                        "--graph", g_path, "--trace", t_path, "--doc", d_path, "--out", out,
                    ],
                    cwd=str(REPO_ROOT), env=env, check=True, capture_output=True, text=True,
                )
                with open(out, "rb") as f:
                    raw = f.read()
                hashes.add(hashlib.sha256(raw).hexdigest())
                parsed = json.loads(raw.decode("utf-8"))
            self.assertEqual(len(hashes), 1)
            kinds = [q["kind"] for q in parsed["anchor_probes"][0]["questions"]]
            self.assertEqual(kinds.count("FRAME_SHIFT_LOSS"), 1)
            self.assertEqual(parsed["summary"]["proposed_new_nodes_valid"], 1)
            self.assertEqual(parsed["summary"]["challenged_items_valid"], 1)
            self.assertEqual([x["id"] for x in parsed["untouched_frontier"]["sibling_frame"]], ["DOPPLER_FLOW"])
            self.assertEqual([x["id"] for x in parsed["untouched_frontier"]["downstream"]], ["FLAP_OUTCOME"])

    def test_pre_prompt_and_post_prompt_with_pre_brief(self):
        with tempfile.TemporaryDirectory() as td:
            g_path, t_path, d_path = self._write_inputs(td, _make_proceed_trace())
            pre_out = os.path.join(td, "pre_out")
            pre_prompt_path = os.path.join(td, "pre_prompt.txt")
            post_prompt_path = os.path.join(td, "post_prompt.txt")

            with contextlib.redirect_stdout(io.StringIO()):
                rc_pp = cli_main(["pre-prompt", "--doc", d_path, "--graph", g_path, "--out", pre_prompt_path])
                rc_pre = cli_main(["pre", "--graph", g_path, "--trace", t_path, "--doc", d_path, "--out", pre_out])
                rc_postp = cli_main([
                    "prompt", "--doc", d_path, "--auditor", "PostAuditor",
                    "--pre-brief", os.path.join(pre_out, "post_brief.md"), "--out", post_prompt_path,
                ])
            self.assertEqual(rc_pp, 0)
            self.assertEqual(rc_pre, 0)
            self.assertEqual(rc_postp, 0)

            pre_txt = Path(pre_prompt_path).read_text(encoding="utf-8")
            self.assertIn("audit_cli pre", pre_txt)
            self.assertIn("stop_at_pre", pre_txt)

            post_txt = Path(post_prompt_path).read_text(encoding="utf-8")
            self.assertIn("BEGIN PRE BRIEF", post_txt)
            self.assertIn("HUNGARIAN_ASSIGNMENT", post_txt)
            self.assertNotIn("audit_cli ask", post_txt)

    def test_pre_gate_blocks_post_on_stop_and_doc_mismatch_and_allows_on_proceed(self):
        with tempfile.TemporaryDirectory() as td:
            g_path, t_proceed, d_path = self._write_inputs(td, _make_proceed_trace())
            t_stop = os.path.join(td, "trace_stop.json")
            other_doc = os.path.join(td, "other.txt")
            with open(t_stop, "w", encoding="utf-8") as f:
                json.dump(_make_stop_trace(), f)
            with open(other_doc, "w", encoding="utf-8") as f:
                f.write(OTHER_DOC)

            pre_stop_dir = os.path.join(td, "pre_stop")
            pre_go_dir = os.path.join(td, "pre_go")
            post_blocked_dir = os.path.join(td, "post_blocked")
            post_mismatch_dir = os.path.join(td, "post_mismatch")
            post_ok_dir = os.path.join(td, "post_ok")

            # 1. stop_at_pre emits report only, and `run --pre-gate` blocks with exit 3
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_stop, "--doc", d_path, "--out", pre_stop_dir]), 0)
            self.assertTrue(os.path.exists(os.path.join(pre_stop_dir, "pre_gate_report.md")))
            self.assertFalse(os.path.exists(os.path.join(pre_stop_dir, "post_brief.md")))
            self.assertFalse(os.path.exists(os.path.join(pre_stop_dir, "questions_seed.json")))

            # 2. proceed_to_post emits handoff and questions_seed passes pipeline.schema
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", pre_go_dir]), 0)
            with open(os.path.join(pre_go_dir, "questions_seed.json"), encoding="utf-8") as f:
                qseed = json.load(f)
            spec = _make_valid_spec(qseed["questions"])
            errs, _ = validate_spec(spec, ingest_document(d_path))
            self.assertEqual(errs, [])
            spec_path = os.path.join(td, "spec.json")
            with open(spec_path, "w", encoding="utf-8") as f:
                json.dump(spec, f)

            # 3. `run --pre-gate` on stop_at_pre -> exit 3, zero Post files written
            err_buf = io.StringIO()
            with contextlib.redirect_stderr(err_buf):
                rc_stop = cli_main([
                    "run", "--doc", d_path, "--spec", spec_path, "--out", post_blocked_dir,
                    "--pre-gate", os.path.join(pre_stop_dir, "explore.json"),
                ])
            self.assertEqual(rc_stop, 3)
            self.assertIn("stop_at_pre", err_buf.getvalue())
            self.assertFalse(os.path.exists(post_blocked_dir))

            # 4. `run --pre-gate` with mismatched document SHA -> exit 3
            err_buf2 = io.StringIO()
            with contextlib.redirect_stderr(err_buf2):
                rc_mis = cli_main([
                    "run", "--doc", other_doc, "--spec", spec_path, "--out", post_mismatch_dir,
                    "--pre-gate", os.path.join(pre_go_dir, "explore.json"),
                ])
            self.assertEqual(rc_mis, 3)
            self.assertIn("SHA-256", err_buf2.getvalue())
            self.assertFalse(os.path.exists(post_mismatch_dir))

            # 5. `run --pre-gate` on proceed_to_post with matching doc -> exit 0, Lean verified!
            out_buf = io.StringIO()
            with contextlib.redirect_stdout(out_buf):
                rc_ok = cli_main([
                    "run", "--doc", d_path, "--spec", spec_path, "--out", post_ok_dir,
                    "--pre-gate", os.path.join(pre_go_dir, "explore.json"),
                ])
            self.assertEqual(rc_ok, 0)
            self.assertTrue(os.path.exists(os.path.join(post_ok_dir, "PrePostUnified_Verified.lean")))
            rep = json.loads(Path(post_ok_dir, "PrePostUnified_report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rep["questions"]["items"]), 1)
            self.assertFalse(rep["questions"]["verified_by_lean"])

    def test_proceed_then_stop_or_invalid_in_same_dir_purges_stale_post_artifacts(self):
        """Codex #27660/#27664: rerunning stop_at_pre or invalid gate in same dir purges stale Post files."""
        invalid_trace = {
            "document_anchors": _make_stop_trace()["document_anchors"],
            "proposed_new_nodes": [],
            "challenged_graph_items": [],
            "pre_gate": {"decision": "stop_at_pre", "reason": "Missing blocking_gaps list"},
        }
        with tempfile.TemporaryDirectory() as td:
            g_path, t_proceed, d_path = self._write_inputs(td, _make_proceed_trace())
            t_stop = os.path.join(td, "trace_stop.json")
            t_bad = os.path.join(td, "trace_bad.json")
            with open(t_stop, "w", encoding="utf-8") as f:
                json.dump(_make_stop_trace(), f)
            with open(t_bad, "w", encoding="utf-8") as f:
                json.dump(invalid_trace, f)
            shared_dir = os.path.join(td, "shared")

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", shared_dir]), 0)
            self.assertTrue(os.path.exists(os.path.join(shared_dir, "post_brief.md")))
            self.assertTrue(os.path.exists(os.path.join(shared_dir, "questions_seed.json")))

            # proceed -> stop in same dir
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_stop, "--doc", d_path, "--out", shared_dir]), 0)
            self.assertTrue(os.path.exists(os.path.join(shared_dir, "pre_gate_report.md")))
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "post_brief.md")))
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "questions_seed.json")))

            # proceed -> invalid in same dir purges report + Post files and exits 2
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", shared_dir]), 0)
            with contextlib.redirect_stderr(io.StringIO()):
                rc_bad = cli_main(["pre", "--graph", g_path, "--trace", t_bad, "--doc", d_path, "--out", shared_dir])
            self.assertEqual(rc_bad, 2)
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "pre_gate_report.md")))
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "post_brief.md")))
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "questions_seed.json")))

    def test_codex_27667_pre_crash_before_and_after_probe_never_leaves_valid_pass(self):
        """Codex #27667 Blocker 1: corrupt trace (before probe) or merge crash (after probe) invalidates explore.json."""
        from unittest import mock

        with tempfile.TemporaryDirectory() as td:
            g_path, t_proceed, d_path = self._write_inputs(td, _make_proceed_trace())
            shared_dir = os.path.join(td, "shared_pre")

            # Seed a valid proceed_to_post run
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", shared_dir]), 0)
            self.assertTrue(os.path.exists(os.path.join(shared_dir, "explore.json")))

            # 1. Failure BEFORE probe (truncated/corrupt trace JSON) must invalidate old explore.json
            t_corrupt = os.path.join(td, "corrupt_trace.json")
            Path(t_corrupt).write_text('{"document_anchors": [', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                cli_main(["pre", "--graph", g_path, "--trace", t_corrupt, "--doc", d_path, "--out", shared_dir])
            for fname in ("explore.json", "explored-graph.json", "pre_gate_report.md", "post_brief.md", "questions_seed.json"):
                self.assertFalse(os.path.exists(os.path.join(shared_dir, fname)), f"stale {fname} survived pre crash!")

            # Verify --pre-gate now rejects the missing explore.json with exit 3
            spec_path = os.path.join(td, "spec.json")
            with open(spec_path, "w", encoding="utf-8") as f:
                json.dump(_make_valid_spec([]), f)
            with contextlib.redirect_stderr(io.StringIO()):
                rc_post = cli_main([
                    "run", "--doc", d_path, "--spec", spec_path, "--out", os.path.join(td, "post_after_crash"),
                    "--pre-gate", os.path.join(shared_dir, "explore.json"),
                ])
            self.assertEqual(rc_post, 3)

            # 2. Failure AFTER probe (e.g. merge_patch_graph raises OSError) in fresh dir must NOT publish explore.json
            fresh_dir = os.path.join(td, "fresh_after_probe_crash")
            with mock.patch("pipeline.preform.merge_patch_graph", side_effect=OSError("simulated disk error")):
                with self.assertRaises(OSError):
                    cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", fresh_dir])
            self.assertFalse(os.path.exists(os.path.join(fresh_dir, "explore.json")))
            self.assertFalse(os.path.exists(os.path.join(fresh_dir, "post_brief.md")))

    def test_codex_27667_post_gate_block_purges_stale_proof_and_reports_in_same_dir(self):
        """Codex #27667 Blocker 2: rerunning `run --pre-gate` after gate turns stop_at_pre purges old Lean/reports."""
        with tempfile.TemporaryDirectory() as td:
            g_path, t_proceed, d_path = self._write_inputs(td, _make_proceed_trace())
            t_stop = os.path.join(td, "trace_stop.json")
            with open(t_stop, "w", encoding="utf-8") as f:
                json.dump(_make_stop_trace(), f)

            pre_go = os.path.join(td, "pre_go")
            pre_stop = os.path.join(td, "pre_stop")
            post_dir = os.path.join(td, "post_shared")

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", pre_go]), 0)
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_stop, "--doc", d_path, "--out", pre_stop]), 0)

            spec_path = os.path.join(td, "spec.json")
            with open(spec_path, "w", encoding="utf-8") as f:
                json.dump(_make_valid_spec([]), f)

            # 1. Passing run writes Verified.lean + reports
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main([
                    "run", "--doc", d_path, "--spec", spec_path, "--out", post_dir,
                    "--pre-gate", os.path.join(pre_go, "explore.json"),
                ]), 0)
            for fname in ("PrePostUnified_Verified.lean", "PrePostUnified_report.json", "PrePostUnified_report.md"):
                self.assertTrue(os.path.exists(os.path.join(post_dir, fname)))

            # 2. Blocked rerun in SAME dir returns exit 3 and purges stale proof + reports without creating new files
            err_buf = io.StringIO()
            with contextlib.redirect_stderr(err_buf):
                rc = cli_main([
                    "run", "--doc", d_path, "--spec", spec_path, "--out", post_dir,
                    "--pre-gate", os.path.join(pre_stop, "explore.json"),
                ])
            self.assertEqual(rc, 3)
            self.assertIn("stop_at_pre", err_buf.getvalue())
            for fname in ("PrePostUnified_Verified.lean", "PrePostUnified_report.json", "PrePostUnified_report.md"):
                self.assertFalse(os.path.exists(os.path.join(post_dir, fname)), f"stale {fname} survived gate block!")
            self.assertEqual(os.listdir(post_dir), [])

    def test_codex_27669_pre_ingest_failure_invalidates_gate_and_graph_aliasing_is_preserved(self):
        """Codex #27669: (1) UTF-8 ingest error invalidates old explore.json; (2) --graph == out/explored-graph.json is preserved and rejected."""
        with tempfile.TemporaryDirectory() as td:
            g_path, t_proceed, d_path = self._write_inputs(td, _make_proceed_trace())
            shared_dir = os.path.join(td, "shared_pre")

            # Seed valid proceed_to_post
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", shared_dir]), 0)
            self.assertTrue(os.path.exists(os.path.join(shared_dir, "explore.json")))
            orig_patched = Path(shared_dir, "explored-graph.json").read_bytes()

            # 1. Corrupt UTF-8 on --doc during rerun in SAME dir must invalidate explore.json BEFORE ingest fails
            Path(d_path).write_bytes(b"\xff\xfe\xfd invalid utf-8 bytes")
            with self.assertRaises(UnicodeDecodeError):
                cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", shared_dir])
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "explore.json")))
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "post_brief.md")))

            # Restore doc and re-seed proceed_to_post
            Path(d_path).write_text(SAMPLE_DOC, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["pre", "--graph", g_path, "--trace", t_proceed, "--doc", d_path, "--out", shared_dir]), 0)
            orig_patched = Path(shared_dir, "explored-graph.json").read_bytes()

            # 2. Passing out/explored-graph.json back as --graph with SAME --out must preserve input graph, invalidate gate, exit 2
            err_buf = io.StringIO()
            with contextlib.redirect_stderr(err_buf):
                rc_alias = cli_main([
                    "pre",
                    "--graph", os.path.join(shared_dir, "explored-graph.json"),
                    "--trace", t_proceed,
                    "--doc", d_path,
                    "--out", shared_dir,
                ])
            self.assertEqual(rc_alias, 2)
            self.assertIn("in-place overwrite", err_buf.getvalue())
            self.assertEqual(Path(shared_dir, "explored-graph.json").read_bytes(), orig_patched)
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "explore.json")))
            self.assertFalse(os.path.exists(os.path.join(shared_dir, "post_brief.md")))


if __name__ == "__main__":
    unittest.main()
