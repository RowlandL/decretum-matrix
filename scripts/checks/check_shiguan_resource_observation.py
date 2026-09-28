"""Read-only resource observation for the Shiguan long-running daemons.

Samples three independent resource facts and judges each against a configurable
threshold, printing one ``OBSERVATION <name>=<value> THRESHOLD=<...> <status>``
line per threshold class:

* ``python_processes`` - host python process count (``tasklist`` -> ``Get-Process``
  -> ``ps`` degradation; SKIP when no read-only probe works).
* ``shiguan_log_bytes_max`` / ``shiguan_state_json_bytes_max`` - metadata-only
  sizes of ``*.log`` and ``*-daemon.json`` / ``*-state.json`` under the OS temp
  directory and the court-shiguan runtime root. File contents are never read.
* ``shiguan_lock_wait_seconds`` - a real, contended ``<path>.lock`` acquisition
  inside an isolated fixture directory created through ``tempfile`` and removed
  afterwards. The real runtime lock is never opened, only stat-ed.

The script never writes outside its own isolated fixture, never kills a process
it did not spawn, and never performs a network request.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

# --- configurable thresholds (defaults; override with the matching CLI flag) --

# 64 MiB: a single daemon log above this is already past the 8 MiB rotation
# contract by 8x, and the historical failure was 31.3 GB (unbounded append).
MAX_LOG_BYTES = 64 * 1024 * 1024
# 8 MiB: matches the accepted service-log rotation ceiling; state/daemon JSON is
# a small projection and must never approach log-scale growth.
MAX_STATE_BYTES = 8 * 1024 * 1024
# 60: host baseline is ~21 python processes; this leaves 3x headroom before a
# runaway spawner (daemon per project) would be flagged.
MAX_PYTHON_PROCESSES = 60
# 45s: the observed long-hold incident was >45s on a single write lock.
MAX_LOCK_WAIT_SECONDS = 45.0
LOCK_HOLD_SECONDS = 5.0
LOCK_TIMEOUT_SECONDS = 90.0
TOP_ITEMS = 5

LOG_PATTERNS = ("*.log",)
STATE_PATTERNS = ("*-daemon.json", "*-state.json")
PRUNED_DIR_NAMES = frozenset({".git", "__pycache__", "node_modules", "legacy-skill-snapshots"})
FIXTURE_PREFIX = "court-shiguan-resource-observation-"
PROBE_LOCK_NAME = "shiguan-write.lock"
REAL_LOCK_NAME = "shiguan-write.lock"
SHIGUAN_MARKER = "shiguan"
SCHEMA = "court.shiguan_resource_observation.v1"
CONTRACT = "SHIGUAN_RESOURCE_OBSERVATION"

CHILD_HOLDER_SCRIPT = """
import os, sys, time
from pathlib import Path

lock = Path(sys.argv[1])
ready = Path(sys.argv[2])
hold = float(sys.argv[3])
fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
os.write(fd, str(os.getpid()).encode("ascii"))
os.close(fd)
ready.write_text("held", encoding="ascii")
time.sleep(hold)
try:
    lock.unlink()
except OSError:
    pass
"""


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{int(size)}B" if unit == "B" else f"{size:.2f}{unit}"
        size /= 1024.0
    return f"{value}B"


def _default_scan_roots() -> list[Path]:
    roots = [Path(tempfile.gettempdir())]
    runtime = os.environ.get("COURT_SHIGUAN_ROOT")
    roots.append(Path(runtime) if runtime else Path.home() / ".agents" / "court-shiguan")
    unique: list[Path] = []
    for root in roots:
        resolved = root.expanduser()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _matches(name: str, patterns: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pattern) for pattern in patterns)


def _is_shiguan_artifact(entry: dict[str, Any]) -> bool:
    return SHIGUAN_MARKER in entry["path"].lower()


def scan_artifact_sizes(roots: list[Path]) -> dict[str, Any]:
    logs: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    unreadable: list[str] = []
    missing_roots: list[str] = []
    pruned: set[str] = set()

    for root in roots:
        if not root.is_dir():
            missing_roots.append(str(root))
            continue
        for current, dirnames, filenames in os.walk(root, followlinks=False):
            kept: list[str] = []
            for name in sorted(dirnames):
                if name in PRUNED_DIR_NAMES:
                    pruned.add(name)
                else:
                    kept.append(name)
            dirnames[:] = kept
            for name in sorted(filenames):
                kind = (
                    "log"
                    if _matches(name, LOG_PATTERNS)
                    else "state"
                    if _matches(name, STATE_PATTERNS)
                    else None
                )
                if kind is None:
                    continue
                path = Path(current) / name
                try:
                    size = path.stat().st_size
                except OSError as exc:
                    unreadable.append(f"{path}:{type(exc).__name__}")
                    continue
                entry = {"path": str(path), "bytes": size}
                (logs if kind == "log" else states).append(entry)

    logs.sort(key=lambda item: (-item["bytes"], item["path"]))
    states.sort(key=lambda item: (-item["bytes"], item["path"]))
    return {
        "logs": logs,
        "states": states,
        "unreadable": unreadable,
        "missing_roots": missing_roots,
        "pruned_dirs": sorted(pruned),
        "roots": [str(root) for root in roots],
    }


def _tasklist_count() -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, "tasklist_unavailable"
    if completed.returncode != 0:
        return None, "tasklist_failed"
    count = 0
    for line in completed.stdout.splitlines():
        image = line.split(",")[0].strip().strip('"').lower()
        if image.startswith("python") and image.endswith(".exe"):
            count += 1
    return count, "tasklist"


def _get_process_count() -> tuple[int | None, str]:
    command = (
        "(Get-Process -Name python* -ErrorAction SilentlyContinue |"
        " Measure-Object).Count"
    )
    for shell in ("powershell", "pwsh"):
        try:
            completed = subprocess.run(
                [shell, "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0 and completed.stdout.strip().isdigit():
            return int(completed.stdout.strip()), f"{shell}:Get-Process"
    return None, "get_process_unavailable"


def _ps_count() -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            ["ps", "-A", "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, "ps_unavailable"
    if completed.returncode != 0:
        return None, "ps_failed"
    count = 0
    for line in completed.stdout.splitlines():
        name = os.path.basename(line.strip()).lower()
        if name.startswith("python"):
            count += 1
    return count, "ps"


def observe_python_processes() -> dict[str, Any]:
    if os.name == "nt":
        count, source = _tasklist_count()
        if count is None:
            count, source = _get_process_count()
    else:
        count, source = _ps_count()
    return {"value": count, "source": source}


def _try_acquire(lock: Path, timeout: float) -> tuple[bool, float]:
    started = time.monotonic()
    deadline = started + timeout
    while True:
        try:
            handle = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                return False, time.monotonic() - started
            time.sleep(0.02)
            continue
        except OSError:
            return False, time.monotonic() - started
        os.close(handle)
        return True, time.monotonic() - started


def _release(lock: Path) -> None:
    try:
        lock.unlink()
    except OSError:
        pass


def _wait_for_holder(ready: Path, child: subprocess.Popen[Any], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready.exists():
            return
        if child.poll() is not None:
            raise TimeoutError(f"fixture_holder_exited_early:{child.returncode}")
        time.sleep(0.02)
    raise TimeoutError("fixture_holder_not_ready")


def observe_lock_wait(
    fixture_root: Path | None,
    hold_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    children: list[subprocess.Popen[Any]] = []
    probe: dict[str, Any] = {"fixture": None, "fixture_root": str(fixture_root or tempfile.gettempdir())}
    try:
        with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX, dir=fixture_root) as temp_dir:
            fixture = Path(temp_dir).resolve()
            probe["fixture"] = str(fixture)
            isolated = fixture.name.startswith(FIXTURE_PREFIX) and fixture.is_relative_to(
                Path(fixture_root).resolve() if fixture_root else Path(tempfile.gettempdir()).resolve()
            )
            probe["fixture_isolated"] = isolated
            if not isolated:
                probe["reason"] = "fixture_not_isolated"
                return probe

            lock = fixture / f"{PROBE_LOCK_NAME}"
            acquired, uncontended = _try_acquire(lock, 5.0)
            if not acquired:
                probe["reason"] = "uncontended_fixture_lock_not_acquirable"
                return probe
            _release(lock)
            probe["uncontended_seconds"] = round(uncontended, 4)

            def start_holder(tag: str) -> subprocess.Popen[Any]:
                ready = fixture / f"holder-{tag}.ready"
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-c",
                        CHILD_HOLDER_SCRIPT,
                        str(lock),
                        str(ready),
                        repr(hold_seconds),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                children.append(child)
                _wait_for_holder(ready, child, 30.0)
                return child

            holder = start_holder("contended")
            acquired, waited = _try_acquire(lock, timeout_seconds)
            probe["timed_out"] = not acquired
            probe["wait_seconds"] = round(waited, 3)
            # Release unconditionally: the probe must hand a clean fixture to
            # the detection phase below, whether or not it won the race.
            _release(lock)
            holder.wait(timeout=hold_seconds + 30.0)

            timeout_holder = start_holder("detect")
            detected, _ = _try_acquire(lock, 0.5)
            probe["timeout_path_verified"] = not detected
            _release(lock)
            timeout_holder.wait(timeout=hold_seconds + 30.0)
            probe["reason"] = ""
            return probe
    except (OSError, subprocess.SubprocessError, TimeoutError, ValueError) as exc:
        probe["reason"] = f"{type(exc).__name__}: {exc}"
        return probe
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()


def observe_real_lock_metadata() -> dict[str, Any]:
    runtime = _default_scan_roots()[-1]
    lock = runtime / ".locks" / REAL_LOCK_NAME
    candidates = [lock] if lock.exists() else []
    if not candidates:
        try:
            candidates = sorted(runtime.rglob(REAL_LOCK_NAME))
        except OSError:
            candidates = []
    observed = []
    for path in candidates[:5]:
        try:
            stat = path.stat()
        except OSError:
            continue
        observed.append(
            {
                "path": str(path),
                "bytes": stat.st_size,
                "age_seconds": round(max(0.0, time.time() - stat.st_mtime), 3),
            }
        )
    return {"runtime_root": str(runtime), "locks": observed}


def _observation(name: str, value: Any, threshold: str, status: str, **extra: Any) -> dict[str, Any]:
    record = {"name": name, "value": value, "threshold": threshold, "status": status}
    record.update(extra)
    return record


def evaluate(options: argparse.Namespace) -> dict[str, Any]:
    roots = [Path(item).expanduser() for item in options.scan_root] or _default_scan_roots()
    sizes = scan_artifact_sizes(roots)
    processes = observe_python_processes()
    lock = observe_lock_wait(
        Path(options.fixture_root).expanduser() if options.fixture_root else None,
        options.lock_hold_seconds,
        options.lock_timeout_seconds,
    )
    real_lock = observe_real_lock_metadata()

    observations: list[dict[str, Any]] = []
    details: list[str] = []
    skips: list[str] = []

    if processes["value"] is None:
        observations.append(
            _observation(
                "python_processes",
                "unavailable",
                f"python_processes<={options.max_python_processes}",
                "SKIP",
                source=processes["source"],
            )
        )
        skips.append(f"python_processes:{processes['source']}")
    else:
        count = int(processes["value"])
        observations.append(
            _observation(
                "python_processes",
                count,
                f"python_processes<={options.max_python_processes}",
                "PASS" if count <= options.max_python_processes else "FAIL",
                source=processes["source"],
            )
        )

    shiguan_logs = [entry for entry in sizes["logs"] if _is_shiguan_artifact(entry)]
    worst_log = shiguan_logs[0]["bytes"] if shiguan_logs else None
    if worst_log is None:
        observations.append(
            _observation(
                "shiguan_log_bytes_max",
                "no_candidate",
                f"log_bytes<={options.max_log_bytes}",
                "SKIP",
            )
        )
        skips.append("shiguan_log_bytes_max:no_shiguan_*.log_candidate")
    else:
        observations.append(
            _observation(
                "shiguan_log_bytes_max",
                worst_log,
                f"log_bytes<={options.max_log_bytes}",
                "PASS" if worst_log <= options.max_log_bytes else "FAIL",
                path=shiguan_logs[0]["path"],
                candidate_count=len(shiguan_logs),
            )
        )
    for entry in sizes["logs"][: options.top]:
        flag = "OVER" if entry["bytes"] > options.max_log_bytes else "ok"
        scope = "shiguan" if _is_shiguan_artifact(entry) else "other"
        details.append(
            f"DETAIL log scope={scope} bytes={entry['bytes']} ({_human_bytes(entry['bytes'])}) "
            f"{flag} {entry['path']}"
        )

    shiguan_states = [entry for entry in sizes["states"] if _is_shiguan_artifact(entry)]
    worst_state = shiguan_states[0]["bytes"] if shiguan_states else None
    if worst_state is None:
        observations.append(
            _observation(
                "shiguan_state_json_bytes_max",
                "no_candidate",
                f"state_bytes<={options.max_state_bytes}",
                "SKIP",
            )
        )
        skips.append("shiguan_state_json_bytes_max:no_shiguan_state_candidate")
    else:
        observations.append(
            _observation(
                "shiguan_state_json_bytes_max",
                worst_state,
                f"state_bytes<={options.max_state_bytes}",
                "PASS" if worst_state <= options.max_state_bytes else "FAIL",
                path=shiguan_states[0]["path"],
                candidate_count=len(shiguan_states),
            )
        )
    for entry in sizes["states"][: options.top]:
        flag = "OVER" if entry["bytes"] > options.max_state_bytes else "ok"
        scope = "shiguan" if _is_shiguan_artifact(entry) else "other"
        details.append(
            f"DETAIL state scope={scope} bytes={entry['bytes']} ({_human_bytes(entry['bytes'])}) "
            f"{flag} {entry['path']}"
        )

    if lock.get("reason"):
        observations.append(
            _observation(
                "shiguan_lock_wait_seconds",
                "unavailable",
                f"lock_wait_seconds<={options.max_lock_wait_seconds}",
                "SKIP",
                reason=lock["reason"],
            )
        )
        skips.append(f"shiguan_lock_wait_seconds:{lock['reason']}")
    else:
        waited = float(lock["wait_seconds"])
        failed = bool(lock.get("timed_out")) or waited > options.max_lock_wait_seconds
        observations.append(
            _observation(
                "shiguan_lock_wait_seconds",
                waited,
                f"lock_wait_seconds<={options.max_lock_wait_seconds}",
                "FAIL" if failed else "PASS",
                timed_out=bool(lock.get("timed_out")),
                timeout_path_verified=bool(lock.get("timeout_path_verified")),
            )
        )
        details.append(
            f"DETAIL lock fixture={lock['fixture']} hold={options.lock_hold_seconds}s "
            f"waited={waited}s timed_out={bool(lock.get('timed_out'))} "
            f"timeout_path_verified={bool(lock.get('timeout_path_verified'))} "
            f"uncontended={lock.get('uncontended_seconds')}s"
        )

    for path in sizes["missing_roots"]:
        details.append(f"DETAIL scan_root_missing {path}")
    for path in sizes["unreadable"][: options.top]:
        details.append(f"DETAIL unreadable_metadata {path}")
    if sizes["pruned_dirs"]:
        details.append("DETAIL pruned_dir_names " + ",".join(sizes["pruned_dirs"]))
    for entry in real_lock["locks"]:
        details.append(
            f"DETAIL real_lock_metadata_only age={entry['age_seconds']}s bytes={entry['bytes']} {entry['path']}"
        )

    passed = sum(1 for item in observations if item["status"] == "PASS")
    failed = sum(1 for item in observations if item["status"] == "FAIL")
    skipped = sum(1 for item in observations if item["status"] == "SKIP")
    verdict = "FAIL" if failed else "PASS" if passed else "SKIP"

    return {
        "schema": SCHEMA,
        "contract": CONTRACT,
        "ok": verdict == "PASS",
        "status": verdict,
        "scan_roots": sizes["roots"],
        "observations": observations,
        "details": details,
        "skipped_observations": skips,
        "counts": {"pass": passed, "fail": failed, "skip": skipped},
        "evidence": {
            "top_logs": sizes["logs"][: options.top],
            "top_states": sizes["states"][: options.top],
            "log_candidate_count": len(sizes["logs"]),
            "state_candidate_count": len(sizes["states"]),
            "python_process_source": processes["source"],
            "lock_probe": lock,
            "real_lock_metadata_only": real_lock,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--scan-root", action="append", default=[], help="repeatable")
    parser.add_argument("--fixture-root", default="")
    parser.add_argument("--top", type=int, default=TOP_ITEMS)
    parser.add_argument("--max-log-bytes", type=int, default=MAX_LOG_BYTES)
    parser.add_argument("--max-state-bytes", type=int, default=MAX_STATE_BYTES)
    parser.add_argument("--max-python-processes", type=int, default=MAX_PYTHON_PROCESSES)
    parser.add_argument("--max-lock-wait-seconds", type=float, default=MAX_LOCK_WAIT_SECONDS)
    parser.add_argument("--lock-hold-seconds", type=float, default=LOCK_HOLD_SECONDS)
    parser.add_argument("--lock-timeout-seconds", type=float, default=LOCK_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    try:
        result = evaluate(args)
    except (OSError, ValueError, TypeError) as exc:
        result = {
            "schema": SCHEMA,
            "contract": CONTRACT,
            "ok": False,
            "status": "ERROR",
            "observations": [],
            "details": [],
            "counts": {"pass": 0, "fail": 1, "skip": 0},
            "failures": [f"observation_setup_error:{type(exc).__name__}:{exc}"],
        }

    if args.json:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(f"CONTRACT={result['contract']} SCHEMA={result['schema']}")
        print("SCAN_ROOTS=" + ",".join(result.get("scan_roots", [])))
        for item in result["observations"]:
            print(
                f"OBSERVATION {item['name']}={item['value']} "
                f"THRESHOLD={item['threshold']} {item['status']}"
            )
        for line in result["details"]:
            print(line)
        for failure in result.get("failures", []):
            print(f"FAILURE {failure}")
        print(
            "SUMMARY "
            f"pass={result['counts']['pass']} fail={result['counts']['fail']} "
            f"skip={result['counts']['skip']}"
        )
        for reason in result.get("skipped_observations", []):
            print(f"SKIP_REASON {reason}")
        print(f"OVERALL={result['status']}")

    if result["status"] == "PASS":
        return 0
    if result["status"] == "SKIP":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
