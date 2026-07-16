"""RED checks for A02 host-memory, Obsidian projection, and child traces.

The checker is intentionally read-only.  It exercises pure public policy
evaluators when they exist and verifies the existing runtime-to-Shiguan
projection without creating memory notes, runtime ledgers, or Shiguan records.
Planning, create-only receipt evaluation, and later read-only ingestion
verification are distinct observable states.
"""

from __future__ import annotations

from copy import deepcopy
import importlib
import sys
from typing import Any, Callable, Iterable


sys.dont_write_bytecode = True


HOST_MEMORY_MODULES = (
    "shiguan_host_memory_projection",
    "memory_decision",
    "court_runtime",
)
HOST_MEMORY_FUNCTIONS = (
    "evaluate_host_memory_projection",
    "evaluate_host_memory_candidate",
    "plan_host_memory_update_note",
)
CHILD_TRACE_MODULES = (
    "court_child_trace",
    "court_runtime",
    "archive_runtime_task",
)
CHILD_TRACE_FUNCTIONS = (
    "validate_child_trace_summaries",
    "validate_child_trace_contract",
)
MEMORY_GRAPH_MODULES = (
    "shiguan_host_memory_projection",
    "internal_memory_shiguan_bridge",
    "sync_shiguan_obsidian_vault",
)
MEMORY_GRAPH_FUNCTIONS = (
    "evaluate_installed_tool_memory_projection",
    "evaluate_tool_class_memory_graph_projection",
    "plan_obsidian_memory_graph_projection",
)
BLANK_HOST_PREFLIGHT_MODULES = (
    "blank_host_memory_preflight",
    "ensure_portable_court_bootstrap",
    "shiguan_host_memory_projection",
)
BLANK_HOST_PREFLIGHT_FUNCTIONS = (
    "evaluate_blank_host_memory_preflight",
    "plan_blank_host_memory_feature_probe",
    "evaluate_memory_feature_preflight",
)

CANONICAL_TOOL_CLASSES = (
    "codex",
    "hermes",
    "claude-code",
    "other:fixture-cli",
)
MEMORY_PROBE_STATES = {
    "codex": "enabled",
    "hermes": "disabled",
    "claude-code": "unavailable",
    "other:fixture-cli": "unknown",
}


def find_public_callable(
    module_names: Iterable[str], function_names: Iterable[str]
) -> tuple[Callable[..., Any] | None, str, list[str]]:
    errors: list[str] = []
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - diagnostic path
            errors.append(f"{module_name}: {type(exc).__name__}: {exc}")
            continue
        for function_name in function_names:
            candidate = getattr(module, function_name, None)
            if callable(candidate):
                return candidate, f"{module_name}.{function_name}", errors
    return None, "", errors


def decision_flag(result: object) -> bool | None:
    if not isinstance(result, dict):
        return None
    for key in ("allowed", "ok", "accepted"):
        value = result.get(key)
        if isinstance(value, bool):
            return value
    return None


def decision_status(result: object) -> str:
    if not isinstance(result, dict):
        return ""
    return str(result.get("status") or result.get("decision") or "")


def nested_dicts(value: object) -> Iterable[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested_dicts(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from nested_dicts(child)


def tool_class_from(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("tool_class") or value.get("canonical_tool_class") or "")
    return str(value)


def graph_map(result: object) -> dict[str, dict[str, object]]:
    if not isinstance(result, dict):
        return {}
    value = result.get("graphs") or result.get("tool_graphs")
    if isinstance(value, dict):
        return {
            str(key): graph
            for key, graph in value.items()
            if isinstance(graph, dict)
        }
    if isinstance(value, list):
        found: dict[str, dict[str, object]] = {}
        for graph in value:
            if not isinstance(graph, dict):
                continue
            tool_class = tool_class_from(graph)
            if tool_class:
                found[tool_class] = graph
        return found
    return {}


def probe_result_map(result: object) -> dict[str, dict[str, object]]:
    if not isinstance(result, dict):
        return {}
    value = result.get("probe_results") or result.get("tools") or result.get("results")
    if isinstance(value, dict):
        return {
            str(key): item
            for key, item in value.items()
            if isinstance(item, dict)
        }
    if isinstance(value, list):
        found: dict[str, dict[str, object]] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            tool_class = tool_class_from(item)
            if tool_class:
                found[tool_class] = item
        return found
    return {}


def blocked_tool_classes(result: object) -> set[str]:
    if not isinstance(result, dict):
        return set()
    found: set[str] = set()
    for key in (
        "blocked_mutations",
        "mutation_blocked_tool_classes",
        "automatic_enablement_blocked",
    ):
        value = result.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            tool_class = tool_class_from(item)
            if tool_class:
                found.add(tool_class)
    return found


def host_memory_base_request() -> dict[str, object]:
    return {
        "evaluation_phase": "planning",
        "newest_explicit_user_authorization": True,
        "menxia_approved": True,
        "current_agent": "codex",
        "target_agent": "codex",
        "target_path": (
            "X:\\red-fixture\\.codex\\memories\\extensions\\ad_hoc\\notes\\"
            "20260714-a02-host-memory.md"
        ),
        "append_only": True,
        "direct_memory_md_write": False,
        "contains_private_body": False,
        "requested_status": "NOTE_CANDIDATE_ALLOWED",
        "create_only_receipt": None,
        "ingestion_verification": None,
        "ingestion_verified": False,
        "dry_run": True,
    }


def host_memory_create_receipt_request() -> dict[str, object]:
    request = host_memory_base_request()
    request.update(
        {
            "evaluation_phase": "create_receipt",
            "requested_status": "NOTE_CREATED_PENDING_INGESTION",
            "create_only_receipt": {
                "success": True,
                "write_mode": "create_only",
                "receipt_id": "fixture-create-only-receipt",
                "target_path": request["target_path"],
                "sha256": "a" * 64,
            },
        }
    )
    return request


def host_memory_ingestion_verification_request() -> dict[str, object]:
    request = host_memory_create_receipt_request()
    request.update(
        {
            "evaluation_phase": "ingestion_verification",
            "requested_status": "APPLIED_VERIFIED",
            "ingestion_verified": True,
            "ingestion_verification": {
                "confirmed": True,
                "method": "read_only",
                "evidence_pointer": "fixture://codex-memory-readback",
            },
        }
    )
    return request


def host_memory_rejection_cases() -> list[tuple[str, dict[str, object]]]:
    base = host_memory_base_request()
    cases: list[tuple[str, dict[str, object]]] = []

    def changed(name: str, **updates: object) -> None:
        request = dict(base)
        request.update(updates)
        cases.append((name, request))

    changed(
        "missing_latest_explicit_user_authorization",
        newest_explicit_user_authorization=False,
    )
    changed("missing_menxia_approval", menxia_approved=False)
    changed("current_agent_is_not_codex", current_agent="hermes")
    changed("target_agent_is_not_current_codex", target_agent="claude-code")
    changed(
        "direct_memory_md_write",
        target_path="X:\\red-fixture\\.codex\\memories\\MEMORY.md",
        direct_memory_md_write=True,
    )
    changed("contains_private_body", contains_private_body=True)
    changed(
        "note_creation_claimed_as_ingested",
        requested_status="APPLIED_VERIFIED",
        ingestion_verified=False,
    )
    changed(
        "dry_run_planning_claims_note_created",
        requested_status="NOTE_CREATED_PENDING_INGESTION",
    )
    changed(
        "created_status_without_create_only_receipt",
        evaluation_phase="create_receipt",
        requested_status="NOTE_CREATED_PENDING_INGESTION",
        create_only_receipt=None,
    )
    invalid_ingestion = host_memory_create_receipt_request()
    invalid_ingestion.update(
        {
            "evaluation_phase": "ingestion_verification",
            "requested_status": "APPLIED_VERIFIED",
            "ingestion_verified": True,
            "ingestion_verification": {
                "confirmed": True,
                "method": "write_back",
                "evidence_pointer": "fixture://invalid-write-verification",
            },
        }
    )
    cases.append(("ingestion_verification_is_not_read_only", invalid_ingestion))
    changed(
        "target_is_not_append_only_ad_hoc_note",
        target_path="X:\\red-fixture\\.codex\\memories\\candidate.md",
        append_only=False,
    )
    return cases


def check_host_memory_contract(failures: list[str]) -> None:
    evaluator, source, import_errors = find_public_callable(
        HOST_MEMORY_MODULES, HOST_MEMORY_FUNCTIONS
    )
    if evaluator is None:
        failures.append(
            "host_memory_public_api_missing: expected a pure evaluator named one of "
            + ", ".join(HOST_MEMORY_FUNCTIONS)
        )
        for case_name, _ in host_memory_rejection_cases():
            failures.append(
                f"host_memory_case_unexercised:{case_name}: no public evaluator"
            )
        if import_errors:
            failures.append("host_memory_import_diagnostics: " + " | ".join(import_errors))
        return

    for case_name, request in host_memory_rejection_cases():
        try:
            result = evaluator(deepcopy(request))
        except Exception as exc:
            failures.append(
                f"host_memory_case_error:{case_name}:{source}:"
                f"{type(exc).__name__}:{exc}"
            )
            continue
        if decision_flag(result) is not False:
            failures.append(
                f"host_memory_rejection_missing:{case_name}:{source}:result={result!r}"
            )
        if decision_status(result) == "APPLIED_VERIFIED":
            failures.append(
                f"host_memory_false_ingestion_claim:{case_name}:{source}:result={result!r}"
            )

    valid_request = host_memory_base_request()
    try:
        valid_result = evaluator(deepcopy(valid_request))
    except Exception as exc:
        failures.append(
            f"host_memory_valid_candidate_error:{source}:{type(exc).__name__}:{exc}"
        )
        return
    if decision_flag(valid_result) is not True:
        failures.append(
            f"host_memory_valid_candidate_rejected:{source}:result={valid_result!r}"
        )
    if decision_status(valid_result) != "NOTE_CANDIDATE_ALLOWED":
        failures.append(
            "host_memory_planning_status_invalid:"
            f"{source}:result={valid_result!r}"
        )
    if decision_status(valid_result) in {
        "NOTE_CREATED_PENDING_INGESTION",
        "APPLIED_VERIFIED",
    }:
        failures.append(
            "host_memory_dry_run_overclaimed_state:"
            f"{source}:result={valid_result!r}"
        )

    create_request = host_memory_create_receipt_request()
    try:
        create_result = evaluator(deepcopy(create_request))
    except Exception as exc:
        failures.append(
            f"host_memory_create_receipt_error:{source}:{type(exc).__name__}:{exc}"
        )
    else:
        if decision_flag(create_result) is not True:
            failures.append(
                f"host_memory_create_receipt_rejected:{source}:result={create_result!r}"
            )
        if decision_status(create_result) != "NOTE_CREATED_PENDING_INGESTION":
            failures.append(
                "host_memory_create_receipt_status_invalid:"
                f"{source}:result={create_result!r}"
            )

    ingestion_request = host_memory_ingestion_verification_request()
    try:
        ingestion_result = evaluator(deepcopy(ingestion_request))
    except Exception as exc:
        failures.append(
            f"host_memory_ingestion_verification_error:{source}:"
            f"{type(exc).__name__}:{exc}"
        )
    else:
        if decision_flag(ingestion_result) is not True:
            failures.append(
                "host_memory_ingestion_verification_rejected:"
                f"{source}:result={ingestion_result!r}"
            )
        if decision_status(ingestion_result) != "APPLIED_VERIFIED":
            failures.append(
                "host_memory_ingestion_verification_status_invalid:"
                f"{source}:result={ingestion_result!r}"
            )


def install_projection_fixture() -> dict[str, object]:
    return {
        "schema": "court.install_projection.v1",
        "skill_name": "court-capability-router",
        "tools": [
            {
                "tool_id": "codex-fixture",
                "tool_class": "codex",
                "detected": True,
                "selected": True,
                "court_skill_installed": True,
            },
            {
                "tool_id": "hermes-fixture",
                "tool_class": "hermes",
                "detected": True,
                "selected": True,
                "court_skill_installed": True,
            },
            {
                "tool_id": "claude-fixture",
                "tool_class": "claude-code",
                "detected": True,
                "selected": False,
                "court_skill_installed": True,
            },
            {
                "tool_id": "fixture-cli",
                "tool_class": "other:fixture-cli",
                "detected": False,
                "selected": True,
                "court_skill_installed": True,
            },
            {
                "tool_id": "not-installed",
                "tool_class": "other:not-installed",
                "detected": True,
                "selected": False,
                "court_skill_installed": False,
            },
            {
                "tool_id": "invalid-class",
                "tool_class": "other:Bad Id!",
                "detected": True,
                "selected": True,
                "court_skill_installed": True,
            },
        ],
    }


def memory_source_fixtures() -> dict[str, list[dict[str, object]]]:
    paths = {
        "codex": ".codex/memories/MEMORY.md",
        "hermes": ".hermes/MEMORY.md",
        "claude-code": ".claude/memory/MEMORY.md",
        "other:fixture-cli": ".fixture-cli/memories/index.json",
    }
    return {
        tool_class: [
            {
                "relative_source_id": f"{tool_class}:fixture-index",
                "relative_source_path": path,
                "sha256": str(index) * 64,
                "state": "enabled",
                "headings": [f"{tool_class} heading"],
                "topics": [f"{tool_class}-only-topic"],
                "relations": [
                    {
                        "source_id": f"{tool_class}:fixture-index",
                        "target_id": f"{tool_class}:fixture-topic",
                    }
                ],
                "raw_body": f"DO_NOT_PROJECT_RAW_BODY_{tool_class}",
                "private_body": f"DO_NOT_PROJECT_PRIVATE_BODY_{tool_class}",
                "package_path": "X:\\red-fixture\\release-fixture.zip",
                "include_in_package": True,
            }
        ]
        for index, (tool_class, path) in enumerate(paths.items(), start=1)
    }


def check_installed_tool_memory_graph(failures: list[str]) -> None:
    evaluator, source, import_errors = find_public_callable(
        MEMORY_GRAPH_MODULES, MEMORY_GRAPH_FUNCTIONS
    )
    if evaluator is None:
        failures.extend(
            [
                "memory_graph_public_api_missing: expected a pure evaluator named one of "
                + ", ".join(MEMORY_GRAPH_FUNCTIONS),
                "memory_graph_manifest_eligibility_unexercised: no public evaluator",
                "memory_graph_canonical_tool_classes_unexercised: no public evaluator",
                "memory_graph_namespace_isolation_unexercised: no public evaluator",
                "memory_graph_source_read_only_unexercised: no public evaluator",
                "memory_graph_metadata_only_package_exclusion_unexercised: no public evaluator",
            ]
        )
        if import_errors:
            failures.append("memory_graph_import_diagnostics: " + " | ".join(import_errors))
        return

    projection = install_projection_fixture()
    projection_before = deepcopy(projection)
    source_fixtures = memory_source_fixtures()
    source_before = deepcopy(source_fixtures)
    calls: list[str] = []

    def read_source_metadata(tool: object, *_args: object, **_kwargs: object) -> object:
        tool_class = tool_class_from(tool)
        calls.append(f"metadata:{tool_class}")
        return deepcopy(source_fixtures.get(tool_class, []))

    def forbidden_host_scan(*_args: object, **_kwargs: object) -> object:
        calls.append("host_scan")
        return [{"tool_class": "other:scan-only", "court_skill_installed": True}]

    def forbidden_effect(name: str) -> Callable[..., object]:
        def effect(*_args: object, **_kwargs: object) -> object:
            calls.append(name)
            raise AssertionError(f"fixture forbids {name}")

        return effect

    request = {
        "install_projection": projection,
        "projection_mode": "default",
        "output_root": "X:\\red-fixture\\obsidian-projection",
        "callbacks": {
            "read_source_metadata": read_source_metadata,
            "read_source_body": forbidden_effect("source_body_read"),
            "write_source": forbidden_effect("source_write"),
            "scan_host_tools": forbidden_host_scan,
            "write_obsidian": forbidden_effect("obsidian_write"),
            "include_package": forbidden_effect("package_include"),
        },
    }
    try:
        result = evaluator(request)
    except Exception as exc:
        failures.append(
            f"memory_graph_valid_fixture_error:{source}:{type(exc).__name__}:{exc}"
        )
        return

    if decision_flag(result) is not True:
        failures.append(f"memory_graph_valid_fixture_rejected:{source}:result={result!r}")
    graphs = graph_map(result)
    expected = set(CANONICAL_TOOL_CLASSES)
    if set(graphs) != expected:
        failures.append(
            "memory_graph_manifest_eligibility_invalid:"
            f"{source}:expected={sorted(expected)!r}:actual={sorted(graphs)!r}"
        )
    metadata_calls = {item.removeprefix("metadata:") for item in calls if item.startswith("metadata:")}
    if metadata_calls != expected or "host_scan" in calls:
        failures.append(
            "memory_graph_used_nonmanifest_discovery:"
            f"{source}:metadata_calls={sorted(metadata_calls)!r}:calls={calls!r}"
        )
    forbidden_calls = {
        "source_body_read",
        "source_write",
        "obsidian_write",
        "package_include",
    }.intersection(calls)
    if forbidden_calls or projection != projection_before or source_fixtures != source_before:
        failures.append(
            "memory_graph_source_not_read_only:"
            f"{source}:forbidden_calls={sorted(forbidden_calls)!r}"
        )

    namespaces: set[str] = set()
    for tool_class, graph in graphs.items():
        namespace = str(graph.get("namespace") or graph.get("namespace_id") or "")
        if not namespace or namespace in namespaces:
            failures.append(
                f"memory_graph_namespace_not_isolated:{tool_class}:{source}:namespace={namespace!r}"
            )
        namespaces.add(namespace)
        for item in nested_dicts(graph):
            item_class = tool_class_from(item)
            if item_class and item_class != tool_class:
                failures.append(
                    "memory_graph_cross_tool_item:"
                    f"owner={tool_class}:item_class={item_class}:{source}:item={item!r}"
                )
                break
        nodes = graph.get("nodes")
        edges = graph.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            failures.append(
                f"memory_graph_nodes_edges_missing:{tool_class}:{source}:graph={graph!r}"
            )
            continue
        node_ids = {
            str(node.get("id"))
            for node in nodes
            if isinstance(node, dict) and node.get("id") is not None
        }
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            edge_source = edge.get("source") or edge.get("from") or edge.get("source_id")
            edge_target = edge.get("target") or edge.get("to") or edge.get("target_id")
            if str(edge_source) not in node_ids or str(edge_target) not in node_ids:
                failures.append(
                    "memory_graph_cross_namespace_edge:"
                    f"owner={tool_class}:{source}:edge={edge!r}:node_ids={sorted(node_ids)!r}"
                )

    serialized = repr(result)
    forbidden_keys = {
        "raw_body",
        "private_body",
        "package_path",
        "include_in_package",
    }
    leaked_keys = sorted(
        key
        for item in nested_dicts(result)
        for key in item
        if key in forbidden_keys
    )
    required_projection_fields = {
        "relative_source_path",
        "state",
        "headings",
        "topics",
        "relations",
    }
    projected_records = [
        item for item in nested_dicts(result) if "relative_source_path" in item
    ]
    incomplete = [
        item
        for item in projected_records
        if not required_projection_fields.issubset(item)
        or not (item.get("sha256") or item.get("fingerprint"))
        or not (item.get("relative_source_id") or item.get("source_id"))
        or str(item.get("relative_source_path", "")).startswith(("X:\\", "/"))
    ]
    if (
        not projected_records
        or incomplete
        or leaked_keys
        or "DO_NOT_PROJECT_" in serialized
        or "release-fixture.zip" in serialized
    ):
        failures.append(
            "memory_graph_metadata_only_projection_invalid:"
            f"{source}:records={len(projected_records)}:incomplete={incomplete!r}:"
            f"leaked_keys={leaked_keys!r}"
        )

    mixed_sources = memory_source_fixtures()
    mixed_sources["codex"][0]["relations"] = [
        {
            "source_id": "codex:fixture-index",
            "target_id": "hermes:fixture-index",
            "target_tool_class": "hermes",
        }
    ]

    def read_mixed_metadata(tool: object, *_args: object, **_kwargs: object) -> object:
        return deepcopy(mixed_sources.get(tool_class_from(tool), []))

    mixed_request = dict(request)
    mixed_request["callbacks"] = dict(
        request["callbacks"], read_source_metadata=read_mixed_metadata
    )
    try:
        mixed_result = evaluator(mixed_request)
    except Exception:
        pass
    else:
        if decision_flag(mixed_result) is not False:
            failures.append(
                f"memory_graph_cross_tool_relation_accepted:{source}:result={mixed_result!r}"
            )


def check_blank_host_memory_preflight(failures: list[str]) -> None:
    evaluator, source, import_errors = find_public_callable(
        BLANK_HOST_PREFLIGHT_MODULES, BLANK_HOST_PREFLIGHT_FUNCTIONS
    )
    if evaluator is None:
        failures.extend(
            [
                "blank_host_memory_preflight_public_api_missing: expected a pure evaluator named one of "
                + ", ".join(BLANK_HOST_PREFLIGHT_FUNCTIONS),
                "blank_host_manifest_probe_candidates_unexercised: no public evaluator",
                "blank_host_probe_before_write_unexercised: no public evaluator",
                "blank_host_probe_enum_evidence_prompt_unexercised: no public evaluator",
                "blank_host_probe_side_effect_free_unexercised: no public evaluator",
                "blank_host_unknown_fail_closed_unexercised: no public evaluator",
                "blank_host_unrequested_tool_mutation_unexercised: no public evaluator",
            ]
        )
        if import_errors:
            failures.append(
                "blank_host_memory_preflight_import_diagnostics: "
                + " | ".join(import_errors)
            )
        return

    projection = install_projection_fixture()
    projection_before = deepcopy(projection)
    events: list[str] = []

    def probe_memory_feature(tool: object, *_args: object, **_kwargs: object) -> object:
        tool_class = tool_class_from(tool)
        events.append(f"probe:{tool_class}")
        return {
            "tool_class": tool_class,
            "status": MEMORY_PROBE_STATES.get(tool_class, "unknown"),
            "evidence": [f"fixture://memory-probe/{tool_class}"],
            "prompt_required": True,
        }

    def forbidden_write(name: str) -> Callable[..., object]:
        def write(*_args: object, **_kwargs: object) -> object:
            events.append(f"write:{name}")
            raise AssertionError(f"read-only preflight attempted {name}")

        return write

    request = {
        "phase": "blank_host_read_only_preflight",
        "blank_host": True,
        "install_projection": projection,
        "newest_explicit_authorized_tool_classes": ["codex"],
        "requested_mutations": [
            {"tool_class": "hermes", "action": "enable_memory", "automatic": True},
            {"tool_class": "claude-code", "action": "install", "automatic": False},
            {
                "tool_class": "other:fixture-cli",
                "action": "enable_memory",
                "automatic": True,
            },
        ],
        "callbacks": {
            "probe_memory_feature": probe_memory_feature,
            "create_shared_root": forbidden_write("create_shared_root"),
            "enable_memory": forbidden_write("enable_memory"),
            "install_tool": forbidden_write("install_tool"),
            "write_config": forbidden_write("write_config"),
        },
    }
    try:
        result = evaluator(request)
    except Exception as exc:
        failures.append(
            f"blank_host_memory_preflight_fixture_error:{source}:"
            f"{type(exc).__name__}:{exc}"
        )
        return

    if decision_flag(result) is not True:
        failures.append(
            f"blank_host_memory_preflight_rejected:{source}:result={result!r}"
        )
    expected = set(MEMORY_PROBE_STATES)
    probe_calls = {
        event.removeprefix("probe:") for event in events if event.startswith("probe:")
    }
    write_events = [event for event in events if event.startswith("write:")]
    if probe_calls != expected:
        failures.append(
            "blank_host_manifest_probe_candidates_invalid:"
            f"{source}:expected={sorted(expected)!r}:actual={sorted(probe_calls)!r}"
        )
    if write_events or projection != projection_before:
        failures.append(
            "blank_host_probe_had_side_effect:"
            f"{source}:write_events={write_events!r}:projection_changed="
            f"{projection != projection_before}"
        )

    items = probe_result_map(result)
    for tool_class, expected_state in MEMORY_PROBE_STATES.items():
        item = items.get(tool_class, {})
        state = str(item.get("status") or item.get("state") or "")
        evidence = item.get("evidence")
        if (
            state != expected_state
            or not evidence
            or item.get("prompt_required") is not True
        ):
            failures.append(
                "blank_host_probe_result_invalid:"
                f"{tool_class}:{source}:expected_state={expected_state}:item={item!r}"
            )

    blocked = blocked_tool_classes(result)
    unknown_item = items.get("other:fixture-cli", {})
    if (
        unknown_item.get("automatic_enablement_allowed") is not False
        and "other:fixture-cli" not in blocked
    ):
        failures.append(
            f"blank_host_unknown_auto_enable_not_blocked:{source}:result={result!r}"
        )
    for tool_class in ("hermes", "claude-code", "other:fixture-cli"):
        item = items.get(tool_class, {})
        if item.get("mutation_allowed") is not False and tool_class not in blocked:
            failures.append(
                "blank_host_unrequested_tool_mutation_not_blocked:"
                f"{tool_class}:{source}:result={result!r}"
            )

    ordering = result.get("preflight_before_writes") if isinstance(result, dict) else None
    if ordering is not True or not isinstance(result, dict) or result.get("prompt_required") is not True:
        failures.append(
            "blank_host_probe_order_or_prompt_gate_missing:"
            f"{source}:result={result!r}"
        )


def child_trace_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    instances = (
        ("gongbu#0001", "A02-DISPATCH-001", "evidence://gongbu-0001"),
        ("gongbu#0002", "A02-DISPATCH-002", "evidence://gongbu-0002"),
    )
    events = (
        ("start", "accepted bounded assignment", "running", "execute bounded work", None),
        ("key_action", "performed one verified action", "running", "finish verification", None),
        ("finish", "reported verified result", "completed", "release temporary worker", None),
        ("release", "released temporary worker", "closed", None, "bounded work complete"),
    )
    for instance_index, (instance_id, dispatch_uid, evidence_pointer) in enumerate(
        instances, start=1
    ):
        for event_index, (event, behavior, status, next_text, release_reason) in enumerate(
            events, start=1
        ):
            record: dict[str, object] = {
                "time": f"2026-07-14T00:0{instance_index}:{event_index:02d}+00:00",
                "event": event,
                "action": event,
                "behavior_summary": behavior,
                "task_id": "CCR-R2-SHIR-20260714-A02",
                "dispatch_uid": dispatch_uid,
                "office_instance_id": instance_id,
                "agent_id": instance_id,
                "role": "gongbu",
                "agent_role": "gongbu",
                "direct_superior": "shangshu",
                "status": status,
                "from_state": "running",
                "to_state": status,
                "actor": "gongbu",
                "evidence_pointer": evidence_pointer,
                "evidence": evidence_pointer,
                "next": next_text,
                "release_reason": release_reason,
                "private_body": "DO_NOT_COPY_PRIVATE_BODY_SENTINEL",
                "prompt_body": "DO_NOT_COPY_PROMPT_SENTINEL",
            }
            records.append(record)
    return records


def trace_ok(result: object) -> bool | None:
    return decision_flag(result)


def traced_instance_ids(result: object) -> set[str]:
    if not isinstance(result, dict):
        return set()
    for key in ("instance_ids", "office_instance_ids"):
        value = result.get(key)
        if isinstance(value, list):
            return {str(item) for item in value}
    for key in ("instances", "instance_summaries"):
        value = result.get(key)
        if isinstance(value, dict):
            return {str(item) for item in value}
        if isinstance(value, list):
            found = set()
            for item in value:
                if isinstance(item, dict):
                    instance_id = item.get("office_instance_id") or item.get("instance_id")
                    if instance_id:
                        found.add(str(instance_id))
                elif item:
                    found.add(str(item))
            return found
    return set()


def check_child_trace_validator(failures: list[str]) -> None:
    validator, source, import_errors = find_public_callable(
        CHILD_TRACE_MODULES, CHILD_TRACE_FUNCTIONS
    )
    required_fields = (
        "time",
        "event",
        "behavior_summary",
        "task_id",
        "dispatch_uid",
        "office_instance_id",
        "role",
        "direct_superior",
        "status",
        "evidence_pointer",
        "next_or_release_reason",
    )
    if validator is None:
        failures.append(
            "child_trace_public_api_missing: expected a validator named one of "
            + ", ".join(CHILD_TRACE_FUNCTIONS)
        )
        for field in required_fields:
            failures.append(
                f"child_trace_missing_field_case_unexercised:{field}: no public validator"
            )
        failures.append(
            "child_trace_same_role_multi_instance_unexercised: no public validator"
        )
        if import_errors:
            failures.append("child_trace_import_diagnostics: " + " | ".join(import_errors))
        return

    valid = child_trace_records()
    try:
        valid_result = validator(deepcopy(valid))
    except Exception as exc:
        failures.append(
            f"child_trace_valid_case_error:{source}:{type(exc).__name__}:{exc}"
        )
        return
    if trace_ok(valid_result) is not True:
        failures.append(f"child_trace_valid_case_rejected:{source}:result={valid_result!r}")
    expected_instances = {"gongbu#0001", "gongbu#0002"}
    actual_instances = traced_instance_ids(valid_result)
    if actual_instances != expected_instances:
        failures.append(
            "child_trace_same_role_instances_collapsed:"
            f"{source}:expected={sorted(expected_instances)!r}:"
            f"actual={sorted(actual_instances)!r}:result={valid_result!r}"
        )

    for field in required_fields:
        invalid = deepcopy(valid)
        if field == "next_or_release_reason":
            invalid[0].pop("next", None)
            invalid[0].pop("release_reason", None)
        else:
            invalid[0].pop(field, None)
        try:
            result = validator(invalid)
        except Exception:
            continue
        if trace_ok(result) is not False:
            failures.append(
                f"child_trace_missing_field_accepted:{field}:{source}:result={result!r}"
            )

    for missing_event in ("key_action", "release"):
        invalid = [
            record
            for record in deepcopy(valid)
            if not (
                record["office_instance_id"] == "gongbu#0002"
                and record["event"] == missing_event
            )
        ]
        try:
            result = validator(invalid)
        except Exception:
            continue
        if trace_ok(result) is not False:
            failures.append(
                "child_trace_incomplete_instance_lifecycle_accepted:"
                f"{missing_event}:{source}:result={result!r}"
            )


def check_runtime_to_shiguan_projection(failures: list[str]) -> None:
    try:
        archive_runtime_task = importlib.import_module("archive_runtime_task")
        compact_events = getattr(archive_runtime_task, "compact_events")
        rendered = compact_events(
            "CCR-R2-SHIR-20260714-A02",
            100,
            child_trace_records(),
        )
    except Exception as exc:
        failures.append(
            f"child_trace_shiguan_projection_error:{type(exc).__name__}:{exc}"
        )
        return

    required_fragments = (
        "CCR-R2-SHIR-20260714-A02",
        "A02-DISPATCH-001",
        "A02-DISPATCH-002",
        "gongbu#0001",
        "gongbu#0002",
        "gongbu",
        "shangshu",
        "evidence://gongbu-0001",
        "evidence://gongbu-0002",
        "accepted bounded assignment",
        "released temporary worker",
    )
    missing = [fragment for fragment in required_fragments if fragment not in rendered]
    if missing:
        failures.append(
            "child_trace_shiguan_projection_missing_fields:"
            f"missing={missing!r}:rendered={rendered[:500]!r}"
        )
    for forbidden in (
        "DO_NOT_COPY_PRIVATE_BODY_SENTINEL",
        "DO_NOT_COPY_PROMPT_SENTINEL",
    ):
        if forbidden in rendered:
            failures.append(
                f"child_trace_shiguan_projection_leaked_private_body:{forbidden}"
            )


def main() -> int:
    failures: list[str] = []
    check_host_memory_contract(failures)
    check_installed_tool_memory_graph(failures)
    check_blank_host_memory_preflight(failures)
    check_child_trace_validator(failures)
    check_runtime_to_shiguan_projection(failures)
    if failures:
        print(f"A02_RED_EXPECTED_FAILURES={len(failures)}", file=sys.stderr)
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("A02_HOST_MEMORY_CHILD_TRACE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
