import EpistemicLedger.AuditRules

/-
Claim record for "Testing the problem of time with cold atoms" (cold-atom
analogue of relational / entropic time). Records what the paper's derivations
lean on; it does not judge truth.
-/
namespace EpistemicLedger.Cases.BlindB.Barontini

inductive Dep where
  /-- "The trap is made by crossing a beam at 1070 nm and one at 1550 nm,
  resulting in final trapping frequencies of ≃ 2π × (25, 70, 70) Hz." -/
  | trapGeometry
  /-- "In the plane x = 0, a thin potential barrier with a width of ≃ 8 µm is
  generated using a digital micromirror device." The barrier defines the
  'dark' (unobserved) and 'bright' (observed) sectors. -/
  | barrierPartitionIntoSectors
  /-- "We repeat the measurement for different values of the height of the
  potential barrier, therefore changing the exchange of entropy between the
  sectors." Cycles only for low V; "For V≃ 1 ... no longer cyclic". -/
  | barrierHeightV
  /-- "we identify one of the analogous fields as a clock"; "we implicitly took
  ϕ as the clock field, through the relations N = N (ϕ) and Σ = Σ(ϕ)." -/
  | clockFieldChoicePhi
  /-- Eq. (3): τ(λ) = σ/k_B ∫ (dS/dϕ)|dϕ|, defined "in analogy with what is done
  in stochastic systems [34]". -/
  | entropicTimeDefinitionEq3
  /-- "σ the (arbitrary) entropic time unit" (Eq. 3). -/
  | entropicTimeUnitSigma
  /-- "the entropy per atom s by utilizing the method of [35], from which we
  derive S = N s [36]" (external estimator, chosen by the author). -/
  | entropyEstimatorMethodRef35
  /-- "we follow the dynamics in lab time for 120 ms, taking an absorption image
  every 2 ms"; wiggles "caused by the coarse sampling in the clock field ϕ". -/
  | imagingSamplingSchedule
  /-- Eq. (3) is an integral along the trajectory λ, evaluated over the image
  sequence acquired in lab time: "Starting from the first big bang, we compute
  τ according to Eq. (3)"; Fig. 2 plots τ "as a function of the external lab
  time". (Inferred: the paper gives no other way to sequence the images.) -/
  | labTimeSequenceOfImages
  /-- "Starting from the first big bang, we compute τ according to Eq. (3)." -/
  | integrationStartAtFirstBigBang
  /-- "For each image we measure N and ϕ by calculating the integral and the
  center of mass of the density profiles". -/
  | atomNumberN
  /-- Same sentence: ϕ = X centre of mass of the bright-sector condensate. -/
  | centerOfMassPhi
  /-- "the entropy per atom s by utilizing the method of [35]". -/
  | entropyPerAtomS
  /-- "For each image we also measure the standard deviation Σ of the density
  profile." -/
  | condensateWidthSigma
  /-- "the system does not experience any measurable dissipation or particle
  loss." -/
  | noDissipationCheck
  /-- "we have verified that, within our errorbars, the entropy of the whole
  mini-universe (dark and bright sector) is constant." -/
  | totalEntropyConstancyCheck
  /-- Eq. (2): GP Hamiltonian with "the average density" in the interaction term
  and "spherical instead of axial coordinates". -/
  | reducedMeanFieldModelEq2
  /-- "we make the approximation M (ϕ) = αϕ"; "From the experimental data we
  infer α ≃ 5 × 10^8 m−1 kg". -/
  | fittedAlpha
  /-- "From the experimental data we infer ... the behavior of the entropy
  dependent pump Λ." -/
  | inferredLambdaPump
  /-- "Using a Feshbach-Villars decomposition ... keeping only the 'positive'
  onward-in-time solutions [33]". -/
  | positiveBranchSelection
  /-- "Performing a simple Taylor expansion we then obtain the entropic time
  Schrödinger equation" (Eq. 6). -/
  | taylorExpansionEq6
  /-- "As initial state we choose a simple Gaussian with width equal to the
  harmonic oscillator length." -/
  | initialGaussianState
  /-- "split-step-Fourier method on a grid of 8192 sites of total length 200 µm.
  The time step used is dτ = 25 σ". -/
  | numericalGridAndStep
  /-- "We then fit the density profiles with a Gaussian function and we plot in
  Fig. 3 b) the values obtained for the standard deviation Σ". -/
  | gaussianFitOfSimulatedProfiles
  /-- Simulation only for one setting: "concentrating as an example on the case
  V ≃ 0". -/
  | simulationOnlyAtVZero
  deriving DecidableEq, Repr

inductive Hyp where
  /-- "This definition ensures that, as long as dS and dϕ have the same sign, the
  arrow of time does not change direction." Record: "With the exception of a few
  'wiggles' where dS and dϕ change sign". -/
  | dSdPhiSameSignAlongData
  /-- Wiggles "caused by the coarse sampling in the clock field ϕ": asserted, no
  finer-sampling test reported. -/
  | wigglesAreSamplingArtefacts
  /-- Method of [35] ("Entropy of a turbulent Bose-Einstein condensate") applied
  to this condensate; no validation for this system reported. -/
  | entropyEstimatorValidHere
  /-- "the system does not experience any measurable dissipation or particle
  loss ... it is essentially a closed system". -/
  | systemIsolated
  /-- "we have verified that, within our errorbars, the entropy of the whole
  mini-universe ... is constant." -/
  | totalEntropyConserved
  /-- "This approximation, and the use of spherical instead of axial
  coordinates, greatly simplify the notation without affecting the physical
  content." Asserted, not shown. -/
  | reducedModelApproxHarmless
  /-- "M (ϕ) = αϕ, which for our case is well justified." Asserted, not shown. -/
  | linearMassApproxHolds
  /-- Eq. (2) "structurally similar to a WDW minisuperspace model"; kinetic sign
  differs, argued "does not affect the phenomenology". Not tested. -/
  | minisuperspaceAnalogyHolds
  /-- Only one construction (entropic time, ϕ clock) tested; other constructions
  (multiple clocks, bounces, ...) listed as future examples (outlook). -/
  | testabilityExtendsToOtherConstructions
  deriving DecidableEq, Repr

def claim1 : Claim Dep Hyp where
  statement := "These results establish a controlled experimental setting in which relational-time constructions can be quantitatively tested."
  kind := .conditional
  used :=
    [ ⟨.trapGeometry, .setByExperimenter⟩,
      ⟨.barrierPartitionIntoSectors, .setByExperimenter⟩,
      ⟨.barrierHeightV, .setByExperimenter⟩,
      ⟨.clockFieldChoicePhi, .setByExperimenter⟩,
      ⟨.entropicTimeDefinitionEq3, .setByExperimenter⟩,
      ⟨.entropicTimeUnitSigma, .setByExperimenter⟩,
      ⟨.entropyEstimatorMethodRef35, .setByExperimenter⟩,
      ⟨.imagingSamplingSchedule, .setByExperimenter⟩,
      ⟨.labTimeSequenceOfImages, .setByExperimenter⟩,
      ⟨.integrationStartAtFirstBigBang, .setByExperimenter⟩,
      ⟨.atomNumberN, .measured⟩,
      ⟨.centerOfMassPhi, .measured⟩,
      ⟨.entropyPerAtomS, .measured⟩,
      ⟨.condensateWidthSigma, .measured⟩,
      ⟨.noDissipationCheck, .measured⟩,
      ⟨.totalEntropyConstancyCheck, .measured⟩,
      ⟨.reducedMeanFieldModelEq2, .setByExperimenter⟩,
      ⟨.fittedAlpha, .measured⟩,
      ⟨.inferredLambdaPump, .measured⟩,
      ⟨.positiveBranchSelection, .setByExperimenter⟩,
      ⟨.taylorExpansionEq6, .setByExperimenter⟩,
      ⟨.initialGaussianState, .setByExperimenter⟩,
      ⟨.numericalGridAndStep, .setByExperimenter⟩,
      ⟨.gaussianFitOfSimulatedProfiles, .setByExperimenter⟩,
      ⟨.simulationOnlyAtVZero, .setByExperimenter⟩ ]
  -- "controlled experimental setting" admits the apparatus knobs; "these
  -- results" admits the measured outputs; "relational-time constructions"
  -- admits the construction that was tested.
  declared :=
    [ .trapGeometry, .barrierPartitionIntoSectors, .barrierHeightV,
      .clockFieldChoicePhi, .entropicTimeDefinitionEq3,
      .atomNumberN, .centerOfMassPhi, .entropyPerAtomS, .condensateWidthSigma,
      .noDissipationCheck, .totalEntropyConstancyCheck ]
  -- τ is linear in the arbitrary positive unit σ (Eq. 3): ordering unchanged.
  forgets := [⟨.entropicTimeUnitSigma, .shown⟩]
  hypotheses :=
    [ ⟨.systemIsolated, .discharged⟩,
      ⟨.totalEntropyConserved, .discharged⟩,
      ⟨.dSdPhiSameSignAlongData, .knownFalse⟩,
      ⟨.wigglesAreSamplingArtefacts, .bet⟩,
      ⟨.entropyEstimatorValidHere, .bet⟩,
      ⟨.reducedModelApproxHarmless, .bet⟩,
      ⟨.linearMassApproxHolds, .bet⟩,
      ⟨.minisuperspaceAnalogyHolds, .bet⟩,
      ⟨.testabilityExtendsToOtherConstructions, .bet⟩ ]
  declaredBets := []

def claim2 : Claim Dep Hyp where
  statement := "Motivated by relational-time approaches discussed in the Wheeler-DeWitt framework, we ask whether the dynamics of the observed sector can be ordered using only internal degrees of freedom. To this end, we construct an entropic time from an experimentally defined coarse-grained entropy, and demonstrate that it can robustly order the events in the observed sector across repeated cycles of expansion and recollapse."
  -- "ordered using only internal degrees of freedom": worded as arising from
  -- the object of study alone.
  kind := .intrinsic
  used :=
    [ ⟨.trapGeometry, .setByExperimenter⟩,
      ⟨.barrierPartitionIntoSectors, .setByExperimenter⟩,
      ⟨.barrierHeightV, .setByExperimenter⟩,
      ⟨.clockFieldChoicePhi, .setByExperimenter⟩,
      ⟨.entropicTimeDefinitionEq3, .setByExperimenter⟩,
      ⟨.entropicTimeUnitSigma, .setByExperimenter⟩,
      ⟨.entropyEstimatorMethodRef35, .setByExperimenter⟩,
      ⟨.imagingSamplingSchedule, .setByExperimenter⟩,
      ⟨.labTimeSequenceOfImages, .setByExperimenter⟩,
      ⟨.integrationStartAtFirstBigBang, .setByExperimenter⟩,
      ⟨.atomNumberN, .measured⟩,
      ⟨.centerOfMassPhi, .measured⟩,
      ⟨.entropyPerAtomS, .measured⟩,
      ⟨.noDissipationCheck, .measured⟩,
      ⟨.totalEntropyConstancyCheck, .measured⟩ ]
  -- "observed sector", "entropic time", "experimentally defined coarse-grained
  -- entropy", "internal degrees of freedom".
  declared :=
    [ .barrierPartitionIntoSectors, .entropicTimeDefinitionEq3,
      .entropyEstimatorMethodRef35, .atomNumberN, .centerOfMassPhi,
      .entropyPerAtomS ]
  forgets := [⟨.entropicTimeUnitSigma, .shown⟩]
  hypotheses :=
    [ ⟨.systemIsolated, .discharged⟩,
      ⟨.totalEntropyConserved, .discharged⟩,
      ⟨.dSdPhiSameSignAlongData, .knownFalse⟩,
      ⟨.wigglesAreSamplingArtefacts, .bet⟩,
      ⟨.entropyEstimatorValidHere, .bet⟩ ]
  declaredBets := []

#eval audit claim1
#eval verdict claim1
#eval audit claim2
#eval verdict claim2

theorem claim1_verdict : verdict claim1 = .rejected := by decide
theorem claim2_verdict : verdict claim2 = .rejected := by decide

end EpistemicLedger.Cases.BlindB.Barontini
