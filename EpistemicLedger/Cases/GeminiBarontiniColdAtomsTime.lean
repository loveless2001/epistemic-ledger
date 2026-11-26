import EpistemicLedger.AuditRules

/-
Independent audit record (by Gemini) for:
  Giovanni Barontini, "Testing the problem of time with cold atoms"
  arXiv:2509.07745v3 (11 Jun 2026) / Phys. Rev. Research, DOI 10.1103/1h9j-df4k

Written directly from the arXiv text without copying other auditors' dependency lists.
-/
namespace EpistemicLedger.Cases.GeminiBarontiniColdAtomsTime

/-- Dependencies extracted from Barontini (2026), Sections 1–5 & Figs. 1–4. -/
inductive Dep where
  /-- Crossed 1070 nm / 1550 nm optical dipole trap setting ω = 2π×(25, 70, 70) Hz. -/
  | opticalDipoleTrap
  /-- Tunable 675 nm DMD optical barrier (width ~8 μm, height V) controlling exchange. -/
  | opticalBarrierHeight
  /-- Experimenter's spatial cut at x = 0 defining "bright (observed)" vs "dark (unobserved)". -/
  | spatialPartitionPlane
  /-- External lab-time sampling (absorption images every 2 ms over 120 ms) ordering λ from "first big bang". -/
  | labTimeImageOrdering
  /-- Free arbitrary entropic time scale unit σ in Eq. (3). -/
  | arbitraryEntropicTimeUnit
  /-- Choice of center-of-mass X as clock field φ and manual selection of positive Feshbach–Villars branch. -/
  | clockAndBranchChoice
  /-- Empirical linear fit M(φ) = α φ and data-inferred pump Λ(τ) plugged into Eq. (6) simulation. -/
  | empiricalPumpAndMassFit
  /-- Measured density profiles yielding N, φ, Σ, and coarse-grained entropy S = N s. -/
  | measuredDensityProfiles
  deriving DecidableEq, Repr

/-- Hypotheses required when reading the lab setup as a time-free WDW construction. -/
inductive Hyp where
  /-- Ordering parameter τ is constructed without external lab-time ordering or branch selection. -/
  | noExternalTimeInConstruction
  /-- Total dark+bright system is well-isolated with negligible dissipation on the ~100 ms timescale. -/
  | negligibleDissipationClosedSystem
  /-- Positive-definite kinetic term in Eq. (2) matches the phenomenology of WDW's indefinite DeWitt metric. -/
  | kineticSignMatchesWdw
  /-- Laboratory BEC analogue transfers to the closed-universe Wheeler–DeWitt problem of time. -/
  | labAnalogueTransfersToWdw
  deriving DecidableEq, Repr

/-- Every dependency the paper's experimental + theoretical derivation relies on. -/
def derivationDeps : List (Dependency Dep) :=
  [ ⟨.opticalDipoleTrap, .setByExperimenter⟩
  , ⟨.opticalBarrierHeight, .setByExperimenter⟩
  , ⟨.spatialPartitionPlane, .setByExperimenter⟩
  , ⟨.labTimeImageOrdering, .setByExperimenter⟩
  , ⟨.arbitraryEntropicTimeUnit, .setByExperimenter⟩
  , ⟨.clockAndBranchChoice, .setByExperimenter⟩
  , ⟨.empiricalPumpAndMassFit, .measured⟩
  , ⟨.measuredDensityProfiles, .measured⟩
  ]

def allDepIds : List Dep := derivationDeps.map (·.id)

/--
Claim 1 (Headline / Abstract-level intrinsic reading):
"The dynamics of the observed sector can be ordered using only internal degrees of
freedom, realizing an operational time-free description analogous to WDW models."
-/
def headlineInternalTimeClaim : Claim Dep Hyp where
  statement :=
    "Dynamics of the observed sector are ordered using only internal degrees of freedom, providing a time-free WDW analogue."
  kind := .intrinsic
  used := derivationDeps
  declared := [.measuredDensityProfiles]
  forgets :=
    [ -- Fig. 2 & 3 directly show τ slows down as barrier height V grows and halts at V ≈ 1;
      -- gain/loss across the barrier was merely "absorbed in the normalization condition" (Eq. 2).
      ⟨.opticalBarrierHeight, .contradicted⟩
    , -- Spatial cut at x = 0 is never removed or shown invariant; removing it removes bright/dark exchange.
      ⟨.spatialPartitionPlane, .notShown⟩
    ]
  hypotheses :=
    [ ⟨.noExternalTimeInConstruction, .knownFalse⟩
    , ⟨.negligibleDissipationClosedSystem, .discharged⟩
    , ⟨.kineticSignMatchesWdw, .bet⟩
    , ⟨.labAnalogueTransfersToWdw, .bet⟩
    ]
  declaredBets := []

/--
Claim 2 (Narrow laboratory operational claim):
Given the experimenter-prepared trap, barrier height V, spatial partition at x = 0,
2 ms lab-time image sequence, chosen clock field/branch, unit σ, and empirically fitted
pump Λ(τ), τ monotonically orders the measured bright-sector observables and Eq. (6)
reproduces Σ(τ) for V ≈ 0.
-/
def narrowLabOrderingClaim : Claim Dep Hyp where
  statement :=
    "Under the declared optical trap, barrier V, spatial cut at x = 0, lab-time image ordering, clock/branch choice, scale σ, and fitted pump Λ(τ), τ orders bright-sector data and Eq. (6) reproduces Σ(τ) at V ≈ 0."
  kind := .conditional
  used := derivationDeps
  declared := allDepIds
  forgets := []
  hypotheses := [⟨.negligibleDissipationClosedSystem, .discharged⟩]
  declaredBets := []

/--
Claim 3 (Narrow analogue-testbed claim with openly declared cosmological bets):
Under all declared experimental dependencies and explicitly declared bets on WDW
transfer and kinetic-metric sign, the platform serves as a controlled relational-time testbed.
-/
def narrowAnalogueTestbedClaim : Claim Dep Hyp where
  statement :=
    "Under all declared experimental dependencies and open bets on WDW transfer and metric sign, the BEC setup serves as a controlled relational-time testbed."
  kind := .conditional
  used := derivationDeps
  declared := allDepIds
  forgets := []
  hypotheses :=
    [ ⟨.negligibleDissipationClosedSystem, .discharged⟩
    , ⟨.kineticSignMatchesWdw, .bet⟩
    , ⟨.labAnalogueTransfersToWdw, .bet⟩
    ]
  declaredBets := [.kineticSignMatchesWdw, .labAnalogueTransfersToWdw]

theorem headline_rejected : verdict headlineInternalTimeClaim = .rejected := by
  decide

theorem headline_contradicts_barrier_forget :
    Finding.forgetContradicted Dep.opticalBarrierHeight ∈ audit headlineInternalTimeClaim := by
  decide

theorem headline_flags_intrinsic_barrier :
    Finding.intrinsicOnExperimenterStructure Dep.opticalBarrierHeight ∈ audit headlineInternalTimeClaim := by
  decide

theorem headline_flags_intrinsic_cut :
    Finding.intrinsicOnExperimenterStructure Dep.spatialPartitionPlane ∈ audit headlineInternalTimeClaim := by
  decide

theorem headline_flags_external_time_false :
    Finding.hypothesisKnownFalse Hyp.noExternalTimeInConstruction ∈ audit headlineInternalTimeClaim := by
  decide

theorem narrow_lab_admissible : verdict narrowLabOrderingClaim = .admissible := by
  decide

theorem narrow_analogue_admissible_on_bets :
    verdict narrowAnalogueTestbedClaim = .admissibleOnDeclaredBets := by
  decide

end EpistemicLedger.Cases.GeminiBarontiniColdAtomsTime
