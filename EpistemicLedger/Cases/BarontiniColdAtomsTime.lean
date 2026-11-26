import EpistemicLedger.AuditRules

/-
Case 1. G. Barontini, "Testing the problem of time with cold atoms",
Phys. Rev. Research 8, L022047 (2026); read from arXiv:2509.07745v3.

Record written by claude from the paper text. Quotes are from the paper.
-/
namespace EpistemicLedger.Cases.BarontiniColdAtomsTime

/-- What the paper's derivation of the entropic time τ uses. -/
inductive Dep where
  /-- Barrier height V, a knob. "The amount of atoms entering or escaping the
  bright sector is determined by the height of the barrier." Fig. 2: the slope
  of τ depends on V, and τ stops at V ≃ 1. -/
  | barrierHeightV
  /-- The partition into 'bright' (observed) and 'dark' (unobserved) at x = 0.
  Both halves are imaged; the paper uses the dark half to check that total
  entropy is constant. The partition is the author's choice. -/
  | observedUnobservedCutAtXZero
  /-- "taking an absorption image every 2 ms" in lab time, then "starting from
  the first big bang, we compute τ": τ is accumulated along the lab-ordered
  sequence of images (claude's reading of the procedure). -/
  | labClockOrderingOfImages
  /-- σ, "the (arbitrary) entropic time unit" in Eq. (3). -/
  | arbitraryEntropicTimeUnitSigma
  /-- Atom number N, centre of mass φ and width Σ of the bright sector, per image. -/
  | measuredBrightSectorObservables
  deriving DecidableEq, Repr

/-- The paper applies no external theorem to a target; no hypotheses to discharge. -/
inductive Hyp where
  deriving DecidableEq, Repr

def usedByDerivation : List (Dependency Dep) :=
  [ ⟨.barrierHeightV, .setByExperimenter⟩,
    ⟨.observedUnobservedCutAtXZero, .setByExperimenter⟩,
    ⟨.labClockOrderingOfImages, .setByExperimenter⟩,
    ⟨.arbitraryEntropicTimeUnitSigma, .setByExperimenter⟩,
    ⟨.measuredBrightSectorObservables, .measured⟩ ]

/-- The abstract's framing: an internal-only ordering. The only dependency it
admits is the bright sector's own observables. The paper offers no forget
step; the one for V is recorded as contradicted because of its own Fig. 2. -/
def headlineClaim : Claim Dep Hyp where
  statement :=
    "The dynamics of the observed sector can be ordered using only internal degrees of freedom."
  kind := .intrinsic
  used := usedByDerivation
  declared := [.measuredBrightSectorObservables]
  forgets := [⟨.barrierHeightV, .contradicted⟩]
  hypotheses := []
  declaredBets := []

/-- The narrow claim the paper's body supports, with every dependency carried. -/
def bodyClaim : Claim Dep Hyp where
  statement :=
    "Given the cut at x = 0, the barrier height V, lab-ordered images and the unit σ, the entropic parameter τ orders the bright-sector data."
  kind := .conditional
  used := usedByDerivation
  declared :=
    [ .barrierHeightV, .observedUnobservedCutAtXZero, .labClockOrderingOfImages,
      .arbitraryEntropicTimeUnitSigma, .measuredBrightSectorObservables ]
  forgets := []
  hypotheses := []
  declaredBets := []

/-- The headline is rejected, and these are exactly the findings. -/
theorem headline_findings :
    audit headlineClaim =
      [ .forgetContradicted .barrierHeightV,
        .droppedDependency .observedUnobservedCutAtXZero,
        .droppedDependency .labClockOrderingOfImages,
        .droppedDependency .arbitraryEntropicTimeUnitSigma,
        .intrinsicOnExperimenterStructure .barrierHeightV,
        .intrinsicOnExperimenterStructure .observedUnobservedCutAtXZero,
        .intrinsicOnExperimenterStructure .labClockOrderingOfImages,
        .intrinsicOnExperimenterStructure .arbitraryEntropicTimeUnitSigma ] := by
  decide

theorem headline_rejected : verdict headlineClaim = .rejected := by decide

/-- Control: the same audit accepts the narrow claim. -/
theorem body_claim_admissible : verdict bodyClaim = .admissible := by decide

end EpistemicLedger.Cases.BarontiniColdAtomsTime
