import EpistemicLedger.OperationFlow
import EpistemicLedger.Cases.V2FlowBenchmarks
import EpistemicLedger.Cases.V2BlindTestSummary

/-
Prints, at build time, which axioms each core OperationFlow soundness theorem
and benchmark proof rests on. None may depend on `Classical.choice`, `sorryAx`,
or compiler reduction axioms — only `{propext, Quot.sound}`.
-/
open EpistemicLedger.OperationFlow

#print axioms admissible_emerges_has_no_smuggling_path
#print axioms unrelated_experimenter_source_preserves_emerges_audit
#print axioms failed_forget_propagates
#print axioms shown_forget_blocks
#print axioms admissible_policy3_clean_both_alarms
#print axioms admissible_effectiveness_has_control_and_charged_cost
#print axioms epistemicVerdict_admissible_iff
#print axioms epistemicVerdict_outOfScope_iff
#print axioms epistemicVerdict_rejected_iff
#print axioms admissible_theoremApplication_implies_hypotheses_satisfied
#print axioms EpistemicLedger.Cases.V2FlowBenchmarks.EpistemicVerdictTests.independent_control_no_cost_ledger_epistemic_admissible
