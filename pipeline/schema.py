"""Strict JSON schema validation, Lean identifier hygiene, and verbatim quote grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pipeline.ingest import IngestedDocument, dehyphenate_and_normalize, normalize_whitespace

IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
MIN_QUOTE_NONSPACE_CHARS = 12
MIN_SUBQUOTE_NONSPACE_CHARS = 3
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
VALID_CLAIM_NATURES = frozenset({"qualitative", "quantitative"})
VALID_QUANTITATIVE_KINDS = frozenset({"order", "threshold", "specificValue", "derivedComparison"})
OUT_OF_SCOPE_QUANTITATIVE_KINDS = frozenset({"specificValue", "derivedComparison"})
DEFAULT_NUMERIC_OUT_OF_SCOPE_REASON = (
    "Specific numerical value or derived comparison (ratio/difference from reported numbers): "
    "an ordinary reviewer can check the reported table directly; out of scope for structural epistemic verification."
)
SUPPORTED_SCHEMA_VERSIONS = frozenset(
    {
        "epistemic-ledger/v2.1",
        "epistemic-ledger/v2.2",
        "epistemic-ledger/v2.3",
        "epistemic-ledger/v2.4",
        "epistemic-ledger/v2.5",
    }
)
VALID_ASK_BACK_STATUS = frozenset({"answered", "not_found", "not_applicable"})
VALID_OWN_WORDING_READINGS = frozenset({"same", "sentence_stronger", "sentence_weaker"})
VALID_SLICE_READINGS = frozenset({"within", "beyond"})
VALID_TEST_INPUTS_READINGS = frozenset({"independent", "fitted_on_test_data", "unclear"})
ASK_BACK_QUESTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "E2",
        "causal",
        "Causal/explanatory support: if this clause is read as causal or explanatory, which test, comparison, "
        "or intervention in the paper separates the proposed mechanism from another explanation, and which "
        "alternative explanation does it rule out? (Reuse recorded ops/controls; or status='not_found' with "
        "'searched_where', or status='not_applicable' with 'reason'.)",
    ),
    (
        "E3",
        "own_wording",
        "Paper's own wording elsewhere: does the paper state the same proposition elsewhere outside this claim "
        "sentence? Quote it verbatim (outside the claim sentence), explain why it refers to the same proposition, "
        "object, and conditions, and record reading ('same' | 'sentence_stronger' | 'sentence_weaker') — or "
        "status='not_found' with 'searched_where', or status='not_applicable' with 'reason'.",
    ),
    (
        "E4",
        "slice",
        "Observation slice: on which cases, data, or experimental settings was this actually done? Quote the "
        "verbatim slice, record reading ('within' | 'beyond'), and give 'reason' — or status='not_found' with "
        "'searched_where', or status='not_applicable' with 'reason'.",
    ),
    (
        "E5",
        "test_inputs",
        "Test inputs (answer applicability explicitly with 'reason' if not claiming an empirical test, agreement, "
        "reproduction, or prediction): which input was fitted/inferred from what data, compared against which "
        "output, and does the sentence claim an independent test? Provide verbatim quote(s), 'fitted_inputs', "
        "'compared_output', 'claims_independent_test', 'reading' ('independent' | 'fitted_on_test_data' | "
        "'unclear'), and 'reason' — or status='not_found' with 'searched_where', or status='not_applicable' with 'reason'.",
    ),
    (
        "E6",
        "rests_on",
        "Upstream claim dependence: does this claim rest on another claim in this record? Provide status='answered' "
        "with 'claim_ids' (list of claim IDs in this record, acyclic) and 'reason' (plus optional verbatim 'quote'), "
        "or status='not_applicable' with 'reason' if standalone.",
    ),
)
KIND_ANCHOR_QUESTION = (
    "E7",
    "kind_anchor",
    "Kind anchor for emergesWithout / emergesWithExclusion: provide 'exclusion_wording_quote' (verbatim substring "
    "inside this claim's own quote saying a source is absent, excluded, not needed, or arises on its own) and "
    "'excluded_object' (naming specifically what is excluded). If no exclusion wording exists in the claim, "
    "either reconsider the claim's kind or record ask_back.kind_anchor = {status: 'not_found', searched_where: '...'} "
    "(keeping the reading explicitly marked as unanchored rather than looping).",
)
# Known legacy/accounting/numeric fields that are intentionally out of scope for EpistemicLedger
# (ignored during structural Lean verification and reported explicitly as out of scope).
OUT_OF_SCOPE_EFFECTIVENESS_KEYS = frozenset({"reconciliations", "method_usage", "control_usage"})


def collect_out_of_scope_spec_fields(spec: Any) -> list[str]:
    """Return sorted names of known out-of-scope accounting/numeric fields present in `spec`."""
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


_ABBREV_RE = re.compile(
    r"(?:^|[\s(])(?:Eq|Fig|Figs|Sec|Secs|Tab|No|Ref|Refs|Vol|Prop|Thm|Lem|Def|App|vs|al|e\.g|i\.e|cf|etc|Dr|Mr|Ms|Prof|v|U\.S)\.$",
    flags=re.IGNORECASE,
)


def _is_sentence_end_at(text: str, idx: int) -> bool:
    ch = text[idx]
    if ch not in ".!?":
        return False
    if ch == "." and idx > 0 and idx + 1 < len(text) and text[idx - 1].isdigit() and text[idx + 1].isdigit():
        return False
    j = idx + 1
    while j < len(text) and text[j] in "\"')]}”’":
        j += 1
    if j < len(text) and not text[j].isspace():
        return False
    if ch == "." and _ABBREV_RE.search(text[max(0, idx - 12) : idx + 1]):
        return False
    return True


def _enclosing_sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Expand `[start, end)` to its enclosing punctuation-delimited sentence in `text`."""
    s = start
    while s > 0:
        if _is_sentence_end_at(text, s - 1):
            break
        s -= 1
    while s < start and (text[s].isspace() or text[s] in "\"')]}”’"):
        s += 1
    e = end
    n = len(text)
    k = end - 1
    while k >= start and text[k] in "\"')]}”’":
        k -= 1
    if not (k >= start and _is_sentence_end_at(text, k)):
        while e < n:
            if _is_sentence_end_at(text, e):
                e += 1
                while e < n and text[e] in "\"')]}”’":
                    e += 1
                break
            e += 1
    return (s, e)


def _has_nonempty_str(val: Any) -> bool:
    return isinstance(val, str) and bool(val.strip())


def _has_quote_or_quotes(entry: dict[str, Any]) -> bool:
    if _has_nonempty_str(entry.get("quote")):
        return True
    qs = entry.get("quotes")
    return isinstance(qs, list) and len(qs) > 0 and all(_has_nonempty_str(q) for q in qs)


def _ask_back_entry_missing_fields(qkey: str, entry: dict[str, Any]) -> list[str]:
    """Return missing required sub-fields for a partial ask-back answer (treated as incomplete
    rather than a fatal structural error so `ask` reports what is missing and `run` still emits Lean proofs)."""
    missing: list[str] = []
    st = entry.get("status")
    valid_st = (
        {"not_found"}
        if qkey == "kind_anchor"
        else ({"answered", "not_applicable"} if qkey == "rests_on" else VALID_ASK_BACK_STATUS)
    )
    if st not in valid_st:
        return ["status"]
    if st == "not_found":
        if not _has_nonempty_str(entry.get("searched_where")):
            missing.append("searched_where")
        return missing
    if st == "not_applicable":
        if not _has_nonempty_str(entry.get("reason")):
            missing.append("reason")
        return missing
    # st == "answered"
    if qkey == "causal":
        if not _has_quote_or_quotes(entry):
            missing.append("quote/quotes")
        if not _has_nonempty_str(entry.get("rules_out")):
            missing.append("rules_out")
    elif qkey == "own_wording":
        if not _has_nonempty_str(entry.get("quote")):
            missing.append("quote")
        if not _has_nonempty_str(entry.get("same_proposition_reason")):
            missing.append("same_proposition_reason")
        if entry.get("reading") not in VALID_OWN_WORDING_READINGS:
            missing.append("reading")
    elif qkey == "slice":
        if not _has_quote_or_quotes(entry):
            missing.append("quote/quotes")
        if entry.get("reading") not in VALID_SLICE_READINGS:
            missing.append("reading")
        if not _has_nonempty_str(entry.get("reason")):
            missing.append("reason")
    elif qkey == "test_inputs":
        if not _has_quote_or_quotes(entry):
            missing.append("quote/quotes")
        if not _has_nonempty_str(entry.get("fitted_inputs")):
            missing.append("fitted_inputs")
        if not _has_nonempty_str(entry.get("compared_output")):
            missing.append("compared_output")
        if not isinstance(entry.get("claims_independent_test"), bool):
            missing.append("claims_independent_test")
        if entry.get("reading") not in VALID_TEST_INPUTS_READINGS:
            missing.append("reading")
        if not _has_nonempty_str(entry.get("reason")):
            missing.append("reason")
    elif qkey == "rests_on":
        if not isinstance(entry.get("claim_ids"), list):
            missing.append("claim_ids")
        if not _has_nonempty_str(entry.get("reason")):
            missing.append("reason")
    return missing


def is_ask_back_entry_complete(qkey: str, entry: Any) -> bool:
    """Return True iff a single ask-back entry (`causal`, `own_wording`, `slice`, `test_inputs`,
    `rests_on`, or `kind_anchor`) has all required fields present (and thus is not a partial draft)."""
    return isinstance(entry, dict) and len(_ask_back_entry_missing_fields(qkey, entry)) == 0


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
    op_name_set: set[str] = set()
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
            op_name = _check_nonempty_str(op["name"], f"{p}.name", errors)
            if op_name is not None:
                op_name_set.add(op_name)
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
        pending_rests_on: list[tuple[str, str, list[str]]] = []

        def check_quote_or_quotes(obj: dict[str, Any], opath: str, required: bool = True) -> None:
            has_q = "quote" in obj
            has_qs = "quotes" in obj
            if has_q and has_qs:
                errors.append(
                    ValidationErrorItem(opath, "ambiguous_quote_keys", "Provide either 'quote' or 'quotes', not both")
                )
            elif has_q:
                check_quote(obj["quote"], f"{opath}.quote")
            elif has_qs:
                qs = obj["quotes"]
                if not isinstance(qs, list):
                    errors.append(
                        ValidationErrorItem(f"{opath}.quotes", "type_error", "Expected list of verbatim quotes")
                    )
                elif len(qs) == 0 and required:
                    errors.append(
                        ValidationErrorItem(f"{opath}.quotes", "empty_list", "Expected non-empty list of verbatim quotes")
                    )
                else:
                    for k_idx, qitem in enumerate(qs):
                        check_quote(qitem, f"{opath}.quotes[{k_idx}]")
            elif required:
                errors.append(
                    ValidationErrorItem(opath, "missing_quote", "Expected verbatim 'quote' or non-empty 'quotes' list")
                )

        def anchor_subquote_match(
            claim_qm_ref: QuoteMatch | None, claim_q: str, sub_q: str, sub_path: str
        ) -> QuoteMatch | None:
            if doc is None or claim_qm_ref is None or not claim_qm_ref.matched or claim_qm_ref.char_offset is None:
                return None
            norm_sq = normalize_whitespace(sub_q)
            norm_cq = normalize_whitespace(claim_q)
            dehy_sq = dehyphenate_and_normalize(sub_q)
            dehy_cq = dehyphenate_and_normalize(claim_q)
            anchored_offset: int | None = None
            anchored_mode = claim_qm_ref.mode
            anchored_norm = norm_sq
            if claim_qm_ref.mode == "exact_ws" and norm_sq in norm_cq:
                anchored_offset = claim_qm_ref.char_offset + norm_cq.find(norm_sq)
                anchored_norm = norm_sq
            elif dehy_sq in dehy_cq:
                if claim_qm_ref.mode == "dehyphenated":
                    anchored_offset = claim_qm_ref.char_offset + dehy_cq.find(dehy_sq)
                else:
                    claim_dehy_off = doc.dehyphenated_text.find(dehy_cq)
                    if claim_dehy_off != -1:
                        anchored_offset = claim_dehy_off + dehy_cq.find(dehy_sq)
                anchored_mode = "dehyphenated"
                anchored_norm = dehy_sq
            if anchored_offset is None:
                return None
            return QuoteMatch(
                path=sub_path,
                quote=sub_q,
                matched=True,
                char_offset=anchored_offset,
                mode=anchored_mode,
                normalized_quote=anchored_norm,
            )

        def check_own_wording_outside_claim(
            claim_qm_ref: QuoteMatch | None, claim_q: str, own_q: str, own_qm_ref: QuoteMatch | None, own_path: str
        ) -> None:
            norm_oq = normalize_whitespace(own_q)
            norm_cq = normalize_whitespace(claim_q)
            dehy_oq = dehyphenate_and_normalize(own_q)
            dehy_cq = dehyphenate_and_normalize(claim_q)
            if doc is not None and claim_qm_ref is not None and claim_qm_ref.matched and claim_qm_ref.char_offset is not None and own_qm_ref is not None and own_qm_ref.matched:
                # Locate claim span and own_wording occurrences in a single coordinate space
                if claim_qm_ref.mode == "exact_ws" and own_qm_ref.mode == "exact_ws":
                    search_text = doc.normalized_text
                    c_start = claim_qm_ref.char_offset
                    c_end = c_start + len(claim_qm_ref.normalized_quote)
                    needle = own_qm_ref.normalized_quote
                    mode_used = "exact_ws"
                else:
                    search_text = doc.dehyphenated_text
                    c_start = search_text.find(dehy_cq)
                    c_end = (c_start + len(dehy_cq)) if c_start != -1 else -1
                    needle = dehy_oq
                    mode_used = "dehyphenated"
                if c_start != -1 and needle:
                    # Expand claim span to its enclosing punctuation-delimited sentence so quoting
                    # another clause from the SAME sentence is caught (Codex #27467 Case 2).
                    sent_start, sent_end = _enclosing_sentence_span(search_text, c_start, c_end)
                    found_outside: int | None = None
                    pos = 0
                    while True:
                        idx = search_text.find(needle, pos)
                        if idx == -1:
                            break
                        o_end = idx + len(needle)
                        if o_end <= sent_start or idx >= sent_end:
                            found_outside = idx
                            break
                        pos = idx + 1
                    if found_outside is None:
                        errors.append(
                            ValidationErrorItem(
                                own_path,
                                "own_wording_inside_claim",
                                "own_wording.quote must appear outside the claim's enclosing sentence",
                            )
                        )
                    else:
                        quotes[-1] = QuoteMatch(
                            path=own_qm_ref.path,
                            quote=own_qm_ref.quote,
                            matched=True,
                            char_offset=found_outside,
                            mode=mode_used,
                            normalized_quote=needle,
                        )
            elif norm_oq and norm_cq and (norm_oq in norm_cq or norm_cq in norm_oq or dehy_oq in dehy_cq or dehy_cq in dehy_oq):
                errors.append(
                    ValidationErrorItem(
                        own_path,
                        "own_wording_inside_claim",
                        "own_wording.quote must appear outside the claim's enclosing sentence",
                    )
                )

        def check_ask_back_entry(
            ab: Any,
            ab_path: str,
            claim_id_ref: str | None,
            claim_kind_ref: str,
            claim_qm_ref: QuoteMatch | None,
            claim_q: Any,
            has_exclusion_wording_quote: bool,
        ) -> None:
            if not isinstance(ab, dict):
                errors.append(ValidationErrorItem(ab_path, "type_error", "ask_back must be an object"))
                return
            allowed_ab_keys = {"causal", "own_wording", "slice", "test_inputs", "rests_on", "kind_anchor"}
            for k in sorted(set(ab.keys()) - allowed_ab_keys):
                errors.append(ValidationErrorItem(f"{ab_path}.{k}", "unknown_key", f"Unknown ask_back key {k!r}"))
            if "kind_anchor" in ab:
                ka_ep = f"{ab_path}.kind_anchor"
                ka_entry = ab["kind_anchor"]
                if claim_kind_ref not in ("emergesWithout", "emergesWithExclusion"):
                    errors.append(
                        ValidationErrorItem(
                            ka_ep,
                            "unexpected_kind_anchor",
                            "ask_back.kind_anchor is only allowed on emergesWithout / emergesWithExclusion claims",
                        )
                    )
                elif not isinstance(ka_entry, dict):
                    errors.append(ValidationErrorItem(ka_ep, "type_error", "kind_anchor must be an object"))
                else:
                    for extra_k in sorted(set(ka_entry.keys()) - {"status", "searched_where", "reason", "notes"}):
                        errors.append(
                            ValidationErrorItem(f"{ka_ep}.{extra_k}", "unknown_key", f"Unknown key {extra_k!r}")
                        )
                    if "status" in ka_entry and ka_entry["status"] != "not_found":
                        errors.append(
                            ValidationErrorItem(
                                f"{ka_ep}.status",
                                "invalid_enum",
                                "ask_back.kind_anchor.status must be 'not_found' (for anchored claims, supply exclusion_wording_quote and excluded_object on the claim)",
                            )
                        )
                    elif ka_entry.get("status") == "not_found" and has_exclusion_wording_quote:
                        errors.append(
                            ValidationErrorItem(
                                ka_ep,
                                "conflicting_kind_anchor",
                                "Cannot supply both exclusion_wording_quote and ask_back.kind_anchor status='not_found'",
                            )
                        )
                    if "searched_where" in ka_entry:
                        _check_nonempty_str(ka_entry["searched_where"], f"{ka_ep}.searched_where", errors)
                    if "reason" in ka_entry:
                        _check_nonempty_str(ka_entry["reason"], f"{ka_ep}.reason", errors)
                    if "notes" in ka_entry:
                        _check_nonempty_str(ka_entry["notes"], f"{ka_ep}.notes", errors)
            for qkey in ("causal", "own_wording", "slice", "test_inputs", "rests_on"):
                if qkey not in ab:
                    continue
                entry = ab[qkey]
                ep = f"{ab_path}.{qkey}"
                if not isinstance(entry, dict):
                    errors.append(ValidationErrorItem(ep, "type_error", f"{qkey} answer must be an object"))
                    continue
                st = entry.get("status")
                valid_st = {"answered", "not_applicable"} if qkey == "rests_on" else VALID_ASK_BACK_STATUS
                if "status" in entry and st not in valid_st:
                    errors.append(
                        ValidationErrorItem(
                            f"{ep}.status", "invalid_enum", f"status must be in {sorted(valid_st)}"
                        )
                    )
                    continue
                if st is None:
                    # Partial draft missing status -> reported as incomplete by `evaluate_ask_back`, not fatal error
                    continue
                if st == "not_found":
                    for extra_k in sorted(set(entry.keys()) - {"status", "searched_where", "reason", "notes"}):
                        errors.append(ValidationErrorItem(f"{ep}.{extra_k}", "unknown_key", f"Unknown key {extra_k!r}"))
                    if "searched_where" in entry:
                        _check_nonempty_str(entry["searched_where"], f"{ep}.searched_where", errors)
                    if "reason" in entry:
                        _check_nonempty_str(entry["reason"], f"{ep}.reason", errors)
                    if "notes" in entry:
                        _check_nonempty_str(entry["notes"], f"{ep}.notes", errors)
                    continue
                if st == "not_applicable":
                    for extra_k in sorted(set(entry.keys()) - {"status", "reason", "notes"}):
                        errors.append(ValidationErrorItem(f"{ep}.{extra_k}", "unknown_key", f"Unknown key {extra_k!r}"))
                    if "reason" in entry:
                        _check_nonempty_str(entry["reason"], f"{ep}.reason", errors)
                    if "notes" in entry:
                        _check_nonempty_str(entry["notes"], f"{ep}.notes", errors)
                    continue

                # st == "answered": validate all PRESENT fields strictly (bad quotes/types/enums fail hard),
                # while missing sub-fields are flagged as incomplete by `evaluate_ask_back` (Codex #27467 Case 1).
                if qkey == "causal":
                    allowed_k = {"status", "quote", "quotes", "rules_out", "supporting_ops", "supporting_nodes", "reason", "notes"}
                    for extra_k in sorted(set(entry.keys()) - allowed_k):
                        errors.append(ValidationErrorItem(f"{ep}.{extra_k}", "unknown_key", f"Unknown key {extra_k!r}"))
                    check_quote_or_quotes(entry, ep, required=False)
                    if "rules_out" in entry:
                        _check_nonempty_str(entry["rules_out"], f"{ep}.rules_out", errors)
                    if "supporting_ops" in entry:
                        if not isinstance(entry["supporting_ops"], list):
                            errors.append(ValidationErrorItem(f"{ep}.supporting_ops", "type_error", "Expected list of op names"))
                        else:
                            for oi, oname in enumerate(entry["supporting_ops"]):
                                if not isinstance(oname, str) or oname not in op_name_set:
                                    errors.append(
                                        ValidationErrorItem(f"{ep}.supporting_ops[{oi}]", "unknown_op", f"Unknown op {oname!r}")
                                    )
                    if "supporting_nodes" in entry:
                        if not isinstance(entry["supporting_nodes"], list):
                            errors.append(ValidationErrorItem(f"{ep}.supporting_nodes", "type_error", "Expected list of nodes"))
                        else:
                            for ni, nname in enumerate(entry["supporting_nodes"]):
                                check_node_ref(nname, f"{ep}.supporting_nodes[{ni}]")
                    if "reason" in entry:
                        _check_nonempty_str(entry["reason"], f"{ep}.reason", errors)
                    if "notes" in entry:
                        _check_nonempty_str(entry["notes"], f"{ep}.notes", errors)
                elif qkey == "own_wording":
                    allowed_k = {"status", "quote", "same_proposition_reason", "reading", "notes"}
                    for extra_k in sorted(set(entry.keys()) - allowed_k):
                        errors.append(ValidationErrorItem(f"{ep}.{extra_k}", "unknown_key", f"Unknown key {extra_k!r}"))
                    if "quote" in entry:
                        before_ow = len(quotes)
                        check_quote(entry["quote"], f"{ep}.quote")
                        own_qm = quotes[-1] if len(quotes) > before_ow else None
                        if isinstance(entry["quote"], str) and isinstance(claim_q, str):
                            check_own_wording_outside_claim(claim_qm_ref, claim_q, entry["quote"], own_qm, f"{ep}.quote")
                    if "same_proposition_reason" in entry:
                        _check_nonempty_str(entry["same_proposition_reason"], f"{ep}.same_proposition_reason", errors)
                    if "reading" in entry and entry["reading"] not in VALID_OWN_WORDING_READINGS:
                        errors.append(
                            ValidationErrorItem(
                                f"{ep}.reading",
                                "invalid_enum",
                                f"reading must be in {sorted(VALID_OWN_WORDING_READINGS)}",
                            )
                        )
                    if "notes" in entry:
                        _check_nonempty_str(entry["notes"], f"{ep}.notes", errors)
                elif qkey == "slice":
                    allowed_k = {"status", "quote", "quotes", "reading", "reason", "notes"}
                    for extra_k in sorted(set(entry.keys()) - allowed_k):
                        errors.append(ValidationErrorItem(f"{ep}.{extra_k}", "unknown_key", f"Unknown key {extra_k!r}"))
                    check_quote_or_quotes(entry, ep, required=False)
                    if "reading" in entry and entry["reading"] not in VALID_SLICE_READINGS:
                        errors.append(
                            ValidationErrorItem(
                                f"{ep}.reading", "invalid_enum", f"reading must be in {sorted(VALID_SLICE_READINGS)}"
                            )
                        )
                    if "reason" in entry:
                        _check_nonempty_str(entry["reason"], f"{ep}.reason", errors)
                    if "notes" in entry:
                        _check_nonempty_str(entry["notes"], f"{ep}.notes", errors)
                elif qkey == "test_inputs":
                    allowed_k = {
                        "status",
                        "quote",
                        "quotes",
                        "fitted_inputs",
                        "compared_output",
                        "claims_independent_test",
                        "reading",
                        "reason",
                        "notes",
                    }
                    for extra_k in sorted(set(entry.keys()) - allowed_k):
                        errors.append(ValidationErrorItem(f"{ep}.{extra_k}", "unknown_key", f"Unknown key {extra_k!r}"))
                    check_quote_or_quotes(entry, ep, required=False)
                    if "fitted_inputs" in entry:
                        _check_nonempty_str(entry["fitted_inputs"], f"{ep}.fitted_inputs", errors)
                    if "compared_output" in entry:
                        _check_nonempty_str(entry["compared_output"], f"{ep}.compared_output", errors)
                    if "claims_independent_test" in entry and not isinstance(entry["claims_independent_test"], bool):
                        errors.append(
                            ValidationErrorItem(
                                f"{ep}.claims_independent_test", "type_error", "claims_independent_test must be a boolean"
                            )
                        )
                    if "reading" in entry and entry["reading"] not in VALID_TEST_INPUTS_READINGS:
                        errors.append(
                            ValidationErrorItem(
                                f"{ep}.reading",
                                "invalid_enum",
                                f"reading must be in {sorted(VALID_TEST_INPUTS_READINGS)}",
                            )
                        )
                    if "reason" in entry:
                        _check_nonempty_str(entry["reason"], f"{ep}.reason", errors)
                    if "notes" in entry:
                        _check_nonempty_str(entry["notes"], f"{ep}.notes", errors)
                elif qkey == "rests_on":
                    allowed_k = {"status", "claim_ids", "reason", "quote", "notes"}
                    for extra_k in sorted(set(entry.keys()) - allowed_k):
                        errors.append(ValidationErrorItem(f"{ep}.{extra_k}", "unknown_key", f"Unknown key {extra_k!r}"))
                    if "reason" in entry:
                        _check_nonempty_str(entry["reason"], f"{ep}.reason", errors)
                    if "quote" in entry:
                        check_quote(entry["quote"], f"{ep}.quote")
                    if "notes" in entry:
                        _check_nonempty_str(entry["notes"], f"{ep}.notes", errors)
                    if "claim_ids" in entry:
                        cids = entry["claim_ids"]
                        if not isinstance(cids, list):
                            errors.append(ValidationErrorItem(f"{ep}.claim_ids", "type_error", "Expected list of claim IDs"))
                        else:
                            valid_refs: list[str] = []
                            for ci, ref_id in enumerate(cids):
                                if not isinstance(ref_id, str) or not ref_id.strip():
                                    errors.append(
                                        ValidationErrorItem(f"{ep}.claim_ids[{ci}]", "invalid_string", "Expected claim ID string")
                                    )
                                else:
                                    valid_refs.append(ref_id)
                            if claim_id_ref is not None:
                                pending_rests_on.append((claim_id_ref, f"{ep}.claim_ids", valid_refs))

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
            base_opt = {"notes", "provenance", "nature", "quantitative_kind", "hedged", "hedge_quote", "ask_back"}
            is_oos_quant = (
                cl.get("nature") == "quantitative"
                and cl.get("quantitative_kind") in OUT_OF_SCOPE_QUANTITATIVE_KINDS
            )
            if kind == "emergesWithout":
                extra = {"target", "tag"}
                base_opt = base_opt | {"exclusion_wording_quote", "excluded_object"}
            elif kind == "emergesWithExclusion":
                extra = {"target", "excluded_channel", "tag"}
                base_opt = base_opt | {"exclusion_wording_quote", "excluded_object"}
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
                }
                base_opt = (
                    base_opt
                    | {"method_measurement_quote", "control_measurement_quote"}
                    | OUT_OF_SCOPE_EFFECTIVENESS_KEYS
                )
            elif kind == "theoremApplication":
                extra = {"target", "hypotheses", "declared_bets"}
            elif kind == "outOfScope":
                if is_oos_quant:
                    extra = set()
                    base_opt = base_opt | {"reason"}
                else:
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
            before_cq = len(quotes)
            check_quote(cl["quote"], f"{p}.quote")
            claim_qm = quotes[-1] if len(quotes) > before_cq else None
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
            is_v24_plus = spec.get("schema_version") in ("epistemic-ledger/v2.4", "epistemic-ledger/v2.5")
            if is_v24_plus and "nature" not in cl:
                errors.append(
                    ValidationErrorItem(
                        f"{p}.nature",
                        "missing_nature",
                        f"{spec.get('schema_version')} claims must declare nature ('qualitative' or 'quantitative')",
                    )
                )
            elif "nature" in cl and cl["nature"] not in VALID_CLAIM_NATURES:
                errors.append(
                    ValidationErrorItem(
                        f"{p}.nature",
                        "invalid_enum",
                        f"nature must be in {sorted(VALID_CLAIM_NATURES)}",
                    )
                )
            if cl.get("nature") == "quantitative":
                if "quantitative_kind" not in cl:
                    errors.append(
                        ValidationErrorItem(
                            f"{p}.quantitative_kind",
                            "missing_quantitative_kind",
                            f"quantitative claim must declare quantitative_kind in {sorted(VALID_QUANTITATIVE_KINDS)}",
                        )
                    )
                elif cl["quantitative_kind"] not in VALID_QUANTITATIVE_KINDS:
                    errors.append(
                        ValidationErrorItem(
                            f"{p}.quantitative_kind",
                            "invalid_enum",
                            f"quantitative_kind must be in {sorted(VALID_QUANTITATIVE_KINDS)}",
                        )
                    )
                elif is_v24_plus:
                    qkind = cl["quantitative_kind"]
                    if qkind in ("order", "threshold") and kind != "effectivenessClaim":
                        errors.append(
                            ValidationErrorItem(
                                f"{p}.kind",
                                "invalid_quantitative_claim_kind",
                                f"quantitative/{qkind} claims must use kind 'effectivenessClaim' so control and cost-accounting structure are checked",
                            )
                        )
                    elif qkind in OUT_OF_SCOPE_QUANTITATIVE_KINDS and kind != "outOfScope":
                        errors.append(
                            ValidationErrorItem(
                                f"{p}.kind",
                                "invalid_quantitative_claim_kind",
                                f"quantitative/{qkind} claims must use kind 'outOfScope'",
                            )
                        )
            elif "quantitative_kind" in cl:
                errors.append(
                    ValidationErrorItem(
                        f"{p}.quantitative_kind",
                        "unexpected_quantitative_kind",
                        "quantitative_kind is only allowed when nature is 'quantitative'",
                    )
                )
            if "hedged" in cl and not isinstance(cl["hedged"], bool):
                errors.append(
                    ValidationErrorItem(f"{p}.hedged", "type_error", "hedged must be a boolean")
                )
            if cl.get("hedged") is True:
                if "hedge_quote" not in cl:
                    errors.append(
                        ValidationErrorItem(
                            f"{p}.hedge_quote",
                            "missing_hedge_quote",
                            "hedged: true requires a verbatim hedge_quote from the document",
                        )
                    )
                else:
                    before_hq = len(quotes)
                    check_quote(cl["hedge_quote"], f"{p}.hedge_quote")
                    hedge_qm = quotes[-1] if len(quotes) > before_hq else None
                    if isinstance(cl["hedge_quote"], str) and isinstance(cl["quote"], str):
                        norm_hq = normalize_whitespace(cl["hedge_quote"])
                        norm_cq = normalize_whitespace(cl["quote"])
                        dehy_hq = dehyphenate_and_normalize(cl["hedge_quote"])
                        dehy_cq = dehyphenate_and_normalize(cl["quote"])
                        if norm_hq and norm_cq and (norm_hq not in norm_cq and dehy_hq not in dehy_cq):
                            errors.append(
                                ValidationErrorItem(
                                    f"{p}.hedge_quote",
                                    "hedge_quote_outside_claim",
                                    "hedge_quote must appear verbatim inside the claim's own quote (attach hedges only to the clause they modify)",
                                )
                            )
                        elif hedge_qm is not None and hedge_qm.matched:
                            anchored = anchor_subquote_match(claim_qm, cl["quote"], cl["hedge_quote"], f"{p}.hedge_quote")
                            if anchored is not None:
                                quotes[-1] = anchored
            elif "hedge_quote" in cl:
                errors.append(
                    ValidationErrorItem(
                        f"{p}.hedge_quote",
                        "unexpected_hedge_quote",
                        "hedge_quote requires hedged: true",
                    )
                )

            # E7: Kind anchor for emergesWithout / emergesWithExclusion (optional on draft, checked by `ask`)
            if "exclusion_wording_quote" in cl:
                ewq = _check_nonempty_str(cl["exclusion_wording_quote"], f"{p}.exclusion_wording_quote", errors)
                if ewq is not None:
                    if len(re.sub(r"\s+", "", ewq)) < MIN_SUBQUOTE_NONSPACE_CHARS:
                        errors.append(
                            ValidationErrorItem(
                                f"{p}.exclusion_wording_quote",
                                "quote_too_short",
                                f"exclusion_wording_quote must contain at least {MIN_SUBQUOTE_NONSPACE_CHARS} non-whitespace characters",
                            )
                        )
                    elif isinstance(cl["quote"], str):
                        norm_ew = normalize_whitespace(ewq)
                        norm_cq = normalize_whitespace(cl["quote"])
                        dehy_ew = dehyphenate_and_normalize(ewq)
                        dehy_cq = dehyphenate_and_normalize(cl["quote"])
                        if norm_ew not in norm_cq and dehy_ew not in dehy_cq:
                            errors.append(
                                ValidationErrorItem(
                                    f"{p}.exclusion_wording_quote",
                                    "exclusion_wording_outside_claim",
                                    "exclusion_wording_quote must appear verbatim inside the claim's own quote",
                                )
                            )
                        else:
                            anchored_ew = anchor_subquote_match(claim_qm, cl["quote"], ewq, f"{p}.exclusion_wording_quote")
                            if anchored_ew is not None:
                                quotes.append(anchored_ew)
            if "excluded_object" in cl:
                _check_nonempty_str(cl["excluded_object"], f"{p}.excluded_object", errors)

            if "ask_back" in cl:
                check_ask_back_entry(
                    cl["ask_back"],
                    f"{p}.ask_back",
                    cid,
                    kind,
                    claim_qm,
                    cl["quote"],
                    has_exclusion_wording_quote="exclusion_wording_quote" in cl,
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
                if "method_measurement_quote" in cl:
                    check_quote(cl["method_measurement_quote"], f"{p}.method_measurement_quote")
                if "control_measurement_quote" in cl and cl["control_measurement_quote"] is not None:
                    check_quote(cl["control_measurement_quote"], f"{p}.control_measurement_quote")
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
                if "reason" in cl:
                    _check_nonempty_str(cl["reason"], f"{p}.reason", errors)
            else:  # conditionalFlow
                check_defined_endpoint(cl["target"], f"{p}.target")
                if not isinstance(cl["declared_sources"], list):
                    errors.append(ValidationErrorItem(f"{p}.declared_sources", "type_error", "Expected list of nodes"))
                else:
                    for j, ds in enumerate(cl["declared_sources"]):
                        check_node_ref(ds, f"{p}.declared_sources[{j}]")

        # Second pass: verify E6 `rests_on` references exist, have no self-loops, and are acyclic.
        rests_adj: dict[str, list[str]] = {}
        rests_path_by_cid: dict[str, str] = {}
        for src_cid, rpath, refs in pending_rests_on:
            rests_path_by_cid[src_cid] = rpath
            cleaned_refs: list[str] = []
            for ri, ref_id in enumerate(refs):
                if ref_id == src_cid:
                    errors.append(
                        ValidationErrorItem(f"{rpath}[{ri}]", "self_rests_on", f"Claim {src_cid!r} cannot rest on itself")
                    )
                elif ref_id not in seen_claim_ids:
                    errors.append(
                        ValidationErrorItem(
                            f"{rpath}[{ri}]",
                            "unknown_rests_on_claim",
                            f"rests_on references unknown claim ID {ref_id!r}",
                        )
                    )
                else:
                    cleaned_refs.append(ref_id)
            rests_adj[src_cid] = cleaned_refs

        visit_state: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=done
        reported_cycle_nodes: set[str] = set()

        def dfs_cycle(node: str) -> None:
            visit_state[node] = 1
            for nxt in rests_adj.get(node, []):
                st_nxt = visit_state.get(nxt, 0)
                if st_nxt == 1:
                    if node not in reported_cycle_nodes:
                        reported_cycle_nodes.add(node)
                        errors.append(
                            ValidationErrorItem(
                                rests_path_by_cid.get(node, "$.claims"),
                                "rests_on_cycle",
                                f"Cyclic rests_on dependency involving claim {node!r} -> {nxt!r}",
                            )
                        )
                elif st_nxt == 0:
                    dfs_cycle(nxt)
            visit_state[node] = 2

        for node_id in sorted(rests_adj.keys()):
            if visit_state.get(node_id, 0) == 0:
                dfs_cycle(node_id)

    return errors, quotes


def evaluate_ask_back(spec: Any) -> dict[str, Any]:
    """Evaluate E2–E7 ask-back completeness per claim (non-blocking for `run`/`compare`/`extract`,
    drives `audit_cli ask` to list still-unanswered questions without emitting any Lean verdict)."""
    if not isinstance(spec, dict) or not isinstance(spec.get("claims"), list):
        return {
            "schema_version": spec.get("schema_version") if isinstance(spec, dict) else None,
            "applicable_v25": False,
            "complete": True,
            "total_claims": 0,
            "unanswered_count": 0,
            "claims": [],
        }

    schema_ver = spec.get("schema_version")
    claims_summary: list[dict[str, Any]] = []
    total_unanswered = 0
    any_ask_back_present = False

    for idx, cl in enumerate(spec["claims"]):
        if not isinstance(cl, dict):
            continue
        cid = str(cl.get("id", f"claim_{idx}"))
        kind = str(cl.get("kind", ""))
        quote = str(cl.get("quote", ""))
        ab = cl.get("ask_back") if isinstance(cl.get("ask_back"), dict) else {}
        if ab or "exclusion_wording_quote" in cl or "excluded_object" in cl:
            any_ask_back_present = True

        is_oos_claim = kind == "outOfScope" or (
            cl.get("nature") == "quantitative" and cl.get("quantitative_kind") in OUT_OF_SCOPE_QUANTITATIVE_KINDS
        )
        if is_oos_claim:
            claims_summary.append(
                {
                    "claim_id": cid,
                    "kind": kind,
                    "quote": quote,
                    "complete": True,
                    "skipped_out_of_scope": True,
                    "answered_states": {},
                    "unanswered": [],
                }
            )
            continue

        answered_states: dict[str, str] = {}
        unanswered: list[dict[str, Any]] = []
        for code, key, qtext in ASK_BACK_QUESTIONS:
            entry = ab.get(key)
            if not isinstance(entry, dict):
                answered_states[key] = "unanswered"
                unanswered.append({"code": code, "field": f"ask_back.{key}", "question": qtext})
            else:
                missing_sub = _ask_back_entry_missing_fields(key, entry)
                if missing_sub:
                    answered_states[key] = "incomplete"
                    missing_paths = ", ".join(f"ask_back.{key}.{m}" for m in missing_sub)
                    unanswered.append(
                        {
                            "code": code,
                            "field": missing_paths,
                            "missing_fields": missing_sub,
                            "question": f"Incomplete `{key}` answer — missing required field(s): {', '.join(missing_sub)}. {qtext}",
                        }
                    )
                else:
                    answered_states[key] = str(entry["status"])

        if kind in ("emergesWithout", "emergesWithExclusion"):
            has_ewq = _has_nonempty_str(cl.get("exclusion_wording_quote"))
            has_obj = _has_nonempty_str(cl.get("excluded_object"))
            ka = ab.get("kind_anchor")
            if has_ewq and has_obj and not (isinstance(ka, dict) and ka.get("status") == "not_found"):
                answered_states["kind_anchor"] = "answered"
            elif isinstance(ka, dict) and ka.get("status") == "not_found" and not has_ewq:
                missing_ka = _ask_back_entry_missing_fields("kind_anchor", ka)
                if missing_ka:
                    answered_states["kind_anchor"] = "incomplete"
                    unanswered.append(
                        {
                            "code": KIND_ANCHOR_QUESTION[0],
                            "field": ", ".join(f"ask_back.kind_anchor.{m}" for m in missing_ka),
                            "missing_fields": missing_ka,
                            "question": f"Incomplete `kind_anchor` answer — missing required field(s): {', '.join(missing_ka)}. {KIND_ANCHOR_QUESTION[2]}",
                        }
                    )
                else:
                    answered_states["kind_anchor"] = "not_found"
            else:
                answered_states["kind_anchor"] = "unanswered"
                missing_parts = []
                if not has_ewq:
                    missing_parts.append("exclusion_wording_quote")
                if not has_obj:
                    missing_parts.append("excluded_object")
                unanswered.append(
                    {
                        "code": KIND_ANCHOR_QUESTION[0],
                        "field": ", ".join(missing_parts) or "kind_anchor",
                        "question": KIND_ANCHOR_QUESTION[2],
                    }
                )

        total_unanswered += len(unanswered)
        claims_summary.append(
            {
                "claim_id": cid,
                "kind": kind,
                "quote": quote,
                "complete": len(unanswered) == 0,
                "skipped_out_of_scope": False,
                "answered_states": answered_states,
                "unanswered": unanswered,
            }
        )

    applicable = schema_ver == "epistemic-ledger/v2.5" or any_ask_back_present
    return {
        "schema_version": schema_ver,
        "applicable_v25": applicable,
        "complete": total_unanswered == 0,
        "total_claims": len(claims_summary),
        "unanswered_count": total_unanswered,
        "claims": claims_summary,
    }
