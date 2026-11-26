/-
Claim records: what an auditor (human or AI) writes down after reading a paper.

A record does NOT say whether a claim is true. It says what the claim's own
derivation leaned on, so that the audit rules (see `AuditRules.lean`) can check
whether the claim, as worded, still carries everything it leaned on.

Identifiers are type parameters, not strings: each case file defines its own
small enumeration of dependencies (`ι`) and hypotheses (`η`). A misspelt
dependency is then a compile error instead of a silent false finding.
-/
namespace EpistemicLedger

/-- Where a structure that the argument relies on comes from (rule 4). -/
inductive Source where
  /-- Chosen or constructed by whoever ran the study (a knob, a cut, a labelling). -/
  | setByExperimenter
  /-- Read off the system under study. -/
  | measured
  deriving DecidableEq, Repr

/-- Anything the derivation of a claim used: a cut, a control, an external input (rule 1).

v1 guidance (after the blind test): list what the claimed result is obtained
through, that is, what it would change with or could not be obtained without.
Routine details nobody would expect to matter need not be listed. -/
structure Dependency (ι : Type) where
  id : ι
  source : Source
  deriving DecidableEq, Repr

/-- Evidence attached to an explicit "forget" step (rule 2).

v1 guidance: "the conclusion" is the property the claim asserts, as worded in
its statement. Ask whether that property stays the same when the dependency
is varied or removed. -/
inductive Invariance where
  /-- The record shows the conclusion is unchanged when the dependency varies. -/
  | shown
  /-- No evidence either way. -/
  | notShown
  /-- The record shows the conclusion DOES change when the dependency varies. -/
  | contradicted
  deriving DecidableEq, Repr

/-- An explicit step that drops a dependency from a claim (rule 2). -/
structure ForgetStep (ι : Type) where
  dependency : ι
  evidence : Invariance
  deriving DecidableEq, Repr

/-- Status of a theorem's hypothesis for the target the theorem is applied to (rule 3). -/
inductive Discharge where
  /-- Shown to hold for the target. -/
  | discharged
  /-- Nobody has checked it for the target. -/
  | bet
  /-- The record itself says it does not hold for the target. -/
  | knownFalse
  deriving DecidableEq, Repr

/-- A hypothesis of a theorem that the claim applies to its target (rule 3). -/
structure Hypothesis (η : Type) where
  id : η
  status : Discharge
  deriving DecidableEq, Repr

/-- How the claim is worded. -/
inductive ClaimKind where
  /-- "Given these dependencies, X holds." -/
  | conditional
  /-- "X arises by itself / internally / from the object of study alone." -/
  | intrinsic
  deriving DecidableEq, Repr

/--
One claim of a paper, as recorded by an auditor.

* `used`         — everything the paper's own derivation used.
* `declared`     — the dependencies the claim admits to. v1: a dependency
                   counts as declared if the paper states it anywhere, not
                   only in the quoted sentence.
* `forgets`      — explicit steps offered to justify dropping a dependency.
* `hypotheses`   — hypotheses of any theorem applied to the claim's target.
* `declaredBets` — unchecked hypotheses the paper openly states the claim
                   rests on (v1: stated anywhere in the paper).
-/
structure Claim (ι η : Type) where
  statement : String
  kind : ClaimKind
  used : List (Dependency ι)
  declared : List ι
  forgets : List (ForgetStep ι)
  hypotheses : List (Hypothesis η)
  declaredBets : List η
  deriving Repr

end EpistemicLedger
