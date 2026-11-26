"""Strict JSON schema validation, Lean identifier hygiene, and verbatim quote grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
VALID_DISCHARGE = frozenset({"discharged", "bet", "knownFalse"})
VALID_CLAIM_KINDS = frozenset(
    {
        "emergesWithout",
        "emergesWithExclusion",
        "independentConvergence",
        "uniqueRecovery",
        "conditionalFlow",
        "effectivenessClaim",
        "theoremApplication",
        "outOfScope",
    }
)
VALID_CLAIM_PROVENANCE = frozenset({"authorClaimed", "reviewerStressTest"})
SUPPORTED_SCHEMA_VERSIONS = frozenset({"epistemic-ledger/v2.1", "epistemic-ledger/v2.2", "epistemic-ledger/v2.3"})
# Known legacy/accounting fields that are intentionally out of scope for EpistemicLedger
# (ignored during structural Lean verification and reported explicitly as out of scope).
OUT_OF_SCOPE_EFFECTIVENESS_KEYS = frozenset({"reconciliations"})
OUT_OF_SCOPE_USAGE_KEYS = frozenset({"arm", "receipt", "charge_event", "quantity_kind"})


def collect_out_of_scope_spec_fields(spec: Any) -> list[str]:
    """Return sorted names of known out-of-scope accounting/bookkeeping fields present in `spec`."""
    found: set[str] = set()
    if not isinstance(spec, dict):
        return []
    claims = spec.get("claims")
    if not isinstance(claims, list):
        return []
    for cl in claims:
        if not isinstance(cl, dict) or cl.get("kind") != "effectivenessClaim":
            continue
        for k in OUT_OF_SCOPE_EFFECTIVENESS_KEYS:
            if k in cl:
                found.add(k)
        for ukey in ("method_usage", "control_usage"):
            ulist = cl.get(ukey)
            if isinstance(ulist, list):
                for entry in ulist:
                    if isinstance(entry, dict):
                        for k in OUT_OF_SCOPE_USAGE_KEYS:
                            if k in entry:
                                found.add(k)
    return sorted(found)


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


_MAGNITUDE_SUFFIXES: dict[str, int] = {
    "k": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "billion": 1_000_000_000,
}
_QUOTE_NUM_RE = re.compile(
    r"(?P<num>\d+(?:[.,_]\d+)*)(?:(?P<sp>\s*)(?P<word>thousand|million|billion)\b|(?P<abbr>[KMBkmb])(?![A-Za-z0-9_]))?",
    flags=re.IGNORECASE,
)
_TRAILING_WORD_MAG_RE = re.compile(r"\s*(?:thousand|million|billion)\b", flags=re.IGNORECASE)
_SCI_EXP_RE = re.compile(r"[eE][+-]?\d")
_UNIT_WORD_MAG_RE = re.compile(r"\b(thousand|million|billion)\b", flags=re.IGNORECASE)
_UNIT_ABBR_MAG_RE = re.compile(r"(?:^|[^A-Za-z0-9])([KMB])(?:$|[^A-Za-z0-9])")


def _unit_magnitude_scale(unit: str) -> int:
    """Return the exact magnitude multiplier explicitly named in `unit`
    (e.g. 'million training samples' -> 1_000_000, 'K steps' -> 1_000), or 1 if none."""
    m_word = _UNIT_WORD_MAG_RE.search(unit)
    if m_word:
        return _MAGNITUDE_SUFFIXES[m_word.group(1).lower()]
    m_abbr = _UNIT_ABBR_MAG_RE.search(unit)
    if m_abbr:
        return _MAGNITUDE_SUFFIXES[m_abbr.group(1).lower()]
    return 1


def extract_quote_integers(qtext: str) -> list[tuple[int, int, int]]:
    """Parse complete non-negative integer tokens from `qtext`, returning `(value, start, end)`.

    Supports plain integers (`500`), thousands-grouped integers (`1,500`), and exact scaled
    quantities with `K`/`M`/`B` or `thousand`/`million`/`billion` suffixes (e.g. `21.6M` ->
    `21600000`, `900M` -> `900000000`, `1.5 billion` -> `1500000000`) when the scaled result
    is an exact integer. Never matches a substring inside a larger grouped number (`500` inside
    `1,500`) or an unscaled decimal (`99` inside `99.4`)."""
    results: list[tuple[int, int, int]] = []
    for m in _QUOTE_NUM_RE.finditer(qtext):
        start, end = m.start(), m.end()
        if start > 0 and qtext[start - 1].isalpha():
            continue
        if start > 0 and qtext[start - 1] == "-" and (start == 1 or not qtext[start - 2].isalnum()):
            continue
        if start > 0 and qtext[start - 1] == "." and (start == 1 or not qtext[start - 2].isalpha()):
            continue
        num_tok = m.group("num")
        suffix = (m.group("word") or m.group("abbr") or "").lower()
        if not suffix and end < len(qtext) and _SCI_EXP_RE.match(qtext[end:]):
            continue
        if suffix:
            mult = _MAGNITUDE_SUFFIXES[suffix]
            if re.fullmatch(r"\d+(?:\.\d+)?", num_tok):
                clean = num_tok
            elif re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", num_tok):
                clean = num_tok.replace(",", "")
            else:
                continue
            try:
                scaled = Decimal(clean) * mult
            except InvalidOperation:
                continue
            if scaled == int(scaled):
                results.append((int(scaled), start, end))
        else:
            if re.fullmatch(r"\d+", num_tok):
                results.append((int(num_tok), start, end))
            elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", num_tok):
                results.append((int(num_tok.replace(",", "")), start, end))
    return results


def _has_intact_doc_numeric_boundary(doc_text: str, abs_start: int, abs_end: int) -> bool:
    """Return True iff `doc_text[abs_start:abs_end]` is NOT sliced out of a larger numeric
    or alphanumeric token in the full source document (e.g. `500` sliced from `1,500`, `1500`,
    `-500`, `500.5`, `500,000`, `900M`, or `900 million`)."""
    if abs_start > 0:
        prev = doc_text[abs_start - 1]
        if prev.isdigit() or prev.isalpha():
            return False
        if prev in ",._" and abs_start >= 2 and doc_text[abs_start - 2].isdigit():
            return False
        if prev == "-" and (abs_start == 1 or not doc_text[abs_start - 2].isalnum()):
            return False
        if prev == "." and (abs_start == 1 or not doc_text[abs_start - 2].isalpha()):
            return False
    if abs_end < len(doc_text):
        nxt = doc_text[abs_end]
        if nxt.isdigit():
            return False
        if nxt in ",._" and abs_end + 1 < len(doc_text) and doc_text[abs_end + 1].isdigit():
            return False
        if abs_end > abs_start and doc_text[abs_end - 1].isalpha() and (nxt.isalnum() or nxt == "_"):
            return False
        if abs_end > abs_start and doc_text[abs_end - 1].isdigit():
            if _SCI_EXP_RE.match(doc_text[abs_end:]):
                return False
            if nxt in "KMBkmb" and (
                abs_end + 1 == len(doc_text) or not (doc_text[abs_end + 1].isalnum() or doc_text[abs_end + 1] == "_")
            ):
                return False
            if _TRAILING_WORD_MAG_RE.match(doc_text[abs_end:]):
                return False
    return True


def extract_doc_bounded_quote_integers(
    qtext: str,
    doc: IngestedDocument | None = None,
    qm: QuoteMatch | None = None,
) -> tuple[list[tuple[int, int, int]], set[int]]:
    """Return `(intact_integers, truncated_values)` for `qtext`, checking token boundaries
    against the full source document at the matched offset when `doc` and `qm` are available."""
    if doc is not None and qm is not None and qm.matched and qm.char_offset is not None:
        doc_text = doc.normalized_text if qm.mode == "exact_ws" else doc.dehyphenated_text
        intact: list[tuple[int, int, int]] = []
        truncated: set[int] = set()
        for val, rel_s, rel_e in extract_quote_integers(qm.normalized_quote):
            if _has_intact_doc_numeric_boundary(doc_text, qm.char_offset + rel_s, qm.char_offset + rel_e):
                intact.append((val, rel_s, rel_e))
            else:
                truncated.add(val)
        return intact, truncated
    return extract_quote_integers(qtext), set()


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
            elif kind == "lossy":
                allowed = {"name", "inputs", "output", "kind", "introduces", "loses", "quote", "rationale"}
                required = {"name", "inputs", "output", "kind", "introduces", "quote"}
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
                if kind == "lossy" and "loses" in op:
                    check_tag_list(op["loses"], f"{p}.loses")
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
                base_opt = base_opt | OUT_OF_SCOPE_EFFECTIVENESS_KEYS
            elif kind == "theoremApplication":
                extra = {"target", "hypotheses", "declared_bets"}
            elif kind == "outOfScope":
                extra = {"reason"}
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

            def check_usage_list(val: Any, upath: str) -> None:
                if not isinstance(val, list):
                    errors.append(ValidationErrorItem(upath, "type_error", "Expected list of usage entries"))
                    return
                for j, entry in enumerate(val):
                    ep = f"{upath}[{j}]"
                    if not _check_allowed_keys(
                        entry,
                        {"source", "dimension", "unit", "amount", "quote"} | OUT_OF_SCOPE_USAGE_KEYS,
                        {"source", "dimension", "unit", "amount", "quote"},
                        ep,
                        errors,
                    ):
                        continue
                    check_node_ref(entry["source"], f"{ep}.source")
                    if isinstance(entry["source"], str) and entry["source"] in node_set and entry["source"] not in source_node_set:
                        errors.append(
                            ValidationErrorItem(
                                f"{ep}.source",
                                "unknown_source",
                                f"Usage source {entry['source']!r} must be a declared SourceNode",
                            )
                        )
                    if entry["dimension"] not in tag_set:
                        errors.append(
                            ValidationErrorItem(f"{ep}.dimension", "unknown_tag", f"Unknown tag {entry['dimension']!r}")
                        )
                    _check_nonempty_str(entry["unit"], f"{ep}.unit", errors)
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
                        unit_scale = _unit_magnitude_scale(entry["unit"]) if isinstance(entry.get("unit"), str) else 1
                        effective_amt = entry["amount"] * unit_scale
                        if effective_amt not in parsed_ints:
                            if entry["amount"] in truncated_vals or effective_amt in truncated_vals:
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
                                        f"Scaled amount {effective_amt} ({entry['amount']} with unit {entry['unit']!r}) does not appear in its verbatim quote: {entry['quote'][:120]!r}",
                                    )
                                )

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
                check_usage_list(cl["method_usage"], f"{p}.method_usage")
                check_usage_list(cl["control_usage"], f"{p}.control_usage")
            elif kind == "theoremApplication":
                check_defined_endpoint(cl["target"], f"{p}.target")
                hyps = cl["hypotheses"]
                if not isinstance(hyps, list) or len(hyps) == 0:
                    errors.append(
                        ValidationErrorItem(
                            f"{p}.hypotheses",
                            "empty_list",
                            "theoremApplication must declare at least one hypothesis",
                        )
                    )
                else:
                    seen_hyps: set[str] = set()
                    for j, h in enumerate(hyps):
                        hp = f"{p}.hypotheses[{j}]"
                        if not _check_allowed_keys(
                            h,
                            {"tag", "status", "quote", "rationale"},
                            {"tag", "status", "quote"},
                            hp,
                            errors,
                        ):
                            continue
                        if not isinstance(h["tag"], str) or h["tag"] not in tag_set:
                            errors.append(ValidationErrorItem(f"{hp}.tag", "unknown_tag", f"Unknown tag {h['tag']!r}"))
                        else:
                            if h["tag"] in seen_hyps:
                                errors.append(
                                    ValidationErrorItem(
                                        f"{hp}.tag",
                                        "duplicate_hypothesis",
                                        f"Duplicate hypothesis tag {h['tag']!r} in claim {cl.get('id')!r}",
                                    )
                                )
                            seen_hyps.add(h["tag"])
                        if h["status"] not in VALID_DISCHARGE:
                            errors.append(
                                ValidationErrorItem(
                                    f"{hp}.status",
                                    "invalid_enum",
                                    f"status must be in {sorted(VALID_DISCHARGE)}",
                                )
                            )
                        check_quote(h["quote"], f"{hp}.quote")
                        if "rationale" in h:
                            _check_nonempty_str(h["rationale"], f"{hp}.rationale", errors)
                    check_tag_list(cl["declared_bets"], f"{p}.declared_bets")
                    if isinstance(cl["declared_bets"], list):
                        for j, b in enumerate(cl["declared_bets"]):
                            if isinstance(b, str) and b in tag_set and b not in seen_hyps:
                                errors.append(
                                    ValidationErrorItem(
                                        f"{p}.declared_bets[{j}]",
                                        "orphan_declared_bet",
                                        f"declared_bets tag {b!r} has no matching entry in hypotheses",
                                    )
                                )
                if not isinstance(hyps, list) or len(hyps) == 0:
                    check_tag_list(cl["declared_bets"], f"{p}.declared_bets")
            elif kind == "outOfScope":
                _check_nonempty_str(cl["reason"], f"{p}.reason", errors)
            else:  # conditionalFlow
                check_defined_endpoint(cl["target"], f"{p}.target")
                if not isinstance(cl["declared_sources"], list):
                    errors.append(ValidationErrorItem(f"{p}.declared_sources", "type_error", "Expected list of nodes"))
                else:
                    for j, ds in enumerate(cl["declared_sources"]):
                        check_node_ref(ds, f"{p}.declared_sources[{j}]")

    return errors, quotes
