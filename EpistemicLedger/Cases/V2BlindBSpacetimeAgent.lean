import EpistemicLedger.OperationFlow

/-
Blind operation-graph record: "Spacetime Emergence in the Memory of a Learning Agent"
(paper/paper.txt). Records what the paper's own derivation used; no truth judgement.
-/
namespace EpistemicLedger.Cases.V2BlindB.SpacetimeAgent

open EpistemicLedger
open EpistemicLedger.OperationFlow

inductive Node where
  /-- Sec. II: "two qubit UDW detectors interacting with a real massless scalar quantum
      field ... in 3+1-dimensional Minkowski spacetime"; field in vacuum, Eqs. (1)-(8). -/
  | minkowskiFieldSetup
  /-- Sec. II/IV: Gaussian smearings Eq. (9), "T = 0.15, σ = 0.15, and λ = 1", Ω = 0;
      "we will fix λ, σ, T". -/
  | detectorSmearing
  /-- Sec. IV, Eqs. (36)-(41): "301×301 grid whose cells index spacetime smearing centres
      x = (x, t)", "detector 1 fixed at the origin", observation o(s) = normalized
      coordinates, eight nearest-neighbour moves. -/
  | spacetimeGrid
  /-- Sec. IV: QMI between the detectors over the grid, Eqs. (10)-(20), Fig. 2. -/
  | qmiLandscape
  /-- Sec. IV, Eqs. (42)-(43): power transform p = 1/4, progress bonus/penalty,
      boundary penalty, goal state at (0, 0). -/
  | rewardShaping
  /-- Sec. IV, Eq. (43): "The reward from the environment is comprised of four terms". -/
  | rewardSignal
  /-- Sec. III, Fig. 1: encoder, latent dynamics, reward model, decoder, H = 1 planner,
      d_z = 20, loss Eq. (56). -/
  | agentArchitecture
  /-- Sec. IV: ε-greedy schedule, edge-biased start curriculum, AdamW settings, replay,
      "five different agent-parameter and environment random-generator seed initializations". -/
  | trainingProtocol
  /-- Sec. III: "We will refer to the collection of these learned internal models as the
      agent's memory". -/
  | agentMemory
  /-- Sec. V, Eqs. (61)-(62): average planner scores over five agents, softmax average
      with "β′ = 2 giving the best results for the reconstruction procedure". -/
  | scoreAveragingRule
  /-- Sec. V, Eq. (62), Fig. 4: scalar softmax-average planner score field S(x). -/
  | plannerScoreField
  /-- Sec. V, Eqs. (70)-(73): 70% neighbour-comparison mask, "lightcone centre is fixed at
      (xc, tc) = (0, 0)", left/right branch point per time row. -/
  | lightconeMaskRule
  /-- Sec. V, Eqs. (72)-(73): extracted lightcone branch points {(Δt_i, Δx_i)}. -/
  | lightconeBranchPoints
  /-- Sec. V, Eqs. (65), (69): quadratic form gtt Δt² + 2gtx ΔtΔx + gxx Δx² with null
      condition q = 0 and "conformal freedom ... gxx = 1". -/
  | quadraticNullAnsatz
  /-- Sec. V, Eq. (74): fitted metric representative g_fit, null slopes ≈ ±0.99994. -/
  | fittedMetric
  deriving DecidableEq, Repr

inductive Tag where
  /-- Abstract/Sec. V: "causal structure of spacetime"; "characteristic null structure",
      the lightcone branches / null directions. -/
  | causalStructure
  /-- Abstract: "spacetime geometry"; Sec. V: Lorentzian metric representative of the
      conformal class (gtt, gtx, gxx). -/
  | metricGeometry
  /-- Sec. VI: "contingent properties of the chosen coordinates or probes". -/
  | probeCoordinateChoice
  deriving DecidableEq, Repr

def graph : FlowGraph Node Tag where
  sources :=
    [ -- Sec. VI: "the causal structure is known analytically and is already reflected in the
      -- known field correlations from which the detector data are generated"; Sec. II: "The
      -- causal propagator encodes information that propagates between different events".
      ⟨.minkowskiFieldSetup, .setByExperimenter, [.causalStructure, .metricGeometry]⟩,
      -- Sec. VI: tests "under ... different detector smearings should be undertaken"
      -- (probe choice is a candidate contingency).
      ⟨.detectorSmearing, .setByExperimenter, [.probeCoordinateChoice]⟩,
      -- Sec. VI: tests "under coordinate changes ... should be undertaken"; Sec. IV: "the RL
      -- agent still receives spacetime coordinates".
      ⟨.spacetimeGrid, .setByExperimenter, [.probeCoordinateChoice]⟩,
      ⟨.rewardShaping, .setByExperimenter, []⟩,
      ⟨.agentArchitecture, .setByExperimenter, []⟩,
      ⟨.trainingProtocol, .setByExperimenter, []⟩,
      ⟨.scoreAveragingRule, .setByExperimenter, []⟩,
      -- Sec. VI: "the metric tensor is subsequently extracted using external tools supplied
      -- when studying it, such as lightcone masking and conformal gauge fixing ... such
      -- geometrically informed post-processing procedures"; Sec. V: centre fixed at (0,0),
      -- one left and one right branch per time row.
      ⟨.lightconeMaskRule, .setByExperimenter, [.causalStructure]⟩,
      -- Sec. VI: "conformal gauge fixing" (gxx = 1); Sec. V Eq. (65): Lorentzian quadratic
      -- form with null condition assumed as the fit model.
      ⟨.quadraticNullAnsatz, .setByExperimenter, [.metricGeometry]⟩ ]
  ops :=
    [ -- Forget step. Sec. VI: "More robust tests of the reconstruction under coordinate
      -- changes and different detector smearings should be undertaken ... This would
      -- substantially strengthen the evidence that the learned relations represent spacetime
      -- structure as opposed to contingent properties of the chosen coordinates or probes."
      -- Not done in the paper -> notShown. (Footnote 2 argues only the overall timescale T0
      -- is irrelevant, "due to the conformal character of the massless field".)
      ⟨"udw_detector_field_interaction", [.minkowskiFieldSetup, .detectorSmearing, .spacetimeGrid],
        .qmiLandscape, .forget .probeCoordinateChoice .notShown⟩,
      -- Sec. IV: "The reward inherits the dependence on spacetime structure from the quantum
      -- mutual information".
      ⟨"reward_from_transformed_qmi", [.qmiLandscape, .rewardShaping], .rewardSignal, .transform []⟩,
      -- Sec. I: "The underlying spacetime structure is implicitly encoded in this reward and
      -- so the RL agent must learn a predictive representation".
      ⟨"model_based_rl_training", [.rewardSignal, .spacetimeGrid, .agentArchitecture, .trainingProtocol],
        .agentMemory, .transform []⟩,
      -- Sec. V: frozen planner evaluated at every grid point, Eqs. (58)-(62).
      ⟨"evaluate_frozen_planner_scores", [.agentMemory, .spacetimeGrid, .scoreAveragingRule],
        .plannerScoreField, .transform []⟩,
      ⟨"neighbour_mask_branch_extraction", [.plannerScoreField, .lightconeMaskRule],
        .lightconeBranchPoints, .transform []⟩,
      ⟨"least_squares_null_fit", [.lightconeBranchPoints, .quadraticNullAnsatz],
        .fittedMetric, .transform []⟩ ]

/-- "emerge within the memory" -> emergesWithout, target = the agent's memory (Sec. III). -/
def claim1 : FlowClaim Node Tag where
  statement := "We show that the causal structure of spacetime can emerge within the memory of a learning agent performing a quantum information task."
  graph := graph
  kind := .emergesWithout .agentMemory .causalStructure

/-- "Within this task, ... is obtained from" -> conditionalFlow on the fitted metric.
Declared: the task setup ("within this task"), the agent ("predictions and actions"), and
the readout tools, which the paper states openly (abstract: "allowing us to reconstruct";
Sec. V; Sec. VI "external tools supplied when studying it"). -/
def claim2 : FlowClaim Node Tag where
  statement := "Within this task, spacetime geometry is obtained from an agent's successful predictions and actions, providing a first step toward showing that spacetime concepts emerge from operational quantum experience."
  graph := graph
  kind := .conditionalFlow .fittedMetric
    [.minkowskiFieldSetup, .detectorSmearing, .spacetimeGrid, .rewardShaping,
     .agentArchitecture, .trainingProtocol, .scoreAveragingRule, .lightconeMaskRule,
     .quadraticNullAnsatz]

#eval auditFlow claim1
#eval epistemicVerdict claim1
#eval auditFlow claim2
#eval epistemicVerdict claim2

theorem claim1_verdict : epistemicVerdict claim1 = .rejected := by decide
theorem claim2_verdict : epistemicVerdict claim2 = .admissible := by decide

end EpistemicLedger.Cases.V2BlindB.SpacetimeAgent
