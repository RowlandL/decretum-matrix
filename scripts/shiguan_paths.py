"""Shared Shiguan data-path helpers for Dercretum-Matrix.

The skill code can be installed in Codex, Agent Skills, or Hermes roots. Shiguan
records are local evidence shared across those runtimes, so their writable
database lives outside any one skill installation by default.
"""

from __future__ import annotations

from copy import deepcopy
import sys

sys.dont_write_bytecode = True

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
from typing import Callable

import court_safe_fs_windows
from court_platform import user_data_base


ROOT_ENV_KEYS = ("COURT_SHARED_SHIGUAN_ROOT", "SHIGUAN_SHARED_ROOT")
CUTOVER_RECEIPT_ENV_KEY = "COURT_SHIGUAN_CUTOVER_RECEIPT"
CUTOVER_RECEIPT_SCHEMA = "court.shiguan_atomic_cutover.result.v1"
CUTOVER_COMMIT_SCHEMA = "court.shiguan_atomic_cutover.commit.v1"
LOCAL_AUTHORITY_REALM_SCHEMA = "court.shiguan.local_authority_realm.v1"
LOCAL_AUTHORITY_REQUIRED_PRODUCTION_GATES = (
    "PENDING_COUNT_ZERO",
    "QUIESCENCE_STABLE",
    "MIGRATION_GATE_PASSED",
)
DEFAULT_PROTECTED_ROOT = (
    Path.home()
    / ".agents"
    / "skills"
    / "decretum-matrix"
    / "references"
).resolve(strict=False)
PROTECTED_RECEIPT_PATHS = (
    "references/shiguan-index.jsonl",
    "references/shiguan-knowledge-graph.json",
    "references/shiguan-tree/_index.md",
    "references/shiguan-tree/capability-index/_index.md",
)
HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
SOURCE_AGENT_ENV_KEYS = ("COURT_SOURCE_AGENT", "SHIGUAN_SOURCE_AGENT", "SOURCE_AGENT")
CLAUDE_CODE_ENV_KEYS = (
    "CLAUDE_CODE",
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    "CLAUDE_CODE_SESSION_ID",
)
AGENT_LABELS = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "hermes": "Hermes",
    "agents": "Agents",
    "unknown": "Unknown",
}
AGENT_ALIASES = {
    "agent": "agents",
    "agent-skills": "agents",
    "claude": "claude-code",
    "claude-code": "claude-code",
    "claudecode": "claude-code",
    "claude_code": "claude-code",
}


def code_root() -> Path:
    return Path(__file__).parents[1]


def resolved_code_root() -> Path:
    return code_root().resolve()


def canonical_source_agent(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    return AGENT_ALIASES.get(normalized, normalized)


def is_claude_code_context(root_texts: tuple[str, ...]) -> bool:
    if any("/.claude/skills/" in text.replace("\\", "/").lower() for text in root_texts):
        return True
    return any(os.environ.get(key) for key in CLAUDE_CODE_ENV_KEYS)


def default_shared_root(home: Path | None = None) -> Path:
    user_home = (home or Path.home()).expanduser()
    return (
        user_home / ".agents" / "court-shiguan" / "decretum-matrix"
    ).resolve()


def default_legacy_shared_root(data_base: Path | None = None) -> Path:
    base = data_base or user_data_base()
    return Path(
        os.path.abspath(
            str(base / "court-shiguan" / "court-capability-router")
        )
    )


def _same_lexical_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def _path_kind(path: Path) -> str:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unknown"
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    is_junction = getattr(path, "is_junction", None)
    try:
        if callable(is_junction) and is_junction():
            return "junction"
    except OSError:
        return "unknown"
    if stat.S_ISLNK(metadata.st_mode):
        return "symlink"
    if bool(attributes & reparse_flag):
        return "reparse"
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    return "other"


def _nonblank(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _aware_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in HEX_DIGITS for character in value)
    )


def _authority_identity_digest(domain: str, value: object) -> str:
    payload = json.dumps(
        {"domain": domain, "value": value},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _phase1_authority_scope_fields() -> dict[str, object]:
    return {
        "phase1_scope": "PURE_RECEIPT_ONLY",
        "production_binding": "DEFERRED_PENDING_MIGRATION_GATE",
        "production_ready": False,
        "authority_root_bound": False,
        "archive_transaction_bound": False,
        "required_production_gates": list(
            LOCAL_AUTHORITY_REQUIRED_PRODUCTION_GATES
        ),
    }


def build_local_authority_realm_receipt(evidence: object) -> dict[str, object]:
    """Build a deterministic Phase 1 receipt from already-probed metadata."""

    if not isinstance(evidence, dict):
        raise ValueError("authority_evidence_malformed")
    raw_root = _nonblank(evidence.get("canonical_root"))
    transport = _nonblank(evidence.get("transport"))
    root_text = (raw_root or "").replace("/", "\\")
    unsupported_reasons: list[str] = []
    if root_text.startswith("\\\\"):
        unsupported_reasons.append("network_path_unsupported")
    if transport != "local_filesystem":
        unsupported_reasons.append("authority_transport_unsupported")
    if evidence.get("local_filesystem_verified") is not True:
        unsupported_reasons.append("local_filesystem_unproven")
    if unsupported_reasons:
        return {
            "schema": LOCAL_AUTHORITY_REALM_SCHEMA,
            "status": "AUTHORITY_TRANSPORT_UNSUPPORTED",
            "allowed": False,
            "reason_codes": unsupported_reasons,
            "authority_realm_id": None,
            "root_fingerprint": None,
            "canonical_root": raw_root,
            "transport": transport,
            "local_filesystem_verified": evidence.get(
                "local_filesystem_verified"
            ),
            "distributed_lock": "NOT_USED",
            **_phase1_authority_scope_fields(),
        }
    required = (
        "authority_realm_seed",
        "canonical_root",
        "filesystem_id",
        "directory_id",
        "identity_evidence",
    )
    normalized: dict[str, str] = {}
    for field in required:
        value = _nonblank(evidence.get(field))
        if value is None:
            raise ValueError(f"authority_evidence_missing:{field}")
        normalized[field] = value
    alias_kind = _nonblank(evidence.get("alias_kind")) or "direct"
    alias_proof = _nonblank(evidence.get("alias_proof"))
    root_reasons: list[str] = []
    if evidence.get("alias_target_verified") is not True:
        root_reasons.append("authority_alias_target_unproven")
    if evidence.get("containment_verified") is not True:
        root_reasons.append("authority_root_escape")
    if alias_kind == "junction":
        if alias_proof != "verified_exact_junction":
            root_reasons.append("authority_junction_unproven")
    elif alias_kind not in {
        "direct",
        "case_alias",
        "lexical_alias",
        "resolved_alias",
    }:
        root_reasons.append("authority_alias_kind_untrusted")
    if root_reasons:
        return {
            "schema": LOCAL_AUTHORITY_REALM_SCHEMA,
            "status": "AUTHORITY_ROOT_UNTRUSTED",
            "allowed": False,
            "reason_codes": root_reasons,
            "authority_realm_id": None,
            "root_fingerprint": None,
            "canonical_root": normalized["canonical_root"],
            "transport": transport,
            "local_filesystem_verified": True,
            "alias_kind": alias_kind,
            "alias_proof": alias_proof,
            "alias_target_verified": evidence.get("alias_target_verified"),
            "containment_verified": evidence.get("containment_verified"),
            "distributed_lock": "NOT_USED",
            **_phase1_authority_scope_fields(),
        }
    canonical_root = os.path.normcase(
        os.path.normpath(os.path.abspath(normalized["canonical_root"]))
    )
    authority_realm_id = "lar-" + _authority_identity_digest(
        "court-shiguan-local-authority-realm-v1",
        normalized["authority_realm_seed"],
    )[:24]
    root_fingerprint = _authority_identity_digest(
        "court-shiguan-local-authority-root-v1",
        {
            "authority_realm_id": authority_realm_id,
            "filesystem_id": normalized["filesystem_id"],
            "directory_id": normalized["directory_id"],
        },
    )
    return {
        "schema": LOCAL_AUTHORITY_REALM_SCHEMA,
        "status": "AUTHORITY_REALM_READY",
        "allowed": True,
        "reason_codes": ["local_authority_realm_ready"],
        "authority_realm_id": authority_realm_id,
        "root_fingerprint": root_fingerprint,
        "canonical_root": canonical_root,
        "transport": evidence.get("transport"),
        "local_filesystem_verified": evidence.get(
            "local_filesystem_verified"
        ),
        "identity_evidence": normalized["identity_evidence"],
        "alias_kind": alias_kind,
        "alias_proof": alias_proof,
        "alias_target_verified": evidence.get("alias_target_verified"),
        "containment_verified": evidence.get("containment_verified"),
        "distributed_lock": "NOT_USED",
        **_phase1_authority_scope_fields(),
    }


def _valid_empty_binding_snapshot(value: object) -> bool:
    return bool(
        type(value) is dict
        and set(value) == {"bindings"}
        and type(value["bindings"]) is list
        and value["bindings"] == []
    )


def _authorized_protected_root(value: object | None = None) -> Path | None:
    candidate = DEFAULT_PROTECTED_ROOT if value is None else value
    if not isinstance(candidate, (str, os.PathLike)):
        return None
    if isinstance(candidate, str) and not candidate.strip():
        return None
    try:
        path = Path(candidate).expanduser()
        if not path.is_absolute() or not path.anchor:
            return None
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _valid_protected_snapshot(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != set(
        PROTECTED_RECEIPT_PATHS
    ):
        return False
    for metadata in value.values():
        if not isinstance(metadata, dict) or not metadata:
            return False
        length = metadata.get("length")
        digest = metadata.get("sha256")
        if (
            type(length) is not int
            or length < 0
            or not _valid_sha256(digest)
        ):
            return False
    return True


def _success_rollback_is_consumable(value: object) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("applied") is False
        and value.get("ok") is True
        and value.get("conservative_stopped") is False
    )


def _cutover_receipt_sha256(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verified_cutover_commit_marker(
    marker: object, receipt: object
) -> bool:
    if not isinstance(marker, dict) or not isinstance(receipt, dict):
        return False
    digest = _cutover_receipt_sha256(receipt)
    if digest is None:
        return False
    for field in (
        "migration_id",
        "receipt_id",
        "run_owner",
        "run_marker_id",
        "nonce",
    ):
        if (
            _nonblank(marker.get(field)) is None
            or marker.get(field) != receipt.get(field)
        ):
            return False
    for field in ("source_root", "target_root", "control_root"):
        if not _same_lexical_path(
            Path(str(marker.get(field, ""))),
            Path(str(receipt.get(field, ""))),
        ):
            return False
    return bool(
        marker.get("schema") == CUTOVER_COMMIT_SCHEMA
        and marker.get("state") == "COMMITTED"
        and marker.get("receipt_sha256") == digest
        and _valid_sha256(marker.get("receipt_sha256"))
        and _aware_timestamp(marker.get("committed_at")) is not None
        and marker.get("committed_at") == receipt.get("committed_at")
    )


def _protected_root_is_separate(
    protected_root: Path,
    *,
    source_root: Path,
    target_root: Path,
) -> bool:
    if not protected_root.is_absolute():
        return False
    for inventory_root in (source_root, target_root):
        if _same_lexical_path(protected_root, inventory_root):
            return False
        try:
            protected_root.relative_to(inventory_root)
            return False
        except ValueError:
            pass
        try:
            inventory_root.relative_to(protected_root)
            return False
        except ValueError:
            pass
    return True


def _receipt_inventory_signature(value: object) -> tuple[object, ...] | None:
    if not isinstance(value, dict):
        return None
    volume_serial = value.get("source_volume_serial")
    directory_id = _nonblank(value.get("source_directory_id"))
    file_count = value.get("file_count")
    total_bytes = value.get("total_bytes")
    newest = _aware_timestamp(value.get("newest_mtime_utc"))
    digest = value.get("inventory_digest")
    exclusion = _nonblank(value.get("exclusion_policy_id"))
    if (
        type(volume_serial) is not int
        or volume_serial <= 0
        or directory_id is None
        or type(file_count) is not int
        or file_count < 0
        or type(total_bytes) is not int
        or total_bytes < 0
        or newest is None
        or not _valid_sha256(digest)
        or exclusion is None
    ):
        return None
    return (
        volume_serial,
        directory_id,
        file_count,
        total_bytes,
        newest.isoformat(),
        str(digest).lower(),
        exclusion,
    )


def _live_inventory_signature(value: object) -> tuple[object, ...] | None:
    if not isinstance(value, dict):
        return None
    file_count = value.get("file_count")
    total_bytes = value.get("total_bytes")
    newest = _aware_timestamp(value.get("newest_mtime_utc"))
    digest = value.get("inventory_digest")
    exclusion = _nonblank(value.get("exclusion_policy_id"))
    if (
        type(file_count) is not int
        or file_count < 0
        or type(total_bytes) is not int
        or total_bytes < 0
        or newest is None
        or not _valid_sha256(digest)
        or exclusion is None
    ):
        return None
    return (
        file_count,
        total_bytes,
        newest.isoformat(),
        str(digest).lower(),
        exclusion,
    )


def _verified_cutover_receipt(
    receipt: object,
    *,
    legacy_root: Path,
    target_root: Path,
    live_state: object | None = None,
    authorized_protected_root: Path | None = None,
) -> bool:
    if not isinstance(receipt, dict):
        return False
    source = Path(str(receipt.get("source_root", "")))
    target = Path(str(receipt.get("target_root", "")))
    control_root = Path(str(receipt.get("control_root", "")))
    protected_root = Path(str(receipt.get("protected_root", "")))
    expected_source = legacy_root / "references"
    expected_target = target_root / "references"
    pending_snapshot = receipt.get("pending_snapshot")
    binding_snapshot = receipt.get("binding_snapshot")
    protected_before = receipt.get("protected_files_before")
    protected_after = receipt.get("protected_files_after")
    rollback = receipt.get("rollback")
    receipt_inventory = _receipt_inventory_signature(receipt)
    expected_protected_root = _authorized_protected_root(
        authorized_protected_root
    )
    if (
        receipt.get("schema") != CUTOVER_RECEIPT_SCHEMA
        or receipt.get("status") != "CUTOVER_VERIFIED"
        or receipt.get("ok") is not True
        or receipt.get("junction_verified") is not True
        or receipt.get("protected_postcheck") != "verified"
        or receipt.get("pending_count") != 0
        or receipt_inventory is None
        or _nonblank(receipt.get("migration_id")) is None
        or _nonblank(receipt.get("receipt_id")) is None
        or _nonblank(receipt.get("run_owner")) is None
        or _nonblank(receipt.get("run_marker_id")) is None
        or _nonblank(receipt.get("nonce")) is None
        or _aware_timestamp(receipt.get("issued_at")) is None
        or _aware_timestamp(receipt.get("committed_at")) is None
        or not isinstance(pending_snapshot, dict)
        or pending_snapshot.get("pending_count") != 0
        or not _valid_empty_binding_snapshot(binding_snapshot)
        or not _valid_protected_snapshot(protected_before)
        or not _valid_protected_snapshot(protected_after)
        or protected_before != protected_after
        or not _success_rollback_is_consumable(rollback)
        or not _same_lexical_path(source, expected_source)
        or not _same_lexical_path(target, expected_target)
        or expected_protected_root is None
        or not _same_lexical_path(protected_root, expected_protected_root)
        or not _protected_root_is_separate(
            protected_root,
            source_root=source,
            target_root=target,
        )
        or _same_lexical_path(control_root, source)
        or _same_lexical_path(control_root, target)
    ):
        return False
    try:
        control_root.relative_to(source)
        return False
    except ValueError:
        pass
    try:
        control_root.relative_to(target)
        return False
    except ValueError:
        pass
    if live_state is None:
        live_state = _probe_live_cutover_state(
            legacy_root,
            target_root,
            receipt=receipt,
            authorized_protected_root=expected_protected_root,
        )
    if not isinstance(live_state, dict):
        return False
    live_inventory = _live_inventory_signature(live_state.get("target_inventory"))
    return bool(
        _verified_cutover_commit_marker(
            live_state.get("commit_marker"), receipt
        )
        and live_state.get("physical_store_count") == 1
        and live_state.get("legacy_references_kind") == "junction"
        and live_state.get("is_junction") is True
        and live_state.get("is_symlink") is False
        and live_state.get("is_reparse") is True
        and live_state.get("target_references_kind") == "directory"
        and _same_lexical_path(
            Path(str(live_state.get("junction_target", ""))),
            expected_target,
        )
        and _same_lexical_path(
            Path(str(live_state.get("canonical_target", ""))),
            expected_target,
        )
        and live_state.get("target_volume_serial") == receipt_inventory[0]
        and live_state.get("target_directory_id") == receipt_inventory[1]
        and live_state.get("identity_evidence") == "windows_handle"
        and live_inventory == receipt_inventory[2:]
        and live_state.get("pending_count") == 0
        and _valid_empty_binding_snapshot(
            live_state.get("binding_snapshot")
        )
        and _same_lexical_path(
            Path(str(live_state.get("protected_root", ""))),
            expected_protected_root,
        )
        and live_state.get("protected_files_after") == protected_after
        and _success_rollback_is_consumable(live_state.get("rollback"))
    )


def _load_cutover_receipt(target_root: Path, legacy_root: Path) -> object:
    configured = os.environ.get(CUTOVER_RECEIPT_ENV_KEY)
    receipt_path = (
        Path(configured).expanduser()
        if configured
        else legacy_root
        / "private-runtime"
        / "shiguan-migration"
        / "shiguan-cutover-receipt.json"
    )
    try:
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _load_cutover_commit_marker(
    target_root: Path, legacy_root: Path
) -> object:
    configured = os.environ.get(CUTOVER_RECEIPT_ENV_KEY)
    control_root = (
        Path(configured).expanduser().parent
        if configured
        else legacy_root / "private-runtime" / "shiguan-migration"
    )
    marker_path = control_root / "shiguan-cutover-commit.json"
    try:
        return json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _metadata_inventory_snapshot(
    root: Path, *, exclusion_policy_id: str
) -> dict[str, object] | None:
    if exclusion_policy_id != "court-shiguan-inventory-v1":
        return None
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    newest_ns = 0
    try:
        paths = sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold())
        for path in paths:
            metadata = path.lstat()
            attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
            reparse_flag = int(
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )
            if stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag):
                return None
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode):
                return None
            relative = path.relative_to(root).as_posix()
            file_count += 1
            total_bytes += int(metadata.st_size)
            newest_ns = max(newest_ns, int(metadata.st_mtime_ns))
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(int(metadata.st_size)).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(int(metadata.st_mtime_ns)).encode("ascii"))
            digest.update(b"\n")
    except (OSError, RuntimeError, ValueError):
        return None
    newest = datetime.fromtimestamp(
        newest_ns / 1_000_000_000 if newest_ns else 0,
        tz=timezone.utc,
    ).isoformat()
    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "newest_mtime_utc": newest,
        "inventory_digest": digest.hexdigest(),
        "exclusion_policy_id": exclusion_policy_id,
    }


def _live_protected_snapshot(protected_root: Path) -> object:
    result: dict[str, dict[str, object]] = {}
    try:
        for protected in PROTECTED_RECEIPT_PATHS:
            relative = Path(protected).relative_to("references")
            path = protected_root / relative
            metadata = path.lstat()
            attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
            reparse_flag = int(
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or bool(attributes & reparse_flag)
            ):
                return None
            data = path.read_bytes()
            result[protected] = {
                "length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
    except (OSError, RuntimeError, ValueError):
        return None
    return result


def _metadata_only_pending_count(root: Path) -> int | None:
    if _path_kind(root) != "directory":
        return None
    count = 0
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                lowered = entry.name.lower()
                if lowered.endswith((".metadata.json", ".meta.json")):
                    continue
                metadata = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(metadata.st_mode):
                    return None
                count += 1
    except OSError:
        return None
    return count


def _metadata_only_binding_snapshot(root: Path) -> dict[str, object] | None:
    presence_root = root / "court-runtime" / "agente-presence"
    if _path_kind(presence_root) != "directory":
        return None
    try:
        with os.scandir(presence_root) as entries:
            for entry in entries:
                metadata = entry.stat(follow_symlinks=False)
                attributes = int(
                    getattr(metadata, "st_file_attributes", 0) or 0
                )
                reparse_flag = int(
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                )
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                    or bool(attributes & reparse_flag)
                ):
                    return None
                return {"bindings": [{"state": "unknown"}]}
    except OSError:
        return None
    return {"bindings": []}


def _windows_directory_identity(root: Path) -> dict[str, object] | None:
    if os.name != "nt":
        return None
    handle: int | None = None
    try:
        handle, information = court_safe_fs_windows._open_verified_path_handle(
            root, Path(".")
        )
        volume_serial = int(information.volume_serial_number)
        file_id = int(information.file_id)
        if volume_serial <= 0 or file_id <= 0:
            return None
        court_safe_fs_windows._confirm_path_still_names_handle(
            root, Path("."), information
        )
        return {
            "target_volume_serial": volume_serial,
            "target_directory_id": str(file_id),
            "identity_evidence": "windows_handle",
        }
    except Exception:
        return None
    finally:
        if handle is not None:
            court_safe_fs_windows._close_file_handle(handle)


def _resolved_junction_target(root: Path) -> Path | None:
    try:
        return root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None


def _probe_live_cutover_state(
    legacy_root: Path,
    target_root: Path,
    *,
    receipt: object | None = None,
    authorized_protected_root: Path | None = None,
    identity_probe: Callable[[Path], dict[str, object] | None] | None = None,
    binding_probe: Callable[[Path], dict[str, object] | None] | None = None,
) -> dict[str, object] | None:
    if not isinstance(receipt, dict):
        return None
    legacy_references = legacy_root / "references"
    target_references = target_root / "references"
    legacy_kind = _path_kind(legacy_references)
    target_kind = _path_kind(target_references)
    if legacy_kind != "junction" or target_kind != "directory":
        return None
    junction_target = _resolved_junction_target(legacy_references)
    if (
        junction_target is None
        or not _same_lexical_path(junction_target, target_references)
    ):
        return None
    identity_provider = identity_probe or _windows_directory_identity
    identity = identity_provider(target_references)
    if not isinstance(identity, dict):
        return None
    exclusion = _nonblank(receipt.get("exclusion_policy_id"))
    protected_root = Path(str(receipt.get("protected_root", "")))
    expected_protected_root = _authorized_protected_root(
        authorized_protected_root
    )
    if (
        exclusion is None
        or expected_protected_root is None
        or not _same_lexical_path(protected_root, expected_protected_root)
        or not _protected_root_is_separate(
            expected_protected_root,
            source_root=legacy_references,
            target_root=target_references,
        )
    ):
        return None
    inventory = _metadata_inventory_snapshot(
        target_references, exclusion_policy_id=exclusion
    )
    protected_after = _live_protected_snapshot(expected_protected_root)
    pending_count = _metadata_only_pending_count(
        target_references / "shiguan-imports" / "pending"
    )
    binding_provider = binding_probe or _metadata_only_binding_snapshot
    binding_snapshot = binding_provider(target_references)
    if (
        inventory is None
        or protected_after is None
        or pending_count is None
        or not _valid_empty_binding_snapshot(binding_snapshot)
        or identity.get("identity_evidence") != "windows_handle"
        or type(identity.get("target_volume_serial")) is not int
        or int(identity["target_volume_serial"]) <= 0
        or _nonblank(identity.get("target_directory_id")) is None
    ):
        return None
    return {
        "physical_store_count": 1,
        "legacy_references_kind": legacy_kind,
        "is_junction": True,
        "is_symlink": False,
        "is_reparse": True,
        "target_references_kind": target_kind,
        "junction_target": str(junction_target),
        "canonical_target": str(target_references),
        "target_volume_serial": identity["target_volume_serial"],
        "target_directory_id": identity["target_directory_id"],
        "identity_evidence": identity["identity_evidence"],
        "target_inventory": inventory,
        "pending_count": pending_count,
        "binding_snapshot": deepcopy(binding_snapshot),
        "protected_root": str(expected_protected_root),
        "protected_files_after": protected_after,
        "rollback": deepcopy(receipt.get("rollback")),
        "commit_marker": _load_cutover_commit_marker(
            target_root, legacy_root
        ),
    }


def _active_shared_root(
    target_root: Path,
    legacy_root: Path,
    *,
    authorized_protected_root: Path | None = None,
) -> Path:
    if _same_lexical_path(target_root, legacy_root):
        return legacy_root
    legacy_references = legacy_root / "references"
    target_references = target_root / "references"
    legacy_kind = _path_kind(legacy_references)
    target_kind = _path_kind(target_references)
    if legacy_kind == "directory":
        if target_kind == "absent":
            return legacy_root
        raise RuntimeError("transitional_shiguan_dual_root_blocked")
    if legacy_kind in {"unknown", "other"}:
        raise RuntimeError("transitional_shiguan_legacy_root_untrusted")
    if legacy_kind == "junction":
        receipt = _load_cutover_receipt(target_root, legacy_root)
        live_state = _probe_live_cutover_state(
            legacy_root,
            target_root,
            receipt=receipt,
            authorized_protected_root=authorized_protected_root,
        )
        if (
            target_kind != "directory"
            or not _verified_cutover_receipt(
                receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=live_state,
                authorized_protected_root=authorized_protected_root,
            )
        ):
            raise RuntimeError("verified_shiguan_cutover_receipt_required")
        return target_root
    if legacy_kind == "absent":
        if target_kind == "absent":
            return target_root
        if target_kind == "directory":
            return target_root
    if target_kind in {"unknown", "other", "reparse", "symlink", "junction"}:
        raise RuntimeError("transitional_shiguan_target_root_untrusted")
    raise RuntimeError("transitional_shiguan_root_topology_untrusted")


def shared_root() -> Path:
    canonical_target = default_shared_root()
    target = canonical_target
    explicit_override = False
    for key in ROOT_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            explicit_override = True
            root = Path(value).expanduser()
            if root.name.lower() == "references":
                target = root.parent.resolve()
            else:
                target = root.resolve()
            break
    if explicit_override and not _same_lexical_path(target, canonical_target):
        return target
    return _active_shared_root(target, default_legacy_shared_root())


def references_root() -> Path:
    return shared_root() / "references"


def reference_path(*parts: str) -> Path:
    return references_root().joinpath(*parts)


def default_obsidian_parent_vault() -> Path:
    return Path.home() / "Documents" / "Obsidian Vault"


def default_obsidian_cache_vault() -> Path:
    return default_obsidian_parent_vault() / "Court Shiguan"


def default_obsidian_shared_vault() -> Path:
    return reference_path("shiguan-tree")


def default_obsidian_inbox() -> Path:
    return default_obsidian_shared_vault() / "Obsidian 回传"


def _create_text_exclusive(path: Path, text: str) -> bool:
    """Create a seed file exactly once without truncating a concurrent writer."""

    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        return False
    return True


def ensure_shared_seed() -> Path:
    """Explicitly initialize shared seed files without registering agent presence."""

    # Imported lazily so court_file_lock can expose shiguan_write_lock_path()
    # without creating a module-import cycle back into this file.
    from court_file_lock import atomic_write_text, file_lock

    refs = references_root()
    tree = refs / "shiguan-tree"
    for directory in (
        refs,
        refs / "plan-archives",
        refs / "memory-decisions",
        refs / "court-runtime",
        refs / "agente-logs",
        refs / "shiguan-imports" / "pending",
        refs / "shiguan-imports" / "processed",
        refs / "shiguan-peers",
        refs / "obsidian-sync",
        tree,
        tree / "capability-index",
        tree / "branches",
        tree / "leaves",
        tree / "manual",
        tree / "meta",
        tree / "sources",
        tree / "sources" / "plan-archives",
        tree / "sources" / "memory-decisions",
        tree / "sources" / "shiguan-tree" / "manual",
        tree / ".obsidian",
        tree / "Obsidian 回传",
        refs / "court-runtime" / "agente-presence",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    write_lock = refs / "court-runtime" / "shiguan-write.lock"
    with file_lock(write_lock):
        readmes = {
            refs / "README.md": "# Shared Court Shiguan\n\nThis directory is the local shared Shiguan database used by Codex, Agent Skills, and Hermes Dercretum-Matrix installations.\n",
            refs / "plan-archives" / "README.md": "# Shiguan Plan Archives\n\nLocal court checkpoints are written here.\n",
            refs / "memory-decisions" / "README.md": "# Shiguan Memory Decisions\n\nDurable memory decisions are recorded here after Menxia approval.\n",
            tree / "README.md": "# 史馆生长树\n\nGenerated Markdown tree for Obsidian and the Shiguan Web UI.\n",
            tree / "capability-index" / "README.md": "# Capability Index\n\nGenerated skill/agent/MCP/CLI/script routing index for Obsidian-visible court capability selection.\n",
            tree / "capability-index" / "_index.md": "---\ntype: shiguan_capability_index_seed\ncapability_index_skill_gate: \"seed\"\n---\n\n# 能力官籍索引 / Capability Routing Index\n\nRun `python scripts/refresh_capability_registry.py` to generate the host-local capability routing table.\n\nInvocation rule: index first, select the smallest suitable bounded capability set, then call under the active authority. Do not wait for the user to name the capability and do not invoke every matching candidate.\n",
            tree / "branches" / "README.md": "# Branches\n\nGenerated content-lineage branches.\n",
            tree / "leaves" / "README.md": "# Leaves\n\nGenerated Shiguan leaves.\n",
            tree / "manual" / "README.md": "# Manual Entries\n\nManual Web UI entries are stored here as JSON.\n",
            tree / "meta" / "schema.md": "# Shiguan Growth Tree Schema\n\nSeed schema; rebuilt by `grow_shiguan_tree.py`.\n",
            tree / "sources" / "README.md": "# Source Mirrors\n\nGenerated in-vault copies of raw Shiguan sources used by Obsidian links.\n",
            tree / "sources" / "plan-archives" / "README.md": "# Plan Archive Sources\n\nGenerated in-vault copies of linked Shiguan plan archive records.\n",
            tree / "sources" / "memory-decisions" / "README.md": "# Memory Decision Sources\n\nGenerated in-vault copies of linked Shiguan memory decision records.\n",
            tree / "Obsidian 回传" / "README.md": "# Obsidian 回传\n\n在 Obsidian 中新增或编辑需要交给 Codex/Hermes 会审的材料时，放在本目录。后台 autosync 会把变更复制到共享 `shiguan-imports/pending`，不会直接覆盖正式史馆记录。\n",
            refs / "obsidian-sync" / "README.md": "# Obsidian Sync\n\nHost-local sync config lives here. API keys must never be packaged or printed.\n",
        }
        for path, text in readmes.items():
            _create_text_exclusive(path, text)

        _create_text_exclusive(refs / "shiguan-index.jsonl", "")
        graph_text = (
            json.dumps(
                {
                    "schema": {
                        "name": "shiguan-multidimensional-knowledge-graph",
                        "version": 1,
                        "portable_seed": True,
                    },
                    "counts": {"entries": 0, "nodes": 1, "edges": 0},
                    "nodes": [{"id": "root:史馆总纪", "kind": "root", "label": "史馆总纪", "count": 1}],
                    "edges": [],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        _create_text_exclusive(refs / "shiguan-knowledge-graph.json", graph_text)

        config = refs / "obsidian-sync" / "config.json"
        initial_config = {
            "endpoint": "https://127.0.0.1:27124",
            "verify_ssl": False,
            "sync_mode": "filesystem_preserve_only",
            "auto_enabled": True,
            "output_folder": "Court Shiguan",
            "vault_path": str(default_obsidian_cache_vault()),
            "cache_vault_path": str(default_obsidian_cache_vault()),
            "source_vault_path": str(default_obsidian_shared_vault()),
            "parent_vault_path": str(default_obsidian_parent_vault()),
            "watch_paths": [str(default_obsidian_cache_vault()), str(default_obsidian_inbox())],
            "autosync_enabled": True,
            "autosync_interval_seconds": 20,
            "service_daemon_script": str(code_root() / "scripts" / "shiguan_service_daemon.py"),
            "service_ensure_script": str(code_root() / "scripts" / "ensure_shiguan_service_daemon.py"),
            "autosync_script": str(code_root() / "scripts" / "shiguan_autosync_daemon.py"),
            "filesystem_sync_script": str(code_root() / "scripts" / "sync_shiguan_obsidian_vault.py"),
            "shared_shiguan_root": str(references_root()),
            "api_key": "",
        }
        created = _create_text_exclusive(
            config,
            json.dumps(initial_config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        if not created:
            try:
                current = json.loads(config.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = None
            if isinstance(current, dict):
                defaults = {
                    "service_daemon_script": initial_config["service_daemon_script"],
                    "service_ensure_script": initial_config["service_ensure_script"],
                    "autosync_script": initial_config["autosync_script"],
                    "filesystem_sync_script": initial_config["filesystem_sync_script"],
                    "source_vault_path": initial_config["source_vault_path"],
                    "shared_shiguan_root": initial_config["shared_shiguan_root"],
                }
                changed = False
                for key, value in defaults.items():
                    if not current.get(key):
                        current[key] = value
                        changed = True
                if changed:
                    atomic_write_text(
                        config,
                        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    )
    return refs


def detect_runtime_agent(explicit: str | None = None) -> dict[str, str]:
    value = (explicit or "").strip()
    if not value:
        for key in SOURCE_AGENT_ENV_KEYS:
            env_value = os.environ.get(key, "").strip()
            if env_value:
                value = env_value
                break

    root = code_root()
    root_texts = (
        "/" + str(root).replace("\\", "/").strip("/").lower() + "/",
        "/" + str(resolved_code_root()).replace("\\", "/").strip("/").lower() + "/",
    )
    if value:
        agent_id = canonical_source_agent(value)
    elif os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_MANAGED_BY_NPM"):
        agent_id = "codex"
    elif is_claude_code_context(root_texts):
        agent_id = "claude-code"
    elif any("/appdata/local/hermes/skills/" in text or "/.hermes/skills/" in text for text in root_texts):
        agent_id = "hermes"
    elif any("/.codex/skills/" in text for text in root_texts):
        agent_id = "codex"
    elif any("/.agents/skills/" in text for text in root_texts):
        agent_id = "agents"
    else:
        agent_id = "unknown"

    display = AGENT_LABELS.get(agent_id, value or agent_id)
    return {
        "source_agent": agent_id,
        "source_agent_label": display,
        "source_agent_skill_root": str(root),
        "shared_shiguan_root": str(references_root()),
    }


def register_agent_presence(event: str = "skill-use", explicit: str | None = None) -> dict[str, object]:
    if os.environ.get("COURT_DISABLE_AGENT_PRESENCE"):
        return {}
    agent = detect_runtime_agent(explicit)
    now = datetime.now().isoformat(timespec="seconds")
    record: dict[str, object] = {
        **agent,
        "agent_id": agent["source_agent"],
        "label": agent["source_agent_label"],
        "status": "online",
        "event": event,
        "last_seen": now,
        "updated_at": now,
        "ttl_seconds": 180,
        "host": socket.gethostname(),
        "pid": os.getpid(),
    }
    root = references_root() / "court-runtime" / "agente-presence"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{agent['source_agent']}.json"
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return record


def relative_to_data(path: Path) -> str:
    resolved = path.resolve()
    for root in (shared_root(), code_root()):
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    try:
        return resolved.relative_to(references_root().resolve()).as_posix()
    except ValueError:
        return str(resolved)


def resolve_source(source: str) -> Path:
    text = str(source or "").replace("/", os.sep)
    if not text:
        return references_root()
    path = Path(text)
    if path.is_absolute():
        return path
    shared_candidate = shared_root() / path
    if shared_candidate.exists() or text.startswith("references" + os.sep):
        return shared_candidate
    return code_root() / path


def legacy_reference_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / ".agents" / "skills" / "court-capability-router" / "references",
        home / ".codex" / "skills" / "court-capability-router" / "references",
        home / ".hermes" / "skills" / "court-capability-router" / "references",
        user_data_base() / "hermes" / "skills" / "court-capability-router" / "references",
    ]
    current = code_root() / "references"
    shared_refs = references_root()
    output: list[Path] = []
    seen: set[str] = set()
    for root in [current, *roots]:
        try:
            if root.resolve() == shared_refs.resolve():
                continue
        except OSError:
            pass
        key = str(root.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        if root.exists():
            output.append(root)
    return output
