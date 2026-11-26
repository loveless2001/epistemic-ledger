import EpistemicLedger.Cases.BarontiniColdAtomsTime
import EpistemicLedger.Cases.GeminiBarontiniColdAtomsTime
import EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa
import EpistemicLedger.Cases.GeminiBalestrieroLeCunPlatonicJepa

/-
Two auditors (claude, gemini) recorded the same two papers. This file states,
as checked theorems, where the two records agree and what is left over.

The `sameAs` maps are claude's judgement of which of gemini's dependencies is
"the same thing" as one of claude's. Both records are kept as first written;
nothing here was edited to make them agree.

Caveat on independence: gemini did not open claude's case files, but both
auditors were in the same chat thread, where claude had already named every
dependency in claude's own lists. So the matched part is not evidence of
independent agreement. The informative part is what only one side recorded.
-/
namespace EpistemicLedger.Cases.AuditorAgreementClaudeVsGemini

namespace Barontini

abbrev ClaudeDep := EpistemicLedger.Cases.BarontiniColdAtomsTime.Dep
abbrev GeminiDep := EpistemicLedger.Cases.GeminiBarontiniColdAtomsTime.Dep

def claudeUsed : List (Dependency ClaudeDep) :=
  EpistemicLedger.Cases.BarontiniColdAtomsTime.usedByDerivation

def geminiUsed : List (Dependency GeminiDep) :=
  EpistemicLedger.Cases.GeminiBarontiniColdAtomsTime.derivationDeps

def sameAs : ClaudeDep → GeminiDep
  | .barrierHeightV => .opticalBarrierHeight
  | .observedUnobservedCutAtXZero => .spatialPartitionPlane
  | .labClockOrderingOfImages => .labTimeImageOrdering
  | .arbitraryEntropicTimeUnitSigma => .arbitraryEntropicTimeUnit
  | .measuredBrightSectorObservables => .measuredDensityProfiles

/-- All 5 of claude's dependencies are in gemini's record with the same source tag. -/
theorem claude_deps_matched_with_same_source :
    ∀ dep ∈ claudeUsed, (⟨sameAs dep.id, dep.source⟩ : Dependency GeminiDep) ∈ geminiUsed := by
  decide

/-- What gemini recorded and claude did not. -/
def geminiOnly : List GeminiDep :=
  (geminiUsed.map (·.id)).filter (fun g => g ∉ claudeUsed.map (fun d => sameAs d.id))

/-- 3 of gemini's 8 dependencies have no counterpart in claude's record. -/
theorem gemini_only_deps :
    geminiOnly = [.opticalDipoleTrap, .clockAndBranchChoice, .empiricalPumpAndMassFit] := by
  decide

/-- Same verdict on the headline and on the narrow claim. -/
theorem verdicts_agree :
    verdict EpistemicLedger.Cases.BarontiniColdAtomsTime.headlineClaim
        = verdict EpistemicLedger.Cases.GeminiBarontiniColdAtomsTime.headlineInternalTimeClaim
      ∧ verdict EpistemicLedger.Cases.BarontiniColdAtomsTime.bodyClaim
        = verdict EpistemicLedger.Cases.GeminiBarontiniColdAtomsTime.narrowLabOrderingClaim := by
  decide

/-- Same verdict, different finding counts: the counts are not comparable
across auditors (gemini records one fact as a hypothesis where claude records
it as a dependency). -/
theorem headline_finding_counts :
    (audit EpistemicLedger.Cases.BarontiniColdAtomsTime.headlineClaim).length = 8
      ∧ (audit EpistemicLedger.Cases.GeminiBarontiniColdAtomsTime.headlineInternalTimeClaim).length = 16 := by
  decide

end Barontini

namespace BalestrieroLeCun

abbrev ClaudeDep := EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa.Dep
abbrev GeminiDep := EpistemicLedger.Cases.GeminiBalestrieroLeCunPlatonicJepa.Dep

def claudeUsed : List (Dependency ClaudeDep) :=
  EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa.usedByExperiments

def geminiUsed : List (Dependency GeminiDep) :=
  EpistemicLedger.Cases.GeminiBalestrieroLeCunPlatonicJepa.experimentDeps

def sameAs : ClaudeDep → GeminiDep
  | .positivePairGroupingByImage => .curatedPositivePairOracle
  | .captionsFromLlavaWithClipVision => .llavaClipRecaptioner
  | .measuredAlignmentScores => .empiricalAlignmentMeasurements

/-- All 3 of claude's dependencies are in gemini's record with the same source tag. -/
theorem claude_deps_matched_with_same_source :
    ∀ dep ∈ claudeUsed, (⟨sameAs dep.id, dep.source⟩ : Dependency GeminiDep) ∈ geminiUsed := by
  decide

/-- What gemini recorded and claude did not. -/
def geminiOnly : List GeminiDep :=
  (geminiUsed.map (·.id)).filter (fun g => g ∉ claudeUsed.map (fun d => sameAs d.id))

/-- 4 of gemini's 7 dependencies have no counterpart in claude's record. The
paper itself names the fitted linear map as a channel of paired information. -/
theorem gemini_only_deps :
    geminiOnly =
      [ .frozenVisionBenchmarkTargets, .pairedOrthonormalLinearMap,
        .goodViewHyperparamSelection, .witCorpusOverlap ] := by
  decide

/-- Same verdict on the headline, the conditional theorem and the engineering claim. -/
theorem verdicts_agree :
    verdict EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa.headlineClaim
        = verdict EpistemicLedger.Cases.GeminiBalestrieroLeCunPlatonicJepa.headlinePrhTheoremClaim
      ∧ verdict EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa.conditionalTheoremClaim
        = verdict EpistemicLedger.Cases.GeminiBalestrieroLeCunPlatonicJepa.conditionalIdealizedTheoremClaim
      ∧ verdict EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa.engineeringClaim
        = verdict EpistemicLedger.Cases.GeminiBalestrieroLeCunPlatonicJepa.narrowEngineeringClaim := by
  decide

/-- The one status the two auditors disagree on: whether "modalities share one
positive-pair distribution" is unchecked (claude) or known false (gemini) for
the paper's experiments. The paper: "no experiment meets the hypotheses of
Theorem 1 exactly, since ... the image side mostly uses crops as positives".
That sentence supports gemini's status. -/
theorem shared_positives_status_disagreement :
    (⟨.sharedPositivePairDistribution, .bet⟩ :
        Hypothesis EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa.Hyp)
        ∈ EpistemicLedger.Cases.BalestrieroLeCunPlatonicJepa.headlineClaim.hypotheses
      ∧ (⟨.sharedPositiveKernelAcrossModalities, .knownFalse⟩ :
        Hypothesis EpistemicLedger.Cases.GeminiBalestrieroLeCunPlatonicJepa.Hyp)
        ∈ EpistemicLedger.Cases.GeminiBalestrieroLeCunPlatonicJepa.headlinePrhTheoremClaim.hypotheses := by
  decide

end BalestrieroLeCun

end EpistemicLedger.Cases.AuditorAgreementClaudeVsGemini
