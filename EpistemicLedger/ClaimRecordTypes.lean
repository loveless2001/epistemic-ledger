/-
Core epistemic provenance, invariance, and theorem-hypothesis types shared by
`EpistemicLedger.OperationFlow`.

Identifiers are type parameters, not strings: each generated or benchmark module
defines its own small enumeration of nodes (`ν`) and structural tags (`σ`) so a
misspelt identifier is a compile error rather than a silent false finding.
-/
namespace EpistemicLedger

/-- Where a structure that the argument relies on comes from. -/
inductive Source where
  /-- Chosen or constructed by whoever ran the study (a knob, a cut, a labelling). -/
  | setByExperimenter
  /-- Read off the system under study. -/
  | measured
  deriving DecidableEq, Repr

/-- Evidence attached to an explicit `forget` operation. -/
inductive Invariance where
  /-- The record shows the conclusion is unchanged when the dependency varies. -/
  | shown
  /-- No evidence either way. -/
  | notShown
  /-- The record shows the conclusion DOES change when the dependency varies. -/
  | contradicted
  deriving DecidableEq, Repr

/-- Status of a theorem's hypothesis for the target the theorem is applied to (Rule 3). -/
inductive Discharge where
  /-- Shown to hold for the target. -/
  | discharged
  /-- Nobody has checked it for the target. -/
  | bet
  /-- The record itself says it does not hold for the target. -/
  | knownFalse
  deriving DecidableEq, Repr

/-- A hypothesis of a theorem that the claim applies to its target (Rule 3). -/
structure Hypothesis (η : Type) where
  id : η
  status : Discharge
  deriving DecidableEq, Repr

end EpistemicLedger
