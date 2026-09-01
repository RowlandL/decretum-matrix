"""Verify projected files across local Decretum Matrix skill roots.

This repository-only checker is a post-install/release gate. Runtime loaders,
startup paths, preload code, and synchronizers must never import or invoke it.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True

from court_platform import user_data_base


ROOT = Path(__file__).resolve().parents[2]
PROJECTION_MANIFEST = Path("references/manifests/install-projection.v1.json")
CHECKER_RELATIVE = Path("scripts/check_active_copy_hashes.py")
CANONICAL_INSTALL_DIRECTORY_NAME = "decretum-matrix"
# M2 投影子门 GREEN：计划书 §4.4 第 4 条 install receipt 强制字段（按 §4.4 逐字）。
INSTALL_RECEIPT_REQUIRED_FIELDS = (
    "selection_policy",
    "primary_root",
    "current_tool",
    "current_tool_root",
    "current_tool_root_proof",
    "status",
    "explicit_extra_targets",
    "selected_roots",
    "authority",
    "receipt_sha256",
)
INSTALL_RECEIPTS_RELATIVE = Path("install-receipts") / "decretum-matrix"


def default_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".agents" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".codex" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".claude" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        user_data_base() / "hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
    ]


def qoder_root() -> Path:
    return Path.home() / ".qoder" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME


def _absolute_no_follow(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _stat_is_link_or_reparse(value: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(value.st_mode) or bool(
        reparse_flag and getattr(value, "st_file_attributes", 0) & reparse_flag
    )


def _known_alias_target(root: Path) -> Path | None:
    """Return the physical target for the two explicitly governed aliases."""
    absolute = _absolute_no_follow(root)
    home = Path.home()
    aliases = {
        _absolute_no_follow(home / ".hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME):
            _absolute_no_follow(user_data_base() / "hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME),
        _absolute_no_follow(home / ".qoder" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME):
            _absolute_no_follow(home / ".agents" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME),
    }
    target = aliases.get(absolute)
    value = _lstat(absolute)
    if target is None or value is None or not _stat_is_link_or_reparse(value):
        return None
    try:
        resolved = absolute.resolve(strict=True)
    except OSError:
        return None
    return target if _absolute_no_follow(resolved) == _absolute_no_follow(target.resolve()) else None


def _safe_relative(value: str) -> Path:
    relative = Path(value)
    if (
        relative == Path(".")
        or relative.is_absolute()
        or bool(relative.anchor)
        or bool(relative.drive)
        or ".." in relative.parts
    ):
        raise ValueError(f"unsafe projection path: {value}")
    return relative


def _is_under(path: Path, root: Path) -> bool:
    try:
        _absolute_no_follow(path).relative_to(_absolute_no_follow(root))
    except ValueError:
        return False
    return True


def _assert_safe_root(root: Path, *, allow_missing: bool, label: str) -> Path:
    absolute = _absolute_no_follow(root)
    alias_target = _known_alias_target(absolute)
    for candidate in [*reversed(absolute.parents), absolute]:
        value = _lstat(candidate)
        if value is None:
            continue
        if _stat_is_link_or_reparse(value):
            if candidate == absolute and alias_target is not None:
                continue
            raise ValueError(f"{label} contains a link or reparse point: {candidate}")
        if not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"{label} ancestor is not a directory: {candidate}")
    if not allow_missing and _lstat(absolute) is None:
        raise ValueError(f"{label} is missing: {absolute}")
    if alias_target is not None:
        target_value = _lstat(alias_target)
        if target_value is None or _stat_is_link_or_reparse(target_value) or not stat.S_ISDIR(target_value.st_mode):
            raise ValueError(f"{label} alias target is unsafe: {alias_target}")
    return absolute


def _assert_safe_descendant(
    root: Path,
    path: Path,
    *,
    allow_missing: bool,
    require_file: bool,
    label: str,
) -> Path:
    root_absolute = _absolute_no_follow(root)
    path_absolute = _absolute_no_follow(path)
    if not _is_under(path_absolute, root_absolute):
        raise ValueError(f"{label} escapes root: {path_absolute}")
    relative = path_absolute.relative_to(root_absolute)
    current = root_absolute
    for index, part in enumerate(relative.parts):
        current = current / part
        value = _lstat(current)
        leaf = index == len(relative.parts) - 1
        if value is None:
            if not allow_missing:
                raise ValueError(f"{label} is missing: {current}")
            continue
        if _stat_is_link_or_reparse(value):
            raise ValueError(f"{label} contains a link or reparse point: {current}")
        if not leaf and not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"{label} parent is not a directory: {current}")
        if leaf and require_file and not stat.S_ISREG(value.st_mode):
            raise ValueError(f"{label} is not a regular file: {current}")
    return path_absolute


def _scan_safe_tree(root: Path, *, label: str) -> list[Path]:
    root = _assert_safe_root(root, allow_missing=False, label=label)
    files: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in sorted(entries, key=lambda item: item.name.casefold()):
                path = Path(entry.path)
                value = entry.stat(follow_symlinks=False)
                if _stat_is_link_or_reparse(value):
                    raise ValueError(f"{label} contains a link or reparse point: {path}")
                if stat.S_ISDIR(value.st_mode):
                    stack.append(path)
                elif stat.S_ISREG(value.st_mode):
                    files.append(path)
                else:
                    raise ValueError(f"{label} contains a non-regular path: {path}")
    return files


def _root_identity(path: Path) -> str:
    return os.path.normcase(str(_absolute_no_follow(path)))


def _physical_authority_root(path: Path) -> Path:
    absolute = _absolute_no_follow(path)
    return _known_alias_target(absolute) or absolute


def _governed_root_contract(
    roots: list[Path], *, receipt_roots: list[Path] | None = None
) -> tuple[str, list[Path]]:
    normalized = [_absolute_no_follow(path) for path in roots]
    identities = [_root_identity(path) for path in normalized]
    if len(set(identities)) != len(identities):
        raise ValueError("installed roots must be unique")
    if receipt_roots is not None:
        # M2 投影子门 GREEN：roots 来自已验证 receipt 的 selected_roots（计划书 §4.4 第 3 条），
        # 逐根 identity 与 receipt 记录一致即视为合法契约，不再要求硬编码 FIVE/SIX 形状。
        receipt_identities = [
            _root_identity(_absolute_no_follow(path)) for path in receipt_roots
        ]
        if identities == receipt_identities:
            return "RECEIPT_SELECTED_ROOTS", normalized
        raise ValueError("governed_roots_not_receipt_derived")
    five = [_absolute_no_follow(path) for path in default_roots()]
    six = [*five, _absolute_no_follow(qoder_root())]
    if identities == [_root_identity(path) for path in five]:
        return "FIVE_GOVERNED_ROOTS", normalized
    if identities == [_root_identity(path) for path in six]:
        return "FIVE_GOVERNED_ROOTS_PLUS_QODER", normalized
    raise ValueError("installed roots do not match the governed five-root or five-plus-Qoder contract")


def _load_projection(source: Path, projection: str) -> list[Path]:
    source = _assert_safe_root(source, allow_missing=False, label="source root")
    manifest_path = source / PROJECTION_MANIFEST
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "court.install_projection.v1":
        raise ValueError(f"invalid projection manifest: {manifest_path}")
    projections = value.get("projections")
    if not isinstance(projections, dict):
        raise ValueError("projection manifest has no projections")
    raw = projections.get(projection)
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ValueError(f"projection is invalid: {projection}")
    cli_public = projections.get("cli_public")
    if not isinstance(cli_public, list) or any(not isinstance(item, str) for item in cli_public):
        raise ValueError("projection is invalid: cli_public")
    entries = [*raw, *cli_public]
    if value.get("protected_shared_agents_seeds", []) != []:
        raise ValueError("protected_shared_agents_seeds must be empty")
    if not entries:
        raise ValueError(f"projection is empty: {projection}")

    files: set[Path] = set()
    for text in entries:
        relative = _safe_relative(text)
        path = _assert_safe_descendant(
            source,
            source / relative,
            allow_missing=False,
            require_file=False,
            label="source projection path",
        )
        value = _lstat(path)
        if value is not None and stat.S_ISREG(value.st_mode):
            files.add(relative)
            continue
        if value is None or not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"projected path is missing: {relative.as_posix()}")
        for child in _scan_safe_tree(path, label="source projection"):
            if "__pycache__" not in child.parts and child.suffix.lower() != ".pyc":
                files.add(child.relative_to(source))
    if not files:
        raise ValueError(f"projection contains no files: {projection}")
    return sorted(files)


def _sha256(path: Path) -> str:
    value = _lstat(path)
    if value is None or _stat_is_link_or_reparse(value) or not stat.S_ISREG(value.st_mode):
        raise ValueError(f"refusing to hash non-regular path: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("receipt_sha256", None)
    # M3 GREEN（R-I1）：install_receipt_path 为运行时落盘路径（fixture 临时目录随机），
    # 不得进入确定性 digest（与 receipt_sha256 同理）。
    payload.pop("install_receipt_path", None)
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def check(
    *,
    source: Path,
    roots: list[Path],
    projection: str = "shared_agents",
    receipt_roots: list[Path] | None = None,
    shard_assertions: list[dict[str, Any]] | None = None,
    verify_codex_agent_roles: bool = True,
) -> dict[str, Any]:
    source = _assert_safe_root(source, allow_missing=False, label="source root")
    # M2 迁移子门 GREEN（R-M4）：shard 断言必须有 consumer 与 evidence 成对支撑（计划书 L188）。
    # 每条断言（缺失/额外/陈旧 shard）必须同时携带 consumer（谁消费该 shard）与
    # evidence（证明该 shard 状态的事实）；缺任一 → fail closed。
    if shard_assertions is not None:
        for assertion in shard_assertions:
            if not isinstance(assertion, dict):
                raise ValueError(
                    "shard_without_consumer_or_evidence:assertion_not_object"
                )
            path = assertion.get("path")
            kind = assertion.get("kind")
            consumer = assertion.get("consumer")
            evidence = assertion.get("evidence")
            if not isinstance(path, str) or not isinstance(kind, str):
                raise ValueError(
                    "shard_without_consumer_or_evidence:path_or_kind_missing"
                )
            if not isinstance(consumer, str) or not consumer:
                raise ValueError(
                    "shard_without_consumer_or_evidence:consumer_missing"
                )
            if not isinstance(evidence, str) or not evidence:
                raise ValueError(
                    "shard_without_consumer_or_evidence:evidence_missing"
                )
    root_contract, governed_roots = _governed_root_contract(
        roots, receipt_roots=receipt_roots
    )
    projected_files = _load_projection(source, projection)
    expected = {
        relative.as_posix(): _sha256(source / relative)
        for relative in projected_files
    }
    projection_sha256 = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    missing_roots: list[str] = []
    drift: list[dict[str, Any]] = []
    extra_files: list[dict[str, str]] = []
    unsafe_paths: list[dict[str, str]] = []
    forbidden_checker_copies: list[str] = []
    root_evidence: list[dict[str, Any]] = []
    verified_physical: dict[str, dict[str, Any]] = {}
    for root in governed_roots:
        physical = _physical_authority_root(root)
        physical_key = _root_identity(physical)
        existing_evidence = verified_physical.get(physical_key)
        if existing_evidence is not None:
            root_evidence.append(
                {
                    "root": str(_absolute_no_follow(root)),
                    "alias_of": (
                        str(_known_alias_target(root))
                        if _known_alias_target(root) is not None
                        else None
                    ),
                    "physical_authority": str(physical),
                    "verification_reused_from": existing_evidence["root"],
                    "checked_files": existing_evidence["checked_files"],
                    "drift_count": existing_evidence["drift_count"],
                    "extra_count": existing_evidence["extra_count"],
                    "unsafe_count": existing_evidence["unsafe_count"],
                    "checker_absent": existing_evidence["checker_absent"],
                }
            )
            continue
        try:
            root = _assert_safe_root(root, allow_missing=True, label="installed root")
        except ValueError as exc:
            unsafe_paths.append(
                {
                    "root": str(_absolute_no_follow(root)),
                    "path": str(_absolute_no_follow(root)),
                    "reason": str(exc),
                }
            )
            evidence = {
                    "root": str(_absolute_no_follow(root)),
                    "alias_of": (
                        str(_known_alias_target(root))
                        if _known_alias_target(root) is not None
                        else None
                    ),
                    "physical_authority": str(physical),
                    "checked_files": 0,
                    "drift_count": 0,
                    "extra_count": 0,
                    "unsafe_count": 1,
                    "checker_absent": None,
                }
            root_evidence.append(evidence)
            verified_physical[physical_key] = evidence
            continue
        if _lstat(root) is None:
            missing_roots.append(str(root))
            continue
        try:
            installed_paths = _scan_safe_tree(root, label="installed root")
        except ValueError as exc:
            unsafe_paths.append(
                {
                    "root": str(root),
                    "path": str(root),
                    "reason": str(exc),
                }
            )
            evidence = {
                    "root": str(root),
                    "alias_of": (
                        str(_known_alias_target(root))
                        if _known_alias_target(root) is not None
                        else None
                    ),
                    "physical_authority": str(physical),
                    "checked_files": 0,
                    "drift_count": 0,
                    "extra_count": 0,
                    "unsafe_count": 1,
                    "checker_absent": None,
                }
            root_evidence.append(evidence)
            verified_physical[physical_key] = evidence
            continue
        installed = {
            path.relative_to(root).as_posix(): path
            for path in installed_paths
        }
        installed_names = set(installed)
        expected_names = set(expected)
        root_extras = sorted(installed_names - expected_names)
        for relative_text in root_extras:
            extra_files.append({"root": str(root), "file": relative_text})
        if CHECKER_RELATIVE.as_posix() in installed_names:
            forbidden_checker_copies.append(str(installed[CHECKER_RELATIVE.as_posix()]))

        root_drift = 0
        for relative_text in sorted(expected_names - installed_names):
            expected_sha256 = expected[relative_text]
            drift.append(
                {
                    "root": str(root),
                    "file": relative_text,
                    "status": "MISSING",
                    "expected_sha256": expected_sha256,
                    "actual_sha256": None,
                }
            )
            root_drift += 1
        for relative_text in sorted(expected_names & installed_names):
            expected_sha256 = expected[relative_text]
            path = _assert_safe_descendant(
                root,
                installed[relative_text],
                allow_missing=False,
                require_file=True,
                label="installed projected file",
            )
            actual_sha256 = _sha256(path)
            if actual_sha256 != expected_sha256:
                drift.append(
                    {
                        "root": str(root),
                        "file": relative_text,
                        "status": "DRIFT",
                        "expected_sha256": expected_sha256,
                        "actual_sha256": actual_sha256,
                    }
                )
                root_drift += 1
        evidence = {
                "root": str(root),
                "alias_of": (
                    str(_known_alias_target(root))
                    if _known_alias_target(root) is not None
                    else None
                ),
                "physical_authority": str(physical),
                "checked_files": len(expected_names & installed_names),
                "drift_count": root_drift,
                "extra_count": len(root_extras),
                "unsafe_count": 0,
                "checker_absent": CHECKER_RELATIVE.as_posix() not in installed_names,
            }
        root_evidence.append(evidence)
        verified_physical[physical_key] = evidence
    ok = not (
        missing_roots
        or drift
        or extra_files
        or unsafe_paths
        or forbidden_checker_copies
    )
    codex_agent_roles: dict[str, Any] = {
        "required": False,
        "ok": True,
        "status": "NOT_APPLICABLE",
    }
    codex_skill_root = Path.home() / ".codex" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME
    if verify_codex_agent_roles and projection == "shared_agents" and any(
        _root_identity(path) == _root_identity(codex_skill_root)
        for path in governed_roots
    ):
        codex_agent_roles["required"] = True
        try:
            from check_codex_agent_roles import validate_installed_agents

            codex_agent_roles.update(validate_installed_agents())
            codex_agent_roles["status"] = (
                "PASS" if codex_agent_roles.get("ok") is True else "FAIL"
            )
        except Exception as exc:
            codex_agent_roles.update(
                {
                    "ok": False,
                    "status": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        ok = ok and codex_agent_roles.get("ok") is True
    version_path = _assert_safe_descendant(
        source,
        source / "VERSION",
        allow_missing=True,
        require_file=True,
        label="source version",
    )
    result = {
        "schema": "court.active_copy_hashes.v2",
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
        "source": str(source),
        "source_version": (
            version_path.read_text(encoding="utf-8").strip()
            if _lstat(version_path) is not None
            else None
        ),
        "projection": projection,
        "projection_sha256": projection_sha256,
        "root_contract": root_contract,
        "roots": [str(path) for path in governed_roots],
        "physical_authority_count": len(verified_physical),
        "physical_authorities": sorted(verified_physical),
        "checked_files": len(projected_files),
        "missing_roots": missing_roots,
        "drift": drift,
        "extra_files": extra_files,
        "unsafe_paths": unsafe_paths,
        "forbidden_checker_copies": forbidden_checker_copies,
        "codex_agent_roles": codex_agent_roles,
        "root_evidence": root_evidence,
        "pending_body_access": "NO",
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result


def _write_fixture_source(root: Path) -> None:
    (root / "references" / "manifests").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "SKILL.md").write_text("# fixture\n", encoding="utf-8")
    (root / "VERSION").write_text("fixture\n", encoding="utf-8")
    (root / "scripts" / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "references" / "manifests" / "install-projection.v1.json").write_text(
        json.dumps(
            {
                "schema": "court.install_projection.v1",
                "identity_manifest": "references/manifests/skill-identity.v1.json",
                "policy": {
                    "required_target": ".agents",
                    "default_optional_target": "current_agent_tool_only",
                    "extra_targets": "explicit_latest_user_request_only",
                    "fanout": "forbidden",
                },
                "protected_shared_agents_seeds": [],
                "frozen_install_references": [],
                "projections": {
                    "shared_agents": [
                        "SKILL.md",
                        "VERSION",
                        "references/manifests/install-projection.v1.json",
                        "references/manifests/skill-identity.v1.json",
                        "scripts/runtime.py",
                    ],
                    "portable_current_tool": [
                        "SKILL.md",
                        "VERSION",
                        "references/manifests/install-projection.v1.json",
                        "references/manifests/skill-identity.v1.json",
                        "scripts/runtime.py",
                    ],
                    "cli_public": [],
                    "repository_only": ["scripts/check_active_copy_hashes.py"],
                },
                "persistent_bindings": [
                    {
                        "profile_source": "agents/standing-officials/bingbu.toml",
                        "dossier_path": "agents/office-dossiers/bingbu/AGENTS.md",
                        "court_skill_path": "SKILL.md",
                        "role_key": "bingbu",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # M3 RED（R-I1）：install 的 LOADED_IDENTITY_EXPECTED 硬编码真实身份字段，
    # fixture source 必须写入完整 skill-identity 契约（display_name 等）才能通过
    # _validate_identity；此处仅写入 install 校验所需字段。
    (root / "references" / "manifests" / "skill-identity.v1.json").write_text(
        json.dumps(
            {
                "schema": "court.skill_identity.v1",
                "display_name": "Decretum Matrix（诏令矩阵）",
                "canonical_skill_name": "decretum-matrix",
                "canonical_invocation": "$decretum-matrix",
                "community_license": "AGPL-3.0-only",
                "rights_owner": "孙华清",
                "maintainer_github": "@RowlandL",
                "maintainer_github_id": 42199880,
                "locator_policy": {
                    "repository_id": "decretum-matrix",
                    "install_directory_name": "decretum-matrix",
                    "legacy_install_directory_name": "court-capability-router",
                    "legacy_install_locator_policy": "absent_or_same_physical_authority",
                    "shiguan_namespace": "court-capability-router",
                    "python_locator_pattern": "court.*",
                    "environment_locator_pattern": "COURT_*",
                    "service_name": "CourtShiguanDaemon",
                    "directory_basename_may_differ_from_skill_name": False,
                    "rename_policy": "rename_install_directory_preserve_shiguan_namespace",
                },
            }
        ),
        encoding="utf-8",
    )


def _self_test() -> dict[str, Any]:
    failures: list[str] = []
    evidence: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="decretum-active-copy-hashes-") as temporary:
        fixture = Path(temporary)
        source = fixture / "source"
        _write_fixture_source(source)
        environment = {
            "HOME": str(fixture / "home"),
            "USERPROFILE": str(fixture / "home"),
            "LOCALAPPDATA": str(fixture / "local-data"),
            "APPDATA": str(fixture / "roaming-data"),
            "XDG_DATA_HOME": str(fixture / "xdg-data"),
        }
        previous_environment = {key: os.environ.get(key) for key in environment}
        os.environ.update(environment)
        try:
            roots = [*default_roots(), qoder_root()]
            for root in roots:
                shutil.copytree(source, root)

            matching = check(source=source, roots=roots, verify_codex_agent_roles=False)
            evidence["matching_six_roots"] = matching
            if not matching.get("ok"):
                failures.append("matching_six_roots:expected_pass")
            if matching.get("receipt_sha256") != _canonical_sha256(matching):
                failures.append("matching_six_roots:receipt_digest_mismatch")
            if matching.get("source_version") != "fixture":
                failures.append("matching_six_roots:source_version_mismatch")
            if not isinstance(matching.get("projection_sha256"), str):
                failures.append("matching_six_roots:projection_digest_missing")

            custom_root = fixture / "custom-root"
            shutil.copytree(source, custom_root)
            try:
                check(source=source, roots=[custom_root], verify_codex_agent_roles=False)
            except ValueError as exc:
                evidence["custom_root_rejected"] = str(exc)
            else:
                failures.append("custom_root_rejected:expected_setup_error")

            try:
                check(source=source, roots=[roots[0], roots[0]], verify_codex_agent_roles=False)
            except ValueError as exc:
                evidence["duplicate_roots_rejected"] = str(exc)
            else:
                failures.append("duplicate_roots_rejected:expected_setup_error")

            manifest_path = source / PROJECTION_MANIFEST
            original_manifest = manifest_path.read_text(encoding="utf-8")
            empty_manifest = json.loads(original_manifest)
            empty_manifest["projections"]["shared_agents"] = []
            manifest_path.write_text(json.dumps(empty_manifest), encoding="utf-8")
            try:
                check(source=source, roots=roots, verify_codex_agent_roles=False)
            except ValueError as exc:
                evidence["empty_projection_rejected"] = str(exc)
            else:
                failures.append("empty_projection_rejected:expected_setup_error")
            finally:
                manifest_path.write_text(original_manifest, encoding="utf-8")

            extra_path = roots[0] / "scripts" / "obsolete_loader.py"
            extra_path.write_text("# stale installed body\n", encoding="utf-8")
            extra = check(source=source, roots=roots, verify_codex_agent_roles=False)
            evidence["extra_file_rejected"] = extra
            if extra.get("ok") or not extra.get("extra_files"):
                failures.append("extra_file_rejected:expected_fail")
            extra_path.unlink()

            outside = fixture / "outside-runtime.py"
            outside.write_text("VALUE = 1\n", encoding="utf-8")
            linked_path = roots[1] / "scripts" / "runtime.py"
            linked_path.unlink()
            try:
                linked_path.symlink_to(outside)
            except OSError as exc:
                evidence["target_symlink_rejected"] = {
                    "status": "SKIP",
                    "reason": f"symlink_fixture_unavailable:{type(exc).__name__}:{exc}",
                }
                shutil.copy2(source / "scripts" / "runtime.py", linked_path)
            else:
                linked = check(source=source, roots=roots, verify_codex_agent_roles=False)
                evidence["target_symlink_rejected"] = linked
                if linked.get("ok") or not linked.get("unsafe_paths"):
                    failures.append("target_symlink_rejected:expected_fail")
                linked_path.unlink()
                shutil.copy2(source / "scripts" / "runtime.py", linked_path)

            (roots[3] / "scripts" / "runtime.py").write_text(
                "VALUE = 2\n",
                encoding="utf-8",
            )
            drift = check(source=source, roots=roots, verify_codex_agent_roles=False)
            evidence["single_file_drift"] = drift
            if drift.get("ok") or not drift.get("drift"):
                failures.append("single_file_drift:expected_fail")
            (roots[3] / "scripts" / "runtime.py").write_text(
                "VALUE = 1\n",
                encoding="utf-8",
            )

            checker_copy = roots[5] / CHECKER_RELATIVE
            checker_copy.write_text("# forbidden installed checker\n", encoding="utf-8")
            projected_checker = check(source=source, roots=roots, verify_codex_agent_roles=False)
            evidence["checker_not_projected"] = projected_checker
            if projected_checker.get("ok") or not projected_checker.get(
                "forbidden_checker_copies"
            ):
                failures.append("checker_not_projected:expected_fail")
            checker_copy.unlink()

            missing_root = str(roots[3])
            shutil.rmtree(roots[3])
            missing = check(source=source, roots=roots, verify_codex_agent_roles=False)
            evidence["missing_root"] = missing
            if missing.get("ok") or missing_root not in missing.get("missing_roots", []):
                failures.append("missing_root:expected_fail")

            # ---- M2 投影子门 RED：R-P1 receipt 缺失不得回落硬编码五根（计划书 §4.4 第 6 条）----
            # 期望：main 默认路径（无 --root 且无已验证 receipt）必须 fail closed，
            # reason=selected_roots_receipt_required；现状回落 default_roots() 直接验证 → RED FAIL。
            import io
            import contextlib
            no_receipt_buffer = io.StringIO()
            with contextlib.redirect_stdout(no_receipt_buffer):
                no_receipt_rc = main(["--json", "--source", str(source)])
            try:
                no_receipt_main = json.loads(no_receipt_buffer.getvalue())
            except json.JSONDecodeError:
                no_receipt_main = {
                    "ok": False,
                    "status": "ERROR",
                    "failures": [f"unparseable:{no_receipt_buffer.getvalue()[:200]}"],
                }
            evidence["selected_roots_receipt_required"] = no_receipt_main
            if no_receipt_main.get("ok") or "selected_roots_receipt_required" not in " ".join(
                str(item) for item in no_receipt_main.get("failures", [])
            ):
                failures.append("selected_roots_receipt_required:expected_fail")

            # ---- M2 投影子门 RED：R-P2 默认路径必须从 receipt selected_roots 派生根（计划书 §4.4 第 3 条）----
            # 期望：fixture home 含合法 receipt（selected_roots=[custom_root]）时，
            # main 默认路径以 receipt 派生 roots 验证（roots 含 custom_root），而非硬编码五根；
            # 现状 main() 无条件回落 default_roots() → RED FAIL。
            r2_receipt_root = fixture / "receipt-selected-root"
            shutil.copytree(source, r2_receipt_root)
            r2_receipt = fixture / "home" / ".agents" / "install-receipts" / "decretum-matrix" / "valid.json"
            r2_receipt.parent.mkdir(parents=True, exist_ok=True)
            r2_receipt.write_text(
                json.dumps(
                    {
                        "schema": "court.install_current_agent_copy.result.v1",
                        "status": "APPLIED",
                        "selection_policy": "receipt",
                        "primary_root": str(fixture / "home" / ".agents"),
                        "current_tool": "fixture",
                        "current_tool_root": str(fixture / "home" / ".agents"),
                        "current_tool_root_proof": "fixture-ok",
                        "status": "APPLIED",
                        "explicit_extra_targets": [str(r2_receipt_root)],
                        "selected_roots": [str(r2_receipt_root)],
                        "authority": "fixture-authority",
                        "receipt_sha256": "fixture-receipt-sha256",
                    }
                ),
                encoding="utf-8",
            )
            r2_buffer = io.StringIO()
            with contextlib.redirect_stdout(r2_buffer):
                r2_rc = main(["--json", "--source", str(source)])
            try:
                r2_main = json.loads(r2_buffer.getvalue())
            except json.JSONDecodeError:
                r2_main = {
                    "ok": False,
                    "status": "ERROR",
                    "failures": [f"unparseable:{r2_buffer.getvalue()[:200]}"],
                }
            evidence["governed_roots_not_receipt_derived"] = r2_main
            r2_roots = [str(item) for item in r2_main.get("roots", [])]
            if not r2_main.get("ok") or str(r2_receipt_root) not in r2_roots:
                failures.append("governed_roots_not_receipt_derived:expected_fail")
            r2_receipt.unlink(missing_ok=True)

            # ---- M2 投影子门 RED：R-P4 install receipt 缺 §4.4 强制字段必须 fail closed（计划书 §4.4 第 4 条）----
            # 期望：含 receipt 但缺 selection_policy/current_tool_root_proof/selected_roots 等字段时，
            # checker 拒绝（reason=install_receipt_missing_required_fields）；现状无 receipt 读取/字段校验 → RED FAIL。
            r4_receipt = fixture / "home" / ".agents" / "install-receipts" / "decretum-matrix" / "invalid.json"
            r4_receipt.parent.mkdir(parents=True, exist_ok=True)
            r4_receipt.write_text(
                json.dumps(
                    {
                        "schema": "court.install_current_agent_copy.result.v1",
                        "status": "APPLIED",
                    }
                ),
                encoding="utf-8",
            )
            r4_buffer = io.StringIO()
            with contextlib.redirect_stdout(r4_buffer):
                r4_rc = main(["--json", "--source", str(source)])
            try:
                r4_main = json.loads(r4_buffer.getvalue())
            except json.JSONDecodeError:
                r4_main = {
                    "ok": False,
                    "status": "ERROR",
                    "failures": [f"unparseable:{r4_buffer.getvalue()[:200]}"],
                }
            evidence["install_receipt_missing_required_fields"] = r4_main
            if r4_main.get("ok") or "install_receipt_missing_required_fields" not in " ".join(
                str(item) for item in r4_main.get("failures", [])
            ):
                failures.append("install_receipt_missing_required_fields:expected_fail")
            r4_receipt.unlink(missing_ok=True)

            # ---- M2 迁移子门 RED：R-M4 shard 断言必须有 consumer 与 evidence（计划书 L188）----
            # 期望：传无 consumer/evidence 成对支撑的 shard 断言时 checker 拒绝
            # （reason=shard_without_consumer_or_evidence）；现状 check() 无 shard 校验
            # （参数未实现 → TypeError 受控捕获）→ RED FAIL。GREEN 实现 shard_assertions 校验后转绿。
            try:
                r4_shard = check(
                    source=source,
                    roots=roots,
                    shard_assertions=[
                        {"path": "scripts/extra-shard.py", "kind": "extra"}
                    ],
                    verify_codex_agent_roles=False,
                )
            except TypeError as exc:
                evidence["shard_without_consumer_or_evidence"] = {
                    "status": "RED_NOT_IMPLEMENTED",
                    "error": f"{type(exc).__name__}:{exc}",
                }
                failures.append("shard_without_consumer_or_evidence:expected_fail")
            except ValueError as exc:
                # GREEN 后：check() 校验 shard_assertions 缺 consumer/evidence → raise 该 reason。
                evidence["shard_without_consumer_or_evidence"] = {
                    "status": "REJECTED",
                    "error": str(exc),
                }
                if "shard_without_consumer_or_evidence" not in str(exc):
                    failures.append("shard_without_consumer_or_evidence:unexpected_reason")
            else:
                evidence["shard_without_consumer_or_evidence"] = r4_shard
                if r4_shard.get("ok") or "shard_without_consumer_or_evidence" not in " ".join(
                    str(item) for item in r4_shard.get("failures", [])
                ):
                    failures.append("shard_without_consumer_or_evidence:expected_fail")

            # ---- M3 RED（R-I1）：install_current_agent_copy APPLY 必须产出含 §4.4 全字段的
            # install receipt（计划书 §4.4 第 4 条 + checker 消费端 INSTALL_RECEIPT_REQUIRED_FIELDS）。
            # 期望：write=True 安装成功后返回结果含 receipt（schema=court.install_current_agent_copy.result.v1，
            # 含 selection_policy/primary_root/current_tool/current_tool_root/current_tool_root_proof/
            # status/explicit_extra_targets/selected_roots/authority/receipt_sha256 十字段）；
            # 现状 install_current_agent_copy APPLY 结果无 receipt 字段（生成端缺失）→ RED FAIL。
            try:
                import sys as _install_sys
                import importlib.util as _il_util

                _install_spec = _il_util.spec_from_file_location(
                    "install_current_agent_copy",
                    str(
                        Path(__file__).resolve().parents[1]
                        / "install_current_agent_copy.py"
                    ),
                )
                _install_mod = None
                if _install_spec is not None and _install_spec.loader is not None:
                    _install_mod = _il_util.module_from_spec(_install_spec)
                    _install_sys.modules["install_current_agent_copy"] = _install_mod
                    _install_spec.loader.exec_module(_install_mod)
                if _install_mod is None:
                    raise ImportError("install_current_agent_copy not importable")
                _r1_home = fixture / "r1-install-home"
                _r1_tool_root = _r1_home / ".agents" / "skills" / "decretum-matrix"
                _r1_tool_root.mkdir(parents=True)
                _r1_applied = _install_mod.install_current_agent_copy(
                    source_root=source,
                    home_root=_r1_home,
                    current_tool="codex",
                    explicit_tools=[],
                    tool_roots={"codex": _r1_tool_root},
                    projection_manifest=source
                    / "references"
                    / "manifests"
                    / "install-projection.v1.json",
                    write=True,
                    fanout=False,
                )
                _r1_receipt = _r1_applied.get("install_receipt") or {}
                evidence["install_receipt_generated"] = {
                    "applied_ok": _r1_applied.get("ok"),
                    "receipt_present": bool(_r1_receipt),
                    "receipt_schema": _r1_receipt.get("schema"),
                    "missing_fields": [
                        field
                        for field in INSTALL_RECEIPT_REQUIRED_FIELDS
                        if field not in _r1_receipt
                    ],
                }
                if (
                    _r1_applied.get("ok") is not True
                    or not _r1_receipt
                    or _r1_receipt.get("schema") != "court.install_current_agent_copy.result.v1"
                    or any(
                        field not in _r1_receipt
                        for field in INSTALL_RECEIPT_REQUIRED_FIELDS
                    )
                ):
                    failures.append("install_receipt_generated:expected_fail")
            except (OSError, ValueError, ImportError) as exc:
                evidence["install_receipt_generated"] = {
                    "status": "RED_NOT_IMPLEMENTED",
                    "error": f"{type(exc).__name__}:{exc}",
                }
                failures.append("install_receipt_generated:expected_fail")
        finally:
            for key, value in previous_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    # M2 投影子门 GREEN：E8 确定性——fixture 随机路径归一化为 <fixture> 占位符，
    # 使 evidence digest 双跑逐字节一致（charter ⑥ 要求；不改任何断言语义，仅归一化序列化面）。
    def _normalize_fixture_paths(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: _normalize_fixture_paths(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_normalize_fixture_paths(item) for item in value]
        if isinstance(value, str):
            return value.replace(str(fixture), "<fixture>").replace(
                str(fixture).lower(), "<fixture>"
            )
        return value

    return {
        "schema": "court.active_copy_hashes_self_test.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "evidence": _normalize_fixture_paths(evidence),
        "failures": failures,
    }


def _load_latest_install_receipt(home: Path) -> dict[str, Any] | None:
    """读取 ~/.agents/install-receipts/decretum-matrix/ 下最新 JSON receipt；无则返回 None。"""
    receipts_dir = home / ".agents" / INSTALL_RECEIPTS_RELATIVE
    if not receipts_dir.is_dir():
        return None
    candidates = sorted(
        receipts_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime_ns if p.is_file() else 0,
        reverse=True,
    )
    if not candidates:
        return None
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def _missing_receipt_fields(receipt: dict[str, Any]) -> list[str]:
    return [field for field in INSTALL_RECEIPT_REQUIRED_FIELDS if field not in receipt]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=[],
        help="Skill root to verify; repeatable. Defaults to receipt-selected roots (plan book §4.4).",
    )
    parser.add_argument("--include-qoder", action="store_true")
    parser.add_argument(
        "--projection",
        choices=("shared_agents", "portable_current_tool"),
        default="shared_agents",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        result = _self_test()
    else:
        explicit_roots = list(args.root)
        receipt_roots: list[Path] | None = None
        if not explicit_roots:
            # M2 投影子门 GREEN：默认路径必须从已验证 receipt 读取 selected_roots；
            # 无 receipt → fail closed（selected_roots_receipt_required）；
            # receipt 缺 §4.4 强制字段 → fail closed（install_receipt_missing_required_fields）。
            try:
                receipt = _load_latest_install_receipt(Path.home())
            except (OSError, json.JSONDecodeError) as exc:
                result = {
                    "schema": "court.active_copy_hashes.v2",
                    "ok": False,
                    "status": "FAIL",
                    "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                    "failures": [f"install_receipt_unreadable:{type(exc).__name__}:{exc}"],
                }
                return 1 if args.json else 0
            if receipt is None:
                result = {
                    "schema": "court.active_copy_hashes.v2",
                    "ok": False,
                    "status": "FAIL",
                    "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                    "failures": ["selected_roots_receipt_required"],
                }
            else:
                missing = _missing_receipt_fields(receipt)
                if missing:
                    result = {
                        "schema": "court.active_copy_hashes.v2",
                        "ok": False,
                        "status": "FAIL",
                        "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                        "failures": [
                            "install_receipt_missing_required_fields:" + ",".join(missing)
                        ],
                    }
                else:
                    try:
                        receipt_roots = [
                            Path(item) for item in receipt.get("selected_roots", [])
                        ]
                    except TypeError as exc:
                        result = {
                            "schema": "court.active_copy_hashes.v2",
                            "ok": False,
                            "status": "FAIL",
                            "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                            "failures": [f"install_receipt_selected_roots_invalid:{exc}"],
                        }
                    else:
                        roots = list(receipt_roots)
                        if args.include_qoder:
                            # 仅当 receipt selected_roots 已含 Qoder 时允许；否则 fail closed。
                            if not any(
                                _root_identity(Path(item))
                                == _root_identity(qoder_root())
                                for item in receipt.get("selected_roots", [])
                            ):
                                result = {
                                    "schema": "court.active_copy_hashes.v2",
                                    "ok": False,
                                    "status": "FAIL",
                                    "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                                    "failures": ["include_qoder_legacy_switch_rejected"],
                                }
                                roots = []
                            else:
                                roots.append(qoder_root())
                        if not roots:
                            result = {
                                "schema": "court.active_copy_hashes.v2",
                                "ok": False,
                                "status": "FAIL",
                                "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                                "failures": ["selected_roots_receipt_required"],
                            }
                        else:
                            try:
                                result = check(
                                    source=args.source,
                                    roots=roots,
                                    projection=args.projection,
                                    receipt_roots=receipt_roots,
                                )
                            except (OSError, ValueError, json.JSONDecodeError) as exc:
                                result = {
                                    "schema": "court.active_copy_hashes.v2",
                                    "ok": False,
                                    "status": "ERROR",
                                    "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                                    "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
                                }
        else:
            roots = explicit_roots
            if args.include_qoder:
                roots.append(qoder_root())
            try:
                result = check(
                    source=args.source,
                    roots=roots,
                    projection=args.projection,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result = {
                    "schema": "court.active_copy_hashes.v2",
                    "ok": False,
                    "status": "ERROR",
                    "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                    "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
                }
    if args.json or args.self_test:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"ACTIVE_COPY_HASHES={result['status']} "
            f"roots={len(result.get('roots', []))} files={result.get('checked_files', 0)}"
        )
        for item in result.get("drift", [])[:50]:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        for root in result.get("missing_roots", []):
            print(f"MISSING_ROOT {root}")
        for path in result.get("forbidden_checker_copies", []):
            print(f"FORBIDDEN_CHECKER_COPY {path}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

