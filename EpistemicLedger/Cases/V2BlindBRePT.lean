import EpistemicLedger.OperationFlow

/-
Blind flow record for "RePT: 3D Geometry Emerges from 2D Relational Pretraining"
(paper/paper.txt). One shared graph for both abstract claims: the default RePT
pipeline (depth-and-pose projection tracks, Sec. 4.1), trained on ARKitScenes
and evaluated on held-out ARKitScenes / ScanNet++ scenes.
-/
namespace EpistemicLedger.Cases.V2BlindB.RePT

open EpistemicLedger
open EpistemicLedger.OperationFlow

inductive Node where
  /-- Multi-view RGB frames of static indoor scenes used for training.
      Sec. 4.1: "We train and evaluate RePT on ARKitScenes [1], using 4492 sequences for training". -/
  | arkitTrainFrames
  /-- Sensor depth maps and camera poses of the training sequences.
      Sec. 4.1: "We construct sparse multi-view landmark tracks using the provided depth maps and camera poses". -/
  | arkitDepthAndPoses
  /-- Node after the RGB-only swap test of depth/pose (App. A.2, Table 2, Table 4). -/
  | depthPoseAfterRgbOnlySwap
  /-- Pretrained frozen image backbone. Sec. 3.2: "we use DINOv2 [16] to map each scene image to patch
      features"; Table 9: "DINOv2 ViT-S/14, frozen". -/
  | dinov2Backbone
  /-- Frozen DINOv2 patch features Z1..ZM of the context images (Eq. 2 input). -/
  | dinoPatchFeatures
  /-- Persistent 2D landmark tracks. App. A.1 "Track formation": "a set of landmarks with persistent
      identifiers, per-frame visibility, and 2D image coordinates". -/
  | landmarkTracks2D
  /-- Episode recipe chosen by the authors. Sec. 4.1: "12 context images ... two distinct landmarks A and B
      ... four cross-view observation pairs ... up to eight additional observation pairs". -/
  | episodeSamplingConfig
  /-- Sampled training episodes (App. A.3). -/
  | trainingEpisodes
  /-- Primary loss. Sec. 3.3 Eq. 6 "Lrel = SmoothL1(p̂B_t, pB_t)"; Sec. 1: "The relational objective
      predicts only 2D coordinates, without depth, camera-pose, or 3D-coordinate targets." -/
  | relationalObjective2D
  /-- Auxiliary CroCo-style cross-view feature reconstruction, also used for 5 epochs of context-encoder
      pretraining. Sec. 3.3 Eq. 7-8; Sec. 4.1 "we initialize the Context Encoder with 5 epochs of
      cross-view reconstruction pretraining". -/
  | reconstructionObjective
  /-- Node after the from-scratch relation-only test of reconstruction (Table 3). -/
  | reconstructionAfterAblation
  /-- Architecture chosen by the authors: context encoder, relational encoder/decoder, 16-D token,
      additive relation q = h(B) - h(A). Sec. 3.2 Eq. 4; Table 9. -/
  | architectureConfig
  /-- Node after the MLP-relation swap test of the additive parameterization (Table 3). -/
  | architectureAfterMlpSwap
  /-- Trained RePT model (context encoder adapted jointly, Sec. 4.4 "Context adaptation"). -/
  | trainedRePT
  /-- Held-out evaluation scenes with RGB, depth and pose: 55 ARKitScenes validation scenes and ScanNet++
      subsets. Sec. 4.3; App. B.1 "sample 1,500 valid cross-view relation pairs ... from arbitrary
      valid-depth image locations". -/
  | evalScenes
  /-- The learned 16-D relation space q_{A->B} on evaluation pairs (the claims' target). Sec. 4.2. -/
  | relationTokensQ
  /-- Ground-truth 3D displacements Δx = xB - xA. Sec. 4.2; App. B.1 "di = xBi - xAi". -/
  | gtDisplacements3D
  /-- Raw-q length/angle/NN-overlap metrics vs. ground truth. Table 1 row "Raw q". -/
  | rawGeometryMetrics
  /-- Linear readouts (scene-specific Ws, shared W, held-out transfer). Table 1; Sec. 5 Limitations:
      "Readouts are fitted using ground-truth 3D displacements". -/
  | linearReadoutGeometry
  deriving DecidableEq, Repr

inductive Tag where
  /-- Metric 3D geometry of the scene (depth, pose, 3D positions/displacements). Abstract: "magnitudes,
      angles, and neighborhoods reflect physical 3D displacement". -/
  | geometry3D
  /-- Additive, displacement-like composition of relations. Sec. 4.4: "The additive difference structure
      therefore acts as an inductive bias that favors a more displacement-like organization". -/
  | additiveComposition
  deriving DecidableEq, Repr

def graph : FlowGraph Node Tag where
  sources :=
    [ -- carries geometry3D: frames are multi-view images of static 3D scenes; Sec. 5: "In a static scene,
      -- the displacement between two points is invariant across viewpoints ... a relation that must
      -- transfer across views is pushed toward encoding this invariant"; Sec. 2.2: FlowMap "recovers depth
      -- and camera parameters through optimization against 2D correspondences".
      ⟨.arkitTrainFrames, .measured, [.geometry3D]⟩,
      -- carries geometry3D: App. A.1 Eq. 9 back-projects each pixel "into world coordinates using its
      -- depth dt(u), the camera intrinsics Kt, and the camera-to-world pose".
      ⟨.arkitDepthAndPoses, .measured, [.geometry3D]⟩,
      -- carries geometry3D: App. C Table 7, frozen DINOv2 features vs constant probe: depth RMSE 0.4448
      -- vs 0.8509, rotation error 45.64 vs 51.12 deg, ego/allo spatial acc 0.7902/0.5320 (chance 25%);
      -- Table 3 "DINOv2 as C" scene-specific Len/Ang 0.6516/0.6616.
      ⟨.dinov2Backbone, .setByExperimenter, [.geometry3D]⟩,
      ⟨.episodeSamplingConfig, .setByExperimenter, []⟩,
      ⟨.relationalObjective2D, .setByExperimenter, []⟩,
      -- carries geometry3D: Sec. 2.2: CroCo-style objectives "reconstruct missing image content with
      -- information from another view, encouraging representations to capture geometric dependencies
      -- across viewpoints".
      ⟨.reconstructionObjective, .setByExperimenter, [.geometry3D]⟩,
      -- carries additiveComposition: Sec. 3.2 Eq. 4 "qA→B = h(j, pB_j; C) − h(i, pA_i; C)".
      ⟨.architectureConfig, .setByExperimenter, [.additiveComposition]⟩,
      -- carries geometry3D: evaluation scenes come with depth and pose; App. B.1 pairs sampled from
      -- "valid-depth image locations", displacements "di = xBi − xAi".
      ⟨.evalScenes, .measured, [.geometry3D]⟩ ]
  ops :=
    [ -- forget geometry3D, evidence shown: App. A.2 / Table 2 / Table 4, RePT trained on RGB-only
      -- CoTracker3 tracks "without using depth" gives comparable geometry (held-out transfer differences
      -- −0.0075 length, −0.0161 angle, +0.0168 m); "the geometric organization also emerges when training
      -- correspondences are obtained by RGB-only tracking". Applied to depth/pose only, not to the frames.
      ⟨"depth_pose_swapped_for_rgb_only_cotracker3_tracks", [.arkitDepthAndPoses],
        .depthPoseAfterRgbOnlySwap, .forget .geometry3D .shown⟩,
      ⟨"construct_landmark_tracks_by_projection", [.arkitTrainFrames, .depthPoseAfterRgbOnlySwap],
        .landmarkTracks2D, .transform []⟩,
      ⟨"extract_frozen_dinov2_features", [.arkitTrainFrames, .dinov2Backbone],
        .dinoPatchFeatures, .transform []⟩,
      ⟨"sample_training_episodes", [.landmarkTracks2D, .episodeSamplingConfig],
        .trainingEpisodes, .transform []⟩,
      -- forget geometry3D, evidence shown: Table 3 "Training from scratch / Relation only" scene-specific
      -- Len/Ang 0.8673/0.8808 vs Full RePT 0.8639/0.8804; Sec. 4.4: "Reconstruction aids optimization but
      -- is not needed for geometric emergence."
      ⟨"reconstruction_removed_from_scratch_relation_only", [.reconstructionObjective],
        .reconstructionAfterAblation, .forget .geometry3D .shown⟩,
      -- forget additiveComposition, evidence contradicted: Table 3 "MLP relation" scene-specific Len/Ang
      -- 0.3335/0.4051 vs 0.8639/0.8804; "Replacing qA→B = h(B; C) − h(A; C) with a learned MLP relation
      -- encoder causes a large reduction in geometric organization."
      ⟨"additive_relation_swapped_for_mlp", [.architectureConfig],
        .architectureAfterMlpSwap, .forget .additiveComposition .contradicted⟩,
      ⟨"train_rept_relational_point_transfer",
        [.dinoPatchFeatures, .trainingEpisodes, .relationalObjective2D,
         .reconstructionAfterAblation, .architectureAfterMlpSwap],
        .trainedRePT, .transform []⟩,
      ⟨"encode_eval_relation_tokens", [.trainedRePT, .evalScenes],
        .relationTokensQ, .transform []⟩,
      ⟨"compute_gt_displacements", [.evalScenes], .gtDisplacements3D, .transform []⟩,
      ⟨"correlate_raw_q_with_gt", [.relationTokensQ, .gtDisplacements3D],
        .rawGeometryMetrics, .transform []⟩,
      ⟨"fit_linear_readouts_on_gt", [.relationTokensQ, .gtDisplacements3D],
        .linearReadoutGeometry, .transform []⟩ ]

def claim1 : FlowClaim Node Tag where
  statement := "We ask whether 3D structure can emerge from learning relations across 2D observations, without 3D prediction targets."
  graph := graph
  kind := .emergesWithout .relationTokensQ .geometry3D

def claim2 : FlowClaim Node Tag where
  statement := "More broadly, our results suggest that 3D geometry need not be an explicit prediction target and can instead emerge as a structural property of representations trained to relate 2D observations, pointing to relational prediction as a complementary route to learning the representations that spatial intelligence builds on."
  graph := graph
  kind := .emergesWithout .relationTokensQ .geometry3D

#eval auditFlow claim1
#eval flowVerdict claim1
#eval auditFlow claim2
#eval flowVerdict claim2

theorem claim1_verdict : flowVerdict claim1 = .rejected := by decide
theorem claim2_verdict : flowVerdict claim2 = .rejected := by decide

end EpistemicLedger.Cases.V2BlindB.RePT
