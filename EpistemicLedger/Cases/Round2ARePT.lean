import EpistemicLedger.AuditRules

/-
Blind record for the paper in `paper/paper.txt`
("RePT: 3D Geometry Emerges from 2D Relational Pretraining").

Two claims, both verbatim sentences of the abstract. The record says what the
paper's own derivation leaned on; it does not say whether the claims are true.
Every `Dep` / `Hyp` constructor carries a quote or a section/table reference.
-/
namespace EpistemicLedger.Cases.Round2A.RePT

inductive Dep where
  /-- The training signal: cross-view 2D point transfer between two DISTINCT
  points. Sec. 3: "a model learns to transfer relations between distinct scene
  points through cross-view 2D point prediction." The matched same-point
  baseline is weaker (Table 3, row "Correspondence": 0.7979 / 0.8259 against
  0.8639 / 0.8804; transfer 0.6038 / 0.6809 against 0.7168 / 0.7844). -/
  | distinctPointRelationalObjective
  /-- Default training tracks are built from sensor depth and camera pose.
  Sec. 4.1: "Depth and pose are used only for offline track construction and
  are never provided to the model or used as prediction targets."
  Varied in Sec. 4.4 / Table 2 / Table 4 (CoTracker3 RGB-only tracks):
  "geometric organization also emerges with RGB-only tracking
  correspondences." -/
  | trainingTracksFromDepthAndPose
  /-- The relation token is defined as a difference of endpoint embeddings
  (Eq. 4). Sec. 4.4: "Replacing qA→B = h(B; C) − h(A; C) with a learned MLP
  relation encoder causes a large reduction in geometric organization" and
  "The additive difference structure therefore acts as an inductive bias that
  favors a more displacement-like organization of the relation space."
  Table 3, row "MLP relation": 0.3335 / 0.4051. -/
  | additiveRelationParameterization
  /-- The Context Encoder is trained jointly with the relational objective.
  Sec. 4.4: "a fixed reconstruction-pretrained scene representation is
  insufficient to produce the geometric organization observed in full RePT,
  highlighting the importance of jointly adapting C to the relational
  objective." Table 3, row "Frozen context": 0.2523 / 0.3175. -/
  | jointlyAdaptedSceneContext
  /-- Images enter through a pretrained, frozen backbone. Sec. 3.2: "we use
  DINOv2 [16] to map each scene image to patch features"; Table 9: "DINOv2
  ViT-S/14, frozen". The backbone itself is never varied. -/
  | frozenDinoV2Backbone
  /-- 3D is read out through linear maps fitted to ground truth. Sec. 5:
  "Readouts are fitted using ground-truth 3D displacements". Removed in
  Sec. 4.2 / Table 1 row "Raw q" (no fitted readout): "Raw relation tokens
  already reflect physical 3D displacement." -/
  | linearReadoutFittedOnGroundTruth3D
  /-- Reconstruction pretraining and auxiliary loss. Sec. 4.1: "we initialize
  the Context Encoder with 5 epochs of cross-view reconstruction pretraining".
  Removed in Table 3 row "Relation only" (0.8673 / 0.8808); Sec. 4.4:
  "Reconstruction aids optimization but is not needed for geometric
  emergence." -/
  | auxiliaryReconstruction
  /-- Sec. 3.2: "We use a 16-dimensional relation token". Varied in Sec. 4.4 /
  Table 8: "Across relation dimensions of 3, 4, 8, 16, and 32, RePT
  consistently develops geometric structure." -/
  | relationTokenDimension
  /-- The data cut. Sec. 5: "Evaluation is limited to static indoor scenes."
  (ARKitScenes for training and evaluation, ScanNet++ for evaluation.) Same
  section: "The hypothesis predicts that the organization should weaken in
  non-rigid scenes". -/
  | staticIndoorSceneData
  /-- The reference every metric is computed against. Sec. 4.2: "let
  ∆xA→B = xB − xA denote the corresponding physical 3D displacement." -/
  | groundTruth3DDisplacements
  /-- The measured agreement between relation tokens and 3D displacement.
  Table 1; Sec. 4.2: "Raw q achieves a length Pearson correlation of 0.5921
  and an angle Pearson correlation of 0.6789." -/
  | relationSpaceGeometryMetrics
  /-- The measured comparison of variants. Table 3, "Controlled comparison of
  design factors", and Table 6 (point-transfer metrics). -/
  | controlledVariantMetrics
  deriving DecidableEq, Repr

inductive Hyp where
  /-- The premise "without 3D prediction targets". Sec. 1: "The relational
  objective predicts only 2D coordinates, without depth, camera-pose, or
  3D-coordinate targets." Fixed by the loss itself (Eq. 6 and Eq. 8). -/
  | trainingUsesNo3DPredictionTargets
  /-- The step from "a fitted readout agrees with 3D" to "the representation
  is organised by 3D". Sec. 5: "This organization is not an artifact of the
  readout. Under the same scene-specific protocol, frozen-context and
  MLP-relation variants reach length and angle correlations of only 0.25 and
  0.32, and 0.33 and 0.41, compared with 0.86 and 0.88 for RePT." -/
  | structureIsNotAnArtifactOfTheReadout
  /-- Needed for "the representations that spatial intelligence builds on".
  Not tested. Sec. 5: "Whether such relational representations can support
  reasoning, planning, or control, and whether RePT extends to dynamic
  environments, are the natural next questions." -/
  | relationalRepresentationsSupportSpatialIntelligence
  deriving DecidableEq, Repr

/-- Everything the paper states (v1: anywhere in the paper). All entries of
`Dep` are stated in the main text or the appendix. -/
def statedInPaper : List Dep :=
  [ .distinctPointRelationalObjective,
    .trainingTracksFromDepthAndPose,
    .additiveRelationParameterization,
    .jointlyAdaptedSceneContext,
    .frozenDinoV2Backbone,
    .linearReadoutFittedOnGroundTruth3D,
    .auxiliaryReconstruction,
    .relationTokenDimension,
    .staticIndoorSceneData,
    .groundTruth3DDisplacements,
    .relationSpaceGeometryMetrics,
    .controlledVariantMetrics ]

/-- Steps the paper offers to show the result does not hang on a choice:
RGB-only tracks (Table 2, Table 4), raw tokens with no fitted readout
(Table 1), training without reconstruction (Table 3), other token sizes
(Table 8). In each the property "3D structure is present" is kept. -/
def offeredForgets : List (ForgetStep Dep) :=
  [ ⟨.trainingTracksFromDepthAndPose, .shown⟩,
    ⟨.linearReadoutFittedOnGroundTruth3D, .shown⟩,
    ⟨.auxiliaryReconstruction, .shown⟩,
    ⟨.relationTokenDimension, .shown⟩ ]

/-- The question of the abstract. Recorded with what the paper's answer to it
(Sec. 4.2 and 4.3, full RePT model) was obtained through. -/
def claim1 : Claim Dep Hyp where
  statement :=
    "We ask whether 3D structure can emerge from learning relations across 2D observations, without 3D prediction targets."
  kind := .intrinsic
  used :=
    [ ⟨.distinctPointRelationalObjective, .setByExperimenter⟩,
      ⟨.trainingTracksFromDepthAndPose, .setByExperimenter⟩,
      ⟨.additiveRelationParameterization, .setByExperimenter⟩,
      ⟨.jointlyAdaptedSceneContext, .setByExperimenter⟩,
      ⟨.frozenDinoV2Backbone, .setByExperimenter⟩,
      ⟨.linearReadoutFittedOnGroundTruth3D, .setByExperimenter⟩,
      ⟨.auxiliaryReconstruction, .setByExperimenter⟩,
      ⟨.relationTokenDimension, .setByExperimenter⟩,
      ⟨.staticIndoorSceneData, .setByExperimenter⟩,
      ⟨.groundTruth3DDisplacements, .measured⟩,
      ⟨.relationSpaceGeometryMetrics, .measured⟩ ]
  declared := statedInPaper
  forgets := offeredForgets
  hypotheses :=
    [ ⟨.trainingUsesNo3DPredictionTargets, .discharged⟩,
      ⟨.structureIsNotAnArtifactOfTheReadout, .discharged⟩ ]
  declaredBets := []

/-- The closing sentence of the abstract. Same derivation as `claim1`, plus
the controlled comparisons ("our results") and the untested step to spatial
intelligence. -/
def claim2 : Claim Dep Hyp where
  statement :=
    "More broadly, our results suggest that 3D geometry need not be an explicit prediction target and can instead emerge as a structural property of representations trained to relate 2D observations, pointing to relational prediction as a complementary route to learning the representations that spatial intelligence builds on."
  kind := .intrinsic
  used :=
    [ ⟨.distinctPointRelationalObjective, .setByExperimenter⟩,
      ⟨.trainingTracksFromDepthAndPose, .setByExperimenter⟩,
      ⟨.additiveRelationParameterization, .setByExperimenter⟩,
      ⟨.jointlyAdaptedSceneContext, .setByExperimenter⟩,
      ⟨.frozenDinoV2Backbone, .setByExperimenter⟩,
      ⟨.linearReadoutFittedOnGroundTruth3D, .setByExperimenter⟩,
      ⟨.auxiliaryReconstruction, .setByExperimenter⟩,
      ⟨.relationTokenDimension, .setByExperimenter⟩,
      ⟨.staticIndoorSceneData, .setByExperimenter⟩,
      ⟨.groundTruth3DDisplacements, .measured⟩,
      ⟨.relationSpaceGeometryMetrics, .measured⟩,
      ⟨.controlledVariantMetrics, .measured⟩ ]
  declared := statedInPaper
  forgets := offeredForgets
  hypotheses :=
    [ ⟨.trainingUsesNo3DPredictionTargets, .discharged⟩,
      ⟨.structureIsNotAnArtifactOfTheReadout, .discharged⟩,
      ⟨.relationalRepresentationsSupportSpatialIntelligence, .bet⟩ ]
  declaredBets := [.relationalRepresentationsSupportSpatialIntelligence]

#eval audit claim1
#eval verdictV1 claim1
#eval rule4Fired claim1

#eval audit claim2
#eval verdictV1 claim2
#eval rule4Fired claim2

theorem claim1_v1 : verdictV1 claim1 = .rejected := by decide
theorem claim1_rule4 : rule4Fired claim1 = true := by decide

theorem claim2_v1 : verdictV1 claim2 = .rejected := by decide
theorem claim2_rule4 : rule4Fired claim2 = true := by decide

end EpistemicLedger.Cases.Round2A.RePT
