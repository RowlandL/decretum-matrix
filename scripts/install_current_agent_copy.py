#!/usr/bin/env python3
"""Manifest-gated installation for ``.agents`` plus the current agent tool.

The public entry point is dependency-injected.  It does not discover or mutate
real host configuration by itself; configuration work is possible only through
the adapter supplied by the caller.  This keeps tests and blank-host planning
safe while using the canonical ``decretum-matrix`` physical install directory.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from typing import Any
import uuid


sys.dont_write_bytecode = True


RESULT_SCHEMA = "court.install_current_agent_copy.result.v1"
PROJECTION_SCHEMA = "court.install_projection.v1"
CONFIG_REQUEST_SCHEMA = "court.blank_host_configuration.request.v1"
IDENTITY_MANIFEST_RELATIVE = "references/manifests/skill-identity.v1.json"

POLICY_EXPECTED = {
    "required_target": ".agents",
    "default_optional_target": "current_agent_tool_only",
    "extra_targets": "explicit_latest_user_request_only",
    "fanout": "forbidden",
}
LOADED_IDENTITY_EXPECTED = {
    "display_name": "Dercretum-Matrix",
    "canonical_skill_name": "decretum-matrix",
    "canonical_invocation": "$decretum-matrix",
    "community_license": "AGPL-3.0-only",
    "rights_owner": "孙华清",
    "maintainer_github": "@RowlandL",
    "maintainer_github_id": 42199880,
}
LOCATOR_POLICY_EXPECTED = {
    "install_directory_name": "decretum-matrix",
    "legacy_install_directory_name": "court-capability-router",
    "legacy_install_locator_policy": "absent_or_same_physical_authority",
    "shiguan_namespace": "court-capability-router",
    "directory_basename_may_differ_from_skill_name": False,
    "rename_policy": "rename_install_directory_preserve_shiguan_namespace",
}
LEGACY_INSTALL_DIRECTORY_NAME = "court-capability-router"
FORBIDDEN_PROJECTION_PREFIXES = (
    ("references", "agente-logs"),
    ("references", "court-runtime"),
    ("references", "memory-decisions"),
    ("references", "shiguan-imports"),
    ("references", "shiguan-tree"),
)
PROTECTED_SHARED_AGENT_PATHS = {
    "references/shiguan-index.jsonl",
    "references/shiguan-knowledge-graph.json",
    "references/shiguan-tree/_index.md",
    "references/shiguan-tree/capability-index/_index.md",
}
PROTECTED_SHARED_AGENT_CONTRACT_SHA256 = (
    "36af654a6c1ca18b16f2479fc77cdde2666d796070e2cb47ff52401a65722e08"
)

_MISSING = object()


class _InstallContractError(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason


def _validate_source_package_sha256(value: object | None) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _InstallContractError("source_package_sha256_invalid")
    return value


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or candidate.drive:
        return False
    return all(part not in {"", ".", ".."} for part in candidate.parts)


def _within(path: Path, root: Path) -> bool:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _read_json(path: Path, *, reason: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _InstallContractError(reason, f"{type(exc).__name__}:{exc}") from exc
    if not isinstance(value, dict):
        raise _InstallContractError(reason, "json_root_not_object")
    return value


def _validate_identity(identity: dict[str, object]) -> None:
    for field, expected in LOADED_IDENTITY_EXPECTED.items():
        if identity.get(field) != expected:
            raise _InstallContractError(
                "identity_mismatch",
                f"{field}:{identity.get(field)!r}!={expected!r}",
            )
    locator = identity.get("locator_policy")
    if not isinstance(locator, dict):
        raise _InstallContractError("identity_mismatch", "locator_policy_not_object")
    for field, expected in LOCATOR_POLICY_EXPECTED.items():
        if locator.get(field) != expected:
            raise _InstallContractError(
                "identity_mismatch",
                f"locator_policy.{field}:{locator.get(field)!r}!={expected!r}",
            )
    if any("email" in str(key).casefold() for key in identity):
        raise _InstallContractError("identity_mismatch", "contact_field_forbidden")


def _load_projection_contract(
    source_root: Path,
    projection_manifest: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    source_root = source_root.resolve(strict=False)
    projection_manifest = projection_manifest.resolve(strict=False)
    if not _within(projection_manifest, source_root):
        raise _InstallContractError("projection_manifest_outside_source")
    manifest = _read_json(projection_manifest, reason="projection_manifest_invalid")
    if manifest.get("schema") != PROJECTION_SCHEMA:
        raise _InstallContractError("projection_manifest_invalid", "schema_mismatch")
    if manifest.get("policy") != POLICY_EXPECTED:
        raise _InstallContractError("projection_manifest_invalid", "policy_mismatch")

    identity_relative = manifest.get("identity_manifest")
    if identity_relative != IDENTITY_MANIFEST_RELATIVE or not _safe_relative(
        identity_relative
    ):
        raise _InstallContractError(
            "projection_manifest_invalid", "identity_manifest_invalid"
        )

    projections = manifest.get("projections")
    if not isinstance(projections, dict):
        raise _InstallContractError("projection_manifest_invalid", "projections_missing")
    for name in ("shared_agents", "portable_current_tool", "repository_only"):
        values = projections.get(name)
        if not isinstance(values, list) or any(
            not _safe_relative(item) for item in values
        ):
            raise _InstallContractError(
                "projection_manifest_invalid", f"projection_invalid:{name}"
            )
    portable = {
        item
        for name in ("shared_agents", "portable_current_tool")
        for item in projections[name]
        if isinstance(item, str)
    }
    repository_only = {
        item for item in projections["repository_only"] if isinstance(item, str)
    }
    if portable & repository_only:
        raise _InstallContractError(
            "projection_manifest_invalid", "repository_only_overlap"
        )
    protected = manifest.get("protected_shared_agents_seeds")
    if not isinstance(protected, dict) or hashlib.sha256(json.dumps(
        protected, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest() != PROTECTED_SHARED_AGENT_CONTRACT_SHA256 or set(protected) != PROTECTED_SHARED_AGENT_PATHS or any(
        not _safe_relative(path)
        or not isinstance(digest, str)
        or len(digest) != 64
        or digest != digest.lower()
        or any(character not in "0123456789abcdef" for character in digest)
        for path, digest in protected.items()
    ):
        raise _InstallContractError(
            "projection_manifest_invalid", "protected_seeds_invalid"
        )
    if portable & set(protected):
        raise _InstallContractError(
            "projection_manifest_invalid", "protected_seed_projection_overlap"
        )

    bindings = manifest.get("persistent_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise _InstallContractError(
            "projection_manifest_invalid", "persistent_bindings_missing"
        )
    seen_roles: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise _InstallContractError(
                "projection_manifest_invalid", "persistent_binding_not_object"
            )
        role_key = binding.get("role_key")
        if not isinstance(role_key, str) or not role_key or role_key in seen_roles:
            raise _InstallContractError(
                "projection_manifest_invalid", "persistent_binding_role_invalid"
            )
        seen_roles.add(role_key)
        for field in ("profile_source", "dossier_path", "court_skill_path"):
            if not _safe_relative(binding.get(field)):
                raise _InstallContractError(
                    "persisted_path_invalid", f"{role_key}:{field}"
                )

    identity_path = source_root / Path(str(identity_relative))
    if not _within(identity_path, source_root):
        raise _InstallContractError("identity_manifest_outside_source")
    identity = _read_json(identity_path, reason="identity_manifest_invalid")
    _validate_identity(identity)
    return manifest, identity


def _failure(
    reason: str,
    *,
    detail: str | None = None,
    targets: list[Path] | None = None,
) -> dict[str, object]:
    return {
        "schema": RESULT_SCHEMA,
        "ok": False,
        "status": "REJECTED",
        "reason": reason,
        "reason_codes": [reason],
        "errors": [detail or reason],
        "targets": [str(path) for path in targets or []],
        "pending_body_accessed": False,
        "real_host_configuration_accessed": False,
    }


def _select_targets(
    *,
    home_root: Path,
    current_tool: str,
    explicit_tools: list[str],
    tool_roots: dict[str, Path],
) -> list[tuple[str, Path, str]]:
    home_root = home_root.resolve(strict=False)
    selected: list[tuple[str, Path, str]] = [
        (
            "shared_agents",
            home_root / ".agents" / "skills" / "decretum-matrix",
            "shared_agents",
        )
    ]
    seen = {selected[0][1].resolve(strict=False)}

    requested: list[str] = []
    if current_tool in tool_roots:
        requested.append(current_tool)
    for tool in explicit_tools:
        if tool not in tool_roots:
            raise _InstallContractError("explicit_tool_unknown", tool)
        if tool not in requested:
            requested.append(tool)

    for tool in requested:
        root = Path(tool_roots[tool]).resolve(strict=False)
        if root in seen:
            continue
        selected.append((tool, root, "portable_current_tool"))
        seen.add(root)

    for _label, target, _projection in selected:
        if not _within(target, home_root):
            raise _InstallContractError("target_outside_home", str(target))
        if target.name != LOCATOR_POLICY_EXPECTED["install_directory_name"]:
            raise _InstallContractError("physical_install_locator_drift", str(target))
    return selected


def _is_junction(path: Path) -> bool:
    probe = getattr(path, "is_junction", None)
    return bool(callable(probe) and probe())


class WindowsJunctionTransactionAdapter:
    def checkpoint(self, *_):
        pass

    def _target(self, p):
        return p.resolve(strict=True)

    def _occupied(self, p):
        return p.exists() or p.is_symlink() or _is_junction(p)

    def _create(self, p, t):
        if os.name != "nt" or not t.is_dir() or self._occupied(p):
            raise RuntimeError("junction")
        p.parent.mkdir(parents=True, exist_ok=True)
        code = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/j", str(p), str(t)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        if code or not _is_junction(p):
            raise RuntimeError(f"junction:{code}")

    def _remove(self, p):
        if _is_junction(p):
            p.rmdir()
        elif p.is_symlink():
            p.unlink()
        elif p.exists():
            raise RuntimeError("alias")

    def prepare_alias(self, **x):
        l, c, t = (
            x[k] for k in ("legacy_alias", "canonical_alias", "physical_root")
        )
        p = c.with_name(f".{c.name}.alias-prepared")
        if (
            l.parent != c.parent
            or l.name != LEGACY_INSTALL_DIRECTORY_NAME
            or c.name != LOCATOR_POLICY_EXPECTED["install_directory_name"]
            or not _is_junction(l)
            or any(map(self._occupied, (c, p)))
        ):
            raise RuntimeError("alias")
        r = self._target(l)
        expected = t.with_name(LEGACY_INSTALL_DIRECTORY_NAME).resolve(strict=False)
        if not r.is_dir() or r.resolve(strict=False) != expected:
            raise RuntimeError("target")
        return tuple(map(str, (l, c, t, p, r)))

    def commit_alias(self, receipt):
        l, c, t, p, _ = map(Path, receipt)
        if not t.is_dir():
            raise RuntimeError("physical")
        self._create(p, t)
        self._remove(l)
        os.replace(p, c)

    def rollback_alias(self, receipt):
        l, c, _, p, t = map(Path, receipt)
        self._remove(c)
        self._remove(p)
        if not self._occupied(l):
            self._create(l, t)


def _install_root_transition_candidates(
    selected: list[tuple[str, Path, str]],
) -> list[dict[str, object]]:
    transitions: list[dict[str, object]] = []
    for _label, target, _projection in selected:
        legacy = target.with_name(LEGACY_INSTALL_DIRECTORY_NAME)
        legacy_present = legacy.exists() or legacy.is_symlink() or _is_junction(legacy)
        target_present = target.exists() or target.is_symlink() or _is_junction(target)
        if legacy_present and legacy.resolve(strict=False) != target.resolve(strict=False):
            if target_present:
                raise _InstallContractError("dual_physical_authority", str(legacy))
            if legacy.is_symlink() or _is_junction(legacy) or not legacy.is_dir():
                raise _InstallContractError("legacy_locator_conflict", str(legacy))
            transitions.append(
                {
                    "mode": "LEGACY_MIGRATION",
                    "source_root": legacy,
                    "restore_root": legacy,
                    "canonical_root": target,
                }
            )
            continue
        if target_present:
            if target.is_symlink() or _is_junction(target) or not target.is_dir():
                raise _InstallContractError("canonical_physical_root_invalid", str(target))
            transitions.append(
                {
                    "mode": "CANONICAL_UPDATE",
                    "source_root": target,
                    "restore_root": target,
                    "canonical_root": target,
                }
            )
    return transitions


def _required_root_transitions(
    candidates: list[dict[str, object]],
    operations: list[tuple[Path, bytes, bytes | None]],
) -> list[dict[str, object]]:
    required: list[dict[str, object]] = []
    for candidate in candidates:
        canonical = Path(str(candidate["canonical_root"]))
        if candidate.get("mode") == "LEGACY_MIGRATION" or any(
            _within(path, canonical) for path, _payload, _previous in operations
        ):
            required.append(candidate)
    return required


def _expand_projection(
    source_root: Path,
    entries: list[object],
) -> list[tuple[PurePosixPath, bytes]]:
    expanded: dict[str, bytes] = {}
    for value in entries:
        if not _safe_relative(value):
            raise _InstallContractError("projection_source_invalid", repr(value))
        relative = PurePosixPath(str(value))
        relative_parts = tuple(part.casefold() for part in relative.parts)
        if any(
            prefix[: len(relative_parts)] == relative_parts
            for prefix in FORBIDDEN_PROJECTION_PREFIXES
        ):
            raise _InstallContractError(
                "projection_private_surface_forbidden", relative.as_posix()
            )
        if "__pycache__" in relative_parts or relative.suffix.casefold() == ".pyc":
            raise _InstallContractError(
                "projection_bytecode_forbidden", relative.as_posix()
            )
        source = source_root / Path(relative.as_posix())
        if not _within(source, source_root):
            raise _InstallContractError("projection_source_escape", relative.as_posix())
        if source.is_symlink():
            raise _InstallContractError("projection_symlink_forbidden", relative.as_posix())
        if source.is_file():
            expanded[relative.as_posix()] = source.read_bytes()
            continue
        if source.is_dir():
            for child in sorted(source.rglob("*")):
                if child.is_symlink():
                    raise _InstallContractError(
                        "projection_symlink_forbidden",
                        child.relative_to(source_root).as_posix(),
                    )
                if not child.is_file():
                    continue
                child_relative = child.relative_to(source_root).as_posix()
                child_parts = tuple(
                    part.casefold() for part in PurePosixPath(child_relative).parts
                )
                if "__pycache__" in child_parts or child.suffix.casefold() == ".pyc":
                    continue
                if any(
                    child_parts[: len(prefix)] == prefix
                    for prefix in FORBIDDEN_PROJECTION_PREFIXES
                ):
                    continue
                if not _safe_relative(child_relative) or not _within(
                    child, source_root
                ):
                    raise _InstallContractError(
                        "projection_source_escape", child_relative
                    )
                expanded[child_relative] = child.read_bytes()
            continue
        raise _InstallContractError(
            "projection_source_missing", relative.as_posix()
        )
    return [(PurePosixPath(key), expanded[key]) for key in sorted(expanded)]


def _parent_chain_is_directory(path: Path, stop: Path) -> bool:
    current = path.parent
    stop = stop.resolve(strict=False)
    while current.resolve(strict=False) != stop:
        if current.exists() and not current.is_dir():
            return False
        if stop not in current.resolve(strict=False).parents:
            return False
        current = current.parent
    return not stop.exists() or stop.is_dir()


def _plan_projection_writes(
    *,
    source_root: Path,
    manifest: dict[str, object],
    selected: list[tuple[str, Path, str]],
    migration_sources: dict[Path, Path] | None = None,
) -> tuple[list[tuple[Path, bytes, bytes | None]], dict[str, int]]:
    projections = manifest["projections"]
    assert isinstance(projections, dict)
    expanded: dict[str, list[tuple[PurePosixPath, bytes]]] = {}
    operations: list[tuple[Path, bytes, bytes | None]] = []
    identical = 0
    replacements = 0
    seed_contract = manifest["protected_shared_agents_seeds"]
    assert isinstance(seed_contract, dict)
    protected: list[tuple[PurePosixPath, bytes]] = []
    for name, expected in sorted(seed_contract.items()):
        relative = PurePosixPath(name)
        source = source_root / Path(name)
        if not _within(source, source_root) or source.is_symlink() or not source.is_file():
            raise _InstallContractError("protected_anchor_source_invalid", name)
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            raise _InstallContractError("protected_anchor_source_drift", name)
        protected.append((relative, payload))
    protected_paths = {relative.as_posix() for relative, _payload in protected}
    for _label, target, projection_name in selected:
        migration_source = (migration_sources or {}).get(target.resolve(strict=False))
        inspection_root = migration_source or target
        if projection_name not in expanded:
            values = projections[projection_name]
            assert isinstance(values, list)
            expanded[projection_name] = _expand_projection(source_root, values)
        if projection_name != "shared_agents":
            for relative, _payload in protected:
                wrong_target = inspection_root / Path(relative.as_posix())
                if wrong_target.exists() or wrong_target.is_symlink():
                    raise _InstallContractError(
                        "protected_anchor_wrong_target", wrong_target.as_posix()
                    )
        entries = expanded[projection_name] + (
            protected if projection_name == "shared_agents" else []
        )
        for relative, payload in entries:
            destination = target / Path(relative.as_posix())
            existing = inspection_root / Path(relative.as_posix())
            if not _within(destination, target) or not _parent_chain_is_directory(
                destination, target
            ):
                raise _InstallContractError(
                    "target_path_escape", str(destination)
                )
            if existing.exists() or existing.is_symlink():
                if existing.is_symlink() or not existing.is_file():
                    raise _InstallContractError(
                        "target_conflict", existing.as_posix()
                    )
                previous = existing.read_bytes()
                if previous != payload:
                    if relative.as_posix() in protected_paths:
                        raise _InstallContractError(
                            "protected_anchor_drift", existing.as_posix()
                        )
                    if migration_source is None:
                        raise _InstallContractError(
                            "target_conflict", existing.as_posix()
                        )
                    operations.append((destination, payload, previous))
                    replacements += 1
                    continue
                identical += 1
                continue
            operations.append((destination, payload, None))
    return operations, {
        "create": len(operations) - replacements,
        "replace": replacements,
        "identical": identical,
    }


def _atomic_create(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.install-",
        dir=path.parent,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() or path.is_symlink():
            raise _InstallContractError("target_conflict", path.as_posix())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_replace_file(path: Path, payload: bytes) -> None:
    if path.is_symlink() or not path.is_file():
        raise _InstallContractError("target_conflict", path.as_posix())
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.install-",
        dir=path.parent,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _transaction_checkpoint(
    adapter: object | None,
    step: str,
    **evidence: object,
) -> None:
    if adapter is None:
        return
    checkpoint = getattr(adapter, "checkpoint", None)
    if not callable(checkpoint):
        raise _InstallContractError("install_transaction_adapter_invalid")
    checkpoint(step, evidence)


def _rollback_projection_writes(
    applied: list[tuple[Path, bytes | None]],
    selected: list[tuple[str, Path, str]],
) -> None:
    target_roots = [target.resolve(strict=False) for _label, target, _kind in selected]
    for path, previous in reversed(applied):
        if previous is None:
            if path.is_file() and not path.is_symlink():
                path.unlink()
        else:
            _atomic_replace_file(path, previous)
        parent = path.parent
        while previous is None and parent.resolve(strict=False) not in target_roots:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _apply_projection_writes(
    operations: list[tuple[Path, bytes, bytes | None]],
    selected: list[tuple[str, Path, str]],
    install_transaction_adapter: object | None = None,
) -> list[tuple[Path, bytes | None]]:
    applied: list[tuple[Path, bytes | None]] = []
    try:
        for path, payload, previous in operations:
            if previous is None:
                _atomic_create(path, payload)
            else:
                _atomic_replace_file(path, payload)
            applied.append((path, previous))
            if path.read_bytes() != payload:
                raise RuntimeError(f"projection verification failed: {path}")
            _transaction_checkpoint(
                install_transaction_adapter,
                "projection_file_applied",
                path=str(path),
            )
    except Exception:
        _rollback_projection_writes(applied, selected)
        raise
    return applied


def _unpublish_root_transitions(records: list[dict[str, object]]) -> None:
    for record in reversed(records):
        canonical = Path(str(record["canonical_root"]))
        stage = Path(str(record["stage_root"]))
        if (canonical.exists() or canonical.is_symlink()) and not (
            stage.exists() or stage.is_symlink()
        ):
            os.replace(canonical, stage)


def _restore_root_transitions(records: list[dict[str, object]]) -> None:
    for record in reversed(records):
        restore_root = Path(str(record["restore_root"]))
        stage = Path(str(record["stage_root"]))
        if stage.exists() or stage.is_symlink():
            if restore_root.exists() or restore_root.is_symlink():
                raise RuntimeError(
                    f"install rollback destination occupied: {restore_root}"
                )
            os.replace(stage, restore_root)


def _staged_selected(
    selected: list[tuple[str, Path, str]],
    records: list[dict[str, object]],
) -> list[tuple[str, Path, str]]:
    stages = {
        Path(str(record["canonical_root"])): Path(str(record["stage_root"]))
        for record in records
    }
    return [
        (label, stages.get(target, target), projection)
        for label, target, projection in selected
    ]


def _staged_operations(
    operations: list[tuple[Path, bytes, bytes | None]],
    records: list[dict[str, object]],
) -> list[tuple[Path, bytes, bytes | None]]:
    roots = [
        (Path(str(record["canonical_root"])), Path(str(record["stage_root"])))
        for record in records
    ]
    staged: list[tuple[Path, bytes, bytes | None]] = []
    for path, payload, previous in operations:
        destination = path
        for canonical, stage in roots:
            try:
                relative = path.relative_to(canonical)
            except ValueError:
                continue
            destination = stage / relative
            break
        staged.append((destination, payload, previous))
    return staged


def _apply_install_transaction(
    *,
    operations: list[tuple[Path, bytes, bytes | None]],
    selected: list[tuple[str, Path, str]],
    transitions: list[dict[str, object]],
    install_transaction_adapter: object | None,
    home_root: Path,
) -> list[dict[str, object]]:
    if install_transaction_adapter is not None and not callable(
        getattr(install_transaction_adapter, "checkpoint", None)
    ):
        raise _InstallContractError("install_transaction_adapter_invalid")
    records: list[dict[str, object]] = []
    applied: list[tuple[Path, bytes | None]] = []
    transaction_selected = selected
    alias_receipt: object | None = None
    try:
        hermes_root = next(
            (target for label, target, _kind in selected if label == "hermes"),
            None,
        )
        hermes_migration = hermes_root is not None and any(
            transition.get("mode") == "LEGACY_MIGRATION"
            and Path(str(transition["canonical_root"])).resolve(strict=False)
            == hermes_root.resolve(strict=False)
            for transition in transitions
        )
        alias_methods = tuple(
            getattr(install_transaction_adapter, name, None)
            for name in ("prepare_alias", "commit_alias", "rollback_alias")
        )
        if hermes_migration and any(callable(method) for method in alias_methods):
            if not all(callable(method) for method in alias_methods):
                raise _InstallContractError("install_transaction_adapter_invalid")
            alias_receipt = alias_methods[0](
                legacy_alias=home_root
                / ".hermes"
                / "skills"
                / LEGACY_INSTALL_DIRECTORY_NAME,
                canonical_alias=home_root
                / ".hermes"
                / "skills"
                / str(LOCATOR_POLICY_EXPECTED["install_directory_name"]),
                physical_root=hermes_root,
            )
        for transition in transitions:
            source_root = Path(str(transition["source_root"]))
            restore_root = Path(str(transition["restore_root"]))
            canonical = Path(str(transition["canonical_root"]))
            stage = canonical.parent / (
                f".{canonical.name}.install-migration-{uuid.uuid4().hex}"
            )
            record: dict[str, object] = {
                "mode": str(transition["mode"]),
                "source_root": str(source_root),
                "restore_root": str(restore_root),
                "canonical_root": str(canonical),
                "stage_root": str(stage),
                "status": "BACKED_UP",
            }
            if stage.exists() or stage.is_symlink():
                raise _InstallContractError("install_migration_stage_conflict", str(stage))
            if (canonical.exists() or canonical.is_symlink()) and canonical != source_root:
                raise _InstallContractError(
                    "dual_physical_authority",
                    str(canonical),
                )
            records.append(record)
            os.replace(source_root, stage)
            _transaction_checkpoint(
                install_transaction_adapter,
                "source_root_backed_up",
                source_root=str(source_root),
                restore_root=str(restore_root),
                stage_root=str(stage),
            )
        transaction_selected = _staged_selected(selected, records)
        applied = _apply_projection_writes(
            _staged_operations(operations, records),
            transaction_selected,
            install_transaction_adapter,
        )
        _transaction_checkpoint(
            install_transaction_adapter,
            "before_commit",
            migration_count=len(records),
            created_count=sum(1 for _path, previous in applied if previous is None),
        )
        for record in records:
            canonical = Path(str(record["canonical_root"]))
            stage = Path(str(record["stage_root"]))
            if canonical.exists() or canonical.is_symlink():
                raise _InstallContractError(
                    "dual_physical_authority",
                    str(canonical),
                )
            os.replace(stage, canonical)
            record["status"] = "PUBLISHED"
            _transaction_checkpoint(
                install_transaction_adapter,
                "canonical_published",
                canonical_root=str(canonical),
            )
        if alias_receipt is not None:
            alias_methods[1](alias_receipt)
    except Exception as exc:
        rollback_errors: list[str] = []
        try:
            _unpublish_root_transitions(records)
        except Exception as rollback_exc:
            rollback_errors.append(
                f"unpublish:{type(rollback_exc).__name__}:{rollback_exc}"
            )
        try:
            _rollback_projection_writes(applied, transaction_selected)
        except Exception as rollback_exc:
            rollback_errors.append(
                f"projection:{type(rollback_exc).__name__}:{rollback_exc}"
            )
        try:
            _restore_root_transitions(records)
        except Exception as rollback_exc:
            rollback_errors.append(
                f"restore:{type(rollback_exc).__name__}:{rollback_exc}"
            )
        if alias_receipt is not None:
            try:
                alias_methods[2](alias_receipt)
            except Exception as rollback_exc:
                rollback_errors.append(
                    f"alias:{type(rollback_exc).__name__}:{rollback_exc}"
                )
        if rollback_errors:
            raise _InstallContractError(
                "install_rollback_failed",
                f"{type(exc).__name__}:{exc};rollback:{'|'.join(rollback_errors)}",
            ) from exc
        raise _InstallContractError(
            "install_transaction_failed",
            f"{type(exc).__name__}:{exc}",
        ) from exc
    for record in records:
        record["status"] = "APPLIED"
    return records


def _nested_get(data: object, dotted_key: str) -> object:
    current = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _delta_gaps(
    path: Path,
    data: dict[str, object],
    delta: dict[str, object],
) -> list[str]:
    gaps: list[str] = []
    set_values = delta.get("set")
    if isinstance(set_values, dict):
        for dotted_key, expected in set_values.items():
            if not isinstance(dotted_key, str):
                continue
            actual = _nested_get(data, dotted_key)
            if actual != expected:
                actual_text = "<missing>" if actual is _MISSING else repr(actual)
                gaps.append(
                    f"{path.name}:{dotted_key}:expected={expected!r}:"
                    f"actual={actual_text}"
                )
    remove_values = delta.get("remove")
    if isinstance(remove_values, list):
        for dotted_key in remove_values:
            if not isinstance(dotted_key, str):
                continue
            actual = _nested_get(data, dotted_key)
            if actual is not _MISSING:
                gaps.append(
                    f"{path.name}:{dotted_key}:expected=<absent>:actual={actual!r}"
                )
    return gaps


def _read_configuration_state(
    adapter: Any,
    tool_class: str,
    paths: list[Path],
    delta: dict[str, object],
) -> tuple[list[str], list[str], list[dict[str, object]], dict[str, object]]:
    gaps: list[str] = []
    evidence: list[str] = []
    records: list[dict[str, object]] = []
    for path in paths:
        raw = adapter.read_effective_config(tool_class, path)
        record = raw if isinstance(raw, dict) else {"parse_ok": False, "parsed": None}
        records.append(record)
        evidence_value = record.get("evidence")
        if isinstance(evidence_value, str):
            evidence.append(evidence_value)
        parsed = record.get("parsed")
        if record.get("parse_ok") is True and isinstance(parsed, dict):
            gaps.extend(_delta_gaps(path, parsed, delta))
        else:
            gaps.append(f"{path.name}:parse_failed")
    runtime_raw = adapter.runtime_probe(tool_class)
    runtime_probe = runtime_raw if isinstance(runtime_raw, dict) else {
        "available": False,
        "standard_requirements_met": False,
    }
    return gaps, evidence, records, runtime_probe


def _refresh_configuration_result(
    config: dict[str, object],
    *,
    adapter: Any,
    tool_class: str,
    paths: list[Path],
    delta: dict[str, object],
) -> None:
    gaps, evidence, records, runtime_probe = _read_configuration_state(
        adapter, tool_class, paths, delta
    )
    parsed_ok = all(record.get("parse_ok") is True for record in records)
    verified = parsed_ok and not gaps
    standard_met = bool(
        verified
        and runtime_probe.get("available") is True
        and runtime_probe.get("standard_requirements_met") is True
    )
    config.update(
        {
            "gaps": gaps,
            "evidence": evidence,
            "effective_files": [str(path) for path in paths],
            "semantic_delta_verified": verified,
            "runtime_probe": runtime_probe,
            "standard_requirements_met": standard_met,
        }
    )


def _direct_effective_files_apply(
    *,
    adapter: Any,
    tool_class: str,
    paths: list[Path],
    delta: dict[str, object],
) -> tuple[bool, dict[str, object], str | None]:
    backups: list[object] = []
    transaction: dict[str, object] | None = None
    receipt: object | None = None
    try:
        for path in paths:
            backups.append(adapter.backup_effective_file(tool_class, path))
        transaction_raw = adapter.begin_effective_files_transaction(tool_class, paths)
        if not isinstance(transaction_raw, dict):
            raise RuntimeError("effective_transaction_not_object")
        transaction = transaction_raw
        for path in paths:
            adapter.write_effective_config(transaction, tool_class, path, delta)
        receipt = adapter.commit_effective_files_transaction(transaction, tool_class)
    except Exception as exc:
        if transaction is not None:
            try:
                adapter.rollback_effective_files_transaction(
                    transaction,
                    tool_class,
                    f"{type(exc).__name__}:{exc}",
                )
            except Exception as rollback_exc:
                return (
                    False,
                    {
                        "backup": backups or False,
                        "transaction": transaction,
                        "receipt": False,
                        "rollback": False,
                    },
                    f"{type(exc).__name__}:{exc};rollback:"
                    f"{type(rollback_exc).__name__}:{rollback_exc}",
                )
        return (
            False,
            {
                "backup": backups or False,
                "transaction": transaction or False,
                "receipt": False,
                "rollback": "restored" if transaction is not None else "not_needed",
            },
            f"{type(exc).__name__}:{exc}",
        )
    return (
        True,
        {
            "backup": backups,
            "transaction": transaction,
            "receipt": receipt,
            "rollback": "available_via_adapter",
        },
        None,
    )


def _configuration_base(
    *,
    tool_class: str,
    explicit_permission: bool,
    controller_probe: dict[str, object],
) -> dict[str, object]:
    return {
        "tool_class": tool_class,
        "standard_requirements_met": False,
        "status": "REMINDER_ONLY",
        "compliance_claimed": False,
        "mutation_authorized": False,
        "controller_probe": controller_probe,
        "mutation_path": "none",
        "upstream_attempt": "controller_probe"
        if controller_probe.get("present") is True
        else "controller_not_present",
        "upstream_result": deepcopy(controller_probe),
        "uncertainty": list(controller_probe.get("uncertainty", []))
        if isinstance(controller_probe.get("uncertainty"), list)
        else [],
        "explanation": "configuration requires explicit, certain, reversible authority",
        "effective_files": [],
        "gaps": [],
        "evidence": [],
        "semantic_delta_verified": False,
        "runtime_probe": {"available": False, "standard_requirements_met": False},
        "reversibility": {},
        "unrelated_install_blocked": False,
        "unrelated_task_blocked": False,
        "newest_explicit_change_permission": explicit_permission,
    }


def _remediate_blank_host_configuration(
    *,
    request: dict[str, object],
    adapter: Any,
    write: bool,
) -> dict[str, object]:
    if request.get("schema") != CONFIG_REQUEST_SCHEMA:
        raise _InstallContractError("blank_host_configuration_invalid", "schema")
    if request.get("blank_host") is not True:
        raise _InstallContractError("blank_host_configuration_invalid", "blank_host")
    tool_class = request.get("tool_class")
    delta = request.get("normalized_semantic_delta")
    if not isinstance(tool_class, str) or not isinstance(delta, dict):
        raise _InstallContractError("blank_host_configuration_invalid", "tool_or_delta")
    explicit_permission = request.get("newest_explicit_change_permission") is True
    direct_authority = request.get("direct_actual_file_change_authority") is True

    probe_raw = adapter.probe_controller(tool_class)
    if not isinstance(probe_raw, dict):
        raise _InstallContractError("blank_host_configuration_invalid", "probe")
    paths_raw = adapter.list_effective_files(tool_class)
    if not isinstance(paths_raw, list) or any(
        not isinstance(path, Path) for path in paths_raw
    ):
        raise _InstallContractError("blank_host_configuration_invalid", "effective_files")
    paths = [Path(path) for path in paths_raw]
    config = _configuration_base(
        tool_class=tool_class,
        explicit_permission=explicit_permission,
        controller_probe=probe_raw,
    )
    _refresh_configuration_result(
        config,
        adapter=adapter,
        tool_class=tool_class,
        paths=paths,
        delta=delta,
    )

    uncertainty = config["uncertainty"]
    assert isinstance(uncertainty, list)
    certainty = probe_raw.get("certainty")
    if isinstance(certainty, dict):
        for field, certain in certainty.items():
            if certain is False and field not in uncertainty:
                uncertainty.append(str(field))
    compatibility = probe_raw.get("compatibility")
    if (
        probe_raw.get("present") is True
        and isinstance(compatibility, dict)
        and compatibility.get("supported") is False
    ):
        reason = compatibility.get("reason")
        if isinstance(reason, str) and reason not in uncertainty:
            uncertainty.append(reason)

    if uncertainty:
        config.update(
            {
                "status": "NO_CHANGE_UNCERTAIN",
                "mutation_authorized": False,
                "compliance_claimed": False,
                "explanation": "uncertain controller/config semantics: "
                + ", ".join(str(item) for item in uncertainty),
            }
        )
        return config

    if not write or not explicit_permission:
        config.update(
            {
                "status": "REMINDER_ONLY",
                "mutation_authorized": False,
                "compliance_claimed": False,
                "explanation": "non-blocking reminder; no newest explicit configuration change authority",
            }
        )
        return config

    if config.get("standard_requirements_met") is True:
        config.update(
            {
                "status": "PASSED",
                "compliance_claimed": True,
                "mutation_authorized": True,
                "mutation_path": "already_compliant",
                "explanation": "effective files already satisfy the normalized semantics",
                "reversibility": {
                    "backup": "not_needed",
                    "transaction": "not_needed",
                    "receipt": "readback_verified",
                    "rollback": "not_needed",
                },
            }
        )
        return config

    config["mutation_authorized"] = True
    if probe_raw.get("present") is not True:
        success, reversibility, error = _direct_effective_files_apply(
            adapter=adapter,
            tool_class=tool_class,
            paths=paths,
            delta=delta,
        )
        config["reversibility"] = reversibility
        config["mutation_path"] = "direct_reversible_effective_files"
        if success:
            _refresh_configuration_result(
                config,
                adapter=adapter,
                tool_class=tool_class,
                paths=paths,
                delta=delta,
            )
        if success and config.get("standard_requirements_met") is True:
            config.update(
                {
                    "status": "PASSED",
                    "compliance_claimed": True,
                    "explanation": "direct transaction verified through actual-file reread and runtime probe",
                }
            )
        else:
            config.update(
                {
                    "status": "ROLLED_BACK",
                    "compliance_claimed": False,
                    "explanation": error or "direct transaction did not verify",
                }
            )
            _refresh_configuration_result(
                config,
                adapter=adapter,
                tool_class=tool_class,
                paths=paths,
                delta=delta,
            )
        return config

    controller_backup: object | None = None
    controller_transaction: dict[str, object] | None = None
    controller_receipt: object | None = None
    try:
        controller_backup = adapter.backup_controller_database(tool_class)
        transaction_raw = adapter.begin_controller_transaction(tool_class)
        if not isinstance(transaction_raw, dict):
            raise RuntimeError("controller_transaction_not_object")
        controller_transaction = transaction_raw
        adapter.update_controller_tool_block(
            controller_transaction,
            tool_class,
            delta,
        )
        controller_receipt = adapter.commit_controller_transaction(
            controller_transaction,
            tool_class,
        )
    except Exception as exc:
        if controller_transaction is not None and controller_backup is not None:
            try:
                adapter.rollback_controller_transaction(
                    controller_transaction,
                    tool_class,
                    f"{type(exc).__name__}:{exc}",
                )
            except Exception:
                pass
        config.update(
            {
                "status": "ROLLED_BACK",
                "compliance_claimed": False,
                "mutation_path": "cc_switch_upstream_then_effective_files",
                "explanation": f"controller transaction failed: {type(exc).__name__}:{exc}",
                "reversibility": {
                    "backup": controller_backup or False,
                    "transaction": controller_transaction or False,
                    "receipt": False,
                    "rollback": "attempted",
                },
            }
        )
        _refresh_configuration_result(
            config,
            adapter=adapter,
            tool_class=tool_class,
            paths=paths,
            delta=delta,
        )
        return config

    controller_reversibility = {
        "backup": controller_backup,
        "transaction": controller_transaction,
        "receipt": controller_receipt,
        "rollback": "available_via_adapter",
    }
    config.update(
        {
            "mutation_path": "cc_switch_upstream_then_effective_files",
            "upstream_attempt": "controller_transaction",
            "upstream_result": controller_receipt,
            "reversibility": controller_reversibility,
        }
    )
    _refresh_configuration_result(
        config,
        adapter=adapter,
        tool_class=tool_class,
        paths=paths,
        delta=delta,
    )
    if config.get("standard_requirements_met") is True:
        config.update(
            {
                "status": "PASSED",
                "compliance_claimed": True,
                "explanation": "controller-first mutation verified in actual effective files",
            }
        )
        return config

    if tool_class == "hermes" and direct_authority:
        direct_success, direct_reversibility, direct_error = (
            _direct_effective_files_apply(
                adapter=adapter,
                tool_class=tool_class,
                paths=paths,
                delta=delta,
            )
        )
        config["mutation_path"] = (
            "cc_switch_upstream_then_authorized_direct_effective_files"
        )
        config["reversibility"] = {
            "backup": [controller_backup, direct_reversibility.get("backup")],
            "transaction": [
                controller_transaction,
                direct_reversibility.get("transaction"),
            ],
            "receipt": [controller_receipt, direct_reversibility.get("receipt")],
            "rollback": "available_via_adapter",
        }
        if direct_success:
            _refresh_configuration_result(
                config,
                adapter=adapter,
                tool_class=tool_class,
                paths=paths,
                delta=delta,
            )
        if direct_success and config.get("standard_requirements_met") is True:
            config.update(
                {
                    "status": "PASSED",
                    "compliance_claimed": True,
                    "explanation": "controller-first attempt required an authorized reversible actual-file fallback",
                }
            )
            return config
        try:
            adapter.rollback_controller_transaction(
                controller_transaction,
                tool_class,
                direct_error or "authorized fallback did not verify",
            )
        except Exception as rollback_exc:
            direct_error = (
                (direct_error + ";") if direct_error else ""
            ) + f"controller_rollback:{type(rollback_exc).__name__}:{rollback_exc}"
        config.update(
            {
                "status": "ROLLED_BACK",
                "compliance_claimed": False,
                "explanation": direct_error or "authorized fallback did not verify",
            }
        )
        _refresh_configuration_result(
            config,
            adapter=adapter,
            tool_class=tool_class,
            paths=paths,
            delta=delta,
        )
        return config

    try:
        rollback = adapter.rollback_controller_transaction(
            controller_transaction,
            tool_class,
            "controller receipt did not materialize in actual effective files",
        )
    except Exception as exc:
        rollback = False
        explanation = f"controller rollback failed: {type(exc).__name__}:{exc}"
    else:
        explanation = "controller receipt was not effective; verified backup restored"
    config.update(
        {
            "status": "ROLLED_BACK",
            "compliance_claimed": False,
            "explanation": explanation,
            "reversibility": {
                **controller_reversibility,
                "rollback": rollback or "attempted",
            },
        }
    )
    _refresh_configuration_result(
        config,
        adapter=adapter,
        tool_class=tool_class,
        paths=paths,
        delta=delta,
    )
    return config


def _portability_evidence(
    platform_context: dict[str, object] | None,
) -> dict[str, object] | None:
    if platform_context is None:
        return None
    return {
        "platform_system": platform_context.get("system"),
        "persistent_path_style": platform_context.get("persistent_path_style"),
        "shared_agents_unique": True,
        "default_current_tool_only": True,
        "windows_registry_used": False,
        "msi_used": False,
        "drive_letter_required": False,
        "artifact_portability": deepcopy(
            platform_context.get("artifact_portability_evidence_request")
        ),
    }


def install_current_agent_copy(
    *,
    source_root: Path,
    home_root: Path,
    current_tool: str,
    explicit_tools: list[str],
    tool_roots: dict[str, Path],
    projection_manifest: Path,
    write: bool,
    fanout: bool = False,
    blank_host_configuration: dict[str, object] | None = None,
    configuration_adapter: object | None = None,
    install_transaction_adapter: object | None = None,
    platform_context: dict[str, object] | None = None,
    source_package_sha256: str | None = None,
) -> dict[str, object]:
    """Plan or apply the manifest projection without real host discovery."""

    source = Path(source_root).resolve(strict=False)
    home = Path(home_root).resolve(strict=False)
    if fanout:
        return _failure("fanout_forbidden")
    try:
        validated_source_package_sha256 = _validate_source_package_sha256(
            source_package_sha256
        )
        manifest, identity = _load_projection_contract(
            source,
            Path(projection_manifest),
        )
        selected = _select_targets(
            home_root=home,
            current_tool=current_tool,
            explicit_tools=list(explicit_tools),
            tool_roots={key: Path(value) for key, value in tool_roots.items()},
        )
        transition_candidates = _install_root_transition_candidates(selected)
        operations, projection_counts = _plan_projection_writes(
            source_root=source,
            manifest=manifest,
            selected=selected,
            migration_sources={
                Path(str(item["canonical_root"])).resolve(strict=False): Path(
                    str(item["source_root"])
                )
                for item in transition_candidates
            },
        )
        transitions = _required_root_transitions(
            transition_candidates,
            operations,
        )
        if write:
            transition_receipts = _apply_install_transaction(
                operations=operations,
                selected=selected,
                transitions=transitions,
                install_transaction_adapter=install_transaction_adapter,
                home_root=home,
            )
        else:
            transition_receipts = [
                {
                    "mode": str(item["mode"]),
                    "source_root": str(item["source_root"]),
                    "restore_root": str(item["restore_root"]),
                    "canonical_root": str(item["canonical_root"]),
                    "stage_root": None,
                    "status": "PLANNED",
                }
                for item in transitions
            ]
    except _InstallContractError as exc:
        return _failure(exc.reason, detail=exc.detail)
    except Exception as exc:
        return _failure(
            "install_transaction_failed",
            detail=f"{type(exc).__name__}:{exc}",
        )

    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "ok": True,
        "status": "INSTALLED" if write else "PLANNED",
        "reason": "projection_applied" if write else "projection_planned",
        "targets": [str(target) for _label, target, _kind in selected],
        "target_classes": [label for label, _target, _kind in selected],
        "projection_counts": projection_counts,
        "loaded_identity": deepcopy(identity),
        "physical_install_directory_name": LOCATOR_POLICY_EXPECTED[
            "install_directory_name"
        ],
        "protected_shiguan_locator": LOCATOR_POLICY_EXPECTED[
            "shiguan_namespace"
        ],
        "install_root_transitions": transition_receipts,
        "legacy_migrations": [
            {**item, "legacy_root": item["source_root"]}
            for item in transition_receipts
            if item.get("mode") == "LEGACY_MIGRATION"
        ],
        "pending_body_accessed": False,
        "real_host_configuration_accessed": False,
    }
    if validated_source_package_sha256 is not None:
        result["source_package_sha256"] = validated_source_package_sha256
    portability = _portability_evidence(platform_context)
    if portability is not None:
        result["portability_evidence"] = portability

    if blank_host_configuration is not None:
        if configuration_adapter is None:
            result["configuration_remediation"] = {
                "tool_class": current_tool,
                "standard_requirements_met": False,
                "status": "NO_CHANGE_UNCERTAIN",
                "compliance_claimed": False,
                "mutation_authorized": False,
                "controller_probe": {},
                "mutation_path": "none",
                "upstream_attempt": "not_run",
                "upstream_result": None,
                "uncertainty": ["configuration_adapter_missing"],
                "explanation": "configuration adapter missing; no host state accessed",
                "effective_files": [],
                "gaps": [],
                "evidence": [],
                "semantic_delta_verified": False,
                "runtime_probe": {
                    "available": False,
                    "standard_requirements_met": False,
                },
                "reversibility": {},
                "unrelated_install_blocked": False,
                "unrelated_task_blocked": False,
            }
        else:
            try:
                result["configuration_remediation"] = (
                    _remediate_blank_host_configuration(
                        request=blank_host_configuration,
                        adapter=configuration_adapter,
                        write=write,
                    )
                )
            except _InstallContractError as exc:
                result["configuration_remediation"] = {
                    "tool_class": current_tool,
                    "standard_requirements_met": False,
                    "status": "NO_CHANGE_UNCERTAIN",
                    "compliance_claimed": False,
                    "mutation_authorized": False,
                    "controller_probe": {},
                    "mutation_path": "none",
                    "upstream_attempt": "not_run",
                    "upstream_result": None,
                    "uncertainty": [exc.reason],
                    "explanation": exc.detail,
                    "effective_files": [],
                    "gaps": [],
                    "evidence": [],
                    "semantic_delta_verified": False,
                    "runtime_probe": {
                        "available": False,
                        "standard_requirements_met": False,
                    },
                    "reversibility": {},
                    "unrelated_install_blocked": False,
                    "unrelated_task_blocked": False,
                }
    return result


__all__ = ["install_current_agent_copy", "WindowsJunctionTransactionAdapter"]
