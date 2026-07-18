"""Read-only A02 host-memory, metadata projection, and child-trace checks."""

from __future__ import annotations

from copy import deepcopy
import sys

sys.dont_write_bytecode = True

import archive_runtime_task
import shiguan_host_memory_projection


TOOLS = {"codex", "hermes", "claude-code", "other:fixture-cli"}
PROBE_STATES = {
    "codex": "enabled",
    "hermes": "disabled",
    "claude-code": "unavailable",
    "other:fixture-cli": "unknown",
}


def expect(errors: list[str], condition: object, case: str) -> None:
    if not condition:
        errors.append(case)


def flag(result: object) -> bool | None:
    value = result.get("ok") if isinstance(result, dict) else None
    return value if isinstance(value, bool) else None


def status(result: object) -> str:
    return str(result.get("status") or "") if isinstance(result, dict) else ""


def nested(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from nested(child)


def tool_class(value: object) -> str:
    return (str(value.get("tool_class") or value.get("canonical_tool_class") or "")
            if isinstance(value, dict) else str(value))


def host_request() -> dict[str, object]:
    return {
        "evaluation_phase": "planning",
        "newest_explicit_user_authorization": True,
        "menxia_approved": True,
        "current_agent": "codex",
        "target_agent": "codex",
        "target_path": "X:\\fixture\\.codex\\memories\\extensions\\ad_hoc\\notes\\a02.md",
        "append_only": True,
        "direct_memory_md_write": False,
        "contains_private_body": False,
        "requested_status": "NOTE_CANDIDATE_ALLOWED",
        "create_only_receipt": None,
        "ingestion_verification": None,
        "ingestion_verified": False,
        "dry_run": True,
    }


def create_request() -> dict[str, object]:
    request = host_request()
    request.update(
        evaluation_phase="create_receipt",
        requested_status="NOTE_CREATED_PENDING_INGESTION",
        create_only_receipt={
            "success": True,
            "write_mode": "create_only",
            "receipt_id": "fixture-receipt",
            "target_path": request["target_path"],
            "sha256": "a" * 64,
        },
    )
    return request


def ingestion_request() -> dict[str, object]:
    request = create_request()
    request.update(
        evaluation_phase="ingestion_verification",
        requested_status="APPLIED_VERIFIED",
        ingestion_verified=True,
        ingestion_verification={
            "confirmed": True,
            "method": "read_only",
            "evidence_pointer": "fixture://memory-readback",
        },
    )
    return request


def check_host_memory(errors: list[str]) -> None:
    evaluate = shiguan_host_memory_projection.evaluate_host_memory_projection
    base = host_request()
    cases = [
        ("host_missing_user_authority", {"newest_explicit_user_authorization": False}),
        ("host_missing_menxia", {"menxia_approved": False}),
        ("host_wrong_current_agent", {"current_agent": "hermes"}),
        ("host_wrong_target_agent", {"target_agent": "claude-code"}),
        ("host_direct_memory", {"target_path": "X:\\fixture\\.codex\\memories\\MEMORY.md", "direct_memory_md_write": True}),
        ("host_private_body", {"contains_private_body": True}),
        ("host_false_ingestion", {"requested_status": "APPLIED_VERIFIED"}),
        ("host_planning_overclaim", {"requested_status": "NOTE_CREATED_PENDING_INGESTION"}),
        ("host_not_append_only", {"target_path": "X:\\fixture\\.codex\\memories\\candidate.md", "append_only": False}),
    ]
    for case, updates in cases:
        request = {**base, **updates}
        before = deepcopy(request)
        result = evaluate(request)
        expect(errors, flag(result) is False, case)
        expect(errors, request == before, case + "_mutated")
        expect(errors, status(result) != "APPLIED_VERIFIED", case + "_overclaimed")

    no_receipt = create_request()
    no_receipt["create_only_receipt"] = None
    result = evaluate(no_receipt)
    expect(errors, flag(result) is False and status(result) != "APPLIED_VERIFIED", "host_missing_create_receipt")
    bad_proof = ingestion_request()
    bad_proof["ingestion_verification"] = {
        "confirmed": True,
        "method": "write_back",
        "evidence_pointer": "fixture://bad-proof",
    }
    result = evaluate(bad_proof)
    expect(errors, flag(result) is False and status(result) != "APPLIED_VERIFIED", "host_ingestion_not_read_only")

    valid = (
        (host_request(), "NOTE_CANDIDATE_ALLOWED"),
        (create_request(), "NOTE_CREATED_PENDING_INGESTION"),
        (ingestion_request(), "APPLIED_VERIFIED"),
    )
    for request, expected in valid:
        before = deepcopy(request)
        result = evaluate(request)
        expect(errors, flag(result) is True and status(result) == expected, "host_valid_" + expected)
        expect(errors, request == before, "host_valid_request_mutated")


def install_projection() -> dict[str, object]:
    specs = (
        ("codex", True, True, True),
        ("hermes", True, True, True),
        ("claude-code", True, False, True),
        ("other:fixture-cli", True, True, False),
        ("other:not-installed", False, False, True),
        ("other:Bad Id!", True, True, True),
    )
    return {
        "tools": [
            {
                "tool_class": name,
                "court_skill_installed": installed,
                "selected": selected,
                "detected": detected,
            }
            for name, installed, selected, detected in specs
        ]
    }


def source_fixtures() -> dict[str, list[dict[str, object]]]:
    paths = {
        "codex": ".codex/memories/MEMORY.md",
        "hermes": ".hermes/MEMORY.md",
        "claude-code": ".claude/memory/MEMORY.md",
        "other:fixture-cli": ".fixture-cli/memories/index.json",
    }
    return {
        owner: [{
            "relative_source_id": owner + ":index",
            "relative_source_path": path,
            "sha256": str(index) * 64,
            "state": "enabled",
            "headings": [owner + " heading"],
            "topics": [owner + " topic"],
            "relations": [{"target_id": owner + ":topic"}],
            "raw_body": "DO_NOT_PROJECT_RAW_BODY",
            "private_body": "DO_NOT_PROJECT_PRIVATE_BODY",
            "package_path": "X:\\fixture\\release.zip",
            "include_in_package": True,
        }]
        for index, (owner, path) in enumerate(paths.items(), 1)
    }


def relative_path(value: object) -> bool:
    path = str(value or "").replace("\\", "/")
    return bool(path and not path.startswith("/") and not (len(path) > 1 and path[1] == ":")
                and all(part not in ("", ".", "..") for part in path.split("/")))


def check_memory_graph(errors: list[str]) -> None:
    evaluate = shiguan_host_memory_projection.evaluate_installed_tool_memory_projection
    projection, sources, calls = install_projection(), source_fixtures(), []
    projection_before, sources_before = deepcopy(projection), deepcopy(sources)

    def read_metadata(tool: object, *_args: object, **_kwargs: object) -> object:
        owner = tool_class(tool)
        calls.append("metadata:" + owner)
        return deepcopy(sources.get(owner, []))

    def forbidden(name: str):
        def effect(*_args: object, **_kwargs: object) -> object:
            calls.append(name)
            raise AssertionError(name)
        return effect

    request = {
        "install_projection": projection,
        "callbacks": {
            "read_source_metadata": read_metadata,
            "read_source_body": forbidden("source_body_read"),
            "write_source": forbidden("source_write"),
            "scan_host_tools": forbidden("host_scan"),
            "write_obsidian": forbidden("obsidian_write"),
            "include_package": forbidden("package_include"),
        },
    }
    result = evaluate(request)
    expect(errors, flag(result) is True, "graph_valid")
    graphs = result.get("graphs", {}) if isinstance(result, dict) else {}
    expect(errors, isinstance(graphs, dict) and set(graphs) == TOOLS, "graph_manifest_eligibility")
    expected_calls = {"metadata:" + owner for owner in TOOLS}
    expect(errors, set(calls) == expected_calls, "graph_nonmanifest_discovery")
    expect(errors, projection == projection_before and sources == sources_before, "graph_input_mutation")

    namespaces = set()
    for owner, graph in graphs.items():
        namespace = graph.get("namespace") if isinstance(graph, dict) else None
        expect(errors, bool(namespace) and namespace not in namespaces, "graph_namespace_" + owner)
        namespaces.add(namespace)
        nodes, edges = graph.get("nodes"), graph.get("edges")
        expect(errors, isinstance(nodes, list) and isinstance(edges, list), "graph_shape_" + owner)
        node_ids = {str(node.get("id")) for node in nodes if isinstance(node, dict) and node.get("id")}
        for edge in edges:
            expect(errors, isinstance(edge, dict)
                   and str(edge.get("source")) in node_ids
                   and str(edge.get("target")) in node_ids, "graph_edge_" + owner)
        for item in nested(graph):
            item_owner = tool_class(item)
            expect(errors, not item_owner or item_owner == owner, "graph_cross_tool_item_" + owner)

    forbidden_keys = {"raw_body", "private_body", "package_path", "include_in_package"}
    expect(errors, not any(forbidden_keys.intersection(item) for item in nested(result)), "graph_forbidden_keys")
    expect(errors, "DO_NOT_PROJECT_" not in repr(result) and "release.zip" not in repr(result), "graph_body_leak")
    records = [item for item in nested(result) if "relative_source_path" in item]
    required = {"relative_source_id", "relative_source_path", "sha256", "state", "headings", "topics", "relations"}
    expect(errors, bool(records), "graph_records_missing")
    for record in records:
        expect(errors, required.issubset(record) and relative_path(record["relative_source_path"]), "graph_record_shape")

    def evaluate_sources(candidate_sources: dict[str, list[dict[str, object]]]) -> object:
        def read(tool: object, *_args: object, **_kwargs: object) -> object:
            return deepcopy(candidate_sources.get(tool_class(tool), []))
        candidate = dict(request)
        candidate["callbacks"] = dict(request["callbacks"], read_source_metadata=read)
        return evaluate(candidate)

    mixed = source_fixtures()
    mixed["codex"][0]["relations"] = [{"target_id": "hermes:index", "target_tool_class": "hermes"}]
    expect(errors, flag(evaluate_sources(mixed)) is False, "graph_cross_tool_relation")
    for bad_path in ("C:/private/MEMORY.md", "/root/MEMORY.md", "../MEMORY.md", "//server/share.md"):
        bad = source_fixtures()
        bad["codex"][0]["relative_source_path"] = bad_path
        expect(errors, flag(evaluate_sources(bad)) is False, "graph_absolute_path")
    no_state = source_fixtures()
    no_state["codex"][0].pop("state")
    normalized = evaluate_sources(no_state)
    normalized_records = [item for item in nested(normalized) if item.get("relative_source_id") == "codex:index"]
    expect(errors, flag(normalized) is True
           and len(normalized_records) == 1
           and normalized_records[0].get("state") == "unknown", "graph_missing_state")


def check_blank_host(errors: list[str]) -> None:
    evaluate = shiguan_host_memory_projection.evaluate_blank_host_memory_preflight
    projection, events = install_projection(), []
    before = deepcopy(projection)

    def probe(tool: object, *_args: object, **_kwargs: object) -> object:
        owner = tool_class(tool)
        events.append("probe:" + owner)
        return {"status": PROBE_STATES.get(owner, "unknown"),
                "evidence": ["fixture://probe/" + owner], "prompt_required": True}

    def forbidden(name: str):
        def write(*_args: object, **_kwargs: object) -> object:
            events.append("write:" + name)
            raise AssertionError(name)
        return write

    request = {
        "install_projection": projection,
        "newest_explicit_authorized_tool_classes": ["codex"],
        "requested_mutations": [
            {"tool_class": "hermes", "action": "enable_memory"},
            {"tool_class": "claude-code", "action": "install"},
            {"tool_class": "other:fixture-cli", "action": "enable_memory"},
        ],
        "callbacks": {
            "probe_memory_feature": probe,
            "create_shared_root": forbidden("create_shared_root"),
            "enable_memory": forbidden("enable_memory"),
            "install_tool": forbidden("install_tool"),
            "write_config": forbidden("write_config"),
        },
    }
    result = evaluate(request)
    expect(errors, flag(result) is True, "blank_valid")
    expect(errors, projection == before and not any(item.startswith("write:") for item in events), "blank_side_effect")
    expect(errors, {item.removeprefix("probe:") for item in events} == TOOLS, "blank_probe_set")
    items = result.get("probe_results", {}) if isinstance(result, dict) else {}
    blocked = set(result.get("blocked_mutations", [])) if isinstance(result, dict) else set()
    expect(errors, isinstance(items, dict) and set(items) == TOOLS, "blank_result_set")
    for owner, expected_state in PROBE_STATES.items():
        item = items.get(owner, {})
        expect(errors, item.get("status") == expected_state and item.get("evidence")
               and item.get("prompt_required") is True, "blank_probe_result_" + owner)
        expect(errors, item.get("mutation_allowed") is False, "blank_mutation_" + owner)
    expect(errors, {"hermes", "claude-code", "other:fixture-cli"}.issubset(blocked), "blank_unrequested_block")
    expect(errors, "other:fixture-cli" in blocked
           or items.get("other:fixture-cli", {}).get("automatic_enablement_allowed") is False,
           "blank_unknown_block")
    expect(errors, result.get("preflight_before_writes") is True
           and result.get("prompt_required") is True, "blank_order_prompt")


def child_records(instance_count: int = 2) -> list[dict[str, object]]:
    lifecycle = (
        ("start", "accepted bounded assignment", "running", "execute bounded work", None),
        ("key_action", "performed verified action", "running", "finish verification", None),
        ("finish", "reported verified result", "completed", "release temporary worker", None),
        ("release", "released temporary worker", "closed", None, "bounded work complete"),
    )
    records = []
    for number in range(1, instance_count + 1):
        instance = f"gongbu#{number:04d}"
        for sequence, (event, behavior, state, next_text, release_reason) in enumerate(lifecycle, 1):
            records.append({
                "time": f"2026-07-14T00:{number:02d}:{sequence:02d}Z",
                "event": event,
                "behavior_summary": behavior,
                "task_id": "CCR-R2-SHIR-20260714-A02",
                "dispatch_uid": f"A02-DISPATCH-{number:03d}",
                "office_instance_id": instance,
                "role": "gongbu",
                "direct_superior": "shangshu",
                "status": state,
                "evidence_pointer": f"evidence://{instance}/{event}",
                "next": next_text,
                "release_reason": release_reason,
                "private_body": "DO_NOT_COPY_PRIVATE_BODY_SENTINEL",
                "prompt_body": "DO_NOT_COPY_PROMPT_SENTINEL",
            })
    return records


def check_child_validator(errors: list[str]) -> None:
    validate = archive_runtime_task.validate_child_trace_summaries
    records = child_records()
    result = validate(deepcopy(records))
    expect(errors, flag(result) is True, "child_valid")
    expect(errors, set(result.get("instance_ids", [])) == {"gongbu#0001", "gongbu#0002"}, "child_instances")

    cross_task = deepcopy(records)
    for record in cross_task:
        if record["office_instance_id"] == "gongbu#0002":
            record["task_id"] = "OTHER-TASK"
    expect(errors, flag(validate(cross_task)) is False, "child_cross_task")
    for field in ("task_id", "dispatch_uid", "role", "direct_superior"):
        drift = deepcopy(records)
        drift[1][field] = "drift"
        expect(errors, flag(validate(drift)) is False, "child_binding_drift_" + field)

    required = "time event behavior_summary task_id dispatch_uid office_instance_id role direct_superior status evidence_pointer".split()
    for field in required:
        invalid = deepcopy(records)
        invalid[0].pop(field)
        expect(errors, flag(validate(invalid)) is False, "child_missing_" + field)
    invalid = deepcopy(records)
    invalid[0]["next"] = invalid[0]["release_reason"] = None
    expect(errors, flag(validate(invalid)) is False, "child_missing_next_or_release")
    for event in ("key_action", "release"):
        invalid = [record for record in deepcopy(records)
                   if not (record["office_instance_id"] == "gongbu#0002" and record["event"] == event)]
        expect(errors, flag(validate(invalid)) is False, "child_missing_event_" + event)
    invalid = deepcopy(records)
    invalid[0]["status"] = {"not": "scalar"}
    expect(errors, flag(validate(invalid)) is False, "child_non_scalar")
    invalid = deepcopy(records)
    invalid[0]["behavior_summary"] = "x" * 1025
    expect(errors, flag(validate(invalid)) is False, "child_field_limit")


def check_child_projection(errors: list[str]) -> None:
    compact = archive_runtime_task.compact_events
    task_id, records = "CCR-R2-SHIR-20260714-A02", child_records()
    rendered = compact(task_id, 100, deepcopy(records))
    required = (
        task_id, "A02-DISPATCH-001", "A02-DISPATCH-002", "gongbu#0001", "gongbu#0002",
        "gongbu", "shangshu", "evidence://gongbu#0001/start", "evidence://gongbu#0002/release",
        "accepted bounded assignment", "released temporary worker", "2026-07-14T00:01:01Z",
    )
    expect(errors, all(value in rendered for value in required), "projection_required_fields")
    expect(errors, "DO_NOT_COPY_" not in rendered, "projection_private_body")

    legacy = {"time": "2026-07-14T00:00:00Z", "action": "legacy-action",
              "from_state": "queued", "to_state": "running", "actor": "taizi"}
    mixed = compact(task_id, 100, [legacy, *deepcopy(records)])
    expect(errors, "legacy-action" in mixed and all(value in mixed for value in required), "projection_mixed")
    limited = compact(task_id, 1, deepcopy(records))
    expect(errors, "gongbu#0001" not in limited and "gongbu#0002" in limited, "projection_limit")
    wrong = compact("OTHER-TASK", 100, deepcopy(records))
    expect(errors, "invalid child trace" in wrong and "accepted bounded assignment" not in wrong, "projection_task_binding")

    sensitive = deepcopy(records)
    sensitive[0]["behavior_summary"] = "Authorization=Bearer " + "SUPER_SECRET_VALUE"
    redacted = compact(task_id, 100, sensitive)
    expect(errors, "SUPER_SECRET_VALUE" not in redacted and "[redacted]" in redacted, "projection_redaction")

    four = child_records(4)
    groups = [four[index * 4:(index + 1) * 4] for index in range(4)]
    interleaved = [record for sequence in range(4) for group in groups for record in [group[sequence]]]
    bounded = compact(task_id, 12, interleaved)
    expect(errors, "invalid child trace" not in bounded
           and "gongbu#0004" in bounded and "gongbu#0001" not in bounded, "projection_complete_instances")

    wide = deepcopy(records)
    for record in wide:
        record["behavior_summary"] = "wide" + "界" * 1000
    wide_result = compact(task_id, 100, wide)
    expect(errors, len(wide_result.encode("utf-8")) <= 4096
           and "gongbu#0001" in wide_result and "gongbu#0002" in wide_result, "projection_utf8_limit")

    generic = [{"time": "t" * 500, "action": "a" * 500, "from_state": "f" * 500,
                "to_state": "t" * 500, "actor": "o" * 500} for _ in range(30)]
    overflow = compact(task_id, 100, [*deepcopy(records), *generic])
    receipt_fields = (task_id, "gongbu#0001", "gongbu#0002", "evidence://gongbu#0001/start")
    expect(errors, overflow.startswith("trace projection blocked: byte limit ")
           and all(value in overflow for value in receipt_fields)
           and len(overflow.encode("utf-8")) <= 4096, "projection_overflow_receipt")
    generic_overflow = compact(task_id, 100, generic)
    expect(errors, task_id in generic_overflow and len(generic_overflow.encode("utf-8")) <= 4096,
           "projection_generic_receipt")


def main() -> int:
    errors: list[str] = []
    check_host_memory(errors)
    check_memory_graph(errors)
    check_blank_host(errors)
    check_child_validator(errors)
    check_child_projection(errors)
    if errors:
        print(f"A02_RED_EXPECTED_FAILURES={len(errors)}", file=sys.stderr)
        for error in errors:
            print("FAIL " + error, file=sys.stderr)
        return 1
    print("A02_HOST_MEMORY_CHILD_TRACE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
