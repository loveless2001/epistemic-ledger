import EpistemicLedger.ClaimRecordTypes

/-
The four audit rules (v0), as a decidable function from a claim record to a
list of findings.

  R1  A claim carries its dependency set.
  R2  Dropping a dependency needs a forget step with evidence of invariance.
  R3  A theorem applied to a target needs each hypothesis discharged for that
      target: unchecked = bet (must be declared), known false = fail.
  R4  A claim worded as "arises by itself" may not rest on a structure that the
      experimenter set.

The rules check the record against itself. They cannot check that the record
is a faithful reading of the paper: a dependency left out of `used` is invisible.
-/
namespace EpistemicLedger

/-- What the audit can report about one claim. -/
inductive Finding (ι η : Type) where
  /-- R1: used by the derivation, not declared, no forget step offered. -/
  | droppedDependency (dep : ι)
  /-- R2: a forget step is offered but carries no evidence of invariance. -/
  | forgetWithoutEvidence (dep : ι)
  /-- R2: the record shows the conclusion changes when this dependency varies. -/
  | forgetContradicted (dep : ι)
  /-- R3: a hypothesis of the applied theorem is known not to hold for the target. -/
  | hypothesisKnownFalse (hyp : η)
  /-- R3: an unchecked hypothesis that the claim does not declare. -/
  | undeclaredBet (hyp : η)
  /-- R4: an "arises by itself" claim rests on an experimenter-set structure. -/
  | intrinsicOnExperimenterStructure (dep : ι)
  deriving DecidableEq, Repr

variable {ι η : Type} [DecidableEq ι] [DecidableEq η]

/-- Does some forget step for dependency `d` carry evidence `e`? -/
def hasForgetEvidence (forgets : List (ForgetStep ι)) (d : ι) (e : Invariance) : Bool :=
  forgets.any (fun step => step.dependency = d ∧ step.evidence = e)

/-- The evidence a list of forget steps holds for dropping `d`, whatever their
order: a contradiction anywhere wins, then `shown`, then `notShown`.
(v0 took the first matching step, so `[shown, contradicted]` passed; found by
codex, see `Cases/AdversarialForgetOrder.lean`.) -/
def forgetEvidenceOf (forgets : List (ForgetStep ι)) (d : ι) : Option Invariance :=
  if hasForgetEvidence forgets d .contradicted then some .contradicted
  else if hasForgetEvidence forgets d .shown then some .shown
  else if hasForgetEvidence forgets d .notShown then some .notShown
  else none

/-- The evidence the record holds for dropping dependency `d`, if any. -/
def forgetEvidence (c : Claim ι η) (d : ι) : Option Invariance :=
  forgetEvidenceOf c.forgets d

/-- R1 + R2 for one used dependency. -/
def dependencyFinding (c : Claim ι η) (dep : Dependency ι) : Option (Finding ι η) :=
  if dep.id ∈ c.declared then none
  else match forgetEvidence c dep.id with
    | some .shown => none
    | some .notShown => some (.forgetWithoutEvidence dep.id)
    | some .contradicted => some (.forgetContradicted dep.id)
    | none => some (.droppedDependency dep.id)

/-- R3 for one applied hypothesis. -/
def hypothesisFinding (c : Claim ι η) (h : Hypothesis η) : Option (Finding ι η) :=
  match h.status with
  | .discharged => none
  | .knownFalse => some (.hypothesisKnownFalse h.id)
  | .bet => if h.id ∈ c.declaredBets then none else some (.undeclaredBet h.id)

/-- R4 for one used dependency. -/
def intrinsicFinding (c : Claim ι η) (dep : Dependency ι) : Option (Finding ι η) :=
  if c.kind = .intrinsic ∧ dep.source = .setByExperimenter
      ∧ forgetEvidence c dep.id ≠ some .shown
  then some (.intrinsicOnExperimenterStructure dep.id)
  else none

/-- All findings for a claim, grouped by rule: R1/R2, then R3, then R4. -/
def audit (c : Claim ι η) : List (Finding ι η) :=
  c.used.filterMap (dependencyFinding c)
    ++ c.hypotheses.filterMap (hypothesisFinding c)
    ++ c.used.filterMap (intrinsicFinding c)

/-- Which rule a finding comes from (1 to 4). -/
def Finding.rule : Finding ι η → Nat
  | .droppedDependency _ => 1
  | .forgetWithoutEvidence _ => 2
  | .forgetContradicted _ => 2
  | .hypothesisKnownFalse _ => 3
  | .undeclaredBet _ => 3
  | .intrinsicOnExperimenterStructure _ => 4

/-- Number of findings per rule, as (R1, R2, R3, R4). The verdict only says
"some finding"; the profile says which rule fired. -/
def ruleProfile (fs : List (Finding ι η)) : Nat × Nat × Nat × Nat :=
  ( fs.countP (fun f => f.rule = 1), fs.countP (fun f => f.rule = 2),
    fs.countP (fun f => f.rule = 3), fs.countP (fun f => f.rule = 4) )

/-- The status a claim gets in the ledger. -/
inductive Verdict where
  /-- No findings and no unchecked hypotheses. -/
  | admissible
  /-- No findings, but the claim openly rests on unchecked hypotheses. -/
  | admissibleOnDeclaredBets
  /-- At least one finding. -/
  | rejected
  deriving DecidableEq, Repr

/-- Does the claim rest on at least one unchecked hypothesis? -/
def hasBet (c : Claim ι η) : Bool :=
  c.hypotheses.any (fun h => h.status = .bet)

def verdict (c : Claim ι η) : Verdict :=
  if (audit c).isEmpty then
    if hasBet c then .admissibleOnDeclaredBets else .admissible
  else .rejected

/-! ### v1 verdict (after the blind test of 2026-11-26)

The blind test showed that "any finding rejects" rejects almost every single
sentence, because rule 1 fires whenever a sentence does not list everything
behind it. In v1 only two kinds of finding reject a claim; the rest are notes.
The v0 `verdict` is kept unchanged so earlier results still compile. -/

/-- Does this finding reject a claim under v1? Rule 4, or a hypothesis known
to be false for the target. -/
def Finding.rejectsV1 : Finding ι η → Bool
  | .intrinsicOnExperimenterStructure _ => true
  | .hypothesisKnownFalse _ => true
  | _ => false

inductive VerdictV1 where
  /-- A rule-4 finding or a known-false hypothesis. -/
  | rejected
  /-- No rejecting finding, but other findings are recorded as notes. -/
  | passedWithNotes
  /-- No findings at all. -/
  | passed
  deriving DecidableEq, Repr

def verdictV1 (c : Claim ι η) : VerdictV1 :=
  if (audit c).any Finding.rejectsV1 then .rejected
  else if (audit c).isEmpty then .passed
  else .passedWithNotes

/-- Did rule 4 fire for this claim? -/
def rule4Fired (c : Claim ι η) : Bool :=
  (audit c).any (fun f => f.rule = 4)

/-! ### The order of forget steps does not matter -/

theorem hasForgetEvidence_perm {l₁ l₂ : List (ForgetStep ι)} (h : l₁.Perm l₂)
    (d : ι) (e : Invariance) :
    hasForgetEvidence l₁ d e = hasForgetEvidence l₂ d e := by
  unfold hasForgetEvidence
  rw [Bool.eq_iff_iff]
  simp only [List.any_eq_true]
  constructor
  · rintro ⟨step, hmem, hp⟩
    exact ⟨step, h.mem_iff.mp hmem, hp⟩
  · rintro ⟨step, hmem, hp⟩
    exact ⟨step, h.mem_iff.mpr hmem, hp⟩

theorem forgetEvidenceOf_perm {l₁ l₂ : List (ForgetStep ι)} (h : l₁.Perm l₂) (d : ι) :
    forgetEvidenceOf l₁ d = forgetEvidenceOf l₂ d := by
  simp only [forgetEvidenceOf, hasForgetEvidence_perm h]

/-- Reordering a claim's forget steps never changes its findings. -/
theorem audit_forget_order_irrelevant (c : Claim ι η) (l : List (ForgetStep ι))
    (h : c.forgets.Perm l) :
    audit { c with forgets := l } = audit c := by
  have hev : ∀ d, forgetEvidence { c with forgets := l } d = forgetEvidence c d :=
    fun d => (forgetEvidenceOf_perm h d).symm
  have h1 : dependencyFinding { c with forgets := l } = dependencyFinding c := by
    funext dep
    simp only [dependencyFinding, hev]
  have h2 : intrinsicFinding { c with forgets := l } = intrinsicFinding c := by
    funext dep
    simp only [intrinsicFinding, hev]
  have h3 : hypothesisFinding { c with forgets := l } = hypothesisFinding c := by
    funext hyp
    rfl
  simp only [audit, h1, h2, h3]

/-! ### What an auditor's omissions can and cannot do -/

/-- Appending entries to `used`, with every other field unchanged, never
removes a finding.

Scope (codex, msg 27247): this covers one kind of auditor error only, a used
dependency left out. It says nothing about a rejection caused by a wrong
record: correcting `declared`, or removing a spurious entry from `used`, can
turn `rejected` into `admissible`
(see `Cases/RejectionNotRobustToOtherRecordErrors.lean`). -/
theorem audit_findings_survive_more_used (c : Claim ι η) (extra : List (Dependency ι)) :
    ∀ f ∈ audit c, f ∈ audit { c with used := c.used ++ extra } := by
  intro f hf
  have h1 : dependencyFinding { c with used := c.used ++ extra } = dependencyFinding c := by
    funext dep
    rfl
  have h2 : intrinsicFinding { c with used := c.used ++ extra } = intrinsicFinding c := by
    funext dep
    rfl
  have h3 : hypothesisFinding { c with used := c.used ++ extra } = hypothesisFinding c := by
    funext hyp
    rfl
  simp only [audit, h1, h2, h3, List.filterMap_append, List.mem_append] at hf ⊢
  rcases hf with (hf | hf) | hf
  · exact Or.inl (Or.inl (Or.inl hf))
  · exact Or.inl (Or.inr hf)
  · exact Or.inr (Or.inl hf)

/-! ### What a clean audit guarantees (about the record, not about the world) -/

/-- R1/R2: in a claim with no findings, every used dependency is either declared
or dropped by a forget step whose invariance is shown. -/
theorem clean_audit_dependency_declared_or_forgotten (c : Claim ι η)
    (h : audit c = []) :
    ∀ dep ∈ c.used, dep.id ∈ c.declared ∨ forgetEvidence c dep.id = some .shown := by
  intro dep hdep
  have h12 := (List.append_eq_nil_iff.mp h).1
  have h1 : c.used.filterMap (dependencyFinding c) = [] :=
    (List.append_eq_nil_iff.mp h12).1
  have hnone : dependencyFinding c dep = none :=
    List.filterMap_eq_nil_iff.mp h1 dep hdep
  unfold dependencyFinding at hnone
  split at hnone
  · exact Or.inl ‹_›
  · right
    split at hnone <;> simp_all

/-- R4: in an "arises by itself" claim with no findings, every experimenter-set
dependency has been dropped by a forget step whose invariance is shown. -/
theorem clean_audit_intrinsic_has_no_experimenter_structure (c : Claim ι η)
    (h : audit c = []) (hkind : c.kind = .intrinsic) :
    ∀ dep ∈ c.used, dep.source = .setByExperimenter →
      forgetEvidence c dep.id = some .shown := by
  intro dep hdep hsrc
  have h3 : c.used.filterMap (intrinsicFinding c) = [] :=
    (List.append_eq_nil_iff.mp h).2
  have hnone : intrinsicFinding c dep = none :=
    List.filterMap_eq_nil_iff.mp h3 dep hdep
  unfold intrinsicFinding at hnone
  split at hnone
  · simp at hnone
  · rename_i hcond
    exact Decidable.byContradiction fun hne => hcond ⟨hkind, hsrc, hne⟩

end EpistemicLedger
