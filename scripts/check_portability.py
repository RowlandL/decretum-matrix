"""Cross-platform and portable-package regression checks."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import court_platform  # noqa: E402
import ensure_supercc_court  # noqa: E402
import package_skill  # noqa: E402
import shiguan_paths  # noqa: E402


def text_file(path: Path) -> bool:
    return path.suffix.lower() in package_skill.TEXT_SUFFIXES or path.suffix.lower() in {"", ".cmd", ".sh", ".ps1"}


def source_candidates() -> list[Path]:
    out: list[Path] = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if package_skill.should_skip(rel, path.is_dir()):
            continue
        if path.is_file() and text_file(path):
            out.append(path)
    return out


def contains_host_path(path: Path) -> bool:
    data = path.read_bytes()
    return any(pattern.search(data) for pattern in package_skill.HOST_ABSOLUTE_PATH_PATTERNS)


def doc_command_portability_violations() -> list[str]:
    violations: list[str] = []
    forbidden_fragments = ("python .\\scripts", "python scripts/", "$env:USERPROFILE", "$env:TEMP")
    for path in source_candidates():
        rel = path.relative_to(ROOT)
        if path.suffix.lower() != ".md" and path.name != "SKILL.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(fragment in text for fragment in forbidden_fragments):
            violations.append(rel.as_posix())
    return sorted(violations)


def bytecode_guard_violations() -> list[str]:
    local_modules = {path.stem for path in SCRIPTS.glob("*.py")}
    violations: list[str] = []
    for path in sorted(SCRIPTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        local_import_lines: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in local_modules:
                    local_import_lines.append(node.lineno)
            elif isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] in local_modules for alias in node.names
            ):
                local_import_lines.append(node.lineno)
        if not local_import_lines:
            continue
        guard_lines = [
            node.lineno
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and node.value.value is True
            and any(
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "sys"
                and target.attr == "dont_write_bytecode"
                for target in node.targets
            )
        ]
        if not guard_lines or min(guard_lines) >= min(local_import_lines):
            violations.append(path.relative_to(ROOT).as_posix())
    return violations


def run() -> dict[str, object]:
    checks: list[dict[str, object]] = []

    original_system = court_platform.platform.system
    original_env = os.environ.copy()
    restore_failure: BaseException | None = None
    try:
        court_platform.platform.system = lambda: "Linux"  # type: ignore[method-assign]
        os.environ.pop("XDG_DATA_HOME", None)
        linux_base = court_platform.user_data_base()
        os.environ["XDG_DATA_HOME"] = "/tmp/court-xdg-data"
        linux_xdg_base = court_platform.user_data_base()

        court_platform.platform.system = lambda: "Darwin"  # type: ignore[method-assign]
        mac_base = court_platform.user_data_base()

        court_platform.platform.system = lambda: "Windows"  # type: ignore[method-assign]
        os.environ["LOCALAPPDATA"] = r"C:\Users\Example\AppData\Local"
        windows_base = court_platform.user_data_base()
        for key in shiguan_paths.CLAUDE_CODE_ENV_KEYS:
            os.environ.pop(key, None)
        runtime_root_detection = (
            shiguan_paths.is_claude_code_context(("/home/user/.claude/skills/decretum-matrix/",))
            and shiguan_paths.is_claude_code_context((r"C:\Users\user\.claude\skills\decretum-matrix",))
            and not shiguan_paths.is_claude_code_context(("/home/user/.codex/skills/decretum-matrix/",))
        )
        synthetic_shared_root = Path(r"C:\Users\Example\.agents\court-shiguan\decretum-matrix")
        os.environ[shiguan_paths.ROOT_ENV_KEYS[0]] = str(synthetic_shared_root)
        os.environ["CODEX_THREAD_ID"] = "test-codex"
        os.environ["CLAUDE_CODE_EFFORT_LEVEL"] = "test-weak-marker"
        runtime_agent = shiguan_paths.detect_runtime_agent()
        codex_runtime_precedence = (
            runtime_agent["source_agent"] == "codex"
            and Path(runtime_agent["shared_shiguan_root"])
            == synthetic_shared_root.resolve() / "references"
        )
        generic_cli_alias = shiguan_paths.detect_runtime_agent("genericcli")
        source_agent_alias_ok = (
            generic_cli_alias["source_agent"] == "generic-cli"
            and generic_cli_alias["source_agent_label"] == "GenericCLI"
        )
        try:
            shiguan_paths.detect_runtime_agent("Taizi")
            invalid_source_agent_rejected = False
        except ValueError as exc:
            invalid_source_agent_rejected = str(exc) == "source_agent_not_allowed:taizi"
    finally:
        court_platform.platform.system = original_system  # type: ignore[method-assign]
        try:
            os.environ.clear()
            os.environ.update(original_env)
        except (ValueError, OSError) as exc:
            # M3 RED（R-PA2）：环境变量恢复超长/失败必须 fail closed 并给出明确 reason，
            # 不得裸崩溃吞没整份报告（Windows 单变量 32767 上限）。
            # 审查（Entry 0052 缺陷 4）：补 stage/checks_completed 诊断字段——
            # 环境准备阶段（try 块）未执行任何检查，checks=[] 属预期，
            # 以 stage=environment_restore 定位失败阶段，消除"检查未执行/崩溃"歧义。
            restore_failure = exc

    if restore_failure is not None:
        return {
            "ok": False,
            "checks": checks,
            "stage": "environment_restore",
            "checks_completed": len(checks),
            "failures": [
                f"environment_restore_overflow:{type(restore_failure).__name__}:{restore_failure}"
            ],
        }

    checks.append(
        {
            "name": "native user data roots are platform-specific",
            "ok": linux_base.as_posix().endswith("/.local/share")
            and linux_xdg_base.as_posix() == "/tmp/court-xdg-data"
            and mac_base.as_posix().endswith("/Library/Application Support")
            and str(windows_base).lower().endswith(r"appdata\local"),
            "details": {
                "linux": str(linux_base),
                "linux_xdg": str(linux_xdg_base),
                "mac": str(mac_base),
                "windows": str(windows_base),
            },
        }
    )

    checks.append(
        {
            "name": "runtime skill-root detection accepts POSIX and Windows separators",
            "ok": runtime_root_detection,
        }
    )
    checks.append({"name": "explicit Codex runtime outranks weak Claude markers", "ok": codex_runtime_precedence})
    checks.append(
        {
            "name": "explicit source-agent override is writer-whitelisted",
            "ok": source_agent_alias_ok and invalid_source_agent_rejected,
        }
    )

    checks.append(
        {
            "name": "host-local registries and generated Shiguan indexes are excluded from portable package input",
            "ok": all(
                package_skill.should_skip(Path(path), False)
                for path in (
                    "references/agent-source-registry.json",
                    "references/shiguan-tree/_index.md",
                    "references/shiguan-tree/最新树叶.md",
                    "references/shiguan-tree/史馆 Web UI.md",
                )
            ),
        }
    )

    hierarchy_runtime = Path("scripts/court_dispatch_hierarchy.py")
    hierarchy_checker = Path("scripts/check_court_dispatch_hierarchy.py")
    hierarchy_manifest_member = (
        f"{package_skill.ROOT_NAME}/references/manifests/court-dispatch-hierarchy.v1.json"
    )
    hierarchy_paths = (
        hierarchy_runtime,
        hierarchy_checker,
        Path("references/manifests/court-dispatch-hierarchy.v1.json"),
    )
    checks.append(
        {
            "name": "dispatch hierarchy runtime module and manifest match the install projection",
            "ok": (
                package_skill.package_includes(hierarchy_runtime, is_dir=False)
                and hierarchy_manifest_member in package_skill.PACKAGE_IDENTITY_REQUIRED_MEMBERS
                and all((ROOT / path).is_file() for path in hierarchy_paths)
                and not package_skill.should_skip(hierarchy_runtime, False)
                and not package_skill.should_skip(
                    Path("references/manifests/court-dispatch-hierarchy.v1.json"), False
                )
            ),
            "details": {
                "runtime_script": hierarchy_runtime.as_posix(),
                "source_checker": hierarchy_checker.as_posix(),
                "required_manifest": hierarchy_manifest_member,
            },
        }
    )

    projection_manifest = json.loads(
        (ROOT / "references" / "manifests" / "install-projection.v1.json").read_text(
            encoding="utf-8"
        )
    )
    projected_shared = set(projection_manifest["projections"]["shared_agents"])
    projected_current_tool = set(
        projection_manifest["projections"]["portable_current_tool"]
    )
    migration_entrypoints = (
        Path("scripts/migrate_legacy_skill_locator.py"),
        Path("scripts/migrate_current_tool_replica.py"),
    )
    checks.append(
        {
            "name": "locator migration entrypoints are portable and projected",
            "ok": (
                all((ROOT / entrypoint).is_file() for entrypoint in migration_entrypoints)
                and all(
                    package_skill.package_includes(entrypoint, is_dir=False)
                    for entrypoint in migration_entrypoints
                )
                and all(
                    entrypoint.as_posix() in projected_shared
                    and entrypoint.as_posix() in projected_current_tool
                    and not package_skill.should_skip(entrypoint, False)
                    for entrypoint in migration_entrypoints
                )
            ),
            "details": {
                "scripts": [entrypoint.as_posix() for entrypoint in migration_entrypoints]
            },
        }
    )

    leaked = sorted(str(path.relative_to(ROOT)).replace("\\", "/") for path in source_candidates() if contains_host_path(path))
    checks.append(
        {
            "name": "portable package candidate text files do not contain host user absolute paths",
            "ok": not leaked,
            "details": {"leaked": leaked[:20], "leaked_count": len(leaked)},
        }
    )

    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    forbidden_powershell_home = "$" + "env:USERPROFILE"
    checks.append(
        {
            "name": "SKILL validation examples use portable script paths",
            "ok": "python -B scripts/quick_validate.py ." in skill_text
            and "python scripts/" not in skill_text
            and forbidden_powershell_home not in skill_text,
        }
    )

    doc_violations = doc_command_portability_violations()
    checks.append(
        {
            "name": "packaged documentation uses portable command examples",
            "ok": not doc_violations,
            "details": {"violations": doc_violations},
        }
    )

    bytecode_violations = bytecode_guard_violations()
    checks.append(
        {
            "name": "court Python entrypoints disable bytecode before local imports",
            "ok": not bytecode_violations,
            "details": {"violations": bytecode_violations, "violation_count": len(bytecode_violations)},
        }
    )

    help_probe = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "package_skill.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    try:
        help_text = help_probe.stdout.decode("utf-8")
        help_utf8 = help_probe.returncode == 0 and "诏令矩阵" in help_text and "\ufffd" not in help_text
    except UnicodeDecodeError:
        help_utf8 = False
    checks.append(
        {
            "name": "package entrypoint emits UTF-8 help without replacement characters",
            "ok": help_utf8,
            "details": {"returncode": help_probe.returncode},
        }
    )

    contract = ensure_supercc_court.shell_contract_block("menxia")
    checks.append(
        {
            "name": "superCC shell contract stays wrapper-relative and role-generic",
            "ok": "supercc-squad.sh receive menxia --json" in contract
            and "supercc-squad.ps1" in contract
            and "supercc-squad.cmd" in contract
            and "cd C:" not in contract
            and "/mnt/c/" not in contract,
        }
    )

    ok = all(bool(check.get("ok")) for check in checks)
    return {"ok": ok, "checks": checks}


def main() -> int:
    payload = run()
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
