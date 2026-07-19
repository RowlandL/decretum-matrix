"""Manage the local-only Shiguan Git hub and native memory repositories."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable
import uuid

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock
from court_platform import user_data_base


REGISTRY_SCHEMA = "decretum.shiguan.memory_git_registry.v1"
RECEIPT_SCHEMA = "decretum.shiguan.memory_git_transaction.v1"
SHARED_REPO_ID = "decretum-matrix-shared-shiguan"
LINK_BEGIN = "<!-- DECRETUM_SHIGUAN_LINK_BEGIN v1 -->"
LINK_END = "<!-- DECRETUM_SHIGUAN_LINK_END -->"
LINK_PATTERN = re.compile(
    re.escape(LINK_BEGIN) + r".*?" + re.escape(LINK_END),
    flags=re.DOTALL,
)
SHARED_ALLOWED_EXACT = frozenset(
    {".gitignore", "README.md", "shiguan-index.jsonl", "shiguan-knowledge-graph.json"}
)
SHARED_ALLOWED_PREFIXES = (
    "plan-archives/",
    "memory-decisions/",
    "shiguan-tree/",
    "memories/",
)
SHARED_DENIED_PREFIXES = (
    "court-runtime/",
    "agente-logs/",
    "obsidian-sync/",
    "shiguan-imports/",
    "shiguan-peers/",
    "shiguan-tree/.obsidian/",
)
SHARED_GITIGNORE = """# Managed by Decretum Matrix Shiguan Git federation v1
*
!.gitignore
!README.md
!shiguan-index.jsonl
!shiguan-knowledge-graph.json
!plan-archives/
!plan-archives/**
!memory-decisions/
!memory-decisions/**
!shiguan-tree/
!shiguan-tree/**
shiguan-tree/.obsidian/
!memories/
!memories/**
"""


class FederationError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


@dataclass(frozen=True)
class MemoryStoreSpec:
    memory_store_id: str
    tool_class: str
    native_root: Path
    git_dir: Path
    pathspecs: tuple[str, ...]
    entrypoint: Path
    repository_mode: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "native_root", Path(self.native_root))
        object.__setattr__(self, "git_dir", Path(self.git_dir))
        object.__setattr__(self, "entrypoint", Path(self.entrypoint))
        object.__setattr__(self, "pathspecs", tuple(self.pathspecs))


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if check and proc.returncode:
        raise FederationError("git_command_failed", f"{' '.join(command)}:{proc.stderr.strip()}")
    return proc


def _git_shared(shared_root: Path, *args: str, check: bool = True) -> str:
    proc = _run(["git", "-C", str(shared_root), *args], check=check)
    return proc.stdout.strip()


def _git_store(store: MemoryStoreSpec, *args: str, check: bool = True) -> str:
    proc = _run(
        ["git", f"--git-dir={store.git_dir}", f"--work-tree={store.native_root}", *args],
        check=check,
    )
    return proc.stdout.strip()


def _valid_pathspec(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return bool(
        normalized
        and not normalized.startswith("/")
        and not re.match(r"^[A-Za-z]:", normalized)
        and ".." not in Path(normalized).parts
        and ".git" not in Path(normalized).parts
    )


def _validate_store(store: MemoryStoreSpec, *, require_native_root: bool = True) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", store.memory_store_id):
        raise FederationError("memory_store_id_invalid", store.memory_store_id)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,31}", store.tool_class):
        raise FederationError("tool_class_invalid", store.tool_class)
    if store.repository_mode not in {"existing", "inline", "separate"}:
        raise FederationError("repository_mode_invalid", store.repository_mode)
    if store.native_root.exists() and not store.native_root.is_dir():
        raise FederationError("native_root_not_directory", str(store.native_root))
    if require_native_root and not store.native_root.is_dir():
        raise FederationError("native_root_missing", str(store.native_root))
    try:
        store.entrypoint.resolve(strict=False).relative_to(store.native_root.resolve())
    except ValueError as exc:
        raise FederationError("entrypoint_outside_native_root", str(store.entrypoint)) from exc
    if not store.pathspecs or any(not _valid_pathspec(value) for value in store.pathspecs):
        raise FederationError("memory_pathspec_invalid", store.memory_store_id)
    entry_relative = store.entrypoint.resolve(strict=False).relative_to(store.native_root.resolve()).as_posix()
    if not any(Path(entry_relative).match(value) for value in store.pathspecs):
        raise FederationError("entrypoint_not_in_pathspec", entry_relative)


def _repo_exists(git_dir: Path) -> bool:
    return (git_dir / "HEAD").is_file() and (git_dir / "config").is_file()


def _remote_snapshot(store: MemoryStoreSpec) -> str:
    if not _repo_exists(store.git_dir):
        return ""
    return _git_store(store, "remote", "-v")


def _managed_status(store: MemoryStoreSpec) -> str:
    if not _repo_exists(store.git_dir):
        return ""
    return _git_store(store, "status", "--porcelain=v1", "--untracked-files=all", "--", *store.pathspecs)


def _preflight(
    shared_root: Path,
    stores: list[MemoryStoreSpec],
    *,
    bootstrap_missing_roots: bool = False,
) -> dict[str, str]:
    if not shared_root.is_dir():
        raise FederationError("shared_root_missing", str(shared_root))
    if len({store.memory_store_id for store in stores}) != len(stores):
        raise FederationError("duplicate_memory_store_id")
    if len({store.tool_class for store in stores}) != len(stores):
        raise FederationError("duplicate_tool_class")
    remotes: dict[str, str] = {}
    for store in stores:
        _validate_store(store, require_native_root=False)
        if not store.native_root.is_dir():
            if not bootstrap_missing_roots:
                raise FederationError("native_root_missing", str(store.native_root))
            if store.repository_mode == "existing":
                raise FederationError("existing_repository_missing", store.memory_store_id)
            remotes[store.memory_store_id] = ""
            continue
        exists = _repo_exists(store.git_dir)
        if store.repository_mode == "existing" and not exists:
            raise FederationError("existing_repository_missing", store.memory_store_id)
        if exists:
            if _git_store(store, "diff", "--cached", "--name-only"):
                raise FederationError("native_index_dirty", store.memory_store_id)
            if _managed_status(store):
                raise FederationError("managed_path_dirty", store.memory_store_id)
        remotes[store.memory_store_id] = _remote_snapshot(store)
    if (shared_root / ".git").exists():
        if _git_shared(shared_root, "diff", "--cached", "--name-only"):
            raise FederationError("shared_index_dirty")
        if _git_shared(shared_root, "remote"):
            raise FederationError("shared_remote_forbidden")
        _assert_shared_tracked_allowlist(shared_root)
    return remotes


def _bootstrap_store_roots(stores: Iterable[MemoryStoreSpec]) -> list[str]:
    created: list[str] = []
    for store in stores:
        if store.native_root.is_dir():
            continue
        if store.repository_mode == "existing":
            raise FederationError("existing_repository_missing", store.memory_store_id)
        store.native_root.mkdir(parents=True, exist_ok=False)
        created.append(store.memory_store_id)
    return created


def _set_identity_shared(shared_root: Path) -> None:
    if not _git_shared(shared_root, "config", "--local", "--get", "user.name", check=False):
        _git_shared(shared_root, "config", "--local", "user.name", "Decretum Matrix Shiguan")
    if not _git_shared(shared_root, "config", "--local", "--get", "user.email", check=False):
        _git_shared(shared_root, "config", "--local", "user.email", "shiguan@local.invalid")


def _set_identity_store(store: MemoryStoreSpec) -> None:
    if not _git_store(store, "config", "--local", "--get", "user.name", check=False):
        _git_store(store, "config", "--local", "user.name", "Decretum Matrix Shiguan")
    if not _git_store(store, "config", "--local", "--get", "user.email", check=False):
        _git_store(store, "config", "--local", "user.email", "shiguan@local.invalid")


def _ensure_store_repo(store: MemoryStoreSpec) -> bool:
    if _repo_exists(store.git_dir):
        _set_identity_store(store)
        head = _git_store(store, "rev-parse", "HEAD", check=False)
        return not bool(re.fullmatch(r"[0-9a-f]{40,64}", head))
    if store.repository_mode == "existing":
        raise FederationError("existing_repository_missing", store.memory_store_id)
    store.git_dir.parent.mkdir(parents=True, exist_ok=True)
    if store.repository_mode == "inline":
        _run(["git", "init", "--initial-branch=main", str(store.native_root)])
    else:
        _run(["git", "init", "--bare", "--initial-branch=main", str(store.git_dir)])
        _git_store(store, "config", "core.bare", "false")
        _git_store(store, "config", "core.worktree", str(store.native_root.resolve()))
        info = store.git_dir / "info"
        info.mkdir(parents=True, exist_ok=True)
        atomic_write_text(info / "exclude", "*\n", newline="")
    _set_identity_store(store)
    if _git_store(store, "remote"):
        raise FederationError("new_native_remote_forbidden", store.memory_store_id)
    return True


def _shared_path_allowed(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized in SHARED_ALLOWED_EXACT:
        return True
    if normalized + "/" in SHARED_ALLOWED_PREFIXES:
        return True
    if any(normalized.startswith(prefix) for prefix in SHARED_DENIED_PREFIXES):
        return False
    return any(normalized.startswith(prefix) for prefix in SHARED_ALLOWED_PREFIXES)


def _assert_shared_tracked_allowlist(shared_root: Path) -> None:
    tracked = [path for path in _git_shared(shared_root, "ls-files", "-z").split("\0") if path]
    forbidden = sorted(path for path in tracked if path and not _shared_path_allowed(path))
    if forbidden:
        raise FederationError("shared_tracked_path_forbidden", ",".join(forbidden[:8]))


def _stage_shared_paths(shared_root: Path, paths: Iterable[Path]) -> None:
    relative: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        rel = path.resolve().relative_to(shared_root.resolve()).as_posix()
        if not _shared_path_allowed(rel):
            raise FederationError("shared_stage_path_forbidden", rel)
        relative.append(rel)
    if relative:
        _git_shared(shared_root, "add", "--", *relative)


def _commit_shared(shared_root: Path, message: str) -> str:
    staged = _git_shared(shared_root, "diff", "--cached", "--name-only")
    if staged:
        _git_shared(shared_root, "commit", "--no-gpg-sign", "-m", message)
    head = _git_shared(shared_root, "rev-parse", "HEAD", check=False)
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise FederationError("shared_head_missing")
    return head


def _ensure_shared_anchor(shared_root: Path, transaction_id: str, stores: list[MemoryStoreSpec]) -> str:
    created = not (shared_root / ".git").exists()
    if created:
        _run(["git", "init", "--initial-branch=main", str(shared_root)])
    _set_identity_shared(shared_root)
    if _git_shared(shared_root, "remote"):
        raise FederationError("shared_remote_forbidden")
    existing_ignore = shared_root / ".gitignore"
    if existing_ignore.exists():
        current = existing_ignore.read_text(encoding="utf-8")
        if current != SHARED_GITIGNORE and "Managed by Decretum Matrix Shiguan Git federation" not in current:
            raise FederationError("shared_gitignore_unmanaged")
    atomic_write_text(existing_ignore, SHARED_GITIGNORE, newline="")
    memories = shared_root / "memories"
    memories.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        memories / "README.md",
        "# Shared Shiguan Memory Git Hub\n\nLocal-only registry and reciprocal links for native tool memory repositories.\n",
        newline="",
    )
    prepared = memories / "transactions" / transaction_id / "prepared.json"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        prepared,
        json.dumps(
            {
                "schema": "decretum.shiguan.memory_git_prepared.v1",
                "transaction_id": transaction_id,
                "memory_store_ids": [store.memory_store_id for store in stores],
                "pending_body_access": "NO",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        newline="",
    )
    stage = [existing_ignore, memories]
    if created:
        stage.extend(
            shared_root / name
            for name in (
                "README.md",
                "shiguan-index.jsonl",
                "shiguan-knowledge-graph.json",
                "plan-archives",
                "memory-decisions",
                "shiguan-tree",
            )
        )
    _stage_shared_paths(shared_root, stage)
    anchor = _commit_shared(shared_root, f"Initialize Shiguan memory Git transaction {transaction_id}")
    _assert_shared_tracked_allowlist(shared_root)
    return anchor


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _render_link(store: MemoryStoreSpec, shared_root: Path, shared_commit: str, transaction_id: str) -> str:
    index = shared_root / "shiguan-tree" / "_index.md"
    namespace = shared_root / "memories" / "tools" / store.tool_class
    return "\n".join(
        [
            LINK_BEGIN,
            "## Shared Shiguan / 共享史馆",
            "",
            f"- Index: [{index.name}]({_file_uri(index)})",
            f"- Tool namespace: [{store.tool_class}]({_file_uri(namespace)})",
            f"- `memory_store_id`: `{store.memory_store_id}`",
            f"- `shared_repo_id`: `{SHARED_REPO_ID}`",
            f"- `shared_commit`: `{shared_commit}`",
            f"- `transaction_id`: `{transaction_id}`",
            LINK_END,
        ]
    )


def _frontmatter_end(text: str) -> int:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return 0
    offset = normalized.find("\n---\n", 4)
    if offset < 0:
        return 0
    logical = offset + len("\n---\n")
    if "\r\n" not in text:
        return logical
    return len(normalized[:logical].replace("\n", "\r\n"))


def _upsert_link(path: Path, block: str) -> tuple[bool, bool, str]:
    existed = path.exists()
    original = path.read_text(encoding="utf-8-sig") if existed else ""
    newline = "\r\n" if "\r\n" in original else "\n"
    rendered = block.replace("\n", newline)
    if LINK_PATTERN.search(original):
        updated = LINK_PATTERN.sub(rendered, original, count=1)
    else:
        offset = _frontmatter_end(original)
        prefix = original[:offset]
        suffix = original[offset:]
        if prefix and not prefix.endswith(("\n", "\r")):
            prefix += newline
        if suffix:
            suffix = suffix.lstrip("\r\n")
            updated = prefix + rendered + newline * 2 + suffix
        else:
            updated = prefix + rendered + newline
    if original.startswith("\ufeff") and not updated.startswith("\ufeff"):
        updated = "\ufeff" + updated
    changed = updated != original
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, updated, newline="")
    return changed, existed, original


def _commit_store(store: MemoryStoreSpec, created_repo: bool, message: str) -> str:
    if created_repo:
        matched: list[str] = []
        for pathspec in store.pathspecs:
            if any(character in pathspec for character in "*?["):
                if any(path.is_file() for path in store.native_root.glob(pathspec)):
                    matched.append(pathspec)
            elif (store.native_root / pathspec).exists():
                matched.append(pathspec)
        entry_relative = store.entrypoint.resolve().relative_to(store.native_root.resolve()).as_posix()
        if not any(Path(entry_relative).match(pathspec) for pathspec in matched):
            matched.append(entry_relative)
        _git_store(store, "add", "-f", "--", *matched)
    else:
        relative = store.entrypoint.resolve().relative_to(store.native_root.resolve()).as_posix()
        _git_store(store, "add", "--", relative)
    staged = _git_store(store, "diff", "--cached", "--name-only")
    if staged:
        _git_store(store, "commit", "--no-gpg-sign", "-m", message)
    head = _git_store(store, "rev-parse", "HEAD", check=False)
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise FederationError("native_head_missing", store.memory_store_id)
    return head


def _branch(store: MemoryStoreSpec) -> str:
    branch = _git_store(store, "symbolic-ref", "--short", "HEAD", check=False)
    return branch or "detached"


def _write_registry(
    shared_root: Path,
    stores: list[MemoryStoreSpec],
    native_commits: dict[str, str],
    shared_anchor: str,
    transaction_id: str,
) -> tuple[dict[str, Any], Path]:
    entries: list[dict[str, Any]] = []
    for store in stores:
        entry = {
            "memory_store_id": store.memory_store_id,
            "tool_class": store.tool_class,
            "native_root": str(store.native_root.resolve()),
            "repo_root": str(store.native_root.resolve()),
            "git_dir": str(store.git_dir.resolve()),
            "memory_pathspec": list(store.pathspecs),
            "entrypoint": str(store.entrypoint.resolve()),
            "branch": _branch(store),
            "HEAD": native_commits[store.memory_store_id],
            "memory_state": "present" if store.entrypoint.stat().st_size else "empty",
            "write_policy": "managed_link_only_noncurrent_body_preserved",
            "shared_commit": shared_anchor,
            "native_commit": native_commits[store.memory_store_id],
            "transaction_id": transaction_id,
        }
        entries.append(entry)
        namespace = shared_root / "memories" / "tools" / store.tool_class
        namespace.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            namespace / "source.json",
            json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            newline="",
        )
        atomic_write_text(
            namespace / "README.md",
            "\n".join(
                [
                    f"# {store.tool_class} native memory",
                    "",
                    f"- `memory_store_id`: `{store.memory_store_id}`",
                    f"- Native entrypoint: [{store.entrypoint.name}]({_file_uri(store.entrypoint)})",
                    f"- Native commit: `{native_commits[store.memory_store_id]}`",
                    f"- Shared anchor: `{shared_anchor}`",
                    f"- Transaction: `{transaction_id}`",
                    "",
                ]
            ),
            newline="",
        )
    receipt_rel = f"court-runtime/memory-git/receipts/{transaction_id}.json"
    registry = {
        "schema": REGISTRY_SCHEMA,
        "repo_id": SHARED_REPO_ID,
        "shared_root": str(shared_root.resolve()),
        "shared_git_dir": str((shared_root / ".git").resolve()),
        "shared_anchor_commit": shared_anchor,
        "transaction_id": transaction_id,
        "status": "MIGRATION_LINKS_VERIFIED",
        "MIGRATION_LINKS_VERIFIED": True,
        "pending_body_access": "NO",
        "receipt_path": receipt_rel,
        "stores": entries,
    }
    registry_path = shared_root / "memories" / "memory-repositories.v1.json"
    atomic_write_text(
        registry_path,
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        newline="",
    )
    completed = shared_root / "memories" / "transactions" / transaction_id / "completed.json"
    atomic_write_text(
        completed,
        json.dumps(
            {
                "schema": "decretum.shiguan.memory_git_completed.v1",
                "transaction_id": transaction_id,
                "shared_anchor_commit": shared_anchor,
                "native_commits": native_commits,
                "status": "PREPARED_FOR_SHARED_REGISTRY_COMMIT",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        newline="",
    )
    return registry, registry_path


def _write_receipt(
    shared_root: Path,
    registry: dict[str, Any],
    shared_registry_commit: str,
) -> Path:
    path = shared_root / str(registry["receipt_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "issued_at": _now_iso(),
        "status": "MIGRATION_LINKS_VERIFIED",
        "MIGRATION_LINKS_VERIFIED": True,
        "transaction_id": registry["transaction_id"],
        "shared_repo_id": SHARED_REPO_ID,
        "shared_anchor_commit": registry["shared_anchor_commit"],
        "shared_registry_commit": shared_registry_commit,
        "native_commits": {
            entry["memory_store_id"]: entry["native_commit"] for entry in registry["stores"]
        },
        "registry_sha256": hashlib.sha256(
            (shared_root / "memories" / "memory-repositories.v1.json").read_bytes()
        ).hexdigest(),
        "pending_body_access": "NO",
        "remote_operations": 0,
    }
    atomic_write_text(path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", newline="")
    return path


def _write_failure_receipt(
    shared_root: Path,
    *,
    transaction_id: str,
    stage: str,
    shared_anchor_commit: str,
    native_commits: dict[str, str],
    error: BaseException,
) -> Path:
    path = shared_root / "court-runtime" / "memory-git" / "receipts" / f"{transaction_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    error_text = str(error)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "issued_at": _now_iso(),
        "status": "FAILED_PARTIAL",
        "MIGRATION_LINKS_VERIFIED": False,
        "transaction_id": transaction_id,
        "shared_repo_id": SHARED_REPO_ID,
        "shared_anchor_commit": shared_anchor_commit,
        "native_commits": native_commits,
        "failure_stage": stage,
        "error_type": type(error).__name__,
        "error_sha256": hashlib.sha256(error_text.encode("utf-8", errors="replace")).hexdigest(),
        "resumable_with_same_transaction_id": True,
        "pending_body_access": "NO",
        "remote_operations": 0,
    }
    atomic_write_text(path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", newline="")
    return path


def _spec_from_entry(entry: dict[str, Any]) -> MemoryStoreSpec:
    git_dir = Path(str(entry["git_dir"]))
    native_root = Path(str(entry["native_root"]))
    mode = "existing" if git_dir == native_root / ".git" else "separate"
    return MemoryStoreSpec(
        memory_store_id=str(entry["memory_store_id"]),
        tool_class=str(entry["tool_class"]),
        native_root=native_root,
        git_dir=git_dir,
        pathspecs=tuple(str(value) for value in entry["memory_pathspec"]),
        entrypoint=Path(str(entry["entrypoint"])),
        repository_mode=mode,
    )


def verify_federation(*, shared_root: Path) -> dict[str, Any]:
    shared_root = Path(shared_root)
    registry_path = shared_root / "memories" / "memory-repositories.v1.json"
    if not registry_path.is_file():
        raise FederationError("registry_missing")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise FederationError("registry_schema_invalid")
    receipt_path = shared_root / str(registry.get("receipt_path") or "")
    if not receipt_path.is_file():
        raise FederationError("paired_receipt_missing")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise FederationError("paired_receipt_schema_invalid")
    if receipt.get("transaction_id") != registry.get("transaction_id"):
        raise FederationError("transaction_id_mismatch")
    if _git_shared(shared_root, "remote"):
        raise FederationError("shared_remote_forbidden")
    if _git_shared(shared_root, "diff", "--cached", "--name-only"):
        raise FederationError("shared_index_dirty")
    shared_head = _git_shared(shared_root, "rev-parse", "HEAD")
    if receipt.get("shared_registry_commit") != shared_head:
        raise FederationError("shared_registry_commit_mismatch")
    _assert_shared_tracked_allowlist(shared_root)
    native_commits = receipt.get("native_commits")
    if not isinstance(native_commits, dict):
        raise FederationError("native_commit_map_invalid")
    for entry in registry.get("stores", []):
        store = _spec_from_entry(entry)
        _validate_store(store)
        if _git_store(store, "diff", "--cached", "--name-only"):
            raise FederationError("native_index_dirty", store.memory_store_id)
        if _managed_status(store):
            raise FederationError("managed_path_dirty", store.memory_store_id)
        head = _git_store(store, "rev-parse", "HEAD")
        if head != entry.get("native_commit") or native_commits.get(store.memory_store_id) != head:
            raise FederationError("native_commit_mismatch", store.memory_store_id)
        link = store.entrypoint.read_text(encoding="utf-8-sig")
        if link.count(LINK_BEGIN) != 1 or link.count(LINK_END) != 1:
            raise FederationError("managed_link_invalid", store.memory_store_id)
        for token in (store.memory_store_id, str(registry["shared_anchor_commit"]), str(registry["transaction_id"])):
            if token not in link:
                raise FederationError("managed_link_binding_mismatch", store.memory_store_id)
        source = shared_root / "memories" / "tools" / store.tool_class / "source.json"
        if not source.is_file():
            raise FederationError("reverse_link_missing", store.memory_store_id)
    return {
        "schema": "decretum.shiguan.memory_git_verification.v1",
        "status": "VERIFIED",
        "MIGRATION_LINKS_VERIFIED": True,
        "transaction_id": registry["transaction_id"],
        "shared_anchor_commit": registry["shared_anchor_commit"],
        "shared_registry_commit": shared_head,
        "managed_store_count": len(registry.get("stores", [])),
        "pending_body_access": "NO",
        "remote_operations": 0,
        "receipt_path": str(receipt_path),
    }


def apply_federation(
    *,
    shared_root: Path,
    stores: Iterable[MemoryStoreSpec],
    transaction_id: str | None = None,
    bootstrap_missing_roots: bool = False,
) -> dict[str, Any]:
    shared_root = Path(shared_root)
    stores_list = list(stores)
    transaction = transaction_id or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,95}", transaction):
        raise FederationError("transaction_id_invalid")
    registry_path = shared_root / "memories" / "memory-repositories.v1.json"
    if registry_path.is_file():
        try:
            existing = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FederationError("registry_json_invalid") from exc
        if existing.get("transaction_id") == transaction:
            reused = verify_federation(shared_root=shared_root)
            reused["status"] = "REUSED"
            reused["bootstrapped_native_roots"] = []
            return reused
    remote_before = _preflight(
        shared_root,
        stores_list,
        bootstrap_missing_roots=bootstrap_missing_roots,
    )
    lock_path = shared_root / "court-runtime" / "shiguan-write.lock"
    stage = "preflight"
    shared_anchor = ""
    native_commits: dict[str, str] = {}
    bootstrapped_native_roots: list[str] = []
    try:
        with file_lock(lock_path, timeout=30.0):
            stage = "native_root_bootstrap"
            bootstrapped_native_roots = _bootstrap_store_roots(stores_list)
            stage = "shared_anchor"
            shared_anchor = _ensure_shared_anchor(shared_root, transaction, stores_list)
            for store in stores_list:
                stage = f"native_commit:{store.memory_store_id}"
                created_repo = _ensure_store_repo(store)
                block = _render_link(store, shared_root, shared_anchor, transaction)
                changed, _existed, _original = _upsert_link(store.entrypoint, block)
                if not changed and not created_repo:
                    current = store.entrypoint.read_text(encoding="utf-8-sig")
                    for token in (store.memory_store_id, shared_anchor, transaction):
                        if token not in current:
                            raise FederationError("managed_link_resume_mismatch", store.memory_store_id)
                    native_commits[store.memory_store_id] = _git_store(store, "rev-parse", "HEAD")
                else:
                    native_commits[store.memory_store_id] = _commit_store(
                        store,
                        created_repo,
                        f"Bind {store.tool_class} memory to shared Shiguan ({transaction})",
                    )
                if _remote_snapshot(store) != remote_before[store.memory_store_id]:
                    raise FederationError("native_remote_changed", store.memory_store_id)
            stage = "shared_registry"
            registry, registry_file = _write_registry(
                shared_root,
                stores_list,
                native_commits,
                shared_anchor,
                transaction,
            )
            _stage_shared_paths(shared_root, [shared_root / "memories", registry_file])
            shared_commit = _commit_shared(shared_root, f"Register native memory repositories ({transaction})")
            stage = "paired_receipt"
            _write_receipt(shared_root, registry, shared_commit)
            stage = "verification"
            verified = verify_federation(shared_root=shared_root)
            verified["status"] = "APPLIED"
            verified["bootstrapped_native_roots"] = bootstrapped_native_roots
            return verified
    except BaseException as exc:
        try:
            _write_failure_receipt(
                shared_root,
                transaction_id=transaction,
                stage=stage,
                shared_anchor_commit=shared_anchor,
                native_commits=native_commits,
                error=exc,
            )
        except OSError:
            pass
        raise


def recall_provenance(*, shared_root: Path) -> dict[str, Any]:
    shared_root = Path(shared_root)
    registry_path = shared_root / "memories" / "memory-repositories.v1.json"
    if not registry_path.is_file():
        return {
            "schema": "decretum.gbrain.memory_git_provenance.v1",
            "registry_available": False,
            "migration_links_verified": False,
            "managed_store_count": 0,
            "stores": [],
        }
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry.get("schema") != REGISTRY_SCHEMA:
            raise ValueError("registry_schema_invalid")
        receipt_path = shared_root / str(registry.get("receipt_path") or "")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("schema") != RECEIPT_SCHEMA:
            raise ValueError("receipt_schema_invalid")
        if receipt.get("transaction_id") != registry.get("transaction_id"):
            raise ValueError("transaction_id_mismatch")
        registry_sha256 = hashlib.sha256(registry_path.read_bytes()).hexdigest()
        if receipt.get("registry_sha256") != registry_sha256:
            raise ValueError("registry_sha256_mismatch")
        if receipt.get("MIGRATION_LINKS_VERIFIED") is not True:
            raise ValueError("migration_links_not_verified")
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {
            "schema": "decretum.gbrain.memory_git_provenance.v1",
            "registry_available": True,
            "migration_links_verified": False,
            "managed_store_count": 0,
            "stores": [],
        }
    stores = [
        {
            "memory_store_id": entry.get("memory_store_id"),
            "tool_class": entry.get("tool_class"),
            "memory_state": entry.get("memory_state"),
            "native_commit": entry.get("native_commit"),
            "shared_commit": entry.get("shared_commit"),
            "transaction_id": entry.get("transaction_id"),
        }
        for entry in registry.get("stores", [])
        if isinstance(entry, dict)
    ]
    return {
        "schema": "decretum.gbrain.memory_git_provenance.v1",
        "registry_available": True,
        "migration_links_verified": True,
        "managed_store_count": len(stores),
        "shared_registry_commit": receipt.get("shared_registry_commit"),
        "transaction_id": receipt.get("transaction_id"),
        "verification_mode": "registry_receipt_sha256",
        "stores": stores,
    }


def default_store_specs(*, shared_root: Path, home: Path | None = None) -> list[MemoryStoreSpec]:
    user_home = Path(home or Path.home())
    control = Path(shared_root) / "court-runtime" / "memory-git" / "git-dirs"
    codex = user_home / ".codex" / "memories"
    claude = user_home / ".claude"
    hermes = user_data_base() / "hermes"
    return [
        MemoryStoreSpec(
            "codex-native-memory",
            "codex",
            codex,
            codex / ".git",
            (
                "MEMORY.md",
                "memory_summary.md",
                "raw_memories.md",
                "extensions/**",
                "skills/**",
                "rollout_summaries/**",
                "automations/**",
            ),
            codex / "MEMORY.md",
            "existing" if _repo_exists(codex / ".git") else "inline",
        ),
        MemoryStoreSpec(
            "claude-code-native-memory",
            "claude-code",
            claude,
            control / "claude-code.git",
            ("memory.md", "OMINA_MEMORY.md", "projects/*/memory/**"),
            claude / "memory.md",
            "separate",
        ),
        MemoryStoreSpec(
            "hermes-native-memory",
            "hermes",
            hermes,
            control / "hermes.git",
            ("memories/**", "profiles/*/memories/**"),
            hermes / "memories" / "MEMORY.md",
            "separate",
        ),
    ]


def _default_shared_root() -> Path:
    from shiguan_paths import references_root

    return references_root()


def _probe(shared_root: Path, stores: list[MemoryStoreSpec]) -> dict[str, Any]:
    output: list[dict[str, Any]] = []
    for store in stores:
        _validate_store(store, require_native_root=False)
        exists = _repo_exists(store.git_dir)
        output.append(
            {
                "memory_store_id": store.memory_store_id,
                "tool_class": store.tool_class,
                "native_root_exists": store.native_root.is_dir(),
                "entrypoint_exists": store.entrypoint.is_file(),
                "repository_exists": exists,
                "repository_mode": store.repository_mode,
                "branch": _branch(store) if exists else "",
                "HEAD": _git_store(store, "rev-parse", "HEAD", check=False) if exists else "",
                "remote_count": len(_git_store(store, "remote").splitlines()) if exists else 0,
                "managed_path_dirty": bool(_managed_status(store)) if exists else False,
                "memory_pathspec": list(store.pathspecs),
            }
        )
    return {
        "schema": "decretum.shiguan.memory_git_probe.v1",
        "shared_root": str(shared_root),
        "shared_repository_exists": (shared_root / ".git").exists(),
        "pending_body_access": "NO",
        "stores": output,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("probe", "apply", "verify"))
    parser.add_argument("--shared-root")
    parser.add_argument("--allow-host-mutation", action="store_true")
    parser.add_argument("--transaction-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    shared = Path(args.shared_root).resolve() if args.shared_root else _default_shared_root()
    try:
        if args.command == "verify":
            result = verify_federation(shared_root=shared)
        else:
            stores = default_store_specs(shared_root=shared)
            if args.command == "probe":
                result = _probe(shared, stores)
            else:
                if not args.allow_host_mutation:
                    raise FederationError("allow_host_mutation_required")
                result = apply_federation(
                    shared_root=shared,
                    stores=stores,
                    transaction_id=args.transaction_id,
                    bootstrap_missing_roots=True,
                )
    except (FederationError, OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "decretum.shiguan.memory_git_command.v1",
            "status": "FAILED",
            "error": str(exc),
            "pending_body_access": "NO",
        }
        code = 2
    else:
        code = 0
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
