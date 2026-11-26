"""Strict JSON schema validation, Lean identifier hygiene, and verbatim quote grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pipeline.ingest import IngestedDocument, dehyphenate_and_normalize, normalize_whitespace

IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
MIN_QUOTE_NONSPACE_CHARS = 12
DISALLOWED_UNICODE_SEPARATORS = frozenset({"\u0085", "\u2028", "\u2029"})

# Lean 4 reserved words & core type names that must not be used as bare constructors/defs.
LEAN_RESERVED = frozenset(
    {
        "abbrev",
        "axiom",
        "by",
        "class",
        "def",
        "deriving",
        "do",
        "else",
        "end",
        "example",
        "false",
        "for",
        "fun",
        "have",
        "if",
        "import",
        "in",
        "inductive",
        "instance",
        "let",
        "match",
        "mutual",
        "namespace",
        "noncomputable",
        "opaque",
        "open",
        "partial",
        "private",
        "protected",
        "return",
        "section",
        "set_option",
        "sorry",
        "structure",
        "syntax",
        "then",
        "theorem",
        "true",
        "universe",
        "variable",
        "where",
        "with",
        "Type",
        "Prop",
        "Sort",
        "Nat",
        "Bool",
        "String",
        "List",
        "Option",
    }
)

VALID_ORIGINS = frozenset({"setByExperimenter", "measured"})
VALID_OP_KINDS = frozenset({"transform", "partition", "lossy", "forget"})
VALID_INVARIANCE = frozenset({"shown", "notShown", "contradicted"})
VALID_CLAIM_KINDS = frozenset(
    {
        "emergesWithout",
        "emergesWithExclusion",
        "independentConvergence",
        "uniqueRecovery",
        "conditionalFlow",
        "effectivenessClaim",
    }
)
VALID_CLAIM_PROVENANCE = frozenset({"authorClaimed", "reviewerStressTest"})
VALID_USAGE_QUANTITY_KINDS = frozenset({"actualSpend", "requestedOrAllocated", "estimatedOrProjected", "unknown"})
SUPPORTED_SCHEMA_VERSIONS = frozenset({"epistemic-ledger/v2.1", "epistemic-ledger/v2.2", "epistemic-ledger/v2.3"})

# Structured billing/transaction/run receipt IDs grounded verbatim inside billing records.
# Plain prose words ("Section 2", "Table 1", "c1") intentionally do NOT match this pattern.
STRUCTURED_RECEIPT_RE = re.compile(
    r"^(?:TXN|INV|REC|RECEIPT|BILL|JOB|RUN|LEDGER|CHARGE|METER|ACCT)[-_:#][A-Za-z0-9][A-Za-z0-9_.\-]*$",
    re.IGNORECASE,
)
STRUCTURED_RECEIPT_SEARCH_RE = re.compile(
    r"(?<![A-Za-z0-9_\-])"
    r"((?:TXN|INV|REC|RECEIPT|BILL|JOB|RUN|LEDGER|CHARGE|METER|ACCT|ORDER|EVENT|BATCH)[-_:#][A-Za-z0-9][A-Za-z0-9_.\-]*)",
    re.IGNORECASE,
)
RECONCILIATION_TOTAL_CUES_RE = re.compile(
    r"\b(?:total|overall|cumulative|all\s+(?:sessions?|runs?|jobs?|charges?|items?)|"
    r"entire\s+(?:study|experiment|period|run)|full\s+period|complete\s+ledger|reconciled|summary)\b",
    re.IGNORECASE,
)

# Cues indicating a figure is a request/allocation/cap/estimate/projection rather than actual spend.
REQUESTED_OR_ALLOCATED_CUES_RE = re.compile(
    r"\b(?:requested|request|requests|allocated|allocation|budgeted|capped|quota|limit|proposed|saved|avoided)\b",
    re.IGNORECASE,
)
ESTIMATED_OR_PROJECTED_CUES_RE = re.compile(
    r"\b(?:estimated|estimate|estimates|projected|projection|planned|expected|target|approx(?:imately)?|hypothetic(?:al|ally)?)\b"
    r"|\bwould\s+(?:require|need|use|cost|spend)\b",
    re.IGNORECASE,
)
# Cues indicating a prose mention restates a previously reported figure rather than a distinct new charge.
RESTATEMENT_CUES_RE = re.compile(
    r"\b(?:previously\s+reported|as\s+(?:previously\s+)?reported|restated|repeated|mentioned\s+(?:above|earlier|before)|"
    r"noted\s+(?:above|earlier|before)|summarized\s+(?:above|earlier)|recalled|recapitulated)\b",
    re.IGNORECASE,
)
ACTUAL_SPEND_CUES_RE = re.compile(
    r"\b(?:used|consumed|charged|billed|spent|incurred|expended|measured|logged)\b",
    re.IGNORECASE,
)
NEGATED_ACTUAL_CUES_RE = re.compile(
    r"\b(?:not|never|no|without)\s+(?:be\s+|been\s+|was\s+|were\s+|have\s+|actually\s+)?(?:used|consumed|charged|billed|spent|incurred|expended|measured)\b"
    r"|n't\s+(?:be\s+|been\s+)?(?:used|consumed|charged|billed|spent|incurred|expended|measured)\b",
    re.IGNORECASE,
)

METHOD_ROLE_WORDS = frozenset({"method"})
CONTROL_ROLE_WORDS = frozenset({"control", "baseline"})
ATTRIBUTION_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "used",
        "using",
        "use",
        "spent",
        "spend",
        "total",
        "cost",
        "costs",
        "budget",
        "budgets",
        "run",
        "runs",
        "node",
        "arm",
        "arms",
        "eval",
        "evaluation",
        "score",
        "output",
        "input",
        "data",
        "all",
        "both",
        "each",
        "per",
        "has",
        "have",
        "had",
        "not",
        "our",
        "they",
        "was",
        "were",
        "are",
        "been",
        "ledger",
        "meter",
        "cluster",
        "shared",
        "resource",
        "resources",
        "hour",
        "hours",
        "unit",
        "units",
        "billed",
        "billing",
        "acc",
        "account",
        "accounts",
    }
)


def extract_quote_integers(qtext: str) -> list[tuple[int, int, int]]:
    """Parse complete non-negative integer tokens (plain or thousands-grouped like `1,500`)
    from `qtext`, returning `(value, start, end)`. Never matches a substring inside a larger
    grouped number (`500` inside `1,500`) or decimal (`99` inside `99.4`)."""
    results: list[tuple[int, int, int]] = []
    for m in re.finditer(r"\d+(?:[.,_]\d+)*", qtext):
        start, end = m.start(), m.end()
        if start > 0 and qtext[start - 1].isalpha():
            continue
        if start > 0 and qtext[start - 1] == "-" and (start == 1 or not qtext[start - 2].isalnum()):
            continue
        tok = m.group(0)
        if re.fullmatch(r"\d+", tok):
            results.append((int(tok), start, end))
        elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", tok):
            results.append((int(tok.replace(",", "")), start, end))
    return results


def _has_intact_doc_numeric_boundary(doc_text: str, abs_start: int, abs_end: int) -> bool:
    """Return True iff `doc_text[abs_start:abs_end]` is NOT sliced out of a larger numeric
    or alphanumeric token in the full source document (e.g. `500` sliced from `1,500`,
    `1500`, `-500`, `500.5`, or `500,000`)."""
    if abs_start > 0:
        prev = doc_text[abs_start - 1]
        if prev.isdigit() or prev.isalpha():
            return False
        if prev in ",._" and abs_start >= 2 and doc_text[abs_start - 2].isdigit():
            return False
        if prev == "-" and (abs_start == 1 or not doc_text[abs_start - 2].isalnum()):
            return False
    if abs_end < len(doc_text):
        nxt = doc_text[abs_end]
        if nxt.isdigit():
            return False
        if nxt in ",._" and abs_end + 1 < len(doc_text) and doc_text[abs_end + 1].isdigit():
            return False
    return True


def extract_doc_bounded_quote_integers(
    qtext: str,
    doc: IngestedDocument | None = None,
    qm: QuoteMatch | None = None,
) -> tuple[list[tuple[int, int, int]], set[int]]:
    """Return `(intact_integers, truncated_values)` for `qtext`.
    When `doc` and a matched `QuoteMatch` are provided, validates each integer's left and right
    boundaries on the full source document at the matched offset so sliced substrings like
    `500 ...` from `1,500 ...` are rejected rather than parsed as `500`."""
    if doc is not None and qm is not None and qm.matched and qm.char_offset is not None:
        doc_text = doc.normalized_text if qm.mode == "exact_ws" else doc.dehyphenated_text
        scan_text = qm.normalized_quote
        q_offset = qm.char_offset
        intact: list[tuple[int, int, int]] = []
        truncated: set[int] = set()
        for val, rel_s, rel_e in extract_quote_integers(scan_text):
            if _has_intact_doc_numeric_boundary(doc_text, q_offset + rel_s, q_offset + rel_e):
                intact.append((val, rel_s, rel_e))
            else:
                truncated.add(val)
        return intact, truncated
    return extract_quote_integers(qtext), set()


def _unit_regex(unit: str) -> str:
    tokens = [t for t in re.split(r"[\s_\-/]+", unit.strip()) if t]
    if not tokens:
        return r"(?!)"
    parts: list[str] = []
    for idx, tok in enumerate(tokens):
        esc = re.escape(tok)
        if idx == len(tokens) - 1 and tok.isalpha() and len(tok) > 2:
            if tok.lower().endswith("s"):
                parts.append(re.escape(tok[:-1]) + "s?")
            else:
                parts.append(esc + "s?")
        else:
            parts.append(esc)
    return r"[\s_\-/]+".join(parts)


def extract_unit_bound_amounts(
    qtext: str,
    unit: str,
    integers: list[tuple[int, int, int]] | None = None,
) -> list[int]:
    """Return integer amounts in `qtext` directly paired with `unit` (e.g. `1,500 GPU-hours`, `$500`)."""
    tokens = [t.lower() for t in re.split(r"[\s_\-/]+", unit.strip()) if t]
    is_usd = tokens in (["usd"], ["dollar"], ["dollars"])
    up = _unit_regex(unit)
    after_re = re.compile(r"[\s\-]*" + up + r"(?![A-Za-z0-9])", re.IGNORECASE)
    before_usd_re = re.compile(r"(?:US)?\$\s*$", re.IGNORECASE)
    found: list[int] = []
    scan_ints = integers if integers is not None else extract_quote_integers(qtext)
    for val, start, end in scan_ints:
        if after_re.match(qtext[end:]):
            found.append(val)
        elif is_usd and before_usd_re.search(qtext[:start]):
            found.append(val)
    return found


def _ident_markers(ident: str | None) -> set[str]:
    if not ident:
        return set()
    parts = [p.lower() for p in re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", ident)]
    markers: set[str] = set()
    for p in parts:
        if p.isalpha() and len(p) >= 3:
            markers.add(p)
    joined = "".join(parts)
    spaced = " ".join(parts)
    if len(joined) >= 3 and any(ch.isalpha() for ch in joined):
        markers.add(joined)
    if len(parts) >= 2 and any(ch.isalpha() for ch in spaced):
        markers.add(spaced)
    return markers


def _unit_stopwords(unit: str) -> set[str]:
    toks = [t.lower() for t in re.split(r"[\s_\-/]+", unit.strip()) if t]
    out: set[str] = set()
    for t in toks:
        out.add(t)
        if t.endswith("s") and len(t) > 2:
            out.add(t[:-1])
        else:
            out.add(t + "s")
    return out


def _quote_contains_receipt_id(qtext: str, receipt: str) -> bool:
    """Match `receipt` verbatim in `qtext` with identifier boundaries that allow trailing
    sentence punctuation (e.g. `under TXN-M1.`) while still blocking substring matches
    inside longer IDs like `TXN-M10` or `TXN-M1.2`."""
    if not receipt:
        return False
    for m in re.finditer(re.escape(receipt), qtext, re.IGNORECASE):
        s, e = m.start(), m.end()
        left_ok = s == 0 or not (
            qtext[s - 1].isalnum()
            or qtext[s - 1] in "_-"
            or (qtext[s - 1] == "." and s >= 2 and qtext[s - 2].isalnum())
        )
        right_ok = e == len(qtext) or not (
            qtext[e].isalnum()
            or qtext[e] in "_-"
            or (qtext[e] == "." and e + 1 < len(qtext) and qtext[e + 1].isalnum())
        )
        if left_ok and right_ok:
            return True
    return False


def extract_structured_receipt_ids(text: str) -> list[str]:
    """Extract distinct structured billing/run/job/invoice IDs from `text`, preserving
    original case and stripping trailing sentence punctuation."""
    out: list[str] = []
    seen: set[str] = set()
    for m in STRUCTURED_RECEIPT_SEARCH_RE.finditer(text):
        raw = m.group(1).rstrip(".,;:")
        if not raw:
            continue
        s = m.start(1)
        if s >= 2 and text[s - 1] == "." and text[s - 2].isalnum():
            continue
        key = raw.upper()
        if key not in seen:
            seen.add(key)
            out.append(raw)
    return out


def _spec_ancestors(spec: dict[str, Any], target: str | None) -> set[str]:
    if not target:
        return set()
    visited = {target}
    ops = spec.get("ops", [])
    changed = True
    while changed:
        changed = False
        for op in ops:
            if isinstance(op, dict) and op.get("output") in visited:
                for inp in op.get("inputs", []):
                    if inp not in visited:
                        visited.add(inp)
                        changed = True
    return visited


def _arm_exclusive_graph_receipts(
    spec: dict[str, Any], arm_node: str, other_arm_node: str | None, exclude_upper: set[str]
) -> list[str]:
    arm_anc = _spec_ancestors(spec, arm_node)
    other_anc = _spec_ancestors(spec, other_arm_node)
    excl = arm_anc - other_anc
    out: list[str] = []
    seen: set[str] = set()
    for src in spec.get("sources", []):
        if isinstance(src, dict) and src.get("node") in excl and isinstance(src.get("quote"), str):
            for rid in extract_structured_receipt_ids(src["quote"]):
                if rid.upper() not in exclude_upper and rid.upper() not in seen:
                    seen.add(rid.upper())
                    out.append(rid)
    for op in spec.get("ops", []):
        if isinstance(op, dict) and op.get("output") in excl and isinstance(op.get("quote"), str):
            for rid in extract_structured_receipt_ids(op["quote"]):
                if rid.upper() not in exclude_upper and rid.upper() not in seen:
                    seen.add(rid.upper())
                    out.append(rid)
    return out


def classify_usage_entry(
    arm_role: str,
    method_node: str,
    control_node: str | None,
    entry: dict[str, Any],
    method_sources: set[str],
    control_sources: set[str],
    all_graph_sources: set[str],
) -> tuple[str, str]:
    """Mechanically classify `(effective_quantity_kind, attribution)` for a `ResourceUsage` entry.

    Scope & trust boundary:
    - Checks single unambiguous unit-bound integer, non-contradictory actual-spend phrasing
      (rejecting requested/allocated/estimated/negated/restated prose), exclusive arm/source
      markers, and a structured billing/run `receipt` ID grounded verbatim inside `quote`.
    - Plain prose mentions lacking a source-grounded structured billing/run receipt ID are
      classified `unverifiedProse` (never `verifiedRecord`), so prose restatements cannot be
      certified as verified actual budget parity.
    - Semantic authenticity of the underlying billing log itself remains outside automated text
      checks and requires human/external audit.
    """
    qtext = str(entry.get("quote", ""))
    unit = str(entry.get("unit", ""))
    amount = entry.get("amount")
    src = str(entry.get("source", ""))
    receipt = str(entry.get("receipt", ""))
    declared_qkind = str(entry.get("quantity_kind", "actualSpend"))

    # 1. Quantity kind check: non-actual quantities (requests, allocations, estimates) cannot certify spend.
    if REQUESTED_OR_ALLOCATED_CUES_RE.search(qtext):
        return "requestedOrAllocated", "contradicted"
    if ESTIMATED_OR_PROJECTED_CUES_RE.search(qtext):
        return "estimatedOrProjected", "contradicted"
    if declared_qkind != "actualSpend":
        return declared_qkind, "unverifiedProse"

    # 2. Restatement / negation check: restated figures or negated spend cannot certify a distinct charge.
    if RESTATEMENT_CUES_RE.search(qtext) or NEGATED_ACTUAL_CUES_RE.search(qtext):
        return "actualSpend", "contradicted"

    # 3. Single unambiguous amount paired with `unit` in this quote.
    bound = extract_unit_bound_amounts(qtext, unit)
    if len(bound) != 1 or bound[0] != amount:
        return "actualSpend", "unverifiedProse"

    # 4. Arm & source marker attribution.
    unit_sw = _unit_stopwords(unit)
    method_raw = set(METHOD_ROLE_WORDS) | _ident_markers(method_node)
    for s in method_sources:
        method_raw |= _ident_markers(s)
    control_raw = set(CONTROL_ROLE_WORDS) | _ident_markers(control_node)
    for s in control_sources:
        control_raw |= _ident_markers(s)

    shared = method_raw & control_raw
    method_excl = method_raw - shared - CONTROL_ROLE_WORDS - ATTRIBUTION_STOPWORDS - unit_sw
    control_excl = control_raw - shared - METHOD_ROLE_WORDS - ATTRIBUTION_STOPWORDS - unit_sw

    if arm_role == "method":
        own_markers, opp_markers = method_excl, control_excl
    else:
        own_markers, opp_markers = control_excl, method_excl

    own_src_markers = _ident_markers(src)
    other_src_markers: set[str] = set()
    for s in all_graph_sources:
        if s != src:
            other_src_markers |= (
                _ident_markers(s) - own_src_markers - shared - ATTRIBUTION_STOPWORDS - unit_sw - own_markers
            )

    qlow = qtext.lower()

    def _hits(markers: set[str]) -> bool:
        return any(re.search(rf"(?<![a-z0-9]){re.escape(m)}(?![a-z0-9])", qlow) for m in markers)

    hits_own = _hits(own_markers)
    hits_opp = _hits(opp_markers)
    hits_other_src = _hits(other_src_markers)

    if (hits_opp or hits_other_src) and not hits_own:
        return "actualSpend", "contradicted"
    if not (hits_own and not hits_opp and not hits_other_src):
        return "actualSpend", "unverifiedProse"

    # 5. Require an explicit actual-spend predicate (reject ambiguous verbs like "had 500 GPU-hours").
    if not ACTUAL_SPEND_CUES_RE.search(qtext):
        return "unknown", "unverifiedProse"

    # 6. Require a structured billing/run receipt ID grounded verbatim (identifier-bounded,
    # allowing trailing sentence punctuation such as `under TXN-M1.`) inside the quote.
    # Plain prose without a source-grounded receipt ID is classified `unverifiedProse`.
    if not STRUCTURED_RECEIPT_RE.fullmatch(receipt):
        return "actualSpend", "unverifiedProse"
    if not _quote_contains_receipt_id(qtext, receipt):
        return "actualSpend", "unverifiedProse"

    return "actualSpend", "verifiedRecord"


def classify_reconciliation_entry(
    arm_role: str,
    method_node: str,
    control_node: str | None,
    rec: dict[str, Any],
    method_sources: set[str],
    control_sources: set[str],
    all_graph_sources: set[str],
) -> str:
    """Mechanically classify whether an `ArmReconciliation` quote establishes a verified
    scope/period total for the arm (`verifiedRecord` | `unverifiedProse` | `contradicted`)."""
    qtext = str(rec.get("quote", ""))
    unit = str(rec.get("unit", ""))
    total = rec.get("reconciled_total")
    receipt = str(rec.get("receipt", ""))

    if (
        REQUESTED_OR_ALLOCATED_CUES_RE.search(qtext)
        or ESTIMATED_OR_PROJECTED_CUES_RE.search(qtext)
        or RESTATEMENT_CUES_RE.search(qtext)
        or NEGATED_ACTUAL_CUES_RE.search(qtext)
    ):
        return "contradicted"

    bound = extract_unit_bound_amounts(qtext, unit)
    if len(bound) != 1 or bound[0] != total:
        return "unverifiedProse"

    if not RECONCILIATION_TOTAL_CUES_RE.search(qtext):
        return "unverifiedProse"

    unit_sw = _unit_stopwords(unit)
    method_raw = set(METHOD_ROLE_WORDS) | _ident_markers(method_node)
    for s in method_sources:
        method_raw |= _ident_markers(s)
    control_raw = set(CONTROL_ROLE_WORDS) | _ident_markers(control_node)
    for s in control_sources:
        control_raw |= _ident_markers(s)
    shared = method_raw & control_raw
    method_excl = method_raw - shared - CONTROL_ROLE_WORDS - ATTRIBUTION_STOPWORDS - unit_sw
    control_excl = control_raw - shared - METHOD_ROLE_WORDS - ATTRIBUTION_STOPWORDS - unit_sw

    own_markers, opp_markers = (method_excl, control_excl) if arm_role == "method" else (control_excl, method_excl)
    qlow = qtext.lower()

    def _hits(markers: set[str]) -> bool:
        return any(re.search(rf"(?<![a-z0-9]){re.escape(m)}(?![a-z0-9])", qlow) for m in markers)

    hits_own = _hits(own_markers)
    hits_opp = _hits(opp_markers)
    if hits_opp and not hits_own:
        return "contradicted"
    if not (hits_own and not hits_opp):
        return "unverifiedProse"

    if not STRUCTURED_RECEIPT_RE.fullmatch(receipt) or not _quote_contains_receipt_id(qtext, receipt):
        return "unverifiedProse"
    return "verifiedRecord"


def compute_claim_usage_details(
    spec: dict[str, Any], claim: dict[str, Any]
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]], list[dict[str, Any]]]:
    """Compute mechanical `(charge_event_id, quantity_kind, attribution)` tuples for
    `(method_usage, control_usage)` AND normalized `reconciliations` (with graph-referenced
    expected receipts merged in) for Lean verification."""
    if claim.get("kind") != "effectivenessClaim":
        return [], [], []
    method_node = str(claim["method_node"])
    control_node = claim.get("control_node")
    cost_tag = str(claim["cost_tag"])
    m_usage = claim.get("method_usage", [])
    c_usage = claim.get("control_usage", [])
    m_sources = {str(u.get("source", "")) for u in m_usage if isinstance(u, dict) and u.get("source")}
    c_sources = {str(u.get("source", "")) for u in c_usage if isinstance(u, dict) and u.get("source")}
    all_sources = {str(s.get("node", "")) for s in spec.get("sources", []) if isinstance(s, dict) and s.get("node")}

    # Link cross-referenced usage entries (e.g. JOB-C1 and INV-C1 billing JOB-C1) via union-find
    # over shared structured IDs found in their quotes or explicit `charge_event` field.
    all_entries = list(m_usage) + list(c_usage)
    n = len(all_entries)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    entry_keys: list[list[str]] = []
    key_owner: dict[str, int] = {}
    for idx, u in enumerate(all_entries):
        keys: list[str] = []
        seen_k: set[str] = set()
        for raw_k in [
            str(u.get("charge_event", "")).strip(),
            str(u.get("receipt", "")).strip(),
            *extract_structured_receipt_ids(str(u.get("quote", ""))),
        ]:
            if raw_k and raw_k.upper() not in seen_k:
                seen_k.add(raw_k.upper())
                keys.append(raw_k)
        entry_keys.append(keys)
        for k in keys:
            ku = k.upper()
            if ku in key_owner:
                union(key_owner[ku], idx)
            else:
                key_owner[ku] = idx

    # For each connected component of linked entries, pick a deterministic canonical chargeEventId
    # (preferring any shared cross-referenced key or explicit charge_event, otherwise the entry's receipt).
    comp_members: dict[int, list[int]] = {}
    for idx in range(n):
        comp_members.setdefault(find(idx), []).append(idx)

    canonical_event: list[str] = [""] * n
    for root, members in comp_members.items():
        if len(members) == 1:
            u = all_entries[members[0]]
            canonical_event[members[0]] = str(u.get("charge_event") or u.get("receipt") or "")
        else:
            key_counts: dict[str, tuple[int, str]] = {}
            for idx in members:
                for k in entry_keys[idx]:
                    ku = k.upper()
                    cnt, orig = key_counts.get(ku, (0, k))
                    key_counts[ku] = (cnt + 1, orig)
            shared_keys = sorted([orig for cnt, orig in key_counts.values() if cnt >= 2])
            chosen = shared_keys[0] if shared_keys else str(all_entries[members[0]].get("receipt", ""))
            for idx in members:
                canonical_event[idx] = chosen

    m_details: list[tuple[str, str, str]] = []
    for i, u in enumerate(m_usage):
        qk, attr = classify_usage_entry("method", method_node, control_node, u, m_sources, c_sources, all_sources)
        m_details.append((canonical_event[i], qk, attr))

    c_details: list[tuple[str, str, str]] = []
    offset = len(m_usage)
    for j, u in enumerate(c_usage):
        qk, attr = classify_usage_entry("control", method_node, control_node, u, m_sources, c_sources, all_sources)
        c_details.append((canonical_event[offset + j], qk, attr))

    # Reconciliations + automatic arm-exclusive graph receipt expectations
    raw_recs = claim.get("reconciliations", [])
    rec_receipts_upper = {str(r.get("receipt", "")).upper() for r in raw_recs if isinstance(r, dict) and r.get("receipt")}
    method_graph_expected = _arm_exclusive_graph_receipts(spec, method_node, control_node, rec_receipts_upper)
    control_graph_expected = (
        _arm_exclusive_graph_receipts(spec, control_node, method_node, rec_receipts_upper) if control_node else []
    )

    lean_recs: list[dict[str, Any]] = []
    covered_arm_units: set[tuple[str, str]] = set()
    for r in raw_recs:
        arm = str(r["arm"])
        dim = str(r["dimension"])
        unit = str(r["unit"])
        role = "method" if arm == method_node else "control"
        attr = classify_reconciliation_entry(
            role, method_node, control_node, r, m_sources, c_sources, all_sources
        )
        rec_id_up = str(r.get("receipt", "")).upper()
        quote_ids = [rid for rid in extract_structured_receipt_ids(str(r.get("quote", ""))) if rid.upper() != rec_id_up]
        graph_ids = method_graph_expected if role == "method" else control_graph_expected
        exp: list[str] = []
        seen_e: set[str] = set()
        for rid in [*r.get("expected_receipts", []), *quote_ids, *graph_ids]:
            if rid and rid.upper() not in seen_e:
                seen_e.add(rid.upper())
                exp.append(rid)
        lean_recs.append(
            {
                "arm": arm,
                "dimension": dim,
                "unit": unit,
                "reconciled_total": r["reconciled_total"],
                "expected_receipts": exp,
                "attribution": attr,
            }
        )
        if dim == cost_tag:
            covered_arm_units.add((arm, unit))

    # Even if no reconciliation entry was provided for an arm/unit, still surface graph-referenced
    # expected receipts so omitted sessions (e.g. TXN-M2 in run_method's quote) are always flagged!
    all_units: list[str] = []
    for u in all_entries:
        if u.get("dimension") == cost_tag and u.get("unit") not in all_units:
            all_units.append(str(u["unit"]))
    for arm_name, graph_ids in [(method_node, method_graph_expected), (control_node, control_graph_expected)]:
        if not arm_name or not graph_ids:
            continue
        for unit in all_units:
            if (arm_name, unit) not in covered_arm_units:
                lean_recs.append(
                    {
                        "arm": arm_name,
                        "dimension": cost_tag,
                        "unit": unit,
                        "reconciled_total": None,
                        "expected_receipts": graph_ids,
                        "attribution": "unverifiedProse",
                    }
                )

    return m_details, c_details, lean_recs


@dataclass(frozen=True)
class ValidationErrorItem:
    path: str
    code: str
    message: str


@dataclass(frozen=True)
class QuoteMatch:
    path: str
    quote: str
    matched: bool
    char_offset: int | None
    mode: str | None  # "exact_ws" or "dehyphenated"
    normalized_quote: str


def is_valid_ident(value: Any) -> bool:
    return isinstance(value, str) and bool(IDENT_RE.match(value)) and value not in LEAN_RESERVED


def _check_ident(value: Any, path: str, errors: list[ValidationErrorItem]) -> str | None:
    if not isinstance(value, str) or not IDENT_RE.match(value):
        errors.append(
            ValidationErrorItem(
                path, "invalid_identifier", f"Expected ASCII identifier matching {IDENT_RE.pattern}, got {value!r}"
            )
        )
        return None
    if value in LEAN_RESERVED:
        errors.append(
            ValidationErrorItem(path, "reserved_keyword", f"Identifier {value!r} is a Lean reserved keyword")
        )
        return None
    return value


def _check_nonempty_str(value: Any, path: str, errors: list[ValidationErrorItem]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(ValidationErrorItem(path, "invalid_string", "Expected non-empty string"))
        return None
    if any((ord(ch) < 32 and ch not in ("\n", "\r", "\t")) or ch in DISALLOWED_UNICODE_SEPARATORS for ch in value):
        errors.append(
            ValidationErrorItem(
                path, "control_char", "String contains disallowed ASCII control or Unicode line-separator characters"
            )
        )
        return None
    return value


def _check_allowed_keys(
    obj: Any, allowed: set[str], required: set[str], path: str, errors: list[ValidationErrorItem]
) -> bool:
    if not isinstance(obj, dict):
        errors.append(ValidationErrorItem(path, "type_error", f"Expected object, got {type(obj).__name__}"))
        return False
    keys = set(obj.keys())
    missing = sorted(required - keys)
    extra = sorted(keys - allowed)
    ok = True
    for k in missing:
        errors.append(ValidationErrorItem(f"{path}.{k}", "missing_key", f"Missing required key {k!r}"))
        ok = False
    for k in extra:
        errors.append(ValidationErrorItem(f"{path}.{k}", "unknown_key", f"Unknown key {k!r}"))
        ok = False
    return ok


def verify_quote_in_document(doc: IngestedDocument, quote: str, path: str) -> QuoteMatch:
    norm_q = normalize_whitespace(quote)
    nonspace_len = len(re.sub(r"\s+", "", norm_q))
    if nonspace_len < MIN_QUOTE_NONSPACE_CHARS:
        return QuoteMatch(path=path, quote=quote, matched=False, char_offset=None, mode=None, normalized_quote=norm_q)

    idx = doc.normalized_text.find(norm_q)
    if idx != -1:
        return QuoteMatch(
            path=path, quote=quote, matched=True, char_offset=idx, mode="exact_ws", normalized_quote=norm_q
        )

    dehy_q = dehyphenate_and_normalize(quote)
    idx2 = doc.dehyphenated_text.find(dehy_q)
    if idx2 != -1:
        return QuoteMatch(
            path=path, quote=quote, matched=True, char_offset=idx2, mode="dehyphenated", normalized_quote=dehy_q
        )

    return QuoteMatch(path=path, quote=quote, matched=False, char_offset=None, mode=None, normalized_quote=norm_q)


def validate_spec(
    spec: Any, doc: IngestedDocument | None = None
) -> tuple[list[ValidationErrorItem], list[QuoteMatch]]:
    """Validate an AuditSpec JSON object and optionally verify all quotes against `doc`.

    Note on quote grounding: verbatim matching proves that each cited sentence appears
    in the source snapshot (anti-hallucination). Whether a quote semantically justifies a
    particular `carries` tag or causal edge remains a separate auditor judgment.
    """
    errors: list[ValidationErrorItem] = []
    quotes: list[QuoteMatch] = []

    top_allowed = {"schema_version", "auditor", "paper_title", "nodes", "tags", "sources", "ops", "claims"}
    top_required = {"schema_version", "auditor", "nodes", "tags", "sources", "ops", "claims"}
    if not _check_allowed_keys(spec, top_allowed, top_required, "$", errors):
        return errors, quotes

    if spec["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(
            ValidationErrorItem(
                "$.schema_version",
                "unsupported_schema",
                f"Expected one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}, got {spec['schema_version']!r}",
            )
        )

    _check_ident(spec["auditor"], "$.auditor", errors)
    if "paper_title" in spec:
        _check_nonempty_str(spec["paper_title"], "$.paper_title", errors)

    # Nodes
    node_set: set[str] = set()
    if not isinstance(spec["nodes"], list) or len(spec["nodes"]) == 0:
        errors.append(ValidationErrorItem("$.nodes", "empty_list", "Must define at least one node"))
    else:
        for i, n in enumerate(spec["nodes"]):
            ident = _check_ident(n, f"$.nodes[{i}]", errors)
            if ident:
                if ident in node_set:
                    errors.append(ValidationErrorItem(f"$.nodes[{i}]", "duplicate", f"Duplicate node {ident!r}"))
                node_set.add(ident)

    # Tags
    tag_set: set[str] = set()
    if not isinstance(spec["tags"], list) or len(spec["tags"]) == 0:
        errors.append(ValidationErrorItem("$.tags", "empty_list", "Must define at least one tag"))
    else:
        for i, t in enumerate(spec["tags"]):
            ident = _check_ident(t, f"$.tags[{i}]", errors)
            if ident:
                if ident in tag_set:
                    errors.append(ValidationErrorItem(f"$.tags[{i}]", "duplicate", f"Duplicate tag {ident!r}"))
                tag_set.add(ident)

    def check_quote(val: Any, path: str) -> None:
        q = _check_nonempty_str(val, path, errors)
        if q is None:
            return
        if len(re.sub(r"\s+", "", q)) < MIN_QUOTE_NONSPACE_CHARS:
            errors.append(
                ValidationErrorItem(
                    path,
                    "quote_too_short",
                    f"Verbatim quote must contain at least {MIN_QUOTE_NONSPACE_CHARS} non-whitespace characters",
                )
            )
            return
        if doc is not None:
            qm = verify_quote_in_document(doc, q, path)
            quotes.append(qm)
            if not qm.matched:
                errors.append(
                    ValidationErrorItem(
                        path,
                        "ungrounded_quote",
                        f"Quote was not found verbatim in source document: {q[:120]!r}",
                    )
                )

    def check_node_ref(val: Any, path: str) -> None:
        if not isinstance(val, str) or val not in node_set:
            errors.append(ValidationErrorItem(path, "unknown_node", f"Unknown node {val!r}"))

    def check_tag_list(val: Any, path: str) -> None:
        if not isinstance(val, list):
            errors.append(ValidationErrorItem(path, "type_error", "Expected list of tag names"))
            return
        for j, t in enumerate(val):
            if not isinstance(t, str) or t not in tag_set:
                errors.append(ValidationErrorItem(f"{path}[{j}]", "unknown_tag", f"Unknown tag {t!r}"))

    # Sources
    source_node_set: set[str] = set()
    if not isinstance(spec["sources"], list):
        errors.append(ValidationErrorItem("$.sources", "type_error", "Expected list"))
    else:
        for i, src in enumerate(spec["sources"]):
            p = f"$.sources[{i}]"
            if not _check_allowed_keys(
                src,
                {"node", "origin", "carries", "quote", "rationale"},
                {"node", "origin", "carries", "quote"},
                p,
                errors,
            ):
                continue
            check_node_ref(src["node"], f"{p}.node")
            if isinstance(src["node"], str) and src["node"] in node_set:
                if src["node"] in source_node_set:
                    errors.append(
                        ValidationErrorItem(
                            f"{p}.node", "duplicate_source", f"Duplicate SourceNode for {src['node']!r}"
                        )
                    )
                source_node_set.add(src["node"])
            if src["origin"] not in VALID_ORIGINS:
                errors.append(
                    ValidationErrorItem(f"{p}.origin", "invalid_enum", f"origin must be in {sorted(VALID_ORIGINS)}")
                )
            check_tag_list(src["carries"], f"{p}.carries")
            check_quote(src["quote"], f"{p}.quote")
            if "rationale" in src:
                _check_nonempty_str(src["rationale"], f"{p}.rationale", errors)

    # Ops
    op_output_set: set[str] = set()
    if not isinstance(spec["ops"], list):
        errors.append(ValidationErrorItem("$.ops", "type_error", "Expected list"))
    else:
        for i, op in enumerate(spec["ops"]):
            p = f"$.ops[{i}]"
            if not isinstance(op, dict):
                errors.append(ValidationErrorItem(p, "type_error", "Expected object"))
                continue
            kind = op.get("kind")
            if kind not in VALID_OP_KINDS:
                errors.append(
                    ValidationErrorItem(f"{p}.kind", "invalid_enum", f"kind must be in {sorted(VALID_OP_KINDS)}")
                )
                continue
            if kind == "forget":
                allowed = {"name", "inputs", "output", "kind", "tag", "evidence", "quote", "rationale"}
                required = {"name", "inputs", "output", "kind", "tag", "evidence", "quote"}
            else:
                allowed = {"name", "inputs", "output", "kind", "introduces", "quote", "rationale"}
                required = {"name", "inputs", "output", "kind", "introduces", "quote"}
            if not _check_allowed_keys(op, allowed, required, p, errors):
                continue
            _check_nonempty_str(op["name"], f"{p}.name", errors)
            if not isinstance(op["inputs"], list):
                errors.append(ValidationErrorItem(f"{p}.inputs", "type_error", "Expected list of nodes"))
            else:
                for j, inp in enumerate(op["inputs"]):
                    check_node_ref(inp, f"{p}.inputs[{j}]")
            check_node_ref(op["output"], f"{p}.output")
            if isinstance(op["output"], str) and op["output"] in node_set:
                op_output_set.add(op["output"])
            if kind == "forget":
                if not isinstance(op["tag"], str) or op["tag"] not in tag_set:
                    errors.append(ValidationErrorItem(f"{p}.tag", "unknown_tag", f"Unknown tag {op['tag']!r}"))
                if op["evidence"] not in VALID_INVARIANCE:
                    errors.append(
                        ValidationErrorItem(
                            f"{p}.evidence", "invalid_enum", f"evidence must be in {sorted(VALID_INVARIANCE)}"
                        )
                    )
            else:
                check_tag_list(op["introduces"], f"{p}.introduces")
            check_quote(op["quote"], f"{p}.quote")
            if "rationale" in op:
                _check_nonempty_str(op["rationale"], f"{p}.rationale", errors)

    defined_graph_nodes = source_node_set | op_output_set

    def check_defined_endpoint(val: Any, path: str) -> None:
        check_node_ref(val, path)
        if isinstance(val, str) and val in node_set and val not in defined_graph_nodes:
            errors.append(
                ValidationErrorItem(
                    path,
                    "undefined_claim_endpoint",
                    f"Claim endpoint {val!r} is neither a SourceNode nor the output of any Op in the graph",
                )
            )

    # Claims
    if not isinstance(spec["claims"], list) or len(spec["claims"]) == 0:
        errors.append(ValidationErrorItem("$.claims", "empty_list", "Must specify at least one claim"))
    else:
        seen_claim_ids: set[str] = set()
        for i, cl in enumerate(spec["claims"]):
            p = f"$.claims[{i}]"
            if not isinstance(cl, dict):
                errors.append(ValidationErrorItem(p, "type_error", "Expected object"))
                continue
            kind = cl.get("kind")
            if kind not in VALID_CLAIM_KINDS:
                errors.append(
                    ValidationErrorItem(f"{p}.kind", "invalid_enum", f"kind must be in {sorted(VALID_CLAIM_KINDS)}")
                )
                continue
            base_req = {"id", "statement", "quote", "kind"}
            base_opt = {"notes", "provenance"}
            if kind == "emergesWithout":
                extra = {"target", "tag"}
            elif kind == "emergesWithExclusion":
                extra = {"target", "excluded_channel", "tag"}
            elif kind == "independentConvergence":
                extra = {"branch_a", "branch_b", "tag"}
            elif kind == "uniqueRecovery":
                extra = {"target", "tag"}
            elif kind == "effectivenessClaim":
                extra = {
                    "method_node",
                    "evaluation_node",
                    "control_node",
                    "cost_ledger_node",
                    "cost_tag",
                    "method_usage",
                    "control_usage",
                }
                base_opt = base_opt | {"reconciliations"}
            else:  # conditionalFlow
                extra = {"target", "declared_sources"}
            if not _check_allowed_keys(cl, base_req | base_opt | extra, base_req | extra, p, errors):
                continue

            cid = _check_ident(cl["id"], f"{p}.id", errors)
            if cid:
                if cid in seen_claim_ids:
                    errors.append(ValidationErrorItem(f"{p}.id", "duplicate_claim_id", f"Duplicate claim id {cid!r}"))
                seen_claim_ids.add(cid)
            _check_nonempty_str(cl["statement"], f"{p}.statement", errors)
            check_quote(cl["quote"], f"{p}.quote")
            if "notes" in cl:
                _check_nonempty_str(cl["notes"], f"{p}.notes", errors)
            if "provenance" in cl and cl["provenance"] not in VALID_CLAIM_PROVENANCE:
                errors.append(
                    ValidationErrorItem(
                        f"{p}.provenance",
                        "invalid_enum",
                        f"provenance must be in {sorted(VALID_CLAIM_PROVENANCE)}",
                    )
                )

            def check_effectiveness_usages(
                m_val: Any,
                c_val: Any,
                r_val: Any,
                claim_path: str,
                method_node_name: Any,
                control_node_name: Any,
            ) -> None:
                seen_receipts: set[str] = set()
                seen_spans: list[tuple[str, int, int, str]] = []  # (path, start, end, dehy_q)

                def _check_one_list(val: Any, upath: str, expected_arm: Any) -> None:
                    if not isinstance(val, list):
                        errors.append(ValidationErrorItem(upath, "type_error", "Expected list of usage entries"))
                        return
                    for j, entry in enumerate(val):
                        ep = f"{upath}[{j}]"
                        if not _check_allowed_keys(
                            entry,
                            {"arm", "source", "receipt", "dimension", "unit", "amount", "quote", "quantity_kind", "charge_event"},
                            {"arm", "source", "receipt", "dimension", "unit", "amount", "quote"},
                            ep,
                            errors,
                        ):
                            continue
                        if "quantity_kind" in entry and entry["quantity_kind"] not in VALID_USAGE_QUANTITY_KINDS:
                            errors.append(
                                ValidationErrorItem(
                                    f"{ep}.quantity_kind",
                                    "invalid_enum",
                                    f"quantity_kind must be in {sorted(VALID_USAGE_QUANTITY_KINDS)}",
                                )
                            )
                        if "charge_event" in entry:
                            _check_nonempty_str(entry["charge_event"], f"{ep}.charge_event", errors)
                        check_node_ref(entry["arm"], f"{ep}.arm")
                        if expected_arm is None or entry["arm"] != expected_arm:
                            errors.append(
                                ValidationErrorItem(
                                    f"{ep}.arm",
                                    "mismatched_usage_arm",
                                    f"Usage arm {entry['arm']!r} must match arm node {expected_arm!r}",
                                )
                            )
                        check_node_ref(entry["source"], f"{ep}.source")
                        if isinstance(entry["source"], str) and entry["source"] in node_set and entry["source"] not in source_node_set:
                            errors.append(
                                ValidationErrorItem(
                                    f"{ep}.source",
                                    "unknown_source",
                                    f"Usage source {entry['source']!r} must be a declared SourceNode",
                                )
                            )
                        rid = _check_nonempty_str(entry["receipt"], f"{ep}.receipt", errors)
                        if rid is not None:
                            if rid in seen_receipts:
                                errors.append(
                                    ValidationErrorItem(
                                        f"{ep}.receipt",
                                        "duplicate_usage_receipt",
                                        f"Duplicate usage receipt {rid!r} within claim (cannot double-count the same line item)",
                                    )
                                )
                            seen_receipts.add(rid)
                        if entry["dimension"] not in tag_set:
                            errors.append(
                                ValidationErrorItem(f"{ep}.dimension", "unknown_tag", f"Unknown tag {entry['dimension']!r}")
                            )
                        unit_ok = _check_nonempty_str(entry["unit"], f"{ep}.unit", errors) is not None
                        valid_amt = isinstance(entry["amount"], int) and not isinstance(entry["amount"], bool) and entry["amount"] >= 0
                        if not valid_amt:
                            errors.append(
                                ValidationErrorItem(f"{ep}.amount", "invalid_amount", "amount must be a non-negative integer")
                            )
                        before_q_len = len(quotes)
                        check_quote(entry["quote"], f"{ep}.quote")
                        qm = quotes[-1] if len(quotes) > before_q_len else None
                        if valid_amt and isinstance(entry["quote"], str):
                            intact_ints, truncated_vals = extract_doc_bounded_quote_integers(
                                entry["quote"], doc=doc, qm=qm
                            )
                            parsed_ints = {v for v, _, _ in intact_ints}
                            if entry["amount"] not in parsed_ints:
                                if entry["amount"] in truncated_vals:
                                    errors.append(
                                        ValidationErrorItem(
                                            f"{ep}.amount",
                                            "truncated_numeric_quote",
                                            f"Amount {entry['amount']} in quote is sliced from a larger numeric token in the source document: {entry['quote'][:120]!r}",
                                        )
                                    )
                                else:
                                    errors.append(
                                        ValidationErrorItem(
                                            f"{ep}.amount",
                                            "ungrounded_usage_amount",
                                            f"Complete integer amount {entry['amount']} does not appear in its verbatim quote: {entry['quote'][:120]!r}",
                                        )
                                    )
                            elif unit_ok:
                                scan_text = (
                                    qm.normalized_quote
                                    if (doc is not None and qm is not None and qm.matched)
                                    else entry["quote"]
                                )
                                unit_bound = extract_unit_bound_amounts(scan_text, entry["unit"], integers=intact_ints)
                                if entry["amount"] not in unit_bound:
                                    errors.append(
                                        ValidationErrorItem(
                                            f"{ep}.unit",
                                            "ungrounded_usage_unit",
                                            f"Amount {entry['amount']} is not paired with unit {entry['unit']!r} in quote: {entry['quote'][:120]!r}",
                                        )
                                    )
                        if isinstance(entry["quote"], str) and entry["quote"].strip():
                            dehy_q = dehyphenate_and_normalize(entry["quote"])
                            span_start = -1
                            span_end = -1
                            if doc is not None and qm is not None and qm.matched:
                                idx_d = doc.dehyphenated_text.find(dehy_q)
                                if idx_d != -1:
                                    span_start, span_end = idx_d, idx_d + len(dehy_q)
                                elif qm.char_offset is not None:
                                    span_start, span_end = qm.char_offset, qm.char_offset + len(qm.normalized_quote)
                            for prev_path, ps, pe, prev_dehy in seen_spans:
                                span_overlap = (
                                    span_start != -1
                                    and ps != -1
                                    and span_start < pe
                                    and ps < span_end
                                )
                                text_overlap = (dehy_q == prev_dehy) or (dehy_q in prev_dehy) or (prev_dehy in dehy_q)
                                if span_overlap or text_overlap:
                                    errors.append(
                                        ValidationErrorItem(
                                            f"{ep}.quote",
                                            "duplicate_usage_quote_span",
                                            f"Usage quote overlaps evidence already cited by {prev_path} (distinct line items require disjoint documentary evidence)",
                                        )
                                    )
                                    break
                            seen_spans.append((ep, span_start, span_end, dehy_q))

                _check_one_list(m_val, f"{claim_path}.method_usage", method_node_name)
                _check_one_list(c_val, f"{claim_path}.control_usage", control_node_name)

                if r_val is not None:
                    rpath = f"{claim_path}.reconciliations"
                    if not isinstance(r_val, list):
                        errors.append(ValidationErrorItem(rpath, "type_error", "Expected list of reconciliation entries"))
                    else:
                        valid_arms = {a for a in (method_node_name, control_node_name) if a is not None}
                        for j, rec in enumerate(r_val):
                            rp = f"{rpath}[{j}]"
                            if not _check_allowed_keys(
                                rec,
                                {"arm", "dimension", "unit", "reconciled_total", "receipt", "quote", "expected_receipts"},
                                {"arm", "dimension", "unit", "reconciled_total", "receipt", "quote"},
                                rp,
                                errors,
                            ):
                                continue
                            check_node_ref(rec["arm"], f"{rp}.arm")
                            if rec["arm"] not in valid_arms:
                                errors.append(
                                    ValidationErrorItem(
                                        f"{rp}.arm",
                                        "mismatched_usage_arm",
                                        f"Reconciliation arm {rec['arm']!r} must match method or control node",
                                    )
                                )
                            if rec["dimension"] not in tag_set:
                                errors.append(
                                    ValidationErrorItem(f"{rp}.dimension", "unknown_tag", f"Unknown tag {rec['dimension']!r}")
                                )
                            unit_ok = _check_nonempty_str(rec["unit"], f"{rp}.unit", errors) is not None
                            _check_nonempty_str(rec["receipt"], f"{rp}.receipt", errors)
                            valid_tot = (
                                isinstance(rec["reconciled_total"], int)
                                and not isinstance(rec["reconciled_total"], bool)
                                and rec["reconciled_total"] >= 0
                            )
                            if not valid_tot:
                                errors.append(
                                    ValidationErrorItem(
                                        f"{rp}.reconciled_total",
                                        "invalid_amount",
                                        "reconciled_total must be a non-negative integer",
                                    )
                                )
                            if "expected_receipts" in rec:
                                if not isinstance(rec["expected_receipts"], list):
                                    errors.append(
                                        ValidationErrorItem(f"{rp}.expected_receipts", "type_error", "Expected list of strings")
                                    )
                                else:
                                    for k, er in enumerate(rec["expected_receipts"]):
                                        _check_nonempty_str(er, f"{rp}.expected_receipts[{k}]", errors)
                            before_q_len = len(quotes)
                            check_quote(rec["quote"], f"{rp}.quote")
                            qm = quotes[-1] if len(quotes) > before_q_len else None
                            if valid_tot and isinstance(rec["quote"], str):
                                intact_ints, truncated_vals = extract_doc_bounded_quote_integers(
                                    rec["quote"], doc=doc, qm=qm
                                )
                                parsed_ints = {v for v, _, _ in intact_ints}
                                if rec["reconciled_total"] not in parsed_ints:
                                    code = "truncated_numeric_quote" if rec["reconciled_total"] in truncated_vals else "ungrounded_usage_amount"
                                    errors.append(
                                        ValidationErrorItem(
                                            f"{rp}.reconciled_total",
                                            code,
                                            f"Reconciled total {rec['reconciled_total']} not intact in quote: {rec['quote'][:120]!r}",
                                        )
                                    )
                                elif unit_ok:
                                    scan_text = (
                                        qm.normalized_quote
                                        if (doc is not None and qm is not None and qm.matched)
                                        else rec["quote"]
                                    )
                                    if rec["reconciled_total"] not in extract_unit_bound_amounts(
                                        scan_text, rec["unit"], integers=intact_ints
                                    ):
                                        errors.append(
                                            ValidationErrorItem(
                                                f"{rp}.unit",
                                                "ungrounded_usage_unit",
                                                f"Reconciled total {rec['reconciled_total']} not paired with unit {rec['unit']!r} in quote",
                                            )
                                        )
                            if isinstance(rec["quote"], str) and rec["quote"].strip():
                                dehy_q = dehyphenate_and_normalize(rec["quote"])
                                span_start = -1
                                span_end = -1
                                if doc is not None and qm is not None and qm.matched:
                                    idx_d = doc.dehyphenated_text.find(dehy_q)
                                    if idx_d != -1:
                                        span_start, span_end = idx_d, idx_d + len(dehy_q)
                                    elif qm.char_offset is not None:
                                        span_start, span_end = qm.char_offset, qm.char_offset + len(qm.normalized_quote)
                                for prev_path, ps, pe, prev_dehy in seen_spans:
                                    span_overlap = span_start != -1 and ps != -1 and span_start < pe and ps < span_end
                                    text_overlap = (dehy_q == prev_dehy) or (dehy_q in prev_dehy) or (prev_dehy in dehy_q)
                                    if span_overlap or text_overlap:
                                        errors.append(
                                            ValidationErrorItem(
                                                f"{rp}.quote",
                                                "duplicate_usage_quote_span",
                                                f"Reconciliation quote overlaps evidence already cited by {prev_path}",
                                            )
                                        )
                                        break
                                seen_spans.append((rp, span_start, span_end, dehy_q))

            if kind in ("emergesWithout", "uniqueRecovery"):
                check_defined_endpoint(cl["target"], f"{p}.target")
                if cl["tag"] not in tag_set:
                    errors.append(ValidationErrorItem(f"{p}.tag", "unknown_tag", f"Unknown tag {cl['tag']!r}"))
            elif kind == "emergesWithExclusion":
                check_defined_endpoint(cl["target"], f"{p}.target")
                check_defined_endpoint(cl["excluded_channel"], f"{p}.excluded_channel")
                if cl["tag"] not in tag_set:
                    errors.append(ValidationErrorItem(f"{p}.tag", "unknown_tag", f"Unknown tag {cl['tag']!r}"))
            elif kind == "independentConvergence":
                check_defined_endpoint(cl["branch_a"], f"{p}.branch_a")
                check_defined_endpoint(cl["branch_b"], f"{p}.branch_b")
                if cl["tag"] not in tag_set:
                    errors.append(ValidationErrorItem(f"{p}.tag", "unknown_tag", f"Unknown tag {cl['tag']!r}"))
            elif kind == "effectivenessClaim":
                check_defined_endpoint(cl["method_node"], f"{p}.method_node")
                check_defined_endpoint(cl["evaluation_node"], f"{p}.evaluation_node")
                if cl["control_node"] is not None:
                    check_defined_endpoint(cl["control_node"], f"{p}.control_node")
                if cl["cost_ledger_node"] is not None:
                    check_defined_endpoint(cl["cost_ledger_node"], f"{p}.cost_ledger_node")
                if cl["cost_tag"] not in tag_set:
                    errors.append(
                        ValidationErrorItem(f"{p}.cost_tag", "unknown_tag", f"Unknown tag {cl['cost_tag']!r}")
                    )
                check_effectiveness_usages(
                    cl["method_usage"],
                    cl["control_usage"],
                    cl.get("reconciliations"),
                    p,
                    cl["method_node"],
                    cl["control_node"],
                )
            else:  # conditionalFlow
                check_defined_endpoint(cl["target"], f"{p}.target")
                if not isinstance(cl["declared_sources"], list):
                    errors.append(ValidationErrorItem(f"{p}.declared_sources", "type_error", "Expected list of nodes"))
                else:
                    for j, ds in enumerate(cl["declared_sources"]):
                        check_node_ref(ds, f"{p}.declared_sources[{j}]")

    return errors, quotes
