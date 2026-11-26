"""Frozen regression suite over 11 public real-document AuditSpec records (46 claims).

Includes:
- 4 independent blind records on *Utah v. Strieff*, 579 U.S. 232 (2016) (fixed & free prompts)
- 2 independent blind records on Balestriero & LeCun (2026) — Platonic JEPA
- 2 independent blind records on the VP != VNP arithmetic-circuit paper
- 3 committed real-paper specs in `pipeline/examples/` (Papadopetraki 2025, Society of AI Scientists)

Any engine change in `EpistemicLedger/OperationFlow.lean` or `pipeline/` that alters a claim's
Lean-verified verdict or finding types immediately surfaces an explicit claim-level diff here.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.lean_runner import run_lean_verification
from pipeline.schema import validate_spec

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "blind_regression" / "golden_verdicts.json"
FORBIDDEN_LOCAL_TOKENS = ("/home/", "/tmp/", "agentchattr")


class BlindRegressionTests(unittest.TestCase):
    def test_frozen_public_blind_records_verdicts_and_finding_types(self) -> None:
        golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        records: dict[str, dict] = golden["records"]
        self.assertEqual(len(records), 11)

        drifts: list[str] = []
        total_claims = 0

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for rel_path, expected_rec in records.items():
                spec_path = REPO_ROOT / rel_path
                self.assertTrue(spec_path.is_file(), f"Missing frozen fixture: {rel_path}")
                raw = spec_path.read_text(encoding="utf-8")
                for tok in FORBIDDEN_LOCAL_TOKENS:
                    self.assertNotIn(tok, raw, f"Local/private token {tok!r} found in {rel_path}")

                spec = json.loads(raw)
                errs, _ = validate_spec(spec, doc=None)
                self.assertEqual(errs, [], f"Schema validation failed for {rel_path}: {errs}")

                res = run_lean_verification(
                    spec,
                    repo_root=REPO_ROOT,
                    out_lean_path=tmp_dir / f"{spec['auditor']}_{total_claims}.lean",
                )
                self.assertTrue(res.raw_axioms_ok, f"Axiom check failed for {rel_path}")

                actual_claims = {
                    c.claim_id: {
                        "verdict": c.verdict,
                        "finding_types": [f["type"] for f in c.findings],
                    }
                    for c in res.claims
                }
                expected_claims = expected_rec["claims"]
                if set(actual_claims.keys()) != set(expected_claims.keys()):
                    drifts.append(
                        f"{rel_path}: claim IDs changed (expected {sorted(expected_claims)}, got {sorted(actual_claims)})"
                    )
                    continue

                for cid, exp in expected_claims.items():
                    total_claims += 1
                    act = actual_claims[cid]
                    if act != exp:
                        drifts.append(
                            f"{rel_path}::{cid}: expected verdict={exp['verdict']} findings={exp['finding_types']}, "
                            f"got verdict={act['verdict']} findings={act['finding_types']}"
                        )

        self.assertEqual(total_claims, 46)
        self.assertEqual(drifts, [], "Engine verdict/finding drift detected:\n" + "\n".join(drifts))


if __name__ == "__main__":
    unittest.main()
