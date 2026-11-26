# Epistemic ledger — Lean prototype v0

Origin: #papers thread 2026-11-26 (user msgs 27229, 27232, 27235, 27238).

## Question
Can a machine checker reject a paper's headline claim, and accept its narrow
body claim, from a hand-written record of what the paper's derivation used?

## Rules (v0)
1. A claim carries its dependency set.
2. Dropping a dependency needs a forget step with evidence of invariance.
3. A theorem applied to a target needs each hypothesis discharged for that
   target. Unchecked = bet (must be declared). Known false = fail.
4. Each structure is tagged `setByExperimenter` or `measured`. A claim worded
   "arises by itself" may not rest on an experimenter-set structure.

## Layout (Lean 4.34.0, core only, no Mathlib)
| File | Owner | Content |
|---|---|---|
| `EpistemicLedger/ClaimRecordTypes.lean` | claude | record types |
| `EpistemicLedger/AuditRules.lean` | claude | `audit`, `verdict`, 2 general theorems |
| `EpistemicLedger/Cases/BarontiniColdAtomsTime.lean` | claude | case 1 |
| `EpistemicLedger/Cases/BalestrieroLeCunPlatonicJepa.lean` | claude | case 2 |
| `EpistemicLedger/AxiomReport.lean` | claude | `#print axioms` for every result |
| `EpistemicLedger/Cases/Gemini*.lean` | gemini | independent records |
| `EpistemicLedger/Cases/Adversarial*.lean` | codex | records built to fool the audit |

Compile: `lake lean EpistemicLedger.lean` (whole library) or
`lake lean EpistemicLedger/Cases/<File>.lean` (one case).

## Status
- [x] Folder, git init (no commit yet), Lean config
- [x] Record types + 4 rules
- [x] Case 1 and case 2: headline + body claims
- [x] Compiles, exit 0. Axioms: `propext`, `Quot.sound` only
- [x] codex: engine review + adversarial record (`Cases/AdversarialForgetOrder.lean`).
      Found: `forgetEvidence` took the first matching forget step, so
      `[shown, contradicted]` passed with zero findings.
- [x] Fix: a contradiction anywhere wins, then `shown`, then `notShown`.
      New theorem `audit_forget_order_irrelevant`. Codex's two orders kept as
      regression tests (both rejected). Compiles, exit 0.
- [x] codex re-verified the fix on a clean copy (9 jobs succeeded).
- [x] gemini: independent records of the same 2 papers
      (`Cases/GeminiBarontiniColdAtomsTime.lean`,
      `Cases/GeminiBalestrieroLeCunPlatonicJepa.lean`).
- [x] Comparison as checked theorems:
      `Cases/AuditorAgreementClaudeVsGemini.lean`.
- [x] New theorem `audit_findings_survive_more_used`: recording more used
      dependencies never removes a finding.
- [ ] Blind agreement test (auditors who have not seen the chat thread).

## Auditor comparison (claude vs gemini)
| Paper | claude deps | gemini deps | matched, same source | only gemini |
|---|---|---|---|---|
| Barontini | 5 | 8 | 5 | 3: dipole trap; clock + branch choice; fitted mass + pump |
| Balestriero–LeCun | 3 | 7 | 3 | 4: frozen vision targets; fitted linear map; good-view-only tuning; WIT overlap |

- Verdicts agree on all 5 claims.
- Finding counts differ (8 vs 16, 10 vs 15) and are not comparable: one fact
  can be recorded as a dependency or as a hypothesis.
- One status disagreement: "modalities share one positive-pair distribution"
  is `bet` for claude, `knownFalse` for gemini. The paper ("the image side
  mostly uses crops as positives") supports gemini.
- claude's records under-list. The paper itself names the fitted linear map
  as a channel of paired information; claude left it out.
- Not blind: gemini had seen claude's dependency names in chat, so the matched
  part is not evidence of independent agreement.
- Records are kept as first written; nothing was edited to make them agree.

## Result so far
| Claim | Verdict | Findings |
|---|---|---|
| Barontini headline ("using only internal degrees of freedom") | rejected | 8 |
| Barontini body claim (all dependencies declared) | admissible | 0 |
| Balestriero–LeCun headline ("no longer a hypothesis but a theorem") | rejected | 10 |
| Balestriero–LeCun conditional theorem | admissible | 0 |
| Balestriero–LeCun engineering claim | admissible | 0 |

## Tasks for gemini
1. Write your own record of each paper, from the paper, without copying
   claude's dependency lists: `Cases/GeminiBarontiniColdAtomsTime.lean`,
   `Cases/GeminiBalestrieroLeCunPlatonicJepa.lean`. Same types, your own
   `Dep` / `Hyp` enumerations, headline + body claim, `decide` theorems.
2. Do not edit claude's files or the root import file; report file names in
   #papers and claude adds the imports.

## Tasks for codex
1. Review `AuditRules.lean`: is each rule implemented as stated? Any claim
   shape that slips through?
2. Write one adversarial record: a headline that should be rejected by the
   four rules as worded, but that `verdict` accepts.

## Blind agreement test (user GO: msg 27252, 2026-11-26 16:26)

Design
- 6 fresh agents, none has seen the chat thread, the critiques, the existing
  records or this plan. One agent per (auditor, paper).
  Auditor A = model fable, auditor B = model opus.
- Each works in its own folder outside the repo, holding only
  `ClaimRecordTypes.lean`, `AuditRules.lean`, a neutral made-up format example
  (one claim, verdict `admissibleOnDeclaredBets`) and the paper text.
- Claims are fixed verbatim quotes, numbered, not labelled headline/narrow.
- Papers: Barontini (full text); Balestriero–LeCun (full text); Anthropic
  "VP ≠ VNP over every field" (pages 1–8 + repository README) as the control
  whose headline should not be rejected under the four rules.

Fixed claims
| Paper | # | Quote |
|---|---|---|
| Barontini | 1 | "These results establish a controlled experimental setting in which relational-time constructions can be quantitatively tested." |
| Barontini | 2 | "...whether the dynamics of the observed sector can be ordered using only internal degrees of freedom. ...demonstrate that it can robustly order the events in the observed sector..." |
| Balestriero–LeCun | 1 | "This demonstrates that the PRH–with JEPAs–is no longer a hypothesis but a theorem and a tool." |
| Balestriero–LeCun | 2 | Theorem 1 as stated |
| Balestriero–LeCun | 3 | "Good views need 42 times fewer training samples than next-token prediction on the same corpus to reach the same alignment" |
| VP ≠ VNP | 1 | "We prove that every arithmetic circuit that computes the permanent ... Hence VP ≠ VNP over every field." |
| VP ≠ VNP | 2 | "The result was discovered by an internal research Claude model and has been formalized in Lean." |

Expectations, written before launch (claude)
| Claim | Expected |
|---|---|
| Barontini 1 | not rejected |
| Barontini 2 | rejected |
| Balestriero–LeCun 1 | rejected |
| Balestriero–LeCun 2 | not rejected |
| Balestriero–LeCun 3 | no prediction (the sentence names the corpus but not how it was built) |
| VP ≠ VNP 1 | not rejected |
| VP ≠ VNP 2 | not rejected |

Measures
- Wrongful rejection: rejections among Barontini 1, Balestriero–LeCun 2,
  VP ≠ VNP 1, VP ≠ VNP 2.
- Missed rejection: non-rejections among Barontini 2, Balestriero–LeCun 1.
- Agreement: A vs B verdict per claim; dependency lists side by side.

Known weakness of the design
- Expected labels are claude's, not ground truth.
- Auditor A is the same model as claude, so it may share claude's reading
  habits even without the thread.
- What counts as "declared" (the quoted sentence only, or anything the paper
  says) is left to each auditor; the type's docstring is the only guidance.

Result (all 6 agents done 2026-11-26; records copied unchanged to
`Cases/Blind{A,B}*.lean`; table kernel-checked in `Cases/BlindTestSummary.lean`,
theorem `blind_test_result`). Findings per rule as (R1, R2, R3, R4).

| Claim | Expected | Auditor A | Auditor B |
|---|---|---|---|
| Barontini 1 | not rejected | rejected (9,1,4,0) | rejected (13,0,7,0) |
| Barontini 2 | rejected | rejected (1,2,1,7) | rejected (8,0,3,9) |
| Balestriero–LeCun 1 | rejected | rejected (8,0,5,0) | rejected (7,0,5,6) |
| Balestriero–LeCun 2 | not rejected | admissibleOnDeclaredBets | admissible |
| Balestriero–LeCun 3 | no prediction | rejected (5,1,0,0) | rejected (6,0,0,0) |
| VP ≠ VNP 1 | not rejected | rejected (2,0,0,0) | rejected (0,0,1,0) |
| VP ≠ VNP 2 | not rejected | admissibleOnDeclaredBets | rejected (1,0,1,0) |

- Missed rejections: 0 of 4 verdicts.
- Wrongful rejections by claude's labels: 5 of 8 verdicts (Barontini 1 ×2,
  VP ≠ VNP 1 ×2, VP ≠ VNP 2 by B).
- 11 of 14 verdicts are `rejected`. The verdict does not discriminate.
- A vs B: same rejected / not rejected on 6 of 7 claims; same exact verdict
  on 5 of 7.
- Dependencies enumerated (A, B): Barontini 19, 25; Balestriero–LeCun 18, 24;
  VP ≠ VNP 10, 10. Earlier non-blind records: claude 5 and 3, gemini 8 and 7.
- Rule 4 fired on Barontini 2 (A 7, B 9) and Balestriero–LeCun 1 (B 6, A 0)
  and on no other claim (theorem `rule4_fired_only_on_two_claims`). A read
  "no longer a hypothesis but a theorem" as conditional wording, so R4 could
  not fire for A.
- Subagent cost: about 0.89M tokens, no GPU.

What the result means
- The v0 result "the machine rejects the headline and accepts the narrow
  claim" was partly an artefact. claude and gemini wrote their own narrow
  claims with every dependency declared. Given the paper's own modest
  sentence verbatim, both blind auditors rejected it.
- R1 fires on almost any single sentence: 10 of the 11 rejections contain R1
  or R2 findings. Two things are undefined in v0 and each auditor chose for
  itself: whether `declared` means the quoted sentence or the whole paper, and
  how finely to enumerate dependencies (5 → 25 for one paper).
- R4 is the only rule that separated the two criticised claims from the rest.
  Caveat: R4 was derived from these same two papers, so its 3 of 4 hits are
  in-sample. Only its 0 of 10 on the other five claims is out-of-sample.
- R4 depends on the `kind` judgement, where A and B disagreed once.

## v1 and blind round 2 (user GO: msg 27255, 2026-11-26 16:57, "find papers yourself, physics or AI/ML")

v1 changes (engine)
- `verdictV1`: only a rule-4 finding or a known-false hypothesis rejects. All
  other findings are notes. v0 `verdict` kept unchanged.
- Guidance in docstrings: `declared` counts anything the paper states;
  dependencies = what the claimed result is obtained through; forget evidence
  is about the property the claim asserts.

Round-1 records re-scored with v1 (in-sample, v1 was designed after seeing them)
- Rejected by both auditors: Barontini 1, Barontini 2, Balestriero–LeCun 1.
  Passed by both: Balestriero–LeCun 2 and 3, VP ≠ VNP 1 and 2.
- Barontini 1 (the modest sentence) is rejected through a known-false
  hypothesis that both blind auditors recorded on their own (the construction
  needs dS and dφ to keep the same sign; the paper reports places where they
  do not).
- In all 14 records rule 4 fired exactly when the auditor recorded the wording
  as `intrinsic`. So in round 1 the machine part of rule 4 added nothing to
  that one judgement.

Round 2: papers, picked by a fixed rule from arXiv listings (newest first)
- Queries: title contains emergent/emergence/emerge (physics: quant-ph,
  cond-mat.quant-gas, gr-qc with "experiment" in the abstract; ML: cs.LG), and
  neutral queries (physics: title "measurement of"; ML: title "benchmark" or
  "an empirical study").
- Rule: walk each listing in order; skip keyword false positives
  ("Emerging entities", "Emergency", "correlation measures") and PDFs over 25
  pages; take the first 2 from each emergence listing and the first 1 from
  each neutral listing.
- Claims: claim 1 = first abstract sentence saying what the authors do or
  find; claim 2 = last abstract sentence. Picked by script.

| Paper | Type | Pages |
|---|---|---|
| 2611.05479 Fermionic Porter–Thomas statistics and their emergence in random matchgate circuits | physics, emergence listing | 10 |
| 2611.03596 Spacetime Emergence in the Memory of a Learning Agent | physics, emergence listing | 19 |
| 2611.33610 Numerical Studies of Ground State Atomic Parity Violation Measurements in Cesium | physics, neutral listing | 9 |
| 2611.31601 RePT: 3D Geometry Emerges from 2D Relational Pretraining | ML, emergence listing | 16 |
| 2611.27618 Potential emergence in LLM agents: a statistical physics perspective | ML, emergence listing | 21 |
| 2611.34935 Can image generation help visual reasoning? An empirical study | ML, neutral listing | 21 |

Expectations for "rule 4 fired", written before launch from the abstracts only (claude)
| Claim | Expected |
|---|---|
| 2611.03596 claim 1 ("causal structure of spacetime can emerge within the memory of a learning agent") | fires |
| 2611.31601 claim 2 ("3D geometry ... can instead emerge as a structural property of representations") | fires |
| 2611.03596 claim 2, 2611.31601 claim 1 | no prediction |
| the other 8 claims | does not fire |

Measures
- A vs B agreement, per claim, on: rule 4 fired; wording `intrinsic`; v1 verdict.
- Rule 4 fired vs the expectations above.
- Rule 4 on the 4 claims from the two neutral-listing papers (expected 0).
- Whether rule 4 ever differs from the `intrinsic` label.
- Rejections that come only from a known-false hypothesis.

Weaknesses
- No ground truth: expectations are claude's, from abstracts only.
- The user has not judged these six papers.
- The selection rule was written by claude after seeing the listings; the
  25-page limit was fixed after seeing page counts (it was 20, which excluded
  the ML neutral paper at 21 pages).

Round 2 result (all 12 agents done 2026-11-26; records copied unchanged to
`Cases/Round2{A,B}*.lean`; table kernel-checked in
`Cases/BlindRound2Summary.lean`, theorem `blind_round2_result`).
Cell = wording / v1 verdict / rule 4.

| Claim | Rule 4 expected | Auditor A | Auditor B |
|---|---|---|---|
| 2611.03596 spacetime 1 | fires | intrinsic / rejected / fired | intrinsic / rejected / fired |
| 2611.03596 spacetime 2 | no prediction | conditional / passed / no | conditional / passed / no |
| 2611.05479 Porter–Thomas 1 | no | conditional / passed / no | conditional / passed / no |
| 2611.05479 Porter–Thomas 2 | no | conditional / passed / no | conditional / passed / no |
| 2611.33610 cesium 1 (neutral) | no | conditional / passedWithNotes / no | conditional / passed / no |
| 2611.33610 cesium 2 (neutral) | no | conditional / passedWithNotes / no | conditional / passedWithNotes / no |
| 2611.31601 RePT 1 | no prediction | intrinsic / rejected / fired | intrinsic / rejected / fired |
| 2611.31601 RePT 2 | fires | intrinsic / rejected / fired | intrinsic / rejected / fired |
| 2611.27618 LLM agents 1 | no | conditional / passed / no | conditional / passed / no |
| 2611.27618 LLM agents 2 | no | conditional / passed / no | conditional / passed / no |
| 2611.34935 image generation 1 (neutral) | no | conditional / passedWithNotes / no | conditional / passed / no |
| 2611.34935 image generation 2 (neutral) | no | conditional / passedWithNotes / no | conditional / passedWithNotes / no |

- A vs B: same wording label 12/12; same rule 4 12/12; same rejected or not
  12/12; same exact v1 verdict 10/12 (two differ only in notes).
- Rule 4 vs expectation: 10/10 for each auditor. Neutral papers: 0 of 8 verdicts.
- Rejected: 3 of 12 claims (round 1 under v0: 11 of 14 verdicts).
- No claim was rejected through a known-false hypothesis. Both auditors met
  the same two candidates (LLM agents: ideal-optimum assumption; cesium: model
  vs laboratory spectra) and both recorded a bet instead.
- Rule 4 fired exactly when the wording was recorded as intrinsic, in all 24
  records (theorem `rule4_equals_wording_label`), as in all 14 of round 1.
- Forget steps did remove experimenter-set structures (RePT: the same 4 for
  both auditors) but never all of them.
- Subagent cost: about 1.51M tokens, no GPU. Both rounds: about 2.4M.

What round 2 does and does not show
- Shown: two auditors given the same sentence, the same paper and the v1
  guidance reach the same wording label and the same rule-4 result on papers
  the rule was not built from, and v1 does not reject almost everything.
- Not shown: that the rejected claims are ones the user would throw out. No
  ground truth exists for these six papers.
- Not shown: that the Lean checker contributes to the discrimination. In 38 of
  38 blind records the rule-4 result equals the auditor's wording label.
- The 10/10 match with claude's expectations is agreement between readers of
  the same sentences (auditor A is the same model as claude), not validation.
- Both auditors are Anthropic models. Agreement between different model
  families was not tested.
- Rule 4 also fires on structures the claim itself names as its source (RePT:
  the training objective). That finding is close to trivial.

## v2: operation-flow engine (user chose the direction, msg 27262, 17:25)
- gemini: `EpistemicLedger/OperationFlow.lean` (graph of operations, inputs
  tagged with the structure they carry, 4 claim kinds) and
  `Cases/V2FlowBenchmarks.lean` (4 papers + 1 control).
- codex review (msg 27264): 3 accepted cases that should not pass
  (`Cases/AdversarialOperationFlow.lean`): `uniqueRecovery` counts a tag the
  operation itself introduces; `independentConvergence` docstring and code
  disagree on shared untagged sources; `conditionalFlow` accepts an
  operation input that is neither a source nor an output.
- claude review (msg 27265), cases in
  `Cases/V2ReviewUndeclaredLeafAndFailedForget.lean`:
  - The undeclared-input hole also lets an emergence claim pass.
  - A forget step without evidence rejects even when nothing carries the tag.
  - The verdict follows the auditor's `carries` label: same operations, label
    removed from one node, rejected becomes admissible. v1's dependence on
    the `intrinsic` label moved to this label.
  - `partition` behaves exactly like `transform`.
  - Missing theorem: if a path exists, the search finds it.
  - Three benchmark graphs do not match the papers: Balestriero–LeCun (vision
    encoder drawn as trained with the pairing oracle and LLaVA recaptions),
    RePT (RGB-only tracker ablation missing; claim paraphrased), Spacetime
    (external fitting tool declared but not connected).
- State at 17:34: gemini editing the engine (adding a dangling-input
  finding); file did not compile, so v2 is not in the root import. The v0/v1
  library compiles, exit 0.
- Next: engine fix lands → turn claude's gap theorems into regression tests →
  add v2 to root → correct the 3 graphs → mini blind test on Spacetime and
  RePT (2 auditors; measure same tag, same tagged nodes, same verdict, and
  whether the verdict ever differs from "some upstream node is tagged").

## v2 blind test (engine frozen at SHA c1b128cef511, confirmed by codex msg 27273)

State before launch
- gemini closed both open review points (msg 27272): a failed forget counts
  only when the structure reaches it; the 3 benchmark graphs were redrawn.
- All of claude's gap theorems are now regression tests. Whole library
  compiles, exit 0, 34 imports.

Design
- 4 fresh agents: auditors A (fable) and B (opus) × papers 2611.03596
  (Spacetime) and 2611.31601 (RePT). Same two verbatim claims per paper as
  round 2. None has seen the thread, earlier records or gemini's graphs.
- Each has `ClaimRecordTypes.lean`, `OperationFlow.lean`, a made-up format
  example showing one rejected and two admissible claims, and the paper text.
- Each chooses the claim kind, names the structure tag, draws the graph
  (sources with `carries`, operations, forget steps with evidence).

Expectations, written before launch (claude)
| Claim | Expected |
|---|---|
| Spacetime 1 | both choose `emergesWithout`, tag the simulated environment as carrying the causal structure, verdict rejected |
| Spacetime 2 | no prediction |
| RePT 1 and 2 | both choose `emergesWithout` with a 3D-geometry tag; depth and pose tagged and blocked by the RGB-only ablation; verdict not predicted, it turns on whether the backbone, the tracker or the data are tagged as carrying 3D |

Measures
- A vs B per claim: same claim kind; same structure named; same nodes tagged
  as carrying it (matched by hand); same verdict.
- How many records have a tagged upstream node and still pass (blocked by a
  forget step with evidence). If none, the verdict again equals one label.

Weaknesses
- 2 papers, 4 claims, 2 auditors from one model family.
- Matching "same node" across two auditors' graphs is claude's judgement.
- No ground truth.

v2 blind test result (4 agents done 2026-11-26; records copied unchanged to
`Cases/V2Blind{A,B}*.lean`; checked in `Cases/V2BlindTestSummary.lean`).

| Claim | Auditor A | Auditor B |
|---|---|---|
| Spacetime 1 | emergesWithout, causal structure; origin = Minkowski field; rejected | same kind, same structure, same origin; rejected |
| Spacetime 2 | conditionalFlow; admissible | conditionalFlow; admissible |
| RePT 1 | emergesWithout, 3D geometry; origin = frozen DINOv2; rejected | emergesWithout, 3D geometry; origin = training frames; rejected |
| RePT 2 | same as RePT 1; rejected | same as RePT 1; rejected |

- Same claim kind 4/4, same structure named 4/4, same verdict 4/4
  (theorem `v2_blind_verdicts`).
- Spacetime: both tag the same three inputs (Minkowski field, light-cone
  readout rule, quadratic fit form) and record the same single forget step.
- RePT, tagged as carrying 3D geometry:
  - both: depth and pose (blocked by the RGB-only ablation, evidence shown);
    frozen DINOv2 (Table 7 depth probe; never ablated).
  - only B: the RGB training frames, the reconstruction objective (blocked,
    evidence shown), the evaluation scenes.
  - only A: the linear readout fitted on ground truth (blocked, evidence shown).
- A's RePT verdict rests on one label: with DINOv2's tag removed, claim 2 is
  admissible (theorem `auditorA_rept_turns_on_backbone_label`). B's stays
  rejected with DINOv2's and the frames' tags removed, through the evaluation
  scenes (theorem `auditorB_rept_still_rejected_without_backbone_and_frames`).
- Expectations: Spacetime 1 as predicted; RePT kind, structure and the
  blocked depth-and-pose route as predicted; RePT verdict was not predicted.
- Subagent cost: about 0.60M tokens. All three blind tests: about 3.0M.

What the v2 test shows
- The graph does work the flat list could not: in all four RePT records an
  input tagged as carrying the structure is blocked by evidence from the
  paper, so "an input is tagged" no longer equals "rejected".
- It localises: both auditors, independently, leave the frozen DINOv2
  backbone as an unblocked carrier, because the paper never removes it. That
  is a concrete, checkable objection, where v1 listed five structures.
- Still one judgement per node: whether an input "carries" the structure.
  A and B agree on the experimenter-set inputs and differ on measured data.
- Design gap: `emergesWithout` counts measured data that contain the
  structure the same as structure the experimenters put in. B rejects RePT
  partly because multi-view frames of a rigid scene imply 3D. Under that
  reading every "learned X from data that contain X" claim is rejected, which
  is not the user's criterion (rule 4: experimenter-set structure credited to
  the object). The engine records each source's origin but does not use it.
- Not shown: anything about truth. 2 papers, 2 auditors, one model family.

## Proposed next (not started, waiting for user)
- From the v2 blind test (needs a user decision; revised after codex msg 27282):
  - claude's first proposal, "only experimenter-set sources and operations
    count as smuggling; measured data is a note", is too coarse. codex's
    counter-case: measured depth used as a training target is measured data
    and still violates "without 3D prediction targets".
  - Revised proposal: an emergence claim lists the inputs its sentence
    credits. A carrier of the structure is allowed only if it is both
    credited and measured. Any other carrier that reaches the target
    unblocked is smuggling. The route is handled by the graph: depth feeding
    the training loss reaches the model; depth feeding only an evaluation
    metric does not.
  - codex also noted A and B audited different target nodes for RePT 1
    (decoded displacements vs relation tokens). Same claim kind and tag, not
    the same target.
- From round 2:
  - User judges the 3 rejected and 9 passed claims of round 2. That is the
    only available check that rule 4 tracks the user's criterion.
  - Rule 4 should skip structures the claim sentence itself credits.
  - Repeat with auditors from other model families (gemini, codex).
  - Decide whether a Lean checker is worth keeping, given that the wording
    label carries the whole result.
- v1 candidates from the blind test (need a user decision):
  - Stop using "any finding" as the verdict. Report the per-rule profile, and
    decide which rules reject.
  - Fix the scope of `declared` (sentence, or whole paper).
  - Give a stopping rule for what counts as a dependency.
  - Say what a forget step's invariance refers to (barrier height was marked
    `shown` by A and `contradicted` by claude and gemini).
- Blind agreement test: 2 fresh agents that have not seen the thread, given
  only the paper and the record types. Per gemini (msg 27245): include at
  least one narrow, clean paper that should come out `admissible`, to measure
  wrongful rejection as well as missed dependencies.
- Second-auditor effort, by goal (corrected per codex, msg 27247):
  - To find missed dependencies: look at claims that came out `admissible`
    (`audit_findings_survive_more_used`: appending to `used` never removes a
    finding).
  - To find wrongful rejections: check each finding of a `rejected` claim
    against the paper. A wrong `declared` list or a spurious `used` entry can
    flip `rejected` to `admissible`
    (`Cases/RejectionNotRobustToOtherRecordErrors.lean`).
- Rule candidates for v1 (gemini, msg 27245):
  - Access / constructive rule: "exists" without the witness handed over
    (e.g. a bound that holds for m ≥ m₀ with no m₀ given).
  - Branch independence: a claim that two branches "converge independently"
    needs their dependency sets to be disjoint.

## Known limits
- The audit checks a record against itself. It does not check that the record
  is a faithful reading of the paper. A dependency left out of `used` is
  invisible.
- `kind`, `source` and hypothesis statuses are the auditor's judgement.
- "Exists but not reachable" (e.g. a bound with no threshold) has no rule yet.

## Unresolved questions
1. Is rule 4 the user's actual criterion, or one of several?
2. Should an undeclared bet reject a claim, or only downgrade it?
3. How to measure agreement between two auditors' records of one paper?
   Partly answered: a checked correspondence map plus the unmatched remainder
   on each side (done). Still open: a blind run, since this one was not blind.
4. Should the first-written records be merged into one corrected record per
   paper, or kept separate as evidence of auditor variation?
