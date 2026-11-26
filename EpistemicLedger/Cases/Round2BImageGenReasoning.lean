import EpistemicLedger.AuditRules

/-
Blind audit record: "Can image generation help visual reasoning? An empirical
study" (paper/paper.txt). Two abstract sentences.
-/
namespace EpistemicLedger.Cases.Round2B.ImageGenReasoning

inductive Dep where
  /-- Sec. 2: "In the first turn, the VLM receives the images and the question but
  is instructed not to answer yet. ... An image generator draws the helper image
  from the hint and the input images. ... The helper image is added to the same
  conversation in a second turn." -/
  | reasoningWithImaginationPipeline
  /-- Sec. 1: "We compare each model with its own direct-answer baseline in both
  modular pipelines and unified models." Prompt in App. B ("Text-only Direct
  prompting"). -/
  | directAnswerBaseline
  /-- Sec. 3 Model Selection / Table 1: "We pair every VLM with every image
  generator in Table 1, and pair Gemini 3.0 Flash ... with its own Nano-Banana, for
  13 modular pipelines in total. We also evaluate BAGEL ... and Janus-Pro-7B". -/
  | modelAndGeneratorSelection
  /-- Sec. 3 Benchmark Selection / Table 2: "We evaluate on nine benchmarks covering
  six kinds of visual reasoning"; "We exclude Rover-TG's spatial-context task and
  ChartQAPro's paragraph-context task." -/
  | benchmarkSelection
  /-- Sec. 3 Evaluation Protocol: "We score answers by rule where possible. For
  responses requiring semantic scoring, the original experiments use
  Gemini-2.5-Flash ... extended scaling runs use Gemini-2.5-Flash-Lite." -/
  | answerScoring
  /-- Accuracies read off the runs: Tables 3, 4 (main) and Table 10 (repeated
  edits). -/
  | measuredAccuracy
  /-- App. C.7: "a rerun of the no-generation baseline and the one- and two-call
  conditions with Qwen3-VL 8B and FLUX.1-Kontext, extended to ten calls." The
  repeated-edit result is for this one pipeline only. -/
  | qwen8bFluxPipelineOnly
  /-- App. C.7: "We generate one hint per question and keep it fixed. The first call
  edits the first original image. Each subsequent call edits the preceding helper.
  At each checkpoint the VLM answers ... using the original images and only the
  latest helper." -/
  | fixedHintChainedEditProtocol
  /-- App. C.7 / Table 10: the "no-generation baseline" of the claim is the rerun
  zero-call condition (ChartQAPro 39.16, ERQA 42.50, MathVista 67.70), not the
  main-table text-only rows (40.8, 44.3, 61.2 in Tables 3-4). -/
  | rerunNoGenerationBaseline
  /-- App. C.7: "one planning call (up to 256 tokens) ... one answer call (up to
  1,024 tokens) ... Each FLUX call uses 24 denoising steps" (main runs: 2048/8192
  tokens, 28 steps, Table 6). -/
  | extendedRunSettings
  /-- Table 10 columns: "Generation calls 0 1 2 3 4 5 8 10"; the claim reads the
  ERQA gain at the 10-call checkpoint ("ERQA rises from 42.50% at baseline to
  45.50% after ten edits"). -/
  | evaluatedCheckpoints
  /-- Table 10 caption: "Each checkpoint uses the same 1,425 ChartQAPro, 400 ERQA,
  and 1,000 MathVista questions." -/
  | repeatedEditQuestionSets
  deriving DecidableEq, Repr

inductive Hyp where
  /-- App. C.2 / Table 8: Gemini-2.5-Flash judge "differs from rule-based accuracy
  by at most 0.4 points on ChartQAPro and VSTAR, and by 2.0 points from human
  annotation on a 100-instance audit set". -/
  | flashJudgeAgreesWithReference
  /-- Sec. 3: "extended scaling runs use Gemini-2.5-Flash-Lite". The reliability
  check of App. C.2 / Table 8 covers Gemini-2.5-Flash only; no check of
  Flash-Lite is reported. -/
  | flashLiteJudgeAgreesWithReference
  deriving DecidableEq, Repr

def claim1 : Claim Dep Hyp where
  statement := "We test whether a generated helper improves the answer to a visual question."
  kind := .conditional
  used :=
    [ ⟨.reasoningWithImaginationPipeline, .setByExperimenter⟩,
      ⟨.directAnswerBaseline, .setByExperimenter⟩,
      ⟨.modelAndGeneratorSelection, .setByExperimenter⟩,
      ⟨.benchmarkSelection, .setByExperimenter⟩,
      ⟨.answerScoring, .setByExperimenter⟩,
      ⟨.measuredAccuracy, .measured⟩ ]
  declared :=
    [ .reasoningWithImaginationPipeline, .directAnswerBaseline,
      .modelAndGeneratorSelection, .benchmarkSelection, .answerScoring,
      .measuredAccuracy ]
  forgets := []
  hypotheses := [ ⟨.flashJudgeAgreesWithReference, .discharged⟩ ]
  declaredBets := []

def claim2 : Claim Dep Hyp where
  statement := "ChartQAPro and MathVista stay below their no-generation baselines, while ERQA gains three points after ten edits."
  kind := .conditional
  used :=
    [ ⟨.reasoningWithImaginationPipeline, .setByExperimenter⟩,
      ⟨.qwen8bFluxPipelineOnly, .setByExperimenter⟩,
      ⟨.fixedHintChainedEditProtocol, .setByExperimenter⟩,
      ⟨.rerunNoGenerationBaseline, .setByExperimenter⟩,
      ⟨.extendedRunSettings, .setByExperimenter⟩,
      ⟨.evaluatedCheckpoints, .setByExperimenter⟩,
      ⟨.repeatedEditQuestionSets, .setByExperimenter⟩,
      ⟨.answerScoring, .setByExperimenter⟩,
      ⟨.measuredAccuracy, .measured⟩ ]
  declared :=
    [ .reasoningWithImaginationPipeline, .qwen8bFluxPipelineOnly,
      .fixedHintChainedEditProtocol, .rerunNoGenerationBaseline,
      .extendedRunSettings, .evaluatedCheckpoints, .repeatedEditQuestionSets,
      .answerScoring, .measuredAccuracy ]
  forgets := []
  hypotheses := [ ⟨.flashLiteJudgeAgreesWithReference, .bet⟩ ]
  declaredBets := []

#eval audit claim1
#eval verdictV1 claim1
#eval rule4Fired claim1
#eval audit claim2
#eval verdictV1 claim2
#eval rule4Fired claim2

theorem claim1_v1 : verdictV1 claim1 = .passed := by decide
theorem claim1_rule4 : rule4Fired claim1 = false := by decide
theorem claim2_v1 : verdictV1 claim2 = .passedWithNotes := by decide
theorem claim2_rule4 : rule4Fired claim2 = false := by decide

end EpistemicLedger.Cases.Round2B.ImageGenReasoning
