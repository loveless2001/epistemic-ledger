import EpistemicLedger.AuditRules

/-
Blind record for "Potential emergence in LLM agents: a statistical physics
perspective" (paper/paper.txt). Two claims, both verbatim abstract sentences.

The record says what the paper's own derivation leaned on. It does not say
whether the claims are true.
-/
namespace EpistemicLedger.Cases.Round2A.AgentStates

inductive Dep where
  /-- Sec. 2.1: "They contain 8 and 12 predefined states, respectively";
  Sec. 4.2: "State definitions, candidate graphs and answer-code mappings
  remain fixed throughout training and evaluation."; Discussion: "Here the
  states are predefined, regex-extractable outputs in a finite space." -/
  | predefinedStateSpace
  /-- Sec. 2.1: "the parser s_i maps a valid response y to destination j";
  Sec. 4.3 "Parsing and counting". -/
  | responseParser
  /-- Sec. 4.2: "all values are predefined destination-state utilities";
  Tables A2 and A4. The theoretical potential is built from these u_j (eq. for
  Phi_i, Sec. 2.2) and eq. (2) takes R_ij as input. -/
  | destinationRewardUtilities
  /-- Sec. 2.1: "The main experiments use β0 = 0.375."; Table 1, "KL
  coefficient". -/
  | klCoefficient
  /-- Sec. 2.1: "train for 8 rounds with LoRA and PPO, using REINFORCE with a
  mean-reward baseline to estimate advantages (Table 1)"; Sec. 4.2: "The
  per-round change of 1/βeff increases with the product of learning rate and
  steps per round". -/
  | trainingProtocol
  /-- Sec. 2.1: "Both tasks start from Qwen3.5-9B". -/
  | baseModel
  /-- Table 1: "Non-thinking mode; maximum 32 generated tokens; sampling
  temperature and top-p both 1"; Sec. 2.4: "showing that inference changes its
  state distribution". -/
  | inferenceSettings
  /-- Appendix A: "the complete inputs used in the T1 and T2 main
  experiments"; Sec. 2.4: "six prompt variants not used for training or model
  selection". -/
  | promptFormulation
  /-- Sec. 2.2: "we estimate the potential by minimising the action for each
  round's transition kernel ... We then define the order parameter by the
  Pearson correlation in equation (6)"; eq. (14), with 0.1 pseudocounts. -/
  | orderParameterEstimator
  /-- Sec. 2.1: "The reference kernel Q uses the same protocol"; Sec. 2.2:
  "From the initial kernel alone, equation (2) predicts each change". -/
  | referenceKernel
  /-- Sec. 2.1: "we repeatedly reset the agent to source i, sample and parse
  responses into destinations j, and normalise their counts"; Fig. 2: "We draw
  4,096 samples per source per round." -/
  | transitionCounts
  /-- Sec. 2.1: "We calibrate this scale from the reward difference and
  Jeffreys divergence between two rounds for each source state, fitting the
  three training seeds of each task jointly, which gives c_T1 = 3.04 and
  c_T2 = 3.45 (Fig. 3a)." Fitted to the same post-training runs that the
  predictions are compared with (Fig. 2a: "at the calibrated βeff,m"). -/
  | effectiveScaleCalibration
  /-- Sec. 2.2: "we fix κ = 0 and jointly fit θ_t and β_i,t"; Sec. 4.3: "the
  T1 and T2 means jointly fit Rmax, H∗, A, Δ". -/
  | fittedCurveParameters
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Sec. 2.1: "In the theoretical treatment, we assume that every response
  maps to a valid destination." Checked in Sec. 4.3: "Invalid rates in the T1
  and T2 main experiments are 0.26% and 0.18%; valid-only renormalisation
  changes mean reward and r in each round by at most 0.0065 and 2.3 × 10−4". -/
  | responsesMapToValidDestinations
  /-- Sec. 2.1: "If the response distribution can be optimised freely, the
  state-space objective is to maximise ..."; Sec. 4.1: "under free
  optimisation the within-class distributions equal the reference
  distributions and the second term vanishes." Not checked for the LoRA
  policy. -/
  | responseDistributionFreelyOptimisable
  /-- Sec. 2.1: "Actual training involves only a finite number of updates, so
  we describe the measured distributions using the effective scale in equation
  (3)"; Sec. 4.1: "the relation between nominal and effective scales is
  unchanged across rounds, making linear calibration possible." Checked in
  Figs 3a and 5a,b; Sec. 2.5: "the deviation of finite training from the ideal
  optimum is captured by the single factor c." (The stricter "every round
  reaches the ideal optimum", c = 1, is what the paper says does not hold;
  the comparisons do not use it.) -/
  | finiteTrainingIsIdealOptimumAtEffectiveScale
  /-- Sec. 4.2: "The main experiments use shared destination rewards"; Sec.
  2.2: "For shared destination rewards, we fix κ = 0". True by construction
  (Tables A2, A4). -/
  | sharedDestinationRewards
  /-- Sec. 4.3: "Theoretical curves use the β → 0 asymptotic forms."; Sec.
  2.3: "deviations at larger β reflect the range of validity of the small-β
  expansion" and "we approximate the effective task-level values using a
  single effective gap." -/
  | smallBetaAsymptoticFormsApply
  /-- Sec. 4.1: "With this approximation, and when η_β ≈ 1 and G_β ≈ G > 0,
  we obtain r ≃ (1 + κ + θβ²)^(−1/2)"; Sec. 2.2: "The derivation and validity
  conditions are given in Section 4.1." No check of these conditions is
  reported. -/
  | orderParameterApproximationConditions
  /-- Both claims speak of post-training and agent behaviour in general.
  Intro: "In this paper we focus on post-training with fixed state
  representations and simplified tasks"; Discussion: "defining such states and
  expressing their rewards as R_ij remain challenging." -/
  | statesAndRewardsDefinableBeyondSimplifiedTasks
  deriving DecidableEq, Repr

/-- What both claims are obtained through: the two main experiments (Figs 2
and 3) and the sensitivity runs (Figs 4 and 5). -/
def usedDeps : List (Dependency Dep) :=
  [ ⟨.predefinedStateSpace, .setByExperimenter⟩,
    ⟨.responseParser, .setByExperimenter⟩,
    ⟨.destinationRewardUtilities, .setByExperimenter⟩,
    ⟨.klCoefficient, .setByExperimenter⟩,
    ⟨.trainingProtocol, .setByExperimenter⟩,
    ⟨.baseModel, .setByExperimenter⟩,
    ⟨.inferenceSettings, .setByExperimenter⟩,
    ⟨.promptFormulation, .setByExperimenter⟩,
    ⟨.orderParameterEstimator, .setByExperimenter⟩,
    ⟨.referenceKernel, .measured⟩,
    ⟨.transitionCounts, .measured⟩,
    -- Fitted to the measured kernels, so tagged `measured`; the fitting form
    -- is the authors' choice.
    ⟨.effectiveScaleCalibration, .measured⟩,
    ⟨.fittedCurveParameters, .measured⟩ ]

/-- v1: declared if the paper states it anywhere. Each entry of `usedDeps` is
stated in the Results, Methods or Appendix A (see the quotes on `Dep`). -/
def declaredDeps : List Dep :=
  [ .predefinedStateSpace, .responseParser, .destinationRewardUtilities,
    .klCoefficient, .trainingProtocol, .baseModel, .inferenceSettings,
    .promptFormulation, .orderParameterEstimator, .referenceKernel,
    .transitionCounts, .effectiveScaleCalibration, .fittedCurveParameters ]

/-- The paper's generality tests whose outcome leaves the reported trends in
place. Intro: "To test generality across training and inference conditions,
we vary the KL coefficient, inference mode, sampling temperature, prompt
variants, model size and family, and reward structure." -/
def generalityTestsPassed : List (ForgetStep Dep) :=
  [ -- Sec. 2.5: "the order parameters of all 7 other branches lie close to
    -- the main-experiment curve of Fig. 2b without refitting (Fig. 5b)".
    ⟨.klCoefficient, .shown⟩,
    -- Sec. 2.4: "The joint variation of the three observables indicates that
    -- the theory is not restricted to a single model size or model family."
    ⟨.baseModel, .shown⟩,
    -- Sec. 2.4: "Both retain the post-training trends of increasing order
    -- parameter r and reward and decreasing entropy." (thinking mode; the
    -- trends also "persist at the lower temperature").
    ⟨.inferenceSettings, .shown⟩,
    -- Sec. 2.4: "The resulting organisation therefore generalises to unseen
    -- task formulations."
    ⟨.promptFormulation, .shown⟩ ]

def hypothesesUsed : List (Hypothesis Hyp) :=
  [ ⟨.responsesMapToValidDestinations, .discharged⟩,
    ⟨.responseDistributionFreelyOptimisable, .bet⟩,
    ⟨.finiteTrainingIsIdealOptimumAtEffectiveScale, .discharged⟩,
    ⟨.sharedDestinationRewards, .discharged⟩,
    ⟨.smallBetaAsymptoticFormsApply, .bet⟩,
    ⟨.orderParameterApproximationConditions, .bet⟩,
    ⟨.statesAndRewardsDefinableBeyondSimplifiedTasks, .bet⟩ ]

/-- Each unchecked hypothesis is stated in the paper as a condition, an
approximation or an open question (see the quotes on `Hyp`). -/
def betsStatedInPaper : List Hyp :=
  [ .responseDistributionFreelyOptimisable,
    .smallBetaAsymptoticFormsApply,
    .orderParameterApproximationConditions,
    .statesAndRewardsDefinableBeyondSimplifiedTasks ]

/-- Worded as a proposal of a tool ("through which ... can be measured and
predicted"); nothing is said to arise by itself. -/
def claim1 : Claim Dep Hyp where
  statement := "In this paper we propose agent states as intermediate variables through which post-training can be measured and predicted."
  kind := .conditional
  used := usedDeps
  declared := declaredDeps
  -- The reward-structure run is not listed here: the reward is an explicit
  -- input of the prediction (eq. 2), and the paper offers no step that drops
  -- it from "measured and predicted".
  forgets := generalityTestsPassed
  hypotheses := hypothesesUsed
  declaredBets := betsStatedInPaper

/-- Worded as a description obtained through a named instrument ("States")
of the effect of a named cause ("post-training"); read as conditional. The
sentence carries no scope ("in two simplified tasks"), which is a matter for
rules 1 and 3, not for the kind. -/
def claim2 : Claim Dep Hyp where
  statement := "States thus provide a quantitative description of how post-training organises agent behaviour."
  kind := .conditional
  used := usedDeps
  declared := declaredDeps
  forgets :=
    generalityTestsPassed ++
    [ -- Sec. 2.4, reward ablation: "the order parameter in round 8 decreases
      -- from 0.78 to 0.46 and, for α ≥ 1, state entropy no longer decreases";
      -- "Whether the reward contains a destination term shared across sources
      -- affects the outcome." The organisation this sentence speaks of
      -- changes with the reward structure.
      ⟨.destinationRewardUtilities, .contradicted⟩ ]
  hypotheses := hypothesesUsed
  declaredBets := betsStatedInPaper

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

end EpistemicLedger.Cases.Round2A.AgentStates
