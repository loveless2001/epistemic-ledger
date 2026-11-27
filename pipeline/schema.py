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
VALID_QUESTION_ASKERS = frozenset({"reader", "human"})
VALID_QUESTION_STATUSES = frozenset({"answered", "partly", "not_in_document"})
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

    top_allowed = {"schema_version", "auditor", "paper_title", "nodes", "tags", "sources", "ops", "claims", "questions"}
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
    seen_claim_ids: set[str] = set()
    if not isinstance(spec["claims"], list) or len(spec["claims"]) == 0:
        errors.append(ValidationErrorItem("$.claims", "empty_list", "Must specify at least one claim"))
    else:
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
            # Legacy keys (`hedged`, `hedge_quote`, `ask_back`, `exclusion_wording_quote`, `excluded_object`)
            # are accepted and silently ignored so older v2.x records still run without errors.
            base_opt = {
                "notes",
                "provenance",
                "nature",
                "quantitative_kind",
                "hedged",
                "hedge_quote",
                "ask_back",
                "exclusion_wording_quote",
                "excluded_object",
            }
            is_oos_quant = (
                cl.get("nature") == "quantitative"
                and cl.get("quantitative_kind") in OUT_OF_SCOPE_QUANTITATIVE_KINDS
            )
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

    # Optional record-level `questions` slot (quote-checked only; never reaches Lean, no verdict effect).
    if "questions" in spec:
        qlist = spec["questions"]
        if not isinstance(qlist, list):
            errors.append(ValidationErrorItem("$.questions", "type_error", "Expected list of question objects"))
        else:
            q_allowed = {
                "about_quote",
                "phrase",
                "question",
                "asked_by",
                "status",
                "answer_quotes",
                "answer",
                "stays_open",
                "searched",
                "claim_id",
            }
            q_base_req = {"about_quote", "phrase", "question", "asked_by", "status"}
            for qi, qitem in enumerate(qlist):
                qp = f"$.questions[{qi}]"
                if not _check_allowed_keys(qitem, q_allowed, q_base_req, qp, errors):
                    continue
                check_quote(qitem["about_quote"], f"{qp}.about_quote")
                phrase = _check_nonempty_str(qitem["phrase"], f"{qp}.phrase", errors)
                if phrase is not None and isinstance(qitem.get("about_quote"), str):
                    about_q = qitem["about_quote"]
                    norm_ph = normalize_whitespace(phrase)
                    norm_ab = normalize_whitespace(about_q)
                    dehy_ph = dehyphenate_and_normalize(phrase)
                    dehy_ab = dehyphenate_and_normalize(about_q)
                    if phrase not in about_q and norm_ph not in norm_ab and dehy_ph not in dehy_ab:
                        errors.append(
                            ValidationErrorItem(
                                f"{qp}.phrase",
                                "phrase_not_in_about_quote",
                                "phrase must appear verbatim inside about_quote",
                            )
                        )
                _check_nonempty_str(qitem["question"], f"{qp}.question", errors)
                if qitem["asked_by"] not in VALID_QUESTION_ASKERS:
                    errors.append(
                        ValidationErrorItem(
                            f"{qp}.asked_by",
                            "invalid_enum",
                            f"asked_by must be in {sorted(VALID_QUESTION_ASKERS)}",
                        )
                    )
                qst = qitem["status"]
                if qst not in VALID_QUESTION_STATUSES:
                    errors.append(
                        ValidationErrorItem(
                            f"{qp}.status",
                            "invalid_enum",
                            f"status must be in {sorted(VALID_QUESTION_STATUSES)}",
                        )
                    )
                elif qst in ("answered", "partly"):
                    if "answer_quotes" not in qitem:
                        errors.append(
                            ValidationErrorItem(
                                f"{qp}.answer_quotes",
                                "missing_key",
                                f"Missing required key 'answer_quotes' for status {qst!r}",
                            )
                        )
                    elif not isinstance(qitem["answer_quotes"], list):
                        errors.append(
                            ValidationErrorItem(
                                f"{qp}.answer_quotes", "type_error", "Expected list of verbatim quotes"
                            )
                        )
                    elif len(qitem["answer_quotes"]) == 0:
                        errors.append(
                            ValidationErrorItem(
                                f"{qp}.answer_quotes",
                                "empty_list",
                                f"status {qst!r} requires at least one verbatim answer_quote",
                            )
                        )
                    else:
                        for aqi, aq in enumerate(qitem["answer_quotes"]):
                            check_quote(aq, f"{qp}.answer_quotes[{aqi}]")
                    if "answer" not in qitem:
                        errors.append(
                            ValidationErrorItem(
                                f"{qp}.answer",
                                "missing_key",
                                f"Missing required key 'answer' for status {qst!r}",
                            )
                        )
                    else:
                        _check_nonempty_str(qitem["answer"], f"{qp}.answer", errors)
                    if qst == "partly":
                        if "stays_open" not in qitem:
                            errors.append(
                                ValidationErrorItem(
                                    f"{qp}.stays_open",
                                    "missing_key",
                                    "Missing required key 'stays_open' for status 'partly'",
                                )
                            )
                        else:
                            _check_nonempty_str(qitem["stays_open"], f"{qp}.stays_open", errors)
                    elif "stays_open" in qitem and qitem["stays_open"] is not None:
                        _check_nonempty_str(qitem["stays_open"], f"{qp}.stays_open", errors)
                    if "searched" in qitem and qitem["searched"] is not None:
                        _check_nonempty_str(qitem["searched"], f"{qp}.searched", errors)
                else:  # qst == "not_in_document"
                    if "answer_quotes" in qitem and qitem["answer_quotes"] is not None:
                        if not isinstance(qitem["answer_quotes"], list):
                            errors.append(
                                ValidationErrorItem(
                                    f"{qp}.answer_quotes", "type_error", "Expected empty list for 'not_in_document'"
                                )
                            )
                        elif len(qitem["answer_quotes"]) > 0:
                            errors.append(
                                ValidationErrorItem(
                                    f"{qp}.answer_quotes",
                                    "unexpected_answer_quotes",
                                    "status 'not_in_document' must not include answer_quotes",
                                )
                            )
                    if "searched" not in qitem:
                        errors.append(
                            ValidationErrorItem(
                                f"{qp}.searched",
                                "missing_key",
                                "Missing required key 'searched' for status 'not_in_document'",
                            )
                        )
                    else:
                        _check_nonempty_str(qitem["searched"], f"{qp}.searched", errors)
                    if "answer" in qitem and qitem["answer"] is not None:
                        _check_nonempty_str(qitem["answer"], f"{qp}.answer", errors)
                    if "stays_open" in qitem and qitem["stays_open"] is not None:
                        _check_nonempty_str(qitem["stays_open"], f"{qp}.stays_open", errors)

                if "claim_id" in qitem and qitem["claim_id"] is not None:
                    qcid = qitem["claim_id"]
                    if not isinstance(qcid, str) or qcid not in seen_claim_ids:
                        errors.append(
                            ValidationErrorItem(
                                f"{qp}.claim_id",
                                "unknown_question_claim",
                                f"Question references unknown claim_id {qcid!r}",
                            )
                        )

    return errors, quotes
