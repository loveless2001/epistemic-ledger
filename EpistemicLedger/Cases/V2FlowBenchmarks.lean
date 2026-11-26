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
        .lossy []⟩
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

/-- Case 1 (Codex P1-1): Same GPU cluster node ID, but 100 GPU-hrs vs 1 GPU-hr -> REJECTED! -/
def unevenQuantitiesSameCluster : FlowClaim Node Tag where
  statement := "Same cluster ID, but method spent 100 GPU-hrs while control spent 1 GPU-hr."
  graph :=
    ⟨[⟨.sharedGpuCluster, .setByExperimenter, [.resourceCost]⟩],
     [⟨"run_method", [.sharedGpuCluster], .autonomousSocietyRun, .transform []⟩,
      ⟨"run_control", [.sharedGpuCluster], .humanPlusAiControlRun, .transform []⟩,
      ⟨"bill", [.sharedGpuCluster], .postHocBillingMeter, .transform []⟩,
      ⟨"eval", [.autonomousSocietyRun, .humanPlusAiControlRun, .postHocBillingMeter],
        .costNormalizedComparison, .transform []⟩]⟩
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .humanPlusAiControlRun) (some .postHocBillingMeter) .resourceCost
    [⟨.autonomousSocietyRun, .sharedGpuCluster, "r_m1", .resourceCost, "gpu_hours", 100, .verified⟩]
    [⟨.humanPlusAiControlRun, .sharedGpuCluster, "r_c1", .resourceCost, "gpu_hours", 1, .verified⟩]

/-- Case 2 (Codex P1-1 converse + post-hoc meter): Two separate accounts both spending 500 USD -> ADMISSIBLE! -/
def separateAccountsEqualDollars : FlowClaim Node Tag where
  statement := "Two separate accounts both spending 500 USD, metered post-hoc directly from both accounts."
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
    [⟨.autonomousSocietyRun, .accountA, "r_a1", .resourceCost, "USD", 500, .verified⟩]
    [⟨.humanPlusAiControlRun, .accountB, "r_b1", .resourceCost, "USD", 500, .verified⟩]

/-- Case 3 (Codex P1-2): `forget .resourceCost .shown` CANNOT erase physically spent human hours! -/
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
    [⟨.autonomousSocietyRun, .sharedGpuCluster, "r_m2", .resourceCost, "gpu_hours", 10, .verified⟩]
    [⟨.humanPlusAiControlRun, .sharedGpuCluster, "r_c2", .resourceCost, "gpu_hours", 10, .verified⟩]

/-- Case 4 (Codex P1-3): Control arm derived from method output -> REJECTED (`dependentControlArm`)! -/
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
    [⟨.autonomousSocietyRun, .sharedGpuCluster, "r_m3", .resourceCost, "gpu_hours", 10, .verified⟩]
    [⟨.clonedControlArm, .sharedGpuCluster, "r_c3", .resourceCost, "gpu_hours", 10, .verified⟩]

/-- Case 5 (Codex R2 P1-2): Ledger cloned solely from control output (no direct metering path) -> REJECTED! -/
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
    [⟨.autonomousSocietyRun, .sharedGpuCluster, "r_m4", .resourceCost, "gpu_hours", 10, .verified⟩]
    [⟨.humanPlusAiControlRun, .sharedGpuCluster, "r_c4", .resourceCost, "gpu_hours", 10, .verified⟩]

/-- Case 6 (Society of AI Scientists macro): no control, no ledger, unquantified budget -> REJECTED! -/
def societyNoControlNoCost : FlowClaim Node Tag where
  statement := "936 autonomous agents across 35 labs without control or cost ledger."
  graph :=
    ⟨[⟨.sharedGpuCluster, .setByExperimenter, [.resourceCost]⟩,
      ⟨.humanOperatorHours, .setByExperimenter, [.resourceCost]⟩],
     [⟨"run_936_agents", [.sharedGpuCluster, .humanOperatorHours], .autonomousSocietyRun, .transform []⟩,
      ⟨"count_papers", [.autonomousSocietyRun], .rawStudyCountReport, .transform []⟩]⟩
  kind := .effectivenessClaim .autonomousSocietyRun .rawStudyCountReport none none .resourceCost [] []

/-- Case 7 (Codex #27315 Bug 3): Triple-counting the same control receipt (500 x 3 = 1500) -> REJECTED! -/
def tripleCountedControlReceipt : FlowClaim Node Tag where
  statement := "Control repeats the exact same 500 GPU-hour receipt three times to match 1,500."
  graph := separateAccountsEqualDollars.graph
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .humanPlusAiControlRun) (some .postHocBillingMeter) .resourceCost
    [⟨.autonomousSocietyRun, .accountA, "r_m1500", .resourceCost, "GPU-hours", 1500, .verified⟩]
    [⟨.humanPlusAiControlRun, .accountB, "r_c500", .resourceCost, "GPU-hours", 500, .verified⟩,
     ⟨.humanPlusAiControlRun, .accountB, "r_c500", .resourceCost, "GPU-hours", 500, .verified⟩,
     ⟨.humanPlusAiControlRun, .accountB, "r_c500", .resourceCost, "GPU-hours", 500, .verified⟩]

/-- Case 8 (Codex #27315 Bug 2): Unverified/contradicted arm attribution CANNOT certify matched budget! -/
def unverifiedAttributionClaim : FlowClaim Node Tag where
  statement := "Free-text quote does not establish which arm incurred the 500 GPU-hours."
  graph := separateAccountsEqualDollars.graph
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .humanPlusAiControlRun) (some .postHocBillingMeter) .resourceCost
    [⟨.autonomousSocietyRun, .accountA, "r_a_unv", .resourceCost, "GPU-hours", 500, .unverified⟩]
    [⟨.humanPlusAiControlRun, .accountB, "r_b_ver", .resourceCost, "GPU-hours", 500, .verified⟩]

/-- Case 9 (Honest multi-item sum): Two distinct verified receipts (500 + 1000) match control 1500 -> ADMISSIBLE! -/
def distinctReceiptsMultiItemSum : FlowClaim Node Tag where
  statement := "Two distinct verified method receipts (500 + 1000) match verified control 1500."
  graph := separateAccountsEqualDollars.graph
  kind := .effectivenessClaim .autonomousSocietyRun .costNormalizedComparison
    (some .humanPlusAiControlRun) (some .postHocBillingMeter) .resourceCost
    [⟨.autonomousSocietyRun, .accountA, "r_m_stage1", .resourceCost, "GPU-hours", 500, .verified⟩,
     ⟨.autonomousSocietyRun, .accountA, "r_m_stage2", .resourceCost, "GPU-hours", 1000, .verified⟩]
    [⟨.humanPlusAiControlRun, .accountB, "r_c_total", .resourceCost, "GPU-hours", 1500, .verified⟩]

theorem uneven_quantities_rejected :
    flowVerdict unevenQuantitiesSameCluster = .rejected ∧
    FlowFinding.unmatchedControlBudget Node.autonomousSocietyRun Node.humanPlusAiControlRun Tag.resourceCost
      ∈ auditFlow unevenQuantitiesSameCluster := by
  decide

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

theorem triple_counted_control_receipt_rejected :
    flowVerdict tripleCountedControlReceipt = .rejected ∧
    FlowFinding.duplicateUsageReceipt Node.humanPlusAiControlRun "r_c500" Tag.resourceCost
      ∈ auditFlow tripleCountedControlReceipt := by
  decide

theorem unverified_attribution_rejected :
    flowVerdict unverifiedAttributionClaim = .rejected ∧
    FlowFinding.unverifiedUsageAttribution Node.autonomousSocietyRun Node.accountA "r_a_unv"
      Tag.resourceCost UsageAttribution.unverified ∈ auditFlow unverifiedAttributionClaim := by
  decide

theorem distinct_receipts_multi_item_sum_admissible :
    flowVerdict distinctReceiptsMultiItemSum = .admissible := by
  decide

end EffectivenessTests

end EpistemicLedger.Cases.V2FlowBenchmarks
