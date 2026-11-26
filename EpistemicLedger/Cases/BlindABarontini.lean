import EpistemicLedger.AuditRules

/-
Claim records for "Testing the problem of time with cold atoms" (G. Barontini,
arXiv:2509.07745v3), read from `paper/paper.txt` only.

Reading rule used for `declared`: a dependency counts as declared when the
quoted sentence names it, or names a category that plainly contains it
("controlled experimental setting" = apparatus and protocol; "we construct an
entropic time" / "relational-time constructions" = Eq. (3) with its clock
variable and its entropy).
-/
namespace EpistemicLedger.Cases.BlindA.Barontini

inductive Dep where
  /-- "a Bose-Einstein condensate of ≃ 2.4 × 10^4 87Rb atoms oscillates back and
  forth along the x direction in a conservative, radially symmetric, optical
  dipole trap", "final trapping frequencies of ≃ 2π × (25, 70, 70) Hz". -/
  | trapAndCondensatePreparation
  /-- "By using optical dipole potentials, we partition the system into a ’dark
  sector’ and a ’bright sector’"; "In the plane x = 0, a thin potential barrier
  with a width of ≃ 8 µm is generated using a digital micromirror device." -/
  | barrierSectorPartition
  /-- "We repeat the measurement for different values of the height of the
  potential barrier, therefore changing the exchange of entropy between the
  sectors." (Figs. 2 and 3 show every barrier height.) -/
  | barrierHeight
  /-- "we follow the dynamics in lab time for 120 ms, taking an absorption image
  every 2 ms"; the exceptions to the ordering are "caused by the coarse sampling
  in the clock field ϕ". -/
  | labTimeSamplingSchedule
  /-- External lab time as the sequence of the images and as the reference the
  ordering is compared with: "Starting from the first big bang, we compute τ
  according to Eq. (3). For a direct comparison, we report in Fig. 2 the values
  of τ as a function of the external lab time"; "the ordering of the data
  broadly reflects the one in lab time". -/
  | labTimeOrderOfData
  /-- "For each image we measure N and ϕ by calculating the integral and the
  center of mass of the density profiles"; "For each image we also measure the
  standard deviation Σ of the density profile." -/
  | measuredBrightSectorObservables
  /-- "the entropy per atom s by utilizing the method of [35], from which we
  derive S = N s [36]". -/
  | entropyEstimator
  /-- "we identify one of the analogous fields as a clock"; "Above, we implicitly
  took ϕ as the clock field, through the relations N = N(ϕ) and Σ = Σ(ϕ)." -/
  | clockFieldChoice
  /-- Eq. (3): "we define the entropic time for our bright sector as", with "σ
  the (arbitrary) entropic time unit, and λ defines the trajectory of ϕ within
  the bright sector". -/
  | entropicTimeDefinition
  /-- Eq. (2): "We model the bright sector by an effective non-Hermitian
  Hamiltonian"; "In the mean-field regime, Ĥbright is the usual Gross-Pitaevskii
  Hamiltonian". -/
  | effectiveGainLossMeanFieldModel
  /-- "For simplicity, in the interaction term we have used the average density.
  This approximation, and the use of spherical instead of axial coordinates,
  greatly simplify the notation without affecting the physical content." -/
  | sphericalCoordsAndAverageDensity
  /-- "Eq. (2) is structurally similar to a WDW minisuperspace model, with X
  playing the role of a uniform massive scalar field ϕ, and R the one of the
  scale factor a". -/
  | minisuperspaceMapping
  /-- "Using a Feshbach-Villars decomposition for ψ ... and keeping only the
  ’positive’ onward-in-time solutions [33]" (derivation of Eq. (5)). -/
  | positiveBranchSelection
  /-- "From the experimental data we infer α ≃ 5 × 10^8 m^−1 kg". -/
  | inferredMassSlopeAlpha
  /-- "From the experimental data we infer ... the behavior of the entropy
  dependent pump Λ"; "the dynamics is completely dominated by the behavior of
  the Λ pump". -/
  | inferredEntropyPumpLambda
  /-- "a standard split-step-Fourier method on a a grid of 8192 sites of total
  length 200 µm. The time step used is dτ = 25 σ, for a total duration of
  250×10^3 σ." -/
  | numericalSolverSettings
  /-- "As initial state we choose a simple Gaussian with width equal to the
  harmonic oscillator length." -/
  | gaussianInitialState
  /-- "We then fit the density profiles with a Gaussian function and we plot in
  Fig. 3 b) the values obtained for the standard deviation Σ as a function of τ
  (dotted line), finding excellent agreement with our data." -/
  | gaussianFitReadout
  /-- "We can now use Eq. (6) to numerically reproduce our experimental
  observations, concentrating as an example on the case V ≃ 0"; Fig. 3 b)
  caption: "numerical simulations using Eq. (6) with V ≃ 0". -/
  | simulationOnlyAtLowestBarrier
  deriving DecidableEq, Repr

inductive Hyp where
  /-- "On the timescale of interest of this experiment (≃ 100 ms), the system
  does not experience any measurable dissipation or particle loss." -/
  | systemIsolatedOnExperimentTimescale
  /-- "For all our data set, we have verified that, within our errorbars, the
  entropy of the whole mini-universe (dark and bright sector) is constant." -/
  | totalEntropyConstant
  /-- Condition of Eq. (3): "as long as dS and dϕ have the same sign, the arrow
  of time does not change direction". Reported for the data: "τ grows
  monotonically almost everywhere"; "With the exception of a few ’wiggles’
  where dS and dϕ change sign". -/
  | entropyAndClockChangeWithSameSign
  /-- "we make the approximation M(ϕ) = αϕ, which for our case is well
  justified" (stated; no check is reported). -/
  | massLinearInClock
  /-- Taylor expansion behind Eq. (6): "The first term under the square root is
  ≈ N times the second term, therefore it is the dominant one when the system
  is away from the big bang or the big crunch (ϕ ≠ 0)"; Fig. 3 a): "ϕ is bound
  by the thickness of the barrier, so that the bright sector never experiences
  the ’singularity’". -/
  | clockPotentialTermDominates
  /-- "the kinetic term in Eq. 2 is positive-definite, whereas in canonical WDW
  equations the DeWitt metric induces an indefinite (hyperbolic) structure";
  "the positive-definite structure does not affect the phenomenology" (argued,
  not checked). -/
  | kineticSignMismatchImmaterial
  /-- Domain of Eq. (6): "As expected, the equation is not well defined when
  there is no entropy -and therefore time- flow." No check is reported for the
  V ≃ 0 run it is solved on. -/
  | entropyFlowNonzeroWhereEquationApplied
  deriving DecidableEq, Repr

/-- Abstract, last sentence. "These results" = the entropic-time ordering
(Figs. 2, 3) and the entropic-time Schrödinger equation compared with data
(Eq. (6), Fig. 3 b), Fig. 4). -/
def claim1 : Claim Dep Hyp where
  statement := "These results establish a controlled experimental setting in which relational-time constructions can be quantitatively tested."
  kind := .conditional
  used :=
    [ ⟨.trapAndCondensatePreparation, .setByExperimenter⟩,
      ⟨.barrierSectorPartition, .setByExperimenter⟩,
      ⟨.barrierHeight, .setByExperimenter⟩,
      ⟨.labTimeSamplingSchedule, .setByExperimenter⟩,
      ⟨.labTimeOrderOfData, .setByExperimenter⟩,
      ⟨.measuredBrightSectorObservables, .measured⟩,
      ⟨.entropyEstimator, .setByExperimenter⟩,
      ⟨.clockFieldChoice, .setByExperimenter⟩,
      ⟨.entropicTimeDefinition, .setByExperimenter⟩,
      ⟨.effectiveGainLossMeanFieldModel, .setByExperimenter⟩,
      ⟨.sphericalCoordsAndAverageDensity, .setByExperimenter⟩,
      ⟨.minisuperspaceMapping, .setByExperimenter⟩,
      ⟨.positiveBranchSelection, .setByExperimenter⟩,
      ⟨.inferredMassSlopeAlpha, .measured⟩,
      ⟨.inferredEntropyPumpLambda, .measured⟩,
      ⟨.numericalSolverSettings, .setByExperimenter⟩,
      ⟨.gaussianInitialState, .setByExperimenter⟩,
      ⟨.gaussianFitReadout, .setByExperimenter⟩,
      ⟨.simulationOnlyAtLowestBarrier, .setByExperimenter⟩ ]
  -- "controlled experimental setting": apparatus, protocol, lab time, data.
  -- "relational-time constructions": Eq. (3) with its clock and its entropy.
  declared :=
    [ .trapAndCondensatePreparation,
      .barrierSectorPartition,
      .barrierHeight,
      .labTimeSamplingSchedule,
      .labTimeOrderOfData,
      .measuredBrightSectorObservables,
      .entropyEstimator,
      .clockFieldChoice,
      .entropicTimeDefinition ]
  -- Barrier height: ordering shown at every height (Figs. 2, 3).
  -- Coordinates / average density: "without affecting the physical content",
  -- stated without a check.
  forgets :=
    [ ⟨.barrierHeight, .shown⟩,
      ⟨.sphericalCoordsAndAverageDensity, .notShown⟩ ]
  hypotheses :=
    [ ⟨.systemIsolatedOnExperimentTimescale, .discharged⟩,
      ⟨.totalEntropyConstant, .discharged⟩,
      ⟨.entropyAndClockChangeWithSameSign, .knownFalse⟩,
      ⟨.massLinearInClock, .bet⟩,
      ⟨.clockPotentialTermDominates, .discharged⟩,
      ⟨.kineticSignMismatchImmaterial, .bet⟩,
      ⟨.entropyFlowNonzeroWhereEquationApplied, .bet⟩ ]
  declaredBets := []

#eval audit claim1
#eval verdict claim1

theorem claim1_verdict : verdict claim1 = .rejected := by decide

/-- Abstract, third and fourth sentences. Worded as an ordering "using only
internal degrees of freedom", hence `intrinsic`. Evidence: Eq. (3), Figs. 2, 3. -/
def claim2 : Claim Dep Hyp where
  statement := "Motivated by relational-time approaches discussed in the Wheeler-DeWitt framework, we ask whether the dynamics of the observed sector can be ordered using only internal degrees of freedom. To this end, we construct an entropic time from an experimentally defined coarse-grained entropy, and demonstrate that it can robustly order the events in the observed sector across repeated cycles of expansion and recollapse."
  kind := .intrinsic
  used :=
    [ ⟨.trapAndCondensatePreparation, .setByExperimenter⟩,
      ⟨.barrierSectorPartition, .setByExperimenter⟩,
      ⟨.barrierHeight, .setByExperimenter⟩,
      ⟨.labTimeSamplingSchedule, .setByExperimenter⟩,
      ⟨.labTimeOrderOfData, .setByExperimenter⟩,
      ⟨.measuredBrightSectorObservables, .measured⟩,
      ⟨.entropyEstimator, .setByExperimenter⟩,
      ⟨.clockFieldChoice, .setByExperimenter⟩,
      ⟨.entropicTimeDefinition, .setByExperimenter⟩ ]
  -- "the observed sector"; "internal degrees of freedom"; "we construct an
  -- entropic time from an experimentally defined coarse-grained entropy".
  declared :=
    [ .barrierSectorPartition,
      .measuredBrightSectorObservables,
      .entropyEstimator,
      .clockFieldChoice,
      .entropicTimeDefinition ]
  -- Barrier height: ordering shown at every height (Figs. 2, 3).
  -- Sampling: exceptions attributed to "the coarse sampling in the clock field
  -- ϕ"; no run with another sampling is reported.
  -- Lab time: offered as replaceable ("an internal ordering parameter can
  -- replace the external one"); τ is computed on, and compared with, the
  -- lab-time sequence of images, and no construction without it is reported.
  forgets :=
    [ ⟨.barrierHeight, .shown⟩,
      ⟨.labTimeSamplingSchedule, .notShown⟩,
      ⟨.labTimeOrderOfData, .notShown⟩ ]
  hypotheses :=
    [ ⟨.systemIsolatedOnExperimentTimescale, .discharged⟩,
      ⟨.totalEntropyConstant, .discharged⟩,
      ⟨.entropyAndClockChangeWithSameSign, .knownFalse⟩ ]
  declaredBets := []

#eval audit claim2
#eval verdict claim2

theorem claim2_verdict : verdict claim2 = .rejected := by decide

end EpistemicLedger.Cases.BlindA.Barontini
