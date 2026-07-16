"""Regression checks for the pure court outcome-acceptance gate."""

from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from court_outcome_gate import (
    ASSESSMENT_SCHEMA,
    OUTCOME_SCHEMA,
    assess_outcome,
    default_outcome_assessment,
    require_completable_assessment,
)
from court_intake_gate import WORK_KINDS


TASK_ID = "task-r4-outcome"
CHARTER_REVISION = 3
CHARTER_SHA256 = "a" * 64
ASSESSED_AT = "2026-07-12T09:10:00Z"
CAPTURED_AT = "2026-07-12T09:00:00Z"
VERIFIED_AT = "2026-07-12T09:01:00Z"
OBSERVED_GATES: set[str] = set()
_ACTIVE_CASE_TOKENS: tuple[object, ...] = ()
_TAINTED_CASE_TOKENS: frozenset[object] = frozenset()


class CaseLedger:
    __slots__ = ("__case_ids", "__seen")

    def __init__(self) -> None:
        object.__setattr__(self, "_CaseLedger__case_ids", ())
        object.__setattr__(self, "_CaseLedger__seen", frozenset())

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ledger storage is capability-owned")

    @property
    def count(self) -> int:
        return len(self.__case_ids)

    @property
    def case_ids(self) -> tuple[str, ...]:
        return self.__case_ids

    def clear(self) -> None:
        object.__setattr__(self, "_CaseLedger__case_ids", ())
        object.__setattr__(self, "_CaseLedger__seen", frozenset())

    def _record(self, case_id: str, capability: object) -> None:
        if not _ACTIVE_CASE_TOKENS or _ACTIVE_CASE_TOKENS[-1] is not capability:
            raise AssertionError("ledger recording outside execute_case ownership")
        if not isinstance(capability, _CaseCapability) or capability.ledger is not self:
            raise AssertionError("ledger capability does not select this ledger")
        if not isinstance(case_id, str) or not case_id or case_id != case_id.strip():
            raise AssertionError(f"invalid case id: {case_id!r}")
        if case_id in self.__seen:
            raise AssertionError(f"duplicate case id: {case_id}")
        object.__setattr__(self, "_CaseLedger__seen", self.__seen | {case_id})
        object.__setattr__(self, "_CaseLedger__case_ids", self.__case_ids + (case_id,))

    def _snapshot(self) -> tuple[tuple[str, ...], frozenset[str]]:
        return self.__case_ids, self.__seen

    def _restore(self, snapshot: tuple[tuple[str, ...], frozenset[str]]) -> None:
        case_ids, seen = snapshot
        object.__setattr__(self, "_CaseLedger__case_ids", case_ids)
        object.__setattr__(self, "_CaseLedger__seen", seen)


class _CaseCapability:
    __slots__ = (
        "ledger",
        "initial_snapshots",
        "expected_snapshots",
        "active_context",
        "tainted_context",
        "tainted",
    )

    def __init__(
        self,
        ledger: CaseLedger,
        expected_snapshot: tuple[tuple[str, ...], frozenset[str]],
    ) -> None:
        self.ledger = ledger
        self.initial_snapshots = {ledger: expected_snapshot}
        self.expected_snapshots = {ledger: expected_snapshot}
        self.active_context: tuple[object, ...] = ()
        self.tainted_context: frozenset[object] = frozenset()
        self.tainted = False


EXECUTED_CASES = CaseLedger()


def execute_case(case_id: str, action, *, ledger: CaseLedger | None = None) -> None:
    global _ACTIVE_CASE_TOKENS, _TAINTED_CASE_TOKENS

    selected_ledger = EXECUTED_CASES if ledger is None else ledger
    selected_snapshot = selected_ledger._snapshot()
    capability = _CaseCapability(selected_ledger, selected_snapshot)
    active_before = _ACTIVE_CASE_TOKENS
    for active_capability in active_before:
        if not isinstance(active_capability, _CaseCapability):
            raise AssertionError("execute_case ownership context corrupted")
        expected_snapshot = active_capability.expected_snapshots.get(selected_ledger)
        if expected_snapshot is None:
            active_capability.initial_snapshots[selected_ledger] = selected_snapshot
            active_capability.expected_snapshots[selected_ledger] = selected_snapshot
        elif selected_snapshot != expected_snapshot:
            raise AssertionError("touched ledger mutated before nested case")

    _ACTIVE_CASE_TOKENS = active_before + (capability,)
    capability.active_context = _ACTIVE_CASE_TOKENS
    capability.tainted_context = _TAINTED_CASE_TOKENS
    try:
        action()
        if _ACTIVE_CASE_TOKENS is not capability.active_context:
            raise AssertionError("active ownership state mutated during case action")
        if capability.tainted or capability in _TAINTED_CASE_TOKENS:
            raise AssertionError("case action caught a failed requirement")
        if _TAINTED_CASE_TOKENS is not capability.tainted_context:
            raise AssertionError("tainted ownership state mutated during case action")
        for touched_ledger, expected_snapshot in capability.expected_snapshots.items():
            if touched_ledger._snapshot() != expected_snapshot:
                raise AssertionError("touched ledger mutated during case action")
        selected_ledger._record(case_id, capability)
        recorded_snapshot = selected_ledger._snapshot()
        for active_capability in capability.active_context:
            if isinstance(active_capability, _CaseCapability):
                active_capability.expected_snapshots[selected_ledger] = recorded_snapshot
    except BaseException:
        for touched_ledger, initial_snapshot in reversed(
            tuple(capability.initial_snapshots.items())
        ):
            touched_ledger._restore(initial_snapshot)
        for active_capability in active_before:
            if not isinstance(active_capability, _CaseCapability):
                continue
            active_capability.tainted = True
            for touched_ledger in capability.initial_snapshots:
                if touched_ledger in active_capability.expected_snapshots:
                    active_capability.expected_snapshots[
                        touched_ledger
                    ] = touched_ledger._snapshot()
        capability.tainted = True
        _TAINTED_CASE_TOKENS = capability.tainted_context.union(
            capability.active_context
        )
        raise
    finally:
        if capability in _TAINTED_CASE_TOKENS:
            _TAINTED_CASE_TOKENS = frozenset(
                token for token in _TAINTED_CASE_TOKENS if token is not capability
            )
        _ACTIVE_CASE_TOKENS = active_before


def require(condition: bool, message: str) -> None:
    global _TAINTED_CASE_TOKENS

    if not _ACTIVE_CASE_TOKENS:
        raise AssertionError("assertion helper outside active execute_case")
    if not condition:
        capability = _ACTIVE_CASE_TOKENS[-1]
        if isinstance(capability, _CaseCapability):
            capability.tainted = True
        _TAINTED_CASE_TOKENS = _TAINTED_CASE_TOKENS.union((capability,))
        raise AssertionError(message)


def expect_case_failure(
    case_id: str,
    action,
    *,
    expected_message: str | None = None,
    expected_message_prefix: str | None = None,
    ledger: CaseLedger | None = None,
) -> None:
    global _TAINTED_CASE_TOKENS

    if not _ACTIVE_CASE_TOKENS:
        raise AssertionError("expected-failure helper outside active execute_case")
    if (expected_message is None) == (expected_message_prefix is None):
        raise AssertionError("expected-failure helper requires one message matcher")

    selected_ledger = EXECUTED_CASES if ledger is None else ledger
    selected_snapshot = selected_ledger._snapshot()
    tainted_before = _TAINTED_CASE_TOKENS
    active_taint_before = {
        capability: capability.tainted
        for capability in _ACTIVE_CASE_TOKENS
        if isinstance(capability, _CaseCapability)
    }
    try:
        execute_case(case_id, action, ledger=selected_ledger)
    except AssertionError as exc:
        actual_message = str(exc)
        matched = (
            actual_message == expected_message
            if expected_message is not None
            else actual_message.startswith(expected_message_prefix or "")
        )
        if not matched:
            raise AssertionError(
                f"expected failure mismatch for {case_id}: {actual_message}"
            ) from exc
        if selected_ledger._snapshot() != selected_snapshot:
            selected_ledger._restore(selected_snapshot)
            raise AssertionError(f"expected failure changed ledger for {case_id}") from exc
        for active_capability, was_tainted in active_taint_before.items():
            active_capability.tainted = was_tainted
        _TAINTED_CASE_TOKENS = tainted_before
        return

    selected_ledger._restore(selected_snapshot)
    for active_capability in _ACTIVE_CASE_TOKENS:
        if (
            isinstance(active_capability, _CaseCapability)
            and active_capability.ledger is selected_ledger
        ):
            active_capability.expected_snapshots[selected_ledger] = selected_snapshot
    require(False, f"expected case failure did not occur: {case_id}")


def has_reason(reasons: object, expected: str) -> bool:
    if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
        return False
    if ":" in expected:
        return expected in reasons
    return any(reason == expected or reason.startswith(f"{expected}:") for reason in reasons)


def require_reason(assessment: dict[str, object], expected: str, label: str) -> None:
    require(
        has_reason(assessment.get("reasons"), expected),
        f"{label}: missing reason {expected}: {assessment}",
    )


def require_error(exc: ValueError, expected: str, label: str) -> None:
    require(str(exc) == expected, f"{label}: expected {expected}, got {exc}")


def validate_checker_contract(source: str, filename: str = "<checker>") -> list[str]:
    """Return stable checker-ownership violations for source or a synthetic mutant."""

    if not isinstance(source, str):
        return ["checker_source_type"]
    try:
        module = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"checker_syntax_error:{exc.lineno or 0}"]

    violations: list[str] = []

    def add(code: str, detail: str = "") -> None:
        violation = f"{code}:{detail}" if detail else code
        if violation not in violations:
            violations.append(violation)

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "record_case":
            add("record_case_escape_hatch", f"definition:{node.lineno}")
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_case"
        ):
            add("record_case_escape_hatch", f"call:{node.lineno}")

    accounting_self_contracts = {
        "check_case_count_contract",
        "check_rework4_case_accounting_contract",
        "check_rework7_capability_ledger_binding_contract",
        "check_rework7_cross_ledger_transaction_contract",
    }
    expected_failure_self_contracts = {
        "check_case_count_contract",
        "check_rework6_expected_failure_isolation_contract",
    }
    failure_suppression_self_contracts = {
        "check_rework4_case_accounting_contract",
        "check_rework5_runtime_ownership_contract",
        "check_rework6_expected_failure_isolation_contract",
        "check_rework6_nested_failure_runtime_contract",
        "check_rework7_capability_ledger_binding_contract",
        "check_rework7_cross_ledger_transaction_contract",
        "check_rework7_runtime_ownership_mutation_contract",
    }
    ownership_state_self_contracts = {
        "check_rework7_runtime_ownership_mutation_contract",
    }
    function_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    module_suppression_aliases = {"suppress"}
    for node in module.body:
        if isinstance(node, ast.ImportFrom) and node.module == "contextlib":
            module_suppression_aliases.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "suppress"
            )

    def catches_assertion_error(handler: ast.ExceptHandler) -> bool:
        if handler.type is None:
            return True
        exception_names = {
            node.id for node in ast.walk(handler.type) if isinstance(node, ast.Name)
        }
        return bool(exception_names & {"AssertionError", "Exception", "BaseException"})

    def handler_always_reraises(handler: ast.ExceptHandler) -> bool:
        return bool(handler.body) and isinstance(handler.body[0], ast.Raise)

    def exception_names(node: ast.AST) -> set[str]:
        names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
        names.update(
            child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)
        )
        return names

    def is_raw_assertion(node: ast.AST) -> bool:
        if isinstance(node, ast.Assert):
            return True
        if not isinstance(node, ast.Raise) or node.exc is None:
            return False
        raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        return isinstance(raised, ast.Name) and raised.id == "AssertionError"

    for function in module.body:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not function.name.startswith("check_"):
            continue

        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(function):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        def owner(node: ast.AST) -> ast.AST:
            cursor = node
            while cursor in parents:
                cursor = parents[cursor]
                if isinstance(cursor, function_types):
                    return cursor
            return function

        nested_functions = {
            node.name: node
            for node in ast.walk(function)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not function
        }
        execute_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "execute_case"
        ]
        expected_failure_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "expect_case_failure"
        ]
        root_execute_calls = [node for node in execute_calls if owner(node) is function]
        if not root_execute_calls:
            add("check_without_execute_case", function.name)

        authorized_actions: set[ast.AST] = set()
        for call in execute_calls + expected_failure_calls:
            action = call.args[1] if len(call.args) >= 2 else None
            if action is None:
                action = next(
                    (keyword.value for keyword in call.keywords if keyword.arg == "action"),
                    None,
                )
            if isinstance(action, ast.Name) and action.id in nested_functions:
                authorized_actions.add(nested_functions[action.id])
            elif isinstance(action, ast.Lambda):
                authorized_actions.add(action)

        changed = True
        while changed:
            changed = False
            for action in tuple(authorized_actions):
                for node in ast.walk(action):
                    if owner(node) is not action or not isinstance(node, ast.Call):
                        continue
                    if isinstance(node.func, ast.Name) and node.func.id in nested_functions:
                        reachable = nested_functions[node.func.id]
                        if reachable not in authorized_actions:
                            authorized_actions.add(reachable)
                            changed = True

        if function.name not in expected_failure_self_contracts:
            for call in expected_failure_calls:
                add(
                    "expected_failure_helper_outside_self_contract",
                    f"{function.name}:{call.lineno}",
                )

        for node in ast.walk(function):
            if not isinstance(node, ast.Try) or not any(
                catches_assertion_error(handler) for handler in node.handlers
            ):
                continue
            guarded_nodes = [
                child for statement in node.body for child in ast.walk(statement)
            ]
            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "execute_case"
                for child in guarded_nodes
            ):
                add("nested_case_failure_swallowed", f"{function.name}:{node.lineno}")
            if any(is_raw_assertion(child) for child in guarded_nodes):
                add("raw_assertion_outside_runtime", f"{function.name}:{node.lineno}")

        root_returns = [
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Return) and node.value is not None and owner(node) is function
        ]
        if root_returns:
            add("check_non_none_return", f"{function.name}:{','.join(map(str, root_returns))}")

        assertion_aliases = {"require", "require_reason", "require_error"}
        expected_failure_aliases = {"expect_case_failure"}
        suppression_aliases = set(module_suppression_aliases)
        suppression_aliases.update(
            alias.asname or alias.name
            for node in ast.walk(function)
            if isinstance(node, ast.ImportFrom) and node.module == "contextlib"
            for alias in node.names
            if alias.name == "suppress"
        )
        exception_aliases = {"AssertionError", "Exception", "BaseException"}
        ownership_aliases = {"_ACTIVE_CASE_TOKENS", "_TAINTED_CASE_TOKENS"}
        ownership_mutator_aliases: set[str] = set()
        ledger_aliases = {"EXECUTED_CASES"}
        capability_aliases: set[str] = set()
        capability_snapshot_aliases: set[str] = set()
        capability_fields = {
            "ledger",
            "initial_snapshots",
            "expected_snapshots",
            "active_context",
            "tainted_context",
            "tainted",
        }
        ownership_mutation_methods = {
            "add",
            "append",
            "clear",
            "difference_update",
            "discard",
            "extend",
            "insert",
            "intersection_update",
            "pop",
            "remove",
            "reverse",
            "sort",
            "symmetric_difference_update",
            "update",
        }
        mapping_mutation_methods = ownership_mutation_methods | {
            "__delitem__",
            "__setitem__",
            "setdefault",
        }
        record_aliases: set[str] = set()
        assignments: list[tuple[list[str], ast.AST]] = []
        for node in ast.walk(function):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                raw_targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                targets = [target.id for target in raw_targets if isinstance(target, ast.Name)]
                if targets and node.value is not None:
                    assignments.append((targets, node.value))
        changed = True
        while changed:
            changed = False
            for targets, value in assignments:
                if isinstance(value, ast.Name) and value.id in assertion_aliases:
                    for target in targets:
                        if target not in assertion_aliases:
                            assertion_aliases.add(target)
                            changed = True
                if isinstance(value, ast.Name) and value.id in expected_failure_aliases:
                    for target in targets:
                        if target not in expected_failure_aliases:
                            expected_failure_aliases.add(target)
                            changed = True
                if (
                    isinstance(value, ast.Name) and value.id in suppression_aliases
                ) or (isinstance(value, ast.Attribute) and value.attr == "suppress"):
                    for target in targets:
                        if target not in suppression_aliases:
                            suppression_aliases.add(target)
                            changed = True
                if (
                    isinstance(value, ast.Name) and value.id in exception_aliases
                ) or (
                    isinstance(value, ast.Attribute) and value.attr in exception_aliases
                ):
                    for target in targets:
                        if target not in exception_aliases:
                            exception_aliases.add(target)
                            changed = True
                reflective_ownership_value = (
                    isinstance(value, ast.Subscript)
                    and isinstance(value.value, ast.Call)
                    and isinstance(value.value.func, ast.Name)
                    and value.value.func.id in {"globals", "locals", "vars"}
                    and isinstance(value.slice, ast.Constant)
                    and value.slice.value
                    in {"_ACTIVE_CASE_TOKENS", "_TAINTED_CASE_TOKENS"}
                )
                if (
                    isinstance(value, ast.Name) and value.id in ownership_aliases
                ) or reflective_ownership_value:
                    for target in targets:
                        if target not in ownership_aliases:
                            ownership_aliases.add(target)
                            changed = True
                is_ledger_alias = (
                    isinstance(value, ast.Name) and value.id in ledger_aliases
                ) or (
                    isinstance(value, ast.Attribute)
                    and value.attr == "ledger"
                    and isinstance(value.value, ast.Name)
                    and value.value.id in capability_aliases
                )
                if is_ledger_alias:
                    for target in targets:
                        if target not in ledger_aliases:
                            ledger_aliases.add(target)
                            changed = True
                is_capability_alias = (
                    isinstance(value, ast.Name) and value.id in capability_aliases
                ) or (
                    isinstance(value, ast.Subscript)
                    and isinstance(value.value, ast.Name)
                    and value.value.id in ownership_aliases
                )
                if is_capability_alias:
                    for target in targets:
                        if target not in capability_aliases:
                            capability_aliases.add(target)
                            changed = True
                is_capability_snapshot_alias = (
                    isinstance(value, ast.Name)
                    and value.id in capability_snapshot_aliases
                ) or (
                    isinstance(value, ast.Attribute)
                    and value.attr in {"initial_snapshots", "expected_snapshots"}
                    and isinstance(value.value, ast.Name)
                    and value.value.id in capability_aliases
                )
                if is_capability_snapshot_alias:
                    for target in targets:
                        if target not in capability_snapshot_aliases:
                            capability_snapshot_aliases.add(target)
                            changed = True
                reflective_ownership_mutator = (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "getattr"
                    and len(value.args) >= 2
                    and isinstance(value.args[0], ast.Name)
                    and value.args[0].id in ownership_aliases
                    and isinstance(value.args[1], ast.Constant)
                    and value.args[1].value in ownership_mutation_methods
                )
                if reflective_ownership_mutator or (
                    isinstance(value, ast.Name)
                    and value.id in ownership_mutator_aliases
                ):
                    for target in targets:
                        if target not in ownership_mutator_aliases:
                            ownership_mutator_aliases.add(target)
                            changed = True
                is_record_alias = (
                    isinstance(value, ast.Attribute) and value.attr in {"record", "_record"}
                ) or (isinstance(value, ast.Name) and value.id in record_aliases)
                if is_record_alias:
                    for target in targets:
                        if target not in record_aliases:
                            record_aliases.add(target)
                            changed = True

        def reflective_name(node: ast.AST, expected: str) -> bool:
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id in {"globals", "locals", "vars"}
                and isinstance(node.slice, ast.Constant)
                and node.slice.value == expected
            ):
                return True
            return (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == expected
            )

        if function.name not in expected_failure_self_contracts:
            expected_failure_uses = [
                node
                for node in ast.walk(function)
                if (
                    isinstance(node, ast.Name)
                    and isinstance(node.ctx, ast.Load)
                    and node.id in expected_failure_aliases
                )
                or reflective_name(node, "expect_case_failure")
            ]
            for node in expected_failure_uses:
                add(
                    "expected_failure_helper_outside_self_contract",
                    f"{function.name}:{node.lineno}",
                )

        if function.name not in failure_suppression_self_contracts:
            for node in ast.walk(function):
                if isinstance(node, ast.Try):
                    for handler in node.handlers:
                        catches_check_failure = handler.type is None or bool(
                            exception_names(handler.type) & exception_aliases
                        )
                        if catches_check_failure and not handler_always_reraises(handler):
                            add(
                                "check_failure_suppression",
                                f"{function.name}:{handler.lineno}",
                            )
                if not isinstance(node, (ast.With, ast.AsyncWith)):
                    continue
                for item in node.items:
                    context = item.context_expr
                    if not isinstance(context, ast.Call):
                        continue
                    suppress_call = (
                        isinstance(context.func, ast.Name)
                        and context.func.id in suppression_aliases
                    ) or (
                        isinstance(context.func, ast.Attribute)
                        and context.func.attr == "suppress"
                    )
                    suppressed_names = set().union(
                        *(exception_names(argument) for argument in context.args)
                    ) if context.args else set()
                    if suppress_call and suppressed_names & {
                        "AssertionError",
                        "Exception",
                        "BaseException",
                    }:
                        add(
                            "check_failure_suppression",
                            f"{function.name}:{node.lineno}",
                        )

        if function.name not in ownership_state_self_contracts:
            def ownership_expression(node: ast.AST) -> bool:
                return (
                    isinstance(node, ast.Name) and node.id in ownership_aliases
                ) or reflective_name(node, "_ACTIVE_CASE_TOKENS") or reflective_name(
                    node, "_TAINTED_CASE_TOKENS"
                )

            global_ownership_names = {
                name
                for node in ast.walk(function)
                if isinstance(node, ast.Global)
                for name in node.names
                if name in {"_ACTIVE_CASE_TOKENS", "_TAINTED_CASE_TOKENS"}
            }
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ownership_mutation_methods
                    and ownership_expression(node.func.value)
                ):
                    add(
                        "ownership_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in ownership_mutator_aliases
                ):
                    add(
                        "ownership_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Name)
                    and isinstance(node.ctx, ast.Store)
                    and node.id in global_ownership_names
                ):
                    add(
                        "ownership_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Subscript)
                    and isinstance(node.ctx, (ast.Store, ast.Del))
                    and ownership_expression(node)
                ):
                    add(
                        "ownership_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )

        if function.name not in accounting_self_contracts:
            def ledger_expression(node: ast.AST) -> bool:
                return isinstance(node, ast.Name) and node.id in ledger_aliases

            def capability_expression(node: ast.AST) -> bool:
                return isinstance(node, ast.Name) and node.id in capability_aliases

            def capability_snapshot_expression(node: ast.AST) -> bool:
                return (
                    isinstance(node, ast.Name)
                    and node.id in capability_snapshot_aliases
                ) or (
                    isinstance(node, ast.Attribute)
                    and node.attr in {"initial_snapshots", "expected_snapshots"}
                    and capability_expression(node.value)
                )

            for call in execute_calls:
                if any(keyword.arg == "ledger" for keyword in call.keywords):
                    add(
                        "alternate_ledger_outside_self_contract",
                        f"{function.name}:{call.lineno}",
                    )

            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "__setattr__"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "object"
                    and len(node.args) >= 2
                    and ledger_expression(node.args[0])
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value
                    in {"_case_ids", "_seen", "_CaseLedger__case_ids", "_CaseLedger__seen"}
                ):
                    add(
                        "case_ledger_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "__setattr__"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "object"
                    and len(node.args) >= 2
                    and capability_expression(node.args[0])
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in capability_fields
                ):
                    add(
                        "case_capability_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and ledger_expression(node.func.value)
                    and node.func.attr in {"_record", "_restore", "clear", "record"}
                ):
                    add(
                        "case_ledger_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.ctx, (ast.Store, ast.Del))
                    and ledger_expression(node.value)
                    and node.attr
                    in {"_case_ids", "_seen", "_CaseLedger__case_ids", "_CaseLedger__seen"}
                ):
                    add(
                        "case_ledger_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.ctx, (ast.Store, ast.Del))
                    and capability_expression(node.value)
                    and node.attr in capability_fields
                ):
                    add(
                        "case_capability_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Subscript)
                    and isinstance(node.ctx, (ast.Store, ast.Del))
                    and capability_snapshot_expression(node.value)
                ):
                    add(
                        "case_capability_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and capability_snapshot_expression(node.func.value)
                    and node.func.attr in mapping_mutation_methods
                ):
                    add(
                        "case_capability_state_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Call)
                    and isinstance(node.func.func, ast.Name)
                    and node.func.func.id == "getattr"
                    and len(node.func.args) >= 2
                    and isinstance(node.func.args[0], ast.Name)
                    and node.func.args[0].id == "EXECUTED_CASES"
                    and isinstance(node.func.args[1], ast.Constant)
                    and node.func.args[1].value in {"record", "_record"}
                ):
                    add(
                        "reflective_ledger_record",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "__setattr__"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "object"
                    and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "EXECUTED_CASES"
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value
                    in {"_case_ids", "_seen", "_CaseLedger__case_ids", "_CaseLedger__seen"}
                ):
                    add(
                        "reflective_private_ledger_mutation",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Subscript)
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Name)
                    and node.func.value.func.id == "globals"
                    and isinstance(node.func.slice, ast.Constant)
                    and node.func.slice.value
                    in {"require", "require_reason", "require_error"}
                ):
                    add(
                        "reflective_assertion_helper",
                        f"{function.name}:{node.lineno}",
                    )
                if isinstance(node, ast.Attribute) and node.attr in {"record", "_record"}:
                    add(
                        "ledger_record_outside_execute_case",
                        f"{function.name}:{node.lineno}",
                    )
                if isinstance(node, ast.Attribute) and node.attr in {
                    "_case_ids",
                    "_seen",
                    "_CaseLedger__case_ids",
                    "_CaseLedger__seen",
                }:
                    add(
                        "private_ledger_mutation_outside_execute_case",
                        f"{function.name}:{node.lineno}",
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in record_aliases
                ):
                    add(
                        "ledger_record_outside_execute_case",
                        f"{function.name}:{node.lineno}",
                    )
                assertion_call = (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in assertion_aliases
                )
                assertion_statement = isinstance(node, (ast.Assert, ast.Raise))
                if (
                    (assertion_call or assertion_statement)
                    and owner(node) not in authorized_actions
                ):
                    add(
                        "assertion_helper_outside_execute_case",
                        f"{function.name}:{node.lineno}",
                    )

    main_function = next(
        (
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        ),
        None,
    )
    if main_function is not None:
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "sum"
            for node in ast.walk(main_function)
        ):
            add("main_sums_checker_totals")
        if not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "clear"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "EXECUTED_CASES"
            for node in ast.walk(main_function)
        ):
            add("main_does_not_reset_ledger")

        count_assignments = [
            node
            for node in ast.walk(main_function)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "case_count"
                for target in node.targets
            )
        ]
        ledger_count_assignment = (
            len(count_assignments) == 1
            and isinstance(count_assignments[0].value, ast.Attribute)
            and count_assignments[0].value.attr == "count"
            and isinstance(count_assignments[0].value.value, ast.Name)
            and count_assignments[0].value.value.id == "EXECUTED_CASES"
        )
        if not ledger_count_assignment:
            add("main_output_not_ledger_derived", "case_count_assignment")

        print_uses_case_count = False
        for node in ast.walk(main_function):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                continue
            for argument in node.args:
                if not isinstance(argument, ast.JoinedStr):
                    continue
                for index, part in enumerate(argument.values[:-1]):
                    if not (
                        isinstance(part, ast.Constant)
                        and isinstance(part.value, str)
                        and "cases=" in part.value
                    ):
                        continue
                    formatted = argument.values[index + 1]
                    if (
                        isinstance(formatted, ast.FormattedValue)
                        and isinstance(formatted.value, ast.Name)
                        and formatted.value.id == "case_count"
                    ):
                        print_uses_case_count = True
        if not print_uses_case_count:
            add("main_output_not_ledger_derived", "printed_cases_field")

    return violations


def artifact_digest(evidence_id: str) -> str:
    return (evidence_id.encode("utf-8").hex() + "0" * 64)[:64]


def outcome_evidence(
    evidence_id: str,
    scope: str,
    *,
    locator: str | None = None,
    result: str = "PASSED",
) -> dict[str, object]:
    return {
        "id": evidence_id,
        "scope": scope,
        "kind": "test",
        "locator": locator or f"scripts/{evidence_id}.py",
        "result": result,
    }


def registry_evidence(
    evidence_id: str,
    scope: str,
    *,
    locator: str | None = None,
    task_id: str = TASK_ID,
    charter_revision: int = CHARTER_REVISION,
    charter_sha256: str = CHARTER_SHA256,
    verification_status: str = "VERIFIED",
    captured_at: str = CAPTURED_AT,
    verified_at: str = VERIFIED_AT,
    command: bool = False,
) -> dict[str, object]:
    digest = artifact_digest(evidence_id)
    value: dict[str, object] = {
        "id": evidence_id,
        "scope": scope,
        "task_id": task_id,
        "charter_revision": charter_revision,
        "charter_sha256": charter_sha256,
        "captured_at": captured_at,
        "verified_at": verified_at,
        "verification_status": verification_status,
    }
    if command:
        value["command_identity"] = locator or f"python -B scripts/{evidence_id}.py"
        value["command_digest"] = digest
    else:
        value["artifact_path"] = locator or f"scripts/{evidence_id}.py"
        value["artifact_sha256"] = digest
    return value


def implementation_bundle() -> tuple[dict[str, object], list[dict[str, object]], dict[str, str]]:
    evidence = [
        outcome_evidence(
            "user-result",
            "user_outcome",
            locator="python -B scripts/check_user_result.py",
        ),
        outcome_evidence("functional", "functional_closure"),
        outcome_evidence("regression", "non_regression"),
        outcome_evidence("risk", "risk_boundary"),
    ]
    registry = [
        registry_evidence(
            "user-result",
            "user_outcome",
            locator="python -B scripts/check_user_result.py",
            command=True,
        ),
        registry_evidence("functional", "functional_closure"),
        registry_evidence("regression", "non_regression"),
        registry_evidence("risk", "risk_boundary"),
    ]
    observed = {item["id"]: artifact_digest(str(item["id"])) for item in registry}
    outcome: dict[str, object] = {
        "schema": OUTCOME_SCHEMA,
        "work_kind": "implementation",
        "result_status": "USABLE",
        "final_usable_result": "The requested implementation is usable.",
        "usable_for": "The bounded implementation task requested by the decree.",
        "functional_closure": {
            "status": "PASSED",
            "reason": "Requested behavior is complete.",
            "evidence_ids": ["functional"],
        },
        "non_regression": {
            "status": "PASSED",
            "reason": "Regression checks pass.",
            "evidence_ids": ["regression"],
        },
        "risk_boundary": {
            "status": "PASSED",
            "reason": "The approved boundary is preserved.",
            "evidence_ids": ["risk"],
        },
        "verification_state": "VERIFIED",
        "evidence": evidence,
        "residual_gaps": [],
    }
    return outcome, registry, observed


def run_assessment(
    outcome: dict[str, object],
    registry: list[dict[str, object]],
    observed: dict[str, str],
    *,
    work_kind: str | None = None,
) -> dict[str, object]:
    return assess_outcome(
        outcome,
        expected_work_kind=work_kind or str(outcome["work_kind"]),
        expected_task_id=TASK_ID,
        expected_charter_revision=CHARTER_REVISION,
        expected_charter_sha256=CHARTER_SHA256,
        evidence_registry=registry,
        observed_digests=observed,
        assessed_at=ASSESSED_AT,
    )


def gate_action(
    label: str,
    expected: str,
    mutate,
    *,
    reason_code: str | None = None,
) -> object:
    def run() -> None:
        outcome, registry, observed = implementation_bundle()
        mutate(outcome, registry, observed)
        assessment = run_assessment(outcome, registry, observed)
        require(assessment["gate"] == expected, f"{label}: {assessment}")
        OBSERVED_GATES.add(str(assessment["gate"]))
        if reason_code is not None:
            require_reason(assessment, reason_code, label)

    return run


def check_default() -> None:
    def run() -> None:
        require(
            default_outcome_assessment()
            == {
                "schema": ASSESSMENT_SCHEMA,
                "gate": "UNASSESSED",
                "reasons": [],
                "outcome": None,
            },
            "default assessment drifted",
        )

    execute_case("default_assessment", run)


def check_five_level_and_structure_cases() -> None:
    execute_case(
        "expect_gate:implementation_pass",
        gate_action("implementation_pass", "PASSED", lambda *_: None),
    )

    def empty_final(outcome, registry, observed) -> None:
        outcome["final_usable_result"] = ""
        for section_name in ("functional_closure", "non_regression", "risk_boundary"):
            outcome[section_name]["evidence_ids"] = []
        outcome["evidence"] = [
            outcome_evidence("control", "control_plane"),
            outcome_evidence("docs", "documentation"),
        ]
        registry[:] = [
            registry_evidence("control", "control_plane"),
            registry_evidence("docs", "documentation"),
        ]
        observed.clear()
        observed.update({"control": artifact_digest("control"), "docs": artifact_digest("docs")})

    execute_case(
        "expect_gate:empty_final_control_only",
        gate_action(
            "empty_final_control_only",
            "RETURN_FOR_REWORK",
            empty_final,
            reason_code="final_usable_result_required",
        ),
    )

    def functional_failed(outcome, *_args) -> None:
        outcome["functional_closure"]["status"] = "FAILED"

    execute_case(
        "expect_gate:functional_failed",
        gate_action(
            "functional_failed",
            "RETURN_FOR_REWORK",
            functional_failed,
            reason_code="functional_closure_failed",
        ),
    )

    def implementation_not_applicable(outcome, *_args) -> None:
        outcome["non_regression"]["status"] = "NOT_APPLICABLE"

    execute_case(
        "expect_gate:implementation_not_applicable",
        gate_action(
            "implementation_not_applicable",
            "RETURN_FOR_REWORK",
            implementation_not_applicable,
            reason_code="non_regression_required",
        ),
    )

    def risk_failed(outcome, *_args) -> None:
        outcome["risk_boundary"]["status"] = "FAILED"

    execute_case(
        "expect_gate:risk_failed",
        gate_action(
            "risk_failed",
            "BLOCKED",
            risk_failed,
            reason_code="risk_boundary_failed",
        ),
    )

    def partial_verification(outcome, *_args) -> None:
        outcome["verification_state"] = "PARTIAL"

    execute_case(
        "expect_gate:partial_verification",
        gate_action(
            "partial_verification",
            "PARTIAL",
            partial_verification,
            reason_code="verification_state_incomplete:PARTIAL",
        ),
    )

    def control_and_docs_only(outcome, registry, observed) -> None:
        for section_name in ("functional_closure", "non_regression", "risk_boundary"):
            outcome[section_name]["evidence_ids"] = []
        outcome["evidence"] = [
            outcome_evidence("control", "control_plane"),
            outcome_evidence("docs", "documentation"),
        ]
        registry[:] = [
            registry_evidence("control", "control_plane"),
            registry_evidence("docs", "documentation"),
        ]
        observed.clear()
        observed.update({"control": artifact_digest("control"), "docs": artifact_digest("docs")})

    execute_case(
        "expect_gate:control_and_docs_only",
        gate_action(
            "control_and_docs_only",
            "PARTIAL",
            control_and_docs_only,
            reason_code="missing_result_scopes",
        ),
    )

    def residual_gaps_without_concerns(outcome, *_args) -> None:
        outcome["residual_gaps"] = ["A bounded gap remains."]

    execute_case(
        "expect_gate:residual_gaps_without_concerns",
        gate_action(
            "residual_gaps_without_concerns",
            "RETURN_FOR_REWORK",
            residual_gaps_without_concerns,
            reason_code="residual_gaps_require_concerns_status",
        ),
    )

    def concerns_with_gaps(outcome, *_args) -> None:
        outcome["result_status"] = "USABLE_WITH_CONCERNS"
        outcome["residual_gaps"] = ["A bounded, disclosed gap remains."]

    execute_case(
        "expect_gate:concerns_with_gaps",
        gate_action("concerns_with_gaps", "PASSED_WITH_CONCERNS", concerns_with_gaps),
    )


def check_all_work_kinds_table_driven() -> None:
    cases = (
        ("implementation", True),
        ("operation", True),
        ("release", True),
        ("audit", False),
        ("plan", False),
        ("research", False),
        ("answer", False),
    )

    def check_table_coverage() -> None:
        require(
            {work_kind for work_kind, _execution in cases} == WORK_KINDS,
            "work-kind table drifted",
        )

    execute_case("work_kind:table_coverage", check_table_coverage)

    def bundle_for_work_kind(
        work_kind: str,
        execution: bool,
    ) -> tuple[dict[str, object], list[dict[str, object]], dict[str, str]]:
        outcome, registry, observed = implementation_bundle()
        outcome["work_kind"] = work_kind
        if not execution:
            outcome["functional_closure"] = {
                "status": "NOT_APPLICABLE",
                "reason": f"{work_kind} does not execute production behavior.",
                "evidence_ids": [],
            }
            outcome["non_regression"] = {
                "status": "NOT_APPLICABLE",
                "reason": f"{work_kind} changes no runtime behavior.",
                "evidence_ids": [],
            }
            outcome["risk_boundary"]["evidence_ids"] = []
            outcome["evidence"] = [deepcopy(outcome["evidence"][0])]
            registry[:] = [deepcopy(registry[0])]
            observed = {"user-result": artifact_digest("user-result")}
        return outcome, registry, observed

    for work_kind, execution in cases:
        def positive(work_kind=work_kind, execution=execution) -> None:
            outcome, registry, observed = bundle_for_work_kind(work_kind, execution)
            assessment = run_assessment(outcome, registry, observed, work_kind=work_kind)
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "PASSED",
                f"{work_kind} should pass: {assessment}",
            )

        execute_case(f"work_kind:{work_kind}:positive", positive)

        def negative(work_kind=work_kind, execution=execution) -> None:
            outcome, registry, observed = bundle_for_work_kind(work_kind, execution)
            if execution:
                outcome["functional_closure"]["status"] = "NOT_APPLICABLE"
                negative_reason = "functional_closure_required"
            else:
                outcome["functional_closure"]["reason"] = ""
                negative_reason = "not_applicable_reason_required:functional_closure"
            assessment = run_assessment(outcome, registry, observed, work_kind=work_kind)
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "RETURN_FOR_REWORK",
                f"{work_kind} negative decision should return for rework: {assessment}",
            )
            require(
                negative_reason in assessment["reasons"],
                f"{work_kind} negative decision reason absent: {assessment}",
            )

        execute_case(f"work_kind:{work_kind}:negative", negative)


def check_padded_canonical_tokens() -> None:
    cases = (
        (
            "schema",
            lambda outcome, _registry, _observed: outcome.__setitem__(
                "schema", f" {OUTCOME_SCHEMA} "
            ),
            "RETURN_FOR_REWORK",
            "schema",
        ),
        (
            "work_kind",
            lambda outcome, _registry, _observed: outcome.__setitem__(
                "work_kind", " implementation "
            ),
            "RETURN_FOR_REWORK",
            "work_kind",
        ),
        (
            "result_status",
            lambda outcome, _registry, _observed: outcome.__setitem__(
                "result_status", " USABLE "
            ),
            "RETURN_FOR_REWORK",
            "result_status",
        ),
        (
            "verification_state",
            lambda outcome, _registry, _observed: outcome.__setitem__(
                "verification_state", " VERIFIED "
            ),
            "RETURN_FOR_REWORK",
            "verification_state",
        ),
        (
            "section_status",
            lambda outcome, _registry, _observed: outcome["functional_closure"].__setitem__(
                "status", " PASSED "
            ),
            "RETURN_FOR_REWORK",
            "section_status:functional_closure",
        ),
        (
            "outcome_scope",
            lambda outcome, _registry, _observed: outcome["evidence"][0].__setitem__(
                "scope", " user_outcome "
            ),
            "RETURN_FOR_REWORK",
            "evidence_scope:user-result",
        ),
        (
            "outcome_id",
            lambda outcome, _registry, _observed: outcome["evidence"][0].__setitem__(
                "id", " user-result "
            ),
            "RETURN_FOR_REWORK",
            "evidence_id:0",
        ),
        (
            "outcome_evidence_result",
            lambda outcome, _registry, _observed: outcome["evidence"][0].__setitem__(
                "result", " PASSED "
            ),
            "RETURN_FOR_REWORK",
            "evidence_result:user-result",
        ),
        (
            "section_evidence_id",
            lambda outcome, _registry, _observed: outcome["functional_closure"][
                "evidence_ids"
            ].__setitem__(0, " functional "),
            "RETURN_FOR_REWORK",
            "section_evidence_id:functional_closure",
        ),
        (
            "registry_scope",
            lambda _outcome, registry, _observed: registry[0].__setitem__(
                "scope", " user_outcome "
            ),
            "PARTIAL",
            "registry_scope_invalid:user-result",
        ),
        (
            "registry_verification_status",
            lambda _outcome, registry, _observed: registry[0].__setitem__(
                "verification_status", " VERIFIED "
            ),
            "PARTIAL",
            "registry_not_verified:user-result",
        ),
        (
            "registry_id",
            lambda _outcome, registry, _observed: registry[0].__setitem__(
                "id", " user-result "
            ),
            "PARTIAL",
            "registry_entry_missing:user-result",
        ),
        (
            "registry_charter_hash",
            lambda _outcome, registry, _observed: registry[0].__setitem__(
                "charter_sha256", f" {CHARTER_SHA256} "
            ),
            "PARTIAL",
            "charter_sha256_invalid:user-result",
        ),
        (
            "registry_artifact_hash",
            lambda _outcome, registry, _observed: registry[1].__setitem__(
                "artifact_sha256", f" {artifact_digest('functional')} "
            ),
            "PARTIAL",
            "digest_format_invalid:functional",
        ),
        (
            "observed_hash",
            lambda _outcome, _registry, observed: observed.__setitem__(
                "functional", f" {artifact_digest('functional')} "
            ),
            "PARTIAL",
            "digest_format_invalid:functional",
        ),
    )
    for label, mutate, expected_gate, reason_code in cases:
        execute_case(
            f"expect_gate:{label}",
            gate_action(label, expected_gate, mutate, reason_code=reason_code),
        )

    def padded_expected_hash() -> None:
        outcome, registry, observed = implementation_bundle()
        assessment = assess_outcome(
            outcome,
            expected_work_kind="implementation",
            expected_task_id=TASK_ID,
            expected_charter_revision=CHARTER_REVISION,
            expected_charter_sha256=f" {CHARTER_SHA256} ",
            evidence_registry=registry,
            observed_digests=observed,
            assessed_at=ASSESSED_AT,
        )
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(assessment["gate"] == "PARTIAL", f"padded expected hash passed: {assessment}")
        require_reason(
            assessment,
            "runtime_freshness_context_missing",
            "padded expected hash",
        )

    execute_case("padded_token:expected_charter_sha256", padded_expected_hash)


def check_registry_id_contract() -> None:
    explicit_id_cases = (None, "", " ", 0, False)
    for invalid_id in explicit_id_cases:
        def run_explicit(invalid_id=invalid_id) -> None:
            outcome, registry, observed = implementation_bundle()
            mapping = {str(item["id"]): deepcopy(item) for item in registry}
            mapping["user-result"]["id"] = invalid_id
            assessment = assess_outcome(
                outcome,
                expected_work_kind="implementation",
                expected_task_id=TASK_ID,
                expected_charter_revision=CHARTER_REVISION,
                expected_charter_sha256=CHARTER_SHA256,
                evidence_registry=mapping,
                observed_digests=observed,
                assessed_at=ASSESSED_AT,
            )
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "PARTIAL",
                f"explicit registry id {invalid_id!r} passed: {assessment}",
            )
            require_reason(
                assessment,
                "registry_entry_missing:user-result",
                f"explicit registry id {invalid_id!r}",
            )

        execute_case(f"registry_id:explicit:{invalid_id!r}", run_explicit)

    mapping_key_cases = (None, "", " ", 7, " user-result ")
    for invalid_key in mapping_key_cases:
        def run_key(invalid_key=invalid_key) -> None:
            outcome, registry, observed = implementation_bundle()
            mapping = {str(item["id"]): deepcopy(item) for item in registry[1:]}
            mapping[invalid_key] = deepcopy(registry[0])
            assessment = assess_outcome(
                outcome,
                expected_work_kind="implementation",
                expected_task_id=TASK_ID,
                expected_charter_revision=CHARTER_REVISION,
                expected_charter_sha256=CHARTER_SHA256,
                evidence_registry=mapping,
                observed_digests=observed,
                assessed_at=ASSESSED_AT,
            )
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "PARTIAL",
                f"registry mapping key {invalid_key!r} passed: {assessment}",
            )
            require_reason(
                assessment,
                "registry_entry_missing:user-result",
                f"registry mapping key {invalid_key!r}",
            )

        execute_case(f"registry_id:mapping_key:{invalid_key!r}", run_key)


def check_authoritative_registry_scope() -> None:
    def missing_registry_scope(_outcome, registry, _observed) -> None:
        del registry[0]["scope"]

    execute_case(
        "expect_gate:missing_registry_scope",
        gate_action(
            "missing_registry_scope",
            "PARTIAL",
            missing_registry_scope,
            reason_code="registry_scope_invalid:user-result",
        ),
    )

    def relabeled_control_plane(_outcome, registry, _observed) -> None:
        registry[0]["scope"] = "control_plane"

    def run_relabeled() -> None:
        outcome, registry, observed = implementation_bundle()
        relabeled_control_plane(outcome, registry, observed)
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "PARTIAL",
            f"control-plane evidence was relabeled: {assessment}",
        )
        require_reason(
            assessment,
            "registry_scope_mismatch:user-result",
            "registry scope mismatch",
        )
        require_reason(
            assessment,
            "missing_result_scopes:user_outcome",
            "authoritative user-outcome scope",
        )

    execute_case("authoritative_registry_scope:relabeled_control_plane", run_relabeled)


def check_completion_expected_work_kind_is_canonical() -> None:
    def run() -> None:
        outcome, registry, observed = implementation_bundle()
        assessment = run_assessment(outcome, registry, observed)
        context = completion_context(registry, observed)
        context["expected_work_kind"] = " implementation "
        try:
            require_completable_assessment(assessment, **context)
        except ValueError as exc:
            require_error(
                exc,
                "assessment_runtime_context_required",
                "padded completion work kind",
            )
        else:
            raise AssertionError("padded completion expected_work_kind crossed completion guard")

    execute_case("completion_guard:padded_expected_work_kind", run)


def check_section_linked_freshness_contract() -> None:
    def rejected_link_with_spare() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["evidence"].append(outcome_evidence("functional-spare", "functional_closure"))
        registry.append(registry_evidence("functional-spare", "functional_closure"))
        observed["functional-spare"] = artifact_digest("functional-spare")
        observed["functional"] = "f" * 64
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "PARTIAL",
            f"rejected linked evidence was replaced by unreferenced evidence: {assessment}",
        )
        for expected_reason in (
            "digest_mismatch:functional",
            "missing_result_scopes:functional_closure",
        ):
            require_reason(assessment, expected_reason, "linked freshness")
        try:
            require_completable_assessment(
                assessment,
                **completion_context(registry, observed),
            )
        except ValueError as exc:
            require_error(exc, "assessment_not_completable", "linked freshness")
        else:
            raise AssertionError("rejected linked evidence crossed completion guard")

    execute_case(
        "section_linked_freshness:rejected_link_with_spare",
        rejected_link_with_spare,
    )

    required_sections = ("functional_closure", "non_regression", "risk_boundary")
    for section_name in required_sections:
        def run_empty(section_name=section_name) -> None:
            outcome, registry, observed = implementation_bundle()
            outcome[section_name]["evidence_ids"] = []
            assessment = run_assessment(outcome, registry, observed)
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "PARTIAL",
                f"empty required section {section_name} passed: {assessment}",
            )
            require_reason(
                assessment,
                f"missing_result_scopes:{section_name}",
                f"empty required section {section_name}",
            )

        execute_case(f"section_linked_freshness:empty:{section_name}", run_empty)


def check_risk_residual_contract() -> None:
    def valid() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["risk_boundary"]["status"] = "PASSED_WITH_RESIDUAL"
        outcome["result_status"] = "USABLE_WITH_CONCERNS"
        outcome["residual_gaps"] = ["A bounded risk remains."]
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "PASSED_WITH_CONCERNS",
            f"valid residual-risk outcome rejected: {assessment}",
        )

    execute_case("risk_residual:valid", valid)

    def wrong_status() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["risk_boundary"]["status"] = "PASSED_WITH_RESIDUAL"
        outcome["residual_gaps"] = ["A bounded risk remains."]
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "RETURN_FOR_REWORK",
            f"residual risk without concerns status passed: {assessment}",
        )
        require_reason(
            assessment,
            "risk_residual_requires_concerns_status",
            "residual risk without concerns status",
        )

    execute_case("risk_residual:wrong_status", wrong_status)

    def missing_gaps() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["risk_boundary"]["status"] = "PASSED_WITH_RESIDUAL"
        outcome["result_status"] = "USABLE_WITH_CONCERNS"
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "RETURN_FOR_REWORK",
            f"residual risk without gaps passed: {assessment}",
        )
        require_reason(
            assessment,
            "risk_residual_requires_gaps",
            "residual risk without gaps",
        )

    execute_case("risk_residual:missing_gaps", missing_gaps)


def check_result_gap_contract_precedence() -> None:
    def concerns_without_gaps_partial(outcome, _registry, _observed) -> None:
        outcome["result_status"] = "USABLE_WITH_CONCERNS"
        outcome["verification_state"] = "PARTIAL"

    def concerns_without_gaps_missing_scope(outcome, _registry, _observed) -> None:
        outcome["result_status"] = "USABLE_WITH_CONCERNS"
        outcome["functional_closure"]["evidence_ids"] = []

    def gaps_without_concerns_partial(outcome, _registry, _observed) -> None:
        outcome["residual_gaps"] = ["A bounded gap remains."]
        outcome["verification_state"] = "PARTIAL"

    def gaps_without_concerns_missing_scope(outcome, _registry, _observed) -> None:
        outcome["residual_gaps"] = ["A bounded gap remains."]
        outcome["functional_closure"]["evidence_ids"] = []

    precedence_cases = (
        (
            "concerns_without_gaps_partial",
            concerns_without_gaps_partial,
            "concerns_require_residual_gaps",
        ),
        (
            "concerns_without_gaps_missing_scope",
            concerns_without_gaps_missing_scope,
            "concerns_require_residual_gaps",
        ),
        (
            "gaps_without_concerns_partial",
            gaps_without_concerns_partial,
            "residual_gaps_require_concerns_status",
        ),
        (
            "gaps_without_concerns_missing_scope",
            gaps_without_concerns_missing_scope,
            "residual_gaps_require_concerns_status",
        ),
    )
    for label, mutate, expected_reason in precedence_cases:
        def run_precedence(
            label=label,
            mutate=mutate,
            expected_reason=expected_reason,
        ) -> None:
            outcome, registry, observed = implementation_bundle()
            mutate(outcome, registry, observed)
            assessment = run_assessment(outcome, registry, observed)
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "RETURN_FOR_REWORK",
                f"{label}: expected RETURN_FOR_REWORK before incomplete evidence: {assessment}",
            )
            require_reason(assessment, expected_reason, label)
            try:
                require_completable_assessment(
                    assessment,
                    **completion_context(registry, observed),
                )
            except ValueError as exc:
                require_error(exc, "assessment_not_completable", label)
            else:
                raise AssertionError(f"{label}: contradictory outcome crossed completion guard")

        execute_case(f"result_gap_precedence:{label}", run_precedence)

    def partial_semantics() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["result_status"] = "PARTIAL"
        outcome["residual_gaps"] = ["An incomplete-evidence gap remains."]
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "PARTIAL",
            f"PARTIAL result lost incomplete-evidence semantics: {assessment}",
        )
        require_reason(assessment, "result_status_partial", "PARTIAL semantics")
        require(
            not has_reason(
                assessment["reasons"],
                "residual_gaps_require_concerns_status",
            ),
            f"PARTIAL result was forced through USABLE gap consistency: {assessment}",
        )

    execute_case("result_gap_precedence:partial_semantics", partial_semantics)

    def passed_with_residual() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["risk_boundary"]["status"] = "PASSED_WITH_RESIDUAL"
        outcome["result_status"] = "USABLE_WITH_CONCERNS"
        outcome["residual_gaps"] = ["A bounded risk remains."]
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "PASSED_WITH_CONCERNS",
            f"PASSED_WITH_RESIDUAL contract regressed: {assessment}",
        )
        try:
            completed = require_completable_assessment(
                assessment,
                **completion_context(registry, observed),
            )
        except ValueError as exc:
            raise AssertionError(f"PASSED_WITH_RESIDUAL completion guard rejected: {exc}") from exc
        require(
            completed["gate"] == "PASSED_WITH_CONCERNS",
            f"PASSED_WITH_RESIDUAL completion drifted: {completed}",
        )

    execute_case("result_gap_precedence:passed_with_residual", passed_with_residual)


def check_registry_charter_revision_types() -> None:
    cases = (3.0, True, "3", 0, -1)
    for invalid_revision in cases:
        def run(invalid_revision=invalid_revision) -> None:
            outcome, registry, observed = implementation_bundle()
            registry[1]["charter_revision"] = invalid_revision
            assessment = run_assessment(outcome, registry, observed)
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "PARTIAL",
                f"registry charter revision {invalid_revision!r} passed: {assessment}",
            )
            require_reason(
                assessment,
                "charter_revision_invalid:functional",
                f"registry charter revision {invalid_revision!r}",
            )

        execute_case(f"registry_charter_revision:{invalid_revision!r}", run)


def check_blocked_shape_diagnostics() -> None:
    cases = (
        ("result_status", "result_status_blocked"),
        ("risk_boundary", "risk_boundary_failed"),
    )
    for trigger, trigger_reason in cases:
        def run(trigger=trigger, trigger_reason=trigger_reason) -> None:
            outcome, registry, observed = implementation_bundle()
            outcome["schema"] = f" {OUTCOME_SCHEMA} "
            if trigger == "result_status":
                outcome["result_status"] = "BLOCKED"
            else:
                outcome["risk_boundary"]["status"] = "FAILED"
            assessment = run_assessment(outcome, registry, observed)
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "BLOCKED",
                f"{trigger} did not retain BLOCKED gate: {assessment}",
            )
            for expected_reason in ("schema", trigger_reason):
                require_reason(assessment, expected_reason, trigger)

        execute_case(f"blocked_shape:{trigger}", run)


def check_freshness_reason_deduplication() -> None:
    def run() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["evidence"][1]["result"] = "FAILED"
        registry[1]["task_id"] = "another-task"
        registry[1]["verification_status"] = "PENDING"
        registry[1]["artifact_sha256"] = "same-but-not-a-sha256"
        observed["functional"] = "same-but-not-a-sha256"
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        functional = next(
            item for item in assessment["outcome"]["evidence"] if item["id"] == "functional"
        )
        expected = [
            "task_id_mismatch",
            "registry_not_verified",
            "digest_format_invalid",
            "evidence_result_not_passed",
        ]
        require(
            functional["freshness"]["reasons"] == expected,
            f"freshness reasons were not stable-unique: {functional['freshness']}",
        )

    execute_case("freshness_reason_deduplication", run)


def check_section_reason_types() -> None:
    cases = (
        ("array", "functional_closure", []),
        ("object", "non_regression", {}),
        ("number", "risk_boundary", 7),
        ("boolean", "functional_closure", False),
        ("null", "non_regression", None),
    )
    for type_label, section_name, invalid_reason in cases:
        def run(
            type_label=type_label,
            section_name=section_name,
            invalid_reason=invalid_reason,
        ) -> None:
            outcome, registry, observed = implementation_bundle()
            outcome[section_name]["reason"] = invalid_reason
            assessment = run_assessment(outcome, registry, observed)
            OBSERVED_GATES.add(str(assessment["gate"]))
            try:
                require_completable_assessment(
                    assessment,
                    **completion_context(registry, observed),
                )
            except ValueError as exc:
                require_error(exc, "assessment_not_completable", type_label)
            else:
                raise AssertionError(
                    f"{type_label}-valued section reason crossed completion guard"
                )
            require(
                assessment["gate"] == "RETURN_FOR_REWORK",
                f"{type_label}-valued section reason passed: {assessment}",
            )
            require_reason(
                assessment,
                f"section_reason_type:{section_name}",
                type_label,
            )

        execute_case(f"section_reason_type:{type_label}", run)


def check_runtime_computed_freshness() -> None:
    def cross_task(_outcome, registry, _observed) -> None:
        registry[0]["task_id"] = "another-task"

    execute_case(
        "expect_gate:cross_task",
        gate_action("cross_task", "PARTIAL", cross_task, reason_code="task_id_mismatch"),
    )

    def old_revision(_outcome, registry, _observed) -> None:
        registry[1]["charter_revision"] = CHARTER_REVISION - 1

    execute_case(
        "expect_gate:old_revision",
        gate_action(
            "old_revision",
            "PARTIAL",
            old_revision,
            reason_code="charter_revision_mismatch",
        ),
    )

    def old_charter_hash(_outcome, registry, _observed) -> None:
        registry[2]["charter_sha256"] = "b" * 64

    execute_case(
        "expect_gate:old_charter_hash",
        gate_action(
            "old_charter_hash",
            "PARTIAL",
            old_charter_hash,
            reason_code="charter_sha256_mismatch",
        ),
    )

    def unverified(_outcome, registry, _observed) -> None:
        registry[3]["verification_status"] = "PENDING"

    execute_case(
        "expect_gate:unverified_registry",
        gate_action(
            "unverified_registry",
            "PARTIAL",
            unverified,
            reason_code="registry_not_verified",
        ),
    )

    def digest_drift(_outcome, _registry, observed) -> None:
        observed["functional"] = "f" * 64

    execute_case(
        "expect_gate:digest_drift",
        gate_action(
            "digest_drift",
            "PARTIAL",
            digest_drift,
            reason_code="digest_mismatch",
        ),
    )

    def malformed_digest(_outcome, registry, observed) -> None:
        registry[1]["artifact_sha256"] = "same-but-not-a-sha256"
        observed["functional"] = "same-but-not-a-sha256"

    execute_case(
        "expect_gate:malformed_digest",
        gate_action(
            "malformed_digest",
            "PARTIAL",
            malformed_digest,
            reason_code="digest_format_invalid",
        ),
    )

    def invalid_time(_outcome, registry, _observed) -> None:
        registry[2]["verified_at"] = "2026-07-12T08:59:59Z"

    execute_case(
        "expect_gate:invalid_time_order",
        gate_action(
            "invalid_time_order",
            "PARTIAL",
            invalid_time,
            reason_code="verified_before_captured",
        ),
    )

    def self_reported_fresh(outcome, _registry, _observed) -> None:
        outcome["evidence"][0]["fresh"] = True

    execute_case(
        "expect_gate:self_reported_fresh",
        gate_action(
            "self_reported_fresh",
            "PARTIAL",
            self_reported_fresh,
            reason_code="self_reported_freshness_forbidden",
        ),
    )

    def missing_context() -> None:
        outcome, _registry, _observed = implementation_bundle()
        assessment = assess_outcome(outcome, expected_work_kind="implementation")
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "PARTIAL",
            f"missing runtime registry passed: {assessment}",
        )
        require_reason(
            assessment,
            "runtime_freshness_context_missing",
            "missing runtime context",
        )

    execute_case("runtime_freshness:missing_context", missing_context)


def check_section_evidence_linkage() -> None:
    def dangling_section_link(outcome, _registry, _observed) -> None:
        outcome["functional_closure"]["evidence_ids"] = ["missing-functional"]

    execute_case(
        "expect_gate:dangling_section_evidence_id",
        gate_action(
            "dangling_section_evidence_id",
            "RETURN_FOR_REWORK",
            dangling_section_link,
            reason_code="section_evidence_missing:functional_closure/missing-functional",
        ),
    )

    def wrong_scope_section_link(outcome, _registry, _observed) -> None:
        outcome["functional_closure"]["evidence_ids"] = ["risk"]

    execute_case(
        "expect_gate:wrong_scope_section_evidence_id",
        gate_action(
            "wrong_scope_section_evidence_id",
            "RETURN_FOR_REWORK",
            wrong_scope_section_link,
            reason_code="section_evidence_scope_mismatch:functional_closure/risk",
        ),
    )


def check_unreferenced_registry_duplicates() -> None:
    def run() -> None:
        outcome, registry, observed = implementation_bundle()
        duplicate = registry_evidence("unreferenced-duplicate", "control_plane")
        registry.extend((duplicate, deepcopy(duplicate)))
        observed["unreferenced-duplicate"] = artifact_digest("unreferenced-duplicate")
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "PARTIAL",
            f"unreferenced duplicate registry id passed: {assessment}",
        )
        require_reason(
            assessment,
            "duplicate_registry_id:unreferenced-duplicate",
            "unreferenced duplicate registry",
        )

    execute_case("unreferenced_registry_duplicate", run)


def completion_context(
    registry: list[dict[str, object]],
    observed: dict[str, str],
    *,
    assessed_at: str = ASSESSED_AT,
) -> dict[str, object]:
    return {
        "expected_work_kind": "implementation",
        "expected_task_id": TASK_ID,
        "expected_charter_revision": CHARTER_REVISION,
        "expected_charter_sha256": CHARTER_SHA256,
        "evidence_registry": registry,
        "observed_digests": observed,
        "assessed_at": assessed_at,
    }


def check_completion_guard_reauthentication() -> None:
    def forged_bundle() -> tuple[dict[str, object], list[dict[str, object]], dict[str, str]]:
        outcome, registry, observed = implementation_bundle()
        forged_outcome = deepcopy(outcome)
        for item in forged_outcome["evidence"]:
            item["freshness"] = {"status": "FRESH", "reasons": []}
        forged = {
            "schema": ASSESSMENT_SCHEMA,
            "gate": "PASSED",
            "reasons": [],
            "outcome": forged_outcome,
        }
        return forged, registry, observed

    def forged_without_context() -> None:
        forged, _registry, _observed = forged_bundle()
        try:
            require_completable_assessment(forged)
        except ValueError as exc:
            require_error(exc, "assessment_runtime_context_required", "forged freshness")
        else:
            raise AssertionError("caller-forged FRESH assessment crossed completion guard")

    execute_case("completion_guard:forged_without_context", forged_without_context)

    def runtime_bound_passed() -> None:
        forged, registry, observed = forged_bundle()
        completed = require_completable_assessment(
            forged,
            **completion_context(registry, observed),
        )
        require(completed["gate"] == "PASSED", "runtime-bound PASSED guard rejected")

    execute_case("completion_guard:runtime_bound_passed", runtime_bound_passed)

    def task_mismatch(registry, observed) -> tuple[object, object, str]:
        mutated = deepcopy(registry)
        mutated[0]["task_id"] = "another-task"
        return mutated, observed, ASSESSED_AT

    def revision_mismatch(registry, observed) -> tuple[object, object, str]:
        mutated = deepcopy(registry)
        mutated[1]["charter_revision"] = CHARTER_REVISION - 1
        return mutated, observed, ASSESSED_AT

    def charter_hash_mismatch(registry, observed) -> tuple[object, object, str]:
        mutated = deepcopy(registry)
        mutated[2]["charter_sha256"] = "b" * 64
        return mutated, observed, ASSESSED_AT

    def registry_verification_mismatch(registry, observed) -> tuple[object, object, str]:
        mutated = deepcopy(registry)
        mutated[3]["verification_status"] = "PENDING"
        return mutated, observed, ASSESSED_AT

    def observed_digest_mismatch(registry, observed) -> tuple[object, object, str]:
        mutated = deepcopy(observed)
        mutated["functional"] = "f" * 64
        return registry, mutated, ASSESSED_AT

    def assessment_time_mismatch(registry, observed) -> tuple[object, object, str]:
        return registry, observed, "2026-07-12T08:59:00Z"

    mutations = (
        ("task_id", task_mismatch),
        ("charter_revision", revision_mismatch),
        ("charter_sha256", charter_hash_mismatch),
        ("registry_verification", registry_verification_mismatch),
        ("observed_digest", observed_digest_mismatch),
        ("assessment_time", assessment_time_mismatch),
    )
    for label, mutate in mutations:
        def run(label=label, mutate=mutate) -> None:
            forged, registry, observed = forged_bundle()
            mutated_registry, mutated_observed, mutated_assessed_at = mutate(
                registry,
                observed,
            )
            try:
                require_completable_assessment(
                    forged,
                    **completion_context(
                        mutated_registry,
                        mutated_observed,
                        assessed_at=mutated_assessed_at,
                    ),
                )
            except ValueError as exc:
                require_error(exc, "assessment_not_completable", label)
            else:
                raise AssertionError(
                    f"{label}: runtime-mismatched assessment crossed completion guard"
                )

        execute_case(f"completion_guard:reauthentication:{label}", run)


def check_completion_reason_integrity() -> None:
    def run() -> None:
        failures: list[str] = []
        outcome, registry, observed = implementation_bundle()
        assessment = run_assessment(outcome, registry, observed)
        assessment_before = deepcopy(assessment)

        try:
            completed = require_completable_assessment(
                assessment,
                **completion_context(registry, observed),
            )
        except ValueError as exc:
            failures.append(f"valid PASSED assessment rejected: {exc}")
        else:
            if completed != assessment_before:
                failures.append("valid PASSED assessment changed during completion")
            if completed is assessment:
                failures.append("valid PASSED assessment was returned by identity")
            if completed.get("outcome") is assessment.get("outcome"):
                failures.append("valid PASSED outcome was not deep-copied")
            if completed.get("reasons") != []:
                failures.append(
                    "accepted revalidated assessment retained problem diagnostics: "
                    f"{completed.get('reasons')!r}"
                )
        if assessment != assessment_before:
            failures.append("completion mutated the candidate PASSED assessment")

        allowed_errors = {
            "assessment_revalidation_mismatch",
            "assessment_not_completable",
        }
        forged_reasons = (
            "registry_entry_missing:forged",
            "digest_mismatch:forged",
            "runtime_freshness_context_missing",
        )
        for forged_reason in forged_reasons:
            forged = deepcopy(assessment_before)
            forged["reasons"] = [forged_reason]
            observed_results: list[str] = []
            for _attempt in range(2):
                try:
                    require_completable_assessment(
                        forged,
                        **completion_context(registry, observed),
                    )
                except ValueError as exc:
                    observed_results.append(str(exc))
                else:
                    observed_results.append("accepted")
            if len(set(observed_results)) != 1:
                failures.append(
                    f"{forged_reason}: completion rejection was not deterministic: "
                    f"{observed_results}"
                )
            if observed_results[0] not in allowed_errors:
                failures.append(
                    f"{forged_reason}: forged reasons crossed completion guard: "
                    f"{observed_results[0]}"
                )

        require(
            not failures,
            "completion reason-integrity regressions: " + " | ".join(failures),
        )

    execute_case("completion_guard:reason_integrity", run)


def check_evidence_uniqueness_and_completion_guard() -> None:
    def duplicate_evidence() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["evidence"].append(deepcopy(outcome["evidence"][0]))
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        require(
            assessment["gate"] == "RETURN_FOR_REWORK",
            f"duplicate evidence id passed: {assessment}",
        )
        require_reason(assessment, "duplicate_evidence_id", "duplicate evidence")

    execute_case("evidence_uniqueness:duplicate", duplicate_evidence)

    def passed_guard() -> None:
        outcome, registry, observed = implementation_bundle()
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        completed = require_completable_assessment(
            assessment,
            **completion_context(registry, observed),
        )
        require(completed["gate"] == "PASSED", "PASSED guard rejected")

    execute_case("completion_guard:passed", passed_guard)

    def partial_guard() -> None:
        outcome, registry, observed = implementation_bundle()
        outcome["verification_state"] = "PARTIAL"
        assessment = run_assessment(outcome, registry, observed)
        OBSERVED_GATES.add(str(assessment["gate"]))
        try:
            require_completable_assessment(assessment)
        except ValueError as exc:
            require_error(exc, "assessment_not_completable", "partial completion")
        else:
            raise AssertionError("PARTIAL assessment crossed completion guard")

    execute_case("completion_guard:partial", partial_guard)


def check_known_section_failure_precedence() -> None:
    cases = (
        (
            "functional_failed_concerns_without_gaps",
            "functional_closure",
            "USABLE_WITH_CONCERNS",
            "VERIFIED",
            [],
            ("functional_closure_failed", "concerns_require_residual_gaps"),
        ),
        (
            "non_regression_failed_usable_with_gaps",
            "non_regression",
            "USABLE",
            "VERIFIED",
            ["A bounded gap remains."],
            ("non_regression_failed", "residual_gaps_require_concerns_status"),
        ),
        (
            "functional_failed_partial_verification",
            "functional_closure",
            "USABLE",
            "PARTIAL",
            [],
            ("functional_closure_failed",),
        ),
        (
            "non_regression_failed_partial_result",
            "non_regression",
            "PARTIAL",
            "VERIFIED",
            ["An incomplete-evidence gap remains."],
            ("non_regression_failed",),
        ),
    )

    for label, section_name, result_status, verification_state, gaps, expected_reasons in cases:
        def run(
            section_name=section_name,
            result_status=result_status,
            verification_state=verification_state,
            gaps=gaps,
            expected_reasons=expected_reasons,
            label=label,
        ) -> None:
            outcome, registry, observed = implementation_bundle()
            outcome[section_name]["status"] = "FAILED"
            outcome["result_status"] = result_status
            outcome["verification_state"] = verification_state
            outcome["residual_gaps"] = list(gaps)
            assessment = run_assessment(outcome, registry, observed)
            OBSERVED_GATES.add(str(assessment["gate"]))
            require(
                assessment["gate"] == "RETURN_FOR_REWORK",
                f"{label}: known section failure was masked: {assessment}",
            )
            for expected_reason in expected_reasons:
                require_reason(assessment, expected_reason, label)

        execute_case(f"known_section_failure:{label}", run)


def check_failed_declared_evidence_is_not_completable() -> None:
    def run() -> None:
        failures: list[str] = []
        cases = (
            ("extra-user-outcome", "user_outcome"),
            ("extra-control-plane", "control_plane"),
            ("extra-unlinked-functional", "functional_closure"),
        )
        for evidence_id, scope in cases:
            outcome, registry, observed = implementation_bundle()
            outcome["evidence"].append(
                outcome_evidence(evidence_id, scope, result="FAILED")
            )
            registry.append(registry_evidence(evidence_id, scope))
            observed[evidence_id] = artifact_digest(evidence_id)
            assessment = run_assessment(outcome, registry, observed)
            OBSERVED_GATES.add(str(assessment["gate"]))
            expected_reason = f"evidence_result_not_passed:{evidence_id}"
            if assessment["gate"] != "RETURN_FOR_REWORK":
                failures.append(
                    f"{evidence_id}: gate={assessment['gate']} expected=RETURN_FOR_REWORK"
                )
            if not has_reason(assessment.get("reasons"), expected_reason):
                failures.append(f"{evidence_id}: missing {expected_reason}")
            if assessment["gate"] in {"PASSED", "PASSED_WITH_CONCERNS"} and any(
                has_reason(assessment.get("reasons"), marker)
                for marker in (
                    "evidence_result_not_passed",
                    "functional_closure_failed",
                    "non_regression_failed",
                    "risk_boundary_failed",
                )
            ):
                failures.append(
                    f"{evidence_id}: accepted assessment carries rejection/failure reasons"
                )
            try:
                require_completable_assessment(
                    assessment,
                    **completion_context(registry, observed),
                )
            except ValueError as exc:
                if str(exc) != "assessment_not_completable":
                    failures.append(
                        f"{evidence_id}: completion rejected with unexpected error {exc}"
                    )
            else:
                failures.append(f"{evidence_id}: completion guard accepted failed evidence")

        require(
            not failures,
            "failed declared evidence false-pass regressions: " + " | ".join(failures),
        )

    execute_case("failed_declared_evidence:not_completable", run)


def check_severity_and_diagnostics_are_independent() -> None:
    def result_blocked_and_functional_failed(outcome) -> None:
        outcome["result_status"] = "BLOCKED"
        outcome["functional_closure"]["status"] = "FAILED"

    def risk_and_non_regression_failed(outcome) -> None:
        outcome["risk_boundary"]["status"] = "FAILED"
        outcome["non_regression"]["status"] = "FAILED"

    def invalid_schema_and_functional_failed(outcome) -> None:
        outcome["schema"] = "court.outcome_acceptance.invalid"
        outcome["functional_closure"]["status"] = "FAILED"

    def partial_verification_and_missing_functional(outcome) -> None:
        outcome["verification_state"] = "PARTIAL"
        outcome["functional_closure"]["evidence_ids"] = []

    def partial_result_and_missing_functional(outcome) -> None:
        outcome["result_status"] = "PARTIAL"
        outcome["functional_closure"]["evidence_ids"] = []

    def partial_result_and_required_functional(outcome) -> None:
        outcome["result_status"] = "PARTIAL"
        outcome["functional_closure"]["status"] = "NOT_APPLICABLE"
        outcome["functional_closure"]["reason"] = "Incorrectly declared unavailable."
        outcome["functional_closure"]["evidence_ids"] = []

    def contradiction_and_section_failed(outcome) -> None:
        outcome["result_status"] = "USABLE_WITH_CONCERNS"
        outcome["non_regression"]["status"] = "FAILED"

    def genuinely_incomplete(outcome) -> None:
        outcome["functional_closure"]["evidence_ids"] = []

    cases = (
        (
            "result_blocked_and_functional_failed",
            result_blocked_and_functional_failed,
            "BLOCKED",
            ("result_status_blocked", "functional_closure_failed"),
        ),
        (
            "risk_and_non_regression_failed",
            risk_and_non_regression_failed,
            "BLOCKED",
            ("risk_boundary_failed", "non_regression_failed"),
        ),
        (
            "invalid_schema_and_functional_failed",
            invalid_schema_and_functional_failed,
            "RETURN_FOR_REWORK",
            ("schema", "functional_closure_failed"),
        ),
        (
            "partial_verification_and_missing_functional",
            partial_verification_and_missing_functional,
            "PARTIAL",
            (
                "verification_state_incomplete:PARTIAL",
                "missing_result_scopes:functional_closure",
            ),
        ),
        (
            "partial_result_and_missing_functional",
            partial_result_and_missing_functional,
            "PARTIAL",
            ("result_status_partial", "missing_result_scopes:functional_closure"),
        ),
        (
            "partial_result_and_required_functional",
            partial_result_and_required_functional,
            "RETURN_FOR_REWORK",
            (
                "functional_closure_required",
                "result_status_partial",
                "missing_result_scopes:functional_closure",
            ),
        ),
        (
            "contradiction_and_section_failed",
            contradiction_and_section_failed,
            "RETURN_FOR_REWORK",
            ("concerns_require_residual_gaps", "non_regression_failed"),
        ),
        (
            "genuinely_incomplete",
            genuinely_incomplete,
            "PARTIAL",
            ("missing_result_scopes:functional_closure",),
        ),
    )

    def run() -> None:
        failures: list[str] = []
        for label, mutate, expected_gate, expected_reasons in cases:
            outcome, registry, observed = implementation_bundle()
            mutate(outcome)
            assessment = run_assessment(outcome, registry, observed)
            repeated = run_assessment(outcome, registry, observed)
            OBSERVED_GATES.add(str(assessment["gate"]))
            if assessment["gate"] != expected_gate:
                failures.append(
                    f"{label}: gate={assessment['gate']} expected={expected_gate}"
                )
            for expected_reason in expected_reasons:
                if not has_reason(assessment.get("reasons"), expected_reason):
                    failures.append(f"{label}: missing {expected_reason}")
            reasons = assessment.get("reasons")
            if not isinstance(reasons, list) or len(reasons) != len(set(reasons)):
                failures.append(f"{label}: diagnostics are not stable-deduplicated")
            if repeated.get("reasons") != reasons:
                failures.append(f"{label}: diagnostics changed across identical assessment")
            try:
                require_completable_assessment(
                    assessment,
                    **completion_context(registry, observed),
                )
            except ValueError as exc:
                if str(exc) != "assessment_not_completable":
                    failures.append(f"{label}: unexpected completion error {exc}")
            else:
                failures.append(f"{label}: non-accepted assessment crossed completion guard")

        require(
            not failures,
            "severity/diagnostic regressions: " + " | ".join(failures),
        )

    execute_case("severity_and_diagnostics:independent", run)


def rework4_checker_contract_mutants() -> dict[str, tuple[str, str]]:
    return {
        "nested_alias_record_and_caught_assertion": (
            """
def check_nested_alias_record_and_caught_assertion():
    def hidden_bypass():
        ledger = EXECUTED_CASES
        record_alias = ledger.record
        try:
            require(False, "caught failure")
        except AssertionError:
            pass
        record_alias("forged")
    hidden_bypass()
    execute_case("dummy", lambda: None)
""",
            "ledger_record_outside_execute_case",
        ),
        "successful_assertion_outside_execute_case": (
            """
def check_successful_assertion_outside_execute_case():
    assertion_alias = require
    assertion_alias(True, "silently accepted")
    execute_case("dummy", lambda: None)
""",
            "assertion_helper_outside_execute_case",
        ),
        "ordinary_check_with_alternate_ledger": (
            """
def check_ordinary_alternate_ledger():
    execute_case("hidden", lambda: None, ledger=CaseLedger())
""",
            "alternate_ledger_outside_self_contract",
        ),
        "manual_print_with_unused_ledger_count": (
            """
def main():
    EXECUTED_CASES.clear()
    case_count = EXECUTED_CASES.count
    print(f"COURT_OUTCOME_GATE_OK cases={108}")
""",
            "main_output_not_ledger_derived",
        ),
        "private_ledger_mutation": (
            """
def check_private_ledger_mutation():
    ledger_alias = EXECUTED_CASES
    ids_alias = ledger_alias._case_ids
    ids_alias.append("forged")
    ledger_alias._seen.add("forged")
    execute_case("dummy", lambda: None)
""",
            "private_ledger_mutation_outside_execute_case",
        ),
    }


def rework5_checker_contract_mutants() -> dict[str, tuple[str, str, str]]:
    return {
        "reflective_getattr_record": (
            """
def check_reflective_getattr_record():
    def run():
        getattr(EXECUTED_CASES, '_record')(
            'forged',
            _ACTIVE_CASE_TOKENS[-1],
        )
    execute_case('declared', run)
""",
            "reflective_ledger_record",
            "check_reflective_getattr_record",
        ),
        "reflective_object_setattr": (
            """
def check_reflective_object_setattr():
    def run():
        object.__setattr__(
            EXECUTED_CASES,
            '_CaseLedger__case_ids',
            ('forged',),
        )
        object.__setattr__(
            EXECUTED_CASES,
            '_CaseLedger__seen',
            frozenset({'forged'}),
        )
    execute_case('declared', run)
""",
            "reflective_private_ledger_mutation",
            "check_reflective_object_setattr",
        ),
        "reflective_globals_require": (
            """
def check_reflective_globals_require():
    def run():
        try:
            globals()['require'](False, 'caught failure')
        except AssertionError:
            pass
    execute_case('declared', run)
""",
            "reflective_assertion_helper",
            "check_reflective_globals_require",
        ),
    }


def rework6_checker_contract_mutants() -> dict[str, tuple[str, str]]:
    return {
        "nested_swallowed_execute_case": (
            """
def check_nested_swallowed_failure():
    def run():
        try:
            execute_case('inner-fails', lambda: require(False, 'forced'))
        except AssertionError:
            pass
    execute_case('outer-recorded', run)
""",
            "nested_case_failure_swallowed",
        ),
        "caught_raw_assertion": (
            """
def check_caught_raw_assertion():
    def run():
        try:
            assert False, 'forced raw assertion'
        except AssertionError:
            pass
    execute_case('outer-recorded', run)
""",
            "raw_assertion_outside_runtime",
        ),
    }


def rework6_expected_failure_contract_sources() -> tuple[str, str]:
    allowed_self_contract = """
def check_rework6_expected_failure_isolation_contract():
    def run():
        expect_case_failure(
            'expected-inner',
            lambda: None,
            expected_message='forced expected failure',
        )
    execute_case('self-contract-parent', run)
"""
    ordinary_check = """
def check_ordinary_expected_failure_isolation():
    def run():
        expect_case_failure(
            'expected-inner',
            lambda: None,
            expected_message='forced expected failure',
        )
    execute_case('ordinary-parent', run)
"""
    return allowed_self_contract, ordinary_check


def rework7_expected_failure_alias_sources() -> dict[str, tuple[str, bool]]:
    return {
        "local_alias": (
            """
def check_ordinary_expected_failure_alias():
    def run():
        helper = expect_case_failure
        helper('hidden', lambda: None, expected_message='forced')
    execute_case('declared', run)
""",
            True,
        ),
        "chained_alias": (
            """
def check_ordinary_expected_failure_chained_alias():
    def run():
        first = expect_case_failure
        second = first
        second('hidden', lambda: None, expected_message='forced')
    execute_case('declared', run)
""",
            True,
        ),
        "callback_indirection": (
            """
def check_ordinary_expected_failure_callback():
    def invoke(callback):
        callback('hidden', lambda: None, expected_message='forced')
    def run():
        invoke(expect_case_failure)
    execute_case('declared', run)
""",
            True,
        ),
        "reflective_globals": (
            """
def check_ordinary_expected_failure_globals():
    def run():
        globals()['expect_case_failure'](
            'hidden', lambda: None, expected_message='forced'
        )
    execute_case('declared', run)
""",
            True,
        ),
        "reflective_vars": (
            """
def check_ordinary_expected_failure_vars():
    def run():
        vars()['expect_case_failure'](
            'hidden', lambda: None, expected_message='forced'
        )
    execute_case('declared', run)
""",
            True,
        ),
        "reflective_locals_alias": (
            """
def check_ordinary_expected_failure_locals():
    def run():
        helper = locals()['expect_case_failure']
        helper('hidden', lambda: None, expected_message='forced')
    execute_case('declared', run)
""",
            True,
        ),
        "reflective_getattr": (
            """
def check_ordinary_expected_failure_getattr():
    def run():
        helper = getattr(sys.modules[__name__], 'expect_case_failure')
        helper('hidden', lambda: None, expected_message='forced')
    execute_case('declared', run)
""",
            True,
        ),
        "allowed_self_contract_alias": (
            """
def check_rework6_expected_failure_isolation_contract():
    def run():
        helper = expect_case_failure
        helper('hidden', lambda: None, expected_message='forced')
    execute_case('declared', run)
""",
            False,
        ),
        "nearby_plural_name": (
            """
def check_nearby_plural_helper_name():
    def run():
        expect_case_failures = lambda: None
        expect_case_failures()
    execute_case('declared', run)
""",
            False,
        ),
    }


def rework7_suppression_sources() -> dict[str, tuple[str, bool]]:
    return {
        "assertion_error_handler": (
            """
def check_ordinary_assertion_suppression():
    def run():
        try:
            require(False, 'hidden')
        except AssertionError:
            pass
    execute_case('declared', run)
""",
            True,
        ),
        "exception_handler": (
            """
def check_ordinary_exception_suppression():
    def run():
        try:
            helper()
        except Exception:
            return
    execute_case('declared', run)
""",
            True,
        ),
        "base_exception_tuple_handler": (
            """
def check_ordinary_base_exception_tuple_suppression():
    def run():
        try:
            helper()
        except (ValueError, BaseException):
            pass
    execute_case('declared', run)
""",
            True,
        ),
        "bare_handler": (
            """
def check_ordinary_bare_suppression():
    def run():
        try:
            helper()
        except:
            pass
    execute_case('declared', run)
""",
            True,
        ),
        "contextlib_suppress": (
            """
def check_ordinary_contextlib_suppression():
    def run():
        with contextlib.suppress(AssertionError):
            require(False, 'hidden')
    execute_case('declared', run)
""",
            True,
        ),
        "suppress_alias": (
            """
def check_ordinary_suppress_alias():
    def run():
        swallow = contextlib.suppress
        with swallow(Exception):
            helper()
    execute_case('declared', run)
""",
            True,
        ),
        "imported_suppress_alias": (
            """
from contextlib import suppress as swallow
def check_ordinary_imported_suppress_alias():
    def run():
        with swallow(BaseException):
            helper()
    execute_case('declared', run)
""",
            True,
        ),
        "exception_type_alias": (
            """
def check_ordinary_exception_type_alias():
    def run():
        failure_type = AssertionError
        try:
            helper()
        except failure_type:
            pass
    execute_case('declared', run)
""",
            True,
        ),
        "value_error_handler": (
            """
def check_nearby_value_error_handler():
    def run():
        try:
            int('not-an-int')
        except ValueError:
            pass
    execute_case('declared', run)
""",
            False,
        ),
        "reraising_assertion_handler": (
            """
def check_nearby_reraising_assertion_handler():
    def run():
        try:
            helper()
        except AssertionError:
            raise
    execute_case('declared', run)
""",
            False,
        ),
    }


def rework7_ownership_mutation_sources() -> dict[str, tuple[str, bool]]:
    return {
        "active_clear": (
            """
def check_ordinary_active_clear():
    def run():
        _ACTIVE_CASE_TOKENS.clear()
    execute_case('declared', run)
""",
            True,
        ),
        "active_alias_pop": (
            """
def check_ordinary_active_alias_pop():
    def run():
        tokens = _ACTIVE_CASE_TOKENS
        tokens.pop()
    execute_case('declared', run)
""",
            True,
        ),
        "tainted_chained_alias_discard": (
            """
def check_ordinary_tainted_chained_alias_discard():
    def run():
        first = _TAINTED_CASE_TOKENS
        second = first
        second.discard(_ACTIVE_CASE_TOKENS[-1])
    execute_case('declared', run)
""",
            True,
        ),
        "reflective_tainted_clear": (
            """
def check_ordinary_reflective_tainted_clear():
    def run():
        globals()['_TAINTED_CASE_TOKENS'].clear()
    execute_case('declared', run)
""",
            True,
        ),
        "reflective_active_alias_clear": (
            """
def check_ordinary_reflective_active_alias_clear():
    def run():
        tokens = globals()['_ACTIVE_CASE_TOKENS']
        tokens.clear()
    execute_case('declared', run)
""",
            True,
        ),
        "reflective_getattr_discard": (
            """
def check_ordinary_reflective_getattr_discard():
    def run():
        mutate = getattr(_TAINTED_CASE_TOKENS, 'discard')
        mutate(_ACTIVE_CASE_TOKENS[-1])
    execute_case('declared', run)
""",
            True,
        ),
        "active_rebind": (
            """
def check_ordinary_active_rebind():
    global _ACTIVE_CASE_TOKENS
    def run():
        global _ACTIVE_CASE_TOKENS
        _ACTIVE_CASE_TOKENS = list(_ACTIVE_CASE_TOKENS)
    execute_case('declared', run)
""",
            True,
        ),
        "read_only_snapshot": (
            """
def check_nearby_read_only_ownership_snapshot():
    def run():
        active_snapshot = tuple(_ACTIVE_CASE_TOKENS)
        tainted_snapshot = frozenset(_TAINTED_CASE_TOKENS)
        len(active_snapshot) + len(tainted_snapshot)
    execute_case('declared', run)
""",
            False,
        ),
        "local_container_clear": (
            """
def check_nearby_local_container_clear():
    def run():
        local_tokens = []
        local_tokens.clear()
    execute_case('declared', run)
""",
            False,
        ),
    }


def rework8_case_accounting_integrity_sources(
) -> dict[str, tuple[str, tuple[str, ...], str]]:
    return {
        "ledger_alias_expected_snapshot_rewrite": (
            """
def check_ordinary_ledger_alias_expected_snapshot_rewrite():
    def run():
        ledger_alias = EXECUTED_CASES
        capability_alias = _ACTIVE_CASE_TOKENS[-1]
        object.__setattr__(
            ledger_alias,
            '_CaseLedger__case_ids',
            ledger_alias.case_ids + ('forged',),
        )
        object.__setattr__(
            ledger_alias,
            '_CaseLedger__seen',
            frozenset(set(ledger_alias.case_ids)),
        )
        capability_alias.expected_snapshots[ledger_alias] = ledger_alias._snapshot()
    execute_case('declared', run)
""",
            ("case_ledger_state_mutation", "case_capability_state_mutation"),
            "check_ordinary_ledger_alias_expected_snapshot_rewrite",
        ),
        "ledger_chained_alias_initial_snapshot_rewrite": (
            """
def check_ordinary_ledger_chained_alias_initial_snapshot_rewrite():
    def run():
        first_alias = EXECUTED_CASES
        ledger_alias = first_alias
        capability_alias = _ACTIVE_CASE_TOKENS[-1]
        object.__setattr__(
            ledger_alias,
            '_CaseLedger__case_ids',
            ('forged-initial',),
        )
        object.__setattr__(
            ledger_alias,
            '_CaseLedger__seen',
            frozenset({'forged-initial'}),
        )
        forged_snapshot = ledger_alias._snapshot()
        capability_alias.initial_snapshots[ledger_alias] = forged_snapshot
        capability_alias.expected_snapshots[ledger_alias] = forged_snapshot
    execute_case('declared', run)
""",
            ("case_ledger_state_mutation", "case_capability_state_mutation"),
            "check_ordinary_ledger_chained_alias_initial_snapshot_rewrite",
        ),
        "capability_snapshot_mappings_clear": (
            """
def check_ordinary_capability_snapshot_mappings_clear():
    def run():
        capability_alias = _ACTIVE_CASE_TOKENS[-1]
        capability_alias.initial_snapshots.clear()
        capability_alias.expected_snapshots.clear()
    execute_case('declared', run)
""",
            ("case_capability_state_mutation",),
            "check_ordinary_capability_snapshot_mappings_clear",
        ),
        "capability_field_rebind": (
            """
def check_ordinary_capability_field_rebind():
    def run():
        capability_alias = _ACTIVE_CASE_TOKENS[-1]
        capability_alias.ledger = CaseLedger()
    execute_case('declared', run)
""",
            ("case_capability_state_mutation",),
            "check_ordinary_capability_field_rebind",
        ),
    }


def isolated_checker_namespace(label: str) -> dict[str, object]:
    source = Path(__file__).read_text(encoding="utf-8")
    namespace: dict[str, object] = {
        "__builtins__": __builtins__,
        "__file__": __file__,
        "__name__": f"<isolated_checker:{label}>",
    }
    exec(compile(source, f"<isolated_checker:{label}>", "exec"), namespace)
    return namespace


def check_rework5_reflective_validator_contract() -> None:
    def run() -> None:
        failures: list[str] = []
        validator = globals().get("validate_checker_contract")
        if not callable(validator):
            failures.append("reusable checker self-contract validator missing")
        else:
            for label, (source, expected_violation, _entrypoint) in (
                rework5_checker_contract_mutants().items()
            ):
                first = validator(source, filename=f"<mutant:{label}:first>")
                repeated = validator(source, filename=f"<mutant:{label}:repeated>")
                if first != repeated:
                    failures.append(
                        f"{label}: reflective violation classes were not stable: "
                        f"{first} != {repeated}"
                    )
                violation_classes = {
                    violation.split(":", 1)[0]
                    for violation in first
                    if isinstance(violation, str) and violation
                }
                if not violation_classes:
                    failures.append(f"{label}: reflective mutant produced no violation class")
                if expected_violation not in violation_classes:
                    failures.append(
                        f"{label}: expected {expected_violation}, got {first}"
                    )

        require(
            not failures,
            "reflective checker-contract regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework5_reflective_validator", run)


def check_rework5_runtime_ownership_contract() -> None:
    def run() -> None:
        failures: list[str] = []

        nested_namespace = isolated_checker_namespace("nested_alternate_ledger")
        nested_primary = nested_namespace["EXECUTED_CASES"]
        nested_alternate = nested_namespace["CaseLedger"]()

        def nested_action() -> None:
            nested_namespace["execute_case"]("nested-primary-inner", lambda: None)
            nested_namespace["execute_case"](
                "nested-alternate",
                lambda: None,
                ledger=nested_alternate,
            )

        nested_namespace["execute_case"]("nested-primary", nested_action)
        if nested_primary.case_ids != ("nested-primary-inner", "nested-primary"):
            failures.append(
                "nested accounting changed the selected primary ledger: "
                f"{nested_primary.case_ids}"
            )
        if nested_alternate.case_ids != ("nested-alternate",):
            failures.append(
                "nested accounting did not preserve the alternate-ledger allowlist: "
                f"{nested_alternate.case_ids}"
            )
        if nested_namespace["_ACTIVE_CASE_TOKENS"]:
            failures.append("nested accounting leaked isolated ownership context")

        outer_tokens_before = tuple(_ACTIVE_CASE_TOKENS)
        mutants = rework5_checker_contract_mutants()
        for label in ("reflective_getattr_record", "reflective_object_setattr"):
            source, _expected_violation, entrypoint = mutants[label]
            namespace = isolated_checker_namespace(label)
            exec(compile(source, f"<runtime_mutant:{label}>", "exec"), namespace)
            ledger = namespace["EXECUTED_CASES"]
            before = (ledger.count, ledger.case_ids)
            rejected = False
            try:
                namespace[entrypoint]()
            except AssertionError:
                rejected = True
            after = (ledger.count, ledger.case_ids)
            if after[0] == before[0] + 2 or after[1][-2:] == ("forged", "declared"):
                failures.append(
                    f"{label}: declared one-case action produced forged+declared entries: "
                    f"{after[1]}"
                )
            if not rejected:
                failures.append(f"{label}: selected-ledger action mutation was not rejected")
            if after != before:
                failures.append(
                    f"{label}: selected-ledger pre/post snapshot changed: "
                    f"{before} -> {after}"
                )
            if namespace["_ACTIVE_CASE_TOKENS"]:
                failures.append(f"{label}: isolated ownership context was not restored")
            if tuple(_ACTIVE_CASE_TOKENS) != outer_tokens_before:
                failures.append(f"{label}: outer ownership context was corrupted")

        label = "reflective_globals_require"
        source, _expected_violation, entrypoint = mutants[label]
        namespace = isolated_checker_namespace(label)
        exec(compile(source, f"<runtime_mutant:{label}>", "exec"), namespace)
        ledger = namespace["EXECUTED_CASES"]
        before = (ledger.count, ledger.case_ids)
        rejected = False
        try:
            namespace[entrypoint]()
        except AssertionError:
            rejected = True
        after = (ledger.count, ledger.case_ids)
        if not rejected:
            failures.append("caught failed require did not taint and reject the active case")
        if after != before:
            failures.append(
                "caught failed require entered the case ledger: "
                f"{before} -> {after}"
            )
        if namespace["_ACTIVE_CASE_TOKENS"]:
            failures.append("caught failed require leaked isolated ownership context")
        if tuple(_ACTIVE_CASE_TOKENS) != outer_tokens_before:
            failures.append("caught failed require corrupted outer ownership context")

        require(
            not failures,
            "runtime ownership regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework5_runtime_ownership", run)


def check_rework6_nested_failure_runtime_contract() -> None:
    def run() -> None:
        failures: list[str] = []

        for label, use_alternate_ledger in (
            ("same_global_ledger", False),
            ("explicit_alternate_ledger", True),
        ):
            namespace = isolated_checker_namespace(label)
            primary_ledger = namespace["EXECUTED_CASES"]
            selected_ledger = (
                namespace["CaseLedger"]() if use_alternate_ledger else primary_ledger
            )
            primary_before = (primary_ledger.count, primary_ledger.case_ids)
            selected_before = (selected_ledger.count, selected_ledger.case_ids)
            context_before = (
                tuple(namespace["_ACTIVE_CASE_TOKENS"]),
                frozenset(namespace["_TAINTED_CASE_TOKENS"]),
            )
            ancestor_tainted = False

            def inner_action() -> None:
                namespace["require"](False, "forced nested failure")

            def outer_action() -> None:
                nonlocal ancestor_tainted
                try:
                    if use_alternate_ledger:
                        namespace["execute_case"](
                            f"{label}:inner-fails",
                            inner_action,
                            ledger=selected_ledger,
                        )
                    else:
                        namespace["execute_case"](
                            f"{label}:inner-fails",
                            inner_action,
                        )
                except AssertionError as exc:
                    if str(exc) != "forced nested failure":
                        failures.append(f"{label}: inner failure changed: {exc}")
                active_tokens = namespace["_ACTIVE_CASE_TOKENS"]
                if active_tokens:
                    ancestor_tainted = (
                        active_tokens[-1] in namespace["_TAINTED_CASE_TOKENS"]
                    )

            rejected = False
            try:
                if use_alternate_ledger:
                    namespace["execute_case"](
                        f"{label}:outer-must-reject",
                        outer_action,
                        ledger=selected_ledger,
                    )
                else:
                    namespace["execute_case"](
                        f"{label}:outer-must-reject",
                        outer_action,
                    )
            except AssertionError:
                rejected = True

            selected_after = (selected_ledger.count, selected_ledger.case_ids)
            primary_after = (primary_ledger.count, primary_ledger.case_ids)
            context_after = (
                tuple(namespace["_ACTIVE_CASE_TOKENS"]),
                frozenset(namespace["_TAINTED_CASE_TOKENS"]),
            )
            if not ancestor_tainted:
                failures.append(f"{label}: nested failure did not taint its ancestor")
            if not rejected:
                failures.append(f"{label}: ancestor accepted a swallowed nested failure")
            if selected_after != selected_before:
                failures.append(
                    f"{label}: selected ledger changed: "
                    f"{selected_before} -> {selected_after}"
                )
            if primary_after != primary_before:
                failures.append(
                    f"{label}: global ledger changed: {primary_before} -> {primary_after}"
                )
            if context_after != context_before:
                failures.append(
                    f"{label}: ownership context changed: "
                    f"{context_before} -> {context_after}"
                )

        require(
            not failures,
            "nested failure propagation regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework6_nested_failure_runtime", run)


def check_rework6_validator_contract() -> None:
    def run() -> None:
        failures: list[str] = []
        validator = globals().get("validate_checker_contract")
        if not callable(validator):
            failures.append("reusable checker self-contract validator missing")
        else:
            for label, (source, expected_violation) in (
                rework6_checker_contract_mutants().items()
            ):
                first = validator(source, filename=f"<mutant:{label}:first>")
                repeated = validator(source, filename=f"<mutant:{label}:repeated>")
                if first != repeated:
                    failures.append(
                        f"{label}: violation classes were not stable: "
                        f"{first} != {repeated}"
                    )
                violation_classes = {
                    violation.split(":", 1)[0]
                    for violation in first
                    if isinstance(violation, str) and violation
                }
                if expected_violation not in violation_classes:
                    failures.append(
                        f"{label}: expected {expected_violation}, got {first}"
                    )

        require(
            not failures,
            "rework6 validator regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework6_validator", run)


def check_rework6_expected_failure_isolation_contract() -> None:
    def run() -> None:
        failures: list[str] = []
        namespace = isolated_checker_namespace("expected_failure_isolation")
        helper = namespace.get("expect_case_failure")
        if not callable(helper):
            failures.append("expected-failure isolation helper missing")
        else:
            ledger = namespace["EXECUTED_CASES"]
            before = (ledger.count, ledger.case_ids)
            verified: list[str] = []

            def expected_inner_failure() -> None:
                namespace["require"](False, "forced expected failure")

            def self_contract_parent() -> None:
                helper(
                    "expected-inner",
                    expected_inner_failure,
                    expected_message="forced expected failure",
                )
                verified.append("expected-inner")

            try:
                namespace["execute_case"](
                    "self-contract-parent",
                    self_contract_parent,
                )
            except AssertionError as exc:
                failures.append(f"expected failure poisoned self-contract parent: {exc}")
            after = (ledger.count, ledger.case_ids)
            if verified != ["expected-inner"]:
                failures.append(f"expected failure was not verified: {verified}")
            if after != (before[0] + 1, before[1] + ("self-contract-parent",)):
                failures.append(
                    "expected failure isolation did not record only its parent: "
                    f"{before} -> {after}"
                )
            if namespace["_ACTIVE_CASE_TOKENS"] or namespace["_TAINTED_CASE_TOKENS"]:
                failures.append("expected failure isolation leaked ownership context")

        validator = globals().get("validate_checker_contract")
        if not callable(validator):
            failures.append("expected-failure helper allowlist validator missing")
        else:
            allowed_source, ordinary_source = rework6_expected_failure_contract_sources()
            allowed_violations = validator(
                allowed_source,
                filename="<expected_failure:self_contract>",
            )
            allowed_classes = {
                violation.split(":", 1)[0]
                for violation in allowed_violations
                if isinstance(violation, str) and violation
            }
            if "expected_failure_helper_outside_self_contract" in allowed_classes:
                failures.append(
                    "expected-failure helper rejected its narrow self-contract allowlist: "
                    f"{allowed_violations}"
                )

            ordinary_first = validator(
                ordinary_source,
                filename="<expected_failure:ordinary:first>",
            )
            ordinary_repeated = validator(
                ordinary_source,
                filename="<expected_failure:ordinary:repeated>",
            )
            if ordinary_first != ordinary_repeated:
                failures.append(
                    "ordinary expected-failure helper violation was not stable: "
                    f"{ordinary_first} != {ordinary_repeated}"
                )
            ordinary_classes = {
                violation.split(":", 1)[0]
                for violation in ordinary_first
                if isinstance(violation, str) and violation
            }
            if "expected_failure_helper_outside_self_contract" not in ordinary_classes:
                failures.append(
                    "ordinary check escaped expected-failure helper allowlist: "
                    f"{ordinary_first}"
                )

        require(
            not failures,
            "expected-failure isolation regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework6_expected_failure_isolation", run)


def check_rework7_capability_ledger_binding_contract() -> None:
    def run() -> None:
        failures: list[str] = []
        namespace = isolated_checker_namespace("rework7_capability_ledger_binding")
        owner_ledger = namespace["CaseLedger"]()
        foreign_ledger = namespace["CaseLedger"]()
        rejection = ""

        def attempt_foreign_record() -> None:
            nonlocal rejection
            capability = namespace["_ACTIVE_CASE_TOKENS"][-1]
            try:
                foreign_ledger._record("forged-foreign", capability)
            except AssertionError as exc:
                rejection = str(exc)

        namespace["execute_case"](
            "declared-owner",
            attempt_foreign_record,
            ledger=owner_ledger,
        )
        if rejection != "ledger capability does not select this ledger":
            failures.append(f"foreign ledger capability was not rejected: {rejection!r}")
        if foreign_ledger.case_ids:
            failures.append(
                f"foreign ledger accepted a mismatched capability: {foreign_ledger.case_ids}"
            )
        if owner_ledger.case_ids != ("declared-owner",):
            failures.append(f"owner ledger did not record exactly once: {owner_ledger.case_ids}")
        if namespace["_ACTIVE_CASE_TOKENS"] or namespace["_TAINTED_CASE_TOKENS"]:
            failures.append("capability-ledger probe leaked ownership state")

        require(
            not failures,
            "rework7 capability-ledger regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework7_capability_ledger_binding", run)


def check_rework7_cross_ledger_transaction_contract() -> None:
    def run() -> None:
        failures: list[str] = []

        for label, outer_is_primary in (
            ("alternate_success_before_global_failure", True),
            ("global_success_before_alternate_failure", False),
        ):
            namespace = isolated_checker_namespace(label)
            primary = namespace["EXECUTED_CASES"]
            alternate = namespace["CaseLedger"]()
            namespace["execute_case"]("seed-primary", lambda: None, ledger=primary)
            namespace["execute_case"]("seed-alternate", lambda: None, ledger=alternate)
            outer_ledger = primary if outer_is_primary else alternate
            inner_ledger = alternate if outer_is_primary else primary
            before = (primary.case_ids, alternate.case_ids)

            def outer_action() -> None:
                namespace["execute_case"](
                    f"{label}:inner-success",
                    lambda: None,
                    ledger=inner_ledger,
                )
                namespace["require"](False, f"{label}:forced-ancestor-failure")

            rejection = ""
            try:
                namespace["execute_case"](
                    f"{label}:outer-fails",
                    outer_action,
                    ledger=outer_ledger,
                )
            except AssertionError as exc:
                rejection = str(exc)
            after = (primary.case_ids, alternate.case_ids)
            if rejection != f"{label}:forced-ancestor-failure":
                failures.append(f"{label}: ancestor failure changed: {rejection!r}")
            if after != before:
                failures.append(f"{label}: touched ledgers did not roll back: {before} -> {after}")
            if namespace["_ACTIVE_CASE_TOKENS"] or namespace["_TAINTED_CASE_TOKENS"]:
                failures.append(f"{label}: ownership state leaked after rollback")

        for label, outer_is_primary in (
            ("primary_outer_alternate_inner_success", True),
            ("alternate_outer_primary_inner_success", False),
        ):
            namespace = isolated_checker_namespace(label)
            primary = namespace["EXECUTED_CASES"]
            alternate = namespace["CaseLedger"]()
            outer_ledger = primary if outer_is_primary else alternate
            inner_ledger = alternate if outer_is_primary else primary

            def outer_action() -> None:
                namespace["execute_case"](
                    f"{label}:inner",
                    lambda: None,
                    ledger=inner_ledger,
                )

            namespace["execute_case"](
                f"{label}:outer",
                outer_action,
                ledger=outer_ledger,
            )
            expected_primary = (
                (f"{label}:outer",) if outer_is_primary else (f"{label}:inner",)
            )
            expected_alternate = (
                (f"{label}:inner",) if outer_is_primary else (f"{label}:outer",)
            )
            if primary.case_ids != expected_primary:
                failures.append(
                    f"{label}: primary success was not exact-once: {primary.case_ids}"
                )
            if alternate.case_ids != expected_alternate:
                failures.append(
                    f"{label}: alternate success was not exact-once: {alternate.case_ids}"
                )
            if namespace["_ACTIVE_CASE_TOKENS"] or namespace["_TAINTED_CASE_TOKENS"]:
                failures.append(f"{label}: ownership state leaked after success")

        require(
            not failures,
            "rework7 cross-ledger transaction regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework7_cross_ledger_transaction", run)


def check_rework7_expected_failure_alias_validator_contract() -> None:
    def run() -> None:
        failures: list[str] = []
        for label, (source, should_reject) in rework7_expected_failure_alias_sources().items():
            first = validate_checker_contract(source, filename=f"<rework7:alias:{label}:first>")
            repeated = validate_checker_contract(
                source,
                filename=f"<rework7:alias:{label}:repeated>",
            )
            if first != repeated:
                failures.append(f"{label}: validator output was unstable: {first} != {repeated}")
            classes = {violation.split(":", 1)[0] for violation in first}
            rejected = "expected_failure_helper_outside_self_contract" in classes
            if rejected != should_reject:
                failures.append(
                    f"{label}: expected reject={should_reject}, got {first}"
                )

        require(
            not failures,
            "rework7 expected-failure alias regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework7_expected_failure_alias_validator", run)


def check_rework7_suppression_validator_contract() -> None:
    def run() -> None:
        failures: list[str] = []
        for label, (source, should_reject) in rework7_suppression_sources().items():
            first = validate_checker_contract(
                source,
                filename=f"<rework7:suppression:{label}:first>",
            )
            repeated = validate_checker_contract(
                source,
                filename=f"<rework7:suppression:{label}:repeated>",
            )
            if first != repeated:
                failures.append(f"{label}: validator output was unstable: {first} != {repeated}")
            classes = {violation.split(":", 1)[0] for violation in first}
            rejected = "check_failure_suppression" in classes
            if rejected != should_reject:
                failures.append(
                    f"{label}: expected reject={should_reject}, got {first}"
                )

        require(
            not failures,
            "rework7 suppression-validator regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework7_suppression_validator", run)


def check_rework7_ownership_mutation_validator_contract() -> None:
    def run() -> None:
        failures: list[str] = []
        for label, (source, should_reject) in rework7_ownership_mutation_sources().items():
            first = validate_checker_contract(
                source,
                filename=f"<rework7:ownership:{label}:first>",
            )
            repeated = validate_checker_contract(
                source,
                filename=f"<rework7:ownership:{label}:repeated>",
            )
            if first != repeated:
                failures.append(f"{label}: validator output was unstable: {first} != {repeated}")
            classes = {violation.split(":", 1)[0] for violation in first}
            rejected = "ownership_state_mutation" in classes
            if rejected != should_reject:
                failures.append(
                    f"{label}: expected reject={should_reject}, got {first}"
                )

        require(
            not failures,
            "rework7 ownership-validator regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework7_ownership_mutation_validator", run)


def check_rework7_runtime_ownership_mutation_contract() -> None:
    def run() -> None:
        failures: list[str] = []

        def active_clear_restore(namespace: dict[str, object]) -> None:
            tokens = namespace["_ACTIVE_CASE_TOKENS"]
            capability = tokens[-1]
            tokens.clear()
            tokens.append(capability)

        def active_pop_restore(namespace: dict[str, object]) -> None:
            tokens = namespace["_ACTIVE_CASE_TOKENS"]
            capability = tokens.pop()
            tokens.append(capability)

        def tainted_clear(namespace: dict[str, object]) -> None:
            try:
                namespace["require"](False, "forced-taint")
            except AssertionError:
                pass
            namespace["_TAINTED_CASE_TOKENS"].clear()

        def tainted_discard(namespace: dict[str, object]) -> None:
            try:
                namespace["require"](False, "forced-taint")
            except AssertionError:
                pass
            capability = namespace["_ACTIVE_CASE_TOKENS"][-1]
            namespace["_TAINTED_CASE_TOKENS"].discard(capability)

        def active_rebind(namespace: dict[str, object]) -> None:
            namespace["_ACTIVE_CASE_TOKENS"] = tuple(
                list(namespace["_ACTIVE_CASE_TOKENS"])
            )

        variants = (
            ("active_clear_restore", active_clear_restore),
            ("active_pop_restore", active_pop_restore),
            ("tainted_clear", tainted_clear),
            ("tainted_discard", tainted_discard),
            ("active_rebind", active_rebind),
        )
        for label, mutate in variants:
            namespace = isolated_checker_namespace(f"rework7_runtime:{label}")
            ledger = namespace["EXECUTED_CASES"]
            before = (ledger.count, ledger.case_ids)

            def action() -> None:
                mutate(namespace)

            rejected = False
            try:
                namespace["execute_case"](f"{label}:must-reject", action)
            except BaseException:
                rejected = True
            after = (ledger.count, ledger.case_ids)
            if not rejected:
                failures.append(f"{label}: ownership mutation was accepted")
            if after != before:
                failures.append(f"{label}: rejected mutation changed ledger: {before} -> {after}")
            if namespace["_ACTIVE_CASE_TOKENS"] or namespace["_TAINTED_CASE_TOKENS"]:
                failures.append(f"{label}: rejected mutation leaked ownership state")

        require(
            not failures,
            "rework7 runtime ownership regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework7_runtime_ownership_mutation", run)


def check_rework8_case_accounting_integrity_contract() -> None:
    def run() -> None:
        failures: list[str] = []
        sources = rework8_case_accounting_integrity_sources()
        validator_results: dict[str, list[str]] = {}

        for label, (source, expected_classes, _entrypoint) in sources.items():
            first = validate_checker_contract(
                source,
                filename=f"<rework8:case_integrity:{label}:first>",
            )
            repeated = validate_checker_contract(
                source,
                filename=f"<rework8:case_integrity:{label}:repeated>",
            )
            validator_results[label] = first
            if first != repeated:
                failures.append(f"{label}: validator output was unstable: {first} != {repeated}")
            classes = {violation.split(":", 1)[0] for violation in first}
            missing = set(expected_classes) - classes
            if missing:
                failures.append(
                    f"{label}: validator missed {sorted(missing)}: {first}"
                )

        primary_label = "ledger_alias_expected_snapshot_rewrite"
        primary_source, _expected_classes, primary_entrypoint = sources[primary_label]
        namespace = isolated_checker_namespace("rework8_case_integrity_runtime")
        exec(
            compile(primary_source, f"<rework8:runtime:{primary_label}>", "exec"),
            namespace,
        )
        ledger = namespace["EXECUTED_CASES"]
        before = (ledger.count, ledger.case_ids)
        namespace[primary_entrypoint]()
        after = (ledger.count, ledger.case_ids)
        if after != (before[0] + 2, before[1] + ("forged", "declared")):
            failures.append(
                f"{primary_label}: exploit probe no longer demonstrates extra accounting: "
                f"{before} -> {after}"
            )
        if not validator_results[primary_label]:
            failures.append(
                f"{primary_label}: validator accepted one declared case that accounted "
                f"two entries: {before} -> {after}"
            )

        require(
            not failures,
            "rework8 case-accounting integrity regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework8_case_integrity", run)


def check_rework4_case_accounting_contract() -> None:
    failures: list[str] = []

    try:
        require(True, "successful assertion must still be runtime-owned")
    except AssertionError:
        pass
    else:
        failures.append("assertion helper succeeded outside an active execute_case")

    unauthorized_ledger = CaseLedger()
    try:
        unauthorized_ledger.record("forged-record")
    except (AttributeError, AssertionError):
        pass
    else:
        failures.append("direct ledger.record succeeded outside execute_case ownership")

    for attribute, operation in (
        ("_case_ids", "append"),
        ("_seen", "add"),
    ):
        private_ledger = CaseLedger()
        try:
            getattr(getattr(private_ledger, attribute), operation)("forged-private")
        except (AttributeError, AssertionError):
            pass
        else:
            failures.append(f"direct private ledger mutation succeeded via {attribute}")

    validator = globals().get("validate_checker_contract")
    if not callable(validator):
        for label in rework4_checker_contract_mutants():
            failures.append(f"{label}: reusable checker self-contract validator missing")
    else:
        current_source = Path(__file__).read_text(encoding="utf-8")
        current_violations = validator(current_source, filename=__file__)
        if current_violations:
            failures.append(
                "current checker rejected by reusable self-contract: "
                + ", ".join(current_violations)
            )
        for label, (source, expected_violation) in rework4_checker_contract_mutants().items():
            violations = validator(source, filename=f"<mutant:{label}>")
            if not any(
                violation == expected_violation
                or violation.startswith(f"{expected_violation}:")
                for violation in violations
            ):
                failures.append(
                    f"{label}: mutant escaped expected {expected_violation}; got {violations}"
                )

    previous_ledger = EXECUTED_CASES
    previous_gates = OBSERVED_GATES
    previous_active_case_tokens = _ACTIVE_CASE_TOKENS
    previous_tainted_case_tokens = _TAINTED_CASE_TOKENS
    try:
        run_checker_groups(
            ((lambda: (_ for _ in ()).throw(AssertionError("forced group failure")),),),
            ledger=CaseLedger(),
            observed_gates=set(),
        )
    except AssertionError as exc:
        if str(exc) != "forced group failure":
            failures.append(f"group failure changed unexpectedly: {exc}")
    else:
        failures.append("forced checker-group failure did not propagate")
    if (
        EXECUTED_CASES is not previous_ledger
        or OBSERVED_GATES is not previous_gates
        or _ACTIVE_CASE_TOKENS is not previous_active_case_tokens
        or _TAINTED_CASE_TOKENS is not previous_tainted_case_tokens
    ):
        failures.append("checker-group failure did not restore global runtime ownership")

    def run() -> None:
        require(
            not failures,
            "case-accounting contract regressions: " + " | ".join(failures),
        )

    execute_case("case_accounting:rework4_contract", run)


def checker_groups() -> tuple[tuple[object, ...], ...]:
    return (
        (
            check_completion_reason_integrity,
            check_rework5_reflective_validator_contract,
            check_rework5_runtime_ownership_contract,
            check_failed_declared_evidence_is_not_completable,
            check_severity_and_diagnostics_are_independent,
            check_rework4_case_accounting_contract,
            check_padded_canonical_tokens,
            check_registry_id_contract,
            check_authoritative_registry_scope,
            check_completion_expected_work_kind_is_canonical,
            check_section_linked_freshness_contract,
            check_risk_residual_contract,
            check_result_gap_contract_precedence,
            check_registry_charter_revision_types,
            check_blocked_shape_diagnostics,
            check_freshness_reason_deduplication,
            check_known_section_failure_precedence,
        ),
        (
            check_default,
            check_five_level_and_structure_cases,
            check_all_work_kinds_table_driven,
            check_runtime_computed_freshness,
            check_section_evidence_linkage,
            check_unreferenced_registry_duplicates,
            check_completion_guard_reauthentication,
            check_evidence_uniqueness_and_completion_guard,
            check_section_reason_types,
        ),
    )


def rework6_red_groups() -> tuple[tuple[object, ...], ...]:
    return (
        (check_rework6_nested_failure_runtime_contract,),
        (check_rework6_validator_contract,),
        (check_rework6_expected_failure_isolation_contract,),
    )


def rework7_red_groups() -> tuple[tuple[object, ...], ...]:
    return (
        (check_rework7_capability_ledger_binding_contract,),
        (check_rework7_cross_ledger_transaction_contract,),
        (check_rework7_expected_failure_alias_validator_contract,),
        (check_rework7_suppression_validator_contract,),
        (check_rework7_ownership_mutation_validator_contract,),
        (check_rework7_runtime_ownership_mutation_contract,),
    )


def rework8_red_groups() -> tuple[tuple[object, ...], ...]:
    return ((check_rework8_case_accounting_integrity_contract,),)


def run_checker_groups(
    groups: tuple[tuple[object, ...], ...],
    *,
    ledger: CaseLedger,
    observed_gates: set[str],
) -> None:
    global EXECUTED_CASES, OBSERVED_GATES, _ACTIVE_CASE_TOKENS, _TAINTED_CASE_TOKENS

    previous_ledger = EXECUTED_CASES
    previous_gates = OBSERVED_GATES
    previous_active_case_tokens = _ACTIVE_CASE_TOKENS
    previous_tainted_case_tokens = _TAINTED_CASE_TOKENS
    EXECUTED_CASES = ledger
    OBSERVED_GATES = observed_gates
    _ACTIVE_CASE_TOKENS = ()
    _TAINTED_CASE_TOKENS = frozenset()
    try:
        for group in groups:
            for checker in group:
                checker()
    finally:
        EXECUTED_CASES = previous_ledger
        OBSERVED_GATES = previous_gates
        _ACTIVE_CASE_TOKENS = previous_active_case_tokens
        _TAINTED_CASE_TOKENS = previous_tainted_case_tokens


def check_case_count_contract() -> None:
    def run() -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        module = ast.parse(source, filename=__file__)

        def direct_nodes(function: ast.FunctionDef) -> list[ast.AST]:
            found: list[ast.AST] = []
            pending = list(function.body)
            while pending:
                node = pending.pop()
                found.append(node)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                pending.extend(ast.iter_child_nodes(node))
            return found

        record_case_violations = [
            f"definition:{node.lineno}"
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "record_case"
        ]
        record_case_violations.extend(
            f"call:{node.lineno}"
            for node in ast.walk(module)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_case"
        )
        require(
            not record_case_violations,
            "record_case escape hatch present: " + ", ".join(record_case_violations),
        )

        main_function: ast.FunctionDef | None = None
        for function in module.body:
            if isinstance(function, ast.FunctionDef) and function.name == "main":
                main_function = function
            if not isinstance(function, ast.FunctionDef) or not function.name.startswith("check_"):
                continue
            nodes = direct_nodes(function)
            invalid_returns = [
                node.lineno
                for node in nodes
                if isinstance(node, ast.Return) and node.value is not None
            ]
            require(
                not invalid_returns,
                f"{function.name}: non-None returns at {invalid_returns}",
            )
            require(
                any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "execute_case"
                    for node in nodes
                ),
                f"{function.name}: no execute_case orchestration",
            )
            direct_ledger_records = [
                node.lineno
                for node in nodes
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "record"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "EXECUTED_CASES"
            ]
            require(
                not direct_ledger_records,
                f"{function.name}: direct EXECUTED_CASES.record at {direct_ledger_records}",
            )
            unwrapped_assertions = [
                node.lineno
                for node in nodes
                if isinstance(node, (ast.Assert, ast.Raise))
                or (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "require"
                )
            ]
            require(
                function.name
                in {
                    "check_case_count_contract",
                    "check_rework4_case_accounting_contract",
                }
                or not unwrapped_assertions,
                f"{function.name}: scenario assertions outside execute_case action at "
                f"{unwrapped_assertions}",
            )

        require(main_function is not None, "main function missing")
        require(
            not any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "sum"
                for node in ast.walk(main_function)
            ),
            "main still sums checker-reported totals",
        )
        require(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "clear"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "EXECUTED_CASES"
                for node in ast.walk(main_function)
            ),
            "main does not reset the execution-derived ledger",
        )
        count_assignments = [
            node
            for node in ast.walk(main_function)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "case_count" for target in node.targets)
        ]
        require(
            len(count_assignments) == 1
            and isinstance(count_assignments[0].value, ast.Attribute)
            and count_assignments[0].value.attr == "count"
            and isinstance(count_assignments[0].value.value, ast.Name)
            and count_assignments[0].value.value.id == "EXECUTED_CASES",
            "main case count is not sourced only from EXECUTED_CASES.count",
        )
        embedded_totals = []
        for node in ast.walk(module):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            marker = "cases="
            if marker not in node.value:
                continue
            remainder = node.value.split(marker, 1)[1]
            suffix = remainder.split(maxsplit=1)[0] if remainder else ""
            if suffix.isdigit():
                embedded_totals.append(f"{node.lineno}:{suffix}")
        require(
            not embedded_totals,
            "manually embedded expected totals: " + ", ".join(embedded_totals),
        )

        ledger = CaseLedger()
        execute_case("baseline", lambda: None, ledger=ledger)
        baseline_count = ledger.count
        execute_case("extra", lambda: None, ledger=ledger)
        require(
            ledger.count == baseline_count + 1,
            "executing an extra scenario did not increment the reported count",
        )
        expect_case_failure(
            "extra",
            lambda: None,
            expected_message="duplicate case id: extra",
            ledger=ledger,
        )

        failing_count = ledger.count

        def forced_failure() -> None:
            raise AssertionError("forced failure")

        expect_case_failure(
            "failing",
            forced_failure,
            expected_message="forced failure",
            ledger=ledger,
        )
        require(ledger.count == failing_count, "failing action entered the case ledger")

        def invalid_risk_residual(outcome, _registry, _observed) -> None:
            outcome["risk_boundary"]["status"] = "PASSED_WITH_RESIDUAL"
            outcome["residual_gaps"] = ["A bounded risk remains."]

        risk_count = ledger.count
        expect_case_failure(
            "forced_risk_residual_failure",
            gate_action(
                "forced_risk_residual_failure",
                "PASSED",
                invalid_risk_residual,
            ),
            expected_message_prefix="forced_risk_residual_failure: ",
            ledger=ledger,
        )
        require(
            ledger.count == risk_count,
            "forced failing risk-residual scenario entered the case ledger",
        )

        groups = checker_groups()
        repeated_ledgers = (CaseLedger(), CaseLedger())
        for repeated_ledger in repeated_ledgers:
            run_checker_groups(groups, ledger=repeated_ledger, observed_gates=set())
        reordered_groups = tuple(tuple(reversed(group)) for group in reversed(groups))
        reordered_ledger = CaseLedger()
        run_checker_groups(reordered_groups, ledger=reordered_ledger, observed_gates=set())
        expected_ids = set(repeated_ledgers[0].case_ids)
        require(
            repeated_ledgers[0].count == repeated_ledgers[1].count == reordered_ledger.count,
            "repeated or reordered checker groups changed the unique case count",
        )
        require(
            expected_ids
            == set(repeated_ledgers[1].case_ids)
            == set(reordered_ledger.case_ids),
            "repeated or reordered checker groups changed the executed case ids",
        )

    execute_case("case_count_contract", run)


def check_five_level_gate_coverage() -> None:
    def run() -> None:
        require(
            OBSERVED_GATES
            == {"PASSED", "PASSED_WITH_CONCERNS", "RETURN_FOR_REWORK", "PARTIAL", "BLOCKED"},
            f"five-level gate coverage drifted: {sorted(OBSERVED_GATES)}",
        )

    execute_case("five_level_gate_coverage", run)


def main() -> int:
    global _ACTIVE_CASE_TOKENS, _TAINTED_CASE_TOKENS

    EXECUTED_CASES.clear()
    OBSERVED_GATES.clear()
    _ACTIVE_CASE_TOKENS = ()
    _TAINTED_CASE_TOKENS = frozenset()
    for group in checker_groups():
        for checker in group:
            checker()
    check_case_count_contract()
    check_five_level_gate_coverage()
    for group in rework6_red_groups():
        for checker in group:
            checker()
    for group in rework7_red_groups():
        for checker in group:
            checker()
    for group in rework8_red_groups():
        for checker in group:
            checker()
    case_count = EXECUTED_CASES.count
    print(f"COURT_OUTCOME_GATE_OK cases={case_count} freshness=RUNTIME_COMPUTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
