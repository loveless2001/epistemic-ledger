import EpistemicLedger.AuditRules

/-
Blind record for "Fermionic Porter–Thomas statistics and their emergence in
random matchgate circuits" (paper/paper.txt). Two claims, both verbatim
sentences of the abstract. The record says what each claim's derivation leaned
on, as stated in the paper; it does not say whether the claims are true.
-/
namespace EpistemicLedger.Cases.Round2A.PorterThomas

inductive Dep where
  /-- Setup: "A random FGS is obtained by drawing Q from the Haar measure on
  SO(2L)" and, number-preserving case, "a random one is obtained by drawing V
  from the Haar measure on U(L)". All expectations E[...] are averages over
  this ensemble (Eq. 1). -/
  | haarEnsembleOfGaussianStates
  /-- Introduction: "the distribution of their outcome probabilities in the
  occupation-number basis"; Setup: "The computational basis corresponds to the
  Fock states". -/
  | occupationNumberBasis
  /-- Setup, below Eq. (1): "D = 2^(L-1) for FGS in the even (or odd) parity
  sector, and D = (L choose N) in the particle-number-conserving case";
  w = D p. Fixes the particle number N or the parity sector, and the rescaling. -/
  | symmetrySectorAndDimension
  /-- PT statistics section: "Permutation matrices leave the Haar measure
  invariant, so we can always reduce to study the distribution of
  w = D|det T|^2 with T = V[[N],[N]] the top N x N minor"; End Matter, proof of
  Prop. 2: "By Haar invariance, all even bitstrings are equivalent, so we
  consider p_psi(0)." -/
  | referenceBitstring
  /-- PT statistics section: "The bitstring probabilities are given by the
  Slater determinant"; End Matter, proof of Prop. 2: "We use the covariance
  matrix ... for a pure Gaussian state it is also orthogonal". -/
  | gaussianDeterminantStructure
  /-- Conclusions: "For noiseless sampling (p~ = p) it equals E[w^2]-1". -/
  | noiselessSampling
  /-- Conclusions: "which is 1 for Porter–Thomas but grows as sqrt(L) for
  random FGS"; Fig. 1(d). "Large" is a statement about growth with L. -/
  | systemSize
  /-- Conclusions: "Using Proposition 2, for random FGS we find logXEB = ...";
  Proposition (2): "w = D prod_j B_j, with independent B_j ~ Beta(j, j)". -/
  | betaProductLawOfProposition2
  /-- Conclusions: "for uniform sampling, p~ = 1/D. The gap Delta ... can be
  used to normalize the score F = (logXEB - logXEB_unif)/Delta, which then
  interpolates between 0 and 1." -/
  | uniformSamplingReference
  deriving DecidableEq, Repr

inductive Hyp where
  /-- End Matter, proof of Prop. 1: "for a uniform random unit vector v in C^L,
  the weight on N components is Beta-distributed"; proof of Prop. 2, Step 2:
  "So the law of v is the uniform probability measure on S^(2L-2), the only
  rotation-invariant one." -/
  | peeledVectorIsUniformOnSphere
  /-- End Matter, proof of Prop. 1: "Conditional on v1, the columns v2, ..., vN
  are Haar-random orthonormal vectors in v1-perp ... independently of c";
  proof of Prop. 2, Step 3: "since this does not depend on q, |psi'> is
  independent of q, and p'_0 has the law of p_0 for L-1 modes." -/
  | remainderIsIndependentAndHaar
  /-- End Matter, proof of Prop. 2, Step 1: "Notice that |psi'> is Gaussian, as
  Pi = lim exp(-beta c_L^dag c_L) is a limit of exponentials of quadratic
  operators [55]. Moreover, it is even." -/
  | projectedStateRemainsGaussian
  /-- Hypothesis of Prop. 2 for the sampled states. Conclusions: "grows as
  sqrt(L) for random FGS. Free-fermion circuits, though classically simulable,
  thus reach large XEB scores"; circuits section: "by the Perron–Frobenius
  theorem P_inf(pi) = 1/(2L-1)!! is the unique stationary state" and "matchgate
  circuits need a depth t ~ L^2 to reach the fermionic Porter–Thomas law." -/
  | sampledStatesAreRandomGaussianStates
  /-- Conclusions: "It remains to be studied whether F provides a faithful
  estimate of the fidelity under realistic noise models, beyond the global
  depolarizing case where it is exact." -/
  | scoreTracksFidelityUnderRealisticNoise
  deriving DecidableEq, Repr

/-- Claim 1. Worded as a derivation for a named ensemble in two named settings:
conditional. Derivation = Propositions 1 and 2 with their End Matter proofs. -/
def claim1 : Claim Dep Hyp where
  statement := "We derive the exact analogue of the Porter--Thomas law for random fermionic Gaussian states, both with and without particle-number conservation."
  kind := .conditional
  used :=
    [ ⟨.haarEnsembleOfGaussianStates, .setByExperimenter⟩,
      ⟨.occupationNumberBasis, .setByExperimenter⟩,
      ⟨.symmetrySectorAndDimension, .setByExperimenter⟩,
      ⟨.referenceBitstring, .setByExperimenter⟩,
      ⟨.gaussianDeterminantStructure, .measured⟩ ]
  declared :=
    [ .haarEnsembleOfGaussianStates,
      .occupationNumberBasis,
      .symmetrySectorAndDimension,
      .gaussianDeterminantStructure ]
  forgets := [⟨.referenceBitstring, .shown⟩]
  hypotheses :=
    [ ⟨.peeledVectorIsUniformOnSphere, .discharged⟩,
      ⟨.remainderIsIndependentAndHaar, .discharged⟩,
      ⟨.projectedStateRemainsGaussian, .discharged⟩ ]
  declaredBets := []

/-- Claim 2. "Ideal" names the sampling condition and the second half is a
proposal; nothing is worded as arising by itself: conditional. Derivation =
the Conclusions paragraph, which applies Prop. 2 to the XEB and logXEB scores. -/
def claim2 : Claim Dep Hyp where
  statement := "Finally, we show that ideal free-fermion sampling yields large linear cross-entropy scores, and propose a log-based benchmark with an exact fermionic normalization."
  kind := .conditional
  used :=
    [ ⟨.haarEnsembleOfGaussianStates, .setByExperimenter⟩,
      ⟨.occupationNumberBasis, .setByExperimenter⟩,
      ⟨.symmetrySectorAndDimension, .setByExperimenter⟩,
      ⟨.noiselessSampling, .setByExperimenter⟩,
      ⟨.systemSize, .setByExperimenter⟩,
      ⟨.uniformSamplingReference, .setByExperimenter⟩,
      ⟨.betaProductLawOfProposition2, .measured⟩ ]
  declared :=
    [ .haarEnsembleOfGaussianStates,
      .occupationNumberBasis,
      .symmetrySectorAndDimension,
      .noiselessSampling,
      .systemSize,
      .uniformSamplingReference,
      .betaProductLawOfProposition2 ]
  forgets := []
  hypotheses :=
    [ ⟨.sampledStatesAreRandomGaussianStates, .discharged⟩,
      ⟨.scoreTracksFidelityUnderRealisticNoise, .bet⟩ ]
  declaredBets := [.scoreTracksFidelityUnderRealisticNoise]

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

end EpistemicLedger.Cases.Round2A.PorterThomas
