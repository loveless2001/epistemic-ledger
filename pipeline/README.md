# Epistemic Ledger Automated Audit Pipeline

End-to-end pipeline connecting any document (`.pdf`, `.md`, `.txt`, or `arxiv:<id>`) to the
Lean 4.34.0 `EpistemicLedger.OperationFlow` verifier kernel.

## Stages

1. **Ingest (`pipeline/ingest.py`)** — Extracts text from local `.md`/`.txt`/`.tex`/`.pdf` (via
   `pdftotext`) or fetches `arxiv:<id>`, binding the audit to an exact SHA-256 snapshot.
2. **Schema & Verbatim Quote Grounding (`pipeline/schema.py`)** — Enforces strict JSON schema
   (`epistemic-ledger/v2.1`–`v2.5`), Lean identifier/keyword hygiene, verbatim quote grounding
   (whitespace-normalized / dehyphenated, ≥ 12 non-space chars) on all sources, ops, claims,
   hypotheses, and optional record-level `questions` (`about_quote`, `phrase` inside `about_quote`
   with no minimum length, verbatim `answer_quotes`). Legacy fields (`ask_back`, `hedged`,
   `hedge_quote`, `exclusion_wording_quote`, `excluded_object`) are accepted and silently ignored.
3. **Lean 4 Kernel Verification (`pipeline/lean_runner.py`)** — Automatically ensures
   `EpistemicLedger.OperationFlow` is built and up to date (works on a fresh clean clone),
   then runs two-pass verification:
   - Pass 1 evaluates `epistemicVerdict` and `auditFlow` inside `lake env lean`.
   - Pass 2 synthesizes a standalone `.lean` proof file (with disjoint `Claims`, `Verdicts`,
     and `Findings` sub-namespaces), verifies `by rfl` in the Lean kernel, checks `#print axioms`
     contains only `{propext, Quot.sound}`, and publishes `*_Verified.lean` atomically only
     after all checks succeed.
4. **Report Generation (`pipeline/report.py`)** — Writes `*_report.json` and `*_report.md`,
   keeping Lean structural verdicts (`lean_verification`) strictly separate from record-level
   reader/human questions (`questions`, `verified_by_lean: false`, rendered under claims when
   `claim_id` is given or grouped by `about_quote` under `## Questions`).

> **Scope note:** Verbatim quote checks prove textual existence in the snapshot
> (anti-hallucination); whether a quote semantically justifies a `carries` tag or causal edge
> remains an auditor/human judgment.

## Usage

Run from the repository root (`epistemic-ledger`):

```bash
# 1. Verify a single AuditSpec JSON against a document
python3 -m pipeline.audit_cli run \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --out /tmp/epistemic-run

# 2. Generate a strict extraction prompt for any LLM/agent (works on PDF or arxiv:<id>)
python3 -m pipeline.audit_cli prompt \
  --doc arxiv:2509.07745 \
  --auditor AuditorA \
  --out /tmp/barontini_prompt.txt
```

## Running the Test Suite

```bash
python3 -m unittest discover -s pipeline/tests -v
```
