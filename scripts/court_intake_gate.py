"""Pure, fail-closed validation for court conversation-intake decisions."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True


INTAKE_SCHEMA = "court.conversation_gate.v1"
LEGACY_INTAKE_SCHEMA = "court.conversation_gate.legacy.v1"
INTAKE_VALIDATION_SCHEMA = "court.conversation_gate.validation.v1"
UNDERSTANDING_SCHEMA = "court.request_understanding.v1"
UNDERSTANDING_THRESHOLD = 95
UNDERSTANDING_DIMENSIONS = (
    "goal",
    "usage_scenario",
    "key_requirements",
    "acceptance_criteria",
)
UNDERSTANDING_LEVELS = frozenset({"CLEAR", "PARTIAL", "MISSING"})
UNDERSTANDING_ROUTES = frozenset({"DIRECT_EXECUTION", "RESTATE_CONFIRM", "SINGLE_QUESTION"})

WORK_KINDS = frozenset(
    {
        "implementation",
        "operation",
        "release",
        "audit",
        "plan",
        "research",
        "answer",
    }
)

MESSAGE_CLASSES = frozenset(
    {
        "CASUAL_CHAT",
        "TRIVIAL_DIRECT",
        "FORMAL_TASK",
        "TASK_CANDIDATE",
        "AMBIGUOUS",
        "TASK_CONTINUATION",
        "TASK_CORRECTION",
        "SIDE_CHAT",
        "UNCLEAR_RELATION",
    }
)
ACTIVE_DECREE_STATES = frozenset({"NONE", "ACTIVE", "PAUSED", "BLOCKED", "WAITING_USER"})
CONFIDENCE_LEVELS = frozenset({"HIGH", "MEDIUM", "LOW"})
RELATIONS = frozenset({"NONE", "CONTINUES", "CORRECTS", "SIDE_CHAT", "NEW_TASK", "UNCLEAR"})
TASKIZATION_CONSENTS = frozenset({"NOT_REQUIRED", "EXPLICIT", "PENDING"})
NEXT_ROUTES = frozenset({"CASUAL_REPLY", "DIRECT_ANSWER", "THREE_DEPARTMENTS", "SINGLE_QUESTION"})

_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "active_decree",
        "active_decree_state",
        "message_class",
        "confidence",
        "relation_to_active_decree",
        "taskization_consent",
        "requires_tools",
        "mutates_state",
        "risk_present",
        "next_route",
        "question",
        "rationale",
    }
)
_OPTIONAL_FIELDS = frozenset({"target_task_id", "understanding"})
_STRING_FIELDS = (
    "schema",
    "active_decree_state",
    "message_class",
    "confidence",
    "relation_to_active_decree",
    "taskization_consent",
    "next_route",
    "question",
    "rationale",
)
_BOOLEAN_FIELDS = ("active_decree", "requires_tools", "mutates_state", "risk_present")


def request_understanding_json_schema() -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": UNDERSTANDING_SCHEMA,
        "type": "object",
        "required": [
            "schema",
            "score",
            "threshold",
            "dimensions",
            "route",
            "question_target",
            "question",
            "options",
            "restatement",
            "confirmation_required",
        ],
        "properties": {
            "schema": {"const": UNDERSTANDING_SCHEMA},
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "threshold": {"const": UNDERSTANDING_THRESHOLD},
            "dimensions": {
                "type": "object",
                "required": list(UNDERSTANDING_DIMENSIONS),
                "properties": {
                    field: {"enum": sorted(UNDERSTANDING_LEVELS)}
                    for field in UNDERSTANDING_DIMENSIONS
                },
                "additionalProperties": False,
            },
            "route": {"enum": sorted(UNDERSTANDING_ROUTES)},
            "question_target": {
                "enum": [*UNDERSTANDING_DIMENSIONS, "CONFIRMATION", "NONE"]
            },
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
            "restatement": {"type": "string"},
            "confirmation_required": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


def validate_request_understanding(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("understanding_type")
    required = {
        "schema",
        "score",
        "threshold",
        "dimensions",
        "route",
        "question_target",
        "question",
        "options",
        "restatement",
        "confirmation_required",
    }
    if set(value) != required:
        raise ValueError("understanding_fields")
    if value.get("schema") != UNDERSTANDING_SCHEMA:
        raise ValueError("understanding_schema")
    score = value.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("understanding_score")
    if value.get("threshold") != UNDERSTANDING_THRESHOLD:
        raise ValueError("understanding_threshold")
    dimensions = value.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != set(UNDERSTANDING_DIMENSIONS):
        raise ValueError("understanding_dimensions")
    if any(level not in UNDERSTANDING_LEVELS for level in dimensions.values()):
        raise ValueError("understanding_dimension_level")
    route = value.get("route")
    if route not in UNDERSTANDING_ROUTES:
        raise ValueError("understanding_route")
    target = value.get("question_target")
    if target not in {*UNDERSTANDING_DIMENSIONS, "CONFIRMATION", "NONE"}:
        raise ValueError("understanding_question_target")
    question = value.get("question")
    restatement = value.get("restatement")
    options = value.get("options")
    confirmation_required = value.get("confirmation_required")
    if not isinstance(question, str) or not isinstance(restatement, str):
        raise ValueError("understanding_text")
    if not isinstance(options, list) or any(
        not isinstance(option, str) or not option.strip() for option in options
    ):
        raise ValueError("understanding_options")
    if len(options) not in {0, 2, 3, 4}:
        raise ValueError("understanding_option_count")
    if type(confirmation_required) is not bool:
        raise ValueError("understanding_confirmation_type")

    def require_single_question() -> None:
        if (
            not question.strip()
            or "\n" in question
            or "\r" in question
            or question.count("?") + question.count("？") > 1
        ):
            raise ValueError("understanding_single_question_required")

    all_clear = all(level == "CLEAR" for level in dimensions.values())
    if score < UNDERSTANDING_THRESHOLD:
        if route != "SINGLE_QUESTION":
            raise ValueError("understanding_below_threshold_requires_question")
        if all_clear or target not in UNDERSTANDING_DIMENSIONS or dimensions[target] == "CLEAR":
            raise ValueError("understanding_question_target_not_uncertain")
        require_single_question()
        if restatement or confirmation_required:
            raise ValueError("understanding_clarification_state")
    else:
        if not all_clear:
            raise ValueError("understanding_clear_dimensions_required")
        if route == "DIRECT_EXECUTION":
            if target != "NONE" or question or options or confirmation_required:
                raise ValueError("understanding_direct_execution_state")
        elif route == "RESTATE_CONFIRM":
            if target != "CONFIRMATION" or not restatement.strip() or not confirmation_required:
                raise ValueError("understanding_restatement_confirmation_state")
            require_single_question()
        else:
            raise ValueError("understanding_ready_route")
    return {
        "schema": UNDERSTANDING_SCHEMA,
        "score": score,
        "threshold": UNDERSTANDING_THRESHOLD,
        "dimensions": {field: str(dimensions[field]) for field in UNDERSTANDING_DIMENSIONS},
        "route": str(route),
        "question_target": str(target),
        "question": question.strip(),
        "options": [str(option).strip() for option in options],
        "restatement": restatement.strip(),
        "confirmation_required": confirmation_required,
    }


def conversation_gate_json_schema() -> dict[str, object]:
    properties: dict[str, dict[str, object]] = {
        field: {"type": "string"} for field in _STRING_FIELDS
    }
    properties["schema"]["const"] = INTAKE_SCHEMA
    for field in _BOOLEAN_FIELDS:
        properties[field] = {"type": "boolean"}
    properties["message_class"]["enum"] = sorted(MESSAGE_CLASSES)
    properties["active_decree_state"]["enum"] = sorted(ACTIVE_DECREE_STATES)
    properties["confidence"]["enum"] = sorted(CONFIDENCE_LEVELS)
    properties["relation_to_active_decree"]["enum"] = sorted(RELATIONS)
    properties["taskization_consent"]["enum"] = sorted(TASKIZATION_CONSENTS)
    properties["next_route"]["enum"] = sorted(NEXT_ROUTES)
    properties["target_task_id"] = {"type": "string", "minLength": 1}
    properties["understanding"] = request_understanding_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": INTAKE_SCHEMA,
        "type": "object",
        "required": sorted(_REQUIRED_FIELDS),
        "optional": ["target_task_id", "understanding"],
        "properties": properties,
        "additionalProperties": False,
    }


def minimal_request_understanding_example() -> dict[str, object]:
    return {
        "schema": UNDERSTANDING_SCHEMA,
        "score": 100,
        "threshold": UNDERSTANDING_THRESHOLD,
        "dimensions": {field: "CLEAR" for field in UNDERSTANDING_DIMENSIONS},
        "route": "DIRECT_EXECUTION",
        "question_target": "NONE",
        "question": "",
        "options": [],
        "restatement": "The goal, usage scenario, key requirements, and acceptance criteria are explicit.",
        "confirmation_required": False,
    }


def minimal_formal_task_example() -> dict[str, object]:
    return {
        "schema": INTAKE_SCHEMA,
        "active_decree": False,
        "active_decree_state": "NONE",
        "message_class": "FORMAL_TASK",
        "confidence": "HIGH",
        "relation_to_active_decree": "NEW_TASK",
        "taskization_consent": "EXPLICIT",
        "requires_tools": True,
        "mutates_state": True,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "explicit formal task routed through Three Departments",
        "understanding": minimal_request_understanding_example(),
    }


def validate_conversation_gate_diagnostics(value: object) -> dict[str, object]:
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        errors.append({"field": "$", "kind": "type", "code": "gate_type"})
        return {"schema": INTAKE_VALIDATION_SCHEMA, "ok": False, "errors": errors}
    raw = dict(value)
    for field in sorted(_REQUIRED_FIELDS - raw.keys()):
        errors.append({"field": field, "kind": "missing", "code": "required"})
    for field in sorted(raw.keys() - _REQUIRED_FIELDS - _OPTIONAL_FIELDS, key=str):
        errors.append({"field": str(field), "kind": "unknown", "code": "additional_property"})
    for field in _STRING_FIELDS:
        if field in raw and not isinstance(raw[field], str):
            errors.append({"field": field, "kind": "type", "code": "string_required"})
    for field in _BOOLEAN_FIELDS:
        if field in raw and type(raw[field]) is not bool:
            errors.append({"field": field, "kind": "type", "code": "boolean_required"})
    if "target_task_id" in raw and not isinstance(raw["target_task_id"], str):
        errors.append({"field": "target_task_id", "kind": "type", "code": "string_required"})
    if "understanding" in raw and not isinstance(raw["understanding"], dict):
        errors.append({"field": "understanding", "kind": "type", "code": "object_required"})
    enum_fields = {
        "schema": {INTAKE_SCHEMA},
        "message_class": MESSAGE_CLASSES,
        "active_decree_state": ACTIVE_DECREE_STATES,
        "confidence": CONFIDENCE_LEVELS,
        "relation_to_active_decree": RELATIONS,
        "taskization_consent": TASKIZATION_CONSENTS,
        "next_route": NEXT_ROUTES,
    }
    for field, allowed in enum_fields.items():
        if field in raw and isinstance(raw[field], str) and raw[field].strip() not in allowed:
            errors.append({"field": field, "kind": "enum", "code": "unsupported_value"})
    if not errors:
        try:
            normalized = validate_conversation_gate(raw)
        except ValueError as exc:
            code = str(exc)
            errors.append({"field": code.split("_", 1)[0], "kind": "coherence", "code": code})
        else:
            return {
                "schema": INTAKE_VALIDATION_SCHEMA,
                "ok": True,
                "errors": [],
                "value": normalized,
            }
    return {"schema": INTAKE_VALIDATION_SCHEMA, "ok": False, "errors": errors}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _require_no_question(question: str, code: str) -> None:
    _require(question == "", code)


def _require_single_question(question: str) -> None:
    _require(bool(question), "clarification_question")
    _require("\n" not in question and "\r" not in question, "clarification_question")
    _require(question.count("?") + question.count("？") <= 1, "clarification_question")


def _require_no_target(target_task_id: str | None) -> None:
    _require(target_task_id is None, "target_task_id_not_allowed")


def _require_target(target_task_id: str | None) -> None:
    _require(bool(target_task_id), "target_task_id_required")


def validate_conversation_gate(value: object) -> dict[str, object]:
    """Return a normalized gate or raise ValueError for an incoherent decision."""

    _require(isinstance(value, dict), "gate_type")
    raw = dict(value)
    missing = sorted(_REQUIRED_FIELDS - raw.keys())
    _require(not missing, f"missing_fields:{','.join(missing)}")
    unknown = raw.keys() - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
    _require(not unknown, "unknown_fields")

    normalized: dict[str, object] = {}
    for field in _STRING_FIELDS:
        item = raw[field]
        _require(isinstance(item, str), f"{field}_type")
        normalized[field] = item.strip()
    for field in _BOOLEAN_FIELDS:
        item = raw[field]
        _require(type(item) is bool, f"{field}_type")
        normalized[field] = item

    target_task_id: str | None = None
    if "target_task_id" in raw:
        target = raw["target_task_id"]
        _require(isinstance(target, str), "target_task_id_type")
        target_task_id = target.strip()
        _require(bool(target_task_id), "target_task_id_empty")
        normalized["target_task_id"] = target_task_id
    if "understanding" in raw:
        normalized["understanding"] = validate_request_understanding(raw["understanding"])

    schema = str(normalized["schema"])
    active_decree = bool(normalized["active_decree"])
    active_state = str(normalized["active_decree_state"])
    message_class = str(normalized["message_class"])
    confidence = str(normalized["confidence"])
    relation = str(normalized["relation_to_active_decree"])
    consent = str(normalized["taskization_consent"])
    requires_tools = bool(normalized["requires_tools"])
    mutates_state = bool(normalized["mutates_state"])
    risk_present = bool(normalized["risk_present"])
    next_route = str(normalized["next_route"])
    question = str(normalized["question"])
    rationale = str(normalized["rationale"])

    _require(schema == INTAKE_SCHEMA, "schema")
    _require(message_class in MESSAGE_CLASSES, "message_class")
    _require(active_state in ACTIVE_DECREE_STATES, "active_decree_state")
    _require(confidence in CONFIDENCE_LEVELS, "confidence")
    _require(relation in RELATIONS, "relation_to_active_decree")
    _require(consent in TASKIZATION_CONSENTS, "taskization_consent")
    _require(next_route in NEXT_ROUTES, "next_route")
    _require(bool(rationale), "rationale")
    if active_decree:
        _require(active_state != "NONE", "active_decree_state_mismatch")
    else:
        _require(active_state == "NONE", "inactive_decree_state_mismatch")

    if message_class == "CASUAL_CHAT":
        _require(consent == "NOT_REQUIRED", "casual_consent")
        if active_decree:
            _require(relation == "SIDE_CHAT", "casual_relation")
        else:
            _require(relation == "NONE", "casual_relation")
        _require(next_route == "CASUAL_REPLY", "casual_route")
        _require(not requires_tools and not mutates_state and not risk_present, "casual_side_effects")
        _require_no_question(question, "casual_question")
        _require_no_target(target_task_id)

    elif message_class == "TRIVIAL_DIRECT":
        _require(not active_decree and relation == "NONE", "direct_relation")
        _require(consent == "NOT_REQUIRED", "direct_consent")
        _require(next_route == "DIRECT_ANSWER", "direct_route")
        _require(not requires_tools and not mutates_state and not risk_present, "direct_side_effects")
        _require_no_question(question, "direct_question")
        _require_no_target(target_task_id)

    elif message_class == "FORMAL_TASK":
        _require(not active_decree, "formal_requires_inactive_decree")
        _require(relation in {"NONE", "NEW_TASK"}, "formal_relation")
        _require(consent == "EXPLICIT", "formal_consent")
        _require(next_route == "THREE_DEPARTMENTS", "formal_route")
        _require_no_question(question, "formal_question")
        _require_no_target(target_task_id)

    elif message_class == "TASK_CANDIDATE":
        _require(not active_decree, "candidate_requires_inactive_decree")
        _require(relation in {"NONE", "NEW_TASK"}, "candidate_relation")
        _require(consent == "PENDING", "clarification_consent")
        _require(next_route == "SINGLE_QUESTION", "clarification_route")
        _require_single_question(question)
        _require(not requires_tools and not mutates_state and not risk_present, "clarification_side_effects")
        _require_no_target(target_task_id)

    elif message_class == "AMBIGUOUS":
        if not active_decree:
            _require(relation in {"NONE", "NEW_TASK", "UNCLEAR"}, "ambiguous_relation")
        _require(consent == "PENDING", "clarification_consent")
        _require(next_route == "SINGLE_QUESTION", "clarification_route")
        _require_single_question(question)
        _require(not requires_tools and not mutates_state and not risk_present, "clarification_side_effects")
        _require_no_target(target_task_id)

    elif message_class == "TASK_CONTINUATION":
        _require(active_decree, "continuation_requires_active_decree")
        _require(relation == "CONTINUES", "continuation_relation")
        _require(consent == "NOT_REQUIRED", "continuation_consent")
        _require(next_route == "THREE_DEPARTMENTS", "continuation_route")
        _require_no_question(question, "continuation_question")
        _require_target(target_task_id)

    elif message_class == "TASK_CORRECTION":
        _require(active_decree, "correction_requires_active_decree")
        _require(relation == "CORRECTS", "correction_relation")
        _require(consent == "NOT_REQUIRED", "correction_consent")
        _require(next_route == "THREE_DEPARTMENTS", "correction_route")
        _require_no_question(question, "correction_question")
        _require_target(target_task_id)

    elif message_class == "SIDE_CHAT":
        _require(active_decree, "side_chat_requires_active_decree")
        _require(relation == "SIDE_CHAT", "side_chat_relation")
        _require(consent == "NOT_REQUIRED", "side_chat_consent")
        _require(next_route == "CASUAL_REPLY", "side_chat_route")
        _require(not mutates_state, "side_chat_must_not_mutate")
        _require_no_question(question, "side_chat_question")
        _require_no_target(target_task_id)

    elif message_class == "UNCLEAR_RELATION":
        _require(active_decree, "unclear_relation_requires_active_decree")
        _require(relation == "UNCLEAR", "unclear_relation")
        _require(consent == "PENDING", "clarification_consent")
        _require(next_route == "SINGLE_QUESTION", "clarification_route")
        _require_single_question(question)
        _require(not requires_tools and not mutates_state and not risk_present, "clarification_side_effects")
        _require_no_target(target_task_id)

    return normalized


def require_new_formal_task_gate(value: object) -> dict[str, object]:
    """Require FORMAL_TASK + EXPLICIT consent + THREE_DEPARTMENTS route."""

    gate = validate_conversation_gate(value)
    _require(gate["message_class"] == "FORMAL_TASK", "new_formal_task_gate_required")
    _require(gate["taskization_consent"] == "EXPLICIT", "new_formal_task_gate_required")
    _require(gate["next_route"] == "THREE_DEPARTMENTS", "new_formal_task_gate_required")
    understanding = gate.get("understanding")
    _require(isinstance(understanding, dict), "formal_understanding_required")
    _require(
        int(understanding["score"]) >= UNDERSTANDING_THRESHOLD,
        "formal_understanding_required",
    )
    _require(
        understanding["route"] == "DIRECT_EXECUTION",
        "formal_understanding_confirmation_pending",
    )
    return gate


def require_task_correction_gate(value: object) -> dict[str, object]:
    """Require active TASK_CORRECTION + CORRECTS + THREE_DEPARTMENTS route."""

    gate = validate_conversation_gate(value)
    _require(gate["message_class"] == "TASK_CORRECTION", "task_correction_gate_required")
    _require(gate["active_decree"] is True, "task_correction_gate_required")
    _require(gate["relation_to_active_decree"] == "CORRECTS", "task_correction_gate_required")
    _require(gate["next_route"] == "THREE_DEPARTMENTS", "task_correction_gate_required")
    return gate


def legacy_conversation_gate() -> dict[str, object]:
    """Return a migration sentinel that is readable but cannot create or revise work."""

    return {
        "schema": LEGACY_INTAKE_SCHEMA,
        "active_decree": False,
        "active_decree_state": "NONE",
        "message_class": "LEGACY_UNCLASSIFIED",
        "confidence": "LOW",
        "relation_to_active_decree": "UNCLEAR",
        "taskization_consent": "PENDING",
        "requires_tools": False,
        "mutates_state": False,
        "risk_present": False,
        "next_route": "SINGLE_QUESTION",
        "question": "",
        "rationale": "legacy runtime task requires revise-charter before new work",
        "creatable": False,
        "revisable": False,
    }
