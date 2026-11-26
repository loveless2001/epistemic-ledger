import EpistemicLedger.AuditRules

/-
Blind record for "Spacetime Emergence in the Memory of a Learning Agent"
(paper/paper.txt). Two abstract sentences, one record each.

Reading in one paragraph: a model-based RL agent moves detector 2 on an (x, t)
grid and is rewarded by a transformed mutual information computed in closed form
for a massless field on Minkowski spacetime. After training, the planner scores
of five agents are averaged, turned into a scalar field S, masked, and a
quadratic form is fitted to the masked ridges, giving null slopes close to ±1.
Both claims rest on this one chain, so they share one `used` list.
-/
namespace EpistemicLedger.Cases.Round2A.SpacetimeAgent

inductive Dep where
  /-- Sec. II: "two qubit UDW detectors interacting with a real massless scalar
  quantum field ϕ̂(x) in 3+1-dimensional Minkowski spacetime", vacuum state, final
  state in closed form (Eq. 12). Sec. VI: "the causal structure is known
  analytically and is already reflected in the known field correlations from
  which the detector data are generated." -/
  | minkowskiVacuumFieldEnvironment
  /-- Sec. IV: "The detector parameters used for this landscape are T = 0.15,
  σ = 0.15, and λ = 1"; Gaussian smearing (Eq. 9), gapless detectors (Ω = 0),
  detector 1 fixed at the origin. Sec. VI: tests under "different detector
  smearings should be undertaken". -/
  | detectorProbeSettings
  /-- Eq. (42)-(43): "To increase the contrast and visibility of the quantum
  mutual information further away from the centre of the spacetime grid ... we
  use the normalized power transform" (p = 1/4), plus progress bonus, penalty
  and boundary penalty. -/
  | rewardTransformAndShaping
  /-- Eq. (36)-(40): 301 × 301 grid, x, t ∈ [−10, 10], normalized coordinates as
  the observation. Sec. IV: "the RL agent still receives spacetime coordinates".
  Fig. 1: the fit uses "displacements measured relative to the fixed detector". -/
  | coordinateGridObservations
  /-- Sec. III-IV, Eq. (56): encoder, decoder, latent dynamics, reward model,
  horizon-1 planner, start-state curriculum; "the weights attached to the loss
  function terms are tuned so the learning scheme can be successful". -/
  | agentArchitectureAndTraining
  /-- Footnote 2: T and σ are written in units of "an arbitrary timescale T0";
  "Our results are valid for any choice of T0 due to the conformal character of
  the massless field." -/
  | timescaleUnitT0
  /-- Sec. IV: "Every trained RL agent reaches a success rate of 1.0"; Fig. 3
  (learning curves); Fig. 5(c) one-step latent dynamics error. -/
  | taskSuccessAndModelDiagnostics
  /-- Fig. 1: "After training: freeze parameters and evaluate the grid";
  Eq. (59), (61): planner action scores of each trained agent at every grid
  point. -/
  | learnedPlannerScoreFields
  /-- Sec. IV: "the final diagnostic fields used for plotting and metric recovery
  are averaged over these trained runs" (five seeds, Eq. 61). Footnote 3: "These
  values characterize the fit to the averaged planner field". -/
  | fiveAgentAveraging
  /-- Eq. (62): scalar softmax-average score S, "with β′ = 2 giving the best
  results for the reconstruction procedure". -/
  | softmaxScoreWithTunedBeta
  /-- Eq. (70)-(73): 70% neighbour-comparison mask, row-by-row branch extraction,
  "the lightcone centre is fixed at (xc, tc) = (0, 0)", rows near tc excluded.
  Sec. VI: "extracted using external tools supplied when studying it, such as
  lightcone masking and conformal gauge fixing". -/
  | lightconeMaskAndBranchExtraction
  /-- Eq. (65), (69): one constant quadratic form fitted by least squares to the
  extracted branch points. -/
  | quadraticNullFit
  /-- Sec. V, after Eq. (68): "conformal freedom in the choice of gxx that we
  choose to be gxx = 1". -/
  | conformalGaugeGxxOne
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Abstract: "without directly providing it with information regarding the
  spacetime metric or causal structure". Holds by construction of the agent's
  inputs: normalized coordinates (Eq. 40) and the scalar reward (Eq. 43). -/
  | agentGivenNoDirectMetricOrCausalInput
  /-- Sec. V: "The idea is that this mask will strip away enough of the
  score-field features to leave just the central ridges of the lightcone
  branches". Checked for this target against the known answer: Eq. (74), null
  slopes "v± ≃ (−0.999939, 0.999939)" versus ±1. -/
  | extractedBranchesAreNullDirections
  /-- Sec. V: "In (1 + 1) dimensions, two null directions determine the conformal
  class of a Lorentzian metric". Holds for the flat (1+1) slice used here; Sec. VI
  notes that curved spacetimes "cannot be identified with two globally straight
  lightcone branches like in Minkowski". -/
  | flatOnePlusOneSliceTwoStraightNullBranches
  /-- Sec. VI: tests under coordinate changes and different smearings "should be
  undertaken"; "This would substantially strengthen the evidence that the learned
  relations represent spacetime structure as opposed to contingent properties of
  the chosen coordinates or probes." Not checked in the paper. -/
  | learnedRelationsNotCoordinateOrProbeArtifacts
  deriving DecidableEq, Repr

/-- The one experimental chain both claims are obtained through. -/
def usedByBothClaims : List (Dependency Dep) :=
  [ ⟨.minkowskiVacuumFieldEnvironment, .setByExperimenter⟩,
    ⟨.detectorProbeSettings, .setByExperimenter⟩,
    ⟨.rewardTransformAndShaping, .setByExperimenter⟩,
    ⟨.coordinateGridObservations, .setByExperimenter⟩,
    ⟨.agentArchitectureAndTraining, .setByExperimenter⟩,
    ⟨.timescaleUnitT0, .setByExperimenter⟩,
    ⟨.taskSuccessAndModelDiagnostics, .measured⟩,
    ⟨.learnedPlannerScoreFields, .measured⟩,
    ⟨.fiveAgentAveraging, .setByExperimenter⟩,
    ⟨.softmaxScoreWithTunedBeta, .setByExperimenter⟩,
    ⟨.lightconeMaskAndBranchExtraction, .setByExperimenter⟩,
    ⟨.quadraticNullFit, .setByExperimenter⟩,
    ⟨.conformalGaugeGxxOne, .setByExperimenter⟩ ]

/-- v1: declared = stated anywhere in the paper. Every dependency above is
described in Sec. II-V or admitted in Sec. VI (see the quotes on `Dep`). -/
def statedInPaper : List Dep :=
  [ .minkowskiVacuumFieldEnvironment, .detectorProbeSettings,
    .rewardTransformAndShaping, .coordinateGridObservations,
    .agentArchitectureAndTraining, .timescaleUnitT0,
    .taskSuccessAndModelDiagnostics, .learnedPlannerScoreFields,
    .fiveAgentAveraging, .softmaxScoreWithTunedBeta,
    .lightconeMaskAndBranchExtraction, .quadraticNullFit,
    .conformalGaugeGxxOne ]

/-- Same status for both claims; all statuses are for the Minkowski target. -/
def hypothesesForBothClaims : List (Hypothesis Hyp) :=
  [ ⟨.agentGivenNoDirectMetricOrCausalInput, .discharged⟩,
    ⟨.extractedBranchesAreNullDirections, .discharged⟩,
    ⟨.flatOnePlusOneSliceTwoStraightNullBranches, .discharged⟩,
    ⟨.learnedRelationsNotCoordinateOrProbeArtifacts, .bet⟩ ]

/-
Claim 1. Kind: "emerge within the memory" is "arises internally" wording.

Forget steps the paper offers:
* T0: footnote 2, a symmetry argument (scale invariance of the massless field),
  not a rerun. Recorded as shown.
* Conformal gauge: Eq. (66)-(68), the null slopes depend only on gtt/gxx and
  gtx/gxx, so the asserted property (causal structure) does not change with the
  choice gxx = 1. Recorded as shown.
* Coordinates: Sec. III argues "although the encoder receives detector
  coordinates as input, the latent variables themselves are not amenable to a
  geometric interpretation a priori", but Sec. VI says tests "under coordinate
  changes ... should be undertaken". Recorded as not shown.
-/
def claim1 : Claim Dep Hyp where
  statement := "We show that the causal structure of spacetime can emerge within the memory of a learning agent performing a quantum information task."
  kind := .intrinsic
  used := usedByBothClaims
  declared := statedInPaper
  forgets :=
    [ ⟨.timescaleUnitT0, .shown⟩,
      ⟨.conformalGaugeGxxOne, .shown⟩,
      ⟨.coordinateGridObservations, .notShown⟩ ]
  hypotheses := hypothesesForBothClaims
  declaredBets := [.learnedRelationsNotCoordinateOrProbeArtifacts]

/-
Claim 2. Kind: scoped by "Within this task", the verb is "is obtained from"
(someone obtains it), and the emergence part is hedged as "a first step toward
showing". Recorded as conditional.

No forget step for the conformal gauge here: the asserted property is "spacetime
geometry", and the paper says what it obtains is, "Within the conformal
convention gxx = 1", "a representative of the conformal class". The gauge stays
a declared dependency of this claim.
-/
def claim2 : Claim Dep Hyp where
  statement := "Within this task, spacetime geometry is obtained from an agent's successful predictions and actions, providing a first step toward showing that spacetime concepts emerge from operational quantum experience."
  kind := .conditional
  used := usedByBothClaims
  declared := statedInPaper
  forgets :=
    [ ⟨.timescaleUnitT0, .shown⟩,
      ⟨.coordinateGridObservations, .notShown⟩ ]
  hypotheses := hypothesesForBothClaims
  declaredBets := [.learnedRelationsNotCoordinateOrProbeArtifacts]

#eval audit claim1
#eval verdictV1 claim1
#eval rule4Fired claim1

#eval audit claim2
#eval verdictV1 claim2
#eval rule4Fired claim2

theorem claim1_v1 : verdictV1 claim1 = .rejected := by decide
theorem claim1_rule4 : rule4Fired claim1 = true := by decide

theorem claim2_v1 : verdictV1 claim2 = .passed := by decide
theorem claim2_rule4 : rule4Fired claim2 = false := by decide

end EpistemicLedger.Cases.Round2A.SpacetimeAgent
