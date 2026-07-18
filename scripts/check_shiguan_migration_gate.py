"""Deterministic RED contract for the shared Shiguan migration gate.

The checker uses temporary paths and metadata-only fixtures.  It never creates,
opens, hashes, copies, moves, deletes, or marks a pending body as seen.  The
future production module is expected to expose one small dependency-injected
entry point::

    evaluate_migration_gate(*, phase: str, operations: object) -> dict

The operation object makes the pending-body short-circuit order observable.  A
non-zero or unknown pending count must return before any other probe or action.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PATH = ROOT / "scripts" / "shiguan_migration_gate.py"
CUTOVER_PATH = ROOT / "scripts" / "migrate_shared_shiguan.py"
PATHS_PATH = ROOT / "scripts" / "shiguan_paths.py"
SHIGUAN_MEMORY_PATH = ROOT / "references" / "court-shiguan-memory.md"
RESULT_SCHEMA = "court.shiguan_migration_gate.result.v1"
PENDING_BLOCK = "MIGRATION_BLOCKED_PENDING_BODIES"
READY = "READY_TO_MIGRATE"
CUTOVER_VERIFIED = "CUTOVER_VERIFIED"
CUTOVER_ROLLED_BACK = "CUTOVER_ROLLED_BACK"
CUTOVER_ROLLBACK_FAILED = "CUTOVER_ROLLBACK_FAILED"
FIXTURE_NOW = datetime(2026, 7, 14, 0, 1, 10, tzinfo=timezone.utc)
_DELETE = object()

PROTECTED_PATHS = (
    "references/shiguan-index.jsonl",
    "references/shiguan-knowledge-graph.json",
    "references/shiguan-tree/_index.md",
    "references/shiguan-tree/capability-index/_index.md",
)

FORBIDDEN_BODY_OR_MUTATION_OPERATIONS = frozenset(
    {
        "traverse_pending_bodies",
        "hash_pending_body",
        "copy_source",
        "move_source",
        "delete_source",
        "mark_pending_seen",
    }
)


class FixtureOperations:
    """Metadata-only operation surface used to prove ordering and fail-closed behavior."""

    def __init__(
        self,
        *,
        pending_count: int | None,
        bindings: list[dict[str, object]],
        stable_scans: list[dict[str, object]],
        current_snapshot: dict[str, object],
        target_context: dict[str, object],
        post_cutover_state: dict[str, object],
        protected_before: dict[str, dict[str, object]],
        protected_after: dict[str, dict[str, object]],
        protected_root: Path,
        receipt_identity: dict[str, object],
    ) -> None:
        self.pending_count = pending_count
        self.bindings = bindings
        self.stable_scans = stable_scans
        self.current_snapshot = current_snapshot
        self.target_context = target_context
        self.post_cutover_state = post_cutover_state
        self.protected_before = protected_before
        self.protected_after = protected_after
        self.protected_root = protected_root
        self.receipt_identity = receipt_identity
        self.calls: list[str] = []
        self.protected_snapshot_roots: list[Path | None] = []
        self.authorized_protected_root_reads = 0

    def _read(self, name: str, value: object) -> Any:
        self.calls.append(name)
        return deepcopy(value)

    def get_pending_body_count(self) -> int | None:
        return self._read("get_pending_body_count", self.pending_count)

    def current_time(self) -> datetime:
        return FIXTURE_NOW

    def get_record_bindings(self) -> list[dict[str, object]]:
        return self._read("get_record_bindings", self.bindings)

    def get_stable_scans(self) -> list[dict[str, object]]:
        return self._read("get_stable_scans", self.stable_scans)

    def get_current_source_snapshot(self) -> dict[str, object]:
        return self._read("get_current_source_snapshot", self.current_snapshot)

    def get_target_context(self) -> dict[str, object]:
        return self._read("get_target_context", self.target_context)

    def get_receipt_identity(self) -> dict[str, object]:
        return self._read("get_receipt_identity", self.receipt_identity)

    def get_authorized_protected_root(self) -> Path:
        self.authorized_protected_root_reads += 1
        return self.protected_root

    def get_protected_file_snapshot(
        self, protected_root: Path | None = None
    ) -> dict[str, dict[str, object]]:
        self.protected_snapshot_roots.append(
            Path(protected_root).resolve(strict=False)
            if protected_root is not None
            else None
        )
        return self._read("get_protected_file_snapshot", self.protected_before)

    def get_post_cutover_state(self) -> dict[str, object]:
        return self._read("get_post_cutover_state", self.post_cutover_state)

    def get_protected_file_snapshots(
        self, protected_root: Path | None = None
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
        self.protected_snapshot_roots.append(
            Path(protected_root).resolve(strict=False)
            if protected_root is not None
            else None
        )
        return self._read(
            "get_protected_file_snapshots",
            (self.protected_before, self.protected_after),
        )

    def _forbidden(self, name: str) -> None:
        self.calls.append(name)
        raise AssertionError(f"forbidden migration operation during gate evaluation: {name}")

    def traverse_pending_bodies(self) -> None:
        self._forbidden("traverse_pending_bodies")

    def hash_pending_body(self) -> None:
        self._forbidden("hash_pending_body")

    def copy_source(self) -> None:
        self._forbidden("copy_source")

    def move_source(self) -> None:
        self._forbidden("move_source")

    def delete_source(self) -> None:
        self._forbidden("delete_source")

    def mark_pending_seen(self) -> None:
        self._forbidden("mark_pending_seen")


class CutoverFixtureOperations:
    """Failure-injectable cutover adapter with no host or service mutations."""

    def __init__(
        self,
        temp_root: Path,
        *,
        fail_at: str | None = None,
        fail_after_effect: bool = False,
        same_volume: bool = True,
        target_exists: bool = False,
        source_is_reparse: bool = False,
        final_recheck_updates: dict[str, object] | None = None,
        protected_after: dict[str, dict[str, object]] | None = None,
        track_final_recheck: bool = False,
        track_protected_postcheck: bool = False,
        track_actual_state: bool = False,
        remove_failure: str | None = None,
        lock_owner_override: str | None = None,
        owner_drift_on_rollback: bool = False,
        final_live_updates: dict[str, object] | None = None,
    ) -> None:
        self.source_root = temp_root / "localappdata" / "court-shiguan" / "court-capability-router" / "references"
        self.target_root = temp_root / "user" / ".agents" / "court-shiguan" / "decretum-matrix" / "references"
        self.agents_root = temp_root / "user" / ".agents"
        self.pending_root = self.source_root / "shiguan-imports" / "pending"
        self.protected_root = (
            temp_root
            / "authorized-installed-skill"
            / "court-capability-router"
            / "references"
        )
        self.fail_at = fail_at
        self.fail_after_effect = fail_after_effect
        self.same_volume = same_volume
        self.target_exists = target_exists
        self.source_is_reparse = source_is_reparse
        self.directory_id = "directory-id-1"
        self.volume_serial = 17
        self.exclusion_policy_id = "court-shiguan-inventory-v1"
        self.inventory = _bound_inventory(
            _inventory(captured_at=_timestamp(60), evidence_id="cutover-current"),
            source_root=self.source_root,
            volume_serial=self.volume_serial,
            directory_id=self.directory_id,
            exclusion_policy_id=self.exclusion_policy_id,
        )
        self.migration_id = "fixture-migration-1"
        self.receipt_id = "fixture-receipt-1"
        self.run_owner = "bingbu#0001:fixture-run"
        self.run_marker_id = "fixture-marker-1"
        self.control_root = (
            self.source_root.parent / "private-runtime" / "shiguan-migration"
        )
        self.issued_at = _timestamp(32)
        self.nonce = "fixture-nonce-1"
        self.pending_snapshot = {"pending_count": 0}
        self.binding_snapshot = {"bindings": []}
        self.protected_before = _protected()
        self.protected_after = deepcopy(protected_after or self.protected_before)
        self.final_recheck_updates = final_recheck_updates or {}
        self.track_final_recheck = track_final_recheck
        self.track_protected_postcheck = track_protected_postcheck
        self.track_actual_state = track_actual_state
        self.remove_failure = remove_failure
        self.lock_owner_override = lock_owner_override
        self.owner_drift_on_rollback = owner_drift_on_rollback
        self.final_live_updates = final_live_updates or {}
        self.events: list[str] = []
        self.protected_snapshot_roots: list[Path | None] = []
        self.authorized_protected_root_reads = 0
        self.daemon_running = True
        self.renamed = False
        self.junction_created = False
        self.run_lock_held = False

    def _event(self, name: str, effect: Callable[[], None] | None = None) -> None:
        self.events.append(name)
        if self.fail_at == name and not self.fail_after_effect:
            raise RuntimeError(f"injected failure: {name}")
        if effect is not None:
            effect()
        if self.fail_at == name and self.fail_after_effect:
            raise RuntimeError(f"injected failure after side effect: {name}")

    def inspect_cutover_context(self) -> dict[str, object]:
        self._event("inspect_cutover_context")
        return {
            "source_root": str(self.source_root),
            "target_root": str(self.target_root),
            "agents_root": str(self.agents_root),
            "pending_root": str(self.pending_root),
            "protected_root": str(self.protected_root),
            "same_volume": self.same_volume,
            "target_exists": self.target_exists,
            "source_is_reparse": self.source_is_reparse,
            "pending_is_reparse": False,
            "target_is_reparse": False,
            "target_parent_reparse_free": True,
            "source_volume_serial": self.volume_serial,
            "target_volume_serial": self.volume_serial,
            "delete_share_verified": True,
            "source_file_id_verified": True,
            "target_parent_file_id_verified": True,
            "source_directory_id": self.directory_id,
            "source_inventory": deepcopy(self.inventory),
            "control_root": str(self.control_root),
        }

    @contextmanager
    def migration_run_lock(
        self, run_identity: dict[str, object]
    ) -> Any:
        self.events.append("acquire_migration_run")
        self.run_lock_held = True
        try:
            yield {
                "migration_id": self.migration_id,
                "run_owner": self.lock_owner_override or self.run_owner,
                "run_marker_id": self.run_marker_id,
                "control_root": str(self.control_root),
            }
        finally:
            self.run_lock_held = False
            self.events.append("release_migration_run")

    def verify_run_owner(self, run_identity: dict[str, object]) -> bool:
        self.events.append("verify_run_owner")
        if self.owner_drift_on_rollback:
            return False
        return (
            self.run_lock_held
            and run_identity.get("migration_id") == self.migration_id
            and run_identity.get("run_owner") == self.run_owner
            and run_identity.get("run_marker_id") == self.run_marker_id
        )

    def current_time(self) -> datetime:
        return FIXTURE_NOW

    def get_authorized_protected_root(self) -> Path:
        self.authorized_protected_root_reads += 1
        return self.protected_root

    def stop_daemon(self) -> None:
        self._event("stop_daemon", lambda: setattr(self, "daemon_running", False))

    def final_metadata_recheck(
        self, receipt_identity: dict[str, object]
    ) -> dict[str, object]:
        if self.track_final_recheck:
            self.events.append("final_metadata_recheck")
        snapshot = {
            "source_root": str(self.source_root),
            "target_root": str(self.target_root),
            "protected_root": str(self.protected_root),
            "source_directory_id": self.directory_id,
            "source_volume_serial": self.volume_serial,
            "file_count": self.inventory["file_count"],
            "total_bytes": self.inventory["total_bytes"],
            "newest_mtime_utc": self.inventory["newest_mtime_utc"],
            "inventory_digest": self.inventory["inventory_digest"],
            "exclusion_policy_id": self.exclusion_policy_id,
            "captured_at": _timestamp(65),
            "migration_id": self.migration_id,
            "receipt_id": self.receipt_id,
            "run_owner": self.run_owner,
            "run_marker_id": self.run_marker_id,
            "control_root": str(self.control_root),
            "issued_at": self.issued_at,
            "nonce": self.nonce,
            "pending_count": 0,
            "pending_snapshot": deepcopy(self.pending_snapshot),
            "binding_snapshot": deepcopy(self.binding_snapshot),
        }
        snapshot.update(deepcopy(self.final_recheck_updates))
        return snapshot

    def snapshot_source(self) -> dict[str, object]:
        self._event("snapshot_source")
        return {
            "source_directory_id": self.directory_id,
            "source_inventory": deepcopy(self.inventory),
        }

    def atomic_rename_to_target(self) -> None:
        self._event("atomic_rename_to_target", lambda: setattr(self, "renamed", True))

    def create_compatibility_junction(self) -> None:
        self._event(
            "create_compatibility_junction",
            lambda: setattr(self, "junction_created", True),
        )

    def verify_post_cutover(self) -> dict[str, object]:
        self._event("verify_post_cutover")
        return {
            "physical_store_count": 1,
            "old_path_kind": "junction",
            "junction_target": str(self.target_root),
            "canonical_target": str(self.target_root),
            "old_path_directory_id": self.directory_id,
            "target_directory_id": self.directory_id,
            "target_volume_serial": self.volume_serial,
            "target_inventory": deepcopy(self.inventory),
        }

    def inspect_final_cutover_state(self) -> dict[str, object]:
        self.events.append("inspect_final_cutover_state")
        state: dict[str, object] = {
            "daemon_running": self.daemon_running,
            "physical_store_count": 1,
            "old_path_kind": "junction",
            "junction_target": str(self.target_root),
            "canonical_target": str(self.target_root),
            "old_path_directory_id": self.directory_id,
            "target_directory_id": self.directory_id,
            "target_volume_serial": self.volume_serial,
            "target_inventory": deepcopy(self.inventory),
            "protected_files_after": deepcopy(self.protected_after),
            "protected_root": str(self.protected_root),
            "pending_count": 0,
            "binding_snapshot": deepcopy(self.binding_snapshot),
            "rollback": {
                "applied": False,
                "ok": True,
                "conservative_stopped": False,
            },
        }
        state.update(deepcopy(self.final_live_updates))
        return state

    def get_protected_file_snapshot(
        self, protected_root: Path | None = None
    ) -> dict[str, dict[str, object]]:
        self.protected_snapshot_roots.append(
            Path(protected_root).resolve(strict=False)
            if protected_root is not None
            else None
        )
        if self.track_protected_postcheck:
            self.events.append("get_protected_file_snapshot")
        return deepcopy(self.protected_after)

    def inspect_actual_state(self) -> dict[str, object]:
        if self.track_actual_state:
            self.events.append("inspect_actual_state")
        return {
            "daemon_running": self.daemon_running,
            "source_exists": not self.renamed or self.junction_created,
            "target_exists": self.renamed,
            "old_path_kind": (
                "junction"
                if self.junction_created
                else ("absent" if self.renamed else "directory")
            ),
            "junction_target": (
                str(self.target_root) if self.junction_created else None
            ),
            "source_directory_id": self.directory_id if not self.renamed else None,
            "target_directory_id": self.directory_id if self.renamed else None,
        }

    def remove_compatibility_junction(self, expected_target: Path) -> None:
        self.events.append("remove_compatibility_junction")
        if (
            expected_target.resolve(strict=False)
            != self.target_root.resolve(strict=False)
            or not self.junction_created
        ):
            raise AssertionError("rollback attempted against an unexpected junction")
        if self.remove_failure == "before":
            raise RuntimeError("injected junction removal failure")
        self.junction_created = False
        if self.remove_failure == "after":
            raise RuntimeError("injected junction removal failure after side effect")

    def atomic_rename_to_source(self, expected_directory_id: str) -> None:
        self._event("atomic_rename_to_source")
        if expected_directory_id != self.directory_id or not self.renamed:
            raise AssertionError("rollback attempted against an unexpected directory")
        self.renamed = False

    def start_daemon(self) -> None:
        self._event("start_daemon", lambda: setattr(self, "daemon_running", True))


def _timestamp(offset_seconds: int) -> str:
    base = datetime(2026, 7, 14, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def _same_fixture_path(left: object, right: Path) -> bool:
    try:
        return os.path.normcase(
            str(Path(str(left)).resolve(strict=False))
        ) == os.path.normcase(str(right.resolve(strict=False)))
    except (OSError, RuntimeError, ValueError):
        return False


def _inventory(
    *,
    captured_at: str,
    digest: str = "a" * 64,
    evidence_id: str = "fixture-evidence",
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "captured_at": captured_at,
        "file_count": 11,
        "total_bytes": 4096,
        "newest_mtime_utc": "2026-07-14T00:00:00+00:00",
        "inventory_digest": digest,
    }


def _bound_inventory(
    value: dict[str, object],
    *,
    source_root: Path,
    volume_serial: int = 17,
    directory_id: str = "directory-id-1",
    exclusion_policy_id: str = "court-shiguan-inventory-v1",
) -> dict[str, object]:
    bound = deepcopy(value)
    bound.setdefault("canonical_source_root", str(source_root.resolve()))
    bound.setdefault("source_volume_serial", volume_serial)
    bound.setdefault("source_directory_id", directory_id)
    bound.setdefault("exclusion_policy_id", exclusion_policy_id)
    return bound


def _protected() -> dict[str, dict[str, object]]:
    return {
        path: {"length": index, "sha256": f"{index:064x}"}
        for index, path in enumerate(PROTECTED_PATHS, start=1)
    }


def _receipt_sha256(receipt: dict[str, object]) -> str:
    payload = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _commit_marker(
    receipt: dict[str, object], *, state: str = "COMMITTED"
) -> dict[str, object]:
    return {
        "schema": "court.shiguan_atomic_cutover.commit.v1",
        "state": state,
        "source_root": receipt["source_root"],
        "target_root": receipt["target_root"],
        "control_root": receipt["control_root"],
        "migration_id": receipt["migration_id"],
        "receipt_id": receipt["receipt_id"],
        "run_owner": receipt["run_owner"],
        "run_marker_id": receipt["run_marker_id"],
        "nonce": receipt["nonce"],
        "receipt_sha256": (
            _receipt_sha256(receipt) if state == "COMMITTED" else None
        ),
        "committed_at": (
            receipt.get("committed_at") if state == "COMMITTED" else None
        ),
    }


def _fixture(
    temp_root: Path,
    *,
    pending_count: int | None = 0,
    bindings: list[dict[str, object]] | None = None,
    stable_scans: list[dict[str, object]] | None = None,
    current_snapshot: dict[str, object] | None = None,
    target_outside_agents: bool = False,
    same_volume: bool = True,
    target_exists: bool = False,
    source_is_reparse: bool = False,
    post_updates: dict[str, object] | None = None,
    mutate_protected: bool = False,
) -> FixtureOperations:
    user_root = temp_root / "user"
    agents_root = user_root / ".agents"
    source_root = temp_root / "localappdata" / "court-shiguan" / "court-capability-router" / "references"
    pending_root = source_root / "shiguan-imports" / "pending"
    protected_root = (
        temp_root
        / "authorized-installed-skill"
        / "court-capability-router"
        / "references"
    )
    target_root = (
        temp_root / "escaped" / "court-shiguan" / "references"
        if target_outside_agents
        else agents_root / "court-shiguan" / "decretum-matrix" / "references"
    )
    raw_scans = stable_scans or [
        _inventory(captured_at=_timestamp(0), evidence_id="scan-1"),
        _inventory(captured_at=_timestamp(30), evidence_id="scan-2"),
    ]
    scans = []
    for index, scan in enumerate(raw_scans, start=1):
        bound_scan = _bound_inventory(scan, source_root=source_root)
        if bound_scan.get("evidence_id") == "fixture-evidence":
            bound_scan["evidence_id"] = f"scan-{index}"
        scans.append(bound_scan)
    current = _bound_inventory(
        current_snapshot
        or _inventory(captured_at=_timestamp(31), evidence_id="current-1"),
        source_root=source_root,
    )
    if current.get("evidence_id") == "fixture-evidence":
        current["evidence_id"] = "current-1"
    before = _protected()
    after = deepcopy(before)
    if mutate_protected:
        changed = PROTECTED_PATHS[0]
        after[changed] = {"length": int(after[changed]["length"]) + 1, "sha256": "f" * 64}
    post = {
        "physical_store_count": 1,
        "old_path_kind": "junction",
        "junction_target": str(target_root),
        "canonical_target": str(target_root),
        "old_path_directory_id": "directory-id-1",
        "target_directory_id": "directory-id-1",
        "protected_root": str(protected_root),
    }
    if post_updates:
        post.update(post_updates)
    return FixtureOperations(
        pending_count=pending_count,
        bindings=bindings or [],
        stable_scans=scans,
        current_snapshot=current,
        target_context={
            "source_root": str(source_root),
            "target_root": str(target_root),
            "agents_root": str(agents_root),
            "pending_root": str(pending_root),
            "protected_root": str(protected_root),
            "same_volume": same_volume,
            "target_exists": target_exists,
            "source_is_reparse": source_is_reparse,
            "pending_is_reparse": False,
            "target_is_reparse": False,
            "target_parent_reparse_free": True,
            "source_volume_serial": 17,
            "target_volume_serial": 17,
            "delete_share_verified": True,
            "source_file_id_verified": True,
            "target_parent_file_id_verified": True,
            "source_directory_id": "directory-id-1",
            "control_root": str(
                source_root.parent / "private-runtime" / "shiguan-migration"
            ),
        },
        post_cutover_state=post,
        protected_before=before,
        protected_after=after,
        protected_root=protected_root,
        receipt_identity={
            "migration_id": "fixture-migration-1",
            "receipt_id": "fixture-receipt-1",
            "run_owner": "bingbu#0001:fixture-run",
            "run_marker_id": "fixture-marker-1",
            "control_root": str(
                source_root.parent / "private-runtime" / "shiguan-migration"
            ),
            "issued_at": _timestamp(32),
            "nonce": "fixture-nonce-1",
        },
    )


def _load_production(errors: list[str]) -> object | None:
    if not PRODUCTION_PATH.is_file():
        errors.append("missing_module:scripts/shiguan_migration_gate.py")
        return None
    spec = importlib.util.spec_from_file_location("shiguan_migration_gate_red_target", PRODUCTION_PATH)
    if spec is None or spec.loader is None:
        errors.append("module_spec_unavailable:scripts/shiguan_migration_gate.py")
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - reported as deterministic RED evidence
        errors.append(f"module_import_error:{type(exc).__name__}:{exc}")
        return None
    return module


def _load_script(path: Path, module_name: str, errors: list[str]) -> object | None:
    if not path.is_file():
        errors.append(f"missing_module:{path.relative_to(ROOT).as_posix()}")
        return None
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        errors.append(f"module_spec_unavailable:{path.relative_to(ROOT).as_posix()}")
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        errors.append(
            f"module_import_error:{path.name}:{type(exc).__name__}:{exc}"
        )
        return None
    return module


def _check_result_shape(name: str, result: object, errors: list[str]) -> dict[str, object] | None:
    if not isinstance(result, dict):
        errors.append(f"{name}:result_not_object")
        return None
    if result.get("schema") != RESULT_SCHEMA:
        errors.append(f"{name}:schema:{result.get('schema')!r}!={RESULT_SCHEMA!r}")
    if result.get("phase") not in {"preflight", "post_cutover"}:
        errors.append(f"{name}:invalid_phase:{result.get('phase')!r}")
    if not isinstance(result.get("status"), str) or not result.get("status"):
        errors.append(f"{name}:missing_status")
    if type(result.get("allowed")) is not bool:
        errors.append(f"{name}:allowed_not_boolean")
    reasons = result.get("reason_codes")
    if not isinstance(reasons, list) or any(not isinstance(item, str) or not item for item in reasons):
        errors.append(f"{name}:invalid_reason_codes")
    return result


def _run_case(
    evaluate: Callable[..., object],
    *,
    name: str,
    phase: str,
    operations: FixtureOperations,
    errors: list[str],
    allowed: bool,
    status: str | None = None,
    reason: str | None = None,
    exact_calls: list[str] | None = None,
    require_bound_receipt: bool = False,
) -> bool:
    before_errors = len(errors)
    try:
        raw = evaluate(phase=phase, operations=operations)
    except Exception as exc:
        errors.append(f"{name}:evaluation_error:{type(exc).__name__}:{exc}")
        return False
    result = _check_result_shape(name, raw, errors)
    if result is None:
        return False
    if result.get("allowed") is not allowed:
        errors.append(f"{name}:allowed:{result.get('allowed')!r}!={allowed!r}")
    if status is not None and result.get("status") != status:
        errors.append(f"{name}:status:{result.get('status')!r}!={status!r}")
    if reason is not None and reason not in result.get("reason_codes", []):
        errors.append(f"{name}:missing_reason:{reason}")
    if require_bound_receipt:
        required = {
            "source_root",
            "target_root",
            "source_directory_id",
            "inventory_digest",
            "migration_id",
            "receipt_id",
            "issued_at",
            "expires_at",
            "nonce",
            "pending_snapshot",
            "binding_snapshot",
            "protected_files_before",
        }
        missing = sorted(field for field in required if field not in result)
        if missing:
            errors.append(f"{name}:unbound_ready_receipt:{','.join(missing)}")
    forbidden = sorted(FORBIDDEN_BODY_OR_MUTATION_OPERATIONS.intersection(operations.calls))
    if forbidden:
        errors.append(f"{name}:forbidden_operations:{','.join(forbidden)}")
    if exact_calls is not None and operations.calls != exact_calls:
        errors.append(f"{name}:call_order:{operations.calls!r}!={exact_calls!r}")
    return len(errors) == before_errors


def _check_cases(evaluate: Callable[..., object], temp_root: Path, errors: list[str]) -> int:
    passed = 0

    cases = [
        {
            "name": "pending_nonzero_short_circuits",
            "phase": "preflight",
            "ops": _fixture(temp_root / "pending-nonzero", pending_count=1),
            "allowed": False,
            "status": PENDING_BLOCK,
            "reason": "pending_bodies_nonzero",
            "calls": ["get_pending_body_count"],
        },
        {
            "name": "pending_unknown_short_circuits",
            "phase": "preflight",
            "ops": _fixture(temp_root / "pending-unknown", pending_count=None),
            "allowed": False,
            "status": PENDING_BLOCK,
            "reason": "pending_bodies_unknown",
            "calls": ["get_pending_body_count"],
        },
        {
            "name": "active_binding_blocks_before_inventory",
            "phase": "preflight",
            "ops": _fixture(temp_root / "active", bindings=[{"state": "active", "record": "r1"}]),
            "allowed": False,
            "reason": "active_binding",
            "calls": ["get_pending_body_count", "get_record_bindings"],
        },
        {
            "name": "stale_binding_blocks_before_inventory",
            "phase": "preflight",
            "ops": _fixture(temp_root / "stale", bindings=[{"state": "stale", "record": "r1"}]),
            "allowed": False,
            "reason": "stale_binding",
            "calls": ["get_pending_body_count", "get_record_bindings"],
        },
        {
            "name": "unknown_binding_blocks_before_inventory",
            "phase": "preflight",
            "ops": _fixture(temp_root / "unknown", bindings=[{"state": "unknown", "record": "*"}]),
            "allowed": False,
            "reason": "unknown_binding",
            "calls": ["get_pending_body_count", "get_record_bindings"],
        },
        {
            "name": "requires_two_stable_scans",
            "phase": "preflight",
            "ops": _fixture(
                temp_root / "one-scan",
                stable_scans=[_inventory(captured_at=_timestamp(0))],
            ),
            "allowed": False,
            "reason": "two_stable_scans_required",
        },
        {
            "name": "requires_thirty_second_scan_interval",
            "phase": "preflight",
            "ops": _fixture(
                temp_root / "short-interval",
                stable_scans=[
                    _inventory(captured_at=_timestamp(0)),
                    _inventory(captured_at=_timestamp(29)),
                ],
            ),
            "allowed": False,
            "reason": "stable_scan_interval_too_short",
        },
        {
            "name": "source_drift_blocks",
            "phase": "preflight",
            "ops": _fixture(
                temp_root / "source-drift",
                current_snapshot=_inventory(captured_at=_timestamp(31), digest="b" * 64),
            ),
            "allowed": False,
            "reason": "source_drift",
        },
        {
            "name": "target_must_stay_under_agents",
            "phase": "preflight",
            "ops": _fixture(temp_root / "target-escape", target_outside_agents=True),
            "allowed": False,
            "reason": "target_outside_agents",
        },
        {
            "name": "source_and_target_must_share_volume",
            "phase": "preflight",
            "ops": _fixture(temp_root / "cross-volume", same_volume=False),
            "allowed": False,
            "reason": "cross_volume_target",
        },
        {
            "name": "target_must_be_absent_before_cutover",
            "phase": "preflight",
            "ops": _fixture(temp_root / "target-exists", target_exists=True),
            "allowed": False,
            "reason": "target_already_exists",
        },
        {
            "name": "source_must_not_be_reparse_point",
            "phase": "preflight",
            "ops": _fixture(temp_root / "source-reparse", source_is_reparse=True),
            "allowed": False,
            "reason": "source_is_reparse_point",
        },
        {
            "name": "stable_metadata_preflight_ready",
            "phase": "preflight",
            "ops": _fixture(temp_root / "ready"),
            "allowed": True,
            "status": READY,
            "bound_receipt": True,
        },
        {
            "name": "post_cutover_rejects_two_physical_stores",
            "phase": "post_cutover",
            "ops": _fixture(
                temp_root / "two-stores",
                post_updates={"physical_store_count": 2},
            ),
            "allowed": False,
            "reason": "multiple_physical_stores",
        },
        {
            "name": "post_cutover_requires_exact_junction",
            "phase": "post_cutover",
            "ops": _fixture(
                temp_root / "wrong-junction",
                post_updates={"junction_target": str(temp_root / "wrong-target")},
            ),
            "allowed": False,
            "reason": "junction_mismatch",
        },
        {
            "name": "protected_cross_conversation_files_unchanged",
            "phase": "post_cutover",
            "ops": _fixture(temp_root / "protected-changed", mutate_protected=True),
            "allowed": False,
            "reason": "protected_file_changed",
        },
        {
            "name": "post_cutover_single_store_and_junction_verified",
            "phase": "post_cutover",
            "ops": _fixture(temp_root / "post-good"),
            "allowed": True,
        },
    ]

    for case in cases:
        if _run_case(
            evaluate,
            name=str(case["name"]),
            phase=str(case["phase"]),
            operations=case["ops"],  # type: ignore[arg-type]
            errors=errors,
            allowed=bool(case["allowed"]),
            status=case.get("status"),  # type: ignore[arg-type]
            reason=case.get("reason"),  # type: ignore[arg-type]
            exact_calls=case.get("calls"),  # type: ignore[arg-type]
            require_bound_receipt=bool(case.get("bound_receipt", False)),
        ):
            passed += 1
    return passed


def _check_phase2_gate_cases(
    evaluate: Callable[..., object],
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    results: dict[str, bool] = {}

    def run_gate(operations: FixtureOperations, label: str) -> dict[str, object] | None:
        try:
            value = evaluate(phase="preflight", operations=operations)
        except Exception as exc:
            errors.append(
                f"{label}:evaluation_error:{type(exc).__name__}:{exc}"
            )
            return None
        if not isinstance(value, dict):
            errors.append(f"{label}:result_not_object")
            return None
        return value

    case_id = "P2-GATE-READY-BINDING-001"
    before = len(errors)
    ready_ops = _fixture(temp_root / case_id.lower())
    ready = run_gate(ready_ops, case_id)
    required = {
        "source_root",
        "target_root",
        "source_volume_serial",
        "source_directory_id",
        "file_count",
        "total_bytes",
        "newest_mtime_utc",
        "inventory_digest",
        "exclusion_policy_id",
        "inventory_captured_at",
        "inventory_evidence_id",
        "migration_id",
        "receipt_id",
        "run_owner",
        "run_marker_id",
        "control_root",
        "issued_at",
        "expires_at",
        "nonce",
        "pending_snapshot",
        "binding_snapshot",
        "protected_files_before",
    }
    if ready is None or ready.get("status") != READY or ready.get("allowed") is not True:
        errors.append(f"{case_id}:valid_evidence_not_ready")
    else:
        missing = sorted(required.difference(ready))
        if missing:
            errors.append(f"{case_id}:missing_fields:{','.join(missing)}")
        if ready.get("binding_snapshot") != {"bindings": []}:
            errors.append(f"{case_id}:binding_snapshot_not_empty")
        control = Path(str(ready.get("control_root", ""))).resolve(strict=False)
        for field in ("source_root", "target_root"):
            inventory_root = Path(str(ready.get(field, ""))).resolve(strict=False)
            if control == inventory_root or control.is_relative_to(inventory_root):
                errors.append(f"{case_id}:control_inside_{field}")
    results[case_id] = len(errors) == before

    case_id = "P2-GATE-EVIDENCE-STRICT-002"
    before = len(errors)

    def expect_evidence_blocked(
        label: str,
        mutate: Callable[[FixtureOperations], None],
        expected_reason: str,
    ) -> None:
        operations = _fixture(temp_root / case_id.lower() / label)
        mutate(operations)
        value = run_gate(operations, f"{case_id}:{label}")
        reasons = value.get("reason_codes", []) if isinstance(value, dict) else []
        if (
            not isinstance(value, dict)
            or value.get("allowed") is not False
            or expected_reason not in reasons
        ):
            errors.append(
                f"{case_id}:{label}:not_blocked_as:{expected_reason}:"
                f"{value!r}"
            )

    def mutate_all_inventory(
        operations: FixtureOperations, field: str, value: object
    ) -> None:
        for snapshot in [*operations.stable_scans, operations.current_snapshot]:
            if value is _DELETE:
                snapshot.pop(field, None)
            else:
                snapshot[field] = deepcopy(value)

    expect_evidence_blocked(
        "canonical_source_mismatch",
        lambda ops: mutate_all_inventory(
            ops, "canonical_source_root", str(temp_root / "other-source")
        ),
        "source_identity_mismatch",
    )
    expect_evidence_blocked(
        "volume_identity_mismatch",
        lambda ops: mutate_all_inventory(ops, "source_volume_serial", 99),
        "source_identity_mismatch",
    )
    expect_evidence_blocked(
        "directory_identity_mismatch",
        lambda ops: mutate_all_inventory(
            ops, "source_directory_id", "other-directory"
        ),
        "source_identity_mismatch",
    )
    expect_evidence_blocked(
        "digest_not_sha256",
        lambda ops: mutate_all_inventory(ops, "inventory_digest", "g" * 64),
        "stable_scans_malformed",
    )
    expect_evidence_blocked(
        "newest_mtime_not_aware",
        lambda ops: mutate_all_inventory(
            ops, "newest_mtime_utc", "2026-07-14T00:00:00"
        ),
        "stable_scans_malformed",
    )
    expect_evidence_blocked(
        "missing_exclusion_policy",
        lambda ops: mutate_all_inventory(ops, "exclusion_policy_id", _DELETE),
        "stable_scans_malformed",
    )

    def duplicate_evidence(operations: FixtureOperations) -> None:
        operations.stable_scans[1]["evidence_id"] = operations.stable_scans[0][
            "evidence_id"
        ]

    expect_evidence_blocked(
        "duplicate_evidence",
        duplicate_evidence,
        "duplicate_scan_evidence",
    )

    def future_evidence(operations: FixtureOperations) -> None:
        operations.stable_scans[0]["captured_at"] = _timestamp(120)
        operations.stable_scans[1]["captured_at"] = _timestamp(150)
        operations.current_snapshot["captured_at"] = _timestamp(151)

    expect_evidence_blocked(
        "future_evidence", future_evidence, "future_scan_evidence"
    )

    def stale_evidence(operations: FixtureOperations) -> None:
        operations.stable_scans[0]["captured_at"] = _timestamp(-1000)
        operations.stable_scans[1]["captured_at"] = _timestamp(-970)
        operations.current_snapshot["captured_at"] = _timestamp(-969)

    expect_evidence_blocked(
        "stale_evidence", stale_evidence, "stale_scan_evidence"
    )
    results[case_id] = len(errors) == before

    case_id = "P2-GATE-BINDINGS-EMPTY-003"
    before = len(errors)
    for label, bindings, reason in (
        ("active", [{"state": "active", "record": "r1"}], "active_binding"),
        ("stale", [{"state": "stale", "record": "r1"}], "stale_binding"),
        ("unknown", [{"state": "unknown", "record": "r1"}], "unknown_binding"),
        ("inactive", [{"state": "inactive", "record": "r1"}], "nonempty_binding_evidence"),
    ):
        operations = _fixture(temp_root / case_id.lower() / label, bindings=bindings)
        value = run_gate(operations, f"{case_id}:{label}")
        reasons = value.get("reason_codes", []) if isinstance(value, dict) else []
        if (
            not isinstance(value, dict)
            or value.get("allowed") is not False
            or reason not in reasons
        ):
            errors.append(f"{case_id}:{label}:not_blocked_as:{reason}:{value!r}")
    results[case_id] = len(errors) == before

    case_id = "P2-WIN-ROOT-SAFETY-004"
    before = len(errors)

    def expect_context_blocked(
        label: str,
        mutate: Callable[[FixtureOperations], None],
        expected_reason: str,
    ) -> None:
        operations = _fixture(temp_root / case_id.lower() / label)
        mutate(operations)
        value = run_gate(operations, f"{case_id}:{label}")
        reasons = value.get("reason_codes", []) if isinstance(value, dict) else []
        if (
            not isinstance(value, dict)
            or value.get("allowed") is not False
            or expected_reason not in reasons
        ):
            errors.append(
                f"{case_id}:{label}:not_blocked_as:{expected_reason}:{value!r}"
            )

    expect_context_blocked(
        "pending_reparse",
        lambda ops: ops.target_context.__setitem__("pending_is_reparse", True),
        "pending_is_reparse_point",
    )
    expect_context_blocked(
        "target_reparse",
        lambda ops: ops.target_context.__setitem__("target_is_reparse", True),
        "target_is_reparse_point",
    )
    expect_context_blocked(
        "target_parent_reparse_unknown",
        lambda ops: ops.target_context.__setitem__(
            "target_parent_reparse_free", False
        ),
        "target_parent_reparse_untrusted",
    )
    expect_context_blocked(
        "delete_share_unknown",
        lambda ops: ops.target_context.__setitem__("delete_share_verified", None),
        "delete_share_unverified",
    )
    expect_context_blocked(
        "source_file_id_unknown",
        lambda ops: ops.target_context.__setitem__("source_file_id_verified", None),
        "file_id_unverified",
    )
    expect_context_blocked(
        "target_file_id_unknown",
        lambda ops: ops.target_context.__setitem__(
            "target_parent_file_id_verified", None
        ),
        "file_id_unverified",
    )

    for label, leaf, reason in (
        ("alternate_data_stream", "bad:ads", "unsafe_target_path"),
        ("device_name", "CON", "unsafe_target_path"),
        ("trailing_dot", "bad.", "unsafe_target_path"),
    ):
        def mutate_target(
            operations: FixtureOperations, *, _leaf: str = leaf
        ) -> None:
            agents_root = Path(str(operations.target_context["agents_root"]))
            operations.target_context["target_root"] = str(
                agents_root / _leaf / "references"
            )

        expect_context_blocked(label, mutate_target, reason)

    def self_migration(operations: FixtureOperations) -> None:
        source = Path(str(operations.target_context["source_root"]))
        operations.target_context["agents_root"] = str(source.parent.parent.parent)
        operations.target_context["target_root"] = str(source)

    expect_context_blocked("self_migration", self_migration, "self_migration")
    results[case_id] = len(errors) == before
    return results


def _ready_receipt(operations: CutoverFixtureOperations) -> dict[str, object]:
    return {
        "schema": RESULT_SCHEMA,
        "phase": "preflight",
        "status": READY,
        "allowed": True,
        "reason_codes": ["preflight_verified"],
        "pending_count": 0,
        "source_root": str(operations.source_root),
        "target_root": str(operations.target_root),
        "protected_root": str(operations.protected_root),
        "source_volume_serial": operations.volume_serial,
        "source_directory_id": operations.directory_id,
        "file_count": operations.inventory["file_count"],
        "total_bytes": operations.inventory["total_bytes"],
        "newest_mtime_utc": operations.inventory["newest_mtime_utc"],
        "inventory_digest": operations.inventory["inventory_digest"],
        "exclusion_policy_id": operations.exclusion_policy_id,
        "inventory_captured_at": operations.inventory["captured_at"],
        "inventory_evidence_id": operations.inventory["evidence_id"],
        "migration_id": operations.migration_id,
        "receipt_id": operations.receipt_id,
        "run_owner": operations.run_owner,
        "run_marker_id": operations.run_marker_id,
        "control_root": str(operations.control_root),
        "issued_at": operations.issued_at,
        "expires_at": _timestamp(332),
        "nonce": operations.nonce,
        "pending_snapshot": deepcopy(operations.pending_snapshot),
        "binding_snapshot": deepcopy(operations.binding_snapshot),
        "protected_files_before": deepcopy(operations.protected_before),
    }


def _check_cutover_cases(
    evaluate_gate: Callable[..., object],
    execute: Callable[..., object],
    cutover_module: object,
    temp_root: Path,
    errors: list[str],
) -> int:
    passed = 0

    def run(
        name: str,
        operations: CutoverFixtureOperations,
        *,
        expected_status: str,
        expected_ok: bool,
        expected_events: list[str],
        gate_receipt: dict[str, object] | None = None,
    ) -> None:
        nonlocal passed
        before = len(errors)
        try:
            raw = execute(
                gate_receipt=gate_receipt or _ready_receipt(operations),
                operations=operations,
            )
        except Exception as exc:
            errors.append(f"{name}:execution_error:{type(exc).__name__}:{exc}")
            return
        if not isinstance(raw, dict):
            errors.append(f"{name}:result_not_object")
            return
        if raw.get("ok") is not expected_ok:
            errors.append(f"{name}:ok:{raw.get('ok')!r}!={expected_ok!r}")
        if raw.get("status") != expected_status:
            errors.append(
                f"{name}:status:{raw.get('status')!r}!={expected_status!r}"
            )
        if operations.events != expected_events:
            errors.append(
                f"{name}:events:{operations.events!r}!={expected_events!r}"
            )
        if expected_ok:
            if not operations.daemon_running or not operations.renamed or not operations.junction_created:
                errors.append(f"{name}:successful_state_not_preserved")
            rollback = raw.get("rollback")
            if not isinstance(rollback, dict) or rollback.get("applied") is not False:
                errors.append(f"{name}:unexpected_rollback")
        else:
            if operations.renamed or operations.junction_created or not operations.daemon_running:
                errors.append(f"{name}:rollback_state_not_restored")
        if len(errors) == before:
            passed += 1

    success = CutoverFixtureOperations(temp_root / "cutover-success")
    run(
        "cutover_success_order",
        success,
        expected_status=CUTOVER_VERIFIED,
        expected_ok=True,
        expected_events=[
            "acquire_migration_run",
            "inspect_cutover_context",
            "stop_daemon",
            "snapshot_source",
            "atomic_rename_to_target",
            "create_compatibility_junction",
            "verify_post_cutover",
            "start_daemon",
            "inspect_final_cutover_state",
            "release_migration_run",
        ],
    )

    before_rename = CutoverFixtureOperations(
        temp_root / "failure-before-rename", fail_at="snapshot_source"
    )
    run(
        "failure_before_rename_restarts_daemon",
        before_rename,
        expected_status=CUTOVER_ROLLED_BACK,
        expected_ok=False,
        expected_events=[
            "acquire_migration_run",
            "inspect_cutover_context",
            "stop_daemon",
            "snapshot_source",
            "verify_run_owner",
            "verify_run_owner",
            "start_daemon",
            "release_migration_run",
        ],
    )

    after_rename = CutoverFixtureOperations(
        temp_root / "failure-after-rename",
        fail_at="create_compatibility_junction",
    )
    run(
        "failure_after_rename_restores_source",
        after_rename,
        expected_status=CUTOVER_ROLLED_BACK,
        expected_ok=False,
        expected_events=[
            "acquire_migration_run",
            "inspect_cutover_context",
            "stop_daemon",
            "snapshot_source",
            "atomic_rename_to_target",
            "create_compatibility_junction",
            "verify_run_owner",
            "verify_run_owner",
            "atomic_rename_to_source",
            "verify_run_owner",
            "start_daemon",
            "release_migration_run",
        ],
    )

    after_junction = CutoverFixtureOperations(
        temp_root / "failure-after-junction", fail_at="verify_post_cutover"
    )
    run(
        "failure_after_junction_removes_only_exact_link",
        after_junction,
        expected_status=CUTOVER_ROLLED_BACK,
        expected_ok=False,
        expected_events=[
            "acquire_migration_run",
            "inspect_cutover_context",
            "stop_daemon",
            "snapshot_source",
            "atomic_rename_to_target",
            "create_compatibility_junction",
            "verify_post_cutover",
            "verify_run_owner",
            "verify_run_owner",
            "remove_compatibility_junction",
            "verify_run_owner",
            "atomic_rename_to_source",
            "verify_run_owner",
            "start_daemon",
            "release_migration_run",
        ],
    )

    blocked = CutoverFixtureOperations(temp_root / "blocked-nonzero")
    blocked_receipt = _ready_receipt(blocked)
    blocked_receipt.update(
        {"allowed": False, "status": PENDING_BLOCK, "pending_count": 69}
    )
    run(
        "nonzero_pending_receipt_blocks_before_operations",
        blocked,
        expected_status="CUTOVER_BLOCKED",
        expected_ok=False,
        expected_events=[],
        gate_receipt=blocked_receipt,
    )

    stale = CutoverFixtureOperations(
        temp_root / "stale-final-recheck",
        final_recheck_updates={"receipt_id": "stale-receipt"},
        track_final_recheck=True,
    )
    before = len(errors)
    try:
        stale_result = execute(
            gate_receipt=_ready_receipt(stale), operations=stale
        )
    except Exception as exc:
        errors.append(
            f"stale_receipt_final_recheck:execution_error:{type(exc).__name__}:{exc}"
        )
    else:
        if "final_metadata_recheck" not in stale.events:
            errors.append("stale_receipt_final_recheck:callback_not_called")
        elif stale.events.index("final_metadata_recheck") < stale.events.index(
            "stop_daemon"
        ):
            errors.append("stale_receipt_final_recheck:callback_before_daemon_stop")
        if "atomic_rename_to_target" in stale.events or stale.renamed or stale.junction_created:
            errors.append("stale_receipt_final_recheck:rename_or_junction_occurred")
        if not stale.daemon_running:
            errors.append("stale_receipt_final_recheck:daemon_not_restored")
        if not isinstance(stale_result, dict) or stale_result.get("status") == CUTOVER_VERIFIED:
            errors.append("stale_receipt_final_recheck:stale_receipt_verified")
    if len(errors) == before:
        passed += 1

    side_effect_before = len(errors)
    for stage in (
        "stop_daemon",
        "atomic_rename_to_target",
        "create_compatibility_junction",
        "start_daemon",
    ):
        operations = CutoverFixtureOperations(
            temp_root / f"side-effect-{stage}",
            fail_at=stage,
            fail_after_effect=True,
            track_actual_state=True,
        )
        try:
            result = execute(
                gate_receipt=_ready_receipt(operations), operations=operations
            )
        except Exception as exc:
            errors.append(
                f"side_effect_then_raise:{stage}:execution_error:{type(exc).__name__}:{exc}"
            )
            continue
        if not isinstance(result, dict) or result.get("ok") is not False:
            errors.append(f"side_effect_then_raise:{stage}:failure_not_reported")
        if "inspect_actual_state" not in operations.events:
            errors.append(f"side_effect_then_raise:{stage}:actual_state_not_probed")
        if operations.renamed or operations.junction_created or not operations.daemon_running:
            errors.append(f"side_effect_then_raise:{stage}:rollback_state_not_restored")
        if stage == "create_compatibility_junction":
            try:
                removed_at = operations.events.index("remove_compatibility_junction")
                renamed_at = operations.events.index("atomic_rename_to_source")
            except ValueError:
                errors.append("side_effect_then_raise:create_compatibility_junction:reverse_actions_missing")
            else:
                if removed_at > renamed_at:
                    errors.append("side_effect_then_raise:create_compatibility_junction:reverse_order_invalid")
    if len(errors) == side_effect_before:
        passed += 1

    protected_after = _protected()
    changed = PROTECTED_PATHS[0]
    protected_after[changed] = {
        "length": int(protected_after[changed]["length"]) + 1,
        "sha256": "f" * 64,
    }
    protected = CutoverFixtureOperations(
        temp_root / "protected-postcheck",
        protected_after=protected_after,
        track_protected_postcheck=True,
    )
    before = len(errors)
    try:
        protected_result = execute(
            gate_receipt=_ready_receipt(protected), operations=protected
        )
    except Exception as exc:
        errors.append(
            f"protected_postcheck:execution_error:{type(exc).__name__}:{exc}"
        )
    else:
        if "get_protected_file_snapshot" not in protected.events:
            errors.append("protected_postcheck:snapshot_not_rechecked")
        if not isinstance(protected_result, dict) or protected_result.get("status") == CUTOVER_VERIFIED:
            errors.append("protected_postcheck:changed_file_verified")
        if protected.renamed or protected.junction_created or not protected.daemon_running:
            errors.append("protected_postcheck:rollback_state_not_restored")
        reasons = protected_result.get("reason_codes", []) if isinstance(protected_result, dict) else []
        if not any("protected" in reason for reason in reasons if isinstance(reason, str)):
            errors.append("protected_postcheck:missing_protected_reason")
    if len(errors) == before:
        passed += 1

    def run_production_receipt(
        name: str,
        root: Path,
        *,
        final_updates: dict[str, object] | None = None,
        expected_success: bool,
    ) -> None:
        nonlocal passed
        case_before = len(errors)
        gate_operations = _fixture(root)
        try:
            receipt = evaluate_gate(phase="preflight", operations=gate_operations)
        except Exception as exc:
            errors.append(
                f"{name}:gate_error:{type(exc).__name__}:{exc}"
            )
            return
        if not isinstance(receipt, dict) or receipt.get("status") != READY:
            errors.append(f"{name}:production_gate_not_ready")
            return
        receipt_before = deepcopy(receipt)
        operations = CutoverFixtureOperations(
            root,
            final_recheck_updates=final_updates,
            track_final_recheck=not expected_success,
        )
        try:
            result = execute(gate_receipt=receipt, operations=operations)
        except Exception as exc:
            errors.append(
                f"{name}:cutover_error:{type(exc).__name__}:{exc}"
            )
            return
        if receipt != receipt_before:
            errors.append(f"{name}:production_receipt_mutated")
        if expected_success:
            if (
                not isinstance(result, dict)
                or result.get("status") != CUTOVER_VERIFIED
                or not operations.daemon_running
                or not operations.renamed
                or not operations.junction_created
            ):
                errors.append(f"{name}:production_receipt_cutover_not_verified")
        else:
            if "final_metadata_recheck" not in operations.events:
                errors.append(f"{name}:final_metadata_recheck_not_called")
            if (
                not isinstance(result, dict)
                or result.get("status") == CUTOVER_VERIFIED
            ):
                errors.append(f"{name}:metadata_drift_verified")
            if (
                "atomic_rename_to_target" in operations.events
                or operations.renamed
                or operations.junction_created
            ):
                errors.append(f"{name}:rename_or_junction_occurred")
            if not operations.daemon_running:
                errors.append(f"{name}:daemon_not_restored")
        if len(errors) == case_before:
            passed += 1

    run_production_receipt(
        "production_gate_receipt_cutover_success",
        temp_root / "production-receipt-success",
        expected_success=True,
    )
    run_production_receipt(
        "production_receipt_pending_drift",
        temp_root / "production-receipt-pending-drift",
        final_updates={"pending_count": 69},
        expected_success=False,
    )
    run_production_receipt(
        "production_receipt_binding_drift",
        temp_root / "production-receipt-binding-drift",
        final_updates={
            "binding_snapshot": {
                "bindings": [{"state": "active", "record": "drift"}]
            }
        },
        expected_success=False,
    )

    for mode in ("before", "after"):
        name = f"junction_remove_failure_{mode}"
        operations = CutoverFixtureOperations(
            temp_root / name,
            fail_at="verify_post_cutover",
            remove_failure=mode,
            track_actual_state=True,
        )
        case_before = len(errors)
        try:
            result = execute(
                gate_receipt=_ready_receipt(operations), operations=operations
            )
        except Exception as exc:
            errors.append(f"{name}:execution_error:{type(exc).__name__}:{exc}")
            continue
        rollback = result.get("rollback") if isinstance(result, dict) else None
        if not isinstance(result, dict) or result.get("status") != CUTOVER_ROLLBACK_FAILED:
            errors.append(f"{name}:rollback_failure_not_reported")
        if "atomic_rename_to_source" in operations.events:
            errors.append(f"{name}:reverse_rename_attempted")
        if operations.daemon_running:
            errors.append(f"{name}:daemon_not_conservatively_stopped")
        if not isinstance(rollback, dict) or rollback.get("conservative_stopped") is not True:
            errors.append(f"{name}:conservative_stopped_not_true")
        if len(errors) == case_before:
            passed += 1

    persist_name = "_persist_cutover_receipt"
    reread_name = "_reread_cutover_receipt"
    original_persist = getattr(cutover_module, persist_name, None)
    original_reread = getattr(cutover_module, reread_name, None)
    had_persist = hasattr(cutover_module, persist_name)
    had_reread = hasattr(cutover_module, reread_name)

    def restore_receipt_helpers() -> None:
        if had_persist:
            setattr(cutover_module, persist_name, original_persist)
        else:
            delattr(cutover_module, persist_name)
        if had_reread:
            setattr(cutover_module, reread_name, original_reread)
        else:
            delattr(cutover_module, reread_name)

    for mode in ("success", "write_failure", "reread_failure"):
        name = f"cutover_receipt_persistence_{mode}"
        operations = CutoverFixtureOperations(temp_root / name)
        receipt_path = (
            operations.source_root.parent
            / "private-runtime"
            / "shiguan-migration"
            / "shiguan-cutover-receipt.json"
        )
        inventory_before = deepcopy(operations.inventory)
        case_before = len(errors)

        def tracked_persist(
            path: Path, receipt: dict[str, object], *, _mode: str = mode
        ) -> None:
            operations.events.append("persist_cutover_receipt")
            if (
                _mode == "write_failure"
                and receipt.get("status") == CUTOVER_VERIFIED
            ):
                raise OSError("injected receipt persistence failure")
            if not callable(original_persist):
                raise RuntimeError("production receipt persistence helper missing")
            original_persist(path, receipt)

        def tracked_reread(
            path: Path,
            expected: dict[str, object],
            *, _mode: str = mode,
        ) -> dict[str, object]:
            operations.events.append("reread_cutover_receipt")
            if (
                _mode == "reread_failure"
                and expected.get("status") == CUTOVER_VERIFIED
            ):
                raise OSError("injected receipt reread failure")
            if not callable(original_reread):
                raise RuntimeError("production receipt reread helper missing")
            return original_reread(path, expected)

        setattr(cutover_module, persist_name, tracked_persist)
        setattr(cutover_module, reread_name, tracked_reread)
        try:
            result = execute(
                gate_receipt=_ready_receipt(operations), operations=operations
            )
        except Exception as exc:
            errors.append(f"{name}:execution_error:{type(exc).__name__}:{exc}")
            restore_receipt_helpers()
            continue
        finally:
            if hasattr(cutover_module, persist_name):
                restore_receipt_helpers()

        if operations.inventory != inventory_before:
            errors.append(f"{name}:source_inventory_changed")
        if receipt_path.is_relative_to(operations.source_root) or receipt_path.is_relative_to(
            operations.target_root
        ):
            errors.append(f"{name}:receipt_inside_migration_inventory")
        if mode == "success":
            if not isinstance(result, dict) or result.get("status") != CUTOVER_VERIFIED:
                errors.append(f"{name}:cutover_not_verified")
            required_order = (
                "start_daemon",
                "inspect_final_cutover_state",
                "persist_cutover_receipt",
                "reread_cutover_receipt",
            )
            try:
                positions = [operations.events.index(event) for event in required_order]
            except ValueError:
                errors.append(f"{name}:event_order_missing:{operations.events!r}")
            else:
                if positions != sorted(positions):
                    errors.append(f"{name}:event_order_invalid:{operations.events!r}")
            if not receipt_path.is_file():
                errors.append(f"{name}:receipt_not_persisted")
        else:
            if not isinstance(result, dict) or result.get("status") == CUTOVER_VERIFIED:
                errors.append(f"{name}:failure_verified")
            if operations.renamed or operations.junction_created or not operations.daemon_running:
                errors.append(f"{name}:rollback_state_not_restored")
        if len(errors) == case_before:
            passed += 1

    ttl_before = len(errors)
    ttl_operations = CutoverFixtureOperations(temp_root / "expired-ready-receipt")
    expired_receipt = _ready_receipt(ttl_operations)
    expired_receipt.update(
        {
            "issued_at": "2000-01-01T00:00:00+00:00",
            "expires_at": "2000-01-01T00:05:00+00:00",
        }
    )
    try:
        expired_result = execute(
            gate_receipt=expired_receipt,
            operations=ttl_operations,
            clock=lambda: FIXTURE_NOW,
        )
    except Exception as exc:
        errors.append(f"ready_receipt_ttl:execution_error:{type(exc).__name__}:{exc}")
    else:
        if not isinstance(expired_result, dict) or expired_result.get("status") != "CUTOVER_BLOCKED":
            errors.append("ready_receipt_ttl:expired_receipt_not_blocked")
        if ttl_operations.events:
            errors.append(f"ready_receipt_ttl:operations_started:{ttl_operations.events!r}")
    if len(errors) == ttl_before:
        passed += 1
    return passed


def _check_phase2_cutover_cases(
    execute: Callable[..., object],
    cutover_module: object,
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    results: dict[str, bool] = {}

    case_id = "P2-RUN-OWNER-LOCK-005"
    before = len(errors)
    foreign = CutoverFixtureOperations(
        temp_root / case_id.lower() / "foreign-owner",
        lock_owner_override="foreign-run-owner",
    )
    try:
        foreign_result = execute(
            gate_receipt=_ready_receipt(foreign), operations=foreign
        )
    except Exception as exc:
        errors.append(f"{case_id}:foreign_owner:execution_error:{type(exc).__name__}:{exc}")
    else:
        if (
            not isinstance(foreign_result, dict)
            or foreign_result.get("status") != "CUTOVER_BLOCKED"
        ):
            errors.append(f"{case_id}:foreign_owner:not_blocked:{foreign_result!r}")
        if not {"acquire_migration_run", "release_migration_run"}.issubset(
            foreign.events
        ):
            errors.append(f"{case_id}:foreign_owner:run_lock_not_used:{foreign.events!r}")
        if any(
            event in foreign.events
            for event in (
                "stop_daemon",
                "atomic_rename_to_target",
                "create_compatibility_junction",
                "remove_compatibility_junction",
                "atomic_rename_to_source",
            )
        ):
            errors.append(f"{case_id}:foreign_owner:side_effects:{foreign.events!r}")

    mismatch = CutoverFixtureOperations(
        temp_root / case_id.lower() / "migration-mismatch"
    )
    mismatch_receipt = _ready_receipt(mismatch)
    mismatch_receipt["migration_id"] = "foreign-migration"
    try:
        mismatch_result = execute(
            gate_receipt=mismatch_receipt, operations=mismatch
        )
    except Exception as exc:
        errors.append(
            f"{case_id}:migration_mismatch:execution_error:{type(exc).__name__}:{exc}"
        )
    else:
        if (
            not isinstance(mismatch_result, dict)
            or mismatch_result.get("status") != "CUTOVER_BLOCKED"
        ):
            errors.append(
                f"{case_id}:migration_mismatch:not_blocked:{mismatch_result!r}"
            )
        if "stop_daemon" in mismatch.events:
            errors.append(
                f"{case_id}:migration_mismatch:daemon_stopped:{mismatch.events!r}"
            )
    results[case_id] = len(errors) == before

    persist_name = "_persist_cutover_receipt"
    reread_name = "_reread_cutover_receipt"
    original_persist = getattr(cutover_module, persist_name, None)
    original_reread = getattr(cutover_module, reread_name, None)

    def restore_helpers() -> None:
        if callable(original_persist):
            setattr(cutover_module, persist_name, original_persist)
        if callable(original_reread):
            setattr(cutover_module, reread_name, original_reread)

    case_id = "P2-CUTOVER-COMMIT-ORDER-006"
    before = len(errors)
    success = CutoverFixtureOperations(temp_root / case_id.lower())

    def success_persist(path: Path, receipt: dict[str, object]) -> None:
        success.events.append("persist_cutover_receipt")
        if not callable(original_persist):
            raise RuntimeError("production receipt persistence helper missing")
        original_persist(path, receipt)

    def success_reread(
        path: Path, expected: dict[str, object]
    ) -> dict[str, object]:
        success.events.append("reread_cutover_receipt")
        if not callable(original_reread):
            raise RuntimeError("production receipt reread helper missing")
        return original_reread(path, expected)

    setattr(cutover_module, persist_name, success_persist)
    setattr(cutover_module, reread_name, success_reread)
    try:
        success_result = execute(
            gate_receipt=_ready_receipt(success), operations=success
        )
    except Exception as exc:
        errors.append(f"{case_id}:execution_error:{type(exc).__name__}:{exc}")
        success_result = None
    finally:
        restore_helpers()
    if not isinstance(success_result, dict) or success_result.get("status") != CUTOVER_VERIFIED:
        errors.append(f"{case_id}:success_not_verified:{success_result!r}")
    else:
        for field in (
            "source_volume_serial",
            "source_directory_id",
            "file_count",
            "total_bytes",
            "newest_mtime_utc",
            "inventory_digest",
            "exclusion_policy_id",
            "migration_id",
            "run_owner",
            "run_marker_id",
            "control_root",
        ):
            if field not in success_result:
                errors.append(f"{case_id}:receipt_missing:{field}")
        if success_result.get("binding_snapshot") != {"bindings": []}:
            errors.append(f"{case_id}:receipt_bindings_not_empty")
        rollback = success_result.get("rollback")
        if not isinstance(rollback, dict) or rollback.get("applied") is not False or rollback.get("ok") is not True:
            errors.append(f"{case_id}:receipt_rollback_not_terminal_clean")
    required_order = (
        "acquire_migration_run",
        "stop_daemon",
        "atomic_rename_to_target",
        "create_compatibility_junction",
        "start_daemon",
        "inspect_final_cutover_state",
        "persist_cutover_receipt",
        "reread_cutover_receipt",
        "release_migration_run",
    )
    try:
        positions = [success.events.index(event) for event in required_order]
    except ValueError:
        errors.append(f"{case_id}:event_order_missing:{success.events!r}")
    else:
        if positions != sorted(positions):
            errors.append(f"{case_id}:event_order_invalid:{success.events!r}")
    receipt_path = success.control_root / "shiguan-cutover-receipt.json"
    if not receipt_path.is_file():
        errors.append(f"{case_id}:atomic_receipt_missing")
    if list(success.control_root.glob(f".{receipt_path.name}.*.tmp")):
        errors.append(f"{case_id}:atomic_temp_residue")
    results[case_id] = len(errors) == before

    case_id = "P2-CUTOVER-TERMINAL-RECEIPT-007"
    before = len(errors)
    for mode in ("start_after_effect", "sharing_violation", "terminal_rewrite_failure"):
        operations = CutoverFixtureOperations(
            temp_root / case_id.lower() / mode,
            fail_at="start_daemon" if mode != "sharing_violation" else None,
            fail_after_effect=mode != "sharing_violation",
        )
        persisted_statuses: list[str] = []
        reread_statuses: list[str] = []

        def tracked_persist(
            path: Path,
            receipt: dict[str, object],
            *,
            _mode: str = mode,
        ) -> None:
            status = str(receipt.get("status"))
            operations.events.append(f"persist:{status}")
            persisted_statuses.append(status)
            if _mode == "sharing_violation" and status == CUTOVER_VERIFIED:
                raise PermissionError("sharing violation")
            if _mode == "terminal_rewrite_failure" and status != CUTOVER_VERIFIED:
                raise PermissionError("terminal receipt rewrite failure")
            if not callable(original_persist):
                raise RuntimeError("production receipt persistence helper missing")
            original_persist(path, receipt)

        def tracked_reread(
            path: Path,
            expected: dict[str, object],
        ) -> dict[str, object]:
            status = str(expected.get("status"))
            operations.events.append(f"reread:{status}")
            reread_statuses.append(status)
            if not callable(original_reread):
                raise RuntimeError("production receipt reread helper missing")
            return original_reread(path, expected)

        setattr(cutover_module, persist_name, tracked_persist)
        setattr(cutover_module, reread_name, tracked_reread)
        try:
            result = execute(
                gate_receipt=_ready_receipt(operations), operations=operations
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:{mode}:execution_error:{type(exc).__name__}:{exc}"
            )
            result = None
        finally:
            restore_helpers()

        if mode == "terminal_rewrite_failure":
            if (
                not isinstance(result, dict)
                or result.get("status") != CUTOVER_ROLLBACK_FAILED
                or operations.daemon_running
            ):
                errors.append(
                    f"{case_id}:{mode}:not_conservatively_stopped:{result!r}:"
                    f"{operations.events!r}"
                )
            rollback = result.get("rollback") if isinstance(result, dict) else None
            if not isinstance(rollback, dict) or rollback.get("conservative_stopped") is not True:
                errors.append(f"{case_id}:{mode}:conservative_stopped_not_true")
            continue

        if (
            not isinstance(result, dict)
            or result.get("status") != CUTOVER_ROLLED_BACK
        ):
            errors.append(f"{case_id}:{mode}:exact_status:{result!r}")
        terminal_statuses = {
            CUTOVER_ROLLED_BACK,
            CUTOVER_ROLLBACK_FAILED,
        }
        if not persisted_statuses or persisted_statuses[-1] not in terminal_statuses:
            errors.append(
                f"{case_id}:{mode}:terminal_receipt_not_rewritten:{persisted_statuses!r}"
            )
        if not reread_statuses or reread_statuses[-1] not in terminal_statuses:
            errors.append(
                f"{case_id}:{mode}:terminal_receipt_not_reread:{reread_statuses!r}"
            )
    results[case_id] = len(errors) == before

    case_id = "P2-ROLLBACK-RUN-OWNER-008"
    before = len(errors)
    owner_drift = CutoverFixtureOperations(
        temp_root / case_id.lower(),
        fail_at="verify_post_cutover",
        owner_drift_on_rollback=True,
        track_actual_state=True,
    )
    try:
        owner_result = execute(
            gate_receipt=_ready_receipt(owner_drift), operations=owner_drift
        )
    except Exception as exc:
        errors.append(f"{case_id}:execution_error:{type(exc).__name__}:{exc}")
        owner_result = None
    if (
        not isinstance(owner_result, dict)
        or owner_result.get("status") != CUTOVER_ROLLBACK_FAILED
    ):
        errors.append(f"{case_id}:exact_status:{owner_result!r}")
    if "verify_run_owner" not in owner_drift.events:
        errors.append(f"{case_id}:owner_not_rechecked:{owner_drift.events!r}")
    if any(
        event in owner_drift.events
        for event in ("remove_compatibility_junction", "atomic_rename_to_source")
    ):
        errors.append(f"{case_id}:foreign_run_dismantled:{owner_drift.events!r}")
    if owner_drift.daemon_running:
        errors.append(f"{case_id}:not_conservatively_stopped")
    results[case_id] = len(errors) == before
    return results


def _check_default_shared_root(
    module: object, temp_root: Path, errors: list[str]
) -> int:
    target = getattr(module, "default_shared_root", None)
    if not callable(target):
        errors.append("missing_callable:default_shared_root")
        return 0
    home = temp_root / "home"
    expected = (
        home / ".agents" / "court-shiguan" / "decretum-matrix"
    ).resolve()
    try:
        actual = target(home)
    except Exception as exc:
        errors.append(
            f"default_shared_root:execution_error:{type(exc).__name__}:{exc}"
        )
        return 0
    if actual != expected:
        errors.append(f"default_shared_root:{actual!s}!={expected!s}")
        return 0
    return 1


def _check_transitional_seed_root(
    module: object, temp_root: Path, errors: list[str]
) -> int:
    ensure = getattr(module, "ensure_shared_seed", None)
    if not callable(ensure):
        errors.append("missing_callable:ensure_shared_seed")
        return 0
    target_root = (
        temp_root
        / "home"
        / ".agents"
        / "court-shiguan"
        / "court-capability-router"
    ).resolve()
    data_base = (temp_root / "localappdata").resolve()
    legacy_root = (
        data_base / "court-shiguan" / "court-capability-router"
    ).resolve()
    (legacy_root / "references").mkdir(parents=True)

    original_default = getattr(module, "default_shared_root")
    original_data_base = getattr(module, "user_data_base")
    keys = (
        "COURT_SHARED_SHIGUAN_ROOT",
        "SHIGUAN_SHARED_ROOT",
        "COURT_SHIGUAN_CUTOVER_RECEIPT",
    )
    saved = {key: os.environ.get(key) for key in keys}
    try:
        setattr(module, "default_shared_root", lambda home=None: target_root)
        setattr(module, "user_data_base", lambda: data_base)
        for key in keys:
            os.environ.pop(key, None)
        actual = ensure()
    except Exception as exc:
        errors.append(
            f"transitional_seed_root:execution_error:{type(exc).__name__}:{exc}"
        )
        return 0
    finally:
        setattr(module, "default_shared_root", original_default)
        setattr(module, "user_data_base", original_data_base)
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    expected = legacy_root / "references"
    if Path(actual).resolve() != expected.resolve():
        errors.append(f"transitional_seed_root:active_root:{actual!s}!={expected!s}")
    if target_root.exists():
        errors.append("transitional_seed_root:target_created_before_cutover")
    return 1 if Path(actual).resolve() == expected.resolve() and not target_root.exists() else 0


def _check_cutover_receipt_consumer(
    module: object, temp_root: Path, errors: list[str]
) -> int:
    validator = getattr(module, "_verified_cutover_receipt", None)
    if not callable(validator):
        errors.append("missing_callable:_verified_cutover_receipt")
        return 0
    legacy_root = (temp_root / "legacy" / "court-capability-router").resolve()
    target_root = (temp_root / "target" / "court-capability-router").resolve()
    receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    authorized_root = Path(str(receipt["protected_root"])).resolve(
        strict=False
    )
    live = _phase2_live_cutover_state(
        legacy_root=legacy_root, target_root=target_root
    )

    passed = 0
    try:
        valid = validator(
            receipt,
            legacy_root=legacy_root,
            target_root=target_root,
            live_state=live,
            authorized_protected_root=authorized_root,
        )
    except Exception as exc:
        errors.append(
            f"cutover_receipt_consumer_valid:execution_error:{type(exc).__name__}:{exc}"
        )
    else:
        if valid is True:
            passed += 1
        else:
            errors.append("cutover_receipt_consumer_valid:verified_receipt_rejected")

    without_schema = deepcopy(receipt)
    without_schema.pop("schema")
    try:
        accepted = validator(
            without_schema,
            legacy_root=legacy_root,
            target_root=target_root,
            live_state=live,
            authorized_protected_root=authorized_root,
        )
    except Exception as exc:
        errors.append(
            f"cutover_receipt_consumer_schema:execution_error:{type(exc).__name__}:{exc}"
        )
    else:
        if accepted is False:
            passed += 1
        else:
            errors.append("cutover_receipt_consumer_schema:missing_schema_accepted")

    strict_before = len(errors)
    mutations: list[tuple[str, dict[str, object]]] = []
    empty_protected = deepcopy(receipt)
    empty_protected["protected_files_before"] = {}
    empty_protected["protected_files_after"] = {}
    mutations.append(("empty_protected", empty_protected))
    missing_protected = deepcopy(receipt)
    missing_protected["protected_files_before"].pop(PROTECTED_PATHS[0])
    missing_protected["protected_files_after"].pop(PROTECTED_PATHS[0])
    mutations.append(("missing_protected", missing_protected))
    bad_directory_id = deepcopy(receipt)
    bad_directory_id["source_directory_id"] = ""
    mutations.append(("empty_directory_id", bad_directory_id))
    bad_inventory = deepcopy(receipt)
    bad_inventory["inventory_digest"] = "not-a-sha256"
    mutations.append(("bad_inventory_digest", bad_inventory))
    for name, candidate in mutations:
        try:
            accepted = validator(
                candidate,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=live,
                authorized_protected_root=authorized_root,
            )
        except Exception as exc:
            errors.append(
                f"cutover_receipt_consumer_strict:{name}:execution_error:{type(exc).__name__}:{exc}"
            )
            continue
        if accepted is not False:
            errors.append(f"cutover_receipt_consumer_strict:{name}:accepted")
    if len(errors) == strict_before:
        passed += 1
    return passed


def _phase2_cutover_receipt(
    *, legacy_root: Path, target_root: Path
) -> dict[str, object]:
    protected = _protected()
    control_root = legacy_root / "private-runtime" / "shiguan-migration"
    protected_root = (
        legacy_root.parent
        / "authorized-installed-skill"
        / "court-capability-router"
        / "references"
    )
    return {
        "schema": "court.shiguan_atomic_cutover.result.v1",
        "ok": True,
        "status": CUTOVER_VERIFIED,
        "reason_codes": ["atomic_cutover_verified"],
        "gate_status": READY,
        "pending_count": 0,
        "source_root": str(legacy_root / "references"),
        "target_root": str(target_root / "references"),
        "protected_root": str(protected_root),
        "source_volume_serial": 17,
        "source_directory_id": "directory-id-1",
        "file_count": 11,
        "total_bytes": 4096,
        "newest_mtime_utc": "2026-07-14T00:00:00+00:00",
        "inventory_digest": "a" * 64,
        "exclusion_policy_id": "court-shiguan-inventory-v1",
        "migration_id": "fixture-migration-1",
        "receipt_id": "fixture-cutover-receipt-1",
        "run_owner": "bingbu#0001:fixture-run",
        "run_marker_id": "fixture-marker-1",
        "control_root": str(control_root),
        "issued_at": _timestamp(32),
        "committed_at": _timestamp(70),
        "nonce": "fixture-nonce-1",
        "junction_verified": True,
        "protected_postcheck": "verified",
        "pending_snapshot": {"pending_count": 0},
        "binding_snapshot": {"bindings": []},
        "protected_files_before": deepcopy(protected),
        "protected_files_after": deepcopy(protected),
        "rollback": {
            "applied": False,
            "ok": True,
            "actions": [],
            "errors": [],
            "conservative_stopped": False,
        },
    }


def _phase2_live_cutover_state(
    *,
    legacy_root: Path,
    target_root: Path,
    receipt: dict[str, object] | None = None,
) -> dict[str, object]:
    bound_receipt = receipt or _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    return {
        "daemon_running": True,
        "physical_store_count": 1,
        "legacy_references_kind": "junction",
        "is_junction": True,
        "is_symlink": False,
        "is_reparse": True,
        "target_references_kind": "directory",
        "junction_target": str(target_root / "references"),
        "canonical_target": str(target_root / "references"),
        "target_volume_serial": 17,
        "target_directory_id": "directory-id-1",
        "identity_evidence": "windows_handle",
        "target_inventory": {
            "file_count": 11,
            "total_bytes": 4096,
            "newest_mtime_utc": "2026-07-14T00:00:00+00:00",
            "inventory_digest": "a" * 64,
            "exclusion_policy_id": "court-shiguan-inventory-v1",
        },
        "pending_count": 0,
        "binding_snapshot": {"bindings": []},
        "protected_files_after": deepcopy(_protected()),
        "protected_root": bound_receipt["protected_root"],
        "rollback": {
            "applied": False,
            "ok": True,
            "conservative_stopped": False,
        },
        "commit_marker": _commit_marker(bound_receipt),
    }


def _check_phase2_path_cases(
    module: object, temp_root: Path, errors: list[str]
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    validator = getattr(module, "_verified_cutover_receipt", None)
    active_root = getattr(module, "_active_shared_root", None)
    if not callable(validator) or not callable(active_root):
        if not callable(validator):
            errors.append("P2-CONSUMER-LIVE-009:missing_validator")
        if not callable(active_root):
            errors.append("P2-ROOT-REFERENCES-010:missing_active_root")
        return {
            "P2-CONSUMER-LIVE-009": False,
            "P2-ROOT-REFERENCES-010": False,
        }

    legacy_root = (temp_root / "legacy" / "court-capability-router").resolve()
    target_root = (temp_root / "target" / "court-capability-router").resolve()
    receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    authorized_root = Path(str(receipt["protected_root"])).resolve(
        strict=False
    )
    live = _phase2_live_cutover_state(
        legacy_root=legacy_root, target_root=target_root
    )

    case_id = "P2-CONSUMER-LIVE-009"
    before = len(errors)
    try:
        accepted = validator(
            receipt,
            legacy_root=legacy_root,
            target_root=target_root,
            live_state=live,
            authorized_protected_root=authorized_root,
        )
    except Exception as exc:
        errors.append(f"{case_id}:valid:execution_error:{type(exc).__name__}:{exc}")
    else:
        if accepted is not True:
            errors.append(f"{case_id}:valid_topology_rejected")

    mutations: list[
        tuple[str, dict[str, object], dict[str, object]]
    ] = []
    wrong_junction = deepcopy(live)
    wrong_junction["junction_target"] = str(temp_root / "wrong-target")
    mutations.append(("wrong_junction", deepcopy(receipt), wrong_junction))
    wrong_volume = deepcopy(live)
    wrong_volume["target_volume_serial"] = 99
    mutations.append(("wrong_volume", deepcopy(receipt), wrong_volume))
    wrong_directory = deepcopy(live)
    wrong_directory["target_directory_id"] = "other-directory"
    mutations.append(("wrong_directory_id", deepcopy(receipt), wrong_directory))
    for field, value in (
        ("file_count", 12),
        ("total_bytes", 8192),
        ("newest_mtime_utc", "2026-07-14T00:00:01+00:00"),
        ("inventory_digest", "b" * 64),
        ("exclusion_policy_id", "other-policy"),
    ):
        changed_live = deepcopy(live)
        changed_live["target_inventory"][field] = value
        mutations.append(
            (f"live_inventory_{field}", deepcopy(receipt), changed_live)
        )
    nonempty_bindings = deepcopy(receipt)
    nonempty_bindings["binding_snapshot"] = {
        "bindings": [{"state": "inactive", "record": "r1"}]
    }
    mutations.append(("nonempty_bindings", nonempty_bindings, deepcopy(live)))
    rollback_applied = deepcopy(receipt)
    rollback_applied["rollback"]["applied"] = True
    mutations.append(("rollback_applied", rollback_applied, deepcopy(live)))
    rollback_failed = deepcopy(receipt)
    rollback_failed["rollback"]["ok"] = False
    mutations.append(("rollback_failed", rollback_failed, deepcopy(live)))
    blank_owner = deepcopy(receipt)
    blank_owner["run_owner"] = " "
    mutations.append(("blank_run_owner", blank_owner, deepcopy(live)))
    missing_schema = deepcopy(receipt)
    missing_schema.pop("schema")
    mutations.append(("missing_schema", missing_schema, deepcopy(live)))

    for label, candidate, candidate_live in mutations:
        try:
            accepted = validator(
                candidate,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=candidate_live,
                authorized_protected_root=authorized_root,
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:{label}:execution_error:{type(exc).__name__}:{exc}"
            )
            continue
        if accepted is not False:
            errors.append(f"{case_id}:{label}:accepted")
    results[case_id] = len(errors) == before

    case_id = "P2-ROOT-REFERENCES-010"
    before = len(errors)
    original_path_kind = getattr(module, "_path_kind")
    original_loader = getattr(module, "_load_cutover_receipt")
    original_probe = getattr(module, "_probe_live_cutover_state", None)
    had_probe = hasattr(module, "_probe_live_cutover_state")
    probed_paths: list[Path] = []
    legacy_references = legacy_root / "references"
    target_references = target_root / "references"

    def fixture_path_kind(path: Path) -> str:
        candidate = Path(path)
        probed_paths.append(candidate)
        if candidate == legacy_references:
            return "junction"
        if candidate == target_references:
            return "directory"
        return "directory"

    setattr(module, "_path_kind", fixture_path_kind)
    setattr(module, "_load_cutover_receipt", lambda target, legacy: deepcopy(receipt))
    setattr(
        module,
        "_probe_live_cutover_state",
        lambda legacy, target, receipt=None, **kwargs: deepcopy(live),
    )
    try:
        selected = active_root(
            target_root,
            legacy_root,
            authorized_protected_root=authorized_root,
        )
    except Exception as exc:
        errors.append(f"{case_id}:execution_error:{type(exc).__name__}:{exc}")
        selected = None
    finally:
        setattr(module, "_path_kind", original_path_kind)
        setattr(module, "_load_cutover_receipt", original_loader)
        if had_probe:
            setattr(module, "_probe_live_cutover_state", original_probe)
        else:
            delattr(module, "_probe_live_cutover_state")
    if selected != target_root:
        errors.append(f"{case_id}:selected:{selected!r}!={target_root!r}")
    if set(probed_paths) != {legacy_references, target_references}:
        errors.append(f"{case_id}:not_references_root_judgment:{probed_paths!r}")
    results[case_id] = len(errors) == before
    return results


def _check_phase3_repair_cases(
    evaluate: Callable[..., object],
    execute: Callable[..., object],
    cutover_module: object,
    paths_module: object,
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    results: dict[str, bool] = {}

    case_id = "P3-TARGET-ONLY-011"
    before = len(errors)
    active_root = getattr(paths_module, "_active_shared_root", None)
    original_path_kind = getattr(paths_module, "_path_kind", None)
    if not callable(active_root) or not callable(original_path_kind):
        errors.append(f"{case_id}:missing_active_root_contract")
    else:
        legacy_root = (temp_root / case_id.lower() / "legacy").resolve()
        target_root = (temp_root / case_id.lower() / "target").resolve()
        legacy_references = legacy_root / "references"
        target_references = target_root / "references"

        def incomplete_kind(path: Path) -> str:
            candidate = Path(path)
            if candidate == legacy_references:
                return "absent"
            if candidate == target_references:
                return "directory"
            return "unknown"

        setattr(paths_module, "_path_kind", incomplete_kind)
        try:
            selected = active_root(target_root, legacy_root)
        except Exception as exc:
            errors.append(
                f"{case_id}:execution_error:{type(exc).__name__}:{exc}"
            )
        else:
            if selected != target_root:
                errors.append(f"{case_id}:target_not_selected:{selected}")
        finally:
            setattr(paths_module, "_path_kind", original_path_kind)
    results[case_id] = len(errors) == before

    case_id = "P3-COMMIT-MARKER-012"
    before = len(errors)
    persist_receipt = getattr(cutover_module, "_persist_cutover_receipt", None)
    reread_receipt = getattr(cutover_module, "_reread_cutover_receipt", None)
    persist_marker = getattr(
        cutover_module, "_persist_cutover_commit_marker", None
    )
    reread_marker = getattr(
        cutover_module, "_reread_cutover_commit_marker", None
    )
    validator = getattr(paths_module, "_verified_cutover_receipt", None)
    marker_contract = all(
        callable(item)
        for item in (
            persist_receipt,
            reread_receipt,
            persist_marker,
            reread_marker,
            validator,
        )
    )
    if not marker_contract:
        errors.append(f"{case_id}:missing_two_phase_commit_marker_contract")
    else:
        success = CutoverFixtureOperations(temp_root / case_id.lower() / "success")

        def tracked_persist_receipt(
            path: Path, receipt: dict[str, object]
        ) -> None:
            success.events.append(f"persist_receipt:{receipt.get('status')}")
            persist_receipt(path, receipt)

        def tracked_reread_receipt(
            path: Path, expected: dict[str, object]
        ) -> dict[str, object]:
            success.events.append(f"reread_receipt:{expected.get('status')}")
            return reread_receipt(path, expected)

        def tracked_persist_marker(
            path: Path, marker: dict[str, object]
        ) -> None:
            success.events.append(f"persist_marker:{marker.get('state')}")
            persist_marker(path, marker)

        def tracked_reread_marker(
            path: Path, expected: dict[str, object]
        ) -> dict[str, object]:
            success.events.append(f"reread_marker:{expected.get('state')}")
            return reread_marker(path, expected)

        setattr(cutover_module, "_persist_cutover_receipt", tracked_persist_receipt)
        setattr(cutover_module, "_reread_cutover_receipt", tracked_reread_receipt)
        setattr(
            cutover_module, "_persist_cutover_commit_marker", tracked_persist_marker
        )
        setattr(
            cutover_module, "_reread_cutover_commit_marker", tracked_reread_marker
        )
        try:
            success_result = execute(
                gate_receipt=_ready_receipt(success), operations=success
            )
        except Exception as exc:
            errors.append(f"{case_id}:success_error:{type(exc).__name__}:{exc}")
            success_result = None
        finally:
            setattr(cutover_module, "_persist_cutover_receipt", persist_receipt)
            setattr(cutover_module, "_reread_cutover_receipt", reread_receipt)
            setattr(
                cutover_module, "_persist_cutover_commit_marker", persist_marker
            )
            setattr(
                cutover_module, "_reread_cutover_commit_marker", reread_marker
            )
        if (
            not isinstance(success_result, dict)
            or success_result.get("status") != CUTOVER_VERIFIED
        ):
            errors.append(f"{case_id}:success_not_verified:{success_result!r}")
        required_order = (
            "acquire_migration_run",
            "inspect_cutover_context",
            "persist_marker:PREPARED",
            "reread_marker:PREPARED",
            "stop_daemon",
            "start_daemon",
            "inspect_final_cutover_state",
            f"persist_receipt:{CUTOVER_VERIFIED}",
            f"reread_receipt:{CUTOVER_VERIFIED}",
            "persist_marker:COMMITTED",
            "reread_marker:COMMITTED",
            "release_migration_run",
        )
        try:
            positions = [success.events.index(event) for event in required_order]
        except ValueError:
            errors.append(f"{case_id}:commit_order_missing:{success.events!r}")
        else:
            if positions != sorted(positions):
                errors.append(f"{case_id}:commit_order_invalid:{success.events!r}")

        stale = CutoverFixtureOperations(
            temp_root / case_id.lower() / "stale-success",
            owner_drift_on_rollback=True,
        )

        def stale_persist(path: Path, receipt: dict[str, object]) -> None:
            if receipt.get("status") == CUTOVER_VERIFIED:
                persist_receipt(path, receipt)
                return
            raise PermissionError("terminal receipt rewrite blocked")

        def stale_reread(
            path: Path, expected: dict[str, object]
        ) -> dict[str, object]:
            if expected.get("status") == CUTOVER_VERIFIED:
                raise RuntimeError("injected success receipt readback failure")
            return reread_receipt(path, expected)

        setattr(cutover_module, "_persist_cutover_receipt", stale_persist)
        setattr(cutover_module, "_reread_cutover_receipt", stale_reread)
        try:
            stale_result = execute(
                gate_receipt=_ready_receipt(stale), operations=stale
            )
        except Exception as exc:
            errors.append(f"{case_id}:stale_error:{type(exc).__name__}:{exc}")
            stale_result = None
        finally:
            setattr(cutover_module, "_persist_cutover_receipt", persist_receipt)
            setattr(cutover_module, "_reread_cutover_receipt", reread_receipt)
        if (
            not isinstance(stale_result, dict)
            or stale_result.get("status") != CUTOVER_ROLLBACK_FAILED
        ):
            errors.append(f"{case_id}:stale_terminal_status:{stale_result!r}")
        receipt_path = stale.control_root / "shiguan-cutover-receipt.json"
        marker_path = stale.control_root / "shiguan-cutover-commit.json"
        try:
            disk_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            disk_marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{case_id}:stale_disk_missing:{type(exc).__name__}:{exc}")
        else:
            if disk_receipt.get("status") != CUTOVER_VERIFIED:
                errors.append(f"{case_id}:stale_success_not_preserved_for_probe")
            live = _phase2_live_cutover_state(
                legacy_root=stale.source_root.parent,
                target_root=stale.target_root.parent,
                receipt=disk_receipt,
            )
            live["commit_marker"] = disk_marker
            try:
                accepted = validator(
                    disk_receipt,
                    legacy_root=stale.source_root.parent,
                    target_root=stale.target_root.parent,
                    live_state=live,
                    authorized_protected_root=stale.protected_root,
                )
            except Exception as exc:
                errors.append(
                    f"{case_id}:consumer_error:{type(exc).__name__}:{exc}"
                )
            else:
                if accepted is not False:
                    errors.append(f"{case_id}:stale_success_consumable")
    results[case_id] = len(errors) == before

    case_id = "P3-PROTECTED-ROOT-013"
    before = len(errors)
    gate_ops = _fixture(temp_root / case_id.lower() / "gate")
    try:
        gate_result = evaluate(phase="preflight", operations=gate_ops)
    except Exception as exc:
        errors.append(f"{case_id}:gate_error:{type(exc).__name__}:{exc}")
        gate_result = None
    expected_protected = gate_ops.protected_root.resolve(strict=False)
    if (
        not isinstance(gate_result, dict)
        or gate_result.get("status") != READY
        or not _same_fixture_path(
            gate_result.get("protected_root"), expected_protected
        )
    ):
        errors.append(f"{case_id}:gate_not_bound_to_protected_root:{gate_result!r}")
    if gate_ops.protected_snapshot_roots != [expected_protected]:
        errors.append(
            f"{case_id}:gate_protected_probe_roots:"
            f"{gate_ops.protected_snapshot_roots!r}"
        )

    cutover_ops = CutoverFixtureOperations(
        temp_root / case_id.lower() / "cutover"
    )
    try:
        cutover_result = execute(
            gate_receipt=_ready_receipt(cutover_ops), operations=cutover_ops
        )
    except Exception as exc:
        errors.append(f"{case_id}:cutover_error:{type(exc).__name__}:{exc}")
        cutover_result = None
    expected_cutover_protected = cutover_ops.protected_root.resolve(strict=False)
    if (
        not isinstance(cutover_result, dict)
        or cutover_result.get("status") != CUTOVER_VERIFIED
    ):
        errors.append(f"{case_id}:cutover_not_verified:{cutover_result!r}")
    if (
        not cutover_ops.protected_snapshot_roots
        or any(
            root != expected_cutover_protected
            for root in cutover_ops.protected_snapshot_roots
        )
        or cutover_ops.target_root.resolve(strict=False)
        in cutover_ops.protected_snapshot_roots
    ):
        errors.append(
            f"{case_id}:cutover_protected_probe_roots:"
            f"{cutover_ops.protected_snapshot_roots!r}"
        )

    legacy_root = (temp_root / case_id.lower() / "paths-legacy").resolve()
    target_root = (temp_root / case_id.lower() / "paths-target").resolve()
    receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    invalid = deepcopy(receipt)
    invalid["protected_root"] = invalid["target_root"]
    invalid_live = _phase2_live_cutover_state(
        legacy_root=legacy_root, target_root=target_root, receipt=invalid
    )
    invalid_live["protected_root"] = invalid["protected_root"]
    invalid_live["commit_marker"] = _commit_marker(invalid)
    paths_validator = getattr(paths_module, "_verified_cutover_receipt", None)
    if not callable(paths_validator):
        errors.append(f"{case_id}:missing_consumer_validator")
    else:
        try:
            accepted = paths_validator(
                invalid,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=invalid_live,
                authorized_protected_root=Path(
                    str(receipt["protected_root"])
                ).resolve(strict=False),
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:consumer_error:{type(exc).__name__}:{exc}"
            )
        else:
            if accepted is not False:
                errors.append(f"{case_id}:shared_target_accepted_as_protected_root")

    probe = getattr(paths_module, "_probe_live_cutover_state", None)
    original_kind = getattr(paths_module, "_path_kind", None)
    original_inventory = getattr(paths_module, "_metadata_inventory_snapshot", None)
    original_pending = getattr(paths_module, "_metadata_only_pending_count", None)
    original_binding = getattr(paths_module, "_metadata_only_binding_snapshot", None)
    original_identity = getattr(paths_module, "_windows_directory_identity", None)
    original_junction_target = getattr(paths_module, "_resolved_junction_target", None)
    original_protected = getattr(paths_module, "_live_protected_snapshot", None)
    if not all(
        callable(item)
        for item in (
            probe,
            original_kind,
            original_inventory,
            original_pending,
            original_binding,
            original_identity,
            original_junction_target,
            original_protected,
        )
    ):
        errors.append(f"{case_id}:missing_live_probe_contract")
    else:
        (legacy_root / "references").mkdir(parents=True, exist_ok=True)
        (target_root / "references").mkdir(parents=True, exist_ok=True)
        probed_roots: list[Path] = []

        def probe_kind(path: Path) -> str:
            return "junction" if Path(path) == legacy_root / "references" else "directory"

        def probe_protected(root: Path) -> dict[str, dict[str, object]]:
            probed_roots.append(Path(root).resolve(strict=False))
            return deepcopy(_protected())

        setattr(paths_module, "_path_kind", probe_kind)
        setattr(
            paths_module,
            "_metadata_inventory_snapshot",
            lambda root, exclusion_policy_id: {
                "file_count": 11,
                "total_bytes": 4096,
                "newest_mtime_utc": "2026-07-14T00:00:00+00:00",
                "inventory_digest": "a" * 64,
                "exclusion_policy_id": exclusion_policy_id,
            },
        )
        setattr(paths_module, "_metadata_only_pending_count", lambda root: 0)
        setattr(
            paths_module,
            "_metadata_only_binding_snapshot",
            lambda root: {"bindings": []},
        )
        setattr(
            paths_module,
            "_windows_directory_identity",
            lambda root: {
                "target_volume_serial": 17,
                "target_directory_id": "directory-id-1",
                "identity_evidence": "windows_handle",
            },
        )
        setattr(
            paths_module,
            "_resolved_junction_target",
            lambda root: target_root / "references",
        )
        setattr(paths_module, "_live_protected_snapshot", probe_protected)
        try:
            probe(
                legacy_root,
                target_root,
                receipt=receipt,
                authorized_protected_root=Path(
                    str(receipt["protected_root"])
                ).resolve(strict=False),
            )
        except Exception as exc:
            errors.append(f"{case_id}:live_probe_error:{type(exc).__name__}:{exc}")
        finally:
            setattr(paths_module, "_path_kind", original_kind)
            setattr(paths_module, "_metadata_inventory_snapshot", original_inventory)
            setattr(paths_module, "_metadata_only_pending_count", original_pending)
            setattr(paths_module, "_metadata_only_binding_snapshot", original_binding)
            setattr(paths_module, "_windows_directory_identity", original_identity)
            setattr(paths_module, "_resolved_junction_target", original_junction_target)
            setattr(paths_module, "_live_protected_snapshot", original_protected)
        expected_probe_root = Path(str(receipt["protected_root"])).resolve(
            strict=False
        )
        if probed_roots != [expected_probe_root]:
            errors.append(f"{case_id}:consumer_protected_probe_roots:{probed_roots!r}")
    results[case_id] = len(errors) == before

    case_id = "P3-SOURCE-PENDING-LEXICAL-014"
    before = len(errors)
    validate_context = getattr(cutover_module, "_validate_cutover_context", None)
    if not callable(validate_context):
        errors.append(f"{case_id}:missing_cutover_context_validator")
    else:
        for label, leaf in (
            ("device", "CON"),
            ("trailing_dot", "bad."),
            ("trailing_space", "bad "),
            ("ads", "bad:ads"),
        ):
            gate_case = _fixture(temp_root / case_id.lower() / f"gate-{label}")
            bad_source = (
                str(temp_root / case_id.lower() / f"raw-{label}")
                + os.sep
                + leaf
                + os.sep
                + "references"
            )
            gate_case.target_context["source_root"] = bad_source
            gate_case.target_context["pending_root"] = str(
                Path(bad_source) / "shiguan-imports" / "pending"
            )
            try:
                gate_value = evaluate(phase="preflight", operations=gate_case)
            except Exception as exc:
                errors.append(
                    f"{case_id}:gate_{label}:execution_error:"
                    f"{type(exc).__name__}:{exc}"
                )
            else:
                if "unsafe_source_path" not in gate_value.get("reason_codes", []):
                    errors.append(
                        f"{case_id}:gate_{label}:not_unsafe_source:{gate_value!r}"
                    )

            cutover_case = CutoverFixtureOperations(
                temp_root / case_id.lower() / f"cutover-{label}"
            )
            cutover_context = cutover_case.inspect_cutover_context()
            cutover_context["source_root"] = bad_source
            cutover_context["pending_root"] = str(
                Path(bad_source) / "shiguan-imports" / "pending"
            )
            _, context_error = validate_context(cutover_context)
            if context_error != "unsafe_source_path":
                errors.append(
                    f"{case_id}:cutover_{label}:{context_error!r}"
                )

        for label, leaf in (
            ("pending_device", "CON"),
            ("pending_trailing_dot", "bad."),
            ("pending_trailing_space", "bad "),
            ("pending_ads", "bad:ads"),
            ("pending_not_derived", "elsewhere"),
        ):
            gate_case = _fixture(temp_root / case_id.lower() / f"gate-{label}")
            gate_case.target_context["pending_root"] = (
                str(temp_root / case_id.lower() / f"raw-{label}")
                + os.sep
                + leaf
            )
            try:
                gate_value = evaluate(phase="preflight", operations=gate_case)
            except Exception as exc:
                errors.append(
                    f"{case_id}:gate_{label}:execution_error:"
                    f"{type(exc).__name__}:{exc}"
                )
            else:
                if "unsafe_pending_path" not in gate_value.get("reason_codes", []):
                    errors.append(
                        f"{case_id}:gate_{label}:not_unsafe_pending:{gate_value!r}"
                    )

            cutover_case = CutoverFixtureOperations(
                temp_root / case_id.lower() / f"cutover-{label}"
            )
            cutover_context = cutover_case.inspect_cutover_context()
            cutover_context["pending_root"] = gate_case.target_context[
                "pending_root"
            ]
            _, context_error = validate_context(cutover_context)
            if context_error != "unsafe_pending_path":
                errors.append(
                    f"{case_id}:cutover_{label}:{context_error!r}"
                )
    results[case_id] = len(errors) == before

    case_id = "P3-ROLLBACK-TERMINAL-015"
    before = len(errors)
    legacy_root = (temp_root / case_id.lower() / "legacy").resolve()
    target_root = (temp_root / case_id.lower() / "target").resolve()
    receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    receipt["rollback"]["conservative_stopped"] = True
    live = _phase2_live_cutover_state(
        legacy_root=legacy_root, target_root=target_root, receipt=receipt
    )
    live["rollback"] = deepcopy(receipt["rollback"])
    live["commit_marker"] = _commit_marker(receipt)
    cutover_validator = getattr(cutover_module, "_valid_cutover_receipt", None)
    consumer_validator = getattr(paths_module, "_verified_cutover_receipt", None)
    producer_rule = getattr(
        cutover_module, "_success_rollback_is_consumable", None
    )
    consumer_rule = getattr(
        paths_module, "_success_rollback_is_consumable", None
    )
    if not all(
        callable(item)
        for item in (
            cutover_validator,
            consumer_validator,
            producer_rule,
            consumer_rule,
        )
    ):
        errors.append(f"{case_id}:missing_shared_rollback_terminal_rule")
    else:
        if cutover_validator(receipt) is not False:
            errors.append(f"{case_id}:producer_accepted_conservative_success")
        try:
            accepted = consumer_validator(
                receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=live,
                authorized_protected_root=Path(
                    str(receipt["protected_root"])
                ).resolve(strict=False),
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:consumer_error:{type(exc).__name__}:{exc}"
            )
        else:
            if accepted is not False:
                errors.append(f"{case_id}:consumer_accepted_conservative_success")
        if (
            producer_rule(receipt["rollback"]) is not False
            or consumer_rule(receipt["rollback"]) is not False
        ):
            errors.append(f"{case_id}:rollback_rule_not_fail_closed")
        clean = deepcopy(receipt["rollback"])
        clean["conservative_stopped"] = False
        if (
            producer_rule(clean) is not True
            or consumer_rule(clean) is not True
        ):
            errors.append(f"{case_id}:rollback_rule_rejects_clean_terminal")
    results[case_id] = len(errors) == before
    return results


def _check_phase4_repair_cases(
    evaluate: Callable[..., object],
    gate_module: object,
    execute: Callable[..., object],
    cutover_module: object,
    paths_module: object,
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    results: dict[str, bool] = {}

    case_id = "P4-BINDING-SNAPSHOT-STRICT-016"
    before = len(errors)
    validators = {
        "gate": getattr(gate_module, "_valid_empty_binding_snapshot", None),
        "producer": getattr(
            cutover_module, "_valid_empty_binding_snapshot", None
        ),
        "consumer": getattr(
            paths_module, "_valid_empty_binding_snapshot", None
        ),
    }
    candidates = (
        ({"bindings": []}, True, "exact_empty"),
        ({"bindings": [], "shadow": []}, False, "extra_key"),
        ({"bindings": ()}, False, "tuple_type"),
        ({"bindings": [{"state": "shadow"}]}, False, "shadow_binding"),
    )
    for surface, validator in validators.items():
        if not callable(validator):
            errors.append(f"{case_id}:{surface}:missing_shared_validator")
            continue
        for candidate, expected, label in candidates:
            try:
                actual = validator(deepcopy(candidate))
            except Exception as exc:
                errors.append(
                    f"{case_id}:{surface}:{label}:execution_error:"
                    f"{type(exc).__name__}:{exc}"
                )
                continue
            if actual is not expected:
                errors.append(
                    f"{case_id}:{surface}:{label}:{actual!r}!={expected!r}"
                )

    shadow_gate = _fixture(
        temp_root / case_id.lower() / "gate-shadow",
        bindings=[{"state": "shadow", "record": "fixture"}],
    )
    try:
        shadow_gate_result = evaluate(
            phase="preflight", operations=shadow_gate
        )
    except Exception as exc:
        errors.append(f"{case_id}:gate_shadow_error:{type(exc).__name__}:{exc}")
    else:
        if (
            not isinstance(shadow_gate_result, dict)
            or shadow_gate_result.get("allowed") is not False
            or shadow_gate_result.get("status") == READY
        ):
            errors.append(
                f"{case_id}:gate_shadow_accepted:{shadow_gate_result!r}"
            )

    shadow_cutover = CutoverFixtureOperations(
        temp_root / case_id.lower() / "producer-shadow"
    )
    shadow_receipt = _ready_receipt(shadow_cutover)
    shadow_receipt["binding_snapshot"] = {
        "bindings": [],
        "shadow": [{"state": "unknown"}],
    }
    try:
        shadow_cutover_result = execute(
            gate_receipt=shadow_receipt, operations=shadow_cutover
        )
    except Exception as exc:
        errors.append(
            f"{case_id}:producer_shadow_error:{type(exc).__name__}:{exc}"
        )
    else:
        if (
            not isinstance(shadow_cutover_result, dict)
            or shadow_cutover_result.get("status") != "CUTOVER_BLOCKED"
            or shadow_cutover.events
        ):
            errors.append(
                f"{case_id}:producer_shadow_not_prelock_blocked:"
                f"result={shadow_cutover_result!r}:events={shadow_cutover.events!r}"
            )

    legacy_root = (temp_root / case_id.lower() / "legacy").resolve()
    target_root = (temp_root / case_id.lower() / "target").resolve()
    consumer_receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    authorized_root = Path(str(consumer_receipt["protected_root"])).resolve(
        strict=False
    )
    consumer_receipt["binding_snapshot"] = {
        "bindings": [],
        "shadow": [{"state": "active"}],
    }
    consumer_live = _phase2_live_cutover_state(
        legacy_root=legacy_root,
        target_root=target_root,
        receipt=consumer_receipt,
    )
    consumer_live["commit_marker"] = _commit_marker(consumer_receipt)
    consumer_validator = getattr(
        paths_module, "_verified_cutover_receipt", None
    )
    if not callable(consumer_validator):
        errors.append(f"{case_id}:consumer:missing_receipt_validator")
    else:
        try:
            accepted = consumer_validator(
                consumer_receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=consumer_live,
                authorized_protected_root=authorized_root,
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:consumer_shadow_error:{type(exc).__name__}:{exc}"
            )
        else:
            if accepted is not False:
                errors.append(f"{case_id}:consumer_shadow_accepted")

    live_probe = getattr(paths_module, "_probe_live_cutover_state", None)
    original_kind = getattr(paths_module, "_path_kind", None)
    original_junction_target = getattr(
        paths_module, "_resolved_junction_target", None
    )
    original_inventory = getattr(
        paths_module, "_metadata_inventory_snapshot", None
    )
    original_pending = getattr(
        paths_module, "_metadata_only_pending_count", None
    )
    original_protected = getattr(
        paths_module, "_live_protected_snapshot", None
    )
    if not all(
        callable(item)
        for item in (
            live_probe,
            original_kind,
            original_junction_target,
            original_inventory,
            original_pending,
            original_protected,
        )
    ):
        errors.append(f"{case_id}:missing_live_binding_probe_contract")
    else:
        exact_receipt = _phase2_cutover_receipt(
            legacy_root=legacy_root, target_root=target_root
        )
        exact_authorized_root = Path(
            str(exact_receipt["protected_root"])
        ).resolve(strict=False)
        legacy_references = legacy_root / "references"
        target_references = target_root / "references"
        binding_probe_roots: list[Path] = []

        def binding_kind(path: Path) -> str:
            return (
                "junction"
                if Path(path) == legacy_references
                else "directory"
            )

        def exact_binding_probe(root: Path) -> dict[str, object]:
            binding_probe_roots.append(Path(root))
            return {"bindings": []}

        setattr(paths_module, "_path_kind", binding_kind)
        setattr(
            paths_module,
            "_resolved_junction_target",
            lambda root: target_references,
        )
        setattr(
            paths_module,
            "_metadata_inventory_snapshot",
            lambda root, exclusion_policy_id: {
                "file_count": 11,
                "total_bytes": 4096,
                "newest_mtime_utc": "2026-07-14T00:00:00+00:00",
                "inventory_digest": "a" * 64,
                "exclusion_policy_id": exclusion_policy_id,
            },
        )
        setattr(paths_module, "_metadata_only_pending_count", lambda root: 0)
        setattr(
            paths_module,
            "_live_protected_snapshot",
            lambda root: deepcopy(_protected()),
        )
        identity_probe = lambda root: {
            "target_volume_serial": 17,
            "target_directory_id": "directory-id-1",
            "identity_evidence": "windows_handle",
        }
        try:
            exact_live = live_probe(
                legacy_root,
                target_root,
                receipt=exact_receipt,
                authorized_protected_root=exact_authorized_root,
                identity_probe=identity_probe,
                binding_probe=exact_binding_probe,
            )
            shadow_live = live_probe(
                legacy_root,
                target_root,
                receipt=exact_receipt,
                authorized_protected_root=exact_authorized_root,
                identity_probe=identity_probe,
                binding_probe=lambda root: {
                    "bindings": [],
                    "shadow": [{"state": "unknown"}],
                },
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:live_binding_probe_error:"
                f"{type(exc).__name__}:{exc}"
            )
            exact_live = None
            shadow_live = None
        finally:
            setattr(paths_module, "_path_kind", original_kind)
            setattr(
                paths_module,
                "_resolved_junction_target",
                original_junction_target,
            )
            setattr(
                paths_module,
                "_metadata_inventory_snapshot",
                original_inventory,
            )
            setattr(
                paths_module,
                "_metadata_only_pending_count",
                original_pending,
            )
            setattr(
                paths_module,
                "_live_protected_snapshot",
                original_protected,
            )
        if (
            not isinstance(exact_live, dict)
            or exact_live.get("binding_snapshot") != {"bindings": []}
            or binding_probe_roots != [target_references]
        ):
            errors.append(
                f"{case_id}:live_binding_evidence_not_used:"
                f"state={exact_live!r}:roots={binding_probe_roots!r}"
            )
        if shadow_live is not None:
            errors.append(f"{case_id}:live_shadow_binding_accepted")
    results[case_id] = len(errors) == before

    case_id = "P4-PROTECTED-ROOT-AUTHORITY-017"
    before = len(errors)
    gate_ops = _fixture(temp_root / case_id.lower() / "gate")
    authorized_gate_root = gate_ops.protected_root.resolve(strict=False)
    wrong_gate_root = (
        temp_root / case_id.lower() / "untrusted-installed-skill" / "references"
    ).resolve(strict=False)
    gate_ops.target_context["protected_root"] = str(wrong_gate_root)
    try:
        gate_result = evaluate(phase="preflight", operations=gate_ops)
    except Exception as exc:
        errors.append(f"{case_id}:gate_error:{type(exc).__name__}:{exc}")
        gate_result = None
    if (
        not isinstance(gate_result, dict)
        or gate_result.get("allowed") is not False
        or gate_result.get("status") == READY
        or gate_ops.authorized_protected_root_reads < 1
        or "get_protected_file_snapshot" in gate_ops.calls
    ):
        errors.append(
            f"{case_id}:gate_wrong_root_not_blocked:result={gate_result!r}:"
            f"authorized={authorized_gate_root}:reads="
            f"{gate_ops.authorized_protected_root_reads}:calls={gate_ops.calls!r}"
        )

    cutover_ops = CutoverFixtureOperations(
        temp_root / case_id.lower() / "producer"
    )
    cutover_receipt = _ready_receipt(cutover_ops)
    cutover_receipt["protected_root"] = str(
        (temp_root / case_id.lower() / "other-protected" / "references").resolve(
            strict=False
        )
    )
    try:
        cutover_result = execute(
            gate_receipt=cutover_receipt, operations=cutover_ops
        )
    except Exception as exc:
        errors.append(f"{case_id}:producer_error:{type(exc).__name__}:{exc}")
        cutover_result = None
    if (
        not isinstance(cutover_result, dict)
        or cutover_result.get("status") != "CUTOVER_BLOCKED"
        or cutover_ops.authorized_protected_root_reads < 1
        or cutover_ops.events
    ):
        errors.append(
            f"{case_id}:producer_wrong_root_not_prelock_blocked:"
            f"result={cutover_result!r}:reads="
            f"{cutover_ops.authorized_protected_root_reads}:"
            f"events={cutover_ops.events!r}"
        )

    legacy_root = (temp_root / case_id.lower() / "legacy").resolve()
    target_root = (temp_root / case_id.lower() / "target").resolve()
    valid_receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    authorized_consumer_root = Path(
        str(valid_receipt["protected_root"])
    ).resolve(strict=False)
    valid_live = _phase2_live_cutover_state(
        legacy_root=legacy_root,
        target_root=target_root,
        receipt=valid_receipt,
    )
    validator = getattr(paths_module, "_verified_cutover_receipt", None)
    if not callable(validator):
        errors.append(f"{case_id}:consumer:missing_receipt_validator")
    else:
        try:
            valid_accepted = validator(
                valid_receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=valid_live,
                authorized_protected_root=authorized_consumer_root,
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:consumer_valid_error:{type(exc).__name__}:{exc}"
            )
            valid_accepted = None
        if valid_accepted is not True:
            errors.append(f"{case_id}:authorized_fixture_rejected")

        wrong_receipt = deepcopy(valid_receipt)
        wrong_receipt["protected_root"] = str(
            (temp_root / case_id.lower() / "self-authorized" / "references").resolve(
                strict=False
            )
        )
        wrong_live = _phase2_live_cutover_state(
            legacy_root=legacy_root,
            target_root=target_root,
            receipt=wrong_receipt,
        )
        wrong_live["protected_root"] = wrong_receipt["protected_root"]
        wrong_live["commit_marker"] = _commit_marker(wrong_receipt)
        try:
            wrong_accepted = validator(
                wrong_receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=wrong_live,
                authorized_protected_root=authorized_consumer_root,
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:consumer_wrong_error:{type(exc).__name__}:{exc}"
            )
        else:
            if wrong_accepted is not False:
                errors.append(f"{case_id}:receipt_self_authorized_wrong_root")
    results[case_id] = len(errors) == before

    case_id = "P4-JUNCTION-EXACT-018"
    before = len(errors)
    legacy_root = (temp_root / case_id.lower() / "legacy").resolve()
    target_root = (temp_root / case_id.lower() / "target").resolve()
    receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    authorized_root = Path(str(receipt["protected_root"])).resolve(
        strict=False
    )
    exact_live = _phase2_live_cutover_state(
        legacy_root=legacy_root, target_root=target_root, receipt=receipt
    )
    exact_live.update(
        {
            "legacy_references_kind": "junction",
            "is_junction": True,
            "is_symlink": False,
            "is_reparse": True,
        }
    )
    validator = getattr(paths_module, "_verified_cutover_receipt", None)
    if not callable(validator):
        errors.append(f"{case_id}:missing_receipt_validator")
    else:
        for label, live_state, expected in (
            ("exact_junction", deepcopy(exact_live), True),
            (
                "generic_reparse",
                {
                    **deepcopy(exact_live),
                    "legacy_references_kind": "reparse",
                    "is_junction": False,
                },
                False,
            ),
            (
                "symlink",
                {
                    **deepcopy(exact_live),
                    "legacy_references_kind": "symlink",
                    "is_junction": False,
                    "is_symlink": True,
                },
                False,
            ),
        ):
            try:
                accepted = validator(
                    receipt,
                    legacy_root=legacy_root,
                    target_root=target_root,
                    live_state=live_state,
                    authorized_protected_root=authorized_root,
                )
            except Exception as exc:
                errors.append(
                    f"{case_id}:{label}:execution_error:"
                    f"{type(exc).__name__}:{exc}"
                )
                continue
            if accepted is not expected:
                errors.append(
                    f"{case_id}:{label}:{accepted!r}!={expected!r}"
                )

    active_root = getattr(paths_module, "_active_shared_root", None)
    original_kind = getattr(paths_module, "_path_kind", None)
    original_loader = getattr(paths_module, "_load_cutover_receipt", None)
    original_probe = getattr(paths_module, "_probe_live_cutover_state", None)
    if not all(
        callable(item)
        for item in (active_root, original_kind, original_loader, original_probe)
    ):
        errors.append(f"{case_id}:missing_active_root_contract")
    else:
        legacy_references = legacy_root / "references"
        target_references = target_root / "references"

        def exact_kind(path: Path) -> str:
            candidate = Path(path)
            if candidate == legacy_references:
                return "junction"
            if candidate == target_references:
                return "directory"
            return "unknown"

        setattr(paths_module, "_path_kind", exact_kind)
        setattr(
            paths_module,
            "_load_cutover_receipt",
            lambda target, legacy: deepcopy(receipt),
        )
        setattr(
            paths_module,
            "_probe_live_cutover_state",
            lambda legacy, target, receipt=None, **kwargs: deepcopy(exact_live),
        )
        try:
            selected = active_root(
                target_root,
                legacy_root,
                authorized_protected_root=authorized_root,
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:active_root_error:{type(exc).__name__}:{exc}"
            )
        else:
            if selected != target_root:
                errors.append(f"{case_id}:active_root_not_target:{selected!r}")
        finally:
            setattr(paths_module, "_path_kind", original_kind)
            setattr(paths_module, "_load_cutover_receipt", original_loader)
            setattr(paths_module, "_probe_live_cutover_state", original_probe)
    results[case_id] = len(errors) == before

    case_id = "P4-PENDING-MISSING-UNKNOWN-019"
    before = len(errors)
    gate_pending_probe = getattr(
        gate_module, "_metadata_only_pending_count", None
    )
    consumer_pending_probe = getattr(
        paths_module, "_metadata_only_pending_count", None
    )
    missing_pending = temp_root / case_id.lower() / "missing-pending"
    empty_pending = temp_root / case_id.lower() / "empty-pending"
    empty_pending.mkdir(parents=True, exist_ok=True)
    if not callable(gate_pending_probe) or not callable(consumer_pending_probe):
        errors.append(f"{case_id}:missing_pending_probe_contract")
    else:
        try:
            missing_gate_count, missing_gate_error = gate_pending_probe(
                missing_pending
            )
            empty_gate_count, empty_gate_error = gate_pending_probe(empty_pending)
            missing_consumer_count = consumer_pending_probe(missing_pending)
            empty_consumer_count = consumer_pending_probe(empty_pending)
        except Exception as exc:
            errors.append(f"{case_id}:probe_error:{type(exc).__name__}:{exc}")
        else:
            if missing_gate_count is not None or not missing_gate_error:
                errors.append(
                    f"{case_id}:gate_missing_not_unknown:"
                    f"{missing_gate_count!r}:{missing_gate_error!r}"
                )
            if empty_gate_count != 0 or empty_gate_error is not None:
                errors.append(
                    f"{case_id}:gate_empty_plain_not_zero:"
                    f"{empty_gate_count!r}:{empty_gate_error!r}"
                )
            if missing_consumer_count is not None:
                errors.append(
                    f"{case_id}:consumer_missing_treated_as_zero:"
                    f"{missing_consumer_count!r}"
                )
            if empty_consumer_count != 0:
                errors.append(
                    f"{case_id}:consumer_empty_plain_not_zero:"
                    f"{empty_consumer_count!r}"
                )

    gate_ops = _fixture(
        temp_root / case_id.lower() / "gate-unknown", pending_count=None
    )
    try:
        gate_result = evaluate(phase="preflight", operations=gate_ops)
    except Exception as exc:
        errors.append(f"{case_id}:gate_error:{type(exc).__name__}:{exc}")
    else:
        if (
            not isinstance(gate_result, dict)
            or gate_result.get("status") != PENDING_BLOCK
            or gate_ops.calls != ["get_pending_body_count"]
        ):
            errors.append(
                f"{case_id}:gate_unknown_not_short_circuited:"
                f"result={gate_result!r}:calls={gate_ops.calls!r}"
            )

    cutover_ops = CutoverFixtureOperations(
        temp_root / case_id.lower() / "producer-unknown"
    )
    pending_unknown_receipt = _ready_receipt(cutover_ops)
    pending_unknown_receipt["pending_count"] = None
    pending_unknown_receipt["pending_snapshot"] = {"pending_count": None}
    try:
        pending_unknown_result = execute(
            gate_receipt=pending_unknown_receipt, operations=cutover_ops
        )
    except Exception as exc:
        errors.append(f"{case_id}:producer_error:{type(exc).__name__}:{exc}")
    else:
        if (
            not isinstance(pending_unknown_result, dict)
            or pending_unknown_result.get("status") != "CUTOVER_BLOCKED"
            or cutover_ops.events
        ):
            errors.append(
                f"{case_id}:producer_unknown_not_prelock_blocked:"
                f"result={pending_unknown_result!r}:events={cutover_ops.events!r}"
            )

    legacy_root = (temp_root / case_id.lower() / "legacy").resolve()
    target_root = (temp_root / case_id.lower() / "target").resolve()
    receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    live = _phase2_live_cutover_state(
        legacy_root=legacy_root, target_root=target_root, receipt=receipt
    )
    live["pending_count"] = None
    validator = getattr(paths_module, "_verified_cutover_receipt", None)
    if callable(validator):
        try:
            accepted = validator(
                receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=live,
                authorized_protected_root=Path(
                    str(receipt["protected_root"])
                ).resolve(strict=False),
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:consumer_error:{type(exc).__name__}:{exc}"
            )
        else:
            if accepted is not False:
                errors.append(f"{case_id}:consumer_unknown_pending_accepted")
    else:
        errors.append(f"{case_id}:missing_consumer_validator")
    results[case_id] = len(errors) == before

    case_id = "P4-WINDOWS-LIVE-IDENTITY-020"
    before = len(errors)
    identity_probe = getattr(
        paths_module, "_windows_directory_identity", None
    )
    if not callable(identity_probe):
        errors.append(f"{case_id}:missing_handle_identity_probe")
    else:
        windows_module = identity_probe.__globals__.get(
            "court_safe_fs_windows"
        )
        if windows_module is None:
            errors.append(f"{case_id}:missing_windows_primitive_module")
        else:
            original_open = getattr(
                windows_module, "_open_verified_path_handle", None
            )
            original_confirm = getattr(
                windows_module, "_confirm_path_still_names_handle", None
            )
            original_close = getattr(windows_module, "_close_file_handle", None)
            if not all(
                callable(item)
                for item in (original_open, original_confirm, original_close)
            ):
                errors.append(f"{case_id}:missing_windows_handle_primitives")
            else:
                identity_events: list[str] = []
                info = SimpleNamespace(
                    volume_serial_number=17,
                    file_id=123456,
                    final_path=str(temp_root / case_id.lower() / "target"),
                )

                def fake_open(path: Path, relative: Path) -> tuple[int, object]:
                    identity_events.append("open_verified_handle")
                    return 101, info

                def fake_confirm(
                    path: Path, relative: Path, observed: object
                ) -> None:
                    identity_events.append("confirm_path_still_names_handle")
                    if observed is not info:
                        raise AssertionError("identity object changed")

                def fake_close(handle: int) -> None:
                    identity_events.append("close_handle")
                    if handle != 101:
                        raise AssertionError("unexpected handle")

                setattr(windows_module, "_open_verified_path_handle", fake_open)
                setattr(
                    windows_module,
                    "_confirm_path_still_names_handle",
                    fake_confirm,
                )
                setattr(windows_module, "_close_file_handle", fake_close)
                try:
                    identity = identity_probe(
                        temp_root / case_id.lower() / "target"
                    )
                except Exception as exc:
                    errors.append(
                        f"{case_id}:identity_error:{type(exc).__name__}:{exc}"
                    )
                    identity = None
                finally:
                    setattr(
                        windows_module,
                        "_open_verified_path_handle",
                        original_open,
                    )
                    setattr(
                        windows_module,
                        "_confirm_path_still_names_handle",
                        original_confirm,
                    )
                    setattr(windows_module, "_close_file_handle", original_close)
                if identity != {
                    "target_volume_serial": 17,
                    "target_directory_id": "123456",
                    "identity_evidence": "windows_handle",
                }:
                    errors.append(f"{case_id}:identity_result:{identity!r}")
                if identity_events != [
                    "open_verified_handle",
                    "confirm_path_still_names_handle",
                    "close_handle",
                ]:
                    errors.append(
                        f"{case_id}:identity_events:{identity_events!r}"
                    )

                zero_info = SimpleNamespace(
                    volume_serial_number=17,
                    file_id=0,
                    final_path=str(temp_root / case_id.lower() / "target-zero"),
                )
                setattr(
                    windows_module,
                    "_open_verified_path_handle",
                    lambda path, relative: (102, zero_info),
                )
                setattr(
                    windows_module,
                    "_confirm_path_still_names_handle",
                    lambda path, relative, observed: None,
                )
                setattr(windows_module, "_close_file_handle", lambda handle: None)
                try:
                    zero_identity = identity_probe(
                        temp_root / case_id.lower() / "target-zero"
                    )
                except Exception as exc:
                    errors.append(
                        f"{case_id}:zero_error:{type(exc).__name__}:{exc}"
                    )
                    zero_identity = None
                finally:
                    setattr(
                        windows_module,
                        "_open_verified_path_handle",
                        original_open,
                    )
                    setattr(
                        windows_module,
                        "_confirm_path_still_names_handle",
                        original_confirm,
                    )
                    setattr(windows_module, "_close_file_handle", original_close)
                if zero_identity is not None:
                    errors.append(f"{case_id}:zero_file_id_accepted")

                zero_volume_info = SimpleNamespace(
                    volume_serial_number=0,
                    file_id=123456,
                    final_path=str(
                        temp_root / case_id.lower() / "target-zero-volume"
                    ),
                )
                setattr(
                    windows_module,
                    "_open_verified_path_handle",
                    lambda path, relative: (103, zero_volume_info),
                )
                setattr(
                    windows_module,
                    "_confirm_path_still_names_handle",
                    lambda path, relative, observed: None,
                )
                setattr(windows_module, "_close_file_handle", lambda handle: None)
                try:
                    zero_volume_identity = identity_probe(
                        temp_root / case_id.lower() / "target-zero-volume"
                    )
                except Exception as exc:
                    errors.append(
                        f"{case_id}:zero_volume_error:"
                        f"{type(exc).__name__}:{exc}"
                    )
                    zero_volume_identity = None
                finally:
                    setattr(
                        windows_module,
                        "_open_verified_path_handle",
                        original_open,
                    )
                    setattr(
                        windows_module,
                        "_confirm_path_still_names_handle",
                        original_confirm,
                    )
                    setattr(windows_module, "_close_file_handle", original_close)
                if zero_volume_identity is not None:
                    errors.append(f"{case_id}:zero_volume_accepted")

                setattr(
                    windows_module,
                    "_open_verified_path_handle",
                    lambda path, relative: (_ for _ in ()).throw(
                        RuntimeError("native identity unavailable")
                    ),
                )
                try:
                    missing_identity = identity_probe(
                        temp_root / case_id.lower() / "target-missing-native"
                    )
                except Exception as exc:
                    errors.append(
                        f"{case_id}:missing_native_error:"
                        f"{type(exc).__name__}:{exc}"
                    )
                    missing_identity = None
                finally:
                    setattr(
                        windows_module,
                        "_open_verified_path_handle",
                        original_open,
                    )
                if missing_identity is not None:
                    errors.append(f"{case_id}:missing_native_identity_accepted")

                setattr(windows_module, "_open_verified_path_handle", fake_open)
                setattr(
                    windows_module,
                    "_confirm_path_still_names_handle",
                    lambda path, relative, observed: (_ for _ in ()).throw(
                        RuntimeError("identity swap")
                    ),
                )
                setattr(windows_module, "_close_file_handle", fake_close)
                try:
                    swapped_identity = identity_probe(
                        temp_root / case_id.lower() / "target-swapped"
                    )
                except Exception as exc:
                    errors.append(
                        f"{case_id}:swap_error:{type(exc).__name__}:{exc}"
                    )
                    swapped_identity = None
                finally:
                    setattr(
                        windows_module,
                        "_open_verified_path_handle",
                        original_open,
                    )
                    setattr(
                        windows_module,
                        "_confirm_path_still_names_handle",
                        original_confirm,
                    )
                    setattr(windows_module, "_close_file_handle", original_close)
                if swapped_identity is not None:
                    errors.append(f"{case_id}:identity_swap_accepted")

    legacy_root = (temp_root / case_id.lower() / "legacy").resolve()
    target_root = (temp_root / case_id.lower() / "target-root").resolve()
    receipt = _phase2_cutover_receipt(
        legacy_root=legacy_root, target_root=target_root
    )
    live = _phase2_live_cutover_state(
        legacy_root=legacy_root, target_root=target_root, receipt=receipt
    )
    live.update(
        {
            "legacy_references_kind": "junction",
            "is_junction": True,
            "is_symlink": False,
            "is_reparse": True,
            "identity_evidence": "stat",
        }
    )
    validator = getattr(paths_module, "_verified_cutover_receipt", None)
    if callable(validator):
        try:
            stat_accepted = validator(
                receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=live,
                authorized_protected_root=Path(
                    str(receipt["protected_root"])
                ).resolve(strict=False),
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:consumer_error:{type(exc).__name__}:{exc}"
            )
        else:
            if stat_accepted is not False:
                errors.append(f"{case_id}:stat_identity_accepted")
    else:
        errors.append(f"{case_id}:missing_consumer_validator")
    results[case_id] = len(errors) == before

    case_id = "P4-ATOMIC-HELPER-EVENTS-021"
    before = len(errors)
    persist_receipt = getattr(cutover_module, "_persist_cutover_receipt", None)
    reread_receipt = getattr(cutover_module, "_reread_cutover_receipt", None)
    persist_marker = getattr(
        cutover_module, "_persist_cutover_commit_marker", None
    )
    reread_marker = getattr(
        cutover_module, "_reread_cutover_commit_marker", None
    )
    atomic_helper = getattr(cutover_module, "atomic_write_text", None)
    if not all(
        callable(item)
        for item in (
            persist_receipt,
            reread_receipt,
            persist_marker,
            reread_marker,
            atomic_helper,
        )
    ):
        errors.append(f"{case_id}:missing_atomic_persistence_contract")
    else:
        helper_globals = getattr(atomic_helper, "__globals__", {})
        helper_tempfile = helper_globals.get("tempfile")
        helper_os = helper_globals.get("os")
        parent_fsync = helper_globals.get("fsync_parent_directory")
        if (
            helper_tempfile is None
            or helper_os is None
            or not callable(parent_fsync)
        ):
            errors.append(f"{case_id}:not_real_court_atomic_helper")
        else:
            atomic_root = temp_root / case_id.lower() / "atomic"
            receipt_path = atomic_root / "shiguan-cutover-receipt.json"
            marker_path = atomic_root / "shiguan-cutover-commit.json"
            receipt = _phase2_cutover_receipt(
                legacy_root=(atomic_root / "legacy").resolve(),
                target_root=(atomic_root / "target").resolve(),
            )
            marker = _commit_marker(receipt)
            events: list[str] = []
            temp_fds: set[int] = set()
            temp_paths: list[Path] = []
            original_mkstemp = helper_tempfile.mkstemp
            original_fsync = helper_os.fsync
            original_replace = helper_os.replace
            original_parent_fsync = parent_fsync

            def tracked_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
                fd, raw_path = original_mkstemp(*args, **kwargs)
                events.append("mkstemp")
                temp_fds.add(fd)
                temp_paths.append(Path(raw_path))
                return fd, raw_path

            def tracked_fsync(descriptor: int) -> None:
                if descriptor in temp_fds:
                    events.append("file_fsync")
                original_fsync(descriptor)

            def tracked_replace(source: object, target: object) -> None:
                source_path = Path(source)
                target_path = Path(target)
                events.append("replace")
                if (
                    source_path.parent != target_path.parent
                    or not source_path.name.startswith(f".{target_path.name}.")
                    or source_path.suffix != ".tmp"
                ):
                    raise AssertionError("atomic temp is not a sibling")
                original_replace(source, target)

            def tracked_parent_fsync(path: Path) -> bool:
                events.append("parent_fsync")
                return bool(original_parent_fsync(path))

            helper_tempfile.mkstemp = tracked_mkstemp
            helper_os.fsync = tracked_fsync
            helper_os.replace = tracked_replace
            helper_globals["fsync_parent_directory"] = tracked_parent_fsync
            try:
                persist_receipt(receipt_path, receipt)
                reread_receipt(receipt_path, receipt)
                events.append("receipt_readback")
                persist_marker(marker_path, marker)
                reread_marker(marker_path, marker)
                events.append("marker_readback")
            except Exception as exc:
                errors.append(
                    f"{case_id}:atomic_success_error:{type(exc).__name__}:{exc}"
                )
            finally:
                helper_tempfile.mkstemp = original_mkstemp
                helper_os.fsync = original_fsync
                helper_os.replace = original_replace
                helper_globals["fsync_parent_directory"] = original_parent_fsync
            expected_events = [
                "mkstemp",
                "file_fsync",
                "replace",
                "parent_fsync",
                "receipt_readback",
                "mkstemp",
                "file_fsync",
                "replace",
                "parent_fsync",
                "marker_readback",
            ]
            if events != expected_events:
                errors.append(f"{case_id}:atomic_event_order:{events!r}")
            if len(temp_paths) != 2 or any(
                path.parent != atomic_root for path in temp_paths
            ):
                errors.append(f"{case_id}:atomic_temp_paths:{temp_paths!r}")

            failure_path = atomic_root / "sharing-failure.json"
            helper_time = helper_globals.get("time")
            if helper_time is None:
                errors.append(f"{case_id}:missing_atomic_retry_clock")
            else:
                original_monotonic = helper_time.monotonic
                original_sleep = helper_time.sleep
                ticks = iter((0.0, 3.0, 3.0))

                def fail_replace(source: object, target: object) -> None:
                    raise PermissionError("injected sharing violation")

                helper_os.replace = fail_replace
                helper_time.monotonic = lambda: next(ticks, 3.0)
                helper_time.sleep = lambda seconds: None
                try:
                    persist_receipt(failure_path, receipt)
                except PermissionError:
                    pass
                except Exception as exc:
                    errors.append(
                        f"{case_id}:sharing_failure_type:"
                        f"{type(exc).__name__}:{exc}"
                    )
                else:
                    errors.append(f"{case_id}:sharing_failure_not_raised")
                finally:
                    helper_os.replace = original_replace
                    helper_time.monotonic = original_monotonic
                    helper_time.sleep = original_sleep
                leftovers = list(
                    atomic_root.glob(f".{failure_path.name}.*.tmp")
                )
                if failure_path.exists() or leftovers:
                    errors.append(
                        f"{case_id}:sharing_failure_left_success_surface:"
                        f"target={failure_path.exists()}:tmp={leftovers!r}"
                    )
    results[case_id] = len(errors) == before
    return results


def _check_phase5_terminal_marker_case(
    execute: Callable[..., object],
    cutover_module: object,
    paths_module: object,
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    case_id = "P5-COMMITTED-MARKER-READBACK-022"
    before = len(errors)
    persist_receipt = getattr(cutover_module, "_persist_cutover_receipt", None)
    reread_marker = getattr(
        cutover_module, "_reread_cutover_commit_marker", None
    )
    validator = getattr(paths_module, "_verified_cutover_receipt", None)
    if not all(callable(item) for item in (persist_receipt, reread_marker, validator)):
        errors.append(f"{case_id}:missing_terminal_commit_contract")
        return {case_id: False}

    operations = CutoverFixtureOperations(
        temp_root / case_id.lower(),
        owner_drift_on_rollback=True,
    )
    committed_probe: dict[str, dict[str, object]] = {}

    def success_only_receipt_persist(
        path: Path, receipt: dict[str, object]
    ) -> None:
        if receipt.get("status") == CUTOVER_VERIFIED:
            persist_receipt(path, receipt)
            return
        raise PermissionError("terminal receipt rewrite blocked")

    def fail_after_committed_marker_readback(
        path: Path, expected: dict[str, object]
    ) -> dict[str, object]:
        value = reread_marker(path, expected)
        if expected.get("state") == "COMMITTED":
            receipt_path = path.parent / "shiguan-cutover-receipt.json"
            committed_probe["receipt"] = json.loads(
                receipt_path.read_text(encoding="utf-8")
            )
            committed_probe["marker"] = deepcopy(value)
            raise RuntimeError("injected committed marker readback failure")
        return value

    setattr(
        cutover_module,
        "_persist_cutover_receipt",
        success_only_receipt_persist,
    )
    setattr(
        cutover_module,
        "_reread_cutover_commit_marker",
        fail_after_committed_marker_readback,
    )
    try:
        result = execute(
            gate_receipt=_ready_receipt(operations), operations=operations
        )
    except Exception as exc:
        errors.append(f"{case_id}:execution_error:{type(exc).__name__}:{exc}")
        result = None
    finally:
        setattr(cutover_module, "_persist_cutover_receipt", persist_receipt)
        setattr(
            cutover_module,
            "_reread_cutover_commit_marker",
            reread_marker,
        )

    if (
        not isinstance(result, dict)
        or result.get("status") != CUTOVER_ROLLBACK_FAILED
    ):
        errors.append(f"{case_id}:terminal_status:{result!r}")

    receipt_path = operations.control_root / "shiguan-cutover-receipt.json"
    marker_path = operations.control_root / "shiguan-cutover-commit.json"
    try:
        disk_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        disk_marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"{case_id}:disk_state_error:{type(exc).__name__}:{exc}")
    else:
        if disk_receipt.get("status") != CUTOVER_VERIFIED:
            errors.append(f"{case_id}:success_receipt_not_preserved_for_probe")
        committed_receipt = committed_probe.get("receipt")
        committed_marker = committed_probe.get("marker")
        if not isinstance(committed_receipt, dict):
            errors.append(f"{case_id}:committed_receipt_probe_missing")
            committed_receipt = {}
        if not isinstance(committed_marker, dict):
            errors.append(f"{case_id}:committed_marker_probe_missing")
            committed_marker = {}
        if committed_receipt.get("status") != CUTOVER_VERIFIED:
            errors.append(f"{case_id}:committed_receipt_probe_not_verified")
        if committed_marker.get("state") != "COMMITTED":
            errors.append(f"{case_id}:committed_marker_probe_not_committed")
        expected_receipt_hash = _receipt_sha256(committed_receipt)
        if committed_marker.get("receipt_sha256") != expected_receipt_hash:
            errors.append(f"{case_id}:committed_marker_receipt_hash_unbound")
        for field in (
            "source_root",
            "target_root",
            "control_root",
            "migration_id",
            "receipt_id",
            "run_owner",
            "run_marker_id",
            "nonce",
        ):
            if committed_marker.get(field) != committed_receipt.get(field):
                errors.append(f"{case_id}:committed_marker_{field}_unbound")
        legacy_root = Path(str(disk_receipt.get("source_root", ""))).parent
        target_root = Path(str(disk_receipt.get("target_root", ""))).parent
        live = _phase2_live_cutover_state(
            legacy_root=legacy_root,
            target_root=target_root,
            receipt=disk_receipt,
        )
        live["commit_marker"] = committed_marker
        try:
            positive_control = validator(
                disk_receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=live,
                authorized_protected_root=operations.protected_root,
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:positive_control_error:{type(exc).__name__}:{exc}"
            )
        else:
            if positive_control is not True:
                errors.append(f"{case_id}:positive_control_not_consumable")
        live["commit_marker"] = disk_marker
        try:
            accepted = validator(
                disk_receipt,
                legacy_root=legacy_root,
                target_root=target_root,
                live_state=live,
                authorized_protected_root=operations.protected_root,
            )
        except Exception as exc:
            errors.append(
                f"{case_id}:consumer_error:{type(exc).__name__}:{exc}"
            )
        else:
            if accepted is not False:
                errors.append(f"{case_id}:disk_success_still_consumable")
    return {case_id: len(errors) == before}


def _check_rc6_authority_mismatch_case(
    gate_module: object,
    errors: list[str],
) -> dict[str, bool]:
    case_id = "RC6-AUTHORITY-MISMATCH-023"
    before = len(errors)
    target = getattr(gate_module, "evaluate_authority_realm_admission", None)
    if not callable(target):
        errors.append(f"{case_id}:missing_callable:evaluate_authority_realm_admission")
        return {case_id: False}

    expected = {
        "schema": "court.shiguan.local_authority_realm.v1",
        "status": "AUTHORITY_REALM_READY",
        "allowed": True,
        "authority_realm_id": "local-authority-realm-a",
        "root_fingerprint": "a" * 64,
        "transport": "local_filesystem",
        "local_filesystem_verified": True,
    }
    presented = deepcopy(expected)
    presented.update(
        {
            "authority_realm_id": "local-authority-realm-b",
            "root_fingerprint": "b" * 64,
        }
    )
    side_effects: list[str] = []
    try:
        result = target(
            task_id="task-rc6",
            operation_id="00000000-0000-4000-8000-000000000006",
            expected_receipt=expected,
            presented_receipt=presented,
        )
    except Exception as exc:
        errors.append(f"{case_id}:unexpected_error:{type(exc).__name__}:{exc}")
        return {case_id: False}

    if isinstance(result, dict) and result.get("allowed") is True:
        side_effects.extend(("allocate_sequence", "write_archive"))
    if not isinstance(result, dict):
        errors.append(f"{case_id}:result_not_dict")
    else:
        if result.get("allowed") is not False:
            errors.append(f"{case_id}:mismatch_not_blocked")
        if result.get("status") != "AUTHORITY_REALM_MISMATCH":
            errors.append(f"{case_id}:wrong_status:{result.get('status')}")
        reasons = result.get("reason_codes")
        if reasons != [
            "authority_realm_id_mismatch",
            "root_fingerprint_mismatch",
        ]:
            errors.append(f"{case_id}:wrong_reason_codes:{reasons}")
    if side_effects:
        errors.append(f"{case_id}:side_effects_before_admission:{side_effects}")
    return {case_id: len(errors) == before}


def _check_rc6_admission_fail_closed_case(
    gate_module: object,
    errors: list[str],
) -> dict[str, bool]:
    case_id = "RC6-ADMISSION-FAIL-CLOSED-027"
    before = len(errors)
    target = getattr(gate_module, "evaluate_authority_realm_admission", None)
    if not callable(target):
        errors.append(f"{case_id}:missing_callable:evaluate_authority_realm_admission")
        return {case_id: False}

    task_id = "task-rc6"
    operation_id = "00000000-0000-4000-8000-000000000027"
    ready: dict[str, object] = {
        "schema": "court.shiguan.local_authority_realm.v1",
        "status": "AUTHORITY_REALM_READY",
        "allowed": True,
        "authority_realm_id": "lar-fixture-ready",
        "root_fingerprint": "c" * 64,
        "transport": "local_filesystem",
        "local_filesystem_verified": True,
    }
    try:
        positive = target(
            task_id=task_id,
            operation_id=operation_id,
            expected_receipt=deepcopy(ready),
            presented_receipt=deepcopy(ready),
        )
    except Exception as exc:
        errors.append(f"{case_id}:positive_error:{type(exc).__name__}:{exc}")
        return {case_id: False}
    if not isinstance(positive, dict) or positive.get("allowed") is not True:
        errors.append(f"{case_id}:positive_control_blocked")
    elif (
        positive.get("admission_stage") != "BEFORE_SEQUENCE_AND_WRITES"
        or positive.get("side_effects_authorized") is not True
    ):
        errors.append(f"{case_id}:positive_control_missing_stage_contract")

    unsupported = deepcopy(ready)
    unsupported.update(
        {
            "status": "AUTHORITY_TRANSPORT_UNSUPPORTED",
            "allowed": False,
            "authority_realm_id": None,
            "root_fingerprint": None,
        }
    )
    untrusted = deepcopy(unsupported)
    untrusted["status"] = "AUTHORITY_ROOT_UNTRUSTED"
    schema_mismatch = deepcopy(ready)
    schema_mismatch["schema"] = "court.shiguan.local_authority_realm.v0"
    local_unproven = deepcopy(ready)
    local_unproven["local_filesystem_verified"] = False
    variants = (
        (
            "transport_unsupported",
            task_id,
            operation_id,
            ready,
            unsupported,
            "AUTHORITY_TRANSPORT_UNSUPPORTED",
        ),
        (
            "root_untrusted",
            task_id,
            operation_id,
            ready,
            untrusted,
            "AUTHORITY_ROOT_UNTRUSTED",
        ),
        (
            "malformed",
            task_id,
            operation_id,
            ready,
            {},
            "AUTHORITY_RECEIPT_INVALID",
        ),
        (
            "schema_mismatch",
            task_id,
            operation_id,
            ready,
            schema_mismatch,
            "AUTHORITY_RECEIPT_INVALID",
        ),
        (
            "task_missing",
            "",
            operation_id,
            ready,
            ready,
            "AUTHORITY_RECEIPT_INVALID",
        ),
        (
            "operation_not_uuid",
            task_id,
            "operation-27",
            ready,
            ready,
            "AUTHORITY_RECEIPT_INVALID",
        ),
        (
            "local_unproven",
            task_id,
            operation_id,
            ready,
            local_unproven,
            "AUTHORITY_TRANSPORT_UNSUPPORTED",
        ),
    )
    side_effects: list[str] = []
    for name, candidate_task, candidate_operation, expected, presented, status in variants:
        try:
            result = target(
                task_id=candidate_task,
                operation_id=candidate_operation,
                expected_receipt=deepcopy(expected),
                presented_receipt=deepcopy(presented),
            )
        except Exception as exc:
            errors.append(f"{case_id}:{name}:unexpected_error:{type(exc).__name__}:{exc}")
            continue
        if isinstance(result, dict) and result.get("allowed") is True:
            side_effects.extend((f"{name}:allocate_sequence", f"{name}:write"))
        if not isinstance(result, dict):
            errors.append(f"{case_id}:{name}:result_not_dict")
            continue
        if result.get("status") != status:
            errors.append(f"{case_id}:{name}:wrong_status:{result.get('status')}")
        if result.get("admission_stage") != "BEFORE_SEQUENCE_AND_WRITES":
            errors.append(f"{case_id}:{name}:wrong_admission_stage")
        if result.get("side_effects_authorized") is not False:
            errors.append(f"{case_id}:{name}:side_effects_authorized")
    if side_effects:
        errors.append(f"{case_id}:effects_before_admission:{side_effects}")
    return {case_id: len(errors) == before}


def _check_rc6_pure_root_fingerprint_case(
    paths_module: object,
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    case_id = "RC6-PURE-ROOT-FINGERPRINT-024"
    before = len(errors)
    target = getattr(paths_module, "build_local_authority_realm_receipt", None)
    if not callable(target):
        errors.append(f"{case_id}:missing_callable:build_local_authority_realm_receipt")
        return {case_id: False}

    first = temp_root / "AuthorityRootA"
    second = temp_root / "AuthorityRootB"
    first.mkdir(parents=True)
    second.mkdir()

    def evidence(path: Path, canonical_root: str) -> dict[str, object]:
        metadata = path.stat()
        return {
            "authority_realm_seed": "rc6-fixture-host",
            "canonical_root": canonical_root,
            "filesystem_id": str(metadata.st_dev),
            "directory_id": str(metadata.st_ino),
            "identity_evidence": "temporary_directory_stat",
            "transport": "local_filesystem",
            "local_filesystem_verified": True,
            "alias_target_verified": True,
            "containment_verified": True,
        }

    canonical = str(first.resolve(strict=True))
    alternate_case = canonical.swapcase() if os.name == "nt" else canonical
    lexical_alias = str(first / "." / "child" / "..")
    receipts = []
    for candidate in (canonical, alternate_case, lexical_alias):
        source = evidence(first, candidate)
        frozen = deepcopy(source)
        try:
            receipt = target(source)
        except Exception as exc:
            errors.append(f"{case_id}:unexpected_error:{type(exc).__name__}:{exc}")
            return {case_id: False}
        if source != frozen:
            errors.append(f"{case_id}:input_mutated")
        receipts.append(receipt)
    try:
        distinct = target(evidence(second, str(second.resolve(strict=True))))
    except Exception as exc:
        errors.append(f"{case_id}:distinct_error:{type(exc).__name__}:{exc}")
        return {case_id: False}

    if not all(isinstance(item, dict) for item in [*receipts, distinct]):
        errors.append(f"{case_id}:receipt_not_dict")
        return {case_id: False}
    realm_ids = {item.get("authority_realm_id") for item in receipts}
    fingerprints = {item.get("root_fingerprint") for item in receipts}
    if len(realm_ids) != 1 or None in realm_ids:
        errors.append(f"{case_id}:alias_realm_ids_differ:{sorted(map(str, realm_ids))}")
    if len(fingerprints) != 1 or None in fingerprints:
        errors.append(
            f"{case_id}:alias_root_fingerprints_differ:{sorted(map(str, fingerprints))}"
        )
    if distinct.get("authority_realm_id") not in realm_ids:
        errors.append(f"{case_id}:same_host_realm_changed")
    if distinct.get("root_fingerprint") in fingerprints:
        errors.append(f"{case_id}:distinct_directory_fingerprint_collision")
    if any(first.iterdir()) or any(second.iterdir()):
        errors.append(f"{case_id}:directory_body_created_or_read_contract_broken")
    return {case_id: len(errors) == before}


def _check_rc6_transport_unsupported_case(
    paths_module: object,
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    case_id = "RC6-TRANSPORT-UNSUPPORTED-025"
    before = len(errors)
    target = getattr(paths_module, "build_local_authority_realm_receipt", None)
    if not callable(target):
        errors.append(f"{case_id}:missing_callable:build_local_authority_realm_receipt")
        return {case_id: False}

    local_root = temp_root / "local-root"
    local_root.mkdir(parents=True)
    metadata = local_root.stat()
    baseline: dict[str, object] = {
        "authority_realm_seed": "rc6-fixture-host",
        "canonical_root": str(local_root.resolve(strict=True)),
        "filesystem_id": str(metadata.st_dev),
        "directory_id": str(metadata.st_ino),
        "identity_evidence": "temporary_directory_stat",
        "transport": "local_filesystem",
        "local_filesystem_verified": True,
        "alias_target_verified": True,
        "containment_verified": True,
    }
    mutations = (
        ("unc_path", {"canonical_root": r"\\fixture-server\shiguan"}),
        ("smb", {"transport": "smb"}),
        ("nfs", {"transport": "nfs"}),
        ("cross_host", {"transport": "cross_host"}),
        ("unknown", {"transport": "unknown"}),
        ("unproven_false", {"local_filesystem_verified": False}),
        ("unproven_none", {"local_filesystem_verified": None}),
    )
    for name, updates in mutations:
        evidence = deepcopy(baseline)
        evidence.update(updates)
        try:
            receipt = target(evidence)
        except Exception as exc:
            errors.append(f"{case_id}:{name}:unexpected_error:{type(exc).__name__}:{exc}")
            continue
        if not isinstance(receipt, dict):
            errors.append(f"{case_id}:{name}:receipt_not_dict")
            continue
        if receipt.get("status") != "AUTHORITY_TRANSPORT_UNSUPPORTED":
            errors.append(f"{case_id}:{name}:wrong_status:{receipt.get('status')}")
        if receipt.get("authority_realm_id") is not None:
            errors.append(f"{case_id}:{name}:realm_id_issued")
        if receipt.get("root_fingerprint") is not None:
            errors.append(f"{case_id}:{name}:root_fingerprint_issued")
        if receipt.get("distributed_lock") != "NOT_USED":
            errors.append(f"{case_id}:{name}:distributed_lock_fallback")
    minimal_variants = (
        (
            "minimal_unc",
            {
                "canonical_root": r"\\fixture-server\shiguan",
                "transport": "smb",
                "local_filesystem_verified": False,
            },
        ),
        (
            "minimal_unproven",
            {
                "canonical_root": str(local_root),
                "transport": "local_filesystem",
                "local_filesystem_verified": False,
            },
        ),
    )
    for name, evidence in minimal_variants:
        try:
            receipt = target(evidence)
        except Exception as exc:
            errors.append(f"{case_id}:{name}:unexpected_error:{type(exc).__name__}:{exc}")
            continue
        if (
            not isinstance(receipt, dict)
            or receipt.get("status") != "AUTHORITY_TRANSPORT_UNSUPPORTED"
            or receipt.get("authority_realm_id") is not None
            or receipt.get("root_fingerprint") is not None
        ):
            errors.append(f"{case_id}:{name}:not_structured_unsupported:{receipt}")
    return {case_id: len(errors) == before}


def _check_rc6_alias_escape_safety_case(
    paths_module: object,
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    case_id = "RC6-ALIAS-ESCAPE-SAFETY-026"
    before = len(errors)
    target = getattr(paths_module, "build_local_authority_realm_receipt", None)
    if not callable(target):
        errors.append(f"{case_id}:missing_callable:build_local_authority_realm_receipt")
        return {case_id: False}

    physical_root = temp_root / "physical-root"
    physical_root.mkdir(parents=True)
    metadata = physical_root.stat()
    baseline: dict[str, object] = {
        "authority_realm_seed": "rc6-fixture-host",
        "canonical_root": str(physical_root.resolve(strict=True)),
        "filesystem_id": str(metadata.st_dev),
        "directory_id": str(metadata.st_ino),
        "identity_evidence": "temporary_directory_stat",
        "transport": "local_filesystem",
        "local_filesystem_verified": True,
        "alias_kind": "direct",
        "alias_target_verified": True,
        "containment_verified": True,
    }
    try:
        direct = target(deepcopy(baseline))
        exact_junction_evidence = deepcopy(baseline)
        exact_junction_evidence.update(
            {
                "alias_kind": "junction",
                "alias_proof": "verified_exact_junction",
            }
        )
        exact_junction = target(exact_junction_evidence)
    except Exception as exc:
        errors.append(f"{case_id}:positive_control_error:{type(exc).__name__}:{exc}")
        return {case_id: False}
    if (
        not isinstance(direct, dict)
        or not isinstance(exact_junction, dict)
        or exact_junction.get("status") != "AUTHORITY_REALM_READY"
        or exact_junction.get("root_fingerprint") != direct.get("root_fingerprint")
    ):
        errors.append(f"{case_id}:verified_exact_junction_not_equivalent")

    rejected = (
        ("junction_unproven", {"alias_kind": "junction", "alias_proof": None}),
        (
            "symlink",
            {"alias_kind": "symlink", "alias_proof": "verified_target_identity"},
        ),
        (
            "generic_reparse",
            {"alias_kind": "reparse", "alias_proof": "verified_target_identity"},
        ),
        ("alias_target_unknown", {"alias_target_verified": False}),
        (
            "escape",
            {
                "canonical_root": str(temp_root.parent / "outside-authority"),
                "containment_verified": False,
            },
        ),
    )
    for name, updates in rejected:
        evidence = deepcopy(baseline)
        evidence.update(updates)
        try:
            receipt = target(evidence)
        except Exception as exc:
            errors.append(f"{case_id}:{name}:unexpected_error:{type(exc).__name__}:{exc}")
            continue
        if not isinstance(receipt, dict):
            errors.append(f"{case_id}:{name}:receipt_not_dict")
            continue
        if receipt.get("status") != "AUTHORITY_ROOT_UNTRUSTED":
            errors.append(f"{case_id}:{name}:wrong_status:{receipt.get('status')}")
        if receipt.get("authority_realm_id") is not None:
            errors.append(f"{case_id}:{name}:realm_id_issued")
        if receipt.get("root_fingerprint") is not None:
            errors.append(f"{case_id}:{name}:root_fingerprint_issued")
        if receipt.get("distributed_lock") != "NOT_USED":
            errors.append(f"{case_id}:{name}:distributed_lock_fallback")
    return {case_id: len(errors) == before}


def _check_rc6_phase1_fixture_only_case(
    gate_module: object,
    paths_module: object,
    temp_root: Path,
    errors: list[str],
) -> dict[str, bool]:
    case_id = "RC6-PHASE1-FIXTURE-ONLY-028"
    before = len(errors)
    builder = getattr(paths_module, "build_local_authority_realm_receipt", None)
    admission = getattr(gate_module, "evaluate_authority_realm_admission", None)
    if not callable(builder) or not callable(admission):
        errors.append(f"{case_id}:missing_rc6_callable")
        return {case_id: False}

    fixture_root = temp_root / "fixture-authority"
    fixture_root.mkdir(parents=True)
    metadata = fixture_root.stat()
    evidence = {
        "authority_realm_seed": "rc6-fixture-host",
        "canonical_root": str(fixture_root.resolve(strict=True)),
        "filesystem_id": str(metadata.st_dev),
        "directory_id": str(metadata.st_ino),
        "identity_evidence": "temporary_directory_stat",
        "transport": "local_filesystem",
        "local_filesystem_verified": True,
        "alias_kind": "direct",
        "alias_target_verified": True,
        "containment_verified": True,
    }
    forbidden_calls: list[str] = []
    originals: dict[str, object] = {}

    def forbidden(name: str) -> Callable[..., object]:
        def fail(*_args: object, **_kwargs: object) -> object:
            forbidden_calls.append(name)
            raise AssertionError(f"forbidden_real_root_probe:{name}")

        return fail

    for name in ("shared_root", "references_root", "_active_shared_root"):
        originals[name] = getattr(paths_module, name, None)
        setattr(paths_module, name, forbidden(name))
    try:
        receipt = builder(evidence)
    except Exception as exc:
        errors.append(f"{case_id}:builder_error:{type(exc).__name__}:{exc}")
        receipt = None
    finally:
        for name, original in originals.items():
            setattr(paths_module, name, original)
    if forbidden_calls:
        errors.append(f"{case_id}:real_root_probe_attempted:{forbidden_calls}")
    if not isinstance(receipt, dict):
        errors.append(f"{case_id}:receipt_not_dict")
        return {case_id: False}

    expected_gates = [
        "PENDING_COUNT_ZERO",
        "QUIESCENCE_STABLE",
        "MIGRATION_GATE_PASSED",
    ]
    for name, expected in (
        ("phase1_scope", "PURE_RECEIPT_ONLY"),
        ("production_binding", "DEFERRED_PENDING_MIGRATION_GATE"),
        ("production_ready", False),
        ("authority_root_bound", False),
        ("archive_transaction_bound", False),
        ("required_production_gates", expected_gates),
    ):
        if receipt.get(name) != expected:
            errors.append(f"{case_id}:receipt_{name}:{receipt.get(name)}")
    try:
        gate = admission(
            task_id="task-rc6",
            operation_id="00000000-0000-4000-8000-000000000028",
            expected_receipt=receipt,
            presented_receipt=deepcopy(receipt),
        )
    except Exception as exc:
        errors.append(f"{case_id}:admission_error:{type(exc).__name__}:{exc}")
        gate = None
    if not isinstance(gate, dict) or gate.get("allowed") is not True:
        errors.append(f"{case_id}:fixture_admission_not_allowed")
    else:
        for name, expected in (
            ("production_ready", False),
            ("authority_root_bound", False),
            ("archive_transaction_bound", False),
            ("required_production_gates", expected_gates),
        ):
            if gate.get(name) != expected:
                errors.append(f"{case_id}:admission_{name}:{gate.get(name)}")
    try:
        reference_text = SHIGUAN_MEMORY_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{case_id}:reference_read_failed:{type(exc).__name__}:{exc}")
    else:
        required_reference_terms = (
            "RC6_LOCAL_AUTHORITY_REALM_PHASE1",
            "AUTHORITY_TRANSPORT_UNSUPPORTED",
            "PENDING_COUNT_ZERO",
            "QUIESCENCE_STABLE",
            "MIGRATION_GATE_PASSED",
        )
        missing = [term for term in required_reference_terms if term not in reference_text]
        if missing:
            errors.append(f"{case_id}:reference_terms_missing:{missing}")
    return {case_id: len(errors) == before}


def evaluate() -> dict[str, object]:
    errors: list[str] = []
    gate_module = _load_production(errors)
    cutover_module = _load_script(
        CUTOVER_PATH, "migrate_shared_shiguan_red_target", errors
    )
    paths_module = _load_script(PATHS_PATH, "shiguan_paths_red_target", errors)
    gate_passed = 0
    cutover_passed = 0
    paths_passed = 0
    quality_cases: dict[str, bool] = {}
    gate_target: Callable[..., object] | None = None
    cutover_target: Callable[..., object] | None = None
    with tempfile.TemporaryDirectory(prefix="court-shiguan-migration-red-") as temp_dir:
        temp_root = Path(temp_dir)
        if gate_module is not None:
            target = getattr(gate_module, "evaluate_migration_gate", None)
            if not callable(target):
                errors.append("missing_callable:evaluate_migration_gate")
            else:
                gate_target = target
                gate_passed = _check_cases(target, temp_root, errors)
                quality_cases.update(
                    _check_phase2_gate_cases(
                        target, temp_root / "phase2-gate", errors
                    )
                )
            quality_cases.update(
                _check_rc6_authority_mismatch_case(gate_module, errors)
            )
            quality_cases.update(
                _check_rc6_admission_fail_closed_case(gate_module, errors)
            )
        if cutover_module is not None:
            execute = getattr(cutover_module, "execute_atomic_cutover", None)
            if not callable(execute):
                errors.append("missing_callable:execute_atomic_cutover")
            elif gate_target is not None:
                cutover_target = execute
                cutover_passed = _check_cutover_cases(
                    gate_target, execute, cutover_module, temp_root, errors
                )
                quality_cases.update(
                    _check_phase2_cutover_cases(
                        execute,
                        cutover_module,
                        temp_root / "phase2-cutover",
                        errors,
                    )
                )
        if paths_module is not None:
            paths_passed = _check_default_shared_root(paths_module, temp_root, errors)
            paths_passed += _check_transitional_seed_root(
                paths_module, temp_root / "transitional-seed", errors
            )
            paths_passed += _check_cutover_receipt_consumer(
                paths_module, temp_root / "receipt-consumer", errors
            )
            quality_cases.update(
                _check_phase2_path_cases(
                    paths_module, temp_root / "phase2-paths", errors
                )
            )
            quality_cases.update(
                _check_rc6_pure_root_fingerprint_case(
                    paths_module, temp_root / "rc6-pure-root", errors
                )
            )
            quality_cases.update(
                _check_rc6_transport_unsupported_case(
                    paths_module, temp_root / "rc6-transport", errors
                )
            )
            quality_cases.update(
                _check_rc6_alias_escape_safety_case(
                    paths_module, temp_root / "rc6-alias-safety", errors
                )
            )
        if (
            gate_target is not None
            and cutover_target is not None
            and cutover_module is not None
            and paths_module is not None
        ):
            quality_cases.update(
                _check_phase3_repair_cases(
                    gate_target,
                    cutover_target,
                    cutover_module,
                    paths_module,
                    temp_root / "phase3-repair",
                    errors,
                )
            )
            quality_cases.update(
                _check_phase4_repair_cases(
                    gate_target,
                    gate_module,
                    cutover_target,
                    cutover_module,
                    paths_module,
                    temp_root / "phase4-repair",
                    errors,
                )
            )
            quality_cases.update(
                _check_phase5_terminal_marker_case(
                    cutover_target,
                    cutover_module,
                    paths_module,
                    temp_root / "phase5-terminal",
                    errors,
                )
            )
            quality_cases.update(
                _check_rc6_phase1_fixture_only_case(
                    gate_module,
                    paths_module,
                    temp_root / "rc6-phase1-only",
                    errors,
                )
            )
    passed_quality_ids = sorted(
        case_id for case_id, case_passed in quality_cases.items() if case_passed
    )
    failed_quality_ids = sorted(
        case_id for case_id, case_passed in quality_cases.items() if not case_passed
    )
    return {
        "ok": not errors,
        "schema": "court.shiguan_migration_gate.check.v1",
        "production_modules": [
            str(PRODUCTION_PATH),
            str(CUTOVER_PATH),
            str(PATHS_PATH),
        ],
        "quality_case_results": {
            case_id: quality_cases[case_id] for case_id in sorted(quality_cases)
        },
        "passed_quality_case_ids": passed_quality_ids,
        "failed_quality_case_ids": failed_quality_ids,
        "pending_body_accessed": False,
        "protected_paths": list(PROTECTED_PATHS),
        "errors": errors,
    }


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
