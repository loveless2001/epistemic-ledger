import EpistemicLedger.OperationFlow

/-
Blind flow record for paper/paper.txt:
"RePT: 3D Geometry Emerges from 2D Relational Pretraining".

The study, as read from the paper:
  training   : frozen DINOv2 patch features -> trainable Context Encoder (scene context C)
               -> relation token q = h(B) - h(A) -> decoder predicts a 2D point; Smooth L1 loss
               on 2D coordinates, plus an auxiliary cross-view reconstruction branch.
               2D point tracks come from depth-and-pose projection (default) or from
               RGB-only CoTracker3 tracking (separate fully trained model).
  evaluation : relation tokens of held-out scenes are compared with ground-truth 3D
               displacements, raw and through a linear readout fitted on those displacements.

Other evidence in the paper that is NOT drawn as a forget step, because no structure tag
flows through it: the same-point "Correspondence" baseline (Table 3), relation dimension
3/4/8/16/32 (Table 8, Appendix D), the ScanNet++ evaluation (Table 2), and the PCK@4
comparison (Table 3, Table 6).

This file records what the paper states. It does not judge whether the claims are true.
-/
namespace EpistemicLedger.Cases.V2BlindA.RePT

open EpistemicLedger
open EpistemicLedger.OperationFlow

inductive Node where
  /-- Sec. 4.1: "We train and evaluate RePT on ARKitScenes [1], using 4492 sequences for
  training and 55 for validation." App. A.1: "RePT is trained using images and the resulting
  2D point observations." -/
  | trainRgbFrames
  /-- Sec. 4.1: "We construct sparse multi-view landmark tracks using the provided depth maps
  and camera poses". -/
  | trainDepthAndPose
  /-- App. A.2: "we process ARKitScenes with CoTracker3 [11], an RGB-only point tracker";
  "Only RGB frames are read." -/
  | coTracker3
  /-- Sec. 3.2: "we use DINOv2 [16] to map each scene image to patch features".
  Table 9: "DINOv2 ViT-S/14, frozen". -/
  | dinov2Backbone
  /-- Sec. 1: "The relational objective predicts only 2D coordinates, without depth,
  camera-pose, or 3D-coordinate targets." Eq. 6 (Smooth L1 on the predicted 2D point). -/
  | pointTransferLoss2D
  /-- Sec. 3.3: "we optionally regularize C with a CroCo-style [28] cross-view feature
  reconstruction objective". Sec. 4.1: "we initialize the Context Encoder with 5 epochs of
  cross-view reconstruction pretraining before relational training". -/
  | reconstructionObjective
  /-- Sec. 3.2, Eq. 4: "their directed relation is represented by the difference between the
  two endpoint embeddings". -/
  | additiveRelationParam
  /-- Sec. 3.2: "The Context Encoder constructs a shared multi-view scene representation C".
  Table 9: learning rate "5 × 10−5 for Ectx" (it is trained during relational training). -/
  | contextEncoder
  /-- Sec. 4.3: "We test whether a single linear map recovers geometry across multiple scenes,
  all excluded from RePT training." (55 ARKitScenes validation scenes; ScanNet++ subsets,
  Table 2.) -/
  | evalRgbFrames
  /-- App. B.1: "we sample 1,500 valid cross-view relation pairs independently from arbitrary
  valid-depth image locations". -/
  | evalDepthAndPose
  /-- App. A.1, Eq. 10: "the accumulated landmarks are transformed into the current camera
  coordinates and reprojected onto the image". -/
  | projectionTracks2D
  /-- App. A.1: "Repeating this process yields a set of landmarks with persistent identifiers,
  per-frame visibility, and 2D image coordinates." App. A.2: "The resulting 2D trajectories
  are used with the same temporal sampling, episode construction, and RePT training
  procedure." -/
  | trainingTracks2D
  /-- Sec. 3.2: "An auxiliary feature reconstruction branch is used only during training".
  Sec. 4.1 (reconstruction-pretrained Context Encoder as "a shared starting point"). -/
  | reconstructionBranch
  /-- Eq. 8: "L = Lrel + λrec Lrec". Table 9: "10 epochs, 55,630 updates". -/
  | trainedRePT
  /-- Sec. 3.2: "We use a 16-dimensional relation token qA→B." App. B.1: "Each relation token
  is encoded from a single observation pair". -/
  | relationTokens
  /-- Sec. 4.2: "∆xA→B = xB − xA denote the corresponding physical 3D displacement".
  App. B.1: "its 3D displacement by di = xBi − xAi". -/
  | gtDisplacements
  /-- Sec. 4.2: "we fit a linear map Ws : R16 → R3 directly from relation tokens to their
  corresponding physical 3D displacement vectors". Sec. 4.3 and App. B.2 (shared W with a
  per-scene rotation Rs). -/
  | fittedReadout
  /-- Fig. 1: "A linear readout fitted after training maps the 16-D relations to 3D
  displacements." App. B.2, Eq. 16: "The final prediction is d̂A→B = qA→B W Rs⊤". -/
  | decodedDisplacements
  /-- Table 1 (length and angle correlation, NN-Overlap@10, 3D error); App. B.3. -/
  | geometryMetrics
  deriving DecidableEq, Repr

inductive Tag where
  /-- The "3D structure" / "3D geometry" of the two claims. Abstract: "magnitudes, angles, and
  neighborhoods reflect physical 3D displacement". Sec. 1 lists the explicit forms: "depth,
  camera-pose, or 3D-coordinate targets". -/
  | geometry3D
  /-- Abstract: "This organization depends on additive relations and adaptive scene context".
  Sec. 4.4: "The additive difference structure therefore acts as an inductive bias". -/
  | additiveRelation
  /-- Abstract: "adaptive scene context". Sec. 4.4: "highlighting the importance of jointly
  adapting C to the relational objective". -/
  | adaptiveSceneContext
  deriving DecidableEq, Repr

def graph : FlowGraph Node Tag where
  sources :=
    [ ⟨.trainRgbFrames, .measured, []⟩,
      -- carries geometry3D: App. A.1, Eq. 9: "Each sampled pixel u = (u, v) is back-projected
      -- into world coordinates using its depth dt(u), the camera intrinsics Kt, and the
      -- camera-to-world pose (Rt, tt)".
      ⟨.trainDepthAndPose, .measured, [.geometry3D]⟩,
      ⟨.coTracker3, .setByExperimenter, []⟩,
      -- carries geometry3D: Table 7, "Geometric information in frozen features on
      -- ARKitScenes": DINOv2 depth RMSE 0.4448 against 0.8509 for the constant probe,
      -- spatial accuracy 0.7902 (ego). Sec. 2.3: "pretrained image and video features expose
      -- information about 3D viewpoint, depth, surface geometry".
      ⟨.dinov2Backbone, .setByExperimenter, [.geometry3D]⟩,
      ⟨.pointTransferLoss2D, .setByExperimenter, []⟩,
      ⟨.reconstructionObjective, .setByExperimenter, []⟩,
      -- carries additiveRelation: Sec. 4.4: "The additive difference structure therefore acts
      -- as an inductive bias that favors a more displacement-like organization of the
      -- relation space."
      ⟨.additiveRelationParam, .setByExperimenter, [.additiveRelation]⟩,
      -- carries adaptiveSceneContext: Sec. 4.4: "highlighting the importance of jointly
      -- adapting C to the relational objective".
      ⟨.contextEncoder, .setByExperimenter, [.adaptiveSceneContext]⟩,
      ⟨.evalRgbFrames, .measured, []⟩,
      -- carries geometry3D: Sec. 5: "Readouts are fitted using ground-truth 3D
      -- displacements"; App. B.1 (pairs sampled at valid-depth locations, di = xBi − xAi).
      ⟨.evalDepthAndPose, .measured, [.geometry3D]⟩ ]
  ops :=
    [ -- App. A.1, Eq. 10: "π([a, b, c]⊤) = (a/c, b/c)⊤ denotes perspective division"
      -- (3D landmark to 2D image point, many-to-one).
      ⟨"project_landmarks_with_depth_and_pose", [.trainRgbFrames, .trainDepthAndPose],
        .projectionTracks2D, .lossy []⟩,
      -- forget geometry3D, shown: Sec. 4.4: "We fully train RePT using CoTracker3
      -- correspondences on randomly sampled RGB pixels, keeping the remaining pipeline
      -- unchanged. Table 2 shows comparable geometry across readout settings". App. A.2 and
      -- Table 4: held-out transfer differences "−0.0075 ± 0.0044 in length correlation,
      -- −0.0161 ± 0.0047 in angle correlation".
      ⟨"supply_2d_tracks_projection_or_rgb_only_cotracker3",
        [.projectionTracks2D, .trainRgbFrames, .coTracker3], .trainingTracks2D,
        .forget .geometry3D .shown⟩,
      -- forget geometry3D, shown: Sec. 4.4: "we train matched models from scratch with and
      -- without reconstruction, and both develop comparable scene-specific and shared
      -- geometry" (Table 3, "Relation only": 0.8673 / 0.8808).
      ⟨"cross_view_reconstruction_pretraining_and_auxiliary_branch",
        [.trainRgbFrames, .dinov2Backbone, .contextEncoder, .reconstructionObjective],
        .reconstructionBranch, .forget .geometry3D .shown⟩,
      -- forget adaptiveSceneContext, contradicted: Sec. 4.4, "Frozen context" variant: "its
      -- scene-specific correlations fall to 0.2523 and 0.3175" (Table 3).
      ⟨"relational_point_transfer_training_with_jointly_adapted_context",
        [.trainRgbFrames, .trainingTracks2D, .dinov2Backbone, .reconstructionBranch,
          .contextEncoder, .additiveRelationParam, .pointTransferLoss2D],
        .trainedRePT, .forget .adaptiveSceneContext .contradicted⟩,
      -- forget additiveRelation, contradicted: Sec. 4.4: "Replacing qA→B = h(B; C) − h(A; C)
      -- with a learned MLP relation encoder causes a large reduction in geometric
      -- organization." (Table 3, "MLP relation": 0.3335 / 0.4051.)
      ⟨"encode_relation_tokens_as_endpoint_differences", [.trainedRePT, .evalRgbFrames],
        .relationTokens, .forget .additiveRelation .contradicted⟩,
      -- Sec. 4.2 and App. B.1: ground-truth displacement of each sampled pair.
      ⟨"backproject_eval_points_to_gt_displacements", [.evalDepthAndPose],
        .gtDisplacements, .transform []⟩,
      -- forget geometry3D, shown: Sec. 5: "This organization is not an artifact of the
      -- readout. Under the same scene-specific protocol, frozen-context and MLP-relation
      -- variants reach length and angle correlations of only 0.25 and 0.32, and 0.33 and
      -- 0.41, compared with 0.86 and 0.88 for RePT." Sec. 4.2: "Raw q achieves a length
      -- Pearson correlation of 0.5921 and an angle Pearson correlation of 0.6789."
      -- App. B.1: "Raw-token metrics use the unprojected relation representation and require
      -- no fitted readout." Sec. 4.3: W frozen and applied to 39 held-out scenes.
      ⟨"fit_linear_readout_on_gt_displacements", [.relationTokens, .gtDisplacements],
        .fittedReadout, .forget .geometry3D .shown⟩,
      -- Fig. 1 and App. B.2, Eq. 16: d̂ = q W Rs⊤.
      ⟨"apply_linear_readout", [.relationTokens, .fittedReadout],
        .decodedDisplacements, .transform []⟩,
      -- Table 1 and App. B.3: decoded or raw tokens compared with the ground truth.
      ⟨"compare_with_gt_length_angle_neighbourhood",
        [.relationTokens, .decodedDisplacements, .gtDisplacements],
        .geometryMetrics, .transform []⟩ ]

/-- Target: the 3D read off the relation space. Sec. 1 restates the question as "whether
metric 3D relations can emerge in a geometrically organized latent space and admit a linear
readout without explicit 3D prediction targets"; Fig. 1: "After training: 3D from a linear
map of q". -/
def claim1 : FlowClaim Node Tag where
  statement := "We ask whether 3D structure can emerge from learning relations across 2D observations, without 3D prediction targets."
  graph := graph
  kind := .emergesWithout .decodedDisplacements .geometry3D

/-- Target: the representation itself ("a structural property of representations"), that is
the relation tokens. Sec. 5: "Our claims concern representation structure rather than
reconstruction." -/
def claim2 : FlowClaim Node Tag where
  statement := "More broadly, our results suggest that 3D geometry need not be an explicit prediction target and can instead emerge as a structural property of representations trained to relate 2D observations, pointing to relational prediction as a complementary route to learning the representations that spatial intelligence builds on."
  graph := graph
  kind := .emergesWithout .relationTokens .geometry3D

#eval auditFlow claim1
#eval flowVerdict claim1
#eval auditFlow claim2
#eval flowVerdict claim2

theorem claim1_verdict : flowVerdict claim1 = .rejected := by decide
theorem claim2_verdict : flowVerdict claim2 = .rejected := by decide

end EpistemicLedger.Cases.V2BlindA.RePT
