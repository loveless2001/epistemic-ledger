import EpistemicLedger.OperationFlow

/-
Epistemic Ledger v2 — Benchmark Suite across 4 real papers + 1 genuine-emergence control:
  1. Barontini (2026), "Testing the problem of time with cold atoms" (arXiv:2509.07745v3)
  2. Balestriero & LeCun (2026), "Proving and Improving the PRH with JEPAs" (arXiv:2610.39302v1)
  3. Spacetime Emergence in the Memory of a Learning Agent (arXiv:2611.03596)
  4. RePT: 3D Geometry Emerges from 2D Relational Pretraining (arXiv:2611.31601)
     — contrasting:
       (4a) Main ARKitScenes pipeline (offline depth + camera pose track construction -> 3D taint!)
       (4b) Clean 2D-only control (experimenter-set RGB dataset, 2D backbone, 2D relational loss,
            NO 3D taint -> ADMISSIBLE! Proves v2 fixes v1's false-rejection degeneration.)
-/
namespace EpistemicLedger.Cases.V2FlowBenchmarks

open EpistemicLedger
open EpistemicLedger.OperationFlow

/-! ### Case 1: Barontini (2026) — Cold Atoms & Problem of Time -/
namespace BarontiniFlow

inductive Node where
  | opticalTrap
  | opticalBarrierV
  | labClock2ms
  | becAtoms
  | brightDarkPartition
  | entropyFlow
  | entropicTimeTau
  | effSchrodingerEq
  deriving DecidableEq, Repr

inductive Tag where
  | harmonicPotential
  | timeOrdering
  | externalBoundary
  deriving DecidableEq, Repr

def graph : FlowGraph Node Tag where
  sources :=
    [ ⟨.opticalTrap, .setByExperimenter, [.harmonicPotential]⟩
    , ⟨.opticalBarrierV, .setByExperimenter, [.externalBoundary, .timeOrdering]⟩
    , ⟨.labClock2ms, .setByExperimenter, [.timeOrdering]⟩
    , ⟨.becAtoms, .measured, []⟩
    ]
  ops :=
    [ ⟨"spatial_cut_x0", [.becAtoms, .opticalTrap, .opticalBarrierV], .brightDarkPartition,
        .partition [.externalBoundary]⟩
    , ⟨"measure_entropy_sequence", [.brightDarkPartition, .labClock2ms], .entropyFlow,
        .transform []⟩
    , ⟨"absorb_barrier_in_norm", [.entropyFlow], .entropicTimeTau,
        .forget .timeOrdering .contradicted⟩
    , ⟨"feshbach_villars_positive_branch", [.entropicTimeTau], .effSchrodingerEq,
        .transform [.timeOrdering]⟩
    ]

/-- Headline: internal time ordering emerges without external time ordering. -/
def headlineClaim : FlowClaim Node Tag where
  statement := "Observed-sector time ordering τ emerges purely from internal degrees of freedom."
  graph := graph
  kind := .emergesWithout .entropicTimeTau .timeOrdering

/-- Narrow conditional claim declaring all upstream experimental sources. -/
def narrowClaim : FlowClaim Node Tag where
  statement := "Given the optical trap, barrier V, 2 ms lab clock, and BEC measurements, τ orders bright-sector evolution."
  graph := graph
  kind := .conditionalFlow .entropicTimeTau [.opticalTrap, .opticalBarrierV, .labClock2ms, .becAtoms]

theorem headline_rejected : flowVerdict headlineClaim = .rejected := by decide
theorem narrow_admissible : flowVerdict narrowClaim = .admissible := by decide

theorem headline_catches_failed_forget :
    FlowFinding.failedForgetOnPath "absorb_barrier_in_norm" Tag.timeOrdering Invariance.contradicted
      ∈ auditFlow headlineClaim := by decide

end BarontiniFlow

/-! ### Case 2: Balestriero & LeCun (2026) — Platonic JEPA -/
namespace PlatonicJepaFlow

inductive Node where
  | trueWorldZ
  | webImageCorpus
  | pairingOracle
  | clipImageTextPretraining
  | llavaRecaptioner
  | realModalityProjection
  | textJepa
  | clipVisionEncoder
  deriving DecidableEq, Repr

inductive Tag where
  | worldStateZ
  | crossModalAlignment
  deriving DecidableEq, Repr

/--
Faithful graph for Recap-DataComp text JEPA vs. CLIP vision encoder (Sec. 4.3 & Sec. 7):
- `clipImageTextPretraining` feeds `llavaRecaptioner` (LLaVA uses CLIP ViT-L/14 as its vision
  encoder) AND `clipVisionEncoder`.
- `pairingOracle` and `llavaRecaptioner` feed ONLY `textJepa` (NOT the vision encoder!).
-/
def graph : FlowGraph Node Tag where
  sources :=
    [ ⟨.trueWorldZ, .measured, [.worldStateZ]⟩
    , ⟨.webImageCorpus, .measured, []⟩
    , ⟨.pairingOracle, .setByExperimenter, [.crossModalAlignment]⟩
    , ⟨.clipImageTextPretraining, .setByExperimenter, [.crossModalAlignment]⟩
    ]
  ops :=
    [ ⟨"lossy_real_observation", [.trueWorldZ, .webImageCorpus], .realModalityProjection,
        .lossyOn [.worldStateZ] []⟩
    , ⟨"llava_recaption_from_clip", [.realModalityProjection, .clipImageTextPretraining],
        .llavaRecaptioner, .transform []⟩
    , ⟨"train_text_jepa", [.realModalityProjection, .pairingOracle, .llavaRecaptioner],
        .textJepa, .transform []⟩
    , ⟨"encode_clip_vision", [.realModalityProjection, .clipImageTextPretraining],
        .clipVisionEncoder, .transform []⟩
    ]

/-- Claim A: Text JEPA (on Recap-DataComp) and CLIP Vision Encoder independently converge. -/
def independentConvergenceClaim : FlowClaim Node Tag where
  statement := "Recap-DataComp text JEPA and CLIP vision encoder independently converge on cross-modal alignment."
  graph := graph
  kind := .independentConvergence .textJepa .clipVisionEncoder .crossModalAlignment

/-- Claim B: Text JEPA uniquely recovers true world state z (fails due to lossy real modalities, e.g. 'The Dress'). -/
def uniqueRecoveryClaim : FlowClaim Node Tag where
  statement := "The learned representation uniquely recovers the underlying world state z."
  graph := graph
  kind := .uniqueRecovery .textJepa .worldStateZ

/-- Claim C: Narrow engineering claim declaring all upstream inputs. -/
def narrowEngineeringClaim : FlowClaim Node Tag where
  statement := "Given web images, pairing oracle, and LLaVA/CLIP recaptions, good-view text JEPA aligns with vision."
  graph := graph
  kind := .conditionalFlow .textJepa [.trueWorldZ, .webImageCorpus, .pairingOracle, .clipImageTextPretraining]

theorem independence_rejected : flowVerdict independentConvergenceClaim = .rejected := by decide
theorem unique_recovery_rejected : flowVerdict uniqueRecoveryClaim = .rejected := by decide
theorem narrow_engineering_admissible : flowVerdict narrowEngineeringClaim = .admissible := by decide

theorem catches_shared_clip_pretraining :
    FlowFinding.sharedUpstreamStructure Node.clipImageTextPretraining Tag.crossModalAlignment
      ∈ auditFlow independentConvergenceClaim := by decide

theorem catches_lossy_observation :
    FlowFinding.lossyChannelOnPath "lossy_real_observation" Node.realModalityProjection
      ∈ auditFlow uniqueRecoveryClaim := by decide

end PlatonicJepaFlow

/-! ### Case 3: Spacetime Emergence in the Memory of a Learning Agent (2611.03596) -/
namespace SpacetimeAgentFlow

inductive Node where
  | minkowskiQftSimulator
  | quantumProbeSetup
  | mutualInfoReward
  | rlInternalMemory
  | externalMetricExtractor
  | reconstructedLightCone
  deriving DecidableEq, Repr

inductive Tag where
  | minkowskiCausalStructure
  | rlOptimization
  deriving DecidableEq, Repr

def graph : FlowGraph Node Tag where
  sources :=
    [ ⟨.minkowskiQftSimulator, .setByExperimenter, [.minkowskiCausalStructure]⟩
    , ⟨.quantumProbeSetup, .setByExperimenter, []⟩
    , ⟨.externalMetricExtractor, .setByExperimenter, []⟩
    ]
  ops :=
    [ ⟨"probe_field_interaction", [.minkowskiQftSimulator, .quantumProbeSetup], .mutualInfoReward,
        .transform []⟩
    , ⟨"model_based_rl_training", [.mutualInfoReward], .rlInternalMemory,
        .transform [.rlOptimization]⟩
    , ⟨"external_metric_fit", [.rlInternalMemory, .externalMetricExtractor], .reconstructedLightCone,
        .transform []⟩
    ]

/-- Headline: Minkowski causal structure emerges without being supplied upstream. -/
def headlineClaim : FlowClaim Node Tag where
  statement := "Causal structure of spacetime emerges in the RL agent's memory without spacetime metric input."
  graph := graph
  kind := .emergesWithout .reconstructedLightCone .minkowskiCausalStructure

/-- Narrow simulator-recovery claim declaring the Minkowski simulator, probes, and external extractor. -/
def narrowRecoveryClaim : FlowClaim Node Tag where
  statement := "An RL agent interacting with a Minkowski QFT simulator reconstructs the simulator's null structure via external extraction tools."
  graph := graph
  kind := .conditionalFlow .reconstructedLightCone
    [.minkowskiQftSimulator, .quantumProbeSetup, .externalMetricExtractor]

theorem headline_rejected : flowVerdict headlineClaim = .rejected := by decide
theorem narrow_recovery_admissible : flowVerdict narrowRecoveryClaim = .admissible := by decide

theorem headline_exhibits_multi_hop_smuggling_path :
    FlowFinding.smuggledStructure
      Tag.minkowskiCausalStructure
      Node.minkowskiQftSimulator
      [.minkowskiQftSimulator, .mutualInfoReward, .rlInternalMemory, .reconstructedLightCone]
      ∈ auditFlow headlineClaim := by decide

end SpacetimeAgentFlow

/-! ### Case 4: RePT (2611.31601) — Main Run, CoTracker3 Ablation, and Clean 2D Control -/
namespace RePTFlow

inductive Node where
  | arkitRgbFrames
  | arkitDepthAndCameraPose
  | dinoV2Backbone
  | relational2DLoss
  | offlineTrackBuilder
  | depthPoseAblated
  | coTracker3Pretrained
  | rgbOnlyTracks
  | reptMainModel
  | reptAblationModel
  | reptClean2DModel
  deriving DecidableEq, Repr

inductive Tag where
  | geometry3D
  | visualFeatures2D
  | relational2DObjective
  deriving DecidableEq, Repr

/--
4a: Main ARKitScenes pipeline (Sec. 4.1: offline tracks built from depth maps + camera poses).
Audits the stronger claim "no 3D information in the pipeline"; the paper's narrower wording
("no 3D prediction targets") allows depth/pose during offline track construction.
-/
def mainGraph : FlowGraph Node Tag where
  sources :=
    [ ⟨.arkitRgbFrames, .measured, [.visualFeatures2D]⟩
    , ⟨.arkitDepthAndCameraPose, .setByExperimenter, [.geometry3D]⟩
    , ⟨.dinoV2Backbone, .setByExperimenter, [.visualFeatures2D]⟩
    , ⟨.relational2DLoss, .setByExperimenter, [.relational2DObjective]⟩
    ]
  ops :=
    [ ⟨"offline_depth_pose_track_builder", [.arkitRgbFrames, .arkitDepthAndCameraPose],
        .offlineTrackBuilder, .transform []⟩
    , ⟨"train_rept_main", [.offlineTrackBuilder, .dinoV2Backbone, .relational2DLoss],
        .reptMainModel, .transform []⟩
    ]

/--
4b: RePT with Table 2 / Appendix A.2 RGB-only CoTracker3 ablation:
- `depth_pose_ablated_by_table2` cleanly blocks the depth+pose path via `.forget .geometry3D .shown`.
- The graph then isolates the remaining auditable question: if `coTracker3Pretrained` carries
  `.geometry3D` (from synthetic 3D point-tracking pretraining), the claim is still rejected via
  `coTracker3Pretrained`; if it does not, the claim passes.
-/
def ablationGraph (coTrackerCarries3D : Bool) : FlowGraph Node Tag where
  sources :=
    [ ⟨.arkitRgbFrames, .measured, [.visualFeatures2D]⟩
    , ⟨.arkitDepthAndCameraPose, .setByExperimenter, [.geometry3D]⟩
    , ⟨.coTracker3Pretrained, .setByExperimenter, if coTrackerCarries3D then [.geometry3D] else []⟩
    , ⟨.dinoV2Backbone, .setByExperimenter, [.visualFeatures2D]⟩
    , ⟨.relational2DLoss, .setByExperimenter, [.relational2DObjective]⟩
    ]
  ops :=
    [ ⟨"offline_depth_pose_track_builder", [.arkitRgbFrames, .arkitDepthAndCameraPose],
        .offlineTrackBuilder, .transform []⟩
    , ⟨"table2_rgb_ablation_forget_depth_pose", [.offlineTrackBuilder],
        .depthPoseAblated, .forget .geometry3D .shown⟩
    , ⟨"cotracker3_rgb_tracks", [.arkitRgbFrames, .coTracker3Pretrained],
        .rgbOnlyTracks, .transform []⟩
    , ⟨"train_rept_ablation", [.depthPoseAblated, .rgbOnlyTracks, .dinoV2Backbone, .relational2DLoss],
        .reptAblationModel, .transform []⟩
    ]

def mainEmergenceClaim : FlowClaim Node Tag where
  statement := "3D geometry emerges from 2D relational pretraining with no 3D information in the pipeline."
  graph := mainGraph
  kind := .emergesWithout .reptMainModel .geometry3D

def ablationClaim (coTrackerCarries3D : Bool) : FlowClaim Node Tag where
  statement := "No 3D-tagged path enters RePT after the Table 2 CoTracker3 RGB-only ablation."
  graph := ablationGraph coTrackerCarries3D
  kind := .emergesWithout .reptAblationModel .geometry3D

theorem main_rejected_for_depth_pose_smuggling :
    flowVerdict mainEmergenceClaim = .rejected := by decide

theorem main_exhibits_offline_3d_path :
    FlowFinding.smuggledStructure
      Tag.geometry3D
      Node.arkitDepthAndCameraPose
      [.arkitDepthAndCameraPose, .offlineTrackBuilder, .reptMainModel]
      ∈ auditFlow mainEmergenceClaim := by decide

/-- With Table 2 ablation blocking depth+pose, if CoTracker3 itself carries 3D pretraining taint,
the checker pinpoints CoTracker3 as the remaining smuggling path. -/
theorem ablation_pinpoints_cotracker_if_tainted :
    flowVerdict (ablationClaim true) = .rejected ∧
    FlowFinding.smuggledStructure
      Tag.geometry3D
      Node.coTracker3Pretrained
      [.coTracker3Pretrained, .rgbOnlyTracks, .reptAblationModel]
      ∈ auditFlow (ablationClaim true) := by decide

/-- With Table 2 ablation blocking depth+pose and no 3D taint in CoTracker3/DINOv2,
no 3D-tagged path is found in the recorded graph despite multiple `setByExperimenter` nodes. -/
theorem ablation_admissible_when_cotracker_clean :
    flowVerdict (ablationClaim false) = .admissible := by decide

end RePTFlow

/-! ### Regression Tests for Codex's & Claude's Review Findings -/
namespace AdversarialRegressions

inductive Node where
  | input | mid | output | other
  deriving DecidableEq, Repr

inductive Tag where
  | geometry
  deriving DecidableEq, Repr

/-- Regression 1 (Codex): `uniqueRecovery` must reject when `.geometry` is fabricated by an op
rather than carried by an upstream `SourceNode`. -/
def fabricatedRecovery : FlowClaim Node Tag where
  statement := "Fabricated tag in op should not satisfy uniqueRecovery access."
  graph := ⟨[⟨.input, .measured, []⟩], [⟨"supply_geometry", [.input], .output, .transform [.geometry]⟩]⟩
  kind := .uniqueRecovery .output .geometry

/-- Regression 2 (Codex): `independentConvergence` must reject when two branches share an
unforgotten `setByExperimenter` source even if that source carries `[]`. -/
def sharedExperimenterInput : FlowClaim Node Tag where
  statement := "Shared unforgotten experimenter input violates branch independence."
  graph :=
    ⟨[⟨.input, .setByExperimenter, []⟩],
     [⟨"left", [.input], .output, .transform [.geometry]⟩,
      ⟨"right", [.input], .other, .transform [.geometry]⟩]⟩
  kind := .independentConvergence .output .other .geometry

/-- Regression 3 (Codex & Claude): `conditionalFlow` must reject graphs with dangling inputs. -/
def danglingInputGraph : FlowClaim Node Tag where
  statement := "Incomplete graph consuming undeclared node must be rejected."
  graph := ⟨[], [⟨"consume_missing", [.input], .output, .transform []⟩]⟩
  kind := .conditionalFlow .output []

/-- Regression 4 (Claude): an idle `.forget tag .notShown` when no upstream node carries `tag`
must NOT reject the claim. -/
def idleForgetGraph : FlowClaim Node Tag where
  statement := "Idle forget with no upstream tag origin should not reject."
  graph :=
    ⟨[⟨.input, .setByExperimenter, []⟩],
     [⟨"step", [.input], .mid, .transform []⟩,
      ⟨"idle_forget", [.mid], .output, .forget .geometry .notShown⟩]⟩
  kind := .emergesWithout .output .geometry

theorem fabricated_recovery_rejected :
    flowVerdict fabricatedRecovery = .rejected ∧
    FlowFinding.unaccessedTargetStructure Node.output Tag.geometry ∈ auditFlow fabricatedRecovery := by
  decide

theorem shared_experimenter_rejected :
    flowVerdict sharedExperimenterInput = .rejected ∧
    FlowFinding.sharedExperimenterSource Node.input ∈ auditFlow sharedExperimenterInput := by
  decide

theorem dangling_input_rejected :
    flowVerdict danglingInputGraph = .rejected ∧
    FlowFinding.danglingInput "consume_missing" Node.input ∈ auditFlow danglingInputGraph := by
  decide

theorem idle_forget_admissible :
    flowVerdict idleForgetGraph = .admissible := by
  decide

end AdversarialRegressions

/-! ### Policy 3 (v2.1) Tests: Separated Channel-Exclusion (Alarm 1) + Author-Supplied (Alarm 2) -/
namespace Policy3Tests

inductive Node where
  | measuredRgb
  | measuredDepth
  | simRenderer
  | simRgb
  | simDepth
  | frozenDinoV2
  | lossTarget
  | trainedModel
  | evalMetric
  deriving DecidableEq, Repr

inductive Tag where
  | geometry3D
  deriving DecidableEq, Repr

/-- Case A (Codex's measured-depth-in-loss counterexample):
`measuredDepth` (`.measured`, carrying `.geometry3D`) is fed into `lossTarget`.
Alarm 1 (`excludedChannelLeak`) MUST fire -> rejected! -/
def measuredDepthInLoss : FlowClaim Node Tag where
  statement := "3D emerges without 3D prediction targets (actually feeds measured depth into lossTarget)."
  graph :=
    ⟨[⟨.measuredRgb, .measured, [.geometry3D]⟩,
      ⟨.measuredDepth, .measured, [.geometry3D]⟩],
     [⟨"loss_with_depth", [.measuredDepth], .lossTarget, .transform []⟩,
      ⟨"train", [.measuredRgb, .lossTarget], .trainedModel, .transform []⟩]⟩
  kind := .emergesWithExclusion .trainedModel .lossTarget .geometry3D

/-- Case B (Codex's clean measured-depth-in-eval-only counterpart):
Even if raw `measuredRgb` is tagged `.geometry3D` (Agent B's reading of perspective cues),
`measuredDepth` is used ONLY in `evalMetric` (NOT `lossTarget`), and no `setByExperimenter`
node carries `.geometry3D`. Both Alarm 1 and Alarm 2 are clean -> admissible! -/
def measuredDepthInEvalOnly : FlowClaim Node Tag where
  statement := "3D emerges from measured RGB without 3D prediction targets (measured depth only in eval)."
  graph :=
    ⟨[⟨.measuredRgb, .measured, [.geometry3D]⟩,
      ⟨.measuredDepth, .measured, [.geometry3D]⟩],
     [⟨"2d_loss_target", [], .lossTarget, .transform []⟩,
      ⟨"train", [.measuredRgb, .lossTarget], .trainedModel, .transform []⟩,
      ⟨"eval", [.trainedModel, .measuredDepth], .evalMetric, .transform []⟩]⟩
  kind := .emergesWithExclusion .trainedModel .lossTarget .geometry3D

/-- Case C (RePT with frozen DINOv2):
`measuredRgb` tagged `.geometry3D` does NOT fire Alarm 2, `lossTarget` has no 3D (Alarm 1 clean),
but `frozenDinoV2` (`.setByExperimenter`, `.geometry3D`) fires Alarm 2 -> rejected! -/
def reptWithFrozenDino : FlowClaim Node Tag where
  statement := "3D emerges from measured RGB + frozen DINOv2 without 3D prediction targets."
  graph :=
    ⟨[⟨.measuredRgb, .measured, [.geometry3D]⟩,
      ⟨.frozenDinoV2, .setByExperimenter, [.geometry3D]⟩],
     [⟨"2d_loss_target", [], .lossTarget, .transform []⟩,
      ⟨"train", [.measuredRgb, .frozenDinoV2, .lossTarget], .trainedModel, .transform []⟩]⟩
  kind := .emergesWithExclusion .trainedModel .lossTarget .geometry3D

/-- Case D (Codex's Simulator Case 1 — RGB from simulator into model, depth in eval only):
Alarm 1 is clean (depth not in lossTarget), but Alarm 2 fires on `simRenderer` (`.setByExperimenter`)
-> rejected under Policy 3! -/
def simulatorRgbOnly : FlowClaim Node Tag where
  statement := "3D emerges from simulator RGB without 3D prediction targets (depth in eval only)."
  graph :=
    ⟨[⟨.simRenderer, .setByExperimenter, [.geometry3D]⟩],
     [⟨"render_rgb", [.simRenderer], .simRgb, .transform []⟩,
      ⟨"render_depth", [.simRenderer], .simDepth, .transform []⟩,
      ⟨"2d_loss_target", [], .lossTarget, .transform []⟩,
      ⟨"train", [.simRgb, .lossTarget], .trainedModel, .transform []⟩,
      ⟨"eval", [.trainedModel, .simDepth], .evalMetric, .transform []⟩]⟩
  kind := .emergesWithExclusion .trainedModel .lossTarget .geometry3D

/-- Case E (Codex's Simulator Case 2 — depth from simulator ALSO fed into lossTarget):
BOTH Alarm 1 (`excludedChannelLeak`) AND Alarm 2 (`authorSuppliedStructure`) fire -> rejected! -/
def simulatorDepthInLoss : FlowClaim Node Tag where
  statement := "3D emerges from simulator without 3D prediction targets (depth also fed into loss)."
  graph :=
    ⟨[⟨.simRenderer, .setByExperimenter, [.geometry3D]⟩],
     [⟨"render_rgb", [.simRenderer], .simRgb, .transform []⟩,
      ⟨"render_depth", [.simRenderer], .simDepth, .transform []⟩,
      ⟨"depth_loss", [.simDepth], .lossTarget, .transform []⟩,
      ⟨"train", [.simRgb, .lossTarget], .trainedModel, .transform []⟩]⟩
  kind := .emergesWithExclusion .trainedModel .lossTarget .geometry3D

theorem measured_depth_in_loss_rejected_by_alarm1 :
    flowVerdict measuredDepthInLoss = .rejected ∧
    FlowFinding.excludedChannelLeak Tag.geometry3D Node.measuredDepth [.measuredDepth, .lossTarget]
      ∈ auditFlow measuredDepthInLoss := by
  decide

theorem measured_depth_in_eval_only_admissible :
    flowVerdict measuredDepthInEvalOnly = .admissible := by
  decide

theorem rept_frozen_dino_rejected_by_alarm2_only :
    flowVerdict reptWithFrozenDino = .rejected ∧
    FlowFinding.authorSuppliedStructure Tag.geometry3D Node.frozenDinoV2 [.frozenDinoV2, .trainedModel]
      ∈ auditFlow reptWithFrozenDino := by
  decide

theorem simulator_rgb_only_rejected_by_alarm2 :
    flowVerdict simulatorRgbOnly = .rejected ∧
    FlowFinding.authorSuppliedStructure Tag.geometry3D Node.simRenderer [.simRenderer, .simRgb, .trainedModel]
      ∈ auditFlow simulatorRgbOnly := by
  decide

theorem simulator_depth_in_loss_triggers_both_alarms :
    flowVerdict simulatorDepthInLoss = .rejected ∧
    FlowFinding.excludedChannelLeak Tag.geometry3D Node.simRenderer [.simRenderer, .simDepth, .lossTarget]
      ∈ auditFlow simulatorDepthInLoss ∧
    FlowFinding.authorSuppliedStructure Tag.geometry3D Node.simRenderer [.simRenderer, .simRgb, .trainedModel]
      ∈ auditFlow simulatorDepthInLoss := by
  decide

end Policy3Tests

/-! ### Tier 2 (v2.3) Tests: Numeric Budgets, Forget-Proof Costs, Arm Independence & Post-Hoc Metering -/
namespace EffectivenessTests

inductive Node where
  | sharedGpuCluster
  | accountA
  | accountB
  | humanOperatorHours
  | forgottenHumanHours
  | autonomousSocietyRun
  | humanPlusAiControlRun
  | clonedControlArm
  | postHocBillingMeter
  | partialCostLedger
  | rawStudyCountReport
  | costNormalizedComparison
  deriving DecidableEq, Repr

inductive Tag where
  | resourceCost
  deriving DecidableEq, Repr

/-- Case 1 (v2.4 structural): Independent arms + post-hoc cost ledger metering both accounts -> ADMISSIBLE! -/
def separateAccountsEqualDollars : FlowClaim Node Tag where
  statement := "Two independent arms metered post-hoc directly from both cost accounts."
  graph :=
    ⟨[⟨.accountA, .setByExperimenter, [.resourceCost]⟩,
      ⟨.accountB, .setByExperimenter, [.resourceCost]⟩],
     [⟨"run_method", [.accountA], .autonomousSocietyRun, .transform []⟩,
      ⟨"run_control", [.accountB], .humanPlusAiControlRun, .transform []⟩,
      ⟨"post_hoc_bill", [.accountA, .accountB, .autonomousSocietyRun, .humanPlusAiControlRun],
        .postHocBillingMeter, .transform []⟩,
      ⟨"eval", [.autonomousSocietyRun, .humanPlusAiControlRun, .postHocBillingMeter],
        .costNormalizedComparison, .transform []⟩]⟩
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .humanPlusAiControlRun) (some .postHocBillingMeter) .resourceCost

/-- Case 2 (Codex P1-2): `forget .resourceCost .shown` CANNOT erase physically spent human hours! -/
def forgetShownCannotEraseCost : FlowClaim Node Tag where
  statement := "Human hours passed through forget .shown into method, omitted from ledger."
  graph :=
    ⟨[⟨.sharedGpuCluster, .setByExperimenter, [.resourceCost]⟩,
      ⟨.humanOperatorHours, .setByExperimenter, [.resourceCost]⟩],
     [⟨"try_forget_hours", [.humanOperatorHours], .forgottenHumanHours, .forget .resourceCost .shown⟩,
      ⟨"run_method", [.sharedGpuCluster, .forgottenHumanHours], .autonomousSocietyRun, .transform []⟩,
      ⟨"run_control", [.sharedGpuCluster], .humanPlusAiControlRun, .transform []⟩,
      ⟨"gpu_only_ledger", [.sharedGpuCluster], .partialCostLedger, .transform []⟩,
      ⟨"eval", [.autonomousSocietyRun, .humanPlusAiControlRun, .partialCostLedger],
        .costNormalizedComparison, .transform []⟩]⟩
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .humanPlusAiControlRun) (some .partialCostLedger) .resourceCost

/-- Case 3 (Codex P1-3): Control arm derived from method output -> REJECTED (`dependentControlArm`)! -/
def controlDerivedFromMethod : FlowClaim Node Tag where
  statement := "Control merely copies/transforms method output."
  graph :=
    ⟨[⟨.sharedGpuCluster, .setByExperimenter, [.resourceCost]⟩],
     [⟨"run_method", [.sharedGpuCluster], .autonomousSocietyRun, .transform []⟩,
      ⟨"clone_method_as_ctrl", [.autonomousSocietyRun], .clonedControlArm, .transform []⟩,
      ⟨"bill", [.sharedGpuCluster], .postHocBillingMeter, .transform []⟩,
      ⟨"eval", [.autonomousSocietyRun, .clonedControlArm, .postHocBillingMeter],
        .costNormalizedComparison, .transform []⟩]⟩
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .clonedControlArm) (some .postHocBillingMeter) .resourceCost

/-- Case 4 (Codex R2 P1-2): Ledger cloned solely from control output (no direct metering path) -> REJECTED! -/
def ledgerClonedFromControlOnly : FlowClaim Node Tag where
  statement := "Fake ledger reads only control output rather than metering cost sources directly."
  graph :=
    ⟨[⟨.sharedGpuCluster, .setByExperimenter, [.resourceCost]⟩],
     [⟨"run_method", [.sharedGpuCluster], .autonomousSocietyRun, .transform []⟩,
      ⟨"run_control", [.sharedGpuCluster], .humanPlusAiControlRun, .transform []⟩,
      ⟨"clone_ctrl_as_ledger", [.humanPlusAiControlRun], .partialCostLedger, .transform []⟩,
      ⟨"eval", [.autonomousSocietyRun, .humanPlusAiControlRun, .partialCostLedger],
        .costNormalizedComparison, .transform []⟩]⟩
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .humanPlusAiControlRun) (some .partialCostLedger) .resourceCost

/-- Case 5 (Society of AI Scientists macro): no control, no ledger -> UNESTABLISHED (`epistemicVerdict`)! -/
def societyNoControlNoCost : FlowClaim Node Tag where
  statement := "936 autonomous agents across 35 labs without control or cost ledger."
  graph :=
    ⟨[⟨.sharedGpuCluster, .setByExperimenter, [.resourceCost]⟩,
      ⟨.humanOperatorHours, .setByExperimenter, [.resourceCost]⟩],
     [⟨"run_936_agents", [.sharedGpuCluster, .humanOperatorHours], .autonomousSocietyRun, .transform []⟩,
      ⟨"count_papers", [.autonomousSocietyRun], .rawStudyCountReport, .transform []⟩]⟩
  kind := .effectivenessClaim .autonomousSocietyRun .rawStudyCountReport none none .resourceCost

theorem separate_accounts_equal_dollars_posthoc_meter_admissible :
    flowVerdict separateAccountsEqualDollars = .admissible := by
  decide

theorem forget_shown_cannot_erase_spent_cost :
    flowVerdict forgetShownCannotEraseCost = .rejected ∧
    FlowFinding.unaccountedCostSource Node.humanOperatorHours Node.partialCostLedger Tag.resourceCost
      ∈ auditFlow forgetShownCannotEraseCost := by
  decide

theorem dependent_control_arm_rejected :
    flowVerdict controlDerivedFromMethod = .rejected ∧
    FlowFinding.dependentControlArm Node.autonomousSocietyRun Node.clonedControlArm
      ∈ auditFlow controlDerivedFromMethod := by
  decide

theorem ledger_cloned_from_control_rejected :
    flowVerdict ledgerClonedFromControlOnly = .rejected ∧
    FlowFinding.unaccountedCostSource Node.sharedGpuCluster Node.partialCostLedger Tag.resourceCost
      ∈ auditFlow ledgerClonedFromControlOnly := by
  decide

theorem society_rejected_no_control_no_cost :
    flowVerdict societyNoControlNoCost = .rejected ∧
    FlowFinding.missingMatchedControl Node.autonomousSocietyRun ∈ auditFlow societyNoControlNoCost ∧
    FlowFinding.missingCostAccounting Node.autonomousSocietyRun Tag.resourceCost ∈ auditFlow societyNoControlNoCost := by
  decide

end EffectivenessTests

/-! ### Four-State `EpistemicVerdict` Tests (`admissible` / `unestablished` / `rejected` / `outOfScope`) -/
namespace EpistemicVerdictTests

open EffectivenessTests

def normativeLegalBalancingClaim : FlowClaim EffectivenessTests.Node EffectivenessTests.Tag where
  statement := "Whether an unlawful Terry stop is attenuated by a pre-existing arrest warrant under the Fourth Amendment."
  graph := EffectivenessTests.societyNoControlNoCost.graph
  kind := .outOfScope "Normative Fourth Amendment attenuation balancing is a legal-policy value judgment, not a causal-flow claim."

theorem separate_accounts_epistemic_admissible :
    epistemicVerdict EffectivenessTests.separateAccountsEqualDollars = .admissible := by
  decide

theorem society_missing_control_and_cost_epistemic_unestablished :
    epistemicVerdict EffectivenessTests.societyNoControlNoCost = .unestablished := by
  decide

theorem dependent_control_epistemic_rejected :
    epistemicVerdict EffectivenessTests.controlDerivedFromMethod = .rejected := by
  decide

theorem normative_balancing_epistemic_out_of_scope :
    epistemicVerdict normativeLegalBalancingClaim = .outOfScope ∧
    FlowFinding.claimOutOfScope
      "Normative Fourth Amendment attenuation balancing is a legal-policy value judgment, not a causal-flow claim."
      ∈ auditFlow normativeLegalBalancingClaim := by
  decide

/-- D4: `missingCostAccounting` alone is informational note-only and does NOT move `epistemicVerdict`
    away from `.admissible` when an independent matched control feeds evaluation. -/
def independentControlNoCostLedger : FlowClaim EffectivenessTests.Node EffectivenessTests.Tag where
  statement := "Randomised treatment vs independent control arm without a declared cost ledger."
  graph :=
    ⟨[⟨.accountA, .setByExperimenter, []⟩,
      ⟨.accountB, .setByExperimenter, []⟩],
     [⟨"run_treatment", [.accountA], .autonomousSocietyRun, .transform []⟩,
      ⟨"run_control", [.accountB], .humanPlusAiControlRun, .transform []⟩,
      ⟨"compare_arms", [.autonomousSocietyRun, .humanPlusAiControlRun], .costNormalizedComparison, .transform []⟩]⟩
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .humanPlusAiControlRun) none .resourceCost

theorem independent_control_no_cost_ledger_epistemic_admissible_with_note :
    epistemicVerdict independentControlNoCostLedger = .admissible ∧
    FlowFinding.missingCostAccounting EffectivenessTests.Node.autonomousSocietyRun EffectivenessTests.Tag.resourceCost
      ∈ auditFlow independentControlNoCostLedger := by
  decide

/-! #### Codex `#27358` Regression Tests: `.notShown` on sole path vs bypass, and `uniqueRecovery` side-branch `.lossy` -/

inductive RNode where
  | srcTag | bypassTag | noise | forgotten | roundedNoise | pairOut | target
  deriving DecidableEq, Repr

inductive RTag where
  | signal
  deriving DecidableEq, Repr

/-- Sole path goes through `.forget .signal .notShown` with NO bypass -> `unestablished` (NOT `rejected`). -/
def solePathNotShownClaim : FlowClaim RNode RTag where
  statement := "Signal emerges after an unverified forget step on the sole path."
  graph :=
    ⟨[⟨.srcTag, .setByExperimenter, [.signal]⟩],
     [⟨"unverified_forget", [.srcTag], .forgotten, .forget .signal .notShown⟩,
      ⟨"readout", [.forgotten], .target, .transform []⟩]⟩
  kind := .emergesWithout .target .signal

/-- Same `.forget .signal .notShown` PLUS an un-attempted bypass -> `rejected` (confirmed leak). -/
def notShownWithBypassClaim : FlowClaim RNode RTag where
  statement := "Signal has an unverified forget on one branch and an un-attempted bypass on another."
  graph :=
    ⟨[⟨.srcTag, .setByExperimenter, [.signal]⟩,
      ⟨.bypassTag, .setByExperimenter, [.signal]⟩],
     [⟨"unverified_forget", [.srcTag], .forgotten, .forget .signal .notShown⟩,
      ⟨"merge", [.forgotten, .bypassTag], .target, .transform []⟩]⟩
  kind := .emergesWithout .target .signal

/-- Codex Finding 2a: `pair(signal_raw, rounded_noise)` — `.lossy` is ONLY on the unrelated `noise` branch,
    so `uniqueRecovery pairOut .signal` is `admissible` (no false rejection!). -/
def losslessSignalWithLossyNoiseClaim : FlowClaim RNode RTag where
  statement := "Recovering raw signal from a pair (raw signal, rounded noise)."
  graph :=
    ⟨[⟨.srcTag, .measured, [.signal]⟩,
      ⟨.noise, .measured, []⟩],
     [⟨"round_noise", [.noise], .roundedNoise, .lossy []⟩,
      ⟨"make_pair", [.srcTag, .roundedNoise], .pairOut, .transform []⟩]⟩
  kind := .uniqueRecovery .pairOut .signal

/-- Codex Finding 2b: `uniqueRecovery` with NO upstream `SourceNode` carrying `.signal` -> `unestablished`
    (missing observational access in the declared graph; legacy `flowVerdict` remains `.rejected`). -/
def unaccessedRecoveryClaim : FlowClaim RNode RTag where
  statement := "Claiming unique recovery of signal with no declared SourceNode carrying signal."
  graph := ⟨[⟨.noise, .measured, []⟩], [⟨"readout", [.noise], .target, .transform []⟩]⟩
  kind := .uniqueRecovery .target .signal

/-- Unhedged emergence across `.forget .signal .notShown` -> `rejected` (Rule 2, Part B: Barontini F2);
    `uniqueRecovery` across `.forget .signal .notShown` remains `unestablished` (tested below). -/
theorem sole_path_notShown_emergence_rejected :
    flowVerdict solePathNotShownClaim = .rejected ∧
    epistemicVerdict solePathNotShownClaim = .rejected ∧
    auditFlow solePathNotShownClaim = [FlowFinding.failedForgetOnPath "unverified_forget" RTag.signal Invariance.notShown] := by
  decide

theorem notShown_with_confirmed_bypass_is_rejected :
    epistemicVerdict notShownWithBypassClaim = .rejected ∧
    FlowFinding.smuggledStructure RTag.signal RNode.bypassTag [.bypassTag, .target]
      ∈ auditFlow notShownWithBypassClaim := by
  decide

theorem lossless_signal_with_lossy_unrelated_noise_admissible :
    epistemicVerdict losslessSignalWithLossyNoiseClaim = .admissible := by
  decide

theorem unaccessed_recovery_is_unestablished_in_epistemic_verdict :
    flowVerdict unaccessedRecoveryClaim = .rejected ∧
    epistemicVerdict unaccessedRecoveryClaim = .unestablished := by
  decide

/-! #### Codex `#27370` Finding 2 Regression Tests: `(x, round(x))` and `uniqueRecovery` via `.notShown` -/

/-- Codex `#27370` 2a: output is pair `(x, round(x))` — direct lossless path from `x` exists,
    so `uniqueRecovery` on `x` is `admissible` even though a parallel branch rounds `x`. -/
def pairRawAndRoundedSignalClaim : FlowClaim RNode RTag where
  statement := "Recovering raw signal x from pair (x, round(x))."
  graph :=
    ⟨[⟨.srcTag, .measured, [.signal]⟩],
     [⟨"round_signal", [.srcTag], .roundedNoise, .lossy []⟩,
      ⟨"make_pair_raw_and_rounded", [.srcTag, .roundedNoise], .pairOut, .transform []⟩]⟩
  kind := .uniqueRecovery .pairOut .signal

/-- Codex `#27370` 2b: sole access path passes through `.forget .signal .notShown` ->
    `unestablished` (neither `admissible` nor `rejected`), with `failedForgetOnPath`. -/
def recoveryThroughNotShownForgetClaim : FlowClaim RNode RTag where
  statement := "Claiming unique recovery when the sole access path crosses an unverified forget."
  graph :=
    ⟨[⟨.srcTag, .measured, [.signal]⟩],
     [⟨"unverified_forget", [.srcTag], .forgotten, .forget .signal .notShown⟩,
      ⟨"readout", [.forgotten], .target, .transform []⟩]⟩
  kind := .uniqueRecovery .target .signal

theorem pair_raw_and_rounded_signal_admissible :
    epistemicVerdict pairRawAndRoundedSignalClaim = .admissible := by
  decide

theorem recovery_through_notShown_is_unestablished :
    flowVerdict recoveryThroughNotShownForgetClaim = .rejected ∧
    epistemicVerdict recoveryThroughNotShownForgetClaim = .unestablished ∧
    auditFlow recoveryThroughNotShownForgetClaim =
      [FlowFinding.failedForgetOnPath "unverified_forget" RTag.signal Invariance.notShown] := by
  decide

/-! #### Rule 3 (`theoremApplication`) Tests: JEPA & Mathematical Preconditions -/

inductive MathNode where
  | realWorld | theoremOut
  deriving DecidableEq, Repr

inductive MathTag where
  | injectiveRendering | populationMinimizers | grh | nonzeroDenominator
  deriving DecidableEq, Repr

def mathGraph : FlowGraph MathNode MathTag :=
  ⟨[⟨.realWorld, .measured, []⟩],
   [⟨"apply_theorem", [.realWorld], .theoremOut, .transform []⟩]⟩

/-- JEPA Theorem 1 applied to real lossy modalities: `injectiveRendering` is `.knownFalse` -> `rejected`. -/
def jepaKnownFalseHypClaim : FlowClaim MathNode MathTag where
  statement := "JEPA Theorem 1 holds on real lossy cameras."
  graph := mathGraph
  kind := .theoremApplication .theoremOut
    [⟨.injectiveRendering, .knownFalse⟩, ⟨.populationMinimizers, .bet⟩]
    [.injectiveRendering] -- even declaring a knownFalse hypothesis never excuses it!

/-- Math theorem assuming GRH with GRH openly declared -> `admissible`. -/
def mathDeclaredBetClaim : FlowClaim MathNode MathTag where
  statement := "Assuming GRH, theorem X holds for all n >= N0."
  graph := mathGraph
  kind := .theoremApplication .theoremOut
    [⟨.grh, .bet⟩, ⟨.nonzeroDenominator, .discharged⟩]
    [.grh]

/-- Math abstract dropping GRH (unchecked `.bet` omitted from `declaredBets`) -> `unestablished`. -/
def mathUndeclaredBetClaim : FlowClaim MathNode MathTag where
  statement := "Unconditionally, theorem X holds."
  graph := mathGraph
  kind := .theoremApplication .theoremOut
    [⟨.grh, .bet⟩, ⟨.nonzeroDenominator, .discharged⟩]
    []

theorem jepa_known_false_hypothesis_rejected :
    epistemicVerdict jepaKnownFalseHypClaim = .rejected ∧
    FlowFinding.hypothesisKnownFalse MathNode.theoremOut MathTag.injectiveRendering
      ∈ auditFlow jepaKnownFalseHypClaim := by
  decide

theorem math_declared_bet_admissible :
    epistemicVerdict mathDeclaredBetClaim = .admissible := by
  decide

theorem math_undeclared_bet_unestablished :
    flowVerdict mathUndeclaredBetClaim = .rejected ∧
    epistemicVerdict mathUndeclaredBetClaim = .unestablished ∧
    auditFlow mathUndeclaredBetClaim =
      [FlowFinding.undeclaredHypothesisBet MathNode.theoremOut MathTag.grh] := by
  decide

/-! #### Codex `#27373` Regression Tests: Parallel Lossy `(n div 2, n mod 2)` & Orphan `declaredBets` -/

inductive QRNode where
  | nVal | qDiv2 | rMod2 | qrPair
  deriving DecidableEq, Repr

inductive QRTag where
  | inputN
  deriving DecidableEq, Repr

/-- Codex `#27373`: `q = n div 2` and `r = n mod 2` are individually `.lossy`, yet `(q, r)` recovers `n = 2q + r`.
    With no single `.lossy` bottleneck, the graph alone cannot decide joint injectivity -> `unestablished`
    (`parallelLossyBranches`), NOT falsely `rejected`! -/
def parallelLossyQRPairClaim : FlowClaim QRNode QRTag where
  statement := "Recover n from pair (n div 2, n mod 2)."
  graph :=
    ⟨[⟨.nVal, .measured, [.inputN]⟩],
     [⟨"div2", [.nVal], .qDiv2, .lossyOn [.inputN] []⟩,
      ⟨"mod2", [.nVal], .rMod2, .lossyOn [.inputN] []⟩,
      ⟨"pair_qr", [.qDiv2, .rMod2], .qrPair, .transform []⟩]⟩
  kind := .uniqueRecovery .qrPair .inputN

/-- Codex `#27373`: keeping `grh` in `declaredBets` while omitting it from `hypotheses` -> `unestablished`
    (`orphanDeclaredBet`), never `admissible`! -/
def orphanDeclaredBetClaim : FlowClaim MathNode MathTag where
  statement := "Orphan declared bet with no matching hypothesis entry."
  graph := mathGraph
  kind := .theoremApplication .theoremOut
    [⟨.nonzeroDenominator, .discharged⟩]
    [.grh]

theorem parallel_lossy_qr_pair_is_unestablished_not_rejected :
    flowVerdict parallelLossyQRPairClaim = .rejected ∧
    epistemicVerdict parallelLossyQRPairClaim = .unestablished ∧
    auditFlow parallelLossyQRPairClaim =
      [FlowFinding.parallelLossyBranches QRNode.qrPair QRTag.inputN [QRNode.qDiv2, QRNode.rMod2]] := by
  decide

theorem orphan_declared_bet_caught_in_lean :
    flowVerdict orphanDeclaredBetClaim = .rejected ∧
    epistemicVerdict orphanDeclaredBetClaim = .unestablished ∧
    auditFlow orphanDeclaredBetClaim =
      [FlowFinding.orphanDeclaredBet MathNode.theoremOut MathTag.grh] := by
  decide

/-! #### Codex `#27376` Regression Tests: Projection `observed = signal` on `(signal, noise)` -/

inductive ProjNode where
  | jointState | observed
  deriving DecidableEq, Repr

inductive ProjTag where
  | signal | noise
  deriving DecidableEq, Repr

/-- Tag-specific projection `observed = signal` loses ONLY `.noise` (`.lossyOn [.noise] []`):
    - recovering `.signal` -> `admissible` (lossless on `.signal`),
    - recovering `.noise` -> `rejected` (`lossyChannelOnPath`). -/
def taggedProjectionGraph : FlowGraph ProjNode ProjTag :=
  ⟨[⟨.jointState, .measured, [.signal, .noise]⟩],
   [⟨"project_first", [.jointState], .observed, .lossyOn [.noise] []⟩]⟩

/-- Untagged projection (`.lossy []`, does not specify which tag collides):
    both `.signal` and `.noise` return `unestablished` (`untargetedLossyChannel`). -/
def untaggedProjectionGraph : FlowGraph ProjNode ProjTag :=
  ⟨[⟨.jointState, .measured, [.signal, .noise]⟩],
   [⟨"project_first", [.jointState], .observed, .lossy []⟩]⟩

theorem tagged_projection_preserves_signal_rejects_noise :
    epistemicVerdict ⟨"Recover signal", taggedProjectionGraph, .uniqueRecovery .observed .signal⟩ = .admissible ∧
    epistemicVerdict ⟨"Recover noise", taggedProjectionGraph, .uniqueRecovery .observed .noise⟩ = .rejected ∧
    auditFlow ⟨"Recover noise", taggedProjectionGraph, .uniqueRecovery .observed .noise⟩ =
      [FlowFinding.lossyChannelOnPath "project_first" ProjNode.observed] := by
  decide

theorem untagged_projection_is_unestablished_for_both_tags :
    epistemicVerdict ⟨"Recover signal", untaggedProjectionGraph, .uniqueRecovery .observed .signal⟩ = .unestablished ∧
    epistemicVerdict ⟨"Recover noise", untaggedProjectionGraph, .uniqueRecovery .observed .noise⟩ = .unestablished ∧
    auditFlow ⟨"Recover signal", untaggedProjectionGraph, .uniqueRecovery .observed .signal⟩ =
      [FlowFinding.untargetedLossyChannel "project_first" ProjNode.observed ProjTag.signal] := by
  decide

/-! #### Codex `#27379` Regression Tests: Side Information `p = s XOR r` vs `(p, r)` -/

inductive XorNode where
  | sBit | rBit | parityP | pairPR
  deriving DecidableEq, Repr

inductive XorTag where
  | signal | reference
  deriving DecidableEq, Repr

def xorSideInfoGraph : FlowGraph XorNode XorTag :=
  ⟨[⟨.sBit, .measured, [.signal]⟩,
    ⟨.rBit, .measured, [.reference]⟩],
   [⟨"measure_parity", [.sBit, .rBit], .parityP, .lossyOn [.signal, .reference] []⟩,
    ⟨"combine_with_reference", [.parityP, .rBit], .pairPR, .transform []⟩]⟩

/-- Observing `p = s XOR r` alone has no side-information bypass -> `rejected` (`lossyChannelOnPath`).
    Observing `(p, r)` has `r` bypassing `measure_parity` -> `unestablished` (`lossyWithSideInformation`). -/
theorem xor_parity_alone_rejected_and_pair_with_reference_unestablished :
    epistemicVerdict ⟨"Recover s from p alone", xorSideInfoGraph, .uniqueRecovery .parityP .signal⟩ = .rejected ∧
    auditFlow ⟨"Recover s from p alone", xorSideInfoGraph, .uniqueRecovery .parityP .signal⟩ =
      [FlowFinding.lossyChannelOnPath "measure_parity" XorNode.parityP] ∧
    epistemicVerdict ⟨"Recover s from (p, r)", xorSideInfoGraph, .uniqueRecovery .pairPR .signal⟩ = .unestablished ∧
    auditFlow ⟨"Recover s from (p, r)", xorSideInfoGraph, .uniqueRecovery .pairPR .signal⟩ =
      [FlowFinding.lossyWithSideInformation "measure_parity" XorNode.parityP [XorNode.rBit]] := by
  decide

end EpistemicVerdictTests

end EpistemicLedger.Cases.V2FlowBenchmarks
