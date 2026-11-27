# Epistemic Ledger

A **Lean 4.34.0** (core only, zero Mathlib) operation-flow verifier and quote-grounded Python CLI pipeline for auditing epistemological and experimental-design claims in scientific papers.

Every structural verdict is machine-checked by the Lean 4 kernel (`by decide` / `by rfl`) using only `{propext, Quot.sound}` — never `Classical.choice`, `sorryAx`, or compiler reduction axioms.

## Epistemic Criteria

Epistemic Ledger is grounded in a recursive meta-cognitive view of knowledge: not a ladder toward certainty, but a discipline that asks at each layer *what conditions allowed the previous layer to stand*, and stops honestly where the evidence stops.

### 1. Four Recursive Layers of Audit

1. **Map edge & the unknown ("where the data stops")** — Never mistake the boundary of current observations, instruments, or models for the boundary of reality. When a paper's evidence stops short, record honestly: *here the data stops* (`unestablished`, neither confirmed nor refuted).
2. **Existence vs. access; sensing vs. modeling** — Separate raw signal contact (*sensing / measurement*) from structured interpretation (*modeling / classification*). Do not smuggle experimenter-supplied coordinates, labels, or assumptions into a claim of spontaneous emergence or independent recovery.
3. **Understanding within a slice** — Strong performance inside one experimental slice does not turn that slice into universal reality, and reproducing data using inputs fitted from that same data is not an independent test.
4. **Expression vs. reality** — Audit each clause by what it asserts rather than by rhetoric or hedging phrases, and record open questions against the exact wording in the document.

**What the Lean verdict covers vs. reader/human questions:**
- **Lean 4 kernel verdict** covers **layer 2** (supplied structure, excluded-channel leaks, shared upstream/experimenter origin, lossy recovery paths, dependent/self controls, and declared-ledger cost accounting) plus **declaration bookkeeping** (undeclared upstream sources, missing matched control, known-false or undeclared theorem hypotheses, and dangling graph inputs).
- **Questions and quote-checked answers (`questions` slot, `verified_by_lean: false`)** let a reader or human point at any phrase in any sentence of the document, ask a question, and record verbatim quote-checked answers, what stays open (`partly`), or where they searched (`not_in_document`) — with zero Lean verdict effect.

### 2. Operational Criteria for Evaluating Claims

- **Qualitative vs. quantitative scope (`v2.4+`):** Every claim declares its `nature` (`qualitative` or `quantitative`). Quantitative claims are checked structurally only for **order** or **threshold** relations (`quantitative_kind: "order" | "threshold"`). Specific numerical figures (`specificValue`), derived arithmetic ratios (`derivedComparison`), and accounting/bookkeeping disputes are returned as `outOfScope`.
- **Whole-document context:** Assumptions, settings, and caveats stated in the paper's body count as declared context (with their document location noted).
- **Verdict and display-state discipline:**
  - `no structural alarm` (Lean enum: `admissible`, `display_state: noStructuralAlarm`) — Zero structural findings in the modeled graph; never presented as positive support or certification of unmodeled reality.
  - `conditional on N declared, unchecked assumption(s)` (Lean enum: `admissible` with `declared_bet_count ≥ 1`, `display_state: conditional`) — Display refinement of `admissible` when a `theoremApplication` claim rests on one or more declared `.bet` hypotheses; each assumption is listed with its document location.
  - `unestablished` — Data or design stops at the map edge (missing control, unchecked theorem bet, lossy channel on recovery path, insufficient observational access, undeclared upstream source, unused declared ledger, or dangling graph input — not a proven contradiction).
  - `rejected` — Direct structural contradiction (smuggled/author-supplied structure or unverified/contradicted removal on an emergence claim, excluded-channel leak, shared upstream/experimenter branch in an independence claim, known-false theorem precondition, dependent/self control, or trivial/unaccounted declared cost ledger).
  - `outOfScope` — Outside structural operation-flow verification (normative/value judgments, specific numerical figures, derived arithmetic comparisons, or bookkeeping).
- **Record-level `questions` slot (separate from Lean proofs):** Optional top-level `questions` array with `about_quote` (verbatim document quote), `phrase` (verbatim words inside `about_quote`, no minimum length), `question`, `asked_by` (`reader` | `human`), `status` (`answered` | `partly` | `not_in_document`), verbatim `answer_quotes` (≥ 1 for `answered`/`partly`, empty/omitted for `not_in_document`), `answer`, `stays_open` (required for `partly`), `searched` (required for `not_in_document`), and optional `claim_id`. Rendered under the claim when `claim_id` is given or grouped by `about_quote` under `## Questions`, stored in JSON under `questions` (`verified_by_lean: false`), with no verdict effect. Legacy v2.x fields (`ask_back`, `hedged`, `hedge_quote`, `exclusion_wording_quote`, `excluded_object`) are silently ignored so older records still run.

## What It Checks

A paper's methodology is encoded as a directed graph of `SourceNode`s (`measured` vs `setByExperimenter`, carrying typed structural tags) and typed `Op`s (`transform`, `partition`, `lossy` with optional `loses`, `forget tag evidence`).

| Claim Kind | What Lean Verifies |
|---|---|
| `emergesWithout` | Target does not receive `tag` along any unblocked path; any `.forget` with `notShown` or `contradicted` on path is `rejected`. |
| `emergesWithExclusion` | **Policy 3:** checks both Alarm 1 (`excludedChannelLeak` into the explicitly excluded channel) and Alarm 2 (`authorSuppliedStructure` from any unforgotten `setByExperimenter` source or op into `target`); `.forget` with `notShown` or `contradicted` on path is `rejected`. |
| `independentConvergence` | Two allegedly independent branches share neither an upstream `tag`-carrying node nor an unforgotten `setByExperimenter` source. |
| `uniqueRecovery` | Verifies a confirmed lossless path from a `SourceNode` carrying `tag` to `target`: marks `unestablished` if every `tag`-carrying path crosses a lossy op affecting `tag` (`lossyChannelOnPath`, respecting tag-specific `loses`), if no upstream `SourceNode` carries `tag` (`unaccessedTargetStructure`), or if the sole path crosses `.forget tag .notShown`. |
| `conditionalFlow` | Checks declared upstream sources in the modeled graph only: every upstream source reaching `target` is explicitly listed in `declaredSources`. |
| `effectivenessClaim` | Structural comparison checks only (no number parsing): independent control arm (`missingMatchedControl`, `trivialSelfControl`, `dependentControlArm`, `unusedControlNode`, `unusedMethodNode`) and, when a cost ledger is declared, direct forget-proof physical cost-source coverage (`trivialCostLedger`, `unusedCostLedger`, `unaccountedCostSource`). Quantitative `order`/`threshold` claims use this structural check; `specificValue`/`derivedComparison` route to `outOfScope`. |
| `theoremApplication` | **Rule 3:** checks each precondition (`discharged` / `bet` / `knownFalse`) of a theorem applied at `target`: `.knownFalse` is always `rejected` (`hypothesisKnownFalse`), unchecked `.bet` omitted from `declared_bets` is `unestablished` (`undeclaredHypothesisBet`), `.discharged` only is `no structural alarm` (`admissible`), and declared `.bet`(s) with no other findings display as `conditional on N declared, unchecked assumption(s)` (`admissible` / `display_state: conditional`). |
| `outOfScope` | Explicitly records a claim outside structural operation-flow verification with a mandatory `reason` string. |

Every structural claim also checks graph completeness (`danglingInput`).

## Out of Scope (Explicitly Reported in Every Output)

- **Semantic quote interpretation:** Verbatim quote grounding proves textual existence in the ingested SHA-256 snapshot (anti-hallucination). Whether a quote semantically justifies a `carries` tag, causal edge, or statistical test requires auditor/human review.
- **Specific numbers & bookkeeping:** Exact numerical figures (`specificValue`), derived arithmetic ratios (`derivedComparison`), and invoice/billing reconciliation are out of scope; legacy accounting keys (`reconciliations`, `method_usage`, `control_usage`) are ignored during structural Lean verification and reported under `## Out of Scope`.
- **Joint invertibility across lossy channels:** Pure DAG topology cannot decide algebraic joint invertibility or side-information recovery; `uniqueRecovery` reports `lossyChannelOnPath` (`unestablished`) whenever every path carrying `tag` crosses a lossy operation affecting `tag`.
- **PDF mathematical typography:** `pdftotext` can drop superscripts/subscripts in formulas; for formula-heavy math papers, pass the `.tex` source directly.

## Quick Start

### 1. Build Lean 4 proofs & soundness theorems (14 jobs)

```bash
lake build
```

### 2. Run the pipeline & frozen blind-record regression test suite (21 tests, 46 frozen public claims)

```bash
python3 -m unittest discover -s pipeline/tests -v
```

### 3. Audit a document or generate an extraction prompt

```bash
# Single audit (supports .pdf via pdftotext, .md, .txt, or arxiv:<id>)
python3 -m pipeline.audit_cli run \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --out /tmp/epistemic-run

# Generate a strict extraction prompt for any LLM/agent
python3 -m pipeline.audit_cli prompt \
  --doc arxiv:2509.07745 \
  --auditor AuditorA \
  --out /tmp/barontini_prompt.txt
```

See [pipeline/README.md](pipeline/README.md) for CLI details (`run`, `prompt`).

## Repository Layout

- `EpistemicLedger/OperationFlow.lean` — Core operation-graph verifier, `epistemicVerdict`, Policy 3, structural `effectivenessClaim`, `theoremApplication`, and constructive soundness theorems (axioms `{propext, Quot.sound}` only).
- `EpistemicLedger/AxiomReport.lean` — Build-time `#print axioms` check over all core soundness theorems.
- `EpistemicLedger/Cases/` — Operation-flow blind-test archives, adversarial regression suites, and benchmark proofs.
- `pipeline/` — Zero-dependency Python 3 stdlib CLI (`ingest.py`, `schema.py`, `lean_runner.py`, `report.py`, `audit_cli.py`) + unit and frozen blind-regression tests (`pipeline/tests/`).
- `pipeline/examples/` — Committed audit specs including real-paper examples (`society_ai_scientists_v21_5claims.json`, `society_ai_scientists_v23.json`, `papadopetraki_2025_v23.json`).
