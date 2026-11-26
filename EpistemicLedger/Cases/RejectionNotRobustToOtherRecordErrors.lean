import EpistemicLedger.AuditRules

/-
Boundary of `audit_findings_survive_more_used`, raised by codex (msg 27247).

That theorem says a rejection survives when entries are appended to `used`.
It does not make a rejection safe against other mistakes in the record. The
synthetic record below is rejected for one reason; fixing either of two
plausible auditor errors makes it admissible.
-/
namespace EpistemicLedger.Cases.RejectionNotRobustToOtherRecordErrors

inductive Dep where
  | threshold
  deriving DecidableEq, Repr

/-- An auditor records that the claim uses a threshold and does not declare it. -/
def asFirstRecorded : Claim Dep Unit where
  statement := "The effect appears above the threshold."
  kind := .conditional
  used := [⟨.threshold, .setByExperimenter⟩]
  declared := []
  forgets := []
  hypotheses := []
  declaredBets := []

theorem first_record_rejected :
    audit asFirstRecorded = [.droppedDependency .threshold]
      ∧ verdict asFirstRecorded = .rejected := by decide

/-- A re-read shows the authors did state the threshold: the auditor had left
it out of `declared`. The only finding disappears. -/
theorem correcting_declared_flips_verdict :
    verdict { asFirstRecorded with declared := [.threshold] } = .admissible := by decide

/-- A re-read shows the claim never used the threshold: the auditor had put a
spurious entry in `used`. The only finding disappears. -/
theorem removing_spurious_used_flips_verdict :
    verdict { asFirstRecorded with used := [] } = .admissible := by decide

end EpistemicLedger.Cases.RejectionNotRobustToOtherRecordErrors
