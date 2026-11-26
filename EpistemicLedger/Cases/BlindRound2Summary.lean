import EpistemicLedger.Cases.Round2ASpacetimeAgent
import EpistemicLedger.Cases.Round2APorterThomas
import EpistemicLedger.Cases.Round2ACesiumParity
import EpistemicLedger.Cases.Round2ARePT
import EpistemicLedger.Cases.Round2AAgentStates
import EpistemicLedger.Cases.Round2AImageGenReasoning
import EpistemicLedger.Cases.Round2BSpacetimeAgent
import EpistemicLedger.Cases.Round2BPorterThomas
import EpistemicLedger.Cases.Round2BCesiumParity
import EpistemicLedger.Cases.Round2BRePT
import EpistemicLedger.Cases.Round2BAgentStates
import EpistemicLedger.Cases.Round2BImageGenReasoning

/-
Blind round 2, 2026-11-26. Twelve records written by fresh agents that had not
seen the chat thread or any earlier record, on six arXiv papers that rule 4
was not derived from. Auditor A = fable, auditor B = opus. The twelve
`Round2*.lean` files are the agents' output, copied unchanged.

This file only tabulates, per claim and auditor:
(wording recorded as intrinsic?, v1 verdict, rule 4 fired?).
-/
namespace EpistemicLedger.Cases.BlindRound2Summary

open EpistemicLedger.Cases

abbrev Cell := Bool × VerdictV1 × Bool

def cell {ι η : Type} [DecidableEq ι] [DecidableEq η] (c : Claim ι η) : Cell :=
  (decide (c.kind = .intrinsic), verdictV1 c, rule4Fired c)

/-- Rows in order: SpacetimeAgent 1, 2; PorterThomas 1, 2; CesiumParity 1, 2;
RePT 1, 2; AgentStates 1, 2; ImageGenReasoning 1, 2. Each row: auditor A, auditor B. -/
def table : List (Cell × Cell) :=
  [ (cell Round2A.SpacetimeAgent.claim1, cell Round2B.SpacetimeAgent.claim1),
    (cell Round2A.SpacetimeAgent.claim2, cell Round2B.SpacetimeAgent.claim2),
    (cell Round2A.PorterThomas.claim1, cell Round2B.PorterThomas.claim1),
    (cell Round2A.PorterThomas.claim2, cell Round2B.PorterThomas.claim2),
    (cell Round2A.CesiumParity.claim1, cell Round2B.CesiumParity.claim1),
    (cell Round2A.CesiumParity.claim2, cell Round2B.CesiumParity.claim2),
    (cell Round2A.RePT.claim1, cell Round2B.RePT.claim1),
    (cell Round2A.RePT.claim2, cell Round2B.RePT.claim2),
    (cell Round2A.AgentStates.claim1, cell Round2B.AgentStates.claim1),
    (cell Round2A.AgentStates.claim2, cell Round2B.AgentStates.claim2),
    (cell Round2A.ImageGenReasoning.claim1, cell Round2B.ImageGenReasoning.claim1),
    (cell Round2A.ImageGenReasoning.claim2, cell Round2B.ImageGenReasoning.claim2) ]

#eval table

set_option maxRecDepth 20000 in
/-- The whole result of blind round 2, kernel-checked. Each cell:
(wording recorded as intrinsic?, v1 verdict, rule 4 fired?); auditor A then B. -/
theorem blind_round2_result :
    table =
      [ ((true, .rejected, true), (true, .rejected, true)),
        ((false, .passed, false), (false, .passed, false)),
        ((false, .passed, false), (false, .passed, false)),
        ((false, .passed, false), (false, .passed, false)),
        ((false, .passedWithNotes, false), (false, .passed, false)),
        ((false, .passedWithNotes, false), (false, .passedWithNotes, false)),
        ((true, .rejected, true), (true, .rejected, true)),
        ((true, .rejected, true), (true, .rejected, true)),
        ((false, .passed, false), (false, .passed, false)),
        ((false, .passed, false), (false, .passed, false)),
        ((false, .passedWithNotes, false), (false, .passed, false)),
        ((false, .passedWithNotes, false), (false, .passedWithNotes, false)) ] := by
  decide

/-- A and B agree on the wording label and on rule 4 for all 12 claims. -/
theorem auditors_agree_on_wording_and_rule4 :
    table.all (fun r => r.1.1 == r.2.1 && r.1.2.2 == r.2.2.2) = true := by
  rw [blind_round2_result]
  decide

/-- In all 24 records rule 4 fired exactly when the wording was recorded as intrinsic. -/
theorem rule4_equals_wording_label :
    table.all (fun r => r.1.1 == r.1.2.2 && r.2.1 == r.2.2.2) = true := by
  rw [blind_round2_result]
  decide

end EpistemicLedger.Cases.BlindRound2Summary
