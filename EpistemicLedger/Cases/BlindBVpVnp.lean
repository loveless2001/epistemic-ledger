import EpistemicLedger.AuditRules

/-
Blind record for "VP ≠ VNP over every field" (pages 1-8 of the paper and the
repository README only; the appendix proof was not available).
-/
namespace EpistemicLedger.Cases.BlindB.VpVnp

open EpistemicLedger

inductive Dep where
  /-- §1.3: "An arithmetic circuit over a commutative ring R is a finite list of
  polynomials ... The size of the circuit is the length of the list, so that
  variables and constants are counted as gates." -/
  | arithmeticCircuitModel
  /-- §1: "For an m × m matrix of variables x_{i,j} ... these are the multilinear
  polynomials PERM_m = ... and HC_m = ..." -/
  | permanentAndHamiltonianCyclePolynomials
  /-- §1.3: "Valiant's classes are defined as follows [Val79, Val82]. A family (f_n)
  of polynomials over a field is in VP if ..." -/
  | valiantClassDefinitions
  /-- Thm 1.1: "every circuit for HC_m, and every circuit for PERM_m if p ≠ 2";
  "In characteristic two the permanent coincides with the determinant". -/
  | characteristicRestrictionForPermanent
  /-- §1.1: "Here and throughout, log = log2." -/
  | logBaseTwoConvention
  /-- §1.2: spectral points "are only known to exist by Zorn's lemma (prop_gauge)";
  README: "should name no axiom other than propext, Classical.choice and Quot.sound". -/
  | classicalFoundationsWithChoice
  /-- §2.1-2.3: the proof works with constructed objects, not the permanent directly:
  "in each case we work with another polynomial" (f_{k,ℓ} of (2.1), Φ of (2.2)),
  spectral points, hubs, and parameters "k = r², ℓ = 100r" (Figure 1). -/
  | proofAuxiliaryConstructions
  /-- README: "lake build", "lake env lean scripts/PrintAxioms.lean"; "re-checks the
  proofs with a second, independently written kernel, nanoda". -/
  | leanKernelProofCheck
  /-- Abstract: "discovered by an internal research Claude model". -/
  | internalResearchClaudeModel
  /-- No account of the discovery process (prompts, human role, selection among
  attempts) appears in the provided text; the abstract and README only assert it:
  "The result was discovered by an internal research Claude model." -/
  | discoveryProcessAccount
  deriving DecidableEq, Repr

inductive Hyp where
  /-- §1.3: PERM "is complete for VNP over every field in which 2 ≠ 0; this is a
  theorem of Valiant"; footnote 1: HC "is VNP-complete for all fields". Applied via
  "an explicit form of Valiant's completeness theorem" (§2.1). -/
  | completenessReductionFieldCondition
  /-- Thm 2.2 (thm_alt): "Over every field k at least one of the two hypotheses of
  Definition 2.1 holds"; "We do not know which of the two hypotheses holds". -/
  | oneOfTheTwoCasesHolds
  /-- §1.1: "As (PERM_m) and (HC_m) are in VNP, Theorem 1.1 gives the following";
  §1.3: "belongs to VNP, for example by Ryser's formula". -/
  | permanentAndHcInVnp
  /-- README: "The build prints sorry warnings from Challenge.lean only"; axioms only
  "propext, Classical.choice and Quot.sound"; CI re-checks with nanoda. -/
  | leanProofsCheckedWithoutSorry
  /-- README: "Lean checks the proofs, but no machine checks that this file says
  what is claimed. Appendix Q ... says where they differ"; "no human mathematician
  has checked the proof". -/
  | leanStatementMatchesClaim
  /-- §1.1: "Section 3 prints the Lean file that states Theorems 1.1 and 1.4 and
  Corollary 1.2 from Mathlib alone"; only the determinantal consequence "is the one
  numbered statement of this paper that is not formalized in Lean" (§1.2). -/
  | mainStatementsFormalized
  deriving DecidableEq, Repr

def claim1 : Claim Dep Hyp where
  statement := "We prove that every arithmetic circuit that computes the permanent of an \
    m × m matrix over the reals has more than m^(c (log m)^(1/3)) gates, for some \
    constant c > 0 and all sufficiently large m. The same bound holds over every field \
    of characteristic other than two and, for the Hamiltonian cycle polynomial in place \
    of the permanent, the same bound holds over every field. Hence VP ≠ VNP over every field."
  kind := .conditional
  used :=
    [ ⟨.arithmeticCircuitModel, .setByExperimenter⟩,
      ⟨.permanentAndHamiltonianCyclePolynomials, .setByExperimenter⟩,
      ⟨.valiantClassDefinitions, .setByExperimenter⟩,
      ⟨.characteristicRestrictionForPermanent, .setByExperimenter⟩,
      ⟨.logBaseTwoConvention, .setByExperimenter⟩,
      ⟨.classicalFoundationsWithChoice, .setByExperimenter⟩,
      ⟨.proofAuxiliaryConstructions, .setByExperimenter⟩,
      ⟨.leanKernelProofCheck, .setByExperimenter⟩ ]
  declared :=
    [ .arithmeticCircuitModel, .permanentAndHamiltonianCyclePolynomials,
      .valiantClassDefinitions, .characteristicRestrictionForPermanent,
      .logBaseTwoConvention, .classicalFoundationsWithChoice ]
  forgets :=
    [ -- The formal statement mentions none of them: it is stated "from Mathlib alone".
      ⟨.proofAuxiliaryConstructions, .shown⟩,
      -- Two independently written kernels (Lean, nanoda) re-check the same proofs.
      ⟨.leanKernelProofCheck, .shown⟩ ]
  hypotheses :=
    [ ⟨.completenessReductionFieldCondition, .discharged⟩,
      ⟨.oneOfTheTwoCasesHolds, .discharged⟩,
      ⟨.permanentAndHcInVnp, .discharged⟩,
      ⟨.leanProofsCheckedWithoutSorry, .discharged⟩,
      ⟨.leanStatementMatchesClaim, .bet⟩ ]
  declaredBets := []

def claim2 : Claim Dep Hyp where
  statement := "The result was discovered by an internal research Claude model and has \
    been formalized in Lean."
  kind := .conditional
  used :=
    [ ⟨.internalResearchClaudeModel, .setByExperimenter⟩,
      ⟨.discoveryProcessAccount, .measured⟩,
      ⟨.leanKernelProofCheck, .setByExperimenter⟩ ]
  declared := [.internalResearchClaudeModel, .leanKernelProofCheck]
  forgets := []
  hypotheses :=
    [ ⟨.mainStatementsFormalized, .discharged⟩,
      ⟨.leanProofsCheckedWithoutSorry, .discharged⟩,
      ⟨.leanStatementMatchesClaim, .bet⟩ ]
  declaredBets := []

#eval audit claim1
#eval verdict claim1
#eval audit claim2
#eval verdict claim2

theorem claim1_verdict : verdict claim1 = .rejected := by decide
theorem claim2_verdict : verdict claim2 = .rejected := by decide

end EpistemicLedger.Cases.BlindB.VpVnp
