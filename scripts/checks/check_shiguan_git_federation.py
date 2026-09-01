"""RED/GREEN fixture gate for Shiguan shared Git and native memory federation."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
from unittest import mock

sys.dont_write_bytecode = True


def _git(work_tree: Path, *args: str, git_dir: Path | None = None) -> str:
    command = ["git"]
    if git_dir is None:
        command.extend(["-C", str(work_tree)])
    else:
        command.extend([f"--git-dir={git_dir}", f"--work-tree={work_tree}"])
    command.extend(args)
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace", env=env)
    if proc.returncode:
        raise AssertionError(f"git_failed:{args}:{proc.stderr.strip()}")
    return proc.stdout.strip()


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@local.invalid")


def _spec(module: Any, **values: Any) -> Any:
    return module.MemoryStoreSpec(**values)


def _check_apply_and_reuse(module: Any, base: Path) -> list[str]:
    shared = base / "shared" / "references"
    (shared / "shiguan-tree").mkdir(parents=True)
    (shared / "shiguan-tree" / "_index.md").write_text("# Fixture index\n", encoding="utf-8")
    (shared / "shiguan-index.jsonl").write_text("", encoding="utf-8")
    unicode_decision = shared / "memory-decisions" / "史馆记忆.md"
    unicode_decision.parent.mkdir(parents=True)
    unicode_decision.write_text("# 史馆记忆\n", encoding="utf-8")
    pending = shared / "shiguan-imports" / "pending" / "opaque.md"
    pending.parent.mkdir(parents=True)
    pending.write_bytes(b"opaque-private-body")
    pending_before = pending.read_bytes()

    codex = base / "home" / ".codex" / "memories"
    _init_repo(codex)
    (codex / "MEMORY.md").write_text("# Codex memory\n\nKeep this body.\n", encoding="utf-8")
    _git(codex, "add", "--", "MEMORY.md")
    _git(codex, "commit", "-m", "fixture codex memory")
    _git(codex, "remote", "add", "origin", "https://example.invalid/codex-memory.git")

    claude = base / "home" / ".claude"
    (claude / "projects" / "demo" / "memory").mkdir(parents=True)
    (claude / "memory.md").write_text("# Claude memory\n", encoding="utf-8")
    (claude / "projects" / "demo" / "memory" / "MEMORY.md").write_text("project memory\n", encoding="utf-8")
    hermes = base / "data" / "hermes"
    (hermes / "memories").mkdir(parents=True)
    (hermes / "profiles" / "empty" / "memories").mkdir(parents=True)
    control = shared / "court-runtime" / "memory-git"

    stores = [
        _spec(
            module,
            memory_store_id="codex-native-memory",
            tool_class="codex",
            native_root=codex,
            git_dir=codex / ".git",
            pathspecs=("MEMORY.md",),
            entrypoint=codex / "MEMORY.md",
            repository_mode="existing",
        ),
        _spec(
            module,
            memory_store_id="claude-code-native-memory",
            tool_class="claude-code",
            native_root=claude,
            git_dir=control / "git-dirs" / "claude-code.git",
            pathspecs=("memory.md", "projects/*/memory/**"),
            entrypoint=claude / "memory.md",
            repository_mode="separate",
        ),
        _spec(
            module,
            memory_store_id="hermes-native-memory",
            tool_class="hermes",
            native_root=hermes,
            git_dir=control / "git-dirs" / "hermes.git",
            pathspecs=("memories/**", "profiles/*/memories/**"),
            entrypoint=hermes / "memories" / "MEMORY.md",
            repository_mode="separate",
        ),
    ]

    result = module.apply_federation(
        shared_root=shared,
        stores=stores,
        transaction_id="fixture-transaction-001",
    )
    assert result["status"] == "APPLIED"
    assert result["MIGRATION_LINKS_VERIFIED"] is True
    assert result["pending_body_access"] == "NO"
    assert pending.read_bytes() == pending_before
    assert "shiguan-imports/pending/opaque.md" not in _git(shared, "ls-files").splitlines()
    assert "memory-decisions/史馆记忆.md" in _git(shared, "-c", "core.quotepath=false", "ls-files").splitlines()
    assert _git(shared, "remote").strip() == ""
    assert _git(codex, "remote", "get-url", "origin") == "https://example.invalid/codex-memory.git"

    registry_path = shared / "memories" / "memory-repositories.v1.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["schema"] == "decretum.shiguan.memory_git_registry.v1"
    assert registry["transaction_id"] == "fixture-transaction-001"
    assert len(registry["stores"]) == 3
    required = {
        "memory_store_id",
        "tool_class",
        "native_root",
        "repo_root",
        "git_dir",
        "memory_pathspec",
        "branch",
        "HEAD",
        "memory_state",
        "write_policy",
        "shared_commit",
        "native_commit",
        "transaction_id",
    }
    for entry in registry["stores"]:
        assert required <= set(entry), f"registry_fields_missing:{entry.get('memory_store_id')}"
        assert entry["transaction_id"] == "fixture-transaction-001"
        namespace = shared / "memories" / "tools" / entry["tool_class"] / "source.json"
        assert namespace.is_file()

    for store in stores:
        text = store.entrypoint.read_text(encoding="utf-8")
        assert text.count(module.LINK_BEGIN) == 1
        assert text.count(module.LINK_END) == 1
        assert store.memory_store_id in text
        assert _git(store.native_root, "diff", "--cached", "--name-only", git_dir=store.git_dir) == ""
        assert _git(store.native_root, "status", "--porcelain", "--", *store.pathspecs, git_dir=store.git_dir) == ""

    provenance = module.recall_provenance(shared_root=shared)
    assert provenance["registry_available"] is True
    assert provenance["migration_links_verified"] is True
    assert provenance["managed_store_count"] == 3
    assert "native_root" not in json.dumps(provenance, ensure_ascii=False)
    with mock.patch.object(module, "_git_shared", side_effect=AssertionError("recall_must_not_scan_git")), mock.patch.object(
        module,
        "_git_store",
        side_effect=AssertionError("recall_must_not_scan_native_git"),
    ):
        cached = module.recall_provenance(shared_root=shared)
    assert cached["migration_links_verified"] is True

    reused = module.apply_federation(
        shared_root=shared,
        stores=stores,
        transaction_id="fixture-transaction-001",
    )
    assert reused["status"] == "REUSED"
    for store in stores:
        assert store.entrypoint.read_text(encoding="utf-8").count(module.LINK_BEGIN) == 1
    return [
        "shared_shiguan_local_git",
        "native_memory_git_federation",
        "reciprocal_managed_links",
        "paired_commit_receipt",
        "pending_paths_excluded",
        "existing_remote_preserved_no_remote_ops",
        "memory_git_recall_provenance",
        "memory_git_recall_receipt_fastpath",
        "memory_git_idempotent_reuse",
        "unicode_shared_paths_unquoted",
    ]


def _check_dirty_fail_closed(module: Any, base: Path) -> list[str]:
    shared = base / "dirty-shared" / "references"
    shared.mkdir(parents=True)
    native = base / "dirty-home" / ".codex" / "memories"
    _init_repo(native)
    entrypoint = native / "MEMORY.md"
    entrypoint.write_text("# Baseline\n", encoding="utf-8")
    _git(native, "add", "--", "MEMORY.md")
    _git(native, "commit", "-m", "baseline")
    entrypoint.write_text("# User dirty change\n", encoding="utf-8")
    before = entrypoint.read_bytes()
    store = _spec(
        module,
        memory_store_id="codex-native-memory",
        tool_class="codex",
        native_root=native,
        git_dir=native / ".git",
        pathspecs=("MEMORY.md",),
        entrypoint=entrypoint,
        repository_mode="existing",
    )
    try:
        module.apply_federation(shared_root=shared, stores=[store], transaction_id="dirty-fixture")
    except module.FederationError as exc:
        assert exc.code == "managed_path_dirty"
    else:
        raise AssertionError("dirty_managed_path_accepted")
    assert entrypoint.read_bytes() == before
    assert not (shared / ".git").exists()
    return ["dirty_managed_path_fail_closed", "preflight_before_mutation"]


def _check_blank_host_bootstrap(module: Any, base: Path) -> list[str]:
    shared = base / "blank-shared" / "references"
    (shared / "shiguan-tree").mkdir(parents=True)
    (shared / "shiguan-tree" / "_index.md").write_text("# Blank host\n", encoding="utf-8")
    home = base / "blank-home"
    with mock.patch.object(module, "user_data_base", return_value=base / "blank-data"):
        stores = module.default_store_specs(shared_root=shared, home=home)
    probe = module._probe(shared, stores)
    assert all(not item["native_root_exists"] for item in probe["stores"])
    try:
        module.apply_federation(shared_root=shared, stores=stores, transaction_id="fixture-blank-denied")
    except module.FederationError as exc:
        assert exc.code == "native_root_missing"
    else:
        raise AssertionError("blank_host_bootstrap_without_authority")
    assert all(not store.native_root.exists() for store in stores)
    result = module.apply_federation(
        shared_root=shared,
        stores=stores,
        transaction_id="fixture-blank-host",
        bootstrap_missing_roots=True,
    )
    assert result["status"] == "APPLIED"
    assert set(result["bootstrapped_native_roots"]) == {store.memory_store_id for store in stores}
    assert all(store.native_root.is_dir() and store.entrypoint.is_file() for store in stores)
    return [
        "blank_host_probe_read_only",
        "blank_host_bootstrap_requires_authority",
        "blank_host_memory_roots_bootstrapped",
        "all_agent_memories_under_shiguan",
    ]


def _check_partial_resume(module: Any, base: Path) -> list[str]:
    shared = base / "resume-shared" / "references"
    (shared / "shiguan-tree").mkdir(parents=True)
    (shared / "shiguan-tree" / "_index.md").write_text("# Resume index\n", encoding="utf-8")
    native = base / "resume-home" / ".codex" / "memories"
    _init_repo(native)
    entrypoint = native / "MEMORY.md"
    entrypoint.write_text("# Resume baseline\n", encoding="utf-8")
    _git(native, "add", "--", "MEMORY.md")
    _git(native, "commit", "-m", "resume baseline")
    store = _spec(
        module,
        memory_store_id="codex-native-memory",
        tool_class="codex",
        native_root=native,
        git_dir=native / ".git",
        pathspecs=("MEMORY.md",),
        entrypoint=entrypoint,
        repository_mode="existing",
    )
    transaction = "fixture-partial-resume"
    with mock.patch.object(module, "_write_registry", side_effect=OSError("fixture shared registry failure")):
        try:
            module.apply_federation(shared_root=shared, stores=[store], transaction_id=transaction)
        except OSError as exc:
            assert "fixture shared registry failure" in str(exc)
        else:
            raise AssertionError("injected_partial_failure_accepted")
    failure_receipt = shared / "court-runtime" / "memory-git" / "receipts" / f"{transaction}.json"
    failure = json.loads(failure_receipt.read_text(encoding="utf-8"))
    assert failure["status"] == "FAILED_PARTIAL"
    assert failure["MIGRATION_LINKS_VERIFIED"] is False
    assert entrypoint.read_text(encoding="utf-8").count(module.LINK_BEGIN) == 1
    assert _git(native, "status", "--porcelain", "--", "MEMORY.md") == ""
    resumed = module.apply_federation(shared_root=shared, stores=[store], transaction_id=transaction)
    assert resumed["status"] == "APPLIED"
    assert resumed["MIGRATION_LINKS_VERIFIED"] is True
    final_receipt = json.loads(failure_receipt.read_text(encoding="utf-8"))
    assert final_receipt["status"] == "MIGRATION_LINKS_VERIFIED"

    unborn_shared = base / "unborn-shared" / "references"
    (unborn_shared / "shiguan-tree").mkdir(parents=True)
    (unborn_shared / "shiguan-tree" / "_index.md").write_text("# Unborn resume\n", encoding="utf-8")
    unborn_native = base / "unborn-home" / "hermes"
    (unborn_native / "profiles" / "empty" / "memories").mkdir(parents=True)
    unborn_store = _spec(
        module,
        memory_store_id="hermes-native-memory",
        tool_class="hermes",
        native_root=unborn_native,
        git_dir=unborn_shared / "court-runtime" / "memory-git" / "git-dirs" / "hermes.git",
        pathspecs=("memories/**", "profiles/*/memories/**"),
        entrypoint=unborn_native / "memories" / "MEMORY.md",
        repository_mode="separate",
    )
    with mock.patch.object(module, "_commit_store", side_effect=OSError("fixture unborn failure")):
        try:
            module.apply_federation(shared_root=unborn_shared, stores=[unborn_store], transaction_id="fixture-unborn-resume")
        except OSError:
            pass
        else:
            raise AssertionError("unborn_partial_failure_accepted")
    assert module._repo_exists(unborn_store.git_dir)
    assert module._git_store(unborn_store, "rev-parse", "HEAD", check=False) == "HEAD"
    resumed_unborn = module.apply_federation(
        shared_root=unborn_shared, stores=[unborn_store], transaction_id="fixture-unborn-resume"
    )
    assert resumed_unborn["status"] == "APPLIED"
    return [
        "partial_transaction_receipt",
        "same_transaction_roll_forward",
        "empty_glob_pathspec_skipped",
        "unborn_repository_roll_forward",
    ]


def evaluate() -> dict[str, Any]:
    checks: list[str] = []
    errors: list[str] = []
    try:
        module = importlib.import_module("shiguan_git_federation")
        with tempfile.TemporaryDirectory(prefix="shiguan-git-federation-") as raw:
            base = Path(raw)
            checks.extend(_check_apply_and_reuse(module, base))
            checks.extend(_check_blank_host_bootstrap(module, base))
            checks.extend(_check_dirty_fail_closed(module, base))
            checks.extend(_check_partial_resume(module, base))
    except (AssertionError, AttributeError, FileNotFoundError, ModuleNotFoundError, OSError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema": "decretum.shiguan_git_federation_gate.v1",
        "gate": "PASSED" if not errors else "FAILED",
        "checks": checks,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"SHIGUAN_GIT_FEDERATION_{result['gate']} checks={len(result['checks'])} errors={len(result['errors'])}")
        for error in result["errors"]:
            print(error)
    return 0 if result["gate"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())



