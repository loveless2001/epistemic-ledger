import EpistemicLedger.AuditRules

/-
Claim records for "Potential emergence in LLM agents: a statistical physics
perspective" (arXiv:2611.27618v1). Two abstract sentences.
-/
namespace EpistemicLedger.Cases.Round2B.AgentStates

inductive Dep where
  /-- "They contain 8 and 12 predefined states, respectively (Fig. 1a,b; definitions
  in Appendix A)"; Discussion: "Here the states are predefined, regex-extractable
  outputs in a finite space." The parser s_i maps responses to states (Sec. 2.1). -/
  | predefinedStatesAndParser
  /-- Fig. 1: "T1 contains 8 states, with transitions allowed between any two distinct
  states ... T2 contains 12 states, each connected to its two neighbours in either
  direction on a ring." Sec. 4.2: "candidate graphs ... remain fixed". -/
  | candidateGraph
  /-- Sec. 4.2: "all values are predefined destination-state utilities" (Tables A2, A4);
  main experiments use "shared destination rewards". Sec. 2.4 ablation: "Whether the
  reward contains a destination term shared across sources affects the outcome." -/
  | destinationRewards
  /-- Sec. 2.1: "Let β0 be the fixed relative penalty coefficient ... The main
  experiments use β0 = 0.375." Varied in Sec. 2.5 / Fig. 5. -/
  | klCoefficient
  /-- Table 1 (LoRA rank 16, REINFORCE baseline, 4 steps per round, 8 rounds, lr 1e-5);
  Sec. 4.2: per-round change of 1/β_eff "increases with the product of learning rate
  and steps per round". -/
  | trainingProtocol
  /-- Sec. 2.1: "Both tasks start from Qwen3.5-9B"; Sec. 2.4 also Qwen3.5-4B and
  Gemma-4-E4B. -/
  | baseModel
  /-- Table 1: "Non-thinking mode; maximum 32 generated tokens; sampling temperature
  and top-p both 1"; Sec. 2.4 varies thinking mode and τ = 0.7. -/
  | inferenceSettings
  /-- Appendix A: "complete inputs used in the T1 and T2 main experiments"; Sec. 2.4:
  "six prompt variants not used for training or model selection". -/
  | promptFormulation
  /-- Sec. 2.1: "The reference kernel Q uses the same protocol"; Sec. 2.2: "Using a
  reference kernel Q before task-specific post-training". -/
  | referenceKernel
  /-- Sec. 2.1: "we repeatedly reset the agent to source i, sample and parse responses
  into destinations j, and normalise their counts ... to estimate T_ij"; 4,096
  samples per source per round (Fig. 2). -/
  | measuredTransitionKernels
  /-- Sec. 2.1, eq. (3): "We calibrate this scale from the reward difference and
  Jeffreys divergence ... which gives c_T1 = 3.04 and c_T2 = 3.45 (Fig. 3a)". -/
  | calibrationFactor
  /-- Sec. 2.2: "we fix κ = 0 and jointly fit θ_t and β_i,t"; "β_i,t absorbs the
  nonzero baseline r of the reference kernel". -/
  | orderParameterFitParameters
  /-- Fig. 3 caption: "In c,f and d,g, the parameters R_max, H_*, A, Δ are jointly
  fitted for each task"; for t5 "only A_i is fitted". -/
  | rewardEntropyFitParameters
  /-- Sec. 2.2: "Following the minimum-action method 45, we estimate the potential by
  minimising the action ... obtaining a centred potential φ̂ without using reward
  information"; eq. (14), pseudocounts α = 0.1 (Sec. 4.3). -/
  | potentialEstimator
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Sec. 2.1: "Actual training involves only a finite number of updates, so we
  describe the measured distributions using the effective scale in equation (3)";
  Sec. 4.1: "This section assumes that optimisation reaches the ideal optimum."
  Supported only by agreement (Fig. 2a Pearson 0.76 / 0.89), not shown to hold. -/
  | trainedKernelIsKLOptimumAtEffectiveScale
  /-- Sec. 4.1: "the relation between nominal and effective scales is unchanged across
  rounds, making linear calibration possible"; checked by Fig. 3a fits and Fig. 5a:
  "every branch follows the same calibration relation". -/
  | calibrationFactorConstantAcrossRounds
  /-- Sec. 2.1: "In the theoretical treatment, we assume that every response maps to
  a valid destination." Sec. 4.3: invalid rates 0.26% and 0.18%; renormalisation
  changes reward and r "by at most 0.0065 and 2.3 × 10⁻⁴". -/
  | everyResponseValid
  /-- Sec. 2.2: "For shared destination rewards, we fix κ = 0"; Sec. 4.2: "All
  transitions into the same destination therefore receive the same reward". -/
  | sharedDestinationRewardKappaZero
  /-- Sec. 4.1: "when η_β ≈ 1 and G_β ≈ G > 0, we obtain r ≃ (1 + κ + θβ²)^(-1/2)";
  no check of η_β or G_β reported. -/
  | orderParameterApproximationConditions
  /-- Sec. 2.3: "As reward gaps differ across sources, we approximate the effective
  task-level values using a single effective gap"; eq. (11). -/
  | singleEffectiveGap
  /-- Sec. 2.3: "deviations at larger β reflect the range of validity of the small-β
  expansion"; eqs (5), (7), (8) are β → 0 asymptotics applied at finite β_eff. -/
  | smallBetaAsymptoticsApply
  deriving DecidableEq, Repr

/-- Dependencies shared by both claims: both rest on the same measurement and
partition-function machinery (Secs 2.1–2.5). -/
def usedDeps : List (Dependency Dep) :=
  [ ⟨.predefinedStatesAndParser, .setByExperimenter⟩,
    ⟨.candidateGraph, .setByExperimenter⟩,
    ⟨.destinationRewards, .setByExperimenter⟩,
    ⟨.klCoefficient, .setByExperimenter⟩,
    ⟨.trainingProtocol, .setByExperimenter⟩,
    ⟨.baseModel, .setByExperimenter⟩,
    ⟨.inferenceSettings, .setByExperimenter⟩,
    ⟨.promptFormulation, .setByExperimenter⟩,
    ⟨.referenceKernel, .measured⟩,
    ⟨.measuredTransitionKernels, .measured⟩,
    ⟨.calibrationFactor, .measured⟩,
    ⟨.orderParameterFitParameters, .measured⟩,
    ⟨.rewardEntropyFitParameters, .measured⟩,
    ⟨.potentialEstimator, .setByExperimenter⟩ ]

/-- Every dependency above is stated somewhere in the paper (v1 rule for `declared`). -/
def declaredDeps : List Dep :=
  [ .predefinedStatesAndParser, .candidateGraph, .destinationRewards, .klCoefficient,
    .trainingProtocol, .baseModel, .inferenceSettings, .promptFormulation,
    .referenceKernel, .measuredTransitionKernels, .calibrationFactor,
    .orderParameterFitParameters, .rewardEntropyFitParameters, .potentialEstimator ]

def appliedHyps : List (Hypothesis Hyp) :=
  [ ⟨.trainedKernelIsKLOptimumAtEffectiveScale, .bet⟩,
    ⟨.calibrationFactorConstantAcrossRounds, .discharged⟩,
    ⟨.everyResponseValid, .discharged⟩,
    ⟨.sharedDestinationRewardKappaZero, .discharged⟩,
    ⟨.orderParameterApproximationConditions, .bet⟩,
    ⟨.singleEffectiveGap, .bet⟩,
    ⟨.smallBetaAsymptoticsApply, .bet⟩ ]

/-- All unchecked hypotheses are stated openly in the paper (Secs 2.1, 2.3, 4.1). -/
def statedBets : List Hyp :=
  [ .trainedKernelIsKLOptimumAtEffectiveScale, .orderParameterApproximationConditions,
    .singleEffectiveGap, .smallBetaAsymptoticsApply ]

def claim1 : Claim Dep Hyp where
  statement := "In this paper we propose agent states as intermediate variables through which post-training can be measured and predicted."
  kind := .conditional
  used := usedDeps
  declared := declaredDeps
  -- Generality steps the paper offers. "Predicted": only the KL branches were
  -- compared with theory (Fig. 5b, "without refitting"); model, prompt and inference
  -- variants report trends at nominal β only, with no theory comparison.
  forgets :=
    [ ⟨.klCoefficient, .shown⟩,
      ⟨.baseModel, .notShown⟩,
      ⟨.promptFormulation, .notShown⟩,
      ⟨.inferenceSettings, .notShown⟩ ]
  hypotheses := appliedHyps
  declaredBets := statedBets

def claim2 : Claim Dep Hyp where
  statement := "States thus provide a quantitative description of how post-training organises agent behaviour."
  kind := .conditional
  used := usedDeps
  declared := declaredDeps
  -- Sec. 2.4: organisation (r and reward up, entropy down) persists across model size
  -- and family ("not restricted to a single model size or model family"), prompt
  -- variants ("generalises to unseen task formulations"), thinking mode / τ = 0.7;
  -- Sec. 2.5 / Fig. 5b for the KL coefficient.
  forgets :=
    [ ⟨.klCoefficient, .shown⟩,
      ⟨.baseModel, .shown⟩,
      ⟨.promptFormulation, .shown⟩,
      ⟨.inferenceSettings, .shown⟩ ]
  hypotheses := appliedHyps
  declaredBets := statedBets

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

end EpistemicLedger.Cases.Round2B.AgentStates
