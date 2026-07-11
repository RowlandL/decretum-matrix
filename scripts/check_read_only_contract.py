"""Verify advertised court check-only and dry-run paths do not mutate host state."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS.parent


def snapshot(root: Path) -> dict[str, tuple[object, ...]]:
    if not root.exists():
        return {}
    result: dict[str, tuple[object, ...]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[relative] = ("file", stat.st_size, stat.st_mtime_ns, digest)
        elif path.is_dir():
            result[relative] = ("dir", stat.st_mtime_ns)
    return result


def isolated_env(base: Path, shared_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    home = base / "home"
    appdata = base / "appdata"
    localappdata = base / "localappdata"
    for path in (home, appdata, localappdata):
        path.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "COURT_SHARED_SHIGUAN_ROOT": str(shared_root),
            "SHIGUAN_SHARED_ROOT": str(shared_root),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(appdata),
            "LOCALAPPDATA": str(localappdata),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
    )
    env.pop("COURT_DISABLE_AGENT_PRESENCE", None)
    return env


def run_read_only(
    label: str,
    args: list[str],
    env: dict[str, str],
    watched_root: Path,
    allowed_returncodes: set[int],
) -> dict[str, object]:
    before = snapshot(watched_root)
    result = subprocess.run(
        [sys.executable, *args],
        cwd=SKILL_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    after = snapshot(watched_root)
    if result.returncode not in allowed_returncodes:
        raise AssertionError(
            f"{label} returned {result.returncode}; stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
    if before != after:
        changed = sorted(set(before) ^ set(after))
        changed.extend(key for key in before.keys() & after.keys() if before[key] != after[key])
        raise AssertionError(f"{label} mutated isolated state: {sorted(set(changed))}")
    return {
        "label": label,
        "returncode": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
    }


def assert_pending_body_not_read(base: Path, shared_root: Path, env: dict[str, str]) -> dict[str, object]:
    pending = shared_root / "references" / "shiguan-imports" / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    secret_body = pending / "secret.json"
    secret_body.write_text('{"text":"TOP-SECRET-BODY","estimated_tokens":9999}\n', encoding="utf-8")
    sidecar_body = pending / "sidecar-body.json"
    sidecar_body.write_text('{"raw_text":"SECOND-SECRET-BODY"}\n', encoding="utf-8")
    (pending / "sidecar-body.metadata.json").write_text(
        json.dumps(
            {
                "id": "sidecar-body",
                "filename": "source-note.md",
                "source_type": "md",
                "status": "pending",
                "imported_at": "fixture",
                "char_count": 120,
                "estimated_tokens": 48,
                "sha256": "0" * 64,
                "suggested_processor": "codex",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    previous = {key: os.environ.get(key) for key in env}
    previous_dont_write_bytecode = sys.dont_write_bytecode
    os.environ.update(env)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(SCRIPTS))
    try:
        module = importlib.import_module("check_shiguan_import_queue")
        module = importlib.reload(module)
        original_read_text = Path.read_text
        original_open = Path.open
        forbidden = {secret_body.resolve(), sidecar_body.resolve()}

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path.resolve() in forbidden:
                raise AssertionError(f"pending body was opened: {path}")
            return original_read_text(path, *args, **kwargs)

        def guarded_open(path: Path, *args: object, **kwargs: object):
            if path.resolve() in forbidden:
                raise AssertionError(f"pending body was opened: {path}")
            return original_open(path, *args, **kwargs)

        before = snapshot(base)
        with mock.patch.object(Path, "read_text", guarded_read_text), mock.patch.object(Path, "open", guarded_open):
            summary = module.queue_summary(8)
        after = snapshot(base)
        if before != after:
            raise AssertionError("metadata-only pending inspection mutated isolated state")
        if summary.get("pending_count") != 2:
            raise AssertionError(f"expected two pending bodies, got {summary.get('pending_count')}")
        samples = {str(item.get("id")): item for item in summary.get("samples", [])}
        if samples["secret"].get("metadata_status") != "unknown":
            raise AssertionError("body without sidecar must report metadata_status=unknown")
        if samples["secret"].get("estimated_tokens") is not None:
            raise AssertionError("body without sidecar must not infer tokens from body text")
        if samples["sidecar-body"].get("estimated_tokens") != 48:
            raise AssertionError("metadata sidecar token estimate was not used")
        serialized = json.dumps(summary, ensure_ascii=False)
        if "TOP-SECRET-BODY" in serialized or "SECOND-SECRET-BODY" in serialized:
            raise AssertionError("pending body leaked into metadata-only summary")
        return {
            "label": "pending_metadata_only",
            "pending_count": summary["pending_count"],
            "unknown_metadata_count": summary["unknown_metadata_count"],
        }
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        if str(SCRIPTS) in sys.path:
            sys.path.remove(str(SCRIPTS))
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> int:
    checks: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="court-read-only-contract-") as temp_dir:
        base = Path(temp_dir)
        blank = base / "blank"
        blank.mkdir()
        blank_shared = blank / "shared"
        blank_env = isolated_env(blank, blank_shared)

        checks.append(
            run_read_only(
                "catalog_shared_state_probe",
                [
                    "-c",
                    (
                        "import sys; "
                        f"sys.path.insert(0, {str(SCRIPTS)!r}); "
                        "import check_catalog; print(check_catalog.check_shiguan_state())"
                    ),
                ],
                blank_env,
                blank,
                {0},
            )
        )
        commands = [
            ("query_shiguan_index", [str(SCRIPTS / "query_shiguan_index.py"), "--format", "json"], {0, 1}),
            ("check_import_queue", [str(SCRIPTS / "check_shiguan_import_queue.py"), "--format", "json"], {0}),
            ("reevaluate_memory_dry_run", [str(SCRIPTS / "reevaluate_memory_decisions.py"), "--dry-run", "--limit", "1"], {0}),
            (
                "shiguan_web_check_only",
                [
                    str(SCRIPTS / "ensure_shiguan_web.py"),
                    "--check-only",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "65530",
                    "--max-port",
                    "65530",
                    "--timeout",
                    "0.05",
                ],
                {0},
            ),
            ("service_daemon_check_only", [str(SCRIPTS / "ensure_shiguan_service_daemon.py"), "--check-only"], {0, 1}),
            ("autosync_check_only", [str(SCRIPTS / "ensure_shiguan_autosync.py"), "--check-only"], {0}),
            (
                "obsidian_vault_dry_run",
                [str(SCRIPTS / "ensure_obsidian_shared_vault.py"), "--dry-run", "--no-set-open"],
                {0},
            ),
            (
                "obsidian_sync_dry_run_missing_tree",
                [str(SCRIPTS / "sync_shiguan_obsidian_vault.py"), "--dry-run", "--vault", str(blank / "vault")],
                {2},
            ),
            (
                "supercc_check_only",
                [
                    str(SCRIPTS / "ensure_supercc_court.py"),
                    "--workspace",
                    str(blank),
                    "--check-only",
                    "--no-auto-install-deps",
                    "--format",
                    "json",
                ],
                {0, 2},
            ),
            (
                "supercc_watchdog_no_apply",
                [
                    str(SCRIPTS / "supercc_watchdog.py"),
                    "--workspace",
                    str(blank),
                    "--roles",
                    "visible-core",
                    "--no-apply",
                    "--format",
                    "json",
                ],
                {0, 2},
            ),
        ]
        for label, args, allowed in commands:
            checks.append(run_read_only(label, args, blank_env, blank, allowed))

        fixture = base / "fixture"
        fixture.mkdir()
        fixture_shared = fixture / "shared"
        fixture_env = isolated_env(fixture, fixture_shared)
        checks.append(assert_pending_body_not_read(fixture, fixture_shared, fixture_env))

        source_tree = fixture_shared / "references" / "shiguan-tree"
        source_tree.mkdir(parents=True, exist_ok=True)
        (source_tree / "_index.md").write_text("---\ntype: test\n---\n# Test\n", encoding="utf-8")
        checks.append(
            run_read_only(
                "obsidian_sync_dry_run_existing_tree",
                [str(SCRIPTS / "sync_shiguan_obsidian_vault.py"), "--dry-run", "--vault", str(fixture / "vault")],
                fixture_env,
                fixture,
                {0},
            )
        )

    print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
