import EpistemicLedger.AuditRules

/-
Blind record for "Can Image Generation Help Visual Reasoning? An Empirical Study"
(paper/paper.txt). Two abstract sentences, recorded from the paper's own text.
The record says what each claim leans on; it does not say whether it is true.
-/
namespace EpistemicLedger.Cases.Round2A.ImageGenReasoning

inductive Dep where
  /-- Sec. 2, Step 1: "we prompt it to write a hint of one or two sentences
  describing a single helper image that would make the question easier". -/
  | modelWrittenHint
  /-- Sec. 3: "for 13 modular pipelines in total. We also evaluate BAGEL ... and
  Janus-Pro-7B ... as unified models." App. D: "Our study evaluates static image
  generators". -/
  | vlmGeneratorPairs
  /-- Sec. 2, Step 3: "The VLM then answers with the question, the original images,
  its hint, and the helper image all in context". App. C.3: "We therefore use
  multi-turn inference for all main experiments." -/
  | answerTurnWithOriginalsHintAndHelper
  /-- Sec. 1: "We compare each model with its own direct-answer baseline in both
  modular pipelines and unified models." -/
  | directAnswerBaseline
  /-- Sec. 3: "We evaluate on nine benchmarks covering six kinds of visual
  reasoning (Table 2)." App. D: "Our evaluation is also confined to
  question-answering benchmarks". -/
  | benchmarkSet
  /-- Sec. 3: "We score answers by rule where possible. For responses requiring
  semantic scoring, the original experiments use Gemini-2.5-Flash ... The
  Janus-Pro-7B evaluation, matched controls, and extended scaling runs use
  Gemini-2.5-Flash-Lite." -/
  | answerScoring
  /-- Sec. 2: "Unless stated otherwise, each question receives one helper image."
  Sec. 5: "By default, the model always generates an image." (Figure 3a) -/
  | oneHelperAlwaysGenerated
  /-- Sec. 3: "All models use non-thinking mode unless otherwise specified."
  (Table 5b shows the baselines move with thinking on.) -/
  | nonThinkingMode
  /-- Sec. 5 / Table 11: "Qwen3-VL 8B receives the same original inputs, hint, turn
  structure, and final instruction. The answer turn adds either no image, a second
  copy of the first original, or a FLUX.1-Kontext helper." -/
  | matchedHelperControl
  /-- Sec. 4: "Table 3 and Table 4 compare every pipeline with the text-only
  baseline of its VLM on ten tasks". -/
  | measuredAccuracies
  /-- App. C.7: "Table 10 reports a rerun of the no-generation baseline and the one-
  and two-call conditions with Qwen3-VL 8B and FLUX.1-Kontext, extended to ten
  calls." -/
  | qwen8bWithFluxKontext
  /-- App. C.7: "We generate one hint per question and keep it fixed." -/
  | fixedHintPerQuestion
  /-- App. C.7: "The first call edits the first original image. Each subsequent call
  edits the preceding helper. At each checkpoint the VLM answers the question
  afresh using the original images and only the latest helper." -/
  | chainedEditsLatestHelperOnly
  /-- Table 10 header: "Generation calls 0 1 2 3 4 5 8 10". -/
  | evaluatedCheckpoints
  /-- Table 10 caption: "Each checkpoint uses the same 1,425 ChartQAPro, 400 ERQA,
  and 1,000 MathVista questions." -/
  | scalingBenchmarksAndQuestions
  /-- App. C.7: "one planning call (up to 256 tokens), n image-generation calls, and
  one answer call (up to 1,024 tokens) ... Each FLUX call uses 24 denoising steps".
  (Table 6 defaults differ: 2048 / 8192 tokens, 28 steps.) -/
  | extendedRunBudget
  /-- App. C.7: "At zero calls it answers directly from the originals." Table 10,
  column 0: 39.16 / 42.50 / 67.70 (the main tables give 40.8 / 44.3 / 61.2). -/
  | rerunNoGenerationBaseline
  /-- Table 10, columns 1 to 10: accuracy at each evaluated round. -/
  | checkpointAccuracies
  deriving DecidableEq, Repr

inductive Hyp where
  /-- App. C.2 / Table 8: "Together, these checks confirm that our evaluation judge
  is robust and that findings are not an artifact of judge design." Scope: "All
  results in Table 8 use Qwen3-VL 8B text inference." -/
  | flashJudgeMatchesRuleAndHumanScoring
  /-- Sec. 3 names Gemini-2.5-Flash-Lite as judge for "The Janus-Pro-7B evaluation,
  matched controls, and extended scaling runs"; App. C.2 checks Gemini-2.5-Flash
  only, and no check of Flash-Lite is reported. -/
  | flashLiteJudgeMatchesRuleAndHumanScoring
  /-- App. C.8: "The direct-answer baseline in the main tables answers before
  planning. The hint-only control answers after planning." Sec. 5: "To measure the
  helper's contribution, we compare answers to the same question while changing
  the image in the answer turn (Table 11)." Table 11 covers one pair on three
  benchmarks; the other pairs and tasks have no such control. -/
  | mainTableChangeDueToHelperNotPlanningTurn
  /-- Table 10 caption: "Each checkpoint uses the same 1,425 ChartQAPro, 400 ERQA,
  and 1,000 MathVista questions." -/
  | sameQuestionsAtEveryCheckpoint
  /-- Sec. 5: "ChartQAPro and MathVista stay below their no-generation baselines at
  every evaluated round." Table 10 has no column for rounds 6, 7 and 9. -/
  | belowBaselineAtUnevaluatedRounds
  /-- Table 10 gives one point estimate per cell, with no interval or repeat (Table
  11 has paired intervals; Table 10 does not). Sec. 5 only says: "Accuracy
  fluctuates across rounds on all three tasks." -/
  | differencesExceedRunToRunVariation
  deriving DecidableEq, Repr

/-- Abstract, sentence 2: the study's aim, worded as a test under a described setup. -/
def claim1 : Claim Dep Hyp where
  statement := "We test whether a generated helper improves the answer to a visual question."
  kind := .conditional
  used :=
    [ ⟨.modelWrittenHint, .setByExperimenter⟩,
      ⟨.vlmGeneratorPairs, .setByExperimenter⟩,
      ⟨.answerTurnWithOriginalsHintAndHelper, .setByExperimenter⟩,
      ⟨.directAnswerBaseline, .setByExperimenter⟩,
      ⟨.benchmarkSet, .setByExperimenter⟩,
      ⟨.answerScoring, .setByExperimenter⟩,
      ⟨.oneHelperAlwaysGenerated, .setByExperimenter⟩,
      ⟨.nonThinkingMode, .setByExperimenter⟩,
      ⟨.matchedHelperControl, .setByExperimenter⟩,
      ⟨.measuredAccuracies, .measured⟩ ]
  declared :=
    [ .modelWrittenHint, .vlmGeneratorPairs, .answerTurnWithOriginalsHintAndHelper,
      .directAnswerBaseline, .benchmarkSet, .answerScoring, .oneHelperAlwaysGenerated,
      .nonThinkingMode, .matchedHelperControl, .measuredAccuracies ]
  forgets := []
  hypotheses :=
    [ ⟨.flashJudgeMatchesRuleAndHumanScoring, .discharged⟩,
      ⟨.flashLiteJudgeMatchesRuleAndHumanScoring, .bet⟩,
      ⟨.mainTableChangeDueToHelperNotPlanningTurn, .bet⟩ ]
  declaredBets := [.mainTableChangeDueToHelperNotPlanningTurn]

/-- Abstract, last sentence: a report of the extended repeated-edit run (Table 10). -/
def claim2 : Claim Dep Hyp where
  statement := "ChartQAPro and MathVista stay below their no-generation baselines, while ERQA gains three points after ten edits."
  kind := .conditional
  used :=
    [ ⟨.qwen8bWithFluxKontext, .setByExperimenter⟩,
      ⟨.fixedHintPerQuestion, .setByExperimenter⟩,
      ⟨.chainedEditsLatestHelperOnly, .setByExperimenter⟩,
      ⟨.evaluatedCheckpoints, .setByExperimenter⟩,
      ⟨.scalingBenchmarksAndQuestions, .setByExperimenter⟩,
      ⟨.extendedRunBudget, .setByExperimenter⟩,
      ⟨.answerScoring, .setByExperimenter⟩,
      ⟨.nonThinkingMode, .setByExperimenter⟩,
      ⟨.rerunNoGenerationBaseline, .measured⟩,
      ⟨.checkpointAccuracies, .measured⟩ ]
  declared :=
    [ .qwen8bWithFluxKontext, .fixedHintPerQuestion, .chainedEditsLatestHelperOnly,
      .evaluatedCheckpoints, .scalingBenchmarksAndQuestions, .extendedRunBudget,
      .answerScoring, .nonThinkingMode, .rerunNoGenerationBaseline,
      .checkpointAccuracies ]
  forgets := []
  hypotheses :=
    [ ⟨.sameQuestionsAtEveryCheckpoint, .discharged⟩,
      ⟨.belowBaselineAtUnevaluatedRounds, .bet⟩,
      ⟨.flashLiteJudgeMatchesRuleAndHumanScoring, .bet⟩,
      ⟨.differencesExceedRunToRunVariation, .bet⟩ ]
  declaredBets := [.belowBaselineAtUnevaluatedRounds]

#eval audit claim1
#eval verdictV1 claim1
#eval rule4Fired claim1

#eval audit claim2
#eval verdictV1 claim2
#eval rule4Fired claim2

theorem claim1_v1 : verdictV1 claim1 = .passedWithNotes := by decide
theorem claim1_rule4 : rule4Fired claim1 = false := by decide

theorem claim2_v1 : verdictV1 claim2 = .passedWithNotes := by decide
theorem claim2_rule4 : rule4Fired claim2 = false := by decide

end EpistemicLedger.Cases.Round2A.ImageGenReasoning
