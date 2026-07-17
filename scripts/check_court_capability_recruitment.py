"""Validate the pure capability-recruitment decision contract offline."""

from __future__ import annotations

import builtins
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any, Iterator, Mapping
import urllib.request


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "references" / "fixtures" / "capability-recruitment-cases.json"
REQUIRED_RESULT_FIELDS = {
    "schema",
    "discovery_query",
    "discovery_status",
    "searched_kinds",
    "candidate_fit",
    "task_complexity",
    "reuse_value",
    "creation_recommendation",
    "question",
    "user_decision",
    "provenance_evidence",
    "reason_codes",
    "network_policy",
    "next_action",
    "input_validation",
    "side_effects",
}
REQUIRED_FIXTURE_CASE_NAMES = frozenset(
    {
        "local_hit_dispatchable",
        "local_miss_network_allowed_not_searched",
        "stale_local_candidate",
        "ambiguous_local_approval_blocked",
        "authority_not_selected",
        "explicit_no_network_zero_calls",
        "no_network_external_consent_cannot_bypass",
        "unset_authority_external_consent_cannot_bypass",
        "unknown_discovery_external_consent_cannot_bypass",
        "skill_public_discovery",
        "plugin_public_discovery",
        "mcp_public_discovery",
        "network_failure_is_unknown",
        "untrusted_source_hard_stop",
        "paid_candidate_hard_stop",
        "login_candidate_hard_stop",
        "private_upload_candidate_hard_stop",
        "candidate_kind_not_searched_hard_stop",
        "unknown_declared_provenance_hard_stop",
        "paid_declaration_conflict_hard_stop",
        "boolean_flag_type_hard_stop",
        "high_likely_reuse_creation_proposal",
        "four_stable_steps_creation_proposal",
        "four_stable_steps_explicit_one_off_stays_direct",
        "bound_local_create_consent_suppresses_proposal_question",
        "sufficient_candidate_prevents_creation",
        "trivial_one_off_no_creation",
        "private_content_no_creation",
        "user_declined_creation_continues",
        "proposal_asked_only_once",
        "existing_combination_sufficient",
    }
)
REQUIRED_REDACTION_CASE_NAMES = frozenset(
    {
        "redacts_private_query_material",
        "redacts_sk_proj_and_fullwidth_colon",
        "redacts_quoted_windows_path_with_spaces",
        "redacts_fullwidth_path_and_password_labels",
        "redacts_identity_repository_and_unlabelled_tokens",
    }
)
REQUIRED_CONSENT_MUTATION_FIELDS = (
    "action",
    "kind",
    "name",
    "purpose",
    "destination",
    "allowed_actions",
    "candidate_snapshot",
    "candidate_digest",
    "discovery_query",
    "discovery_status",
    "decree_id",
    "turn_id",
)
REQUIRED_ACTUAL_CANDIDATE_MUTATION_FIELDS = (
    "requires_paid_action",
    "requires_login",
    "requires_private_upload",
    "trusted",
    "verified",
)
MIN_FIXTURE_CASES = len(REQUIRED_FIXTURE_CASE_NAMES)
MIN_REDACTION_CASES = len(REQUIRED_REDACTION_CASE_NAMES)
MIN_CONSENT_MUTATION_FIELDS = len(REQUIRED_CONSENT_MUTATION_FIELDS)
C1_RED_CASE_COUNT = 20
C1_RED_FIELDS = frozenset(
    {"action", "candidate_digest", "content_hash", "destination", "discovery_query",
     "discovery_status", "immutable_ref", "kind", "source"}
)
REQUIRED_STABLE_CASE_IDS = frozenset(
    {
        "local_hit", "local_miss", "local_stale", "local_ambiguous",
        "public_discovery_allowed", "approval_blocked", "explicit_no_network", "redacted_query",
        "skill_candidate", "plugin_candidate", "mcp_candidate", "discovery_failure",
        "untrusted_source", "paid_candidate", "login_required_candidate", "private_upload_candidate",
        "create_skill_high_reuse", "create_skill_one_off_rejected",
        "create_skill_secret_input_rejected", "user_rejected_continue",
    }
)


def _load_fixture() -> dict[str, Any]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("fixture_root_not_object")
    if data.get("schema") != "court_capability_recruitment_cases.v1":
        raise AssertionError("fixture_schema")
    return data


def _fixture_quality_errors(data: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    cases = data.get("cases")
    redaction_cases = data.get("redaction_cases")
    consent_binding = data.get("consent_binding")
    c1_red_cases = data.get("c1_red_mutation_cases")

    if not isinstance(cases, list) or not cases:
        errors.append("fixture_cases_empty")
        cases = []
    elif len(cases) < MIN_FIXTURE_CASES:
        errors.append(f"fixture_cases_below_fixed_minimum:{len(cases)}<{MIN_FIXTURE_CASES}")

    if not isinstance(redaction_cases, list) or not redaction_cases:
        errors.append("fixture_redaction_cases_empty")
        redaction_cases = []
    elif len(redaction_cases) < MIN_REDACTION_CASES:
        errors.append(f"fixture_redaction_cases_below_fixed_minimum:{len(redaction_cases)}<{MIN_REDACTION_CASES}")

    all_names: list[str] = []
    group_names: dict[str, list[str]] = {"cases": [], "redaction_cases": []}
    for group_name, group in (("cases", cases), ("redaction_cases", redaction_cases)):
        for index, item in enumerate(group):
            if not isinstance(item, dict):
                errors.append(f"fixture_{group_name}_entry_not_object:{index}")
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                errors.append(f"fixture_{group_name}_name_empty:{index}")
                continue
            all_names.append(name)
            group_names[group_name].append(name)
    duplicates = sorted({name for name in all_names if all_names.count(name) > 1})
    if duplicates:
        errors.append("fixture_case_names_not_unique:" + ",".join(duplicates))
    case_names = set(group_names["cases"])
    redaction_names = set(group_names["redaction_cases"])
    main_case_ids = [str(item.get("id") or "").strip() for item in cases if isinstance(item, dict)]
    if len(main_case_ids) != len(cases) or any(not case_id for case_id in main_case_ids):
        errors.append("fixture_main_case_id_missing")
    if len(main_case_ids) != len(set(main_case_ids)):
        errors.append("fixture_main_case_ids_not_unique")
    missing_stable_ids = sorted(REQUIRED_STABLE_CASE_IDS - set(main_case_ids))
    if missing_stable_ids:
        errors.append("fixture_required_stable_case_ids_missing:" + ",".join(missing_stable_ids))
    if len(cases) != MIN_FIXTURE_CASES or case_names != REQUIRED_FIXTURE_CASE_NAMES:
        missing = sorted(REQUIRED_FIXTURE_CASE_NAMES - case_names)
        extra = sorted(case_names - REQUIRED_FIXTURE_CASE_NAMES)
        errors.append(
            f"fixture_cases_not_fixed_contract:count={len(cases)};missing={','.join(missing)};extra={','.join(extra)}"
        )
    if len(redaction_cases) != MIN_REDACTION_CASES or redaction_names != REQUIRED_REDACTION_CASE_NAMES:
        missing = sorted(REQUIRED_REDACTION_CASE_NAMES - redaction_names)
        extra = sorted(redaction_names - REQUIRED_REDACTION_CASE_NAMES)
        errors.append(
            f"fixture_redaction_cases_not_fixed_contract:count={len(redaction_cases)};"
            f"missing={','.join(missing)};extra={','.join(extra)}"
        )

    if not isinstance(consent_binding, dict):
        errors.append("fixture_consent_binding_empty")
    else:
        mutation_fields = consent_binding.get("mutation_fields")
        if not isinstance(mutation_fields, list) or not mutation_fields:
            errors.append("fixture_consent_mutation_fields_empty")
        else:
            normalized_fields = [str(item).strip() for item in mutation_fields if str(item).strip()]
            if tuple(normalized_fields) != REQUIRED_CONSENT_MUTATION_FIELDS:
                errors.append(
                    "fixture_consent_mutation_fields_not_fixed_contract:"
                    + ",".join(normalized_fields)
                )
            if len(normalized_fields) != len(set(normalized_fields)):
                errors.append("fixture_consent_mutation_fields_not_unique")
        actual_mutation_fields = consent_binding.get("actual_candidate_mutation_fields")
        if not isinstance(actual_mutation_fields, list):
            errors.append("fixture_actual_candidate_mutation_fields_empty")
        else:
            normalized_actual = tuple(str(item).strip() for item in actual_mutation_fields)
            if normalized_actual != REQUIRED_ACTUAL_CANDIDATE_MUTATION_FIELDS:
                errors.append(
                    "fixture_actual_candidate_mutation_fields_not_fixed_contract:"
                    + ",".join(normalized_actual)
                )
        implied = consent_binding.get("create_does_not_imply")
        if not isinstance(implied, list) or not implied:
            errors.append("fixture_cross_action_cases_empty")
    if not isinstance(c1_red_cases, list) or len(c1_red_cases) != C1_RED_CASE_COUNT:
        errors.append(f"fixture_c1_red_case_count:{len(c1_red_cases) if isinstance(c1_red_cases, list) else 0}")
    else:
        case_ids = [str(item.get("id") or "").strip() for item in c1_red_cases if isinstance(item, dict)]
        if len(case_ids) != C1_RED_CASE_COUNT or any(not case_id for case_id in case_ids):
            errors.append("fixture_c1_red_case_id_missing")
        if len(case_ids) != len(set(case_ids)):
            errors.append("fixture_c1_red_case_ids_not_unique")
        covered_fields = {
            str(item.get("field") or "").strip()
            for item in c1_red_cases
            if isinstance(item, dict) and item.get("mode") in {"request_mutation", "consent_mutation"}
        }
        if covered_fields != C1_RED_FIELDS:
            errors.append("fixture_c1_red_fields_not_fixed_contract:" + ",".join(sorted(covered_fields)))
        stale_actions = {
            str(action).upper()
            for item in c1_red_cases
            if isinstance(item, dict) and item.get("mode") == "stale_actions"
            for action in item.get("actions", [])
        }
        if stale_actions != {"CREATE", "INSTALL", "MODIFY", "ENABLE"}:
            errors.append("fixture_c1_red_stale_actions_not_fixed_contract:" + ",".join(sorted(stale_actions)))
    return errors


def _check_fixture_quality_gate(data: dict[str, Any], errors: list[str]) -> dict[str, object]:
    errors.extend(_fixture_quality_errors(data))

    cleared = copy.deepcopy(data)
    cleared["cases"] = []
    if "fixture_cases_empty" not in _fixture_quality_errors(cleared):
        errors.append("fixture_gate_did_not_reject_cleared_cases")

    below_minimum = copy.deepcopy(data)
    below_minimum["cases"] = list(below_minimum.get("cases", []))[: MIN_FIXTURE_CASES - 1]
    if not any(item.startswith("fixture_cases_below_fixed_minimum:") for item in _fixture_quality_errors(below_minimum)):
        errors.append("fixture_gate_did_not_enforce_fixed_minimum")

    duplicate = copy.deepcopy(data)
    duplicate_cases = list(duplicate.get("cases", []))
    if duplicate_cases:
        duplicate_cases.append(copy.deepcopy(duplicate_cases[0]))
    duplicate["cases"] = duplicate_cases
    if not any(item.startswith("fixture_case_names_not_unique:") for item in _fixture_quality_errors(duplicate)):
        errors.append("fixture_gate_did_not_reject_duplicate_case")

    duplicate_id = copy.deepcopy(data)
    duplicate_id_cases = list(duplicate_id.get("cases", []))
    if len(duplicate_id_cases) >= 2:
        duplicate_id_cases[1]["id"] = duplicate_id_cases[0]["id"]
    duplicate_id["cases"] = duplicate_id_cases
    if "fixture_main_case_ids_not_unique" not in _fixture_quality_errors(duplicate_id):
        errors.append("fixture_gate_did_not_reject_duplicate_main_case_id")

    replaced = copy.deepcopy(data)
    replaced_cases = list(replaced.get("cases", []))
    if replaced_cases:
        replaced_cases[0] = copy.deepcopy(replaced_cases[0])
        replaced_cases[0]["name"] = "replacement-with-same-count"
    replaced["cases"] = replaced_cases
    if not any(item.startswith("fixture_cases_not_fixed_contract:") for item in _fixture_quality_errors(replaced)):
        errors.append("fixture_gate_did_not_pin_required_case_names")

    weakened_mutations = copy.deepcopy(data)
    weakened_mutations["consent_binding"]["actual_candidate_mutation_fields"] = ["trusted"]
    if not any(
        item.startswith("fixture_actual_candidate_mutation_fields_not_fixed_contract:")
        for item in _fixture_quality_errors(weakened_mutations)
    ):
        errors.append("fixture_gate_did_not_pin_actual_candidate_mutations")

    return {
        "minimum_cases": MIN_FIXTURE_CASES,
        "minimum_redaction_cases": MIN_REDACTION_CASES,
        "minimum_consent_mutation_fields": MIN_CONSENT_MUTATION_FIELDS,
        "actual_candidate_mutation_fields": len(REQUIRED_ACTUAL_CANDIDATE_MUTATION_FIELDS),
        "case_names_unique": not any(
            item.startswith("fixture_case_names_not_unique:") for item in _fixture_quality_errors(data)
        ),
        "c1_red_case_ids_distinct": len(
            {str(item.get("id") or "") for item in data.get("c1_red_mutation_cases", []) if isinstance(item, dict)}
        ) == C1_RED_CASE_COUNT,
        "main_case_ids_unique": len(
            {str(item.get("id") or "") for item in data.get("cases", []) if isinstance(item, dict)}
        ) == len(data.get("cases", [])),
        "required_stable_case_ids": len(REQUIRED_STABLE_CASE_IDS),
    }


def _deep_get(value: object, dotted: str) -> object:
    current = value
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(dotted)
    return current


def _merge_case(data: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(data["defaults"])
    payload.update(copy.deepcopy(case.get("input", {})))
    templates = data["candidate_templates"]
    local_refs = payload.pop("local_candidate_refs", [])
    discovered_refs = payload.pop("discovered_candidate_refs", [])
    payload["local_candidates"] = [copy.deepcopy(templates[name]) for name in local_refs]
    payload["discovered_candidates"] = [copy.deepcopy(templates[name]) for name in discovered_refs]
    candidate_overrides = payload.pop("candidate_overrides", {})
    if isinstance(candidate_overrides, Mapping):
        for candidate in [*payload["local_candidates"], *payload["discovered_candidates"]]:
            updates = candidate_overrides.get(candidate.get("name"))
            if isinstance(updates, Mapping):
                candidate.update(copy.deepcopy(dict(updates)))
    action_binding_ref = payload.pop("action_binding_ref", None)
    if action_binding_ref:
        binding = copy.deepcopy(data["action_bindings"][action_binding_ref])
        payload["action_request"] = binding["request"]
        payload["consent"] = binding["consent"]
        if binding.get("action_candidate_ref"):
            payload["action_candidate"] = copy.deepcopy(templates[binding["action_candidate_ref"]])
        elif isinstance(binding.get("action_candidate"), dict):
            payload["action_candidate"] = copy.deepcopy(binding["action_candidate"])
    return payload


def _tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        digest.update(relative.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


@contextmanager
def _forbid_side_effects() -> Iterator[dict[str, int]]:
    counters = {"network_calls": 0, "write_calls": 0, "subprocess_calls": 0, "cache_write_calls": 0}
    original_open = builtins.open
    original_socket = socket.socket
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    original_urlopen = urllib.request.urlopen
    original_subprocess_methods = {
        name: getattr(subprocess, name) for name in ("Popen", "call", "check_call", "check_output", "run")
    }
    bootstrap_external = importlib.import_module("importlib._bootstrap_external")
    original_write_atomic = getattr(bootstrap_external, "_write_atomic")
    original_path_methods = {
        name: getattr(Path, name)
        for name in ("write_text", "write_bytes", "touch", "mkdir", "unlink", "rename", "replace")
    }
    original_os_methods = {
        name: getattr(os, name)
        for name in ("remove", "unlink", "rename", "replace", "mkdir", "makedirs")
    }

    def guarded_open(file: object, mode: str = "r", *args: object, **kwargs: object):
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            counters["write_calls"] += 1
            raise AssertionError(f"write_forbidden:open:{file}")
        return original_open(file, mode, *args, **kwargs)

    def network_forbidden(*_args: object, **_kwargs: object):
        counters["network_calls"] += 1
        raise AssertionError("network_forbidden")

    def write_forbidden(*_args: object, **_kwargs: object):
        counters["write_calls"] += 1
        raise AssertionError("write_forbidden")

    def subprocess_forbidden(*_args: object, **_kwargs: object):
        counters["subprocess_calls"] += 1
        raise AssertionError("subprocess_forbidden")

    def cache_write_forbidden(*_args: object, **_kwargs: object):
        counters["cache_write_calls"] += 1
        raise AssertionError("cache_write_forbidden")

    builtins.open = guarded_open
    socket.socket = network_forbidden  # type: ignore[assignment]
    socket.create_connection = network_forbidden  # type: ignore[assignment]
    socket.getaddrinfo = network_forbidden  # type: ignore[assignment]
    urllib.request.urlopen = network_forbidden  # type: ignore[assignment]
    for name in original_subprocess_methods:
        setattr(subprocess, name, subprocess_forbidden)
    setattr(bootstrap_external, "_write_atomic", cache_write_forbidden)
    for name in original_path_methods:
        setattr(Path, name, write_forbidden)
    for name in original_os_methods:
        setattr(os, name, write_forbidden)
    try:
        yield counters
    finally:
        builtins.open = original_open
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create_connection  # type: ignore[assignment]
        socket.getaddrinfo = original_getaddrinfo  # type: ignore[assignment]
        urllib.request.urlopen = original_urlopen  # type: ignore[assignment]
        for name, method in original_subprocess_methods.items():
            setattr(subprocess, name, method)
        setattr(bootstrap_external, "_write_atomic", original_write_atomic)
        for name, method in original_path_methods.items():
            setattr(Path, name, method)
        for name, method in original_os_methods.items():
            setattr(os, name, method)


def _load_modules(errors: list[str]):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    for module_name in ("check_capability_index_gate", "court_capability_recruitment"):
        sys.modules.pop(module_name, None)
    recruitment = None
    gate = None
    try:
        recruitment = importlib.import_module("court_capability_recruitment")
    except ModuleNotFoundError:
        errors.append("missing_module:court_capability_recruitment")
    except Exception as exc:  # pragma: no cover - surfaced as a controlled RED
        errors.append(f"recruitment_import_error:{type(exc).__name__}:{exc}")
    try:
        gate = importlib.import_module("check_capability_index_gate")
    except Exception as exc:  # pragma: no cover - surfaced as a controlled RED
        errors.append(f"gate_import_error:{type(exc).__name__}:{exc}")
    return recruitment, gate


def _check_side_effect_guard(errors: list[str]) -> dict[str, bool]:
    probes = {
        "socket": lambda: socket.socket(),
        "subprocess": lambda: subprocess.run([sys.executable, "-V"]),
        "filesystem": lambda: Path("forbidden-side-effect-probe").write_text("x", encoding="utf-8"),
    }
    caught: dict[str, bool] = {}
    with _forbid_side_effects() as counters:
        for name, probe in probes.items():
            try:
                probe()
            except AssertionError:
                caught[name] = True
            else:
                caught[name] = False
                errors.append(f"side_effect_guard_probe_not_caught:{name}")
        bootstrap_external = importlib.import_module("importlib._bootstrap_external")
        try:
            getattr(bootstrap_external, "_write_atomic")("forbidden.pyc", b"x", 0o666)
        except AssertionError:
            caught["cache"] = True
        else:
            caught["cache"] = False
            errors.append("side_effect_guard_probe_not_caught:cache")
    expected = {"network_calls": 1, "write_calls": 1, "subprocess_calls": 1, "cache_write_calls": 1}
    if counters != expected:
        errors.append(f"side_effect_guard_probe_counts:{counters!r}")
    return caught


def _check_cases(data: dict[str, Any], recruitment: object, errors: list[str]) -> int:
    evaluate = getattr(recruitment, "evaluate_recruitment", None)
    if not callable(evaluate):
        errors.append("missing_callable:evaluate_recruitment")
        return 0
    passed = 0
    for raw_case in data.get("cases", []):
        name = str(raw_case.get("name", "unnamed"))
        try:
            result = evaluate(_merge_case(data, raw_case))
        except Exception as exc:
            errors.append(f"{name}:evaluation_error:{type(exc).__name__}:{exc}")
            continue
        missing = sorted(REQUIRED_RESULT_FIELDS - set(result)) if isinstance(result, dict) else sorted(REQUIRED_RESULT_FIELDS)
        if missing:
            errors.append(f"{name}:missing_result_fields:{','.join(missing)}")
            continue
        case_errors: list[str] = []
        for dotted, expected in raw_case.get("expect", {}).items():
            try:
                actual = _deep_get(result, dotted)
            except KeyError:
                case_errors.append(f"missing:{dotted}")
                continue
            if actual != expected:
                case_errors.append(f"{dotted}:{actual!r}!={expected!r}")
        reasons = result.get("reason_codes", [])
        for reason in raw_case.get("reason_includes", []):
            if reason not in reasons:
                case_errors.append(f"missing_reason:{reason}")
        for reason in raw_case.get("reason_excludes", []):
            if reason in reasons:
                case_errors.append(f"forbidden_reason:{reason}")
        if result.get("side_effects") != {"network_calls": 0, "write_calls": 0, "actions": []}:
            case_errors.append("side_effect_contract")
        if case_errors:
            errors.extend(f"{name}:{item}" for item in case_errors)
        else:
            passed += 1
    return passed


def _check_redaction(data: dict[str, Any], recruitment: object, errors: list[str]) -> int:
    redact = getattr(recruitment, "redact_discovery_query", None)
    if not callable(redact):
        errors.append("missing_callable:redact_discovery_query")
        return 0
    passed = 0
    github_classic = "gh" + "p_" + "A" * 36
    github_fine = "github" + "_pat_" + "A" * 24
    gitlab_token = "gl" + "pat-" + "A" * 24
    boundary_cases = [
        {
            "name": "builtin_sk_proj_fullwidth_colon",
            "query": "Need reusable reports token：sk-proj-0123456789abcdef source：private.py",
            "must_not_contain": ["sk-proj-0123456789abcdef", "private.py"],
            "must_contain": ["Need reusable reports"],
        },
        {
            "name": "builtin_windows_path_with_spaces",
            "query": 'Need indexing for "C:\\Users\\alice\\Private Repo\\secret file.txt"',
            "must_not_contain": ["C:\\Users\\alice", "Private Repo", "secret file.txt"],
            "must_contain": ["Need indexing"],
        },
        {
            "name": "builtin_unquoted_fullwidth_label_path",
            "query": "Need metadata 路径：C:\\Users\\alice\\Private Repo\\secret.txt 日志：password：hunter2",
            "must_not_contain": ["C:\\Users\\alice", "Private Repo", "hunter2"],
            "must_contain": ["Need metadata"],
        },
        {
            "name": "builtin_unquoted_windows_path_with_spaces",
            "query": "Need metadata path C:\\Users\\alice\\Secret Folder\\x.txt for reusable reports",
            "must_not_contain": ["C:\\Users\\alice", "Secret Folder", "Folder\\x.txt", "x.txt"],
            "must_contain": ["Need metadata", "for reusable reports"],
        },
        {
            "name": "builtin_identity_repository_unlabelled_tokens",
            "query": (
                "Need metadata username: alice 用户名：张三 "
                "private_repository: acme/hidden-repo 私有仓库：公司/隐秘库 "
                f"{github_classic} {github_fine} {gitlab_token}"
            ),
            "must_not_contain": [
                "alice",
                "张三",
                "acme/hidden-repo",
                "公司/隐秘库",
                github_classic,
                github_fine,
                gitlab_token,
            ],
            "must_contain": ["Need metadata"],
        },
    ]
    for case in [*data.get("redaction_cases", []), *boundary_cases]:
        name = str(case.get("name", "unnamed"))
        try:
            output = redact(case["query"], case.get("redaction_terms", []))
        except Exception as exc:
            errors.append(f"{name}:redaction_error:{type(exc).__name__}:{exc}")
            continue
        case_errors = [token for token in case.get("must_not_contain", []) if token.casefold() in output.casefold()]
        case_errors.extend(
            f"missing:{token}" for token in case.get("must_contain", []) if token.casefold() not in output.casefold()
        )
        if case_errors:
            errors.extend(f"{name}:redaction_leak:{item}" for item in case_errors)
        else:
            passed += 1
    return passed


def _check_evaluator_query_boundary(data: dict[str, Any], recruitment: object, errors: list[str]) -> int:
    evaluate = getattr(recruitment, "evaluate_recruitment", None)
    if not callable(evaluate):
        errors.append("missing_callable:evaluate_recruitment_for_query_boundary")
        return 0
    github_classic = "gh" + "p_" + "A" * 36
    secret_query = (
        'Need report automation token：sk-proj-evaluator-secret '
        'path："C:\\Users\\alice\\Private Repo\\secret file.txt" '
        'username: alice 用户名：张三 private_repository: acme/hidden-repo '
        f'私有仓库：公司/隐秘库 {github_classic}'
    )
    payload = copy.deepcopy(data["defaults"])
    payload["capability_need"] = secret_query
    try:
        result = evaluate(payload)
    except Exception as exc:
        errors.append(f"evaluator_query_boundary_error:{type(exc).__name__}:{exc}")
        return 0
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
    leaked = [
        token
        for token in (
            "sk-proj-evaluator-secret",
            "C:\\Users\\alice",
            "Private Repo",
            "secret file.txt",
            "alice",
            "张三",
            "acme/hidden-repo",
            "公司/隐秘库",
            github_classic,
        )
        if token.casefold() in serialized.casefold()
    ]
    if leaked:
        errors.append("evaluator_query_boundary_leak:" + ",".join(leaked))
        return 0
    return 1


def _changed_value(field: str, value: object) -> object:
    if field == "allowed_actions":
        return ["CREATE", "INSTALL"]
    if field == "candidate_snapshot" and isinstance(value, Mapping):
        changed = copy.deepcopy(dict(value))
        changed["name"] = f"changed-{changed.get('name', 'candidate')}"
        return changed
    return f"changed-{value}"


def _check_consent(data: dict[str, Any], recruitment: object, errors: list[str]) -> dict[str, int]:
    validate = getattr(recruitment, "validate_action_consent", None)
    normalize = getattr(recruitment, "normalize_candidate_snapshot", None)
    digest = getattr(recruitment, "candidate_snapshot_digest", None)
    missing_callables = [
        name
        for name, value in (
            ("validate_action_consent", validate),
            ("normalize_candidate_snapshot", normalize),
            ("candidate_snapshot_digest", digest),
        )
        if not callable(value)
    ]
    if missing_callables:
        errors.extend(f"missing_callable:{name}" for name in missing_callables)
        return {
            "valid": 0,
            "mutations_rejected": 0,
            "cross_actions_rejected": 0,
            "external_provenance_rejected": 0,
            "actual_candidate_rejected": 0,
            "actual_security_mutations_rejected": 0,
            "execution_recheck_passed": 0,
        }
    fixture = data["consent_binding"]
    request = copy.deepcopy(fixture["request"])
    consent = copy.deepcopy(fixture["consent"])
    actual_candidate = {
        "kind": request["kind"],
        "name": request["name"],
        "source": "local_creation",
        "purpose": request["purpose"],
        "destination": request["destination"],
        "requires_paid_action": False,
        "requires_login": False,
        "requires_private_upload": False,
        "trusted": False,
        "verified": False,
    }
    candidate_snapshot = normalize(actual_candidate)
    candidate_digest = digest(candidate_snapshot)
    binding_additions = {
        "decree_id": "DECREE-C1-QUALITY",
        "turn_id": "TURN-C1-001",
        "candidate_snapshot": candidate_snapshot,
        "candidate_digest": candidate_digest,
        "discovery_query": "reusable structured capability",
        "discovery_status": "PUBLIC_DISCOVERY_NO_QUALIFIED_CANDIDATE",
    }
    request.update(copy.deepcopy(binding_additions))
    consent.update(copy.deepcopy(binding_additions))
    try:
        valid = validate(request, consent, actual_candidate)
    except TypeError as exc:
        errors.append(f"consent_actual_candidate_binding_missing:{exc}")
        return {
            "valid": 0,
            "mutations_rejected": 0,
            "cross_actions_rejected": 0,
            "external_provenance_rejected": 0,
            "actual_candidate_rejected": 0,
            "actual_security_mutations_rejected": 0,
            "execution_recheck_passed": 0,
        }
    valid_count = int(valid.get("status") == "VALID")
    if not valid_count:
        errors.append(f"consent_valid_base:{valid!r}")
    try:
        execution_recheck_passed = int(_deep_get(valid, "execution_recheck.status") == "PASSED") if valid_count else 0
    except KeyError:
        execution_recheck_passed = 0
    if not execution_recheck_passed:
        errors.append(f"consent_execution_recheck_missing:{valid!r}")

    normalized_request = copy.deepcopy(request)
    normalized_request["candidate_snapshot"] = {
        key: f"  {value}  " if isinstance(value, str) else copy.deepcopy(value)
        for key, value in reversed(list(candidate_snapshot.items()))
    }
    normalized = validate(normalized_request, consent, actual_candidate)
    if normalized.get("status") != "VALID":
        errors.append(f"consent_normalized_snapshot_not_accepted:{normalized!r}")

    mutations_rejected = 0
    mutation_fields = [
        "action",
        "kind",
        "name",
        "purpose",
        "destination",
        "allowed_actions",
        "candidate_snapshot",
        "candidate_digest",
        "discovery_query",
        "discovery_status",
        "decree_id",
        "turn_id",
    ]
    for field in mutation_fields:
        changed = copy.deepcopy(request)
        changed[field] = _changed_value(field, changed[field])
        result = validate(changed, consent, actual_candidate)
        if result.get("status") != "INVALID":
            errors.append(f"consent_mutation_not_rejected:{field}:{result!r}")
        else:
            mutations_rejected += 1
    cross_actions_rejected = 0
    for action in fixture["create_does_not_imply"]:
        changed = copy.deepcopy(request)
        changed["action"] = action
        changed["allowed_actions"] = [action]
        result = validate(changed, consent, actual_candidate)
        if result.get("status") != "INVALID":
            errors.append(f"create_implied_forbidden_action:{action}:{result!r}")
        else:
            cross_actions_rejected += 1
    stale = copy.deepcopy(consent)
    stale["current_turn"] = False
    if validate(request, stale, actual_candidate).get("status") != "INVALID":
        errors.append("stale_consent_not_rejected")
    vague = copy.deepcopy(consent)
    vague["explicit"] = False
    if validate(request, vague, actual_candidate).get("status") != "INVALID":
        errors.append("non_explicit_consent_not_rejected")

    changed_actual = copy.deepcopy(actual_candidate)
    changed_actual["name"] = "different-actual-candidate"
    actual_candidate_rejected = int(validate(request, consent, changed_actual).get("status") == "INVALID")
    if not actual_candidate_rejected:
        errors.append("consent_not_bound_to_actual_candidate")

    actual_security_mutations_rejected = 0
    actual_mutation_fields = fixture.get("actual_candidate_mutation_fields", [])
    if tuple(actual_mutation_fields) != REQUIRED_ACTUAL_CANDIDATE_MUTATION_FIELDS:
        errors.append("consent_actual_candidate_mutation_fixture_drift")
    for field in REQUIRED_ACTUAL_CANDIDATE_MUTATION_FIELDS:
        if field not in candidate_snapshot:
            errors.append(f"consent_security_field_not_in_snapshot:{field}")
            continue
        changed_actual = copy.deepcopy(actual_candidate)
        changed_actual[field] = not bool(changed_actual[field])
        changed_digest = digest(normalize(changed_actual))
        result = validate(request, consent, changed_actual)
        if changed_digest == candidate_digest or result.get("status") != "INVALID":
            errors.append(f"consent_security_mutation_not_bound:{field}:{result!r}")
        else:
            actual_security_mutations_rejected += 1

    external = data["action_bindings"]["external_install"]
    external_request = copy.deepcopy(external["request"])
    external_consent = copy.deepcopy(external["consent"])
    external_candidate = copy.deepcopy(data["candidate_templates"]["public_skill_good"])
    external_binding = {
        "decree_id": "DECREE-C1-QUALITY",
        "turn_id": "TURN-C1-002",
        "candidate_snapshot": normalize(external_candidate),
        "discovery_query": "reusable structured capability",
        "discovery_status": "PUBLIC_DISCOVERY_FOUND",
    }
    external_binding["candidate_digest"] = digest(external_binding["candidate_snapshot"])
    external_request.update(copy.deepcopy(external_binding))
    external_consent.update(copy.deepcopy(external_binding))
    if validate(external_request, external_consent, external_candidate).get("status") != "VALID":
        errors.append("external_consent_valid_base")
    external_provenance_rejected = 0
    for field in external["required_provenance_fields"]:
        changed_request = copy.deepcopy(external_request)
        changed_consent = copy.deepcopy(external_consent)
        changed_request.pop(field, None)
        changed_consent.pop(field, None)
        result = validate(changed_request, changed_consent, external_candidate)
        if result.get("status") != "INVALID":
            errors.append(f"external_consent_missing_provenance_not_rejected:{field}:{result!r}")
        else:
            external_provenance_rejected += 1
    return {
        "valid": valid_count,
        "mutations_rejected": mutations_rejected,
        "cross_actions_rejected": cross_actions_rejected,
        "external_provenance_rejected": external_provenance_rejected,
        "actual_candidate_rejected": actual_candidate_rejected,
        "actual_security_mutations_rejected": actual_security_mutations_rejected,
        "execution_recheck_passed": execution_recheck_passed,
    }


def _check_c1_red_mutations(data: dict[str, Any], recruitment: object, errors: list[str]) -> dict[str, int]:
    validate = getattr(recruitment, "validate_action_consent", None)
    evaluate = getattr(recruitment, "evaluate_recruitment", None)
    normalize = getattr(recruitment, "normalize_candidate_snapshot", None)
    digest = getattr(recruitment, "candidate_snapshot_digest", None)
    if not all(callable(item) for item in (validate, evaluate, normalize, digest)):
        errors.append("c1_red_missing_recruitment_surfaces")
        return {"cases": C1_RED_CASE_COUNT, "passed": 0, "stale_actions_blocked": 0}

    external = data["action_bindings"]["external_install"]
    base_request = copy.deepcopy(external["request"])
    base_consent = copy.deepcopy(external["consent"])
    actual_candidate = copy.deepcopy(data["candidate_templates"]["public_skill_good"])
    snapshot = normalize(actual_candidate)
    additions = {
        "candidate_snapshot": snapshot,
        "candidate_digest": digest(snapshot),
        "decree_id": "DECREE-C1-RED",
        "turn_id": "TURN-C1-RED",
        "discovery_query": "reusable structured capability",
        "discovery_status": "PUBLIC_DISCOVERY_FOUND",
    }
    base_request.update(copy.deepcopy(additions))
    base_consent.update(copy.deepcopy(additions))
    passed = 0
    stale_actions_blocked = 0
    forward_actions = {"CREATE", "INSTALL", "MODIFY", "ENABLE", "FORWARD_BOUND_ACTION_TO_EXECUTOR"}

    for case in data.get("c1_red_mutation_cases", []):
        case_id = str(case.get("id") or "missing-id")
        mode = case.get("mode")
        if mode in {"request_mutation", "consent_mutation"}:
            request = copy.deepcopy(base_request)
            consent = copy.deepcopy(base_consent)
            field = str(case.get("field") or "")
            target = request if mode == "request_mutation" else consent
            target[field] = _changed_value(field, target.get(field))
            result = validate(request, consent, actual_candidate)
            if result.get("status") != "INVALID":
                errors.append(f"c1_red_binding_mutation_not_rejected:{case_id}:{field}:{result.get('status')}")
            else:
                passed += 1
            continue

        if mode == "stale_actions":
            case_ok = True
            for action in case.get("actions", []):
                action = str(action).upper()
                request = copy.deepcopy(base_request)
                consent = copy.deepcopy(base_consent)
                request["action"] = action
                consent["action"] = action
                request["allowed_actions"] = [action]
                consent["allowed_actions"] = [action]
                consent["current_turn"] = False
                validation = validate(request, consent, actual_candidate)
                context = copy.deepcopy(data["defaults"])
                context.update(
                    {
                        "authority": "autonomous",
                        "network_attempted": True,
                        "network_status": "success",
                        "searched_kinds": ["skill"],
                        "discovered_candidates": [actual_candidate],
                        "action_request": request,
                        "action_candidate": actual_candidate,
                        "consent": consent,
                    }
                )
                decision = evaluate(context)
                next_action = str(_deep_get(decision, "next_action.action"))
                if validation.get("status") != "INVALID" or next_action in forward_actions:
                    case_ok = False
                    errors.append(
                        f"c1_red_stale_consent_action_not_blocked:{case_id}:{action}:"
                        f"validation={validation.get('status')}:next={next_action}"
                    )
                else:
                    stale_actions_blocked += 1
            if case_ok:
                passed += 1
    return {"cases": C1_RED_CASE_COUNT, "passed": passed, "stale_actions_blocked": stale_actions_blocked}


def _check_malformed_inputs(data: dict[str, Any], recruitment: object, errors: list[str]) -> int:
    evaluate = getattr(recruitment, "evaluate_recruitment", None)
    if not callable(evaluate):
        errors.append("missing_callable:evaluate_recruitment_for_malformed_inputs")
        return 0
    cases = [
        ("capability_need", [], "INVALID_CAPABILITY_NEED_TYPE"),
        ("authority", 7, "INVALID_AUTHORITY_TYPE"),
        ("authority", "root", "INVALID_AUTHORITY_VALUE"),
        ("network_attempted", "false", "INVALID_NETWORK_ATTEMPTED_TYPE"),
        ("network_status", ["success"], "INVALID_NETWORK_STATUS_TYPE"),
        ("network_status", "mystery", "INVALID_NETWORK_STATUS_VALUE"),
        ("stable_steps", "four", "INVALID_STABLE_STEPS_TYPE"),
        ("stable_steps", -1, "INVALID_STABLE_STEPS_VALUE"),
        ("explicit_no_network", "false", "INVALID_EXPLICIT_NO_NETWORK_TYPE"),
        ("network_discovery_approved", "false", "INVALID_NETWORK_APPROVAL_TYPE"),
        ("stable_io", "false", "INVALID_STABLE_IO_TYPE"),
        ("stable_verification", "false", "INVALID_STABLE_VERIFICATION_TYPE"),
        ("creation_benefit", "false", "INVALID_CREATION_BENEFIT_TYPE"),
        ("existing_combination_sufficient", "false", "INVALID_EXISTING_COMBINATION_TYPE"),
        ("contains_secret_or_private_content", "false", "INVALID_PRIVATE_CONTENT_TYPE"),
        ("user_declined_creation", "false", "INVALID_USER_DECLINED_TYPE"),
        ("proposal_asked_in_decree", "false", "INVALID_PROPOSAL_ASKED_TYPE"),
        ("searched_kinds", "skill", "INVALID_SEARCHED_KINDS_TYPE"),
        ("searched_kinds", ["skill", "skill"], "DUPLICATE_SEARCHED_KIND"),
        ("searched_kinds", ["cli"], "INVALID_SEARCHED_KIND:cli"),
        ("local_candidates", {}, "INVALID_LOCAL_CANDIDATES_TYPE"),
        ("local_candidates", ["skill"], "INVALID_LOCAL_CANDIDATE_TYPE:0"),
        ("discovered_candidates", "skill", "INVALID_DISCOVERED_CANDIDATES_TYPE"),
        ("redaction_terms", "alice", "INVALID_REDACTION_TERMS_TYPE"),
        ("task_complexity", 1, "INVALID_TASK_COMPLEXITY_TYPE"),
        ("reuse_value", ["recurring"], "INVALID_REUSE_VALUE_TYPE"),
    ]
    passed = 0
    for field, malformed, expected_code in cases:
        payload = copy.deepcopy(data["defaults"])
        payload[field] = malformed
        try:
            result = evaluate(payload)
        except Exception as exc:
            errors.append(f"malformed_input_unstable_exception:{field}:{type(exc).__name__}:{exc}")
            continue
        validation = result.get("input_validation", {}) if isinstance(result, dict) else {}
        validation_errors = validation.get("errors", []) if isinstance(validation, dict) else []
        if (
            validation.get("status") != "INVALID"
            or expected_code not in validation_errors
            or _deep_get(result, "next_action.action") != "BLOCKED_BY_AUTHORITY"
        ):
            errors.append(f"malformed_input_not_fail_closed:{field}:{malformed!r}:{result!r}")
        else:
            passed += 1
    return passed


def _check_reviewer_candidate_contract(data: dict[str, Any], recruitment: object, errors: list[str]) -> int:
    evaluate = getattr(recruitment, "evaluate_recruitment", None)
    if not callable(evaluate):
        errors.append("missing_callable:evaluate_recruitment_for_reviewer_contract")
        return 0

    passed = 0

    def evaluate_candidate(candidate: dict[str, Any], searched_kinds: list[str], *, local: bool = False):
        payload = copy.deepcopy(data["defaults"])
        payload.update(
            {
                "network_attempted": not local,
                "network_status": "not_run" if local else "success",
                "searched_kinds": searched_kinds,
                "local_candidates": [candidate] if local else [],
                "discovered_candidates": [] if local else [candidate],
            }
        )
        return evaluate(payload)

    public_good = copy.deepcopy(data["candidate_templates"]["public_skill_good"])
    kind_mismatch = evaluate_candidate(public_good, ["plugin"])
    mismatch_reasons = kind_mismatch.get("reason_codes", [])
    if (
        "CANDIDATE_KIND_NOT_SEARCHED" not in mismatch_reasons
        or _deep_get(kind_mismatch, "candidate_fit.qualified_external_count") != 0
        or _deep_get(kind_mismatch, "candidate_fit.hard_stop_count") != 1
    ):
        errors.append(f"reviewer_candidate_kind_not_searched_accepted:{kind_mismatch!r}")
    else:
        passed += 1

    local_good = copy.deepcopy(data["candidate_templates"]["local_good_skill"])
    local_mismatch = evaluate_candidate(local_good, ["plugin"], local=True)
    if (
        "CANDIDATE_KIND_NOT_SEARCHED" not in local_mismatch.get("reason_codes", [])
        or _deep_get(local_mismatch, "candidate_fit.dispatchable_count") != 0
        or _deep_get(local_mismatch, "candidate_fit.hard_stop_count") != 1
    ):
        errors.append(f"reviewer_local_candidate_kind_not_searched_accepted:{local_mismatch!r}")
    else:
        passed += 1

    unknown_mutations: list[tuple[str, object]] = [
        ("publisher", "unknown"),
        ("license", "unknown"),
        ("permissions", ["unknown"]),
        ("install_behavior", "unknown"),
        ("network_data_behavior", "unknown"),
        ("maintenance_signal", "unknown"),
        ("risk", "unknown"),
    ]
    for field, value in unknown_mutations:
        candidate = copy.deepcopy(public_good)
        candidate[field] = value
        result = evaluate_candidate(candidate, ["skill"])
        expected = f"PROVENANCE_VALUE_UNKNOWN:{field}"
        if (
            expected not in result.get("reason_codes", [])
            or _deep_get(result, "candidate_fit.qualified_external_count") != 0
            or _deep_get(result, "candidate_fit.hard_stop_count") != 1
        ):
            errors.append(f"reviewer_unknown_provenance_accepted:{field}:{result!r}")
        else:
            passed += 1

    type_mutations = [
        ("requires_paid_action", "false"),
        ("requires_login", 0),
        ("requires_private_upload", "no"),
        ("trusted", "true"),
        ("verified", 1),
    ]
    for field, value in type_mutations:
        candidate = copy.deepcopy(public_good)
        candidate[field] = value
        result = evaluate_candidate(candidate, ["skill"])
        expected = f"PROVENANCE_FIELD_TYPE_INVALID:{field}"
        if expected not in result.get("reason_codes", []) or _deep_get(result, "candidate_fit.hard_stop_count") != 1:
            errors.append(f"reviewer_boolean_type_accepted:{field}:{result!r}")
        else:
            passed += 1

    conflict_mutations = [
        ("paid", {"install_behavior": "paid_subscription", "requires_paid_action": False}, "CANDIDATE_PAID_STATE_CONFLICT"),
        ("login", {"network_data_behavior": "authenticated_cloud", "requires_login": False}, "CANDIDATE_LOGIN_STATE_CONFLICT"),
        ("private_upload", {"permissions": ["upload_content"], "requires_private_upload": False}, "CANDIDATE_PRIVATE_UPLOAD_STATE_CONFLICT"),
    ]
    for name, updates, expected in conflict_mutations:
        candidate = copy.deepcopy(public_good)
        candidate.update(updates)
        result = evaluate_candidate(candidate, ["skill"])
        if expected not in result.get("reason_codes", []) or _deep_get(result, "candidate_fit.hard_stop_count") != 1:
            errors.append(f"reviewer_declared_state_conflict_accepted:{name}:{result!r}")
        else:
            passed += 1
    return passed


def _check_external_provenance(data: dict[str, Any], recruitment: object, errors: list[str]) -> int:
    evaluate = getattr(recruitment, "evaluate_recruitment", None)
    if not callable(evaluate):
        errors.append("missing_callable:evaluate_recruitment_for_provenance")
        return 0
    mutations = [
        ("http_url", {"url": "http://example.invalid/skill"}, "INSECURE_PROVENANCE_URL"),
        ("unpinned_ref", {"immutable_ref": "release-candidate"}, "UNPINNED_OR_MUTABLE_REF"),
        ("zero_hash", {"content_hash": "0" * 64}, "MISSING_OR_INVALID_CONTENT_HASH"),
        ("wrong_permissions_type", {"permissions": "read_workspace"}, "PROVENANCE_FIELD_TYPE_INVALID:permissions"),
        ("self_attested_kind", {"kind": "executable"}, "UNSUPPORTED_CANDIDATE_KIND"),
    ]
    passed = 0
    for name, updates, expected_reason in mutations:
        candidate = copy.deepcopy(data["candidate_templates"]["public_skill_good"])
        candidate.update(updates)
        payload = copy.deepcopy(data["defaults"])
        payload.update(
            {
                "network_attempted": True,
                "network_status": "success",
                "searched_kinds": [
                    str(candidate.get("kind") or "skill")
                    if str(candidate.get("kind") or "").casefold() in {"skill", "plugin", "mcp"}
                    else "skill"
                ],
                "discovered_candidates": [candidate],
            }
        )
        try:
            result = evaluate(payload)
        except Exception as exc:
            errors.append(f"provenance_case_exception:{name}:{type(exc).__name__}:{exc}")
            continue
        reasons = result.get("reason_codes", []) if isinstance(result, dict) else []
        qualified = _deep_get(result, "candidate_fit.qualified_external_count")
        hard_stops = _deep_get(result, "candidate_fit.hard_stop_count")
        if expected_reason not in reasons or qualified != 0 or hard_stops != 1:
            errors.append(f"provenance_case_not_rejected:{name}:{result!r}")
        else:
            passed += 1
    local_mutations = [
        ("local_mutable_ref", {"immutable_ref": "release-candidate", "content_hash": "a" * 64}, "UNPINNED_OR_MUTABLE_REF"),
        ("local_unknown_hash", {"immutable_ref": "v1.2.3", "content_hash": "unknown"}, "MISSING_OR_INVALID_CONTENT_HASH"),
        ("local_missing_hash", {"immutable_ref": "v1.2.3", "content_hash": None}, "MISSING_OR_INVALID_CONTENT_HASH"),
        ("local_unknown_source", {"source": "unknown"}, "LOCAL_PROVENANCE_SOURCE_MISSING_OR_UNKNOWN"),
        ("local_kind_mismatch", {"immutable_ref": "v1.2.3", "content_hash": "a" * 64, "kind": "plugin"}, "CANDIDATE_KIND_NOT_SEARCHED"),
    ]
    for name, updates, expected_reason in local_mutations:
        candidate = copy.deepcopy(data["candidate_templates"]["local_good_skill"])
        candidate.update(updates)
        for field in [key for key, value in updates.items() if value is None]:
            candidate.pop(field, None)
        payload = copy.deepcopy(data["defaults"])
        payload.update({"searched_kinds": ["skill"], "local_candidates": [candidate]})
        result = evaluate(payload)
        reasons = result.get("reason_codes", [])
        if (
            expected_reason not in reasons
            or _deep_get(result, "candidate_fit.dispatchable_count") != 0
            or _deep_get(result, "next_action.action") == "DISPATCH_LOCAL"
        ):
            errors.append(f"local_provenance_case_not_rejected:{name}:{result!r}")
        else:
            passed += 1
    return passed


def _check_gate_contract(gate: object, errors: list[str]) -> dict[str, object]:
    builder = getattr(gate, "build_recruitment_next_action", None)
    exit_code = getattr(gate, "dispatch_exit_code", None)
    main = getattr(gate, "main", None)
    if not callable(builder):
        errors.append("gate_missing_callable:build_recruitment_next_action")
    if not callable(exit_code):
        errors.append("gate_missing_callable:dispatch_exit_code")
    if not callable(main):
        errors.append("gate_missing_callable:main")
    if not callable(builder) or not callable(exit_code) or not callable(main):
        return {"ok": False}

    partial = {
        "capability_index_skill_gate": "PARTIAL",
        "candidate_count": 0,
        "dispatchable_candidate_count": 0,
        "candidates": [],
        "prerequisites": {},
    }
    action = builder(partial, authority="autonomous", explicit_no_network=False)
    if action.get("schema") != "court.capability_recruitment.v1":
        errors.append("gate_recruitment_schema")
    if action.get("discovery_status") != "UNKNOWN_NOT_SEARCHED":
        errors.append(f"gate_unknown_not_searched:{action!r}")
    if action.get("action") != "DISCOVER_PUBLIC_METADATA":
        errors.append(f"gate_next_action:{action!r}")
    if exit_code(partial, require_dispatchable=False) != 0:
        errors.append("gate_partial_default_exit")
    if exit_code(partial, require_dispatchable=True) == 0:
        errors.append("gate_partial_require_dispatchable_exit")

    passed_result = {
        "capability_index_skill_gate": "PASSED",
        "candidate_count": 1,
        "dispatchable_candidate_count": 1,
        "candidates": [
            {
                "scope": "local",
                "dispatchable": True,
                "verification_status": "VERIFIED_LOCAL",
                "trusted": True,
                "fit_status": "STRONG_LOCAL_FIT",
            }
        ],
        "prerequisites": {},
    }
    if exit_code(passed_result, require_dispatchable=True) != 0:
        errors.append("gate_passed_require_dispatchable_exit")
    unverified = dict(passed_result)
    unverified["dispatchable_candidate_count"] = 1
    unverified["candidates"] = [
        {
            "dispatchable": True,
            "verification_status": "UNVERIFIED",
            "trusted": True,
            "fit_status": "STRONG_LOCAL_FIT",
        }
    ]
    if exit_code(unverified, require_dispatchable=True) == 0:
        errors.append("gate_unverified_require_dispatchable_exit")

    select_candidates = getattr(gate, "select_candidates", None)
    original_load_records = getattr(gate, "load_records", None)
    if not callable(select_candidates) or not callable(original_load_records):
        errors.append("gate_missing_lexical_fit_surface")
    else:
        weak_record = {
            "kind": "skill",
            "name": "generic-helper",
            "source": "codex_skills",
            "description": "A generic report helper.",
            "path": str(ROOT),
            "court_units": ["Libu-HR"],
            "primary_fit": ["generic"],
        }
        self_attested_record = {
            **weak_record,
            "name": "specialized-report-validation",
            "description": "Specialized report validation capability.",
            "path": str(ROOT / "scripts" / "court_capability_recruitment.py"),
        }
        mismatched_name_record = {
            **self_attested_record,
            "path": str(ROOT / "SKILL.md"),
        }
        valid_skill_record = {
            **weak_record,
            "name": "decretum-matrix",
            "description": "Dercretum-Matrix court capability router.",
            "path": str(ROOT / "SKILL.md"),
            "primary_fit": ["court", "capability", "router"],
        }
        root_external_skill_record = copy.deepcopy(valid_skill_record)
        python_script_path = ROOT / "scripts" / "court_capability_recruitment.py"
        python_cli_record = {
            "kind": "cli",
            "name": "court_capability_recruitment",
            "source": "path",
            "description": "Court capability recruitment Python module.",
            "path": str(python_script_path),
            "relative_path": "cli:court_capability_recruitment",
            "court_units": ["Libu-HR"],
            "primary_fit": ["court", "capability", "recruitment"],
        }
        executable_path = Path(sys.executable).resolve()
        executable_name = executable_path.stem
        valid_cli_record = {
            "kind": "cli",
            "name": executable_name,
            "source": "path",
            "description": "Verified Python runtime executable.",
            "path": str(executable_path),
            "relative_path": f"cli:{executable_name.casefold()}",
            "court_units": ["Hubu-Finance"],
            "primary_fit": [executable_name, "runtime", "executable"],
        }
        skill_roots = {"codex_skills": [ROOT]}
        try:
            setattr(gate, "load_records", lambda _path: [weak_record])
            weak = select_candidates(
                "specialized report validation",
                1,
                Path("unused.json"),
                source_roots=skill_roots,
                executable_inventory={},
            )
            if len(weak) != 1:
                errors.append(f"gate_weak_lexical_candidate_missing:{weak!r}")
            elif weak[0].get("dispatchable") is not False or weak[0].get("fit_status") != "WEAK_LEXICAL_MATCH":
                errors.append(f"gate_weak_lexical_candidate_dispatchable:{weak[0]!r}")

            for label, record in (
                ("self_attested_kind", self_attested_record),
                ("mismatched_skill_name", mismatched_name_record),
            ):
                setattr(gate, "load_records", lambda _path, selected=record: [selected])
                rejected = select_candidates(
                    "specialized report validation",
                    1,
                    Path("unused.json"),
                    source_roots=skill_roots,
                    executable_inventory={},
                )
                if len(rejected) != 1:
                    errors.append(f"gate_{label}_candidate_missing:{rejected!r}")
                elif (
                    rejected[0].get("dispatchable") is not False
                    or rejected[0].get("verification_status") == "VERIFIED_LOCAL"
                    or rejected[0].get("kind_evidence_status") != "VERIFIED"
                    and rejected[0].get("kind_evidence_status") != "FAILED"
                ):
                    errors.append(f"gate_{label}_incorrectly_verified:{rejected[0]!r}")

            setattr(gate, "load_records", lambda _path: [valid_skill_record])
            verified = select_candidates(
                "court capability router",
                1,
                Path("unused.json"),
                source_roots=skill_roots,
                executable_inventory={},
            )
            if len(verified) != 1:
                errors.append(f"gate_verified_skill_candidate_missing:{verified!r}")
            elif (
                verified[0].get("dispatchable") is not True
                or verified[0].get("verification_status") != "VERIFIED_LOCAL"
                or verified[0].get("kind_evidence_status") != "VERIFIED"
            ):
                errors.append(f"gate_verified_skill_candidate_not_dispatchable:{verified[0]!r}")

            setattr(gate, "load_records", lambda _path: [root_external_skill_record])
            root_external = select_candidates(
                "court capability router",
                1,
                Path("unused.json"),
                source_roots={"codex_skills": [ROOT / "references"]},
                executable_inventory={},
            )
            if (
                len(root_external) != 1
                or root_external[0].get("dispatchable") is not False
                or "DECLARED_SOURCE_ROOT_MISMATCH" not in root_external[0].get("verification_evidence", [])
            ):
                errors.append(f"gate_root_external_skill_verified:{root_external!r}")

            setattr(gate, "load_records", lambda _path: [python_cli_record])
            python_cli = select_candidates(
                "court capability recruitment",
                1,
                Path("unused.json"),
                source_roots={"path": [python_script_path.parent]},
                executable_inventory={"court_capability_recruitment": [python_script_path]},
            )
            if (
                len(python_cli) != 1
                or python_cli[0].get("dispatchable") is not False
                or "CLI_EXECUTABLE_TYPE_INVALID" not in python_cli[0].get("verification_evidence", [])
            ):
                errors.append(f"gate_ordinary_python_file_verified_as_cli:{python_cli!r}")

            setattr(gate, "load_records", lambda _path: [valid_cli_record])
            valid_cli = select_candidates(
                f"{executable_name} runtime executable",
                1,
                Path("unused.json"),
                source_roots={"path": [executable_path.parent]},
                executable_inventory={executable_name.casefold(): [executable_path]},
            )
            if (
                len(valid_cli) != 1
                or valid_cli[0].get("dispatchable") is not True
                or valid_cli[0].get("verification_status") != "VERIFIED_LOCAL"
                or valid_cli[0].get("source_root_verified") is not True
                or valid_cli[0].get("executable_identity_verified") is not True
            ):
                errors.append(f"gate_inventory_executable_not_verified:{valid_cli!r}")

            wrong_inventory = select_candidates(
                f"{executable_name} runtime executable",
                1,
                Path("unused.json"),
                source_roots={"path": [executable_path.parent]},
                executable_inventory={executable_name.casefold(): [python_script_path]},
            )
            if (
                len(wrong_inventory) != 1
                or wrong_inventory[0].get("dispatchable") is not False
                or "CLI_EXECUTABLE_IDENTITY_MISMATCH" not in wrong_inventory[0].get("verification_evidence", [])
            ):
                errors.append(f"gate_uninventoried_executable_verified:{wrong_inventory!r}")
        except Exception as exc:
            errors.append(f"gate_structural_verification_contract_exception:{type(exc).__name__}:{exc}")
        finally:
            setattr(gate, "load_records", original_load_records)

    original_evaluate = getattr(gate, "evaluate")
    original_argv = sys.argv[:]
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        setattr(gate, "evaluate", lambda _query, _top: partial)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            cli_exit = main(["--query", "fixture", "--json", "--require-dispatchable"])
    except (SystemExit, TypeError) as exc:
        errors.append(f"gate_require_dispatchable_cli_contract:{type(exc).__name__}:{exc}")
        cli_exit = None
    finally:
        setattr(gate, "evaluate", original_evaluate)
        sys.argv = original_argv
    if cli_exit != 2:
        errors.append(f"gate_require_dispatchable_cli_exit:{cli_exit!r}")
    return {"ok": True, "partial_exit": exit_code(partial, True), "passed_exit": exit_code(passed_result, True)}


def _check_index_query_boundaries(gate: object, errors: list[str]) -> int:
    evaluate_index = getattr(gate, "evaluate", None)
    main = getattr(gate, "main", None)
    if not callable(evaluate_index) or not callable(main):
        errors.append("gate_missing_query_boundary_surfaces")
        return 0

    github_classic = "gh" + "p_" + "A" * 36
    secret_query = (
        'Need report validation token：sk-proj-index-secret '
        'path："C:\\Users\\alice\\Private Repo\\secret file.txt" '
        'username: alice 用户名：张三 private_repository: acme/hidden-repo '
        f'私有仓库：公司/隐秘库 {github_classic}'
    )
    forbidden = (
        "sk-proj-index-secret",
        "C:\\Users\\alice",
        "Private Repo",
        "secret file.txt",
        "alice",
        "张三",
        "acme/hidden-repo",
        "公司/隐秘库",
        github_classic,
    )
    passed = 0

    originals = {
        name: getattr(gate, name)
        for name in ("manifest_path", "catalog_path", "reference_path", "prerequisite_status", "load_records")
    }
    try:
        setattr(gate, "manifest_path", lambda: FIXTURE)
        setattr(gate, "catalog_path", lambda: ROOT / "SKILL.md")
        setattr(gate, "reference_path", lambda *_parts: ROOT / "SKILL.md")
        setattr(
            gate,
            "prerequisite_status",
            lambda manifest, catalog, shared: {
                "find_skills": True,
                "skill_creator": True,
                "quick_validate": True,
                "catalog": True,
                "manifest_path": str(manifest),
                "catalog_path": str(catalog),
                "shared_shiguan_capability_index": True,
                "shared_shiguan_capability_index_path": str(shared),
            },
        )
        setattr(gate, "load_records", lambda _path: [])
        result = evaluate_index(secret_query, 1)
    except Exception as exc:
        errors.append(f"index_query_boundary_exception:{type(exc).__name__}:{exc}")
    else:
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
        leaked = [token for token in forbidden if token.casefold() in serialized.casefold()]
        if leaked:
            errors.append("index_query_boundary_leak:" + ",".join(leaked))
        else:
            passed += 1
    finally:
        for name, value in originals.items():
            setattr(gate, name, value)

    original_evaluate = getattr(gate, "evaluate")
    for json_mode in (False, True):
        stdout = io.StringIO()
        stderr = io.StringIO()
        cli_result = {
            "capability_index_skill_gate": "PARTIAL",
            "query": secret_query,
            "candidate_count": 0,
            "dispatchable_candidate_count": 0,
            "candidates": [],
            "prerequisites": {},
        }
        try:
            setattr(gate, "evaluate", lambda _query, _top, value=cli_result: copy.deepcopy(value))
            argv = ["--query", secret_query]
            if json_mode:
                argv.append("--json")
            with redirect_stdout(stdout), redirect_stderr(stderr):
                cli_exit = main(argv)
        except Exception as exc:
            errors.append(f"cli_query_boundary_exception:{json_mode}:{type(exc).__name__}:{exc}")
            continue
        finally:
            setattr(gate, "evaluate", original_evaluate)
        output = stdout.getvalue() + stderr.getvalue()
        leaked = [token for token in forbidden if token.casefold() in output.casefold()]
        if cli_exit != 0:
            errors.append(f"cli_query_boundary_exit:{json_mode}:{cli_exit}")
        elif leaked:
            errors.append(f"cli_query_boundary_leak:{json_mode}:" + ",".join(leaked))
        else:
            passed += 1
    return passed


def _check_manifest_contract(gate: object, errors: list[str]) -> int:
    parse_payload = getattr(gate, "parse_manifest_payload", None)
    evaluate_index = getattr(gate, "evaluate", None)
    exit_code = getattr(gate, "dispatch_exit_code", None)
    if not callable(parse_payload):
        errors.append("gate_missing_callable:parse_manifest_payload")
    if not callable(evaluate_index) or not callable(exit_code):
        errors.append("gate_missing_manifest_surfaces")
        return 0

    passed = 0
    if callable(parse_payload):
        empty = parse_payload({"capabilities": []})
        corrupt = parse_payload({"capabilities": "not-a-list"})
        if empty.get("status") != "VALID" or empty.get("state") != "EMPTY" or empty.get("records") != []:
            errors.append(f"manifest_empty_not_distinguished:{empty!r}")
        else:
            passed += 1
        if corrupt.get("status") != "CORRUPT" or corrupt.get("state") != "CORRUPT":
            errors.append(f"manifest_corrupt_payload_not_rejected:{corrupt!r}")
        else:
            passed += 1

    originals = {
        name: getattr(gate, name)
        for name in ("manifest_path", "catalog_path", "reference_path", "prerequisite_status")
    }
    try:
        setattr(gate, "manifest_path", lambda: ROOT / "SKILL.md")
        setattr(gate, "catalog_path", lambda: ROOT / "SKILL.md")
        setattr(gate, "reference_path", lambda *_parts: ROOT / "SKILL.md")
        setattr(
            gate,
            "prerequisite_status",
            lambda manifest, catalog, shared: {
                "find_skills": True,
                "skill_creator": True,
                "quick_validate": True,
                "catalog": True,
                "manifest_path": str(manifest),
                "catalog_path": str(catalog),
                "shared_shiguan_capability_index": True,
                "shared_shiguan_capability_index_path": str(shared),
            },
        )
        result = evaluate_index("court capability", 1)
    except Exception as exc:
        errors.append(f"manifest_corrupt_evaluation_exception:{type(exc).__name__}:{exc}")
    else:
        error = result.get("error", {}) if isinstance(result, dict) else {}
        if (
            result.get("capability_index_skill_gate") != "FAILED"
            or result.get("manifest_state") != "CORRUPT"
            or error.get("code") != "manifest_corrupt"
            or exit_code(result) == 0
        ):
            errors.append(f"manifest_corrupt_not_nonzero_failure:{result!r}")
        else:
            passed += 1
    finally:
        for name, value in originals.items():
            setattr(gate, name, value)
    return passed


def evaluate() -> dict[str, object]:
    data = _load_fixture()
    errors: list[str] = []
    guard_catches = _check_side_effect_guard(errors)
    before = _tree_fingerprint(ROOT)
    counts: dict[str, object] = {"fixture_gate": _check_fixture_quality_gate(data, errors)}
    with _forbid_side_effects() as side_effect_attempts:
        recruitment, gate = _load_modules(errors)
        if recruitment is not None:
            counts["cases_passed"] = _check_cases(data, recruitment, errors)
            counts["redaction_passed"] = _check_redaction(data, recruitment, errors)
            counts["evaluator_query_boundary_passed"] = _check_evaluator_query_boundary(data, recruitment, errors)
            counts["consent"] = _check_consent(data, recruitment, errors)
            counts["c1_red"] = _check_c1_red_mutations(data, recruitment, errors)
            counts["malformed_inputs_passed"] = _check_malformed_inputs(data, recruitment, errors)
            counts["reviewer_candidate_contract_passed"] = _check_reviewer_candidate_contract(
                data, recruitment, errors
            )
            counts["external_provenance_passed"] = _check_external_provenance(data, recruitment, errors)
        if gate is not None:
            counts["gate"] = _check_gate_contract(gate, errors)
            counts["index_cli_query_boundaries_passed"] = _check_index_query_boundaries(gate, errors)
            counts["manifest_contract_passed"] = _check_manifest_contract(gate, errors)
    after = _tree_fingerprint(ROOT)
    if before != after:
        errors.append("workspace_mutated_during_check")
    if side_effect_attempts != {
        "network_calls": 0,
        "write_calls": 0,
        "subprocess_calls": 0,
        "cache_write_calls": 0,
    }:
        errors.append(f"side_effect_attempts:{side_effect_attempts!r}")
    return {
        "ok": not errors,
        "schema": data.get("decision_schema"),
        "fixture_cases": len(data.get("cases", [])),
        "counts": counts,
        "side_effect_evidence": {
            "network_calls": side_effect_attempts["network_calls"],
            "write_calls": side_effect_attempts["write_calls"],
            "subprocess_calls": side_effect_attempts["subprocess_calls"],
            "cache_write_calls": side_effect_attempts["cache_write_calls"],
            "guard_catches": guard_catches,
            "target_imports_guarded": True,
            "workspace_fingerprint_unchanged": before == after,
        },
        "errors": errors,
    }


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
