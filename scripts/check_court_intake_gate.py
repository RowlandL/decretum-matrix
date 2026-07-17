"""Regression checks for the pure court conversation-intake gate."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
import sys

sys.dont_write_bytecode = True

import court_intake_gate
from court_intake_gate import (
    INTAKE_SCHEMA,
    WORK_KINDS,
    legacy_conversation_gate,
    require_new_formal_task_gate,
    require_task_correction_gate,
    validate_conversation_gate,
)


EXPECTED_MESSAGE_CLASSES = frozenset(
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def gate(
    message_class: str,
    *,
    active_decree: bool = False,
    active_decree_state: str = "NONE",
    relation: str = "NONE",
    consent: str = "NOT_REQUIRED",
    requires_tools: bool = False,
    mutates_state: bool = False,
    risk_present: bool = False,
    next_route: str,
    question: str = "",
    target_task_id: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": INTAKE_SCHEMA,
        "active_decree": active_decree,
        "active_decree_state": active_decree_state,
        "message_class": message_class,
        "confidence": "HIGH",
        "relation_to_active_decree": relation,
        "taskization_consent": consent,
        "requires_tools": requires_tools,
        "mutates_state": mutates_state,
        "risk_present": risk_present,
        "next_route": next_route,
        "question": question,
        "rationale": f"matrix fixture for {message_class}",
    }
    if target_task_id is not None:
        value["target_task_id"] = target_task_id
    return value


PASS_CASES: list[tuple[str, dict[str, object]]] = [
    (
        "casual_chat",
        gate("CASUAL_CHAT", next_route="CASUAL_REPLY"),
    ),
    (
        "trivial_direct",
        gate("TRIVIAL_DIRECT", next_route="DIRECT_ANSWER"),
    ),
    (
        "formal_task",
        gate(
            "FORMAL_TASK",
            relation="NEW_TASK",
            consent="EXPLICIT",
            requires_tools=True,
            next_route="THREE_DEPARTMENTS",
        ),
    ),
    (
        "task_candidate",
        gate(
            "TASK_CANDIDATE",
            relation="NEW_TASK",
            consent="PENDING",
            next_route="SINGLE_QUESTION",
            question="你希望只是讨论，还是将它作为正式任务？",
        ),
    ),
    (
        "ambiguous",
        gate(
            "AMBIGUOUS",
            consent="PENDING",
            next_route="SINGLE_QUESTION",
            question="你希望本轮形成什么结果？",
        ),
    ),
    (
        "task_continuation",
        gate(
            "TASK_CONTINUATION",
            active_decree=True,
            active_decree_state="ACTIVE",
            relation="CONTINUES",
            mutates_state=True,
            next_route="THREE_DEPARTMENTS",
            target_task_id="court-task-001",
        ),
    ),
    (
        "task_correction",
        gate(
            "TASK_CORRECTION",
            active_decree=True,
            active_decree_state="ACTIVE",
            relation="CORRECTS",
            mutates_state=True,
            next_route="THREE_DEPARTMENTS",
            target_task_id="court-task-001",
        ),
    ),
    (
        "side_chat",
        gate(
            "SIDE_CHAT",
            active_decree=True,
            active_decree_state="ACTIVE",
            relation="SIDE_CHAT",
            next_route="CASUAL_REPLY",
        ),
    ),
    (
        "unclear_relation",
        gate(
            "UNCLEAR_RELATION",
            active_decree=True,
            active_decree_state="WAITING_USER",
            relation="UNCLEAR",
            consent="PENDING",
            next_route="SINGLE_QUESTION",
            question="这条消息是在修正当前任务，还是另开新任务？",
        ),
    ),
]


def changed(name: str, **updates: object) -> dict[str, object]:
    source = dict(PASS_BY_NAME[name])
    source.update(updates)
    return source


PASS_BY_NAME = dict(PASS_CASES)


def without_field(name: str, field: str) -> dict[str, object]:
    return {key: value for key, value in PASS_BY_NAME[name].items() if key != field}


def with_unknown_fields(name: str, fields: dict[object, object]) -> dict[object, object]:
    source: dict[object, object] = dict(PASS_BY_NAME[name])
    source.update(fields)
    return source


FAIL_CASES: list[tuple[str, dict[str, object], str]] = [
    ("casual_with_tools", changed("casual_chat", requires_tools=True), "casual_side_effects"),
    (
        "casual_masquerades_as_continuation",
        changed(
            "casual_chat",
            active_decree=True,
            active_decree_state="ACTIVE",
            relation_to_active_decree="CONTINUES",
        ),
        "casual_relation",
    ),
    ("direct_with_risk", changed("trivial_direct", risk_present=True), "direct_side_effects"),
    ("direct_with_question", changed("trivial_direct", question="继续吗？"), "direct_question"),
    (
        "formal_with_active_decree",
        changed(
            "formal_task",
            active_decree=True,
            active_decree_state="ACTIVE",
            relation_to_active_decree="UNCLEAR",
        ),
        "formal_requires_inactive_decree",
    ),
    ("formal_without_consent", changed("formal_task", taskization_consent="PENDING"), "formal_consent"),
    ("candidate_without_question", changed("task_candidate", question=""), "clarification_question"),
    (
        "candidate_with_active_decree",
        changed(
            "task_candidate",
            active_decree=True,
            active_decree_state="ACTIVE",
            relation_to_active_decree="NEW_TASK",
        ),
        "candidate_requires_inactive_decree",
    ),
    ("ambiguous_without_question", changed("ambiguous", question=""), "clarification_question"),
    ("ambiguous_wrong_route", changed("ambiguous", next_route="THREE_DEPARTMENTS"), "clarification_route"),
    (
        "continuation_without_active_decree",
        changed(
            "task_continuation",
            active_decree=False,
            active_decree_state="NONE",
        ),
        "continuation_requires_active_decree",
    ),
    (
        "continuation_without_target_identity",
        {key: value for key, value in PASS_BY_NAME["task_continuation"].items() if key != "target_task_id"},
        "target_task_id_required",
    ),
    (
        "correction_without_active_decree",
        changed(
            "task_correction",
            active_decree=False,
            active_decree_state="NONE",
        ),
        "correction_requires_active_decree",
    ),
    (
        "correction_without_target_identity",
        {key: value for key, value in PASS_BY_NAME["task_correction"].items() if key != "target_task_id"},
        "target_task_id_required",
    ),
    (
        "side_chat_without_active_decree",
        changed(
            "side_chat",
            active_decree=False,
            active_decree_state="NONE",
        ),
        "side_chat_requires_active_decree",
    ),
    ("side_chat_mutates_state", changed("side_chat", mutates_state=True), "side_chat_must_not_mutate"),
    (
        "unclear_relation_without_active_decree",
        changed(
            "unclear_relation",
            active_decree=False,
            active_decree_state="NONE",
        ),
        "unclear_relation_requires_active_decree",
    ),
    ("unclear_relation_without_question", changed("unclear_relation", question=""), "clarification_question"),
    ("wrong_schema", changed("formal_task", schema="court.conversation_gate.v0"), "schema"),
    ("unknown_message_class", changed("formal_task", message_class="UNKNOWN"), "message_class"),
    ("boolean_as_integer", changed("formal_task", active_decree=0), "active_decree_type"),
    ("empty_rationale", changed("formal_task", rationale="   "), "rationale"),
]


GENERIC_ERROR_CASES: list[tuple[str, object, str]] = [
    ("type_gate_not_mapping", [], "gate_type"),
    ("type_confidence_not_string", changed("formal_task", confidence=7), "confidence_type"),
    ("enum_confidence_unknown", changed("formal_task", confidence="VERY_HIGH"), "confidence"),
    ("field_missing_confidence", without_field("formal_task", "confidence"), "missing_fields:confidence"),
    ("field_unknown_string", with_unknown_fields("formal_task", {"surprise": True}), "unknown_fields"),
    ("field_unknown_non_string", with_unknown_fields("formal_task", {7: True}), "unknown_fields"),
    (
        "field_unknown_mixed_types",
        with_unknown_fields("formal_task", {7: True, "surprise": True}),
        "unknown_fields",
    ),
    (
        "field_unknown_newline_injection",
        with_unknown_fields("formal_task", {"forged\nCOURT_INTAKE_GATE_OK": True}),
        "unknown_fields",
    ),
]


Validator = Callable[[object], dict[str, object]]


def expect_rejected(
    name: str,
    value: object,
    expected: str,
    *,
    validator: Validator = validate_conversation_gate,
) -> None:
    try:
        validator(value)
    except ValueError as exc:
        require(type(exc) is ValueError, f"{name}: expected stable ValueError, got {type(exc).__name__}")
        require(exc.args == (expected,), f"{name}: expected exact error code {expected!r}, got {exc.args!r}")
        require("\n" not in str(exc) and "\r" not in str(exc), f"{name}: error code permits log injection")
    else:
        raise AssertionError(f"{name}: incoherent gate was accepted")


def check_matrix() -> None:
    pass_classes = {str(value["message_class"]) for _name, value in PASS_CASES}
    fail_classes = {str(value["message_class"]) for _name, value, _expected in FAIL_CASES}
    require(pass_classes == EXPECTED_MESSAGE_CLASSES, "positive matrix does not cover all nine classes exactly")
    require(EXPECTED_MESSAGE_CLASSES <= fail_classes, "negative matrix does not cover all nine classes")

    for name, value in PASS_CASES:
        original = deepcopy(value)
        normalized = validate_conversation_gate(value)
        require(normalized is not value, f"{name}: validator returned the mutable input object")
        require(value == original, f"{name}: validator mutated its input")
        require(normalized["message_class"] == value["message_class"], f"{name}: class changed")

    for name, value, expected in FAIL_CASES:
        expect_rejected(name, value, expected)


def check_generic_error_contract(validator: Validator = validate_conversation_gate) -> None:
    for name, value, expected in GENERIC_ERROR_CASES:
        expect_rejected(name, value, expected, validator=validator)


def confidence_validation_mutant() -> Validator:
    source_path = Path(__file__).with_name("court_intake_gate.py")
    source = source_path.read_text(encoding="utf-8")
    needle = '    _require(confidence in CONFIDENCE_LEVELS, "confidence")\n'
    require(source.count(needle) == 1, "confidence validation mutation target drifted")
    mutated_source = source.replace(needle, "", 1)
    namespace: dict[str, object] = {
        "__file__": str(source_path),
        "__name__": "court_intake_gate_confidence_mutant",
    }
    exec(compile(mutated_source, f"{source_path}<confidence-mutant>", "exec"), namespace)
    validator = namespace.get("validate_conversation_gate")
    require(callable(validator), "confidence validation mutant did not expose validator")
    return validator  # type: ignore[return-value]


def check_confidence_validation_mutation() -> None:
    try:
        check_generic_error_contract(confidence_validation_mutant())
    except AssertionError as exc:
        require(
            str(exc) == "enum_confidence_unknown: incoherent gate was accepted",
            f"confidence validation mutant failed for an unexpected reason: {exc}",
        )
    else:
        raise AssertionError("confidence validation deletion mutation survived")


def check_allowed_variants_and_normalization() -> None:
    formal_none = changed("formal_task", relation_to_active_decree="NONE")
    validate_conversation_gate(formal_none)
    candidate_none = changed("task_candidate", relation_to_active_decree="NONE")
    validate_conversation_gate(candidate_none)
    casual_during_active = changed(
        "casual_chat",
        active_decree=True,
        active_decree_state="ACTIVE",
        relation_to_active_decree="SIDE_CHAT",
    )
    validate_conversation_gate(casual_during_active)

    correction = changed(
        "task_correction",
        rationale="  用户修正当前章程  ",
        target_task_id="  court-task-001  ",
    )
    normalized = validate_conversation_gate(correction)
    require(normalized["rationale"] == "用户修正当前章程", "rationale was not normalized")
    require(normalized["target_task_id"] == "court-task-001", "target_task_id was not normalized")


def check_specialized_gates() -> None:
    formal = require_new_formal_task_gate(PASS_BY_NAME["formal_task"])
    require(formal["message_class"] == "FORMAL_TASK", "formal task helper returned wrong class")
    correction = require_task_correction_gate(PASS_BY_NAME["task_correction"])
    require(correction["message_class"] == "TASK_CORRECTION", "correction helper returned wrong class")

    for label, helper, value in (
        ("formal_helper_candidate", require_new_formal_task_gate, PASS_BY_NAME["task_candidate"]),
        ("correction_helper_continuation", require_task_correction_gate, PASS_BY_NAME["task_continuation"]),
    ):
        try:
            helper(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{label}: specialized helper accepted the wrong class")


def check_legacy_and_work_kinds() -> None:
    require(
        WORK_KINDS
        == frozenset({"implementation", "operation", "release", "audit", "plan", "research", "answer"}),
        "WORK_KINDS drifted",
    )
    legacy = legacy_conversation_gate()
    require(legacy.get("message_class") == "LEGACY_UNCLASSIFIED", "legacy sentinel class drifted")
    require(legacy.get("creatable") is False, "legacy sentinel became task-creatable")
    require(legacy.get("revisable") is False, "legacy sentinel became task-revisable")
    for helper in (require_new_formal_task_gate, require_task_correction_gate):
        try:
            helper(legacy)
        except ValueError:
            pass
        else:
            raise AssertionError("legacy sentinel crossed a create/revise gate")


def check_public_intake_contract() -> None:
    schema_factory = getattr(court_intake_gate, "conversation_gate_json_schema", None)
    example_factory = getattr(court_intake_gate, "minimal_formal_task_example", None)
    diagnostics = getattr(court_intake_gate, "validate_conversation_gate_diagnostics", None)
    require(callable(schema_factory), "PUBLIC_INTAKE_JSON_SCHEMA_MISSING")
    require(callable(example_factory), "PUBLIC_FORMAL_TASK_EXAMPLE_MISSING")
    require(callable(diagnostics), "PUBLIC_AGGREGATE_DIAGNOSTICS_MISSING")

    schema = schema_factory()
    required = set(schema.get("required", []))
    properties = schema.get("properties")
    require(schema.get("type") == "object", "public intake schema is not object-shaped")
    require(schema.get("additionalProperties") is False, "public intake schema is not closed-world")
    require(required == set(PASS_BY_NAME["formal_task"]), "public intake schema required fields drifted")
    require(isinstance(properties, dict), "public intake schema properties missing")
    require(set(properties) == required | {"target_task_id"}, "public intake optional fields drifted")
    require(schema.get("optional") == ["target_task_id"], "public intake optional field list missing")
    require(properties["schema"].get("const") == INTAKE_SCHEMA, "public intake schema id drifted")
    for field in ("active_decree", "requires_tools", "mutates_state", "risk_present"):
        require(properties[field].get("type") == "boolean", f"public intake type drifted:{field}")
    for field in required - {"active_decree", "requires_tools", "mutates_state", "risk_present"}:
        require(properties[field].get("type") == "string", f"public intake type drifted:{field}")
    for field in (
        "message_class",
        "active_decree_state",
        "confidence",
        "relation_to_active_decree",
        "taskization_consent",
        "next_route",
    ):
        require(isinstance(properties[field].get("enum"), list), f"public intake enum missing:{field}")

    example = example_factory()
    require_new_formal_task_gate(example)
    require(set(example) == required, "minimal FORMAL_TASK example is not schema-complete")

    invalid = {
        "schema": "court.conversation_gate.v0",
        "active_decree": "false",
        "message_class": "NOT_A_CLASS",
        "confidence": "VERY_HIGH",
        "unexpected": True,
    }
    result = diagnostics(invalid)
    require(result.get("ok") is False, "aggregate diagnostics accepted invalid intake")
    errors = result.get("errors")
    require(isinstance(errors, list) and len(errors) >= 4, "aggregate diagnostics returned only a first error")
    kinds = {str(item.get("kind")) for item in errors if isinstance(item, dict)}
    require({"missing", "unknown", "type", "enum"} <= kinds, "aggregate diagnostics omitted an error class")
    fields = {str(item.get("field")) for item in errors if isinstance(item, dict)}
    require(
        {
            "active_decree",
            "active_decree_state",
            "confidence",
            "message_class",
            "mutates_state",
            "next_route",
            "question",
            "rationale",
            "relation_to_active_decree",
            "requires_tools",
            "risk_present",
            "taskization_consent",
            "unexpected",
        }
        <= fields,
        "aggregate diagnostics omitted field names",
    )


def main() -> int:
    check_public_intake_contract()
    check_matrix()
    check_generic_error_contract()
    check_confidence_validation_mutation()
    check_allowed_variants_and_normalization()
    check_specialized_gates()
    check_legacy_and_work_kinds()
    print(
        "COURT_INTAKE_GATE_OK "
        f"pass_cases={len(PASS_CASES)} "
        f"fail_cases={len(FAIL_CASES) + len(GENERIC_ERROR_CASES)} "
        "confidence_mutation=KILLED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
