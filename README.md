# Epistemic Ledger

A **Lean 4.34.0** (core only, zero Mathlib) operation-flow verifier and quote-grounded Python CLI pipeline for auditing epistemological and experimental-design claims in scientific papers.

Every structural verdict is machine-checked by the Lean 4 kernel (`by decide`) using only `{propext, Quot.sound}` — never `Classical.choice`, `sorryAx`, or compiler reduction axioms.

## Epistemic Criteria

Epistemic Ledger is grounded in a recursive meta-cognitive view of knowledge: not a ladder toward certainty, but a discipline that asks at each layer *what conditions allowed the previous layer to stand*, and stops honestly where the evidence stops.

### 1. Four Recursive Layers of Audit

1. **Map edge & the unknown ("where the data stops")** — Never mistake the boundary of current observations, instruments, or models for the boundary of reality. Do not declare *"nothing exists beyond this edge,"* and do not invent conclusions beyond it. When a paper's evidence stops short, record honestly: *here the data stops* (`unestablished`, neither confirmed nor refuted).
2. **Existence vs. access; sensing vs. modeling** — What lies outside a subject's observational slice does not cease to exist. Separate raw signal contact (*sensing / measurement*) from structured interpretation (*modeling / classification*). Do not smuggle experimenter-supplied coordinates, labels, or assumptions into a claim of spontaneous emergence or independent recovery.
3. **Understanding within a slice** — Understanding deepens by comparing models, testing predictions, and separating competing mechanisms across cases. Strong performance inside one experimental slice does not turn that slice into universal reality, and reproducing data using inputs fitted from that same data is not an independent test.
4. **Expression vs. reality** — Language selects, cuts, names, and smooths reality; a polished claim can assert more than the paper actually established. Audit each clause by what it asserts (rather than by rhetoric or hedges), compare it against the paper's own wording elsewhere, and trace whether it rests on earlier claims.

**What the Lean verdict covers vs. reader-recorded evidence:**
- **Lean 4 kernel verdict** covers **layer 2** (supplied structure, excluded-channel leaks, shared upstream/experimenter origin, tag-specific lossy bottlenecks, dependent/self controls, and declared-ledger cost accounting) plus **declaration bookkeeping** (undeclared upstream sources, missing matched control, known-false or undeclared theorem hypotheses, and dangling graph inputs).
- **Layers 1, 3, and 4** (where the data stops beyond the graph, causal separation from alternative explanations, tested slice vs. asserted scope, fitted test inputs, and expression vs. the paper's own wording elsewhere) are **reader-recorded, quote-checked evidence** (`reader_ask_back`, `verified_by_lean: false`), displayed first in reports and never turned into Lean verdicts.

### 2. Operational Criteria for Evaluating Claims

- **Qualitative vs. quantitative scope (`v2.4+`):** Every claim declares its `nature` (`qualitative` or `quantitative`). Quantitative claims are checked structurally only for **order** or **threshold** relations (`quantitative_kind: "order" | "threshold"`). Specific numerical figures (`specificValue`), derived arithmetic ratios (`derivedComparison`), and accounting/bookkeeping disputes are returned as `outOfScope` — the ledger audits epistemic structure, not number-crunching.
- **Whole-document context:** An abstract cannot carry every condition; assumptions, settings, and caveats stated in the paper's body count as declared context (with their document location noted).
- **Verdict and display-state discipline:**
  - `no structural alarm` (Lean enum: `admissible`, `display_state: noStructuralAlarm`) — Zero verdict-bearing structural findings in the modeled graph; never presented as positive support or certification of unmodeled reality.
  - `conditional on N declared, unchecked assumption(s)` (Lean enum: `admissible` with `declared_bet_count ≥ 1`, `display_state: conditional`) — Display refinement of `admissible` when a `theoremApplication` claim rests on one or more declared `.bet` hypotheses; each assumption is listed with its document location.
  - `unestablished` — Data or design stops at the map edge (missing control, unchecked theorem bet, insufficient observational access, undeclared upstream source, unused declared ledger, or ambiguous lossy path — not a proven contradiction).
  - `rejected` — Direct structural contradiction (smuggled/author-supplied structure or unverified/contradicted removal on an emergence claim, excluded-channel leak, shared upstream branch in an independence claim, tag-specific lossy bottleneck with no side-information bypass, known-false theorem precondition, dependent/self control, or trivial/unaccounted declared cost ledger).
  - `outOfScope` — Outside structural operation-flow verification (normative/value judgments, specific numerical figures, derived arithmetic comparisons, or bookkeeping).
- **Quote-grounded ask-back evidence & stop answers (`v2.5`, separate from Lean proofs):** `audit_cli ask` probes each in-scope claim across layers 1, 3, and 4 — **causal separation** (E2: what test rules out a competing mechanism), **own wording** (E3: how the paper states the same point outside the claim sentence), **slice** (E4: tested settings vs. asserted scope), **test inputs** (E5: whether compared outputs rely on fitted inputs), **rests on** (E6: upstream claim dependencies), and **kind anchor** (E7: verbatim exclusion wording for emergence claims). Reports lead with the reader's **stop answers** (E2 `not_found`, E3 `sentence_stronger`, E4 `beyond`, E5 `fitted_on_test_data`, plus E6 upstream claim display states), clearly labeled *"reader-recorded, quote-checked, not Lean-verified"* under `reader_ask_back` (`verified_by_lean: false`), keeping human-readable evidence strictly distinct from Lean's `kernel_verified` structural verdict.
- **Boundary of formal verification:** Lean 4 verifies only the structural graph verdict over the formalized model. Semantic interpretation of quotes, causal adequacy, and final judgment on overclaiming vs. under-support remain explicitly visible to human reviewers rather than hidden inside a black-box score.

## What It Checks

A paper's methodology is encoded as a directed graph of `SourceNode`s (`measured` vs `setByExperimenter`, carrying typed structural tags) and typed `Op`s (`transform`, `partition`, `lossy`, `forget tag evidence`).

| Claim Kind | What Lean Verifies |
|---|---|
| `emergesWithout` | Target does not receive `tag` along any unblocked path; any `.forget` with `notShown` or `contradicted` on path is `rejected`. |
| `emergesWithExclusion` | **Policy 3:** checks both Alarm 1 (`excludedChannelLeak` into the explicitly excluded channel) and Alarm 2 (`authorSuppliedStructure` from any unforgotten `setByExperimenter` source or op into `target`); `.forget` with `notShown` or `contradicted` on path is `rejected`. |
| `independentConvergence` | Two allegedly independent branches share neither an upstream `tag`-carrying node nor an unforgotten `setByExperimenter` source. |
| `uniqueRecovery` | Verifies a confirmed lossless path from a `SourceNode` carrying `tag` to `target`: rejects only when a single complete **tag-specific** `.lossyOn` (`loses: [tag]`) bottleneck with no co-input/ancestor side-information bypass cuts all `tag`-carrying paths (`lossyChannelOnPath`), and marks `unestablished` for side-information bypass like `(s XOR r, r)` (`lossyWithSideInformation`), untargeted `.lossy` (`untargetedLossyChannel`), parallel lossy branches like `(n div 2, n mod 2)` (`parallelLossyBranches`), missing access (`unaccessedTargetStructure`), or `.forget tag .notShown`. |
| `conditionalFlow` | Every upstream source reaching `target` is explicitly declared in `declaredSources`. |
| `effectivenessClaim` | Structural comparison checks only (no number parsing): independent control arm (`missingMatchedControl`, `trivialSelfControl`, `dependentControlArm`, `unusedControlNode`, `unusedMethodNode`) and, when a cost ledger is declared, direct forget-proof physical cost-source coverage (`trivialCostLedger`, `unusedCostLedger`, `unaccountedCostSource`). Absence of cost accounting (`missingCostAccounting`) is recorded as a note (`no cost accounting recorded; not counted`) and does not move the verdict. Quantitative `order`/`threshold` claims use this structural check; `specificValue`/`derivedComparison` route to `outOfScope`. |
| `theoremApplication` | **Rule 3:** checks each precondition (`discharged` / `bet` / `knownFalse`) of a theorem applied at `target`: `.knownFalse` is always `rejected` (`hypothesisKnownFalse`), unchecked `.bet` omitted from `declared_bets` is `unestablished` (`undeclaredHypothesisBet`), `.discharged` only is `no structural alarm` (`admissible`), and declared `.bet`(s) with no other findings display as `conditional on N declared, unchecked assumption(s)` (`admissible` / `display_state: conditional`). |
| `outOfScope` | Explicitly records a claim outside structural operation-flow verification (e.g., normative legal balancing, value judgments, specific numeric figures, derived arithmetic comparisons, or financial bookkeeping) with a mandatory `reason` string. |

Every structural claim also checks graph completeness (`danglingInput`).

## Four-State Epistemic Verdict (`EpistemicVerdict`) & Display States

`epistemicVerdict` (preserving legacy 2-state `flowVerdict` untouched for historical proofs) classifies every claim into four kernel-checked Lean states; reports refine `admissible` into two display states (`noStructuralAlarm` vs. `conditional`) without altering the Lean enum:

| Display State (Lean Enum) | Meaning |
|---|---|
| `no structural alarm` (`admissible`, `declared_bet_count = 0`) | **Zero verdict-bearing structural findings** in the modeled graph (never certifies unmodeled reality; absence of cost accounting is shown as a note, not counted). |
| `conditional on N declared, unchecked assumption(s)` (`admissible`, `declared_bet_count ≥ 1`) | **Display refinement of `admissible`** — zero structural alarms, but the applied theorem explicitly depends on `N` declared `.bet` hypothesis assumption(s), each listed with its document location. |
| `unestablished` (`unestablished`) | **Data/design stops at the map edge** — missing matched control, unused declared cost ledger, unchecked theorem bet, `.notShown` forget on a `uniqueRecovery` path, missing observational access (`unaccessedTargetStructure`), undeclared upstream source, or dangling graph input (not a proven structural contradiction). |
| `rejected` (`rejected`) | **Direct structural/empirical contradiction** — confirmed smuggled/author-supplied structure (bypass, `.notShown` or `.contradicted` forget on emergence), excluded-channel leak, shared upstream/experimenter branch, tag-specific lossy bottleneck on a `tag`-carrying path, known-false theorem hypothesis, dependent/self control, or trivial/unaccounted declared cost ledger. |
| `outOfScope` (`outOfScope`) | **Outside structural operation-flow scope** — normative, legal-policy, specific-number / derived-comparison, or bookkeeping dispute explicitly marked via `kind: "outOfScope"`. |

## Out of Scope (Explicitly Reported in Every Output)

- **Semantic quote interpretation:** Verbatim quote grounding proves textual existence in the ingested SHA-256 snapshot (anti-hallucination). Whether a quote semantically justifies a `carries` tag, causal edge, or statistical test requires auditor/human review.
- **Specific numbers & bookkeeping:** Exact numerical figures (`specificValue`), derived arithmetic ratios (`derivedComparison`), invoice reconciliation, billing-period completeness, and cross-document deduplication are intentionally out of scope; known legacy accounting keys (`reconciliations`, `arm`, `receipt`, `charge_event`, `quantity_kind`) are ignored during structural Lean verification and reported explicitly under `## Out of Scope`.
- **Unmodeled joint source-support constraints:** In `uniqueRecovery`, `lossyChannelOnPath` certifies non-recoverability assuming distinct disconnected `SourceNode`s can vary independently (so colliding inputs of the bottleneck op remain jointly valid while holding outside observations fixed). When two inputs are coupled (e.g., `c = r`), derive both from a shared upstream `SourceNode` (yielding `lossyWithSideInformation` / `unestablished`) or omit `loses` (yielding `untargetedLossyChannel` / `unestablished`).
- **PDF mathematical typography:** `pdftotext` can drop superscripts/subscripts in formulas; verbatim quote grounding verifies fidelity to the extracted snapshot and every PDF report warns about this under `## Out of Scope`. For formula-heavy math papers, pass the `.tex` source directly (ingested as UTF-8 without `pdftotext`).

## Quick Start

### 1. Build Lean 4 proofs & soundness theorems

```bash
lake build
```

### 2. Run the pipeline & frozen blind-record regression test suite (27 tests, 46 frozen public claims)

```bash
python3 -m unittest discover -s pipeline/tests -v
```

### 3. Audit a document, run the ask-back check, or compare independent auditors

```bash
# Single audit (supports .pdf via pdftotext, .md, .txt, or arxiv:<id>)
python3 -m pipeline.audit_cli run \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --out /tmp/epistemic-run

# Check unanswered v2.5 reader ask-back questions (exits 4 if incomplete, 0 if complete or legacy v2.1-v2.4)
python3 -m pipeline.audit_cli ask \
  --doc pipeline/examples/sample_framework.md \
  --spec /path/to/spec_v25.json

# Multi-auditor quote-anchored comparison
python3 -m pipeline.audit_cli compare \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --spec pipeline/examples/sample_framework_auditor_b.json \
  --out /tmp/epistemic-compare
```

See [pipeline/README.md](pipeline/README.md) for full CLI options (`run`, `ask`, `compare`, `prompt`, `extract`).

## Repository Layout

- `EpistemicLedger/OperationFlow.lean` — Core operation-graph verifier, Policy 3, Tier-2 experimental `effectivenessClaim`, and constructive soundness theorems (axioms `{propext, Quot.sound}` only).
- `EpistemicLedger/Cases/` — Operation-flow blind-test archives, adversarial test suites, and benchmark proofs.
- `pipeline/` — Zero-dependency Python 3 stdlib CLI (`ingest.py`, `schema.py`, `lean_runner.py`, `report.py`, `audit_cli.py`) + unit tests (`pipeline/tests/test_pipeline.py`).
- `pipeline/examples/` — Committed audit specs including real-paper examples (`society_ai_scientists_v21_5claims.json`, `society_ai_scientists_v23.json`, `papadopetraki_2025_v23.json`).
