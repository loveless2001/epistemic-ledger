import EpistemicLedger.AuditRules
import EpistemicLedger.Cases.BarontiniColdAtomsTime
import EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa
import EpistemicLedger.Cases.AdversarialForgetOrder
import EpistemicLedger.Cases.BlindTestSummary

/-
Prints, at build time, which axioms each result rests on. The aim is that none
of them needs `Classical.choice`: the ledger should not itself lean on
"exists without exhibiting".
-/
open EpistemicLedger

#print axioms audit_forget_order_irrelevant
#print axioms audit_findings_survive_more_used
#print axioms clean_audit_dependency_declared_or_forgotten
#print axioms clean_audit_intrinsic_has_no_experimenter_structure
#print axioms Cases.BarontiniColdAtomsTime.headline_findings
#print axioms Cases.BarontiniColdAtomsTime.headline_rejected
#print axioms Cases.BarontiniColdAtomsTime.body_claim_admissible
#print axioms Cases.BalestrieroLeCunPlatonicJepa.headline_findings
#print axioms Cases.BalestrieroLeCunPlatonicJepa.headline_rejected
#print axioms Cases.BalestrieroLeCunPlatonicJepa.conditional_theorem_admissible
#print axioms Cases.BalestrieroLeCunPlatonicJepa.engineering_claim_admissible
#print axioms AdversarialForgetOrder.contradictory_record_rejected
#print axioms AdversarialForgetOrder.reversed_record_rejected
#print axioms Cases.BlindTestSummary.blind_test_result
#print axioms Cases.BlindTestSummary.rule4_fired_only_on_two_claims
#print axioms Cases.BlindTestSummary.rejected_count
