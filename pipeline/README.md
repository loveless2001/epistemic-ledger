# Epistemic Ledger Automated Audit Pipeline

End-to-end two-stage pipeline (**Pre -> Gate -> Post**) connecting any document (`.pdf`, `.md`, `.txt`, `.tex`, or `arxiv:<id>`) to optional NMF + IPOD pre-formalization exploration and the Lean 4.34.0 `EpistemicLedger.OperationFlow` verifier kernel.

## Stages

### Stage 0 — Shared Ingest (`pipeline/ingest.py`)
Extracts text from local `.md`/`.txt`/`.tex`/`.pdf` (via `pdftotext`) or fetches `arxiv:<id>`, binding both Pre and Post to the exact same SHA-256 snapshot.

### Stage 1 — Pre-Formalization & Pre-Gate (`pipeline/preform.py`, optional)
- **`pre-prompt`:** emits a bidirectional NMF + IPOD exploration & Pre-Gate prompt (the concept graph is an optional tool, never mandatory policy or ground truth).
- **`pre`:** runs deterministic graph probing (`untouched_frontier`, `FRAME_SHIFT_LOSS` on `measures` edges), validates verbatim quotes, NMF+IPOD `proposed_new_nodes`, `challenged_graph_items` pushbacks, and executes the **Pre-Gate**:
  - `stop_at_pre`: purges any stale Post handoff files in `--out`, writes `pre_gate_report.md`, and stops before Lean/Post.
  - `proceed_to_post`: also writes `post_brief.md` + `questions_seed.json` (matching `pipeline/schema.py`'s `questions` contract).

### Stage 2 — Post-Formalization & Lean 4 Verification
1. **Schema & Verbatim Quote Grounding (`pipeline/schema.py`)** — Enforces strict JSON schema
   (`epistemic-ledger/v2.1`–`v2.5`), Lean identifier/keyword hygiene, verbatim quote grounding
   (whitespace-normalized / dehyphenated, ≥ 12 non-space chars) on all sources, ops, claims,
   hypotheses, and optional record-level `questions` (`about_quote`, `phrase` inside `about_quote`
   with no minimum length, verbatim `answer_quotes`). Legacy fields (`ask_back`, `hedged`,
   `hedge_quote`, `exclusion_wording_quote`, `excluded_object`) are accepted and silently ignored.
2. **Pre-Gate Guard (`--pre-gate` on `run`, optional)** — If passed, refuses to run Post/Lean (exit 3) unless `explore.json` matches the `--doc` SHA-256 and cleared `proceed_to_post`.
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
# Stage 1 (Pre): emit Pre-formalization prompt and run Pre-Gate handoff
python3 -m pipeline.audit_cli pre-prompt --doc <doc> --graph concept-graph.json --out /tmp/pre_prompt.txt
python3 -m pipeline.audit_cli pre --graph concept-graph.json --trace trace.json --doc <doc> --out /tmp/pre-out

# Stage 2 (Post): emit Post prompt (optionally with Pre's post_brief.md) and verify in Lean 4
python3 -m pipeline.audit_cli prompt --doc <doc> --auditor AuditorA --pre-brief /tmp/pre-out/post_brief.md --out /tmp/post_prompt.txt
python3 -m pipeline.audit_cli run --doc <doc> --spec spec.json --pre-gate /tmp/pre-out/explore.json --out /tmp/post-out

# Standalone Post run (without Pre-Gate, backward-compatible)
python3 -m pipeline.audit_cli run \
  --doc pipeline/examples/sample_framework.md \
  --spec pipeline/examples/sample_framework_auditor_a.json \
  --out /tmp/epistemic-run
```

## Running the Test Suite

```bash
python3 -m unittest discover -s pipeline/tests -v
```
