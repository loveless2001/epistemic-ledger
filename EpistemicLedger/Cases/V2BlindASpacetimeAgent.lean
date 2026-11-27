import EpistemicLedger.OperationFlow

/-
Blind flow record for paper/paper.txt:
"Spacetime Emergence in the Memory of a Learning Agent".

The study is a numerical one: a model-based reinforcement-learning agent moves
detector 2 on a grid of (x, t) smearing centres and is rewarded with a function
of the detector pair's quantum mutual information; afterwards the authors read a
quadratic form off the trained planner's score field. One graph serves both
claims. All quotes are from paper/paper.txt (line-break hyphens removed).

Reading choices that are mine (also listed in the reply):
* Every entry node is `setByExperimenter`: the environment is computed from
  closed-form expressions (Sec. II, Eq. (12)-(20)); nothing is read off a
  physical system.
* Claim 2 is recorded as `conditionalFlow`. A source counts as declared when
  the paper states it as something the result was obtained through, anywhere in
  the paper (the guidance on `declared` in ClaimRecordTypes.lean), not only in
  the quoted sentence.
-/
namespace EpistemicLedger.Cases.V2BlindA.SpacetimeAgent

open EpistemicLedger
open EpistemicLedger.OperationFlow

inductive Node where
  /-- Sec. II: "a real massless scalar quantum field ϕ̂(x) in 3+1-dimensional Minkowski
  spacetime"; "ρ̂ϕ is chosen to be the vacuum state of the field". -/
  | minkowskiScalarField
  /-- Sec. II, Eq. (9) (Gaussian spacetime smearing), "trivial internal dynamics, with Ω = 0";
  Sec. IV: "T = 0.15, σ = 0.15, and λ = 1"; Fig. 1: "Detector 1 is fixed at the origin". -/
  | udwDetectorProtocol
  /-- Sec. IV, Eq. (36)-(41): "a 301×301 grid whose cells index spacetime smearing centres";
  "The action set A consists of the eight nearest-neighbour grid moves"; Eq. (40): the
  observation is "the normalized coordinate representation". -/
  | detectorPlacementGrid
  /-- Sec. IV, Eq. (42): "the normalized power transform of the quantum mutual information";
  Eq. (43): "The reward from the environment is comprised of four terms". -/
  | rewardShaping
  /-- Sec. III: "an encoder, decoder, transition model, reward model, and a planning rule that
  combines their predictions into a decision"; Sec. IV, Eq. (56) and the hyperparameter list. -/
  | agentArchitectureAndTraining
  /-- Sec. IV: "Training is performed for five different agent-parameter and environment
  random-generator seed initializations". -/
  | trainingSeeds
  /-- Sec. V, Eq. (62), (70)-(73); Fig. 1: "A cell enters the candidate lightcone mask when its
  score exceeds that of at least 70% of the eight neighbouring cells in a radius-1 square";
  "with β′ = 2 giving the best results for the reconstruction procedure". -/
  | lightconeReadoutRule
  /-- Sec. V, Eq. (65), (69); Fig. 1: "Least squares then fits the quadratic form to the
  extracted branch points, with displacements measured relative to the fixed detector and the
  conformal freedom fixed by gxx = 1". -/
  | quadraticNullFormAnsatz
  /-- Sec. II, Eq. (10), (12)-(20); Sec. IV: "The bare quantum mutual information range is
  [3.1929×10−8 , 6.5477×10−2 ]". -/
  | mutualInformationLandscape
  /-- Sec. IV, Eq. (43); Sec. I: "a transformed quantum mutual-information objective that
  provides the sole reward". -/
  | shapedReward
  /-- Sec. IV: "Experience replay works as a memory buffer that holds observed transitions
  (st , at , rt+1 , st+1 )". -/
  | replayTransitions
  /-- Sec. III: "We will refer to the collection of these learned internal models as the
  agent's memory"; Fig. 1 box "Learned World Model". -/
  | learnedWorldModelMemory
  /-- Sec. V, Eq. (61): "we first average the action scores themselves"; Fig. 1: "After
  training: freeze parameters and evaluate the grid". -/
  | plannerScoreField
  /-- Sec. V, Eq. (72)-(73): "the extracted lightcone branch points (∆ti , ∆xi )". -/
  | lightconeBranchPoints
  /-- Sec. V, Eq. (74): "the resulting coefficients obtained from the five-agent averaged field
  are assembled into the metric representative". -/
  | fittedConformalMetric
  /-- Abstract: "spacetime geometry is obtained"; Sec. V: "recovers a representative of the
  conformal class that closely approximates the Minkowski metric in these coordinates". -/
  | recoveredSpacetimeGeometry
  deriving DecidableEq, Repr

inductive Tag where
  /-- Abstract: "the characteristic null structure of spacetime"; Fig. 2: "the diagonal ridge
  structure associated with the light cone". -/
  | causalNullStructure
  /-- Sec. I: "a Lorentzian metric tensor, which is an object encoding spacetime distances,
  angles, and causal relationships"; Sec. V, Eq. (65) (the quadratic form). -/
  | spacetimeMetricGeometry
  /-- Sec. VI: "contingent properties of the chosen coordinates or probes". -/
  | coordinateAndProbeChoice
  deriving DecidableEq, Repr

def graph : FlowGraph Node Tag where
  sources :=
    [ -- carries: Sec. VI: "the causal structure is known analytically and is already reflected
      -- in the known field correlations from which the detector data are generated";
      -- Sec. II: "the spacetime geometry and field-theoretic quantities from which it is
      -- generated remain directly inaccessible" (it = the reward).
      ⟨.minkowskiScalarField, .setByExperimenter, [.causalNullStructure, .spacetimeMetricGeometry]⟩,
      -- carries: the probe choice. Sec. VI: "More robust tests of the reconstruction under
      -- coordinate changes and different detector smearings should be undertaken".
      ⟨.udwDetectorProtocol, .setByExperimenter, [.coordinateAndProbeChoice]⟩,
      -- carries: the coordinate choice. Sec. IV: "the RL agent still receives spacetime
      -- coordinates"; Eq. (36)-(40).
      ⟨.detectorPlacementGrid, .setByExperimenter, [.coordinateAndProbeChoice]⟩,
      ⟨.rewardShaping, .setByExperimenter, []⟩,
      -- carries nothing: Sec. I: "a model-based RL agent with no initial conception of spacetime".
      ⟨.agentArchitectureAndTraining, .setByExperimenter, []⟩,
      ⟨.trainingSeeds, .setByExperimenter, []⟩,
      -- carries: Sec. V: "the lightcone centre is fixed at (xc , tc ) = (0, 0)" and "at most one
      -- left and one right branch point are retained for each time row"; Sec. VI: "extracted
      -- using external tools supplied when studying it, such as lightcone masking and conformal
      -- gauge fixing".
      ⟨.lightconeReadoutRule, .setByExperimenter, [.causalNullStructure]⟩,
      -- carries: Sec. V, Eq. (65): "determine the coefficients of the quadratic form", with
      -- "conformal freedom in the choice of gxx that we choose to be gxx = 1"; Sec. VI:
      -- "geometrically informed post-processing procedures".
      ⟨.quadraticNullFormAnsatz, .setByExperimenter, [.spacetimeMetricGeometry]⟩ ]
  ops :=
    [ -- Sec. II, Eq. (10)-(20), evaluated on the (1 + 1)-dimensional slice of Sec. IV.
      -- Lossy: Sec. VI: "quantum mutual information is not a pure measure of signalling as it
      -- contains both causally mediated and state-dependent correlations"; further quantities
      -- would be needed "to reconstruct more than just the conformal structure".
      ⟨"evaluate_detector_mutual_information_on_grid",
        [.minkowskiScalarField, .udwDetectorProtocol, .detectorPlacementGrid],
        .mutualInformationLandscape, .lossy []⟩,
      -- Eq. (42)-(43). Sec. IV: "The reward inherits the dependence on spacetime structure from
      -- the quantum mutual information".
      ⟨"shape_reward", [.mutualInformationLandscape, .rewardShaping], .shapedReward, .transform []⟩,
      -- Sec. III-IV: ϵ-greedy interaction; Fig. 1 "Store Transition".
      ⟨"explore_grid_and_store_transitions",
        [.shapedReward, .detectorPlacementGrid, .agentArchitectureAndTraining, .trainingSeeds],
        .replayTransitions, .transform []⟩,
      -- Sec. IV, Eq. (44)-(56): "the minimization of a composite loss function over uniformly
      -- sampled experience replay mini-batches".
      ⟨"minimize_composite_loss_on_replay",
        [.replayTransitions, .agentArchitectureAndTraining, .trainingSeeds],
        .learnedWorldModelMemory, .transform []⟩,
      -- Sec. V, Eq. (59), (61): frozen planners evaluated at every grid point, then averaged
      -- over the five agents.
      ⟨"evaluate_frozen_planners_on_grid_and_average_five_agents",
        [.learnedWorldModelMemory, .detectorPlacementGrid], .plannerScoreField, .transform []⟩,
      -- Sec. V, Eq. (62), (70)-(73). Lossy: "this mask will strip away enough of the score-field
      -- features to leave just the central ridges of the lightcone branches".
      ⟨"softmax_average_neighbour_mask_and_branch_extraction",
        [.plannerScoreField, .lightconeReadoutRule], .lightconeBranchPoints, .lossy []⟩,
      -- Sec. V, Eq. (69), (74).
      ⟨"least_squares_quadratic_form_fit",
        [.lightconeBranchPoints, .quadraticNullFormAnsatz], .fittedConformalMetric, .transform []⟩,
      -- FORGET (coordinate / probe choice), evidence notShown. The fit "in these coordinates"
      -- (Sec. V) is read as "spacetime geometry" (abstract). Sec. VI: "More robust tests of the
      -- reconstruction under coordinate changes and different detector smearings should be
      -- undertaken as well before making this step. This would substantially strengthen the
      -- evidence that the learned relations represent spacetime structure as opposed to
      -- contingent properties of the chosen coordinates or probes." No such test is reported.
      ⟨"read_fit_as_spacetime_geometry_not_coordinate_or_probe_property",
        [.fittedConformalMetric], .recoveredSpacetimeGeometry,
        .forget .coordinateAndProbeChoice .notShown⟩ ]

/-- Worded as emergence ("can emerge within the memory"): the null structure is asserted to
arise in the agent's memory, "without directly providing it with information regarding the
spacetime metric or causal structure" (abstract). -/
def claim1 : FlowClaim Node Tag where
  statement := "We show that the causal structure of spacetime can emerge within the memory of a learning agent performing a quantum information task."
  graph := graph
  kind := .emergesWithout .learnedWorldModelMemory .causalNullStructure

/-- Worded as a scoped statement of what the geometry is obtained from ("Within this task, ...
is obtained from ..."); emergence is only "a first step toward showing". Declared sources, with
where the paper states them:
* the task: field (abstract, Sec. II), probes (Sec. II, IV), grid and moves (Eq. (36)-(41)),
  reward (Eq. (42)-(43));
* the agent: architecture and training (Sec. III-IV), five seeds (Sec. IV);
* the readout: mask and branch extraction (Eq. (62), (70)-(73)), quadratic fit with gxx = 1
  (Eq. (65)-(69)), both admitted in Sec. VI: "the metric tensor is subsequently extracted using
  external tools supplied when studying it, such as lightcone masking and conformal gauge
  fixing". -/
def claim2 : FlowClaim Node Tag where
  statement := "Within this task, spacetime geometry is obtained from an agent's successful predictions and actions, providing a first step toward showing that spacetime concepts emerge from operational quantum experience."
  graph := graph
  kind := .conditionalFlow .recoveredSpacetimeGeometry
    [ .minkowskiScalarField, .udwDetectorProtocol, .detectorPlacementGrid, .rewardShaping,
      .agentArchitectureAndTraining, .trainingSeeds,
      .lightconeReadoutRule, .quadraticNullFormAnsatz ]

#eval auditFlow claim1
#eval epistemicVerdict claim1

#eval auditFlow claim2
#eval epistemicVerdict claim2

theorem claim1_verdict : epistemicVerdict claim1 = .rejected := by decide
theorem claim2_verdict : epistemicVerdict claim2 = .admissible := by decide

-- Sensitivity note (checked once, then removed): if `declaredSources` held only what the quoted
-- sentence names (the task and the agent), `auditFlow` returned two `undeclaredUpstreamSource`
-- findings, for `lightconeReadoutRule` and `quadraticNullFormAnsatz`.

end EpistemicLedger.Cases.V2BlindA.SpacetimeAgent
