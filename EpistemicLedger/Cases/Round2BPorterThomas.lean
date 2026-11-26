import EpistemicLedger.AuditRules

/-
Blind record: "Fermionic Porter–Thomas statistics and their emergence in random
matchgate circuits" (paper/paper.txt). Two abstract claims.
-/
namespace EpistemicLedger.Cases.Round2B.PorterThomas

inductive Dep where
  /-- Setup: "A random FGS is obtained by drawing Q from the Haar measure on
  SO(2L)" and "a random one is obtained by drawing V from the Haar measure on
  U(L)". The ensemble defining "random" is the author's choice. -/
  | haarEnsembleOfGaussianStates
  /-- Intro: "the distribution of their outcome probabilities in the
  occupation-number basis"; Setup: "The computational basis corresponds to the
  Fock states". The statistics are those of this basis. -/
  | occupationNumberBasis
  /-- Eq. (1): "X is the set of allowed bitstrings and D = |X|. Specifically,
  D = 2^(L-1) for FGS in the even (or odd) parity sector, and D = (L choose N)
  in the particle-number-conserving case." The rescaling w = D p and the
  restriction to the allowed sector define what "the analogue" is. -/
  | allowedSectorAndRescaling
  /-- Prop. 1: "w = D ∏ B_j, with B_j ∼ Beta(j, L − N)"; Eq. (2) "at large L and
  fixed density ν = N/L". The number-preserving law depends on the chosen
  particle number N. -/
  | particleNumberN
  /-- Conclusions: "For noiseless sampling (p̃ = p) it equals E[w²]−1". The
  sampled distribution is set to the ideal one. -/
  | noiselessSampling
  /-- Conclusions: "linear cross-entropy benchmark XEB = D E_{x∼p̃}[p_x] − 1,
  commonly used to certify sampling experiments". The score definition is chosen. -/
  | linearXebDefinition
  /-- Conclusions: "we propose the log-based score logXEB = E_{x∼p̃}[ln w_x]". -/
  | logXebDefinition
  /-- Conclusions: "logXEB = ... for uniform sampling, p̃ = 1/D. The gap ∆ ...
  can be used to normalize the score F = (logXEB − logXEB_unif)/∆". The uniform
  reference point of the normalization is chosen. -/
  | uniformSamplingReference
  /-- Conclusions: "Using Proposition 2, for random FGS we find logXEB = ...";
  Fig. 1d "Second moment E[w²] for generic FGS ... grows as ∼ √L". The XEB and
  logXEB values are computed on the generic (non-number-preserving) Haar
  ensemble. -/
  | genericFgsSecondMomentAndLogMean
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Sec. "Number-preserving FGSs": "Permutation matrices leave the Haar
  measure invariant, so we can always reduce to study ... the top N×N minor";
  End Matter proof of Prop. 2: "By Haar invariance, all even bitstrings are
  equivalent". -/
  | haarInvarianceReducesToOneBitstring
  /-- End Matter, proof of Prop. 1: "for a uniform random unit vector v ∈ C^L,
  the weight on N components is Beta-distributed: Beta(N, L − N)" (standard
  fact, used as a lemma). -/
  | uniformVectorWeightIsBeta
  /-- End Matter, proof of Prop. 2, Step 1: "|ψ′⟩ is Gaussian, as Π = lim
  e^{−β c†c} is a limit of exponentials of quadratic operators [55]". -/
  | projectedStateStaysGaussian
  /-- End Matter, proof of Prop. 2, Steps 2–3: last column of Γ "is distributed
  uniformly on this sphere"; "q ∼ Beta(L − 1, L − 1)"; "|ψ′⟩ is independent of
  q". -/
  | iterationFactorsIndependent
  /-- Conclusions: "Free-fermion circuits, though classically simulable, thus
  reach large XEB scores"; circuit outputs approach the random-FGS law:
  Perron–Frobenius "P∞(π) = 1/(2L − 1)!! is the unique stationary state",
  3-design argument for Z_t, Fig. 2, Theorem. -/
  | circuitOutputsReachRandomFgsLaw
  /-- Conclusions: "beyond the global depolarizing case where it is exact"
  (asserted; logXEB is linear in p̃, so F is exact for p̃ = F p + (1−F)/D). -/
  | fExactUnderGlobalDepolarizing
  /-- Conclusions: "It remains to be studied whether F provides a faithful
  estimate of the fidelity under realistic noise models". -/
  | fFaithfulUnderRealisticNoise
  deriving DecidableEq, Repr

/-- Claim 1. -/
def claim1 : Claim Dep Hyp where
  statement := "We derive the exact analogue of the Porter--Thomas law for random fermionic Gaussian states, both with and without particle-number conservation."
  kind := .conditional
  used :=
    [ ⟨.haarEnsembleOfGaussianStates, .setByExperimenter⟩,
      ⟨.occupationNumberBasis, .setByExperimenter⟩,
      ⟨.allowedSectorAndRescaling, .setByExperimenter⟩,
      ⟨.particleNumberN, .setByExperimenter⟩ ]
  declared :=
    [ .haarEnsembleOfGaussianStates, .occupationNumberBasis,
      .allowedSectorAndRescaling, .particleNumberN ]
  forgets := []
  hypotheses :=
    [ ⟨.haarInvarianceReducesToOneBitstring, .discharged⟩,
      ⟨.uniformVectorWeightIsBeta, .discharged⟩,
      ⟨.projectedStateStaysGaussian, .discharged⟩,
      ⟨.iterationFactorsIndependent, .discharged⟩ ]
  declaredBets := []

/-- Claim 2. -/
def claim2 : Claim Dep Hyp where
  statement := "Finally, we show that ideal free-fermion sampling yields large linear cross-entropy scores, and propose a log-based benchmark with an exact fermionic normalization."
  kind := .conditional
  used :=
    [ ⟨.noiselessSampling, .setByExperimenter⟩,
      ⟨.haarEnsembleOfGaussianStates, .setByExperimenter⟩,
      ⟨.occupationNumberBasis, .setByExperimenter⟩,
      ⟨.linearXebDefinition, .setByExperimenter⟩,
      ⟨.logXebDefinition, .setByExperimenter⟩,
      ⟨.uniformSamplingReference, .setByExperimenter⟩,
      ⟨.genericFgsSecondMomentAndLogMean, .setByExperimenter⟩ ]
  declared :=
    [ .noiselessSampling, .haarEnsembleOfGaussianStates, .occupationNumberBasis,
      .linearXebDefinition, .logXebDefinition, .uniformSamplingReference,
      .genericFgsSecondMomentAndLogMean ]
  forgets := []
  hypotheses :=
    [ ⟨.circuitOutputsReachRandomFgsLaw, .discharged⟩,
      ⟨.fExactUnderGlobalDepolarizing, .discharged⟩,
      ⟨.fFaithfulUnderRealisticNoise, .bet⟩ ]
  declaredBets := [.fFaithfulUnderRealisticNoise]

#eval audit claim1
#eval verdictV1 claim1
#eval rule4Fired claim1
#eval audit claim2
#eval verdictV1 claim2
#eval rule4Fired claim2

theorem claim1_v1 : verdictV1 claim1 = .passed := by decide
theorem claim1_rule4 : rule4Fired claim1 = false := by decide
theorem claim2_v1 : verdictV1 claim2 = .passed := by decide
theorem claim2_rule4 : rule4Fired claim2 = false := by decide

end EpistemicLedger.Cases.Round2B.PorterThomas
