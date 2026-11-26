# Epistemic Ledger

A **Lean 4.34.0** (core only, zero Mathlib) operation-flow verifier and quote-grounded Python CLI pipeline for auditing epistemological and experimental-design claims in scientific papers.

Every claim verdict is machine-checked by the Lean 4 kernel (`by decide`) using only `{propext, Quot.sound}` — never `Classical.choice`, `sorryAx`, or compiler reduction axioms.

## What It Checks

A paper's methodology is encoded as a directed graph of `SourceNode`s (`measured` vs `setByExperimenter`, carrying typed structural tags) and typed `Op`s (`transform`, `partition`, `lossy`, `forget tag evidence`).

| Claim Kind | What Lean Verifies |
|---|---|
| `emergesWithout` | Target does not receive `tag` along any unblocked path; no failed `.forget` (`notShown`/`contradicted`) sits on path. |
| `emergesWithExclusion` | **Policy 3:** checks both Alarm 1 (`excludedChannelLeak` into the explicitly excluded channel) and Alarm 2 (`authorSuppliedStructure` from any unforgotten `setByExperimenter` source or op into `target`). |
| `independentConvergence` | Two allegedly independent branches share neither an upstream `tag`-carrying node nor an unforgotten `setByExperimenter` source. |
| `uniqueRecovery` | Verifies a confirmed lossless path from a `SourceNode` carrying `tag` to `target`: rejects only when a single complete **tag-specific** `.lossyOn` (`loses: [tag]`) bottleneck with no co-input/ancestor side-information bypass cuts all `tag`-carrying paths (`lossyChannelOnPath`), and marks `unestablished` for side-information bypass like `(s XOR r, r)` (`lossyWithSideInformation`), untargeted `.lossy` (`untargetedLossyChannel`), parallel lossy branches like `(n div 2, n mod 2)` (`parallelLossyBranches`), missing access (`unaccessedTargetStructure`), or `.forget tag .notShown`. |
| `conditionalFlow` | Every upstream source reaching `target` is explicitly declared in `declaredSources`. |
| `effectivenessClaim` | Independent control arm (`missingMatchedControl`, `trivialSelfControl`, `dependentControlArm`), direct forget-proof physical cost-source coverage (`missingCostAccounting`, `trivialCostLedger`, `unusedCostLedger`, `unaccountedCostSource`), and arithmetic parity of declared `(source, unit, amount)` usage entries (`unquantifiedBudget`, `unboundUsageSource`, `unmatchedControlBudget`). |
| `theoremApplication` | **Rule 3:** checks each precondition (`discharged` / `bet` / `knownFalse`) of a theorem applied at `target`: `.knownFalse` is always `rejected` (`hypothesisKnownFalse`), unchecked `.bet` omitted from `declared_bets` is `unestablished` (`undeclaredHypothesisBet`), and `.discharged` or declared `.bet` is `admissible`. |
| `outOfScope` | Explicitly records a claim outside structural operation-flow verification (e.g., normative legal balancing, value judgments, or financial bookkeeping) with a mandatory `reason` string. |

Every structural claim also checks graph completeness (`danglingInput`).

## Four-State Epistemic Verdict (`EpistemicVerdict`)

`epistemicVerdict` (preserving legacy 2-state `flowVerdict` untouched for historical proofs) classifies every claim into four kernel-checked states:

| Verdict | Meaning |
|---|---|
| `admissible` | **Consistent within declared slice** — zero structural findings in the modeled graph (never certifies unmodeled reality). |
| `unestablished` | **Data/design stops at the map edge** — missing control, missing cost ledger, unquantified budget, `.notShown` forget on the sole path, missing observational access (`unaccessedTargetStructure`), undeclared upstream source, or dangling graph input (not a proven structural contradiction). |
| `rejected` | **Direct structural/empirical contradiction** — confirmed smuggled/author-supplied structure (bypass or `.contradicted` forget), excluded-channel leak, shared upstream/experimenter branch, lossy channel on a `tag`-carrying path, dependent/self control, unaccounted cost source, or unmatched numeric budgets. |
| `outOfScope` | **Outside structural operation-flow scope** — normative, legal-policy, or bookkeeping dispute explicitly marked via `kind: "outOfScope"`. |

## Out of Scope (Explicitly Reported in Every Output)

- **Semantic quote interpretation:** Verbatim quote grounding proves textual existence in the ingested SHA-256 snapshot (anti-hallucination). Whether a quote semantically justifies a `carries` tag, causal edge, or statistical test requires auditor/human review.
- **Accounting / bookkeeping verification:** Invoice reconciliation, billing-period completeness, actual-vs-requested prose semantics, and cross-document deduplication are intentionally out of scope; known legacy accounting keys (`reconciliations`, `arm`, `receipt`, `charge_event`, `quantity_kind`) are ignored during structural Lean verification and reported explicitly under `## Out of Scope`.
- **Unmodeled joint source-support constraints:** In `uniqueRecovery`, `lossyChannelOnPath` certifies non-recoverability assuming distinct disconnected `SourceNode`s can vary independently (so colliding inputs of the bottleneck op remain jointly valid while holding outside observations fixed). When two inputs are coupled (e.g., `c = r`), derive both from a shared upstream `SourceNode` (yielding `lossyWithSideInformation` / `unestablished`) or omit `loses` (yielding `untargetedLossyChannel` / `unestablished`).

## Quick Start

### 1. Build Lean 4 proofs & soundness theorems (42 jobs)

```bash
lake build
```

### 2. Run the pipeline test suite (24 tests)

```bash
python3 -m unittest discover -s pipeline/tests -v
```

### 3. Audit a document or compare independent auditors

```bash
# Single audit (supports .pdf via pdftotext, .md, .txt, or arxiv:<id>)
python3 -m pipeline.audit_cli run \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --out /tmp/epistemic-run

# Multi-auditor quote-anchored comparison
python3 -m pipeline.audit_cli compare \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --spec pipeline/examples/sample_framework_auditor_b.json \
  --out /tmp/epistemic-compare
```

See [pipeline/README.md](pipeline/README.md) for full CLI options (`run`, `compare`, `prompt`, `extract`).

## Repository Layout

- `EpistemicLedger/OperationFlow.lean` — Core operation-graph verifier, Policy 3, Tier-2 experimental `effectivenessClaim`, and constructive soundness theorems (axioms `{propext, Quot.sound}` only).
- `EpistemicLedger/AuditRules.lean` — Historical v0/v1 flat-record audit rules (R1–R4).
- `EpistemicLedger/Cases/` — Blind-test archives (Rounds 1–3), adversarial test suites, and benchmark proofs.
- `pipeline/` — Zero-dependency Python 3 stdlib CLI (`ingest.py`, `schema.py`, `lean_runner.py`, `report.py`, `audit_cli.py`) + unit tests (`pipeline/tests/test_pipeline.py`).
- `pipeline/examples/` — Committed audit specs including real-paper examples (`society_ai_scientists_v21_5claims.json`, `society_ai_scientists_v23.json`, `papadopetraki_2025_v23.json`).
