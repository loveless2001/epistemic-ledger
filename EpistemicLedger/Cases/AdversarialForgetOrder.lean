import EpistemicLedger.AuditRules

/-
Adversarial case by codex (2026-11-26). In v0, `forgetEvidence` took the first
matching forget step, so the record below passed with zero findings while the
same entries in reverse order were rejected.

After the fix (a contradiction anywhere wins), claude turned codex's two
theorems into regression tests: both orders must now be rejected. The record
itself is unchanged.
-/
namespace EpistemicLedger.AdversarialForgetOrder

inductive Dep where
  | threshold
  deriving DecidableEq, Repr

/-- A synthetic headline. The same record includes a counterexample to
invariance under changes to the experimenter's threshold. -/
def headline : Claim Dep Unit where
  statement := "The observed boundary arises entirely from the system itself."
  kind := .intrinsic
  used := [⟨.threshold, .setByExperimenter⟩]
  declared := []
  forgets := [⟨.threshold, .shown⟩, ⟨.threshold, .contradicted⟩]
  hypotheses := []
  declaredBets := []

/-- v0 accepted this record (`audit headline = []`). It must be rejected. -/
theorem contradictory_record_rejected :
    audit headline =
        [.forgetContradicted .threshold, .intrinsicOnExperimenterStructure .threshold] ∧
      verdict headline = .rejected := by decide

/-- The reversed order gives the same findings. -/
theorem reversed_record_rejected :
    let c := { headline with forgets := headline.forgets.reverse }
    audit c =
        [.forgetContradicted .threshold, .intrinsicOnExperimenterStructure .threshold] ∧
      verdict c = .rejected := by decide

end EpistemicLedger.AdversarialForgetOrder
