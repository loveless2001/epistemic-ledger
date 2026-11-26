import EpistemicLedger.AuditRules

/-
Blind claim record for "VP ≠ VNP over every field" (pages 1 to 8 of 70, plus
the repository README). The full proof (pages 9 to 70) was not provided.

How the fields were filled:

* `used`         every model, definition, proof choice, axiom-level input and
                 tool or check that the provided text says the derivation
                 relies on. Intermediate lemmas that the paper proves are not
                 listed one by one; a theorem applied under a condition is
                 recorded in `hypotheses` instead.
* `declared`     only what the quoted claim itself names.
* `forgets`      a step the paper explicitly offers after which the conclusion
                 no longer mentions the dependency. `shown` means the provided
                 overview states the step with its lemma; the proofs themselves
                 are in pages that were not provided.
* `hypotheses`   statuses are the ones the paper and the README report. Nothing
                 was re-run or re-proved by the auditor.
* `declaredBets` unchecked hypotheses that the paper or the README state openly.

Maths glyphs in quotes are normalised (m0, μ, PERM_m), because the text
extraction of the PDF garbles them.
-/
namespace EpistemicLedger.Cases.BlindA.VpVnp

inductive Dep where
  /-- Section 1.3: "We call the entries of the list the gates of the circuit,
  and we say that the circuit computes each of the polynomials in the list." -/
  | arithmeticCircuitModel
  /-- Section 1.3: "The size of the circuit is the length of the list, so that
  variables and constants are counted as gates." Footnote 2: "Counting only the
  additions and multiplications would change the size by a factor of at most
  three." -/
  | gateCountConvention
  /-- Section 1.3: "Valiant’s classes are defined as follows [Val79, Val82]." -/
  | valiantClassDefinitions
  /-- Section 1.1, after Theorem 1.1: "In characteristic two the permanent
  coincides with the determinant; since the determinant has polynomial-size
  circuits, the theorem does not apply there." -/
  | fieldCharacteristic
  /-- Section 2.2, "The two cases": "the constants, among them m0, depend on
  the integer μ, for which the proof gives no value, and this is why
  Theorem 1.1 comes with no value for m0." -/
  | unknownConstantMu
  /-- Section 2.1: "The proof consists of two cases, the contracting case and
  the flat case, according to which of two technical hypotheses (described
  next) holds." Also: "We do not know which of the two hypotheses holds, even
  over R, nor do we show that the two are mutually exclusive." -/
  | flatOrContractingCaseSplit
  /-- Section 2.1: "Rather than analyzing the permanent or Hamiltonian cycle
  polynomial directly, in each case we work with another polynomial, which the
  permanent, and likewise the Hamiltonian cycle polynomial, can express." -/
  | auxiliaryPolynomials
  /-- Section 1.2: "The spectral points that we use are not explicit at all,
  since they are only known to exist by Zorn’s lemma (prop_gauge)." -/
  | zornsLemmaForSpectralPoints
  /-- Section 1: "The full proofs are in the associated Lean release and in the
  appendix". README: "This folder holds the paper and its Lean 4 formalization.
  Both were written by AI models"; the statement file "states all of the above
  and imports only Mathlib"; the proofs may use the axioms "propext,
  Classical.choice and Quot.sound". -/
  | leanFormalization
  /-- Abstract and README: "The result was discovered by an internal research
  Claude model". The provided text does not describe the model or how it was
  run. -/
  | internalResearchModel
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Theorem 2.2 (thm_alt): "Over every field k at least one of the two
  hypotheses of Definition 2.1 holds, that is, one of the two cases occurs." -/
  | oneOfTheTwoCasesHolds
  /-- Footnote 1: "The permanent is VNP-complete for fields of characteristic
  other than 2, while the Hamiltonian cycle polynomial is VNP-complete for all
  fields." Section 2.1: "so a circuit for the permanent gives, by substitution,
  circuits of about the same size for them." -/
  | completenessReductionApplies
  /-- Section 2: "Throughout this section we assume that the field of
  coefficients k has characteristic different from two; the last paragraph of
  Section 2.5 treats characteristic two." Section 2.5 is outside the provided
  pages. -/
  | characteristicTwoTreatedSeparately
  /-- Section 1.1: "As (PERM_m) and (HC_m) are in VNP, Theorem 1.1 gives the
  following." -/
  | permanentAndHamiltonianInVnp
  /-- README: "Lean checks the proofs"; "The last command should name no axiom
  other than propext, Classical.choice and Quot.sound."; the CI "re-checks the
  proofs with a second, independently written kernel, nanoda." -/
  | leanKernelAcceptsTheProofs
  /-- Section 1.1: "Section 3 prints the Lean file that states Theorems 1.1 and
  1.4 and Corollary 1.2 from Mathlib alone." Section 1.2 names the exception:
  "this consequence is the one numbered statement of this paper that is not
  formalized in Lean". -/
  | mainResultsAreAmongFormalizedStatements
  /-- README: "Lean checks the proofs, but no machine checks that this file
  says what is claimed."; "no human mathematician has checked the proof.";
  Appendix Q (not provided) "says where they differ". -/
  | leanStatementSaysWhatIsClaimed
  deriving DecidableEq, Repr

def claim1 : Claim Dep Hyp where
  statement :=
    "We prove that every arithmetic circuit that computes the permanent of an m × m matrix over the reals has more than m^(c (log m)^(1/3)) gates, for some constant c > 0 and all sufficiently large m. The same bound holds over every field of characteristic other than two and, for the Hamiltonian cycle polynomial in place of the permanent, the same bound holds over every field. Hence VP ≠ VNP over every field."
  -- The sentence states its model, its fields and its range of m; it does not
  -- say that anything arises by itself.
  kind := .conditional
  used :=
    [ ⟨.arithmeticCircuitModel, .setByExperimenter⟩,
      ⟨.gateCountConvention, .setByExperimenter⟩,
      ⟨.valiantClassDefinitions, .setByExperimenter⟩,
      ⟨.fieldCharacteristic, .measured⟩,
      ⟨.unknownConstantMu, .measured⟩,
      ⟨.flatOrContractingCaseSplit, .setByExperimenter⟩,
      ⟨.auxiliaryPolynomials, .setByExperimenter⟩,
      ⟨.zornsLemmaForSpectralPoints, .setByExperimenter⟩,
      ⟨.leanFormalization, .setByExperimenter⟩ ]
  -- Named in the quote: "arithmetic circuit"; "VP ≠ VNP"; "over the reals",
  -- "characteristic other than two", "every field"; "for some constant c > 0
  -- and all sufficiently large m".
  -- Not named in the quote: Zorn's lemma, and the Lean release. The next
  -- sentence of the abstract (claim 2) does name Lean.
  declared :=
    [ .arithmeticCircuitModel,
      .valiantClassDefinitions,
      .fieldCharacteristic,
      .unknownConstantMu ]
  forgets :=
    [ -- Footnote 2: a factor of at most three leaves the bound as worded.
      ⟨.gateCountConvention, .shown⟩,
      -- Theorem 2.2, and Section 2.2: "The flat case gives the bound ... of
      -- Theorem 1.1 ... and the contracting case gives the stronger bound".
      ⟨.flatOrContractingCaseSplit, .shown⟩,
      -- Section 2.1, "Where the permanent enters" (lem_fkl_perm, lem_circuit):
      -- "a circuit for the permanent gives, by substitution, circuits of about
      -- the same size for them. The Hamiltonian cycle polynomial has the same
      -- property".
      ⟨.auxiliaryPolynomials, .shown⟩ ]
  hypotheses :=
    [ ⟨.oneOfTheTwoCasesHolds, .discharged⟩,
      ⟨.completenessReductionApplies, .discharged⟩,
      ⟨.characteristicTwoTreatedSeparately, .discharged⟩,
      ⟨.permanentAndHamiltonianInVnp, .discharged⟩,
      ⟨.leanKernelAcceptsTheProofs, .discharged⟩,
      ⟨.mainResultsAreAmongFormalizedStatements, .discharged⟩,
      ⟨.leanStatementSaysWhatIsClaimed, .bet⟩ ]
  -- Stated openly in the README, not in the quoted sentences.
  declaredBets := [.leanStatementSaysWhatIsClaimed]

def claim2 : Claim Dep Hyp where
  statement :=
    "The result was discovered by an internal research Claude model and has been formalized in Lean."
  -- An attribution and a status report that name what they lean on (the model,
  -- Lean); the sentence does not say "by itself" or "alone".
  kind := .conditional
  -- For the first half the provided text gives no derivation, only the
  -- attribution itself, so nothing beyond the named model could be recorded.
  used :=
    [ ⟨.internalResearchModel, .setByExperimenter⟩,
      ⟨.leanFormalization, .setByExperimenter⟩ ]
  declared := [.internalResearchModel, .leanFormalization]
  forgets := []
  hypotheses :=
    [ ⟨.leanKernelAcceptsTheProofs, .discharged⟩,
      ⟨.mainResultsAreAmongFormalizedStatements, .discharged⟩,
      ⟨.leanStatementSaysWhatIsClaimed, .bet⟩ ]
  -- Stated openly in the README, not in the quoted sentence.
  declaredBets := [.leanStatementSaysWhatIsClaimed]

#eval audit claim1
#eval verdict claim1
#eval audit claim2
#eval verdict claim2

/-- Both findings are about the wording of the quote: it names neither Zorn's
lemma nor the Lean release. -/
theorem claim1_findings :
    audit claim1 =
      [ .droppedDependency .zornsLemmaForSpectralPoints,
        .droppedDependency .leanFormalization ] := by decide

theorem claim1_verdict : verdict claim1 = .rejected := by decide

theorem claim2_findings : audit claim2 = [] := by decide

theorem claim2_verdict : verdict claim2 = .admissibleOnDeclaredBets := by decide

end EpistemicLedger.Cases.BlindA.VpVnp
