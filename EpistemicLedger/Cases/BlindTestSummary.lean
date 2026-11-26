import EpistemicLedger.Cases.BlindABarontini
import EpistemicLedger.Cases.BlindABalestrieroLeCun
import EpistemicLedger.Cases.BlindAVpVnp
import EpistemicLedger.Cases.BlindBBarontini
import EpistemicLedger.Cases.BlindBBalestrieroLeCun
import EpistemicLedger.Cases.BlindBVpVnp

/-
Blind agreement test, 2026-11-26. Six records written by fresh agents that had
not seen the chat thread, the critiques or any earlier record. Auditor A =
fable, auditor B = opus. The six `Blind*.lean` files are the agents' output,
copied unchanged.

This file only tabulates: verdict and per-rule finding counts for each of the
seven fixed claims, for each auditor.
-/
namespace EpistemicLedger.Cases.BlindTestSummary

open EpistemicLedger.Cases

/-- One row: claim label, auditor A (verdict, profile), auditor B (verdict, profile).
A profile is the number of findings per rule, (R1, R2, R3, R4). -/
abbrev Row := String × (Verdict × (Nat × Nat × Nat × Nat)) × (Verdict × (Nat × Nat × Nat × Nat))

def table : List Row :=
  [ ("Barontini 1 (testbed sentence)",
      (verdict BlindA.Barontini.claim1, ruleProfile (audit BlindA.Barontini.claim1)),
      (verdict BlindB.Barontini.claim1, ruleProfile (audit BlindB.Barontini.claim1))),
    ("Barontini 2 (only internal degrees of freedom)",
      (verdict BlindA.Barontini.claim2, ruleProfile (audit BlindA.Barontini.claim2)),
      (verdict BlindB.Barontini.claim2, ruleProfile (audit BlindB.Barontini.claim2))),
    ("Balestriero-LeCun 1 (no longer a hypothesis but a theorem)",
      (verdict BlindA.BalestrieroLeCun.claim1, ruleProfile (audit BlindA.BalestrieroLeCun.claim1)),
      (verdict BlindB.BalestrieroLeCun.claim1, ruleProfile (audit BlindB.BalestrieroLeCun.claim1))),
    ("Balestriero-LeCun 2 (Theorem 1 as stated)",
      (verdict BlindA.BalestrieroLeCun.claim2, ruleProfile (audit BlindA.BalestrieroLeCun.claim2)),
      (verdict BlindB.BalestrieroLeCun.claim2, ruleProfile (audit BlindB.BalestrieroLeCun.claim2))),
    ("Balestriero-LeCun 3 (42 times fewer samples)",
      (verdict BlindA.BalestrieroLeCun.claim3, ruleProfile (audit BlindA.BalestrieroLeCun.claim3)),
      (verdict BlindB.BalestrieroLeCun.claim3, ruleProfile (audit BlindB.BalestrieroLeCun.claim3))),
    ("VP != VNP 1 (main theorem)",
      (verdict BlindA.VpVnp.claim1, ruleProfile (audit BlindA.VpVnp.claim1)),
      (verdict BlindB.VpVnp.claim1, ruleProfile (audit BlindB.VpVnp.claim1))),
    ("VP != VNP 2 (formalized in Lean)",
      (verdict BlindA.VpVnp.claim2, ruleProfile (audit BlindA.VpVnp.claim2)),
      (verdict BlindB.VpVnp.claim2, ruleProfile (audit BlindB.VpVnp.claim2))) ]

#eval table

/-- The table without its labels, in claim order. -/
def tableValues : List ((Verdict × (Nat × Nat × Nat × Nat)) × (Verdict × (Nat × Nat × Nat × Nat))) :=
  table.map (·.2)

set_option maxRecDepth 20000 in
/-- The whole result of the blind test, kernel-checked.
Rows: Barontini 1, Barontini 2, Balestriero–LeCun 1, 2, 3, VP ≠ VNP 1, 2.
Each side: verdict and findings per rule (R1, R2, R3, R4); auditor A then B. -/
theorem blind_test_result :
    tableValues =
      [ ((.rejected, 9, 1, 4, 0), (.rejected, 13, 0, 7, 0)),
        ((.rejected, 1, 2, 1, 7), (.rejected, 8, 0, 3, 9)),
        ((.rejected, 8, 0, 5, 0), (.rejected, 7, 0, 5, 6)),
        ((.admissibleOnDeclaredBets, 0, 0, 0, 0), (.admissible, 0, 0, 0, 0)),
        ((.rejected, 5, 1, 0, 0), (.rejected, 6, 0, 0, 0)),
        ((.rejected, 2, 0, 0, 0), (.rejected, 0, 0, 1, 0)),
        ((.admissibleOnDeclaredBets, 0, 0, 0, 0), (.rejected, 1, 0, 1, 0)) ] := by
  decide

/-- Rule 4 findings per claim, (auditor A, auditor B). It fired only on
Barontini 2 (both auditors) and Balestriero–LeCun 1 (auditor B, who read the
wording as "arises by itself"; auditor A read it as conditional). -/
theorem rule4_fired_only_on_two_claims :
    tableValues.map (fun r => (r.1.2.2.2.2, r.2.2.2.2.2)) =
      [(0, 0), (7, 9), (0, 6), (0, 0), (0, 0), (0, 0), (0, 0)] := by
  rw [blind_test_result]
  decide

/-- 11 of the 14 verdicts are `rejected`. -/
theorem rejected_count :
    (tableValues.map (fun r => [r.1.1, r.2.1])).flatten.count .rejected = 11 := by
  rw [blind_test_result]
  decide

/-! ### The same six records under the v1 verdict (in-sample: v1 was designed after seeing them) -/

/-- Per claim: (v1 verdict, wording recorded as intrinsic?, rule 4 fired?) for A, then B. -/
def v1Table : List ((VerdictV1 × Bool × Bool) × (VerdictV1 × Bool × Bool)) :=
  let row {ι η : Type} [DecidableEq ι] [DecidableEq η] (c : Claim ι η) : VerdictV1 × Bool × Bool :=
    (verdictV1 c, decide (c.kind = .intrinsic), rule4Fired c)
  [ (row BlindA.Barontini.claim1, row BlindB.Barontini.claim1),
    (row BlindA.Barontini.claim2, row BlindB.Barontini.claim2),
    (row BlindA.BalestrieroLeCun.claim1, row BlindB.BalestrieroLeCun.claim1),
    (row BlindA.BalestrieroLeCun.claim2, row BlindB.BalestrieroLeCun.claim2),
    (row BlindA.BalestrieroLeCun.claim3, row BlindB.BalestrieroLeCun.claim3),
    (row BlindA.VpVnp.claim1, row BlindB.VpVnp.claim1),
    (row BlindA.VpVnp.claim2, row BlindB.VpVnp.claim2) ]

#eval v1Table

/-- Number of dependencies each auditor enumerated, per paper: (A, B). -/
def dependencyCounts : List (String × Nat × Nat) :=
  [ ("Barontini",
      (BlindA.Barontini.claim1.used ++ BlindA.Barontini.claim2.used).map (·.id) |>.eraseDups |>.length,
      (BlindB.Barontini.claim1.used ++ BlindB.Barontini.claim2.used).map (·.id) |>.eraseDups |>.length),
    ("Balestriero-LeCun",
      (BlindA.BalestrieroLeCun.claim1.used ++ BlindA.BalestrieroLeCun.claim2.used
        ++ BlindA.BalestrieroLeCun.claim3.used).map (·.id) |>.eraseDups |>.length,
      (BlindB.BalestrieroLeCun.claim1.used ++ BlindB.BalestrieroLeCun.claim2.used
        ++ BlindB.BalestrieroLeCun.claim3.used).map (·.id) |>.eraseDups |>.length),
    ("VP != VNP",
      (BlindA.VpVnp.claim1.used ++ BlindA.VpVnp.claim2.used).map (·.id) |>.eraseDups |>.length,
      (BlindB.VpVnp.claim1.used ++ BlindB.VpVnp.claim2.used).map (·.id) |>.eraseDups |>.length) ]

#eval dependencyCounts

end EpistemicLedger.Cases.BlindTestSummary
