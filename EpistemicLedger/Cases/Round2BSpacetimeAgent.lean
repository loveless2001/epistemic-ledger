import EpistemicLedger.AuditRules

/-
Claim records for "Spacetime Emergence in the Memory of a Learning Agent"
(paper/paper.txt). Two abstract sentences are recorded.
-/
namespace EpistemicLedger.Cases.Round2B.SpacetimeAgent

inductive Dep where
  /-- Sec. I: "generates a transformed quantum mutual-information objective that
  provides the sole reward to a model-based RL agent"; Sec. II: "The core idea of
  our paper is to allow an RL agent to move the second detector ... attempting to
  maximize the quantum mutual information". The task is the authors' choice. -/
  | qmiRewardObjective
  /-- Eq. (42): "To increase the contrast and visibility of the quantum mutual
  information further away from the centre ... we use the normalized power
  transform", p = 1/4; Eq. (43): progress terms 0.02 / -0.05 and boundary penalty. -/
  | powerTransformAndRewardShaping
  /-- Fig. 2: "highlighting the dependence of the quantum mutual information on the
  properties of spacetime through the central, diagonal lightcone ridges"; Sec. I:
  "The underlying spacetime structure is implicitly encoded in this reward". The
  field correlations of the Minkowski vacuum are the object under study. -/
  | minkowskiFieldCorrelations
  /-- Sec. IV: "The detector parameters used for this landscape are T = 0.15,
  σ = 0.15, and λ = 1"; Sec. II: "we will fix λ, σ, T". -/
  | detectorSmearingAndCoupling
  /-- Sec. IV: "the RL agent still receives spacetime coordinates"; Eq. (40):
  o_t = ((x+10)/20, (t+10)/20). -/
  | coordinateObservations
  /-- Eqs. (36)-(41): a 301×301 grid with x, t ∈ [−10, 10], equal spacing Δ in x
  and t, and "the eight nearest-neighbour grid moves" (δx, δt ∈ {−1, 0, 1}). -/
  | gridAndEightNeighbourActions
  /-- Sec. IV, Eq. (56): "the weights attached to the loss function terms are tuned
  so the learning scheme can be successful"; decoder terms "anchor the latent state
  to the observed coordinates"; latent dimension d_z = 20. -/
  | architectureAndLossWeights
  /-- Sec. IV: "Episode starts are sampled uniformly during the first 35% of
  training, from a 70% uniform and 30% edge-biased mixture ..."; "This start
  schedule forces the planner to learn from longer moves". -/
  | startStateCurriculum
  /-- Eq. (61) and Fig. 4: the planner action scores J of the trained agents,
  "the trained planner maps the detector-generated reward landscape to a local
  action flow and a score surface that retain the underlying spacetime features". -/
  | trainedPlannerScores
  /-- Sec. IV: "the final diagnostic fields used for plotting and metric recovery
  are averaged over these trained runs"; footnote 3: fitting "the agents
  separately" was not done. -/
  | fiveAgentAveraging
  /-- Eq. (62): scalar softmax-average score S "with β′ = 2 giving the best
  results for the reconstruction procedure". -/
  | softmaxTemperatureBetaPrime
  /-- Eq. (70): neighbour-comparison mask, cell kept when "its score exceeds that
  of at least 70% of the eight neighbouring cells"; incomplete edge windows
  rejected (Fig. 1 caption). -/
  | neighbourMaskThreshold
  /-- Sec. V: "the lightcone centre is fixed at (xc, tc) = (0, 0)", "rows
  sufficiently close to tc excluded from the fit", widest contiguous run kept
  (Eq. (71)), at most one left and one right point per row. -/
  | branchExtractionRules
  /-- Eqs. (65), (69): least-squares fit of a quadratic null form "with the
  conformal freedom fixed by gxx = 1"; Sec. VI: "the metric tensor is subsequently
  extracted using external tools supplied when studying it, such as lightcone
  masking and conformal gauge fixing". -/
  | quadraticNullFitWithConformalGauge
  /-- Sec. IV: "Every trained RL agent reaches a success rate of 1.0 and a mean
  final objective Ĩ = 1.0"; Fig. 3 learning curves. -/
  | taskSuccess
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Sec. V: "In (1 + 1) dimensions, two null directions determine the conformal
  class of a Lorentzian metric", Eqs. (66)-(68); Sec. I: "null structure determines
  the Lorentzian metric only up to a conformal factor [3, 7, 8]". Holds for the
  flat (1+1) target. -/
  | nullDirectionsFixConformalClass
  /-- Fig. 2 caption: "the diagonal ridge structure associated with the light
  cone"; Sec. VI: the causal structure "is already reflected in the known field
  correlations from which the detector data are generated". Shown for this
  landscape (even though Sec. VI notes QMI "contains ... correlations at spacelike
  separation"). -/
  | qmiRidgesTrackLightCone
  /-- Sec. VI: "More robust tests of the reconstruction under coordinate changes
  and different detector smearings should be undertaken ... This would
  substantially strengthen the evidence that the learned relations represent
  spacetime structure as opposed to contingent properties of the chosen
  coordinates or probes." Not checked; openly stated. -/
  | structureNotContingentOnCoordinatesOrProbes
  deriving DecidableEq, Repr

/-- Dependencies shared by both claims: the training setup and the readout. -/
def setupAndReadout : List (Dependency Dep) :=
  [ ⟨.qmiRewardObjective, .setByExperimenter⟩,
    ⟨.powerTransformAndRewardShaping, .setByExperimenter⟩,
    ⟨.minkowskiFieldCorrelations, .measured⟩,
    ⟨.detectorSmearingAndCoupling, .setByExperimenter⟩,
    ⟨.coordinateObservations, .setByExperimenter⟩,
    ⟨.gridAndEightNeighbourActions, .setByExperimenter⟩,
    ⟨.architectureAndLossWeights, .setByExperimenter⟩,
    ⟨.startStateCurriculum, .setByExperimenter⟩,
    ⟨.trainedPlannerScores, .measured⟩,
    ⟨.fiveAgentAveraging, .setByExperimenter⟩,
    ⟨.softmaxTemperatureBetaPrime, .setByExperimenter⟩,
    ⟨.neighbourMaskThreshold, .setByExperimenter⟩,
    ⟨.branchExtractionRules, .setByExperimenter⟩,
    ⟨.quadraticNullFitWithConformalGauge, .setByExperimenter⟩ ]

/-- Every dependency above is stated somewhere in the paper (Secs. II, IV, V, VI). -/
def setupAndReadoutIds : List Dep :=
  setupAndReadout.map (·.id)

def sharedHypotheses : List (Hypothesis Hyp) :=
  [ ⟨.nullDirectionsFixConformalClass, .discharged⟩,
    ⟨.qmiRidgesTrackLightCone, .discharged⟩,
    ⟨.structureNotContingentOnCoordinatesOrProbes, .bet⟩ ]

def claim1 : Claim Dep Hyp where
  statement := "We show that the causal structure of spacetime can emerge within the memory of a learning agent performing a quantum information task."
  kind := .intrinsic
  used := setupAndReadout
  declared := setupAndReadoutIds
  forgets := []
  hypotheses := sharedHypotheses
  declaredBets := [.structureNotContingentOnCoordinatesOrProbes]

def claim2 : Claim Dep Hyp where
  statement := "Within this task, spacetime geometry is obtained from an agent's successful predictions and actions, providing a first step toward showing that spacetime concepts emerge from operational quantum experience."
  kind := .conditional
  used := setupAndReadout ++ [⟨.taskSuccess, .measured⟩]
  declared := setupAndReadoutIds ++ [.taskSuccess]
  forgets := []
  hypotheses := sharedHypotheses
  declaredBets := [.structureNotContingentOnCoordinatesOrProbes]

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

end EpistemicLedger.Cases.Round2B.SpacetimeAgent
