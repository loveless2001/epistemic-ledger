import EpistemicLedger.AuditRules

/-
Blind record for "RePT: 3D Geometry Emerges from 2D Relational Pretraining".
Two abstract sentences; both lean on the same experimental derivation
(Sections 3-5, Tables 1-3, Appendix A-D), so they share the `used` list.
-/
namespace EpistemicLedger.Cases.Round2B.RePT

inductive Dep where
  /-- Sec. 3.1/3.3: "relational point transfer requires a relation between two
  distinct physical points to remain applicable under a new view configuration";
  Sec. 4.4: the matched same-point correspondence baseline "achieves lower length
  and angle correlations than RePT" (Table 3). Chosen training objective. -/
  | distinctPointRelationalObjective
  /-- Eq. (4) "qA→B = h(j, pB; C) − h(i, pA; C)"; Sec. 4.4: replacing it "with a
  learned MLP relation encoder causes a large reduction in geometric organization"
  (Table 3: Len. 0.3335 vs 0.8639). Chosen parameterization. -/
  | additiveRelationParameterization
  /-- Sec. 4.4 "Context adaptation": frozen context "scene-specific correlations fall
  to 0.2523 and 0.3175 ... highlighting the importance of jointly adapting C to the
  relational objective". Chosen training regime. -/
  | adaptiveSceneContext
  /-- Sec. 3.2 "we use DINOv2 [16] to map each scene image to patch features";
  Table 9 "DINOv2 ViT-S/14, frozen". Backbone never varied. -/
  | frozenDINOv2Backbone
  /-- Sec. 4.1 "We construct sparse multi-view landmark tracks using the provided
  depth maps and camera poses"; Sec. 5 "Default training tracks are constructed
  offline from depth and pose". -/
  | trainingTracksFromDepthAndPose
  /-- Sec. 3.3 auxiliary CroCo-style reconstruction (λrec = 0.1) and Sec. 4.1
  "we initialize the Context Encoder with 5 epochs of cross-view reconstruction
  pretraining". -/
  | reconstructionObjectiveAndInit
  /-- Sec. 3.2 "We use a 16-dimensional relation token qA→B". -/
  | relationTokenDim16
  /-- Sec. 4.1 "We train and evaluate RePT on ARKitScenes [1], using 4492 sequences";
  Sec. 5 "Evaluation is limited to static indoor scenes". Dataset choice; the
  training data are never varied (ScanNet++ is evaluation only). -/
  | arkitScenesStaticIndoorTrainingData
  /-- Sec. 4.2 "we fit a linear map Ws : R16 → R3 directly from relation tokens to
  their corresponding physical 3D displacement vectors"; Sec. 5 "Readouts are fitted
  using ground-truth 3D displacements". Evaluation choice. -/
  | linearReadoutFittedOnGroundTruth3D
  /-- Sec. 4.2 "∆xA→B = xB − xA denote the corresponding physical 3D displacement";
  App. B.1 displacements from valid-depth locations. Read off the scenes. -/
  | groundTruth3DDisplacements
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Sec. 4.3 "Cross-dataset generalization": on ScanNet++ "RePT retains strong
  geometric organization" (Table 2). Checked for one other dataset. -/
  | holdsOnAnotherDataset
  /-- Sec. 5 "Evaluation is limited to static indoor scenes"; "The hypothesis predicts
  that the organization should weaken in non-rigid scenes". Unchecked, stated. -/
  | holdsBeyondStaticIndoorScenes
  /-- Sec. 5 "Whether such relational representations can support reasoning,
  planning, or control ... are the natural next questions". Unchecked, stated. -/
  | representationsSupportSpatialIntelligence
  deriving DecidableEq, Repr

/-- The derivation both claims lean on. -/
def usedDeps : List (Dependency Dep) :=
  [ ⟨.distinctPointRelationalObjective, .setByExperimenter⟩,
    ⟨.additiveRelationParameterization, .setByExperimenter⟩,
    ⟨.adaptiveSceneContext, .setByExperimenter⟩,
    ⟨.frozenDINOv2Backbone, .setByExperimenter⟩,
    ⟨.trainingTracksFromDepthAndPose, .setByExperimenter⟩,
    ⟨.reconstructionObjectiveAndInit, .setByExperimenter⟩,
    ⟨.relationTokenDim16, .setByExperimenter⟩,
    ⟨.arkitScenesStaticIndoorTrainingData, .setByExperimenter⟩,
    ⟨.linearReadoutFittedOnGroundTruth3D, .setByExperimenter⟩,
    ⟨.groundTruth3DDisplacements, .measured⟩ ]

/-- v1: declared if stated anywhere in the paper. All of them are
(abstract: "depends on additive relations and adaptive scene context";
Sec. 5 limitations name readouts, depth/pose tracks, static indoor scenes;
Sec. 3-4 and Table 9 name the rest). -/
def declaredDeps : List Dep :=
  [ .distinctPointRelationalObjective, .additiveRelationParameterization,
    .adaptiveSceneContext, .frozenDINOv2Backbone, .trainingTracksFromDepthAndPose,
    .reconstructionObjectiveAndInit, .relationTokenDim16,
    .arkitScenesStaticIndoorTrainingData, .linearReadoutFittedOnGroundTruth3D,
    .groundTruth3DDisplacements ]

/-- Forget steps the paper offers, with its evidence. -/
def forgetSteps : List (ForgetStep Dep) :=
  [ -- App. A.2 "These results show that the geometric organization also emerges
    -- when training correspondences are obtained by RGB-only tracking" (Table 4).
    ⟨.trainingTracksFromDepthAndPose, .shown⟩,
    -- Sec. 4.4 "Reconstruction aids optimization but is not needed for geometric
    -- emergence" (Table 3, "Relation only" from scratch: Len. 0.8673).
    ⟨.reconstructionObjectiveAndInit, .shown⟩,
    -- Sec. 4.4 "Across relation dimensions of 3, 4, 8, 16, and 32, RePT
    -- consistently develops geometric structure" (Table 8).
    ⟨.relationTokenDim16, .shown⟩,
    -- Sec. 4.2 "Raw q achieves a length Pearson correlation of 0.5921 and an angle
    -- Pearson correlation of 0.6789 ... before any explicit geometric calibration".
    ⟨.linearReadoutFittedOnGroundTruth3D, .shown⟩ ]

def claim1 : Claim Dep Hyp where
  statement := "We ask whether 3D structure can emerge from learning relations across 2D observations, without 3D prediction targets."
  kind := .intrinsic
  used := usedDeps
  declared := declaredDeps
  forgets := forgetSteps
  hypotheses := []
  declaredBets := []

def claim2 : Claim Dep Hyp where
  statement := "More broadly, our results suggest that 3D geometry need not be an explicit prediction target and can instead emerge as a structural property of representations trained to relate 2D observations, pointing to relational prediction as a complementary route to learning the representations that spatial intelligence builds on."
  kind := .intrinsic
  used := usedDeps
  declared := declaredDeps
  forgets := forgetSteps
  hypotheses :=
    [ ⟨.holdsOnAnotherDataset, .discharged⟩,
      ⟨.holdsBeyondStaticIndoorScenes, .bet⟩,
      ⟨.representationsSupportSpatialIntelligence, .bet⟩ ]
  declaredBets := [.holdsBeyondStaticIndoorScenes, .representationsSupportSpatialIntelligence]

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

end EpistemicLedger.Cases.Round2B.RePT
