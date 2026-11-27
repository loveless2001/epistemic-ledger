import EpistemicLedger.OperationFlow

/- The initial OperationFlow checker admitted the first three cases. Each
regression checks the specific finding as well as the verdict. -/
namespace EpistemicLedger.Cases.AdversarialOperationFlow

open OperationFlow

inductive Node where
  | input | intermediate | output | other
  deriving DecidableEq, Repr

inductive Tag where
  | geometry
  deriving DecidableEq, Repr

private def verdictFor (g : FlowGraph Node Tag) (k : FlowClaimKind Node Tag) : EpistemicVerdict :=
  epistemicVerdict ⟨"Synthetic review case", g, k⟩

/-- The only tagged origin is an operation. The measured source carries no geometry. -/
private def injected : FlowGraph Node Tag :=
  ⟨[⟨.input, .measured, []⟩], [⟨"supply geometry", [.input], .output, .transform [.geometry]⟩]⟩

theorem injected_tag_cannot_establish_recovery :
    let claim : FlowClaim Node Tag := ⟨"Recovery", injected, .uniqueRecovery .output .geometry⟩
    auditFlow claim = [.unaccessedTargetStructure .output .geometry] ∧
      epistemicVerdict claim = .unestablished := by decide

/-- Both branches use the same unforgotten experimenter-set input. Each
operation introduces the target tag independently of the other operation. -/
private def sharedSetup : FlowGraph Node Tag :=
  ⟨[⟨.input, .setByExperimenter, []⟩],
   [⟨"left", [.input], .output, .transform [.geometry]⟩,
    ⟨"right", [.input], .other, .transform [.geometry]⟩]⟩

theorem shared_setup_precludes_independence :
    let claim : FlowClaim Node Tag :=
      ⟨"Independent branches", sharedSetup, .independentConvergence .output .other .geometry⟩
    auditFlow claim = [.sharedExperimenterSource .input] ∧
      epistemicVerdict claim = .rejected := by decide

/-- A transform consumes a raw input for which no source or producing op was recorded. -/
private def dangling : FlowGraph Node Tag :=
  ⟨[], [⟨"consume missing input", [.input], .output, .transform []⟩]⟩

theorem missing_input_is_reported :
    let claim : FlowClaim Node Tag := ⟨"Conditional result", dangling, .conditionalFlow .output []⟩
    auditFlow claim = [.danglingInput "consume missing input" .input] ∧
      epistemicVerdict claim = .unestablished := by decide

private def blocked : FlowGraph Node Tag :=
  ⟨[⟨.input, .measured, [.geometry]⟩],
   [⟨"remove geometry", [.input], .output, .forget .geometry .shown⟩]⟩

/-- Forget blocks this tag, while the conditional provenance rule still requires the input. -/
example : verdictFor blocked (.emergesWithout .output .geometry) = .admissible ∧
    verdictFor blocked (.conditionalFlow .output []) = .unestablished ∧
    verdictFor blocked (.conditionalFlow .output [.input]) = .admissible := by decide

private def parallel (k : OpKind Tag) : FlowGraph Node Tag :=
  { blocked with ops := blocked.ops ++ [⟨"second path", [.input], .output, k⟩] }

private def rejectsBothOrders (g : FlowGraph Node Tag) : Prop :=
  verdictFor g (.emergesWithout .output .geometry) = .rejected ∧
    verdictFor { g with ops := g.ops.reverse } (.emergesWithout .output .geometry) = .rejected

example : rejectsBothOrders (parallel (.transform [])) := by unfold rejectsBothOrders; decide
example : rejectsBothOrders (parallel (.forget .geometry .contradicted)) := by
  unfold rejectsBothOrders
  decide

private def chain : FlowGraph Node Tag :=
  ⟨blocked.sources,
   [⟨"first", [.input], .intermediate, .transform []⟩,
    ⟨"second", [.intermediate], .output, .transform []⟩,
    ⟨"third", [.output], .other, .transform []⟩]⟩

/-- A witness using every operation in an acyclic graph needs the last unit of fuel. -/
example : findSmugglingPath chain .geometry .other =
    some [.input, .intermediate, .output, .other] := by decide

private def cyclic : FlowGraph Node Tag :=
  { chain with ops := ⟨"back edge", [.other], .intermediate, .transform []⟩ :: chain.ops }

/-- Backward search encounters the cycle first. Both positive and negative searches terminate. -/
example : verdictFor cyclic (.emergesWithout .other .geometry) = .rejected ∧
    verdictFor { cyclic with sources := [⟨.input, .measured, []⟩] } (.emergesWithout .other .geometry) =
      .admissible := by decide

end EpistemicLedger.Cases.AdversarialOperationFlow
