"""Verify active Decretum Matrix skill copies have matching source hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from court_platform import user_data_base
from install_current_agent_copy import PROTECTED_SHARED_AGENT_CONTRACT_SHA256


CANONICAL_INSTALL_DIRECTORY_NAME = "decretum-matrix"
LEGACY_INSTALL_DIRECTORY_NAME = "court-capability-router"


EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "agente-logs",
    "capability-index",
    "court-runtime",
    "memory-decisions",
    "obsidian-sync",
    "plan-archives",
    "shiguan-backups",
    "shiguan-imports",
    "shiguan-peers",
    "shiguan-tidy-reports",
}
EXCLUDED_FILES = {
    "installed-capabilities-catalog.md",
    "installed-skills-catalog.md",
    "installed-capabilities-manifest.json",
    "shiguan-index.jsonl",
    "shiguan-knowledge-graph.json",
}
FORBIDDEN_GENERATED_EXACT = {
    "references/installed-capabilities-catalog.md",
    "references/installed-skills-catalog.md",
    "references/installed-capabilities-manifest.json",
    "references/shiguan-index.jsonl",
    "references/shiguan-knowledge-graph.json",
    "references/shiguan-tree/_index.md",
    "references/shiguan-tree/最新树叶.md",
    "references/shiguan-tree/史馆 Web UI.md",
}


def active_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".agents" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".codex" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".claude" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        user_data_base() / "hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
    ]


def legacy_locator_conflicts(roots: list[Path]) -> list[str]:
    conflicts: list[str] = []
    for root in roots:
        legacy = root.with_name(LEGACY_INSTALL_DIRECTORY_NAME)
        if (legacy.exists() or legacy.is_symlink()) and (
            legacy.resolve(strict=False) != root.resolve(strict=False)
        ):
            conflicts.append(str(legacy))
    return conflicts


def should_skip(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if relative.as_posix() in FORBIDDEN_GENERATED_EXACT:
        return True
    if any(part.startswith("references.imported-") for part in relative.parts):
        return True
    if path.is_dir():
        return bool(set(relative.parts) & EXCLUDED_DIRS)
    if set(relative.parts) & EXCLUDED_DIRS:
        return True
    if path.name in EXCLUDED_FILES:
        return True
    lower_name = path.name.lower()
    if (
        lower_name.startswith(".tmp-")
        or ".backup" in lower_name
        or lower_name.endswith((".pyc", ".tmp", ".bak", ".log", ".sqlite", ".sqlite3", ".db"))
    ):
        return True
    if "Obsidian 回传" in relative.parts:
        return True
    if relative.as_posix().startswith("references/startup-tasks/") and path.name != "README.md":
        return True
    if relative.as_posix().startswith("references/shiguan-tree/leaves/") and path.name != "README.md":
        return True
    if relative.as_posix().startswith("references/shiguan-tree/branches/") and path.name != "README.md":
        return True
    if relative.as_posix().startswith("references/shiguan-tree/sources/") and path.name != "README.md":
        return True
    return False


def forbidden_generated_artifacts(
    root: Path, allowed_protected: set[str] | None = None
) -> list[str]:
    artifacts: list[str] = []
    allowed = allowed_protected or set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        text = relative.as_posix()
        if text in allowed:
            continue
        if (
            "__pycache__" in relative.parts
            or relative.suffix.lower() == ".pyc"
            or text in FORBIDDEN_GENERATED_EXACT
            or ("capability-index" in relative.parts and path.name != "README.md")
            or (text.startswith("references/startup-tasks/") and path.name != "README.md")
            or (
                any(text.startswith(f"references/shiguan-tree/{part}/") for part in ("branches", "leaves", "sources"))
                and path.name != "README.md"
            )
        ):
            artifacts.append(text)
    return sorted(artifacts)


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if should_skip(path, root):
            continue
        if path.is_file():
            files.append(path.relative_to(root))
    return files


def iter_union_files(roots: list[Path]) -> list[Path]:
    relatives: set[Path] = set()
    for root in roots:
        if root.exists():
            relatives.update(iter_source_files(root))
    return sorted(relatives)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def protected_anchor_contract() -> tuple[dict[str, str], list[str]]:
    path = Path(__file__).resolve().parent.parent / "references/manifests/install-projection.v1.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["protected_shared_agents_seeds"]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return {}, [f"protected_anchor_contract:{type(exc).__name__}"]
    digest = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not isinstance(value, dict) or digest != PROTECTED_SHARED_AGENT_CONTRACT_SHA256:
        return {}, ["protected_anchor_contract:manifest_drift"]
    return {str(key): str(digest).lower() for key, digest in value.items()}, []


def check(files: list[str] | None = None) -> dict[str, object]:
    roots = active_roots()
    protected, contract_errors = protected_anchor_contract()
    legacy_conflicts = legacy_locator_conflicts(roots)
    missing_roots = [str(root) for root in roots if not root.exists()]
    forbidden_generated: dict[str, list[str]] = {}
    for index, root in enumerate(roots):
        if root.exists():
            artifacts = forbidden_generated_artifacts(
                root, set(protected) if index == 0 else None
            )
            if artifacts:
                forbidden_generated[str(root)] = artifacts
    protected_drift: list[dict[str, object]] = []
    for relative, expected in protected.items():
        path = roots[0] / Path(relative)
        actual = sha256(path).lower() if path.is_file() and not path.is_symlink() else None
        if actual != expected:
            protected_drift.append(
                {"file": relative, "expected": expected, "actual": actual}
            )
    if files:
        relatives = [Path(item) for item in files]
    else:
        relatives = iter_union_files(roots)

    drift: list[dict[str, object]] = []
    for relative in relatives:
        hashes: dict[str, str] = {}
        missing: list[str] = []
        for root in roots:
            path = root / relative
            if not path.exists():
                missing.append(str(path))
                continue
            hashes[str(root)] = sha256(path)
        unique = sorted(set(hashes.values()))
        if missing or len(unique) != 1:
            drift.append(
                {
                    "file": relative.as_posix(),
                    "missing": missing,
                    "hashes": hashes,
                }
            )
    return {
        "ok": not missing_roots and not drift and not forbidden_generated and not legacy_conflicts and not protected_drift and not contract_errors,
        "roots": [str(root) for root in roots],
        "missing_roots": missing_roots,
        "checked_files": len(relatives),
        "drift": drift,
        "forbidden_generated": forbidden_generated,
        "protected_anchor_drift": protected_drift,
        "protected_anchor_contract_errors": contract_errors,
        "legacy_locator_conflicts": legacy_conflicts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--file", action="append", default=[], help="Relative file to check; repeatable.")
    args = parser.parse_args()

    result = check(args.file or None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(f"ACTIVE_COPY_HASHES_OK roots={len(result['roots'])} files={result['checked_files']}")
    else:
        print("ACTIVE_COPY_HASHES_FAILED")
        for item in result["drift"][:50]:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        if result["missing_roots"]:
            print("MISSING_ROOTS " + ", ".join(result["missing_roots"]))
        if result["legacy_locator_conflicts"]:
            print("LEGACY_LOCATOR_CONFLICTS " + ", ".join(result["legacy_locator_conflicts"]))
        for root, paths in result["forbidden_generated"].items():
            print(f"FORBIDDEN_GENERATED {root} " + ", ".join(paths[:50]))
        for item in result["protected_anchor_drift"]:
            print("PROTECTED_ANCHOR_DRIFT " + json.dumps(item, sort_keys=True))
        for error in result["protected_anchor_contract_errors"]:
            print("PROTECTED_ANCHOR_CONTRACT " + error)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
