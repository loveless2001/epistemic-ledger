import EpistemicLedger.Cases.V2BlindASpacetimeAgent
import EpistemicLedger.Cases.V2BlindBSpacetimeAgent
import EpistemicLedger.Cases.V2BlindARePT
import EpistemicLedger.Cases.V2BlindBRePT

/-
v2 blind test, 2026-11-26. Four operation-graph records written by fresh
agents that had not seen the chat thread, earlier records or gemini's
benchmark graphs. Auditor A = fable, auditor B = opus. Engine frozen at
`OperationFlow.lean` SHA c1b128cef511. The four `V2Blind*.lean` files are the
agents' output, copied unchanged.
-/
namespace EpistemicLedger.Cases.V2BlindTestSummary

open EpistemicLedger
open EpistemicLedger.OperationFlow
open EpistemicLedger.Cases

/-- Remove every structure tag from one source node, keeping all operations. -/
def untag {ν σ : Type} [DecidableEq ν] (g : FlowGraph ν σ) (n : ν) : FlowGraph ν σ :=
  { g with sources := g.sources.map (fun s => if s.node = n then { s with carries := [] } else s) }

/-- Verdicts in order: Spacetime 1, Spacetime 2, RePT 1, RePT 2; auditor A then B. -/
def verdicts : List (FlowVerdict × FlowVerdict) :=
  [ (flowVerdict V2BlindA.SpacetimeAgent.claim1, flowVerdict V2BlindB.SpacetimeAgent.claim1),
    (flowVerdict V2BlindA.SpacetimeAgent.claim2, flowVerdict V2BlindB.SpacetimeAgent.claim2),
    (flowVerdict V2BlindA.RePT.claim1, flowVerdict V2BlindB.RePT.claim1),
    (flowVerdict V2BlindA.RePT.claim2, flowVerdict V2BlindB.RePT.claim2) ]

/-- A and B reach the same verdict on all four claims. -/
theorem v2_blind_verdicts :
    verdicts =
      [ (.rejected, .rejected), (.admissible, .admissible),
        (.rejected, .rejected), (.rejected, .rejected) ] := by
  decide

/-- Auditor A's RePT verdict rests on one label: remove the 3D tag from the
frozen backbone, keep every operation, and claim 2 is admissible. -/
theorem auditorA_rept_turns_on_backbone_label :
    flowVerdict { V2BlindA.RePT.claim2 with
      graph := untag V2BlindA.RePT.claim2.graph .dinov2Backbone } = .admissible := by
  decide

/-- Auditor B tagged more inputs: with the backbone's and the training frames'
tags removed, claim 2 is still rejected. -/
theorem auditorB_rept_still_rejected_without_backbone_and_frames :
    flowVerdict { V2BlindB.RePT.claim2 with
      graph := untag (untag V2BlindB.RePT.claim2.graph .dinov2Backbone) .arkitTrainFrames }
      = .rejected := by
  decide

#eval auditFlow { V2BlindB.RePT.claim2 with
  graph := untag (untag V2BlindB.RePT.claim2.graph .dinov2Backbone) .arkitTrainFrames }

end EpistemicLedger.Cases.V2BlindTestSummary
