"""Lazy command registry for the Decretum Matrix unified CLI."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import importlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "references" / "manifests" / "cli-command-surface.v1.json"
RESULT_SCHEMA = "decretum.cli.result.v1"
GROUP_ORDER = ("court", "office", "shiguan", "supercc", "install", "release", "check")
GROUP_DESCRIPTIONS = {
    "court": "court runtime, semantic continuity, admission, and fast-open commands",
    "office": "office lifecycle and compatibility commands",
    "shiguan": "Shiguan archive, index, and evidence commands",
    "supercc": "explicit experimental superCC CLI commands",
    "install": "installation, migration, and updater commands",
    "release": "package and release validation commands",
    "check": "focused validation commands and the aggregate check",
}
PROJECT_ROOT_GROUPS = frozenset({"check", "release"})
DAILY_HELP_COMMANDS: dict[str, tuple[str, ...]] = {
    "court": (
        "closeout-session",
        "intake-schema",
        "intake-template",
        "intake-validate",
        "open",
        "status",
    ),
    "office": ("admit", "close", "finish", "preload-ack", "report", "start"),
    "shiguan": (
        "archive-checkpoint",
        "build-shiguan-knowledge-graph",
        "grow-shiguan-tree",
        "memory-decision",
        "query-shiguan-index",
        "shiguan-git-federation",
        "tidy-shiguan-records",
    ),
    "supercc": ("supercc-squad",),
    "install": ("migrate", "rollback", "update"),
    "release": (),
    "check": ("all",),
}
COURT_RUNTIME_HINTS = (
    "admission-schema",
    "admission-template",
    "admission-validate",
    "agent-admit",
    "agent-finish",
    "agent-preload-ack",
    "agent-report",
    "agent-start",
    "capsule-template",
    "capsule-validate",
    "create",
    "events",
    "intake-schema",
    "intake-template",
    "intake-validate",
    "probe",
    "semantic",
    "semantic-context-schema",
    "semantic-context-template",
    "semantic-context-validate",
    "status",
)
OFFICE_RUNTIME_COMMANDS = ("admit", "start", "preload-ack", "report", "finish", "close")
FORBIDDEN_EAGER_MODULES = (
    "court_runtime",
    "court_model_router",
    "court_dispatch_hierarchy",
    "ensure_supercc_court",
    "install_current_agent_copy",
    "shiguan_paths",
)


class CliUsageError(ValueError):
    pass


@dataclass(frozen=True)
class CommandRecord:
    group: str
    command: str
    loader: str
    side_effect: str
    authority_requirement: str
    legacy_path: str
    handler: str
    receipt_schema: str
    compatibility_state: str


@dataclass(frozen=True)
class InvocationResult:
    returncode: int
    stdout: str
    stderr: str
    loader: str
    legacy_path: str | None
    normalization_notes: tuple[str, ...] = ()


def command_cwd(group: str, invocation_cwd: Path) -> Path:
    """Return the working directory for a command group.

    Skill/runtime commands keep the user's invocation directory so relative
    request files and user paths mean what the caller wrote. Project engineering
    commands remain code-root bound because they validate this source tree.
    """

    return ROOT if group in PROJECT_ROOT_GROUPS else invocation_cwd


def resolve_user_path(value: str, invocation_cwd: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else invocation_cwd / path


def _authority_requirement(side_effect: str) -> str:
    if side_effect == "read_only":
        return "none"
    if side_effect == "request_dependent":
        return "runtime_gate"
    return "explicit_authority"


def load_registry() -> dict[tuple[str, str], CommandRecord]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"CLI command manifest unavailable: {exc}") from exc
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("CLI command manifest entries must contain an array")
    records: dict[tuple[str, str], CommandRecord] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("CLI command manifest entry must contain an object")
        group = str(entry.get("group") or "")
        command = str(entry.get("command") or "")
        if group not in GROUP_ORDER or not command:
            continue
        legacy_path = str(entry.get("legacy_path") or "")
        handler = str(entry.get("handler") or "")
        loader = (
            "court_runtime.main"
            if legacy_path == "scripts/court_runtime.py"
            else handler
            if handler.startswith("python_module:")
            else "isolated_subprocess"
        )
        side_effect = str(entry.get("side_effect") or "request_dependent")
        record = CommandRecord(
            group=group,
            command=command,
            loader=loader,
            side_effect=side_effect,
            authority_requirement=_authority_requirement(side_effect),
            legacy_path=legacy_path,
            handler=handler,
            receipt_schema=str(entry.get("receipt_schema") or "legacy.entrypoint.result.v1"),
            compatibility_state=str(entry.get("compatibility_state") or "legacy_supported"),
        )
        key = (group, command)
        if key in records:
            raise ValueError(f"duplicate CLI command: {group} {command}")
        records[key] = record
    return records


def render_root_help() -> str:
    rows = [
        "Decretum Matrix unified CLI",
        "",
        "Usage:",
        "  decretum-matrix [--format text|json] <group> <command> [args...]",
        "  python -B scripts/court_cli.py [--format text|json] <group> <command> [args...]",
        "",
        "Groups:",
    ]
    width = max(len(group) for group in GROUP_ORDER)
    rows.extend(f"  {group.ljust(width)}  {GROUP_DESCRIPTIONS[group]}" for group in GROUP_ORDER)
    rows.extend(
        (
            "",
            "Compatibility:",
            "  Existing raw court_runtime commands remain accepted without a group.",
            "",
            "Common legacy top-level court commands:",
        )
    )
    rows.extend(f"  {command}" for command in sorted(COURT_RUNTIME_HINTS))
    return "\n".join(rows)


def render_group_help(group: str) -> str:
    if group not in GROUP_ORDER:
        raise CliUsageError(f"unknown command group: {group}")
    records = load_registry()
    available = {command for record_group, command in records if record_group == group}
    if group == "court":
        available.update(COURT_RUNTIME_HINTS)
        available.update(("closeout-session", "open"))
    elif group == "office":
        available.update(OFFICE_RUNTIME_COMMANDS)
    elif group == "install":
        available.update(("update", "migrate", "rollback"))
    elif group == "check":
        available.add("all")
    commands = {
        command
        for command in DAILY_HELP_COMMANDS.get(group, ())
        if command in available or group in {"court", "office", "install", "check"}
    }
    rows = [
        f"Decretum Matrix {group} commands",
        "",
        f"Usage: decretum-matrix {group} <command> [args...]",
        "",
        "Commands:",
    ]
    if commands:
        rows.extend(f"  {command}" for command in sorted(commands))
    else:
        rows.append("  (project-stage commands are available by explicit command or direct script)")
    if len(available) > len(commands):
        rows.extend(
            (
                "",
                "Note:",
                "  Default help shows the daily Skill surface; compatibility adapters remain callable explicitly.",
            )
        )
    return "\n".join(rows)


def _option_value(argv: Sequence[str], name: str) -> str | None:
    for index, value in enumerate(argv):
        if value == name:
            return argv[index + 1] if index + 1 < len(argv) else None
        prefix = name + "="
        if value.startswith(prefix):
            return value[len(prefix) :]
    return None


def _has_role_binding(argv: Sequence[str]) -> bool:
    roles = _option_value(argv, "--requested-roles")
    if isinstance(roles, str) and roles.strip():
        return True
    bindings = _option_value(argv, "--requested-bindings-json")
    if not isinstance(bindings, str) or not bindings.strip():
        return False
    try:
        value = json.loads(bindings)
    except json.JSONDecodeError:
        return False
    return isinstance(value, list) and any(
        isinstance(item, dict) and isinstance(item.get("role"), str) and item["role"].strip()
        for item in value
    )


def normalize_runtime_argv(argv: Sequence[str]) -> tuple[list[str], tuple[str, ...]]:
    """Translate a legacy V1 agent-type flag into V2 reserved binding metadata."""

    values = list(argv)
    if not values or values[0] != "agent-admit" or "--needs-agent-type-override" not in values:
        return values, ()
    protocol = (_option_value(values, "--protocol-mode") or "").lower()
    active = (_option_value(values, "--active-session-protocol") or "").lower()
    v2_intent = protocol == "v2" or active == "v2"
    unsupported_override = any(
        option in values
        for option in ("--needs-model-override", "--needs-reasoning-effort-override")
    )
    if not v2_intent or unsupported_override or not _has_role_binding(values):
        return values, ()
    normalized = [value for value in values if value != "--needs-agent-type-override"]
    return normalized, ("v2_reserved_agent_type_from_binding",)


def _first_non_option(argv: Sequence[str]) -> tuple[str | None, int]:
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--format":
            index += 2
            continue
        if value.startswith("--format="):
            index += 1
            continue
        if not value.startswith("-"):
            return value, index
        index += 1
    return None, -1


def _extract_format(argv: Sequence[str]) -> tuple[str, list[str]]:
    output_format = "text"
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--format":
            if index + 1 >= len(argv):
                raise CliUsageError("--format requires text or json")
            output_format = argv[index + 1]
            index += 2
            continue
        if value.startswith("--format="):
            output_format = value.split("=", 1)[1]
            index += 1
            continue
        remaining.append(value)
        index += 1
    if output_format not in {"text", "json"}:
        raise CliUsageError("--format must be text or json")
    return output_format, remaining


def _capture_runtime(
    argv: Sequence[str],
    *,
    output_format: str,
    cwd: Path,
) -> InvocationResult:
    normalized, notes = normalize_runtime_argv(argv)
    runtime_argv = list(normalized)
    if output_format == "json":
        runtime_argv = ["--format", "json", *runtime_argv]
    record = CommandRecord(
        group="court",
        command="runtime",
        loader="isolated_runtime_process",
        side_effect="request_dependent",
        authority_requirement="runtime_gate",
        legacy_path="scripts/court_runtime.py",
        handler="isolated_subprocess:scripts/court_runtime.py",
        receipt_schema="legacy.entrypoint.result.v1",
        compatibility_state="canonical_runtime_process",
    )
    captured = _capture_subprocess(record, runtime_argv, cwd=cwd)
    return InvocationResult(
        returncode=captured.returncode,
        stdout=captured.stdout,
        stderr=captured.stderr,
        loader="isolated_runtime_process",
        legacy_path=captured.legacy_path,
        normalization_notes=notes,
    )


def _legacy_runtime(argv: Sequence[str], *, cwd: Path) -> int:
    normalized, _ = normalize_runtime_argv(argv)
    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "court_runtime.py"), *normalized],
        cwd=cwd,
        check=False,
    )
    return int(completed.returncode)


def _capture_court_open(
    arguments: Sequence[str],
    output_format: str,
    *,
    cwd: Path,
) -> InvocationResult:
    values = list(arguments)
    if output_format == "json":
        values.extend(("--format", "json"))
    record = CommandRecord(
        group="court",
        command="open",
        loader="isolated_native_open_process",
        side_effect="request_dependent",
        authority_requirement="runtime_gate",
        legacy_path="scripts/court_open_fastpath.py",
        handler="isolated_subprocess:scripts/court_open_fastpath.py",
        receipt_schema="court.open.fast.v2",
        compatibility_state="canonical_native_process",
    )
    captured = _capture_subprocess(record, values, cwd=cwd)
    return InvocationResult(
        returncode=captured.returncode,
        stdout=captured.stdout,
        stderr=captured.stderr,
        loader="isolated_native_open_process",
        legacy_path=captured.legacy_path,
    )


def _subprocess_command(record: CommandRecord, arguments: Sequence[str]) -> list[str]:
    path = ROOT / record.legacy_path
    suffix = path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, "-B", str(path), *arguments]
    if suffix in {".mjs", ".js"}:
        executable = shutil.which("node")
        if not executable:
            raise CliUsageError("node is required for this command")
        return [executable, str(path), *arguments]
    if suffix == ".ps1":
        executable = shutil.which("pwsh") or shutil.which("powershell")
        if not executable:
            raise CliUsageError("PowerShell is required for this command")
        return [executable, "-NoProfile", "-File", str(path), *arguments]
    if suffix == ".sh":
        executable = shutil.which("bash")
        if not executable:
            raise CliUsageError("bash is required for this command")
        return [executable, str(path), *arguments]
    if suffix == ".cmd":
        executable = shutil.which("cmd.exe") or shutil.which("cmd")
        if not executable:
            raise CliUsageError("cmd.exe is required for this command")
        return [executable, "/d", "/c", str(path), *arguments]
    raise CliUsageError(f"unsupported compatibility adapter: {record.legacy_path}")


def _capture_subprocess(
    record: CommandRecord,
    arguments: Sequence[str],
    *,
    cwd: Path,
) -> InvocationResult:
    completed = subprocess.run(
        _subprocess_command(record, arguments),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
    )
    return InvocationResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        loader=record.loader,
        legacy_path=record.legacy_path,
    )


def _capture_python_module(
    module_name: str,
    arguments: Sequence[str],
    *,
    output_format: str,
    legacy_path: str,
) -> InvocationResult:
    module_arguments = list(arguments)
    if output_format == "json":
        module_arguments.extend(("--format", "json"))
    stdout = io.StringIO()
    stderr = io.StringIO()
    module = importlib.import_module(module_name)
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            returncode = int(module.main(module_arguments))
        except SystemExit as exc:
            returncode = int(exc.code or 0)
    return InvocationResult(
        returncode=returncode,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
        loader=f"python_module:{module_name}",
        legacy_path=legacy_path,
    )


def _json_payload(text: str) -> object:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _structured_request(
    arguments: Sequence[str],
    schema: str,
    *,
    invocation_cwd: Path,
) -> dict[str, object]:
    request_json: str | None = None
    request_file: str | None = None
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if value == "--request-json" and index + 1 < len(arguments):
            request_json = arguments[index + 1]
            index += 2
            continue
        if value == "--request-file" and index + 1 < len(arguments):
            request_file = arguments[index + 1]
            index += 2
            continue
        raise CliUsageError(f"unknown structured request argument: {value}")
    if bool(request_json) == bool(request_file):
        raise CliUsageError("exactly one of --request-json or --request-file is required")
    try:
        value = (
            json.loads(request_json)
            if request_json is not None
            else json.loads(resolve_user_path(str(request_file), invocation_cwd).read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise CliUsageError(f"structured request invalid: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise CliUsageError(f"structured request schema must be {schema}")
    return value


def invoke_install_core(
    operation: str,
    request: object,
    *,
    core: object | None = None,
) -> dict[str, object]:
    if operation not in {"update", "migrate"}:
        raise CliUsageError("install operation must be update or migrate")
    if not isinstance(request, dict) or request.get("schema") != "decretum.install.request.v1":
        raise CliUsageError("install request schema invalid")
    required = {
        "source_root",
        "home_root",
        "current_tool",
        "explicit_tools",
        "tool_roots",
        "projection_manifest",
        "write",
    }
    missing = sorted(required - set(request))
    if missing:
        raise CliUsageError("install request fields missing: " + ",".join(missing))
    if type(request.get("write")) is not bool:
        raise CliUsageError("install request write must be boolean")
    if request.get("fanout", False) is not False:
        raise CliUsageError("install request fanout must remain false")
    explicit_tools = request.get("explicit_tools")
    tool_roots = request.get("tool_roots")
    if not isinstance(explicit_tools, list) or any(not isinstance(item, str) for item in explicit_tools):
        raise CliUsageError("install request explicit_tools invalid")
    if not isinstance(tool_roots, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in tool_roots.items()
    ):
        raise CliUsageError("install request tool_roots invalid")
    if core is None:
        module = importlib.import_module("install_current_agent_copy")
        core = module.install_current_agent_copy
    if not callable(core):
        raise CliUsageError("install updater core is unavailable")
    result = core(
        source_root=Path(str(request["source_root"])),
        home_root=Path(str(request["home_root"])),
        current_tool=str(request["current_tool"]),
        explicit_tools=list(explicit_tools),
        tool_roots={key: Path(value) for key, value in tool_roots.items()},
        projection_manifest=Path(str(request["projection_manifest"])),
        write=bool(request["write"]),
        fanout=False,
        source_package_sha256=request.get("source_package_sha256"),
        platform_context=request.get("platform_context"),
        backup_root=(
            Path(str(request["backup_root"]))
            if request.get("backup_root") is not None
            else None
        ),
    )
    if not isinstance(result, dict):
        raise CliUsageError("install updater core returned an invalid receipt")
    return {
        **result,
        "cli_operation": operation,
        "updater_core": "install_current_agent_copy.install_current_agent_copy",
    }


def _capture_install_core(
    operation: str,
    arguments: Sequence[str],
    *,
    invocation_cwd: Path,
) -> InvocationResult:
    request = _structured_request(
        arguments,
        "decretum.install.request.v1",
        invocation_cwd=invocation_cwd,
    )
    result = invoke_install_core(operation, request)
    return InvocationResult(
        returncode=0 if result.get("ok") is True else 2,
        stdout=json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n",
        stderr="",
        loader="install_current_agent_copy.install_current_agent_copy",
        legacy_path="scripts/install_current_agent_copy.py",
    )


def invoke_install_rollback(
    request: object,
    *,
    core: object | None = None,
) -> dict[str, object]:
    if not isinstance(request, dict) or request.get("schema") != "decretum.install.rollback.request.v1":
        raise CliUsageError("install rollback request schema invalid")
    for field in ("home_root", "backup_root"):
        if not isinstance(request.get(field), str) or not str(request[field]).strip():
            raise CliUsageError(f"install rollback request {field} invalid")
    if core is None:
        module = importlib.import_module("install_current_agent_copy")
        core = module.rollback_install_backup
    if not callable(core):
        raise CliUsageError("install rollback core is unavailable")
    result = core(
        home_root=Path(str(request["home_root"])),
        backup_root=Path(str(request["backup_root"])),
    )
    if not isinstance(result, dict):
        raise CliUsageError("install rollback core returned an invalid receipt")
    return {
        **result,
        "cli_operation": "rollback",
        "rollback_core": "install_current_agent_copy.rollback_install_backup",
    }


def _capture_install_rollback(
    arguments: Sequence[str],
    *,
    invocation_cwd: Path,
) -> InvocationResult:
    request = _structured_request(
        arguments,
        "decretum.install.rollback.request.v1",
        invocation_cwd=invocation_cwd,
    )
    result = invoke_install_rollback(request)
    return InvocationResult(
        returncode=0 if result.get("ok") is True else 2,
        stdout=json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n",
        stderr="",
        loader="install_current_agent_copy.rollback_install_backup",
        legacy_path="scripts/install_current_agent_copy.py",
    )


def _normalized_exit_code(result: InvocationResult, payload: object) -> int:
    if result.returncode == 0:
        return 0
    if result.returncode == 2:
        error_code = payload.get("error_code") if isinstance(payload, dict) else None
        invalid = isinstance(error_code, str) and any(
            token in error_code for token in ("invalid", "missing", "unknown")
        )
        if invalid or " error: " in f" {result.stderr.lower()} ":
            return 3
        return 2
    return 3


def _emit_invocation(command: str, result: InvocationResult, output_format: str) -> int:
    payload = _json_payload(result.stdout)
    exit_code = _normalized_exit_code(result, payload)
    if output_format == "text":
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        return exit_code
    problems: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get("problems"), list):
        problems.extend(str(item) for item in payload["problems"])
    if result.stderr.strip():
        problems.extend(line for line in result.stderr.splitlines() if line.strip())
    if exit_code and not problems:
        problems.append(f"adapter_exit_code:{result.returncode}")
    envelope = {
        "schema": RESULT_SCHEMA,
        "ok": exit_code == 0,
        "command": command,
        "status": "PASS" if exit_code == 0 else "BLOCKED" if exit_code == 2 else "INVALID",
        "receipt_id": payload.get("receipt_id") if isinstance(payload, dict) else None,
        "problems": problems,
        "evidence": {
            "loader": result.loader,
            "legacy_path": result.legacy_path,
            "original_exit_code": result.returncode,
            "normalization": list(result.normalization_notes),
        },
        "payload": payload,
    }
    print(json.dumps(envelope, ensure_ascii=True, indent=2, sort_keys=True))
    return exit_code


def _usage_payload(message: str, command: str | None = None) -> dict[str, object]:
    return {
        "schema": RESULT_SCHEMA,
        "ok": False,
        "command": command,
        "status": "INVALID",
        "receipt_id": None,
        "problems": [message],
        "evidence": {"loader": "court_cli_registry", "legacy_path": None},
    }


def _emit_usage(message: str, output_format: str, command: str | None = None) -> int:
    if output_format == "json":
        print(json.dumps(_usage_payload(message, command), ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(f"decretum-matrix: error: {message}", file=sys.stderr)
    return 3


def _resolve_and_run(
    group: str,
    command: str,
    arguments: Sequence[str],
    output_format: str,
    *,
    invocation_cwd: Path,
) -> int:
    records = load_registry()
    key = (group, command)
    cwd = command_cwd(group, invocation_cwd)
    if group == "court" and command == "open":
        result = _capture_court_open(arguments, output_format, cwd=cwd)
        return _emit_invocation("court open", result, output_format)
    if group == "court" and command == "closeout-session":
        result = _capture_python_module(
            "court_session_closeout",
            arguments,
            output_format=output_format,
            legacy_path="scripts/court_session_closeout.py",
        )
        return _emit_invocation("court closeout-session", result, output_format)
    if group == "court" and key not in records:
        result = _capture_runtime([command, *arguments], output_format=output_format, cwd=cwd)
        return _emit_invocation(f"court {command}", result, output_format)
    if group == "office" and command in OFFICE_RUNTIME_COMMANDS:
        result = _capture_runtime(["office", command, *arguments], output_format=output_format, cwd=cwd)
        return _emit_invocation(f"office {command}", result, output_format)
    if group == "install" and command in {"update", "migrate"}:
        result = _capture_install_core(command, arguments, invocation_cwd=invocation_cwd)
        return _emit_invocation(f"install {command}", result, output_format)
    if group == "install" and command == "rollback":
        result = _capture_install_rollback(arguments, invocation_cwd=invocation_cwd)
        return _emit_invocation("install rollback", result, output_format)
    if group == "check" and command == "all":
        record = records.get(("check", "quick-validate"))
        if record is None:
            raise CliUsageError("check all requires the quick-validate adapter")
        default_arguments = list(arguments) if arguments else [str(ROOT)]
        result = _capture_subprocess(record, default_arguments, cwd=cwd)
        return _emit_invocation("check all", result, output_format)
    record = records.get(key)
    if record is None:
        if group == "office":
            result = _capture_runtime(["office", command, *arguments], output_format=output_format, cwd=cwd)
            return _emit_invocation(f"office {command}", result, output_format)
        raise CliUsageError(f"unknown command: {group} {command}")
    if record.loader == "court_runtime.main":
        result = _capture_runtime(arguments, output_format=output_format, cwd=cwd)
    elif record.loader.startswith("python_module:"):
        result = _capture_python_module(
            record.loader.split(":", 1)[1],
            arguments,
            output_format=output_format,
            legacy_path=record.legacy_path,
        )
    else:
        result = _capture_subprocess(record, arguments, cwd=cwd)
    return _emit_invocation(f"{group} {command}", result, output_format)


def main(argv: list[str] | None = None) -> int:
    invocation_cwd = Path.cwd().resolve(strict=False)
    raw = list(sys.argv[1:] if argv is None else argv)
    first, _ = _first_non_option(raw)
    if first is not None and first not in GROUP_ORDER:
        return _legacy_runtime(raw, cwd=command_cwd("court", invocation_cwd))
    try:
        output_format, values = _extract_format(raw)
    except CliUsageError as exc:
        return _emit_usage(str(exc), "text")
    if not values or values[0] in {"-h", "--help"}:
        help_text = render_root_help()
        if output_format == "json":
            print(json.dumps({"schema": RESULT_SCHEMA, "ok": True, "command": "help", "status": "PASS", "help": help_text}, ensure_ascii=True, indent=2, sort_keys=True))
        else:
            print(help_text)
        return 0
    group = values[0]
    if group not in GROUP_ORDER:
        return _emit_usage(f"unknown command group: {group}", output_format)
    if len(values) == 1 or values[1] in {"-h", "--help"}:
        help_text = render_group_help(group)
        if output_format == "json":
            print(json.dumps({"schema": RESULT_SCHEMA, "ok": True, "command": f"{group} help", "status": "PASS", "help": help_text}, ensure_ascii=True, indent=2, sort_keys=True))
        else:
            print(help_text)
        return 0
    try:
        return _resolve_and_run(
            group,
            values[1],
            values[2:],
            output_format,
            invocation_cwd=invocation_cwd,
        )
    except (CliUsageError, OSError, ValueError) as exc:
        return _emit_usage(str(exc), output_format, f"{group} {values[1]}")


if __name__ == "__main__":
    raise SystemExit(main())
