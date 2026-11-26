# Epistemic Ledger Automated Audit Pipeline

End-to-end pipeline connecting any document (`.pdf`, `.md`, `.txt`, or `arxiv:<id>`) to the
Lean 4.34.0 `EpistemicLedger.OperationFlow` (v2.1 / Policy 3) verifier kernel.

## Stages

1. **Ingest (`pipeline/ingest.py`)** — Extracts text from local `.md`/`.txt`/`.pdf` (via `pdftotext`)
   or fetches `arxiv:<id>`, binding the audit to an exact SHA-256 snapshot.
2. **Schema & Verbatim Quote Grounding (`pipeline/schema.py`)** — Enforces strict JSON schema
   (`epistemic-ledger/v2.1`), Lean identifier/keyword hygiene, and verifies that **every**
   source, operation, and claim quote appears verbatim (whitespace-normalized / dehyphenated,
   ≥ 12 non-space chars) in the ingested document.
3. **Lean 4 Kernel Verification (`pipeline/lean_runner.py`)** — Two-pass compilation against
   `EpistemicLedger.OperationFlow`:
   - Pass 1 evaluates `flowVerdict` and `auditFlow` inside `lake env lean`.
   - Pass 2 synthesizes a standalone `.lean` proof file with `by decide` theorems certifying
     every verdict and finding list, compiles it with the Lean kernel, and verifies `#print axioms`
     contains only `{propext, Quot.sound}` (rejecting `Classical.choice` or `sorryAx`).
4. **Report & Multi-Auditor Reconciliation (`pipeline/report.py`)** — Writes `*_report.json`,
   `*_report.md` (with verbatim evidence quotes), and `comparison.md` / `comparison.json` when
   2+ auditors inspect the same document.

## Usage

Run from the repository root (`projects/epistemic-ledger`):

```bash
# 1. Verify a single AuditSpec JSON against a document
python3 -m pipeline.audit_cli run \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --out /tmp/epistemic-run

# 2. Compare two independent auditors on the same document
python3 -m pipeline.audit_cli compare \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --spec pipeline/examples/sample_framework_auditor_b.json \
  --out /tmp/epistemic-compare

# 3. Generate a strict extraction prompt for any LLM/agent (works on PDF or arxiv:<id>)
python3 -m pipeline.audit_cli prompt \
  --doc arxiv:2509.07745 \
  --auditor AuditorA \
  --out /tmp/barontini_prompt.txt

# 4. One-command end-to-end extraction + Lean verification via any CLI extractor
python3 -m pipeline.audit_cli extract \
  --doc pipeline/examples/sample_framework.md \
  --extractor-cmd "cat pipeline/examples/sample_framework_auditor_a.json" \
  --auditor AutoA \
  --out /tmp/epistemic-extract
```

## Running the Test Suite

```bash
python3 -m unittest discover -s pipeline/tests -v
```
