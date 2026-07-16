"""Pure complexity and hierarchical budget decisions for court dispatch."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime
import math
import ntpath


COMPLEXITY_RESULTS = (
    "MINIMAL_PASS",
    "NECESSARY_COMPLEXITY_APPROVED",
    "LOW_VALUE_REJECTED",
    "BUDGET_DEFERRED",
)

DEFAULT_NORMAL_PARALLEL_LIMIT = 16
LATEST_USER_PARALLEL_CONTROL = "latest_user_explicit"
CURRENT_USER_PARALLEL_CONTROL = "current_user_explicit"

_LEVEL_CHILD = {
    "root": "department",
    "department": "ministry",
    "ministry": "worker",
}

_DEPARTMENT_ROLES = frozenset({"zhongshu", "menxia", "shangshu"})
_MINISTRY_ROLES = frozenset({"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"})

_RESOURCE_FIELDS = (
    "sample_id",
    "sampled_at",
    "decision_at",
    "now",
    "max_sample_age_seconds",
    "host_capacity",
    "active_agents",
    "retained_agents",
    "reclamation_verified",
    "ram_percent",
    "free_memory_mb",
    "context_tokens",
    "message_chars",
    "tool_calls",
    "time_seconds",
)

_MANDATORY_HARD_LIMITS = frozenset(
    {
        "ram_percent_max",
        "memory_mb_max",
        "context_tokens_max",
        "message_chars_max",
        "tool_calls_max",
        "time_seconds_max",
        "retained_agents_max",
    }
)

_COUNT_HARD_LIMITS = frozenset(
    {
        "context_tokens_max",
        "message_chars_max",
        "tool_calls_max",
        "retained_agents_max",
    }
)

_DOS_RESERVED_NAMES = frozenset({"con", "prn", "aux", "nul"})

_COMPOSITE_FACTORS = (
    "agent_count",
    "host_capacity",
    "retained_agents",
    "reclamation_verified",
    "ram_percent",
    "free_memory_mb",
    "measured_agent_cost",
    "message_chars",
    "time_seconds",
    "write_set",
    "complexity",
    "marginal_value",
    "lease",
)


def _reject(reason: str) -> None:
    raise ValueError(reason)


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _require_strict_bool(value: object) -> bool:
    if not isinstance(value, bool):
        _reject("strict_bool_required")
    return value


def _aware_timestamp(value: object, reason: str) -> datetime:
    if not _nonempty_text(value):
        _reject(reason)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        _reject(reason)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _reject(reason)
    return parsed


def _hard_limits_valid(value: object) -> bool:
    if (
        not isinstance(value, Mapping)
        or not value
        or not _MANDATORY_HARD_LIMITS.issubset(value)
    ):
        return False
    for name, limit in value.items():
        if not _finite_number(limit) or float(limit) < 0.0:
            return False
        if name in _COUNT_HARD_LIMITS and not _valid_count(limit):
            return False
    ram_max = value.get("ram_percent_max")
    return not (_finite_number(ram_max) and float(ram_max) > 100.0)


def _validated_hard_limits(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or not value:
        _reject("hard_limits_required")
    if not _MANDATORY_HARD_LIMITS.issubset(value):
        _reject("hard_limits_missing_mandatory_cap")
    for name, limit in value.items():
        if isinstance(limit, (int, float)) and not isinstance(limit, bool) and not math.isfinite(float(limit)):
            _reject("non_finite_number")
        if not _finite_number(limit):
            _reject("hard_limits_required")
        if float(limit) < 0.0:
            _reject("hard_limit_negative")
        if name in _COUNT_HARD_LIMITS and not _valid_count(limit):
            _reject("hard_limit_count_not_integer")
    ram_max = value.get("ram_percent_max")
    if _finite_number(ram_max) and float(ram_max) > 100.0:
        _reject("hard_limit_ram_percent_invalid")
    return deepcopy(dict(value))


def _normalized_path(value: str) -> str:
    raw = value.strip().replace("/", "\\")
    if not raw:
        return ""
    if raw.casefold().startswith("\\\\?\\unc\\"):
        raw = "\\\\" + raw[8:]
    elif raw.casefold().startswith("\\\\?\\"):
        raw = raw[4:]
    components = []
    for component in raw.split("\\"):
        if component in {"", ".", ".."}:
            components.append(component)
        else:
            components.append(component.rstrip(" ."))
    normalized = ntpath.normcase(ntpath.normpath("\\".join(components)))
    return normalized.rstrip("\\")


def _validated_write_path(value: object) -> str:
    if not isinstance(value, str):
        _reject("write_set_path_must_be_string")
    raw = value.strip().replace("/", "\\")
    if not raw:
        _reject("write_set_required")
    folded = raw.casefold()
    if (
        folded.startswith("\\\\.\\")
        or folded.startswith("\\??\\")
        or folded.startswith("\\\\??\\")
        or folded.startswith("\\device\\")
        or folded.startswith("\\global??\\")
        or folded.startswith("\\dosdevices\\")
        or folded.startswith("\\\\?\\globalroot")
        or folded.startswith("\\\\?\\volume{")
    ):
        _reject("write_set_device_alias_forbidden")
    if raw.casefold().startswith("\\\\?\\unc\\"):
        raw = "\\\\" + raw[8:]
    elif raw.casefold().startswith("\\\\?\\"):
        raw = raw[4:]
    drive, tail = ntpath.splitdrive(raw)
    if ":" in tail:
        _reject("write_set_ads_forbidden")
    for component in tail.split("\\"):
        name = component.rstrip(" .").split(".", 1)[0].casefold()
        if (
            name in _DOS_RESERVED_NAMES
            or (len(name) == 4 and name[:3] in {"com", "lpt"} and name[3] in "123456789")
        ):
            _reject("write_set_dos_reserved_name")
    if raw in {".", ".\\"} or (drive and not drive.startswith("\\\\") and tail in {"", ".", ".\\"}):
        _reject("write_set_current_directory_forbidden")
    normalized = _normalized_path(raw)
    if normalized in {"", "."}:
        _reject("write_set_current_directory_forbidden")
    return normalized


def _validated_write_set(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        _reject("write_set_required")
    return tuple(_validated_write_path(path) for path in value)


def _validated_read_scope(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        _reject("read_scope_required")
    normalized: list[str] = []
    for path in value:
        if not isinstance(path, str) or not path.strip():
            _reject("read_scope_path_must_be_string")
        candidate = _validated_write_path(path)
        drive, _ = ntpath.splitdrive(candidate)
        if drive or ntpath.isabs(candidate) or candidate == ".." or candidate.startswith("..\\"):
            _reject("read_scope_out_of_bounds")
        normalized.append(candidate)
    return tuple(normalized)


def _validated_access_contract(
    *,
    access_mode: object,
    read_scope: object,
    write_set: object,
    mutation_allowed: object,
    integration_authority: bool,
) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    mutation = _require_strict_bool(mutation_allowed)
    if access_mode == "read_only":
        if not isinstance(write_set, Sequence) or isinstance(write_set, (str, bytes)):
            _reject("write_set_must_be_sequence")
        if write_set:
            _reject("read_only_write_set_forbidden")
        if mutation or integration_authority:
            _reject("read_only_authority_forbidden")
        return (), _validated_read_scope(read_scope), mutation
    if access_mode != "read_write":
        _reject("invalid_access_mode")
    if not mutation:
        _reject("writer_mutation_authority_required")
    normalized_writes = _validated_write_set(write_set)
    normalized_reads = normalized_writes if not read_scope else _validated_write_set(read_scope)
    return normalized_writes, normalized_reads, mutation


def _paths_overlap(left: str, right: str) -> bool:
    a = _normalized_path(left)
    b = _normalized_path(right)
    return a == b or a.startswith(f"{b}\\") or b.startswith(f"{a}\\")


def _authority_chain_allows(
    parent: Mapping[str, object],
    *,
    child_level: str,
    child_role: str,
) -> bool:
    parent_level = parent.get("level")
    parent_role = parent.get("role_key")
    if parent_level == "root":
        return parent_role == "taizi" and child_level == "department" and child_role in _DEPARTMENT_ROLES
    if parent_level == "department":
        return parent_role == "shangshu" and child_level == "ministry" and child_role in _MINISTRY_ROLES
    if parent_level == "ministry":
        return parent_role in _MINISTRY_ROLES and child_level == "worker" and child_role == parent_role
    return False


def _has_active_descendant(pool: Mapping[str, object], ancestor_id: str) -> bool:
    values = pool.get("leases")
    if not isinstance(values, Mapping):
        _reject("invalid_budget_pool")
    for value in values.values():
        if not isinstance(value, Mapping) or value.get("status") != "ACTIVE":
            continue
        parent_id = value.get("parent_id")
        visited: set[str] = set()
        while isinstance(parent_id, str) and parent_id not in visited:
            if parent_id == ancestor_id:
                return True
            visited.add(parent_id)
            parent = values.get(parent_id)
            parent_id = parent.get("parent_id") if isinstance(parent, Mapping) else None
    return False


def _active_leases(pool: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
    values = pool.get("leases")
    if not isinstance(values, Mapping):
        _reject("invalid_budget_pool")
    for value in values.values():
        if not isinstance(value, Mapping):
            _reject("invalid_budget_pool")
        if value.get("status") == "ACTIVE":
            yield value


def _lease_by_child(pool: Mapping[str, object], child_id: str) -> Mapping[str, object] | None:
    values = pool.get("leases")
    if not isinstance(values, Mapping):
        _reject("invalid_budget_pool")
    value = values.get(child_id)
    return value if isinstance(value, Mapping) else None


def _lease_by_id(pool: Mapping[str, object], lease_id: str) -> tuple[str, Mapping[str, object]]:
    values = pool.get("leases")
    if not isinstance(values, Mapping):
        _reject("invalid_budget_pool")
    for child_id, value in values.items():
        if isinstance(child_id, str) and isinstance(value, Mapping) and value.get("lease_id") == lease_id:
            return child_id, value
    _reject("unknown_lease")


def _integration_binding_snapshot(
    pool: Mapping[str, object],
    child_id: str,
    value: Mapping[str, object],
) -> dict[str, object]:
    return {
        "child_id": child_id,
        "lease_id": value.get("lease_id"),
        "role_key": value.get("role_key"),
        "instance_key": value.get("instance_key"),
        "shard_id": value.get("shard_id"),
        "write_set": deepcopy(value.get("write_set")),
        "approved_by": value.get("approved_by"),
        "release_generation": value.get("release_generation"),
        "release_history": deepcopy(value.get("release_history")),
        "generation": int(pool.get("reassessment_generation", 0)),
    }


def _refresh_integration_binding(pool: dict[str, object]) -> None:
    binding = pool.get("integration_authority_binding")
    leases = pool.get("leases")
    if not isinstance(binding, Mapping) or not isinstance(leases, Mapping):
        return
    child_id = binding.get("child_id")
    value = leases.get(child_id)
    if isinstance(child_id, str) and isinstance(value, Mapping):
        pool["integration_authority_binding"] = _integration_binding_snapshot(pool, child_id, value)


def _append_resource_sample(pool: dict[str, object], sample: Mapping[str, object]) -> None:
    history = pool.get("resource_sample_history")
    if not isinstance(history, tuple):
        _reject("budget_pool_invariant_violation")
    stored = deepcopy(dict(sample))
    pool["resource_sample_history"] = history + (stored,)
    pool["last_resource_sample"] = stored


def _validate_budget_pool(pool: Mapping[str, object]) -> None:
    if not isinstance(pool, Mapping):
        _reject("budget_pool_invariant_violation")
    leases = pool.get("leases")
    root_id = pool.get("root_id")
    total = pool.get("normalized_total_share")
    hard_limits = pool.get("hard_limits")
    generation = pool.get("reassessment_generation")
    super_giant_task_gate = pool.get("super_giant_task_gate")
    release_ledger = pool.get("lease_release_history")
    if (
        pool.get("schema") != "court.budget.pool.v1"
        or not _nonempty_text(pool.get("budget_id"))
        or not isinstance(leases, Mapping)
        or not _nonempty_text(root_id)
        or root_id not in leases
        or not _finite_number(total)
        or not math.isclose(float(total), 100.0, abs_tol=1e-9)
        or not _hard_limits_valid(hard_limits)
        or not _valid_count(generation)
        or not isinstance(super_giant_task_gate, bool)
        or not isinstance(release_ledger, tuple)
    ):
        _reject("budget_pool_invariant_violation")
    trigger = pool.get("last_reassessment_trigger")
    if trigger not in {None, "NEW_WAVE", "RESOURCE_CHANGE", "LEASE_RELEASE"}:
        _reject("budget_pool_invariant_violation")
    if (generation == 0 and trigger is not None) or (generation > 0 and trigger is None):
        _reject("budget_pool_invariant_violation")
    last_sample = pool.get("last_resource_sample")
    sample_history = pool.get("resource_sample_history")
    if not isinstance(sample_history, tuple):
        _reject("budget_pool_invariant_violation")
    if (last_sample is None) != (not sample_history):
        _reject("budget_pool_invariant_violation")
    sample_ids: set[str] = set()
    previous_sampled: datetime | None = None
    previous_decision: datetime | None = None
    previous_now: datetime | None = None
    for sample_entry in sample_history:
        if not isinstance(sample_entry, Mapping):
            _reject("budget_pool_invariant_violation")
        try:
            validated_sample = _validated_resource_sample(sample_entry)
        except (TypeError, ValueError):
            _reject("budget_pool_invariant_violation")
        sample_id = validated_sample.get("sample_id")
        sampled_at = _resource_timestamp(validated_sample.get("sampled_at"))
        decision_at = _resource_timestamp(validated_sample.get("decision_at"))
        now = _resource_timestamp(validated_sample.get("now"))
        if (
            not _nonempty_text(sample_id)
            or str(sample_id) in sample_ids
            or (previous_sampled is not None and sampled_at <= previous_sampled)
            or (previous_decision is not None and decision_at <= previous_decision)
            or (previous_now is not None and now <= previous_now)
        ):
            _reject("budget_pool_invariant_violation")
        sample_ids.add(str(sample_id))
        previous_sampled = sampled_at
        previous_decision = decision_at
        previous_now = now
    if sample_history and last_sample != sample_history[-1]:
        _reject("budget_pool_invariant_violation")

    lease_ids: set[str] = set()
    integration_owners: list[tuple[str, Mapping[str, object]]] = []
    release_generations: set[int] = set()
    release_timeline: list[tuple[int, datetime]] = []
    expected_release_ledger: list[dict[str, object]] = []
    active_instances: set[str] = set()
    active_shards: set[tuple[str, str]] = set()
    active_writes: list[str] = []
    numeric_fields = (
        "normalized_share",
        "envelope_share",
        "allocated_share",
        "reserve_share",
        "available_share",
    )
    for child_id, value in leases.items():
        if not _nonempty_text(child_id) or not isinstance(value, Mapping):
            _reject("budget_pool_invariant_violation")
        required_text = (
            "lease_id",
            "task_id",
            "phase_id",
            "wave_id",
            "role_key",
            "instance_key",
            "level",
            "expected_output",
            "approved_by",
            "approved_at",
            "start_condition",
            "expiry_condition",
            "preload_ack",
            "shard_id",
            "integration_domain",
            "owner_id",
        )
        if (
            value.get("schema") != "court.budget.lease.v1"
            or any(not _nonempty_text(value.get(field)) for field in required_text)
            or value.get("preload_ack") != "PASSED"
        ):
            _reject("budget_pool_invariant_violation")
        try:
            approved_timestamp = _aware_timestamp(value.get("approved_at"), "approval_timestamp_invalid")
        except ValueError:
            _reject("budget_pool_invariant_violation")
        numbers = {field: value.get(field) for field in numeric_fields}
        if any(not _finite_number(number) for number in numbers.values()):
            _reject("budget_pool_invariant_violation")
        envelope = float(numbers["envelope_share"])
        allocated = float(numbers["allocated_share"])
        reserve = float(numbers["reserve_share"])
        available = float(numbers["available_share"])
        if any(number < 0.0 for number in (envelope, allocated, reserve, available)):
            _reject("budget_pool_invariant_violation")
        if not math.isclose(float(numbers["normalized_share"]), envelope, abs_tol=1e-9):
            _reject("budget_pool_invariant_violation")
        if allocated + reserve > envelope + 1e-9:
            _reject("budget_pool_invariant_violation")
        if not math.isclose(available, envelope - allocated - reserve, abs_tol=1e-9):
            _reject("budget_pool_invariant_violation")

        lease_id = value.get("lease_id")
        if not _nonempty_text(lease_id) or lease_id in lease_ids:
            _reject("budget_pool_invariant_violation")
        lease_ids.add(str(lease_id))
        if value.get("budget_id") != pool.get("budget_id"):
            _reject("budget_pool_invariant_violation")
        lease_caps = value.get("hard_caps")
        if not isinstance(lease_caps, Mapping) or dict(lease_caps) != dict(hard_limits):
            _reject("budget_pool_invariant_violation")
        measured = value.get("measured_cost")
        if not isinstance(measured, Mapping):
            _reject("budget_pool_invariant_violation")
        measured_values = tuple(
            measured.get(field)
            for field in ("memory_mb", "context_tokens", "message_chars", "tool_calls", "time_seconds")
        )
        if (
            any(not _finite_number(number) for number in measured_values)
            or float(measured_values[0]) <= 0.0
            or any(float(number) < 0.0 for number in measured_values[1:])
        ):
            _reject("budget_pool_invariant_violation")
        try:
            normalized_writes, normalized_reads, mutation_allowed = _validated_access_contract(
                access_mode=value.get("access_mode"),
                read_scope=value.get("read_scope"),
                write_set=value.get("write_set"),
                mutation_allowed=value.get("mutation_allowed"),
                integration_authority=value.get("integration_authority") is True,
            )
        except ValueError:
            _reject("budget_pool_invariant_violation")
        if (
            value.get("write_set") != normalized_writes
            or value.get("read_scope") != normalized_reads
            or value.get("mutation_allowed") is not mutation_allowed
        ):
            _reject("budget_pool_invariant_violation")
        return_conditions = value.get("return_conditions")
        if (
            not isinstance(return_conditions, tuple)
            or not return_conditions
            or any(not _nonempty_text(item) for item in return_conditions)
        ):
            _reject("budget_pool_invariant_violation")
        if not isinstance(value.get("integration_authority"), bool):
            _reject("budget_pool_invariant_violation")

        launch_state = value.get("launch_state")
        launch_sample_id = value.get("launch_sample_id")
        launch_usage = value.get("launch_usage")
        launch_history = value.get("launch_history")
        if not isinstance(launch_history, tuple):
            _reject("budget_pool_invariant_violation")
        if value.get("level") == "root":
            if (
                launch_state != "NOT_APPLICABLE"
                or launch_sample_id is not None
                or launch_usage is not None
                or launch_history
            ):
                _reject("budget_pool_invariant_violation")
        elif launch_state == "READY":
            if launch_sample_id is not None or launch_usage is not None or launch_history:
                _reject("budget_pool_invariant_violation")
        elif launch_state == "CONSUMED":
            if (
                not _nonempty_text(launch_sample_id)
                or not isinstance(launch_usage, Mapping)
                or len(launch_history) != 1
                or not isinstance(launch_history[0], Mapping)
            ):
                _reject("budget_pool_invariant_violation")
            launch_record = launch_history[0]
            launch_generation = launch_record.get("generation")
            if (
                launch_record.get("sample_id") != launch_sample_id
                or launch_record.get("usage") != launch_usage
                or not _valid_count(launch_generation)
                or int(launch_generation) > int(generation)
            ):
                _reject("budget_pool_invariant_violation")
        else:
            _reject("budget_pool_invariant_violation")

        status = value.get("status")
        history = value.get("release_history")
        if status not in {"ACTIVE", "RELEASED"} or not isinstance(history, tuple):
            _reject("budget_pool_invariant_violation")
        terminal_fields = (
            value.get("release_reason"),
            value.get("release_evidence"),
            value.get("release_authority"),
            value.get("released_by"),
            value.get("released_at"),
        )
        if status == "ACTIVE":
            if (
                any(field is not None for field in terminal_fields)
                or value.get("release_generation") is not None
                or history
            ):
                _reject("budget_pool_invariant_violation")
        else:
            if (
                any(not _nonempty_text(field) for field in terminal_fields)
                or value.get("release_authority") != value.get("released_by")
                or value.get("released_by") not in {"taizi", value.get("direct_superior")}
                or len(history) != 1
                or not isinstance(history[0], Mapping)
            ):
                _reject("budget_pool_invariant_violation")
            release_record = history[0]
            release_generation = release_record.get("generation")
            if (
                release_record.get("reason") != value.get("release_reason")
                or release_record.get("evidence") != value.get("release_evidence")
                or release_record.get("released_by") != value.get("released_by")
                or release_record.get("released_at") != value.get("released_at")
                or not _valid_count(release_generation)
                or int(release_generation) <= 0
                or int(release_generation) > int(generation)
                or value.get("release_generation") != release_generation
                or int(release_generation) in release_generations
            ):
                _reject("budget_pool_invariant_violation")
            release_generations.add(int(release_generation))
            expected_release_ledger.append(
                {
                    "child_id": str(child_id),
                    "lease_id": value.get("lease_id"),
                    "generation": int(release_generation),
                    "reason": value.get("release_reason"),
                    "evidence": value.get("release_evidence"),
                    "released_by": value.get("released_by"),
                    "released_at": value.get("released_at"),
                }
            )
            try:
                released_timestamp = _aware_timestamp(
                    value.get("released_at"),
                    "release_timestamp_invalid",
                )
            except ValueError:
                _reject("budget_pool_invariant_violation")
            if released_timestamp < approved_timestamp:
                _reject("budget_pool_invariant_violation")
            release_timeline.append((int(release_generation), released_timestamp))
        if status == "ACTIVE":
            instance_key = str(value.get("instance_key"))
            shard_key = (str(value.get("role_key")), str(value.get("shard_id")))
            if instance_key in active_instances or shard_key in active_shards:
                _reject("budget_pool_invariant_violation")
            if any(
                _paths_overlap(path, existing)
                for path in normalized_writes
                for existing in active_writes
            ):
                _reject("budget_pool_invariant_violation")
            active_instances.add(instance_key)
            active_shards.add(shard_key)
            active_writes.extend(normalized_writes)
        if value.get("integration_authority") is True:
            integration_owners.append((str(child_id), value))
        if value.get("level") != "root" and value.get("integration_domain") != value.get("role_key"):
            _reject("budget_pool_invariant_violation")

    ordered_releases = sorted(release_timeline, key=lambda item: item[0])
    if any(
        later_timestamp < earlier_timestamp
        for (_, earlier_timestamp), (_, later_timestamp) in zip(
            ordered_releases,
            ordered_releases[1:],
        )
    ):
        _reject("budget_pool_invariant_violation")
    if trigger == "LEASE_RELEASE" and int(generation) not in release_generations:
        _reject("budget_pool_invariant_violation")
    expected_release_ledger.sort(key=lambda entry: int(entry["generation"]))
    if tuple(expected_release_ledger) != release_ledger:
        _reject("budget_pool_invariant_violation")

    binding = pool.get("integration_authority_binding")
    shangshu_leases = [
        (str(child_id), value)
        for child_id, value in leases.items()
        if isinstance(value, Mapping)
        and value.get("role_key") == "shangshu"
        and value.get("level") == "department"
    ]
    if (
        len(shangshu_leases) > 1
        and super_giant_task_gate is not True
    ):
        _reject("budget_pool_invariant_violation")
    if shangshu_leases and sum(child_id == "shangshu" for child_id, _ in shangshu_leases) != 1:
        _reject("budget_pool_invariant_violation")
    if binding is None:
        if integration_owners or shangshu_leases:
            _reject("budget_pool_invariant_violation")
    elif (
        not isinstance(binding, Mapping)
        or len(integration_owners) != 1
        or integration_owners[0][0] != "shangshu"
        or integration_owners[0][1].get("role_key") != "shangshu"
        or integration_owners[0][1].get("instance_key") != "shangshu"
        or integration_owners[0][1].get("level") != "department"
        or integration_owners[0][1].get("parent_id") != "taizi"
        or integration_owners[0][1].get("direct_superior") != "taizi"
        or dict(binding)
        != _integration_binding_snapshot(pool, integration_owners[0][0], integration_owners[0][1])
    ):
        _reject("budget_pool_invariant_violation")
    root = leases[root_id]
    if (
        not isinstance(root, Mapping)
        or root.get("level") != "root"
        or root.get("role_key") != "taizi"
        or root.get("instance_key") != "taizi"
        or root.get("parent_id") is not None
        or root.get("parent_budget_id") is not None
        or root.get("direct_superior") is not None
        or root.get("approved_by") != "taizi"
        or root.get("integration_domain") != "court"
        or not math.isclose(float(root.get("envelope_share", -1.0)), float(total), abs_tol=1e-9)
    ):
        _reject("budget_pool_invariant_violation")

    for child_id, value in leases.items():
        if not isinstance(value, Mapping):
            _reject("budget_pool_invariant_violation")
        parent_id = value.get("parent_id")
        if child_id != root_id:
            parent = leases.get(parent_id)
            if (
                not _nonempty_text(parent_id)
                or not isinstance(parent, Mapping)
                or value.get("parent_budget_id") != parent.get("lease_id")
                or value.get("direct_superior") != parent_id
                or value.get("approved_by") != parent_id
                or _LEVEL_CHILD.get(str(parent.get("level"))) != value.get("level")
                or not _authority_chain_allows(
                    parent,
                    child_level=str(value.get("level")),
                    child_role=str(value.get("role_key")),
                )
                or value.get("task_id") != parent.get("task_id")
                or value.get("phase_id") != parent.get("phase_id")
                or value.get("wave_id") != parent.get("wave_id")
                or value.get("hard_caps") != parent.get("hard_caps")
                or (value.get("status") == "ACTIVE" and parent.get("status") != "ACTIVE")
            ):
                _reject("budget_pool_invariant_violation")
            try:
                child_approved = _aware_timestamp(value.get("approved_at"), "approval_timestamp_invalid")
                parent_approved = _aware_timestamp(parent.get("approved_at"), "approval_timestamp_invalid")
            except ValueError:
                _reject("budget_pool_invariant_violation")
            if child_approved < parent_approved:
                _reject("budget_pool_invariant_violation")
            if value.get("status") == "RELEASED" and parent.get("status") == "RELEASED":
                child_generation = value.get("release_generation")
                parent_generation = parent.get("release_generation")
                if (
                    not _valid_count(child_generation)
                    or not _valid_count(parent_generation)
                    or int(child_generation) >= int(parent_generation)
                ):
                    _reject("budget_pool_invariant_violation")
        expected_allocated = sum(
            float(child.get("envelope_share", 0.0))
            for child in leases.values()
            if isinstance(child, Mapping)
            and child.get("parent_id") == child_id
            and child.get("status") == "ACTIVE"
        )
        if not math.isclose(
            float(value.get("allocated_share", -1.0)),
            expected_allocated,
            abs_tol=1e-9,
        ):
            _reject("budget_pool_invariant_violation")


def evaluate_complexity_budget(
    *,
    user_instruction: str | None,
    necessary_complexity: bool,
    simpler_equivalent_available: bool,
    low_marginal_value: bool,
    budget_sufficient: bool,
    risk_acceptable: bool,
    rollback_ready: bool,
) -> dict[str, object]:
    """Apply explicit user priority, otherwise the four-factor Taizi decision."""

    if user_instruction not in (None, "MINIMAL", "ALLOW_NECESSARY", "DEFER_FOR_BUDGET"):
        _reject("unknown_user_complexity_instruction")
    necessary_complexity = _require_strict_bool(necessary_complexity)
    simpler_equivalent_available = _require_strict_bool(simpler_equivalent_available)
    low_marginal_value = _require_strict_bool(low_marginal_value)
    budget_sufficient = _require_strict_bool(budget_sufficient)
    risk_acceptable = _require_strict_bool(risk_acceptable)
    rollback_ready = _require_strict_bool(rollback_ready)

    source = "USER_EXPLICIT" if user_instruction is not None else "TAIZI_BUDGET"
    considered = ("necessity", "budget", "risk", "rollback")

    if not budget_sufficient or not risk_acceptable or not rollback_ready:
        result = "BUDGET_DEFERRED"
    elif user_instruction in ("MINIMAL", "DEFER_FOR_BUDGET"):
        result = "BUDGET_DEFERRED" if necessary_complexity else "MINIMAL_PASS"
    elif low_marginal_value:
        result = "LOW_VALUE_REJECTED"
    elif necessary_complexity and not simpler_equivalent_available:
        result = "NECESSARY_COMPLEXITY_APPROVED"
    else:
        result = "MINIMAL_PASS"

    return {
        "schema": "court.complexity.decision.v1",
        "result": result,
        "decision_source": source,
        "considered_factors": considered,
        "hard_gates_preserved": True,
    }


def is_super_giant_task(
    *,
    task_kind: str,
    batch_item_count: int | None = None,
    information_unit_count: int | None = None,
) -> bool:
    for count in (batch_item_count, information_unit_count):
        if count is not None and not _valid_count(count):
            _reject("invalid_task_count")
    if task_kind in {
        "small_game_design",
        "small_game_development",
        "medium_game_design",
        "medium_game_development",
        "large_game_design",
        "large_game_development",
    }:
        return True
    if task_kind == "batch_processing":
        return batch_item_count is not None and batch_item_count > 10
    if task_kind == "complex_information_judgment":
        return information_unit_count is not None and information_unit_count > 30
    return False


def should_degrade_complexity(
    *,
    remaining_super_giant: bool,
    system_memory_percent: float,
) -> bool:
    remaining_super_giant = _require_strict_bool(remaining_super_giant)
    if (
        not _finite_number(system_memory_percent)
        or float(system_memory_percent) < 0.0
        or float(system_memory_percent) > 100.0
    ):
        _reject("invalid_system_memory_percent")
    return not remaining_super_giant or system_memory_percent >= 99.0


def resolve_parallel_limit(
    *,
    configured_limit: int,
    explicit_count: int | None,
    unlock: bool,
    control_source: str | None,
    system_memory_percent: float,
) -> dict[str, object]:
    """Resolve a wave ceiling without replacing capacity or lease gates."""

    if not _valid_count(configured_limit) or configured_limit < 1:
        _reject("parallel_configured_limit_invalid")
    if explicit_count is not None and (
        not _valid_count(explicit_count) or explicit_count < 1
    ):
        _reject("parallel_explicit_count_invalid")
    unlock = _require_strict_bool(unlock)
    if (
        not _finite_number(system_memory_percent)
        or float(system_memory_percent) < 0.0
        or float(system_memory_percent) > 100.0
    ):
        _reject("invalid_system_memory_percent")

    override_requested = unlock or (
        explicit_count is not None
        and explicit_count > DEFAULT_NORMAL_PARALLEL_LIMIT
    )
    if override_requested and control_source not in {
        LATEST_USER_PARALLEL_CONTROL,
        CURRENT_USER_PARALLEL_CONTROL,
    }:
        _reject("parallel_override_not_current_user_explicit")

    if explicit_count is not None:
        effective_limit = min(configured_limit, explicit_count)
        authorization = "EXPLICIT_COUNT"
    elif unlock:
        effective_limit = configured_limit
        authorization = "EXPLICIT_UNLOCK"
    else:
        effective_limit = min(configured_limit, DEFAULT_NORMAL_PARALLEL_LIMIT)
        authorization = "DEFAULT_NORMAL_16"

    degraded = float(system_memory_percent) >= 99.0
    if degraded:
        effective_limit = min(effective_limit, DEFAULT_NORMAL_PARALLEL_LIMIT)

    return {
        "configured_limit": configured_limit,
        "effective_limit": effective_limit,
        "explicit_count": explicit_count,
        "unlock": unlock,
        "control_source": control_source,
        "authorization": authorization,
        "degraded": degraded,
        "degrade_reason": "system_memory_pressure" if degraded else None,
        "budget_lease_required": True,
        "auto_fill_to_limit": False,
    }


def evaluate_context_economy(
    *,
    pool: Mapping[str, object],
    semantic_receipt_hash: str,
    invariant_capsule_hash: str,
    capsule_bytes: int,
    fork_context: str,
    result_mode: str,
    tool_output_mode: str,
    override_source: str | None,
    system_memory_percent: float,
) -> dict[str, object]:
    """Apply Taizi's bounded context discretion without creating budget state."""

    _validate_budget_pool(pool)
    for value, reason in (
        (semantic_receipt_hash, "semantic_receipt_hash_required"),
        (invariant_capsule_hash, "invariant_capsule_hash_required"),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
            _reject(reason)
    if not _valid_count(capsule_bytes):
        _reject("context_capsule_size_invalid")
    if not _finite_number(system_memory_percent) or not 0.0 <= float(system_memory_percent) <= 100.0:
        _reject("invalid_system_memory_percent")

    override = override_source in {"latest_user_explicit", "current_user_explicit", "taizi_explicit_budget"}
    if override_source is not None and not override:
        _reject("context_economy_override_not_explicit")
    if float(system_memory_percent) >= 99.0:
        decision = "DEGRADED"
        reason = "system_memory_pressure"
    else:
        if not override and capsule_bytes > 2048:
            _reject("context_capsule_budget_exceeded")
        if not override and fork_context not in {"none", "minimal"}:
            _reject("implicit_full_context_forbidden")
        if not override and result_mode != "bounded_structured_receipt":
            _reject("bounded_structured_receipt_required")
        if not override and tool_output_mode not in {"aggregate", "pointer"}:
            _reject("aggregate_or_pointer_tool_output_required")
        decision = "APPROVED_OVERRIDE" if override else "APPROVED"
        reason = None

    return {
        "schema": "court.context.economy.receipt.v1",
        "decision": decision,
        "reason": reason,
        "budget_id": pool["budget_id"],
        "semantic_receipt_hash": semantic_receipt_hash.lower(),
        "invariant_capsule_hash": invariant_capsule_hash.lower(),
        "capsule_bytes": capsule_bytes,
        "fork_context": fork_context,
        "result_mode": result_mode,
        "tool_output_mode": tool_output_mode,
        "override_source": override_source,
    }


def normalize_budget_pool(
    *,
    total_share: float,
    root_id: str,
    reserve_share: float,
    hard_limits: Mapping[str, object],
    task_id: str,
    phase: str,
    wave_id: str,
    approved_by: str,
    approved_at: str,
    expected_output: str,
    return_conditions: Sequence[str],
    super_giant_task_gate: bool = False,
) -> dict[str, object]:
    """Create the normalized Taizi root envelope."""

    if not _finite_number(total_share) or not _finite_number(reserve_share):
        _reject("non_finite_number")
    if float(total_share) != 100.0:
        _reject("budget_pool_must_normalize_to_100")
    if not _nonempty_text(root_id) or root_id != "taizi":
        _reject("taizi_root_required")
    if reserve_share < 0 or reserve_share >= total_share:
        _reject("invalid_reserve_share")
    validated_limits = _validated_hard_limits(hard_limits)
    super_giant_task_gate = _require_strict_bool(super_giant_task_gate)
    if approved_by != "taizi":
        _reject("approver_mismatch")
    _aware_timestamp(approved_at, "approval_timestamp_invalid")
    if (
        any(not _nonempty_text(value) for value in (task_id, phase, wave_id, expected_output))
        or not isinstance(return_conditions, Sequence)
        or isinstance(return_conditions, (str, bytes))
        or not return_conditions
        or any(not _nonempty_text(value) for value in return_conditions)
    ):
        _reject("budget_scope_required")

    budget_id = f"budget:{task_id}:{phase}:{wave_id}"
    lease_id = f"{budget_id}:{root_id}"
    root = {
        "schema": "court.budget.lease.v1",
        "budget_id": budget_id,
        "lease_id": lease_id,
        "parent_budget_id": None,
        "parent_id": None,
        "task_id": task_id,
        "phase_id": phase,
        "wave_id": wave_id,
        "role_key": "taizi",
        "instance_key": root_id,
        "level": "root",
        "direct_superior": None,
        "normalized_share": float(total_share),
        "envelope_share": float(total_share),
        "allocated_share": 0.0,
        "reserve_share": float(reserve_share),
        "available_share": float(total_share - reserve_share),
        "hard_caps": deepcopy(validated_limits),
        "measured_cost": {
            "memory_mb": 1,
            "context_tokens": 1,
            "message_chars": 0,
            "tool_calls": 1,
            "time_seconds": 0.0,
        },
        "write_set": _validated_write_set(("court/budget",)),
        "access_mode": "read_write",
        "read_scope": _validated_read_scope(("court/budget",)),
        "mutation_allowed": True,
        "expected_output": expected_output,
        "complexity_score": 0.0,
        "marginal_value_score": 10.0,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "start_condition": "decree_approved",
        "expiry_condition": "decree_closed_or_cancelled",
        "return_conditions": tuple(return_conditions),
        "preload_ack": "PASSED",
        "shard_id": root_id,
        "integration_domain": "court",
        "integration_authority": False,
        "owner_id": root_id,
        "launch_state": "NOT_APPLICABLE",
        "launch_sample_id": None,
        "launch_usage": None,
        "launch_history": (),
        "status": "ACTIVE",
        "release_reason": None,
        "release_evidence": None,
        "release_authority": None,
        "released_by": None,
        "released_at": None,
        "release_generation": None,
        "release_history": (),
    }
    pool = {
        "schema": "court.budget.pool.v1",
        "budget_id": budget_id,
        "normalized_total_share": float(total_share),
        "root_id": root_id,
        "hard_limits": deepcopy(validated_limits),
        "leases": {root_id: root},
        "reassessment_generation": 0,
        "last_reassessment_trigger": None,
        "last_resource_sample": None,
        "resource_sample_history": (),
        "integration_authority_binding": None,
        "super_giant_task_gate": super_giant_task_gate,
        "lease_release_history": (),
    }
    _validate_budget_pool(pool)
    return pool


def allocate_budget_lease(
    pool: Mapping[str, object],
    *,
    parent_id: str,
    allocator_id: str,
    child_id: str,
    child_level: str,
    share: float,
    reserve_share: float,
    owning_worker_id: str | None,
    task_id: str,
    phase: str,
    wave_id: str,
    role_key: str,
    instance_key: str,
    direct_superior: str,
    shard_id: str,
    write_set: Sequence[str],
    expected_output: str,
    approved_by: str,
    approved_at: str,
    start_condition: str,
    expiry_condition: str,
    return_conditions: Sequence[str],
    preload_ack: str,
    hard_caps: Mapping[str, object],
    measured_cost: Mapping[str, object],
    complexity_score: float,
    marginal_value_score: float,
    integration_domain: str,
    integration_authority: bool,
    access_mode: str = "read_write",
    read_scope: Sequence[str] = (),
    mutation_allowed: bool = True,
) -> dict[str, object]:
    """Allocate a direct-child lease without mutating the input pool."""

    _validate_budget_pool(pool)
    integration_authority = _require_strict_bool(integration_authority)
    mutation_allowed = _require_strict_bool(mutation_allowed)
    if access_mode == "read_only" and (mutation_allowed or integration_authority):
        _reject("read_only_authority_forbidden")
    parent = _lease_by_child(pool, parent_id)
    if parent is None or parent.get("status") != "ACTIVE":
        _reject("missing_parent_lease")
    if allocator_id != parent_id:
        _reject("self_mint_forbidden")
    if _LEVEL_CHILD.get(str(parent.get("level"))) != child_level:
        _reject("cross_level_allocation")
    if role_key == "taizi" or instance_key == "taizi" or instance_key.startswith("taizi#"):
        _reject("taizi_singleton")
    existing_shangshu = any(
        current.get("role_key") == "shangshu" and current.get("level") == "department"
        for current in _active_leases(pool)
    )
    is_shangshu_deputy = (
        parent.get("level") == "root"
        and role_key == "shangshu"
        and existing_shangshu
    )
    if is_shangshu_deputy and pool.get("super_giant_task_gate") is not True:
        _reject("shangshu_deputy_requires_super_giant")
    if is_shangshu_deputy and integration_authority:
        _reject("shangshu_deputy_not_global_integrator")
    if integration_authority and pool.get("integration_authority_binding") is not None:
        _reject("duplicate_integration_authority")
    if not _authority_chain_allows(parent, child_level=child_level, child_role=role_key):
        _reject("authority_chain_violation")
    if direct_superior != parent_id:
        _reject("direct_superior_mismatch")
    if task_id != parent.get("task_id"):
        _reject("task_scope_mismatch")
    if phase != parent.get("phase_id"):
        _reject("phase_scope_mismatch")
    if wave_id != parent.get("wave_id"):
        _reject("wave_scope_mismatch")
    if not isinstance(hard_caps, Mapping) or not hard_caps:
        _reject("hard_caps_required")
    validated_caps = _validated_hard_limits(hard_caps)
    if validated_caps != parent.get("hard_caps"):
        _reject("hard_caps_mismatch")
    if approved_by != allocator_id:
        _reject("approver_mismatch")
    _aware_timestamp(approved_at, "approval_timestamp_invalid")
    if preload_ack != "PASSED":
        _reject("preload_required")
    if not _nonempty_text(child_id) or not _nonempty_text(instance_key):
        _reject("instance_key_required")
    existing = _lease_by_child(pool, child_id)
    if existing is not None:
        if existing.get("status") == "ACTIVE":
            _reject("duplicate_child_id")
        _reject("child_id_history_conflict")
    if not _nonempty_text(shard_id):
        _reject("shard_id_required")
    if not _nonempty_text(integration_domain):
        _reject("integration_domain_required")
    if integration_domain != role_key:
        _reject("integration_domain_mismatch")
    normalized_writes, normalized_reads, mutation_allowed = _validated_access_contract(
        access_mode=access_mode,
        read_scope=read_scope,
        write_set=write_set,
        mutation_allowed=mutation_allowed,
        integration_authority=integration_authority,
    )
    if (
        any(not _nonempty_text(value) for value in (expected_output, start_condition, expiry_condition))
        or not isinstance(return_conditions, Sequence)
        or isinstance(return_conditions, (str, bytes))
        or not return_conditions
        or any(not _nonempty_text(value) for value in return_conditions)
    ):
        _reject("lease_contract_required")
    if not isinstance(measured_cost, Mapping):
        _reject("measured_cost_required")
    measured_values = tuple(
        measured_cost.get(field)
        for field in ("memory_mb", "context_tokens", "message_chars", "tool_calls", "time_seconds")
    )
    if any(isinstance(value, (int, float)) and not math.isfinite(float(value)) for value in measured_values):
        _reject("non_finite_number")
    if any(not _finite_number(value) for value in measured_values):
        _reject("measured_cost_required")
    if float(measured_values[0]) <= 0 or any(float(value) < 0 for value in measured_values[1:]):
        _reject("measured_cost_required")
    lease_numbers = (share, reserve_share, complexity_score, marginal_value_score)
    if any(isinstance(value, (int, float)) and not math.isfinite(float(value)) for value in lease_numbers):
        _reject("non_finite_number")
    if any(not _finite_number(value) for value in lease_numbers):
        _reject("invalid_lease_share")
    if share <= 0 or reserve_share < 0:
        _reject("invalid_lease_share")
    if share <= reserve_share:
        _reject("invalid_lease_share")

    for current in _active_leases(pool):
        if current.get("instance_key") == instance_key:
            _reject("duplicate_instance_key")
        if current.get("role_key") == role_key and current.get("shard_id") == shard_id:
            _reject("duplicate_shard")
        if integration_authority and current.get("integration_authority") is True:
            _reject("duplicate_integration_authority")
        current_writes = current.get("write_set")
        if isinstance(current_writes, (tuple, list)):
            if any(_paths_overlap(path, existing) for path in normalized_writes for existing in current_writes):
                _reject("write_set_overlap")

    available = float(parent.get("available_share", -1.0))
    if available < float(share):
        _reject("parent_envelope_exceeded")

    result = deepcopy(dict(pool))
    result_leases = deepcopy(dict(pool.get("leases", {})))
    budget_id = str(pool.get("budget_id"))
    lease_id = f"{budget_id}:{child_id}"
    child = {
        "schema": "court.budget.lease.v1",
        "budget_id": budget_id,
        "lease_id": lease_id,
        "parent_budget_id": parent.get("lease_id"),
        "parent_id": parent_id,
        "task_id": task_id,
        "phase_id": phase,
        "wave_id": wave_id,
        "role_key": role_key,
        "instance_key": instance_key,
        "level": child_level,
        "direct_superior": direct_superior,
        "normalized_share": float(share),
        "envelope_share": float(share),
        "allocated_share": 0.0,
        "reserve_share": float(reserve_share),
        "available_share": float(share - reserve_share),
        "hard_caps": deepcopy(validated_caps),
        "measured_cost": deepcopy(dict(measured_cost)),
        "write_set": normalized_writes,
        "access_mode": access_mode,
        "read_scope": normalized_reads,
        "mutation_allowed": mutation_allowed,
        "expected_output": expected_output,
        "complexity_score": float(complexity_score),
        "marginal_value_score": float(marginal_value_score),
        "approved_by": approved_by,
        "approved_at": approved_at,
        "start_condition": start_condition,
        "expiry_condition": expiry_condition,
        "return_conditions": tuple(return_conditions),
        "preload_ack": preload_ack,
        "shard_id": shard_id,
        "integration_domain": integration_domain,
        "integration_authority": integration_authority,
        "owner_id": owning_worker_id or child_id,
        "launch_state": "READY",
        "launch_sample_id": None,
        "launch_usage": None,
        "launch_history": (),
        "status": "ACTIVE",
        "release_reason": None,
        "release_evidence": None,
        "release_authority": None,
        "released_by": None,
        "released_at": None,
        "release_generation": None,
        "release_history": (),
    }
    parent_copy = deepcopy(dict(parent))
    parent_copy["allocated_share"] = float(parent.get("allocated_share", 0.0)) + float(share)
    parent_copy["available_share"] = (
        float(parent.get("envelope_share", 0.0))
        - float(parent_copy["allocated_share"])
        - float(parent.get("reserve_share", 0.0))
    )
    result_leases[parent_id] = parent_copy
    result_leases[child_id] = child
    result["leases"] = result_leases
    if integration_authority:
        result["integration_authority_binding"] = _integration_binding_snapshot(
            result,
            child_id,
            child,
        )
    _validate_budget_pool(result)
    return result


def _release_timestamp(value: object) -> datetime:
    return _aware_timestamp(value, "release_timestamp_invalid")


def release_budget_lease(
    pool: Mapping[str, object],
    *,
    lease_id: str,
    reason: str,
    evidence: str | None,
    active_useful: bool,
    released_by: str,
    released_at: str,
) -> dict[str, object]:
    """Release a lease and return its share to the direct parent."""

    _validate_budget_pool(pool)
    active_useful = _require_strict_bool(active_useful)
    child_id, current = _lease_by_id(pool, lease_id)
    if current.get("level") == "root":
        _reject("root_lease_not_releasable")
    if current.get("status") != "ACTIVE":
        _reject("lease_not_active")
    if _has_active_descendant(pool, child_id):
        _reject("active_descendants_present")
    exception_reasons = {"SAFETY_EXCEPTION", "CANCELLED", "DEGRADED", "FAILED_CLOSED"}
    terminal_reasons = exception_reasons | {"COMPLETED"}
    if active_useful and reason not in exception_reasons:
        _reject("active_useful_lease_protected")
    if reason not in terminal_reasons:
        _reject("release_reason_not_terminal")
    return_conditions = current.get("return_conditions")
    if (
        not isinstance(return_conditions, Sequence)
        or isinstance(return_conditions, (str, bytes))
        or reason not in return_conditions
    ):
        _reject("release_reason_not_allowed")
    if reason in {"SAFETY_EXCEPTION", "CANCELLED"} and not _nonempty_text(evidence):
        _reject("exception_evidence_required")
    if reason in {"COMPLETED", "DEGRADED", "FAILED_CLOSED"} and not _nonempty_text(evidence):
        _reject("release_evidence_required")
    if not _nonempty_text(released_by):
        _reject("release_authority_required")
    if released_by not in {"taizi", current.get("direct_superior")}:
        _reject("release_authority_mismatch")
    release_timestamp = _release_timestamp(released_at)
    approval_timestamp = _aware_timestamp(current.get("approved_at"), "approval_timestamp_invalid")
    if release_timestamp < approval_timestamp:
        _reject("release_before_approval")

    result = deepcopy(dict(pool))
    release_generation = int(pool.get("reassessment_generation", 0)) + 1
    result["reassessment_generation"] = release_generation
    result["last_reassessment_trigger"] = "LEASE_RELEASE"
    result_leases = deepcopy(dict(pool.get("leases", {})))
    released = deepcopy(dict(current))
    released["status"] = "RELEASED"
    released["release_reason"] = reason
    released["release_evidence"] = evidence
    released["release_authority"] = released_by
    released["released_by"] = released_by
    released["released_at"] = released_at
    released["release_generation"] = release_generation
    release_record = {
        "reason": reason,
        "evidence": evidence,
        "released_by": released_by,
        "released_at": released_at,
        "generation": release_generation,
    }
    released["release_history"] = tuple(current.get("release_history", ())) + (release_record,)
    result_leases[child_id] = released
    release_ledger = result.get("lease_release_history")
    if not isinstance(release_ledger, tuple):
        _reject("budget_pool_invariant_violation")
    result["lease_release_history"] = release_ledger + (
        {
            "child_id": child_id,
            "lease_id": lease_id,
            "generation": release_generation,
            "reason": reason,
            "evidence": evidence,
            "released_by": released_by,
            "released_at": released_at,
        },
    )

    parent_id = current.get("parent_id")
    parent = result_leases.get(parent_id)
    if not isinstance(parent_id, str) or not isinstance(parent, Mapping):
        _reject("missing_parent_lease")
    parent_copy = deepcopy(dict(parent))
    parent_copy["allocated_share"] = max(
        0.0,
        float(parent.get("allocated_share", 0.0)) - float(current.get("envelope_share", 0.0)),
    )
    parent_copy["available_share"] = (
        float(parent.get("envelope_share", 0.0))
        - float(parent_copy["allocated_share"])
        - float(parent.get("reserve_share", 0.0))
    )
    result_leases[parent_id] = parent_copy
    result["leases"] = result_leases
    _refresh_integration_binding(result)
    _validate_budget_pool(result)
    return result


def _resource_timestamp(value: object) -> datetime:
    return _aware_timestamp(value, "resource_sample_timestamp_invalid")


def _validated_resource_sample(resource_state: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(resource_state, Mapping) or any(field not in resource_state for field in _RESOURCE_FIELDS):
        _reject("resource_sample_incomplete")
    if not _nonempty_text(resource_state.get("sample_id")):
        _reject("resource_sample_incomplete")
    numeric_fields = (
        "max_sample_age_seconds",
        "host_capacity",
        "active_agents",
        "retained_agents",
        "ram_percent",
        "free_memory_mb",
        "context_tokens",
        "message_chars",
        "tool_calls",
        "time_seconds",
    )
    for field in numeric_fields:
        value = resource_state.get(field)
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            _reject("resource_sample_non_finite")
        if not _finite_number(value):
            _reject("resource_sample_incomplete")
    if any(float(resource_state[field]) < 0.0 for field in numeric_fields):
        _reject("resource_sample_negative")
    if float(resource_state["ram_percent"]) > 100.0:
        _reject("resource_sample_ram_percent_invalid")
    for field in (
        "host_capacity",
        "active_agents",
        "retained_agents",
        "context_tokens",
        "message_chars",
        "tool_calls",
    ):
        if not _valid_count(resource_state.get(field)):
            _reject("resource_sample_count_not_integer")
    _require_strict_bool(resource_state.get("reclamation_verified"))
    if float(resource_state["max_sample_age_seconds"]) == 0.0:
        _reject("resource_sample_incomplete")
    sampled_at = _resource_timestamp(resource_state.get("sampled_at"))
    decision_at = _resource_timestamp(resource_state.get("decision_at"))
    now = _resource_timestamp(resource_state.get("now"))
    if sampled_at > decision_at or decision_at > now:
        _reject("resource_sample_timestamp_invalid")
    age_seconds = (now - sampled_at).total_seconds()
    if age_seconds > float(resource_state["max_sample_age_seconds"]):
        _reject("resource_sample_stale")
    sample = deepcopy(dict(resource_state))
    sample["sample_age_seconds"] = age_seconds
    return sample


def _require_fresh_resource_sample(
    pool: Mapping[str, object],
    sample: Mapping[str, object],
    previous_sample_id: str | None,
    *,
    require_previous_id: bool = False,
) -> None:
    history = pool.get("resource_sample_history")
    if not isinstance(history, tuple):
        _reject("budget_pool_invariant_violation")
    if history:
        previous = history[-1]
        if not isinstance(previous, Mapping):
            _reject("budget_pool_invariant_violation")
        last_id = previous.get("sample_id")
        if require_previous_id and previous_sample_id != last_id:
            _reject("resource_resample_required")
        if previous_sample_id is not None and previous_sample_id != last_id:
            _reject("resource_resample_required")
        if sample.get("sample_id") == last_id:
            _reject("resource_resample_required")
        if any(
            isinstance(entry, Mapping) and entry.get("sample_id") == sample.get("sample_id")
            for entry in history[:-1]
        ):
            _reject("resource_sample_replayed")
        if _resource_timestamp(sample.get("sampled_at")) <= _resource_timestamp(previous.get("sampled_at")):
            _reject("resource_resample_required")
        if (
            _resource_timestamp(sample.get("decision_at"))
            <= _resource_timestamp(previous.get("decision_at"))
            or _resource_timestamp(sample.get("now")) <= _resource_timestamp(previous.get("now"))
        ):
            _reject("resource_sample_time_not_monotonic")
    elif previous_sample_id is not None:
        _reject("resource_resample_required")


def _candidate_lease(
    pool: Mapping[str, object],
    candidate: Mapping[str, object],
) -> Mapping[str, object] | None:
    child_id = candidate.get("child_id")
    lease_id = candidate.get("lease_id")
    if not isinstance(child_id, str) or not isinstance(lease_id, str):
        return None
    value = _lease_by_child(pool, child_id)
    if value is None or value.get("lease_id") != lease_id or value.get("status") != "ACTIVE":
        return None
    return value


def _per_agent_hard_limit_reason(value: Mapping[str, object]) -> str | None:
    hard_caps = value.get("hard_caps")
    measured = value.get("measured_cost")
    if not isinstance(hard_caps, Mapping) or not isinstance(measured, Mapping):
        return "measured_agent_cost"
    memory_max = hard_caps.get("memory_mb_max")
    if _finite_number(memory_max) and float(measured.get("memory_mb", 0.0)) > float(memory_max):
        return "per_agent_memory"
    context_max = hard_caps.get("context_tokens_max")
    if _finite_number(context_max) and float(measured.get("context_tokens", 0.0)) > float(context_max):
        return "per_agent_context"
    messages_max = hard_caps.get("message_chars_max")
    if _finite_number(messages_max) and float(measured.get("message_chars", 0.0)) > float(messages_max):
        return "per_agent_messages"
    tools_max = hard_caps.get("tool_calls_max")
    if _finite_number(tools_max) and float(measured.get("tool_calls", 0.0)) > float(tools_max):
        return "per_agent_tools"
    time_max = hard_caps.get("time_seconds_max")
    if _finite_number(time_max) and float(measured.get("time_seconds", 0.0)) > float(time_max):
        return "per_agent_time"
    return None


def _hard_limit_reason(
    hard_limits: Mapping[str, object],
    resource_state: Mapping[str, object],
    eligible: Sequence[Mapping[str, object]],
) -> str | None:
    ram_max = hard_limits.get("ram_percent_max")
    if _finite_number(ram_max) and float(resource_state["ram_percent"]) >= float(ram_max):
        return "ram"
    context_max = hard_limits.get("context_tokens_max")
    if _finite_number(context_max) and float(resource_state["context_tokens"]) > float(context_max):
        return "context"
    messages_max = hard_limits.get("message_chars_max")
    if _finite_number(messages_max) and float(resource_state["message_chars"]) > float(messages_max):
        return "messages"
    tools_max = hard_limits.get("tool_calls_max")
    if _finite_number(tools_max) and float(resource_state["tool_calls"]) > float(tools_max):
        return "tools"
    time_max = hard_limits.get("time_seconds_max")
    if _finite_number(time_max) and float(resource_state["time_seconds"]) > float(time_max):
        return "time"
    retained_max = hard_limits.get("retained_agents_max")
    if _finite_number(retained_max) and int(resource_state["retained_agents"]) > int(retained_max):
        return "retained"
    physical_occupancy = int(resource_state["active_agents"])
    if resource_state.get("reclamation_verified") is False:
        physical_occupancy += int(resource_state["retained_agents"])
    if physical_occupancy >= int(resource_state["host_capacity"]):
        return "host_capacity"
    memory_costs = []
    for value in eligible:
        measured = value.get("measured_cost")
        if isinstance(measured, Mapping) and _finite_number(measured.get("memory_mb")):
            memory_costs.append(float(measured["memory_mb"]))
    if memory_costs and float(resource_state["free_memory_mb"]) < min(memory_costs):
        return "free_memory"
    return None


def plan_budgeted_launch(
    pool: Mapping[str, object],
    *,
    candidates: Sequence[Mapping[str, object]],
    resource_state: Mapping[str, object],
    requested_count: int,
    taizi_approved_count: int,
    previous_sample_id: str | None,
    taizi_approved_bindings: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Approve a measured small wave before any child starts."""

    _validate_budget_pool(pool)
    if not _valid_count(requested_count):
        _reject("invalid_requested_count")
    if not _valid_count(taizi_approved_count):
        _reject("invalid_approved_count")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        _reject("candidate_contract_invalid")
    sample = _validated_resource_sample(resource_state)
    sample_id = str(sample["sample_id"])
    _require_fresh_resource_sample(
        pool,
        sample,
        previous_sample_id,
        require_previous_id=True,
    )
    if requested_count != len(candidates):
        _reject("requested_count_mismatch")
    if taizi_approved_count > requested_count:
        _reject("approval_count_invalid")

    deferred: dict[str, str] = {}
    eligible: dict[str, Mapping[str, object]] = {}
    candidate_leases: dict[str, Mapping[str, object]] = {}
    prospective_write_sets: dict[str, tuple[str, ...]] = {}
    seen_children: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            _reject("candidate_contract_invalid")
        child = candidate.get("child_id")
        child_id = child if isinstance(child, str) and child else f"candidate-{index + 1}"
        if child_id in seen_children:
            _reject("duplicate_wave_candidate")
        seen_children.add(child_id)
        root = _lease_by_child(pool, str(pool.get("root_id")))
        if (
            child_id == pool.get("root_id")
            or child_id == "taizi"
            or (isinstance(root, Mapping) and candidate.get("lease_id") == root.get("lease_id"))
        ):
            _reject("root_or_taizi_candidate_forbidden")
        value = _candidate_lease(pool, candidate)
        if value is None:
            deferred[child_id] = "child_lease_required"
            continue
        if value.get("level") == "root" or value.get("role_key") == "taizi":
            _reject("root_or_taizi_candidate_forbidden")
        if value.get("launch_state") == "CONSUMED":
            _reject("child_lease_already_consumed")
        if value.get("launch_state") != "READY":
            _reject("child_lease_not_launchable")
        candidate_leases[child_id] = value
        prospective_write_sets[child_id] = _validated_write_set(
            candidate.get("prospective_write_set", value.get("write_set"))
        )
        measured = value.get("measured_cost")
        if not isinstance(measured, Mapping) or not _finite_number(measured.get("memory_mb")):
            deferred[child_id] = "measured_agent_cost_required"
            continue
        per_agent_reason = _per_agent_hard_limit_reason(value)
        if per_agent_reason is not None:
            deferred[child_id] = f"hard_limit:{per_agent_reason}"
            continue
        if float(value.get("marginal_value_score", 0.0)) <= float(value.get("complexity_score", 0.0)):
            deferred[child_id] = "low_marginal_value"
            continue
        eligible[child_id] = value

    if (
        taizi_approved_bindings is None
        or not isinstance(taizi_approved_bindings, Sequence)
        or isinstance(taizi_approved_bindings, (str, bytes))
    ):
        _reject("approved_bindings_required")
    if len(taizi_approved_bindings) != taizi_approved_count:
        _reject("approved_binding_count_mismatch")
    approved_order: list[str] = []
    approved_seen: set[str] = set()
    for binding in taizi_approved_bindings:
        if not isinstance(binding, Mapping):
            _reject("approved_binding_mismatch")
        child_id = binding.get("child_id")
        if not _nonempty_text(child_id):
            _reject("approved_binding_mismatch")
        child_key = str(child_id)
        if child_key in approved_seen:
            _reject("approved_binding_mismatch")
        if child_key not in seen_children:
            _reject("approved_binding_not_requested")
        value = candidate_leases.get(child_key)
        if value is None:
            _reject("approved_binding_mismatch")
        expected = {
            "child_id": child_key,
            "lease_id": value.get("lease_id"),
            "instance_key": value.get("instance_key"),
            "role_key": value.get("role_key"),
            "write_set": value.get("write_set"),
            "approved_by": "taizi",
        }
        if any(binding.get(field) != expected_value for field, expected_value in expected.items()):
            _reject("approved_binding_mismatch")
        approved_seen.add(child_key)
        approved_order.append(child_key)

    approved_eligible = [(child_id, eligible[child_id]) for child_id in approved_order if child_id in eligible]
    for child_id in eligible:
        if child_id not in approved_seen:
            deferred[child_id] = "not_approved_this_wave"

    serialization_conflicts: list[tuple[str, str]] = []
    for left_index, (left_id, _) in enumerate(approved_eligible):
        left_writes = prospective_write_sets[left_id]
        for right_id, _ in approved_eligible[left_index + 1 :]:
            right_writes = prospective_write_sets[right_id]
            if any(_paths_overlap(left, right) for left in left_writes for right in right_writes):
                serialization_conflicts.append((left_id, right_id))

    hard_limits = pool.get("hard_limits")
    if not isinstance(hard_limits, Mapping):
        _reject("invalid_budget_pool")
    hard_reason = _hard_limit_reason(hard_limits, sample, [value for _, value in approved_eligible])
    launch_ids: list[str] = []

    serialization_applied = bool(serialization_conflicts) and hard_reason is None
    if hard_reason is not None:
        for child_id, _ in approved_eligible:
            deferred[child_id] = f"hard_limit:{hard_reason}"
    elif serialization_applied:
        for child_id, _ in approved_eligible:
            deferred[child_id] = "shared_write_set_serialized"
    else:
        physical_occupancy = int(sample["active_agents"])
        if sample.get("reclamation_verified") is False:
            physical_occupancy += int(sample["retained_agents"])
        host_remaining = max(0, int(sample["host_capacity"]) - physical_occupancy)
        memory_remaining = float(sample["free_memory_mb"])
        context_max = hard_limits.get("context_tokens_max")
        context_remaining = (
            float(context_max) - float(sample["context_tokens"])
            if _finite_number(context_max)
            else math.inf
        )
        tools_max = hard_limits.get("tool_calls_max")
        tools_remaining = (
            float(tools_max) - float(sample["tool_calls"])
            if _finite_number(tools_max)
            else math.inf
        )
        messages_max = hard_limits.get("message_chars_max")
        messages_remaining = (
            float(messages_max) - float(sample["message_chars"])
            if _finite_number(messages_max)
            else math.inf
        )
        time_max = hard_limits.get("time_seconds_max")
        time_remaining = (
            float(time_max) - float(sample["time_seconds"])
            if _finite_number(time_max)
            else math.inf
        )
        for child_id, value in approved_eligible:
            measured = value.get("measured_cost")
            memory_mb = float(measured.get("memory_mb", 0.0)) if isinstance(measured, Mapping) else 0.0
            context_tokens = (
                float(measured.get("context_tokens", 0.0)) if isinstance(measured, Mapping) else 0.0
            )
            message_chars = (
                float(measured.get("message_chars", 0.0)) if isinstance(measured, Mapping) else 0.0
            )
            tool_calls = float(measured.get("tool_calls", 0.0)) if isinstance(measured, Mapping) else 0.0
            time_seconds = (
                float(measured.get("time_seconds", 0.0)) if isinstance(measured, Mapping) else 0.0
            )
            if host_remaining <= 0:
                deferred[child_id] = "composite_budget_exhausted:host_capacity"
                continue
            if memory_mb > memory_remaining:
                deferred[child_id] = "composite_budget_exhausted:free_memory"
                continue
            if context_tokens > context_remaining:
                deferred[child_id] = "composite_budget_exhausted:context"
                continue
            if message_chars > messages_remaining:
                deferred[child_id] = "composite_budget_exhausted:messages"
                continue
            if tool_calls > tools_remaining:
                deferred[child_id] = "composite_budget_exhausted:tools"
                continue
            if time_seconds > time_remaining:
                deferred[child_id] = "composite_budget_exhausted:time"
                continue
            launch_ids.append(child_id)
            host_remaining -= 1
            memory_remaining -= memory_mb
            context_remaining -= context_tokens
            messages_remaining -= message_chars
            tools_remaining -= tool_calls
            time_remaining -= time_seconds

    consumed_pool: dict[str, object] = deepcopy(dict(pool))
    consumed_leases = deepcopy(dict(pool.get("leases", {})))
    for child_id in launch_ids:
        current = consumed_leases.get(child_id)
        if not isinstance(current, Mapping):
            _reject("child_lease_required")
        consumed = deepcopy(dict(current))
        usage = deepcopy(dict(current.get("measured_cost", {})))
        launch_record = {
            "sample_id": sample_id,
            "generation": int(pool.get("reassessment_generation", 0)),
            "usage": usage,
        }
        consumed["launch_state"] = "CONSUMED"
        consumed["launch_sample_id"] = sample_id
        consumed["launch_usage"] = usage
        consumed["launch_history"] = tuple(current.get("launch_history", ())) + (launch_record,)
        consumed_leases[child_id] = consumed
    consumed_pool["leases"] = consumed_leases
    if not serialization_applied:
        _append_resource_sample(consumed_pool, sample)
    _validate_budget_pool(consumed_pool)

    approved_count = len(launch_ids)
    if serialization_applied:
        approval_status = "SERIALIZED"
    elif approved_count == requested_count:
        approval_status = "APPROVED"
    elif approved_count:
        approval_status = "DOWNSIZED"
    else:
        approval_status = "DEFERRED"

    return {
        "schema": "court.budget.small_wave.v1",
        "preflight_before_launch": True,
        "decision_model": "COMPOSITE_NOT_SINGLE_THRESHOLD",
        "decision_factors": _COMPOSITE_FACTORS,
        "resource_sample_complete": True,
        "resource_sample_id": sample_id,
        "resource_sampled_at": sample["sampled_at"],
        "requested_count": requested_count,
        "taizi_approved_count": taizi_approved_count,
        "taizi_approved_bindings": tuple(deepcopy(list(taizi_approved_bindings))),
        "approved_binding_ids": tuple(approved_order),
        "approved_count": approved_count,
        "approval_status": approval_status,
        "launch_ids": tuple(launch_ids),
        "serial_queue": tuple(approved_order) if serialization_applied else (),
        "serialization_conflicts": tuple(serialization_conflicts),
        "deferred": deferred,
        "interrupt_ids": (),
        "resample_required_before_next_wave": True,
        "budget_pool": consumed_pool,
    }


def reassess_budget_pool(
    pool: Mapping[str, object],
    *,
    trigger: str,
    resource_state: Mapping[str, object],
    active_useful_lease_ids: Sequence[str],
    cancelled_lease_ids: Sequence[str],
    exception_evidence: Mapping[str, str],
) -> dict[str, object]:
    """Record a fresh wave/resource sample without blindly revoking useful leases."""

    _validate_budget_pool(pool)
    if trigger not in {"NEW_WAVE", "RESOURCE_CHANGE"}:
        _reject("unknown_reassessment_trigger")
    if (
        not isinstance(active_useful_lease_ids, Sequence)
        or isinstance(active_useful_lease_ids, (str, bytes))
        or not isinstance(cancelled_lease_ids, Sequence)
        or isinstance(cancelled_lease_ids, (str, bytes))
        or not isinstance(exception_evidence, Mapping)
    ):
        _reject("reassessment_contract_invalid")
    sample = _validated_resource_sample(resource_state)
    _require_fresh_resource_sample(pool, sample, None)
    result: dict[str, object] = deepcopy(dict(pool))
    active_useful = set(active_useful_lease_ids)
    if len(set(cancelled_lease_ids)) != len(cancelled_lease_ids):
        _reject("duplicate_cancelled_lease")

    def lease_depth(lease_id: str) -> int:
        child_id, current = _lease_by_id(pool, lease_id)
        depth = 0
        visited = {child_id}
        parent_id = current.get("parent_id")
        values = pool.get("leases")
        if not isinstance(values, Mapping):
            _reject("invalid_budget_pool")
        while isinstance(parent_id, str):
            if parent_id in visited:
                _reject("budget_pool_invariant_violation")
            visited.add(parent_id)
            depth += 1
            parent = values.get(parent_id)
            parent_id = parent.get("parent_id") if isinstance(parent, Mapping) else None
        return depth

    ordered_cancelled = sorted(cancelled_lease_ids, key=lambda value: (-lease_depth(value), value))
    for lease_id in ordered_cancelled:
        _, current = _lease_by_id(result, lease_id)
        result = release_budget_lease(
            result,
            lease_id=lease_id,
            reason="CANCELLED",
            evidence=exception_evidence.get(lease_id),
            active_useful=lease_id in active_useful,
            released_by=str(current.get("direct_superior", "")),
            released_at=str(sample["decision_at"]),
        )
    result["reassessment_generation"] = int(result.get("reassessment_generation", 0)) + 1
    result["last_reassessment_trigger"] = trigger
    _append_resource_sample(result, sample)
    _refresh_integration_binding(result)
    _validate_budget_pool(result)
    return result
