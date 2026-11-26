import EpistemicLedger.OperationFlow

/-
Review cases for the v2 operation-flow engine (claude, 2026-11-26).
Synthetic graphs. Each theorem states what the engine does today; the comments
say whether that behaviour is a closed gap (now a regression test) or still
open. Nothing in `OperationFlow.lean` was changed by claude.
-/
namespace EpistemicLedger.Cases.V2ReviewUndeclaredLeafAndFailedForget

open EpistemicLedger
open EpistemicLedger.OperationFlow

inductive Node where
  | simulator
  | probe
  | agentMemory
  | readout
  deriving DecidableEq, Repr

inductive Tag where
  | causalStructure
  deriving DecidableEq, Repr

/-- The simulator carries the structure and feeds the agent. -/
def fullGraph : FlowGraph Node Tag where
  sources :=
    [ ⟨.simulator, .setByExperimenter, [.causalStructure]⟩,
      ⟨.probe, .setByExperimenter, []⟩ ]
  ops :=
    [ ⟨"train", [.simulator, .probe], .agentMemory, .transform []⟩,
      ⟨"read", [.agentMemory], .readout, .transform []⟩ ]

/-- Same operations, but the auditor did not list the simulator under
`sources`. It is still an input of the "train" operation. -/
def graphWithUndeclaredLeaf : FlowGraph Node Tag :=
  { fullGraph with sources := [⟨.probe, .setByExperimenter, []⟩] }

def emergenceOn (g : FlowGraph Node Tag) : FlowClaim Node Tag where
  statement := "The causal structure emerges in the readout."
  graph := g
  kind := .emergesWithout .readout .causalStructure

/-- With the simulator declared, the claim is rejected. -/
theorem full_graph_rejected : flowVerdict (emergenceOn fullGraph) = .rejected := by decide

/-- GAP 1 (closed). With the simulator left out of `sources`, the same claim
used to pass, although the graph itself shows an input whose origin and
structure were never stated. Since gemini's dangling-input check
(2026-11-26 17:35) it is rejected. Kept as a regression test. -/
theorem undeclared_leaf_input_rejected :
    flowVerdict (emergenceOn graphWithUndeclaredLeaf) = .rejected := by decide

/-- GAP 1 (closed), conditional claims: the undeclared input is now reported. -/
theorem undeclared_leaf_input_rejected_conditional :
    flowVerdict
      { statement := "Given the probe, the readout holds."
        graph := graphWithUndeclaredLeaf
        kind := .conditionalFlow .readout [.probe] } = .rejected := by decide

/-- A graph in which nothing carries the structure, with one forget step that
has no evidence. -/
def graphWithIdleForget : FlowGraph Node Tag where
  sources := [⟨.probe, .setByExperimenter, []⟩]
  ops :=
    [ ⟨"train", [.probe], .agentMemory, .transform []⟩,
      ⟨"claimed_irrelevant", [.agentMemory], .readout, .forget .causalStructure .notShown⟩ ]

/-- GAP 2 (closed). No source and no operation carries the structure, so there
is no smuggling path. The claim used to be rejected anyway, because a forget
step without evidence rejected on its own. Since gemini's fix (2026-11-26
17:39) a failed forget only counts when the structure actually reaches it.
Kept as a regression test. -/
theorem idle_forget_no_longer_rejects :
    findSmugglingPath graphWithIdleForget .causalStructure .readout = none
      ∧ flowVerdict (emergenceOn graphWithIdleForget) = .admissible := by decide

/-- OBSERVATION (open). Whether an emergence claim is rejected follows the auditor's
`carries` label: the same operations with the label removed from the simulator
pass. In a pipeline where every input reaches the target, the path search adds
nothing to that one label. -/
theorem verdict_follows_the_carries_label :
    flowVerdict (emergenceOn
      { fullGraph with
        sources :=
          [ ⟨.simulator, .setByExperimenter, []⟩,
            ⟨.probe, .setByExperimenter, []⟩ ] }) = .admissible := by decide

end EpistemicLedger.Cases.V2ReviewUndeclaredLeafAndFailedForget
