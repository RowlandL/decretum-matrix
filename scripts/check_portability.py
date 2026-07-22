"""Cross-platform and portable-package regression checks."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
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
    finally:
        court_platform.platform.system = original_system  # type: ignore[method-assign]
        os.environ.clear()
        os.environ.update(original_env)

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
