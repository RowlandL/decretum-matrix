"""Exercise crash release and concurrent Shiguan checkpoint integrity."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
import errno
import hashlib
import importlib.util
import io
import json
import multiprocessing
import os
import pickle
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
import tempfile
import threading
import time
import types
from typing import Any
from types import SimpleNamespace
from unittest.mock import patch

from court_file_lock import atomic_write_text, file_lock


CHECKPOINT_WRITERS = 32
WEB_UPSERT_THREADS = 32
ATOMIC_WRITERS = 32
CHECKPOINT_LOCK_TIMEOUT_SECONDS = 120.0
CHECKPOINT_JOIN_TIMEOUT_SECONDS = 180.0


def _seed_worker(shared: str, window: str, reached: Any, release: Any, result: Any) -> None:
    import court_file_lock as locking
    import shiguan_paths as paths

    config = Path(shared) / "references/obsidian-sync/config.json"
    real_open, real_fdopen = Path.open, os.fdopen
    publication = "rename" if os.name == "nt" else "link"
    real_mkstemp, real_publish = tempfile.mkstemp, getattr(os, publication)
    candidate_fds = set()

    class ScheduledWriter:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def write(self, data):
            middle = len(data) // 2
            self.handle.write(data[:middle])
            self.handle.flush()
            reached.set()
            assert release.wait(15), "seed candidate writer was not released"
            self.handle.write(data[middle:])
            return len(data)

    def scheduled_open(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        # Retain the real failure control for the old final-name-first writer.
        return ScheduledWriter(handle) if path == config and mode == "x" and window == "write" else handle

    def scheduled_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        if Path(name).name.startswith(".config.json."):
            candidate_fds.add(fd)
        return fd, name

    def scheduled_fdopen(fd, *args, **kwargs):
        handle = real_fdopen(fd, *args, **kwargs)
        # This is the actual new candidate write, before its flush/fsync/commit.
        return ScheduledWriter(handle) if fd in candidate_fds and window == "write" else handle

    def scheduled_publish(source, target, **kwargs):
        if Path(target) == config and window in {"commit", "exit"}:
            reached.set()
            if window == "exit":
                os._exit(23)
            assert release.wait(15), "seed name commit was not released"
        return real_publish(source, target, **kwargs)

    with patch.dict(os.environ, {"COURT_SHARED_SHIGUAN_ROOT": shared,
                                "COURT_DISABLE_AGENT_PRESENCE": "1"}), \
            patch.object(Path, "open", scheduled_open), \
            patch.object(locking.tempfile, "mkstemp", scheduled_mkstemp), \
            patch.object(locking.os, "fdopen", scheduled_fdopen), \
            patch.object(locking.os, publication, scheduled_publish):
        if window == "warm":
            with file_lock(config.parents[1] / "court-runtime/shiguan-write.lock", shared=True):
                reached.set()
                assert release.wait(15)
                refs = paths.ensure_shared_seed()
        else:
            refs = paths.ensure_shared_seed()
        raw = (refs / "obsidian-sync/config.json").read_bytes()
        try:
            value = json.loads(raw)
            valid = isinstance(value, dict) and "shared_shiguan_root" in value
        except json.JSONDecodeError:
            valid = False
        graph = json.loads((refs / "shiguan-knowledge-graph.json").read_bytes())
        index_rows = [json.loads(line) for line in (refs / "shiguan-index.jsonl").read_text(
            encoding="utf-8").splitlines() if line.strip()]
        result.put({"valid_json": valid, "config_bytes": len(raw),
                    "valid_graph": isinstance(graph, dict), "valid_index_rows": len(index_rows)})


def _seed_winner(target: str, payload: str, barrier: Any, result: Any) -> None:
    import shiguan_paths as paths
    publication = "rename" if os.name == "nt" else "link"
    real_publish = getattr(os, publication)

    def simultaneous_publish(source, destination, **kwargs):
        barrier.wait(10)  # Both complete candidates exist before either commit.
        return real_publish(source, destination, **kwargs)

    with patch.object(os, publication, simultaneous_publish):
        created = paths._create_text_exclusive(Path(target), payload)
    result.put({"created": created, "payload": payload})


def check_seed_publication(root: Path) -> dict[str, object]:
    import court_file_lock as locking
    import shiguan_paths as paths

    root.mkdir()
    context = multiprocessing.get_context("spawn")
    windows = {}
    for window in ("write", "commit", "warm"):
        shared = root / window
        config = shared / "references/obsidian-sync/config.json"
        env = {"COURT_SHARED_SHIGUAN_ROOT": str(shared), "COURT_DISABLE_AGENT_PRESENCE": "1"}
        if window == "warm":
            with patch.dict(os.environ, env):
                paths.ensure_shared_seed()
        reached, release, result = context.Event(), context.Event(), context.Queue()
        first = context.Process(target=_seed_worker,
            args=(str(shared), window, reached, release, context.Queue()))
        second = context.Process(target=_seed_worker,
            args=(str(shared), "reader", context.Event(), context.Event(), result))
        first.start()
        try:
            assert reached.wait(10), f"real seed {window} window not reached"
            if window != "warm":
                # A completed candidate must not make an unfinished final name visible.
                final_visible_before_commit = config.exists()
            second.start()
            observed = result.get(timeout=10)
        finally:
            release.set()
            join_processes([p for p in (first, second) if p.pid is not None], timeout=20)
        assert first.exitcode == second.exitcode == 0, (first.exitcode, second.exitcode)
        assert observed["valid_json"], (window, observed)
        assert observed["valid_graph"] and observed["valid_index_rows"] == 0, (window, observed)
        if window != "warm":
            assert not final_visible_before_commit, f"seed final visible during {window}"
        assert isinstance(json.loads(config.read_bytes()), dict)
        windows[window] = observed

    # Two independent complete, different UTF-8 payloads compete for one name.
    target, results = root / "winner.txt", context.Queue()
    barrier = context.Barrier(2)
    payloads = ["赢家甲\n完整载荷一\n", "赢家乙\n完整载荷二\n"]
    workers = [context.Process(target=_seed_winner, args=(str(target), text, barrier, results))
               for text in payloads]
    for child in workers:
        child.start()
    try:
        outcomes = [results.get(timeout=15) for _ in workers]
    finally:
        join_processes(workers, timeout=20)
    assert all(child.exitcode == 0 for child in workers)
    winners = [entry for entry in outcomes if entry["created"]]
    assert len(winners) == 1, outcomes
    assert target.read_bytes() == winners[0]["payload"].encode("utf-8")
    assert not list(root.glob(".winner.txt.*.tmp"))

    # A warm ensure still visits all 18 seeds but opens no candidate or fsync.
    shared = root / "preserved"
    with patch.dict(os.environ, {"COURT_SHARED_SHIGUAN_ROOT": str(shared),
                                "COURT_DISABLE_AGENT_PRESENCE": "1"}):
        refs = paths.ensure_shared_seed()
        config = refs / "obsidian-sync/config.json"
        value = json.loads(config.read_bytes())
        for key in ("service_daemon_script", "service_ensure_script", "filesystem_sync_script"):
            value[key] = "manual-preserved"
        preserved = {config: (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\r\n").encode(),
                     refs / "shiguan-index.jsonl": b'{"manual":true}\r\n',
                     refs / "shiguan-knowledge-graph.json": b'{"manual_graph":true}\r\n',
                     refs / "README.md": "# 人工内容\r\n".encode("utf-8")}
        for path, raw in preserved.items():
            path.write_bytes(raw)
        with patch.object(paths, "_create_text_exclusive", wraps=paths._create_text_exclusive) as creates, \
                patch.object(locking.tempfile, "mkstemp", side_effect=AssertionError("warm seed made candidate")), \
                patch.object(locking.os, "fsync", side_effect=AssertionError("warm seed fsync")):
            # Avoid the unrelated lock-file initialization fsync: it already exists.
            paths.ensure_shared_seed()
        assert creates.call_count == 18, creates.call_count
        assert all(path.read_bytes() == raw for path, raw in preserved.items())

        lock = refs / "court-runtime/shiguan-write.lock"
        for shared_mode in (False, True):
            with file_lock(lock, shared=shared_mode):
                paths.ensure_shared_seed()  # EX->SH and SH->SH remain legal.

    # Every precommit exception leaves the final absent and cleans only its candidate.
    target = root / "retry.txt"
    foreign = root / ".retry.txt.foreign.tmp"
    foreign.write_bytes(b"foreign candidate")
    real_fdopen = os.fdopen

    class FailedWriter:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return self.handle.__exit__(*args)
        def write(self, data):
            self.handle.write(data[:1])
            raise OSError("isolated candidate write failure")

    failures = (("write", patch.object(locking.os, "fdopen",
                  side_effect=lambda fd, *a, **kw: FailedWriter(real_fdopen(fd, *a, **kw)))),
                ("fsync", patch.object(locking.os, "fsync", side_effect=OSError("isolated fsync failure"))),
                ("publication", patch.object(locking.os, "rename" if os.name == "nt" else "link",
                                             side_effect=PermissionError("isolated publication denial"))))
    for label, fault in failures:
        with fault:
            try:
                paths._create_text_exclusive(target, "完整重试\n")
            except OSError as exc:
                assert "isolated" in str(exc), (label, exc)
            else:
                raise AssertionError(f"{label} failure was swallowed")
        assert not target.exists()
        assert list(root.glob(".retry.txt.*.tmp")) == [foreign]
        assert paths._create_text_exclusive(target, "完整重试\n") is True
        assert target.read_bytes() == "完整重试\n".encode("utf-8")
        target.unlink()
    assert foreign.read_bytes() == b"foreign candidate"
    with patch.object(locking.os, "rename" if os.name == "nt" else "link",
                      side_effect=OSError(errno.ENOTSUP, "isolated unsupported publication")):
        try:
            paths._create_text_exclusive(target, "unpublished")
        except OSError as exc:
            assert exc.errno == errno.ENOTSUP
        else:
            raise AssertionError("unsupported publication was swallowed")
    assert not target.exists()

    # An error after publication cannot roll back a complete, already visible file.
    with patch.object(locking, "fsync_parent_directory", side_effect=OSError("isolated postcommit failure")):
        try:
            paths._create_text_exclusive(target, "完整发布\r\n保留换行\r末行\n")
        except OSError:
            pass
        else:
            raise AssertionError("postcommit error was swallowed")
    assert target.read_bytes() == "完整发布\r\n保留换行\r末行\n".encode("utf-8")
    target.unlink()

    # Crash after candidate fsync, before atomic name publication; retry is safe.
    shared = root / "crashed"
    reached, release, result = context.Event(), context.Event(), context.Queue()
    crashed = context.Process(target=_seed_worker,
        args=(str(shared), "exit", reached, release, result))
    crashed.start()
    try:
        assert reached.wait(10)
    finally:
        join_processes([crashed], timeout=15)
    assert crashed.exitcode == 23, crashed.exitcode
    assert not (shared / "references/obsidian-sync/config.json").exists()
    with patch.dict(os.environ, {"COURT_SHARED_SHIGUAN_ROOT": str(shared),
                                "COURT_DISABLE_AGENT_PRESENCE": "1"}):
        refs = paths.ensure_shared_seed()
    assert isinstance(json.loads((refs / "obsidian-sync/config.json").read_bytes()), dict)

    # Default API remains None + replacement; no-clobber never calls replace.
    assert locking.atomic_write_bytes(target, b"old") is None
    assert locking.atomic_write_bytes(target, b"new") is None
    assert target.read_bytes() == b"new"
    with patch.object(locking.os, "replace", side_effect=AssertionError("no-clobber used replace")):
        try:
            locking.atomic_write_bytes(target, b"loser", no_clobber=True)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing target was not rejected")
    assert target.read_bytes() == b"new"
    # EEXIST happens after the candidate's file object closes. Reuse that raw
    # descriptor for another file before cleanup; cleanup must not close it.
    publication = "rename" if os.name == "nt" else "link"
    real_publish = getattr(os, publication)
    candidate_fds, reused_fds = [], []
    def tracked_fdopen(fd, *args, **kwargs):
        candidate_fds.append(fd)
        return real_fdopen(fd, *args, **kwargs)
    def occupied_publish(*args, **kwargs):
        try:
            return real_publish(*args, **kwargs)
        except FileExistsError:
            reused_fds.append(os.open(foreign, os.O_RDONLY))
            raise
    try:
        with patch.object(locking.os, "fdopen", tracked_fdopen), \
                patch.object(locking.os, publication, occupied_publish):
            try:
                locking.atomic_write_bytes(target, b"loser", no_clobber=True)
            except FileExistsError:
                pass
            else:
                raise AssertionError("existing target was not rejected")
        assert reused_fds == candidate_fds, "fixture did not reuse the closed candidate descriptor"
        assert os.read(reused_fds[0], 100) == b"foreign candidate", "cleanup closed another file's descriptor"
    finally:
        for fd in reused_fds:
            os.close(fd)
    return {"evidence_level": "ISOLATED_REAL_PROCESSES", "windows": windows,
            "complete_payload_winners": 1, "warm_existing_seed_calls": 18,
            "warm_candidates_and_fsync": 0, "manual_bytes_preserved": True,
            "write_fsync_publication_errors_propagate_and_retry": True,
            "publication_primitive": "windows_rename" if os.name == "nt" else "posix_link",
            "unsupported_publication_error_preserved": True, "closed_descriptor_reuse_safe": True,
            "postcommit_error_preserves_final": True, "utf8_newline_bytes_preserved": True,
            "precommit_crash_final_absent_and_retry": True, "default_replace_none": True,
            "shared_reentry_preserved": True}


def _graph_worker(index: str, output: str, lock: str, older: bool,
                  reached: Any, release: Any, finished: Any) -> None:
    from commands import build_shiguan_knowledge_graph as graph
    real_build = graph.build_graph

    def scheduled(rows):
        if older:
            reached.set()
            if not release.wait(15):
                raise TimeoutError("old graph snapshot was not released")
        return real_build(rows)

    with patch.object(graph, "index_path", return_value=Path(index)), \
            patch.object(graph, "graph_path", return_value=Path(output)), \
            patch.object(graph, "shiguan_write_lock_path", return_value=Path(lock), create=True), \
            patch.object(graph, "build_graph", side_effect=scheduled):
        if older:
            graph.build_and_write()
        else:
            reached.set()
            with file_lock(Path(lock), timeout=10):
                rows = [{"id": "older", "topic": "older"}, {"id": "newer", "topic": "newer"}]
                atomic_write_text(Path(index), "".join(json.dumps(row) + "\n" for row in rows))
                graph.build_and_write()
        finished.set()


def check_graph_transaction(root: Path) -> dict[str, object]:
    root.mkdir()
    index, output, lock = root / "index.jsonl", root / "graph.json", root / "write.lock"
    atomic_write_text(index, json.dumps({"id": "older", "topic": "older"}) + "\n")
    context = multiprocessing.get_context("spawn")
    loaded, release, old_done = context.Event(), context.Event(), context.Event()
    attempted, unused, new_done = context.Event(), context.Event(), context.Event()
    older = context.Process(target=_graph_worker,
        args=(str(index), str(output), str(lock), True, loaded, release, old_done))
    newer = context.Process(target=_graph_worker,
        args=(str(index), str(output), str(lock), False, attempted, unused, new_done))
    older.start()
    try:
        assert loaded.wait(10), "old graph never read its index"
        newer.start()
        assert attempted.wait(10), "updater never attempted its transaction"
        updated_before_release = new_done.wait(0.3)
    finally:
        release.set()
        join_processes([p for p in (older, newer) if p.pid is not None], timeout=20)
    assert older.exitcode == newer.exitcode == 0, (older.exitcode, newer.exitcode)
    graph = json.loads(output.read_text(encoding="utf-8"))
    assert len(index.read_text(encoding="utf-8").splitlines()) == 2
    assert graph["counts"]["entries"] == 2, graph["counts"]
    # enrich_entry derives record_uid; retain the two original content topics.
    assert {node["topic"] for node in graph["nodes"] if node["kind"] == "record"} == {"older", "newer"}
    assert not updated_before_release, "index writer bypassed the old builder transaction"
    return {"independent_processes": 2, "final_entries": 2, "updater_waited": True}


class _FakeTensor:
    """Tiny deterministic matrix for ISOLATED engine scheduling, never model evidence."""
    def __init__(self, values):
        self.values = values

    @property
    def shape(self):
        return (len(self.values), len(self.values[0]) if self.values else 0)

    @property
    def T(self):
        return _FakeTensor([list(row) for row in zip(*self.values)])

    def __matmul__(self, other):
        return _FakeTensor([[sum(a * b for a, b in zip(row, col))
                             for col in zip(*other.values)] for row in self.values])

    def __getitem__(self, index):
        return self.values[index]


def _fake_save(value, target):
    data = pickle.dumps(value)
    if hasattr(target, "write"):
        target.write(data)
    else:
        # Deliberate slow serialization exposes a direct-to-live-cache write.
        with Path(target).open("wb") as handle:
            handle.write(data[:len(data) // 2])
            handle.flush()
            time.sleep(0.03)
            handle.write(data[len(data) // 2:])


def _fake_load(target, **_kwargs):
    with Path(target).open("rb") as handle:
        return pickle.load(handle)


@contextmanager
def _fake_recall_module():
    torch = types.ModuleType("torch")
    torch.device = lambda value: SimpleNamespace(type=value)
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    torch.Tensor, torch.save, torch.load = _FakeTensor, _fake_save, _fake_load
    nn, functional = types.ModuleType("torch.nn"), types.ModuleType("torch.nn.functional")
    torch.nn, nn.functional = nn, functional
    transformers = types.ModuleType("transformers")
    transformers.AutoTokenizer = object
    path = Path(__file__).resolve().parents[2] / "training/laya-shiguan/service/shiguan_recall.py"
    spec = importlib.util.spec_from_file_location("isolated_shiguan_recall", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"torch": torch, "torch.nn": nn, "torch.nn.functional": functional,
                                 "transformers": transformers, spec.name: module}):
        spec.loader.exec_module(module)
        yield module


def _fake_embed(texts):
    return _FakeTensor([[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts])


def _live_rows(count: int) -> list[dict]:
    return [{"court_code": f"isolated-{i}", "topic": "alpha" if i == 0 else f"beta-{i}",
             "summary": "alpha" if i == 0 else "beta", "memory_decision": "SKIP"}
            for i in range(count)]


def _write_live(path: Path, count: int) -> None:
    atomic_write_text(path, "".join(json.dumps(row) + "\n" for row in _live_rows(count)))


def check_recall_snapshots(root: Path) -> dict[str, object]:
    root.mkdir()
    references = root / "override/references"
    live, cache = references / "shiguan-index.jsonl", root / "cache/index.pt"
    _write_live(live, 2)
    with patch.dict(os.environ, {"SHIGUAN_REFERENCES_ROOT": str(references),
            "COURT_SHARED_SHIGUAN_ROOT": str(root / "different-global"),
            "SHIGUAN_RECALL_CACHE": str(cache)}), _fake_recall_module() as recall:
        engine = recall.ShiguanRecall(device="cpu")
        entered, second_build, release = threading.Event(), threading.Event(), threading.Event()
        calls, calls_lock = [], threading.Lock()

        def cold_embed(texts):
            if len(texts) == 2:
                with calls_lock:
                    calls.append(1)
                    if len(calls) == 2:
                        second_build.set()
                entered.set()
                assert release.wait(5)
            return _fake_embed(texts)

        engine._embed = cold_embed
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(engine.recall, "query-alpha", 1)
            assert entered.wait(3)
            second = pool.submit(engine.recall, "query-beta", 1)
            second_build.wait(0.2)
            release.set()
            results = [first.result(timeout=5), second.result(timeout=5)]
        assert len(calls) == 1, f"duplicate cold builds: {len(calls)}"
        assert [result["matches"][0]["court_code"] for result in results] == ["isolated-0", "isolated-1"]

        # A failed build publishes nothing and releases single-flight for a retry.
        retry = recall.ShiguanRecall(device="cpu")
        def failed_embed(_texts):
            raise RuntimeError("isolated embedding failure")
        retry._embed = failed_embed
        try:
            retry.build(force=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError("failed embedding unexpectedly succeeded")
        assert retry.rows == [] and retry.vecs is None, "failed build leaked partial rows"
        retry._embed = _fake_embed
        retry.build(force=True)
        assert retry.stats()["indexed_records"] == 2

        # Capture a recall before its query embedding; publish a new generation
        # while it is delayed. The response must retain its own old generation.
        query_entered, query_release = threading.Event(), threading.Event()
        def scheduled_embed(texts):
            if texts == ["query-alpha"]:
                query_entered.set()
                assert query_release.wait(5)
            return _fake_embed(texts)
        engine._embed = scheduled_embed
        with ThreadPoolExecutor(max_workers=1) as pool:
            old_query = pool.submit(engine.recall, "query-alpha", 1)
            assert query_entered.wait(3)
            _write_live(live, 3)
            engine.build(force=True)
            query_release.set()
            old_result = old_query.result(timeout=5)
        assert old_result["stats"]["indexed_records"] == 2, old_result
        assert engine.stats()["indexed_records"] == 3

        # Force builds serialize, and stats/recall retain the published snapshot.
        active, max_active = 0, 0
        force_entered, force_release = threading.Event(), threading.Event()
        def force_embed(texts):
            nonlocal active, max_active
            if len(texts) == 4:
                with calls_lock:
                    active += 1
                    max_active = max(max_active, active)
                force_entered.set()
                assert force_release.wait(5)
                with calls_lock:
                    active -= 1
            return _fake_embed(texts)
        engine._embed = force_embed
        _write_live(live, 4)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(engine.build, True)
            assert force_entered.wait(3)
            second = pool.submit(engine.build, True)
            time.sleep(0.1)
            assert engine.stats()["indexed_records"] == 3
            assert engine.recall("query-beta", 1)["stats"]["indexed_records"] == 3
            force_release.set()
            first.result(timeout=5)
            second.result(timeout=5)
        assert max_active == 1, max_active
        assert engine.stats()["indexed_records"] == 4 and engine.vecs.shape[0] == 4

        # A writer may not slip between the actual override index rows and stamp.
        _write_live(live, 2)
        old_size = live.stat().st_size
        rows_read, writer_attempted, writer_done = threading.Event(), threading.Event(), threading.Event()
        real_rows = recall.rows_from_live_index
        def scheduled_rows(path):
            rows = real_rows(path)
            rows_read.set()
            assert writer_attempted.wait(3)
            writer_done.wait(0.2)
            return rows
        def update_live():
            assert rows_read.wait(3)
            writer_attempted.set()
            with file_lock(references / "court-runtime/shiguan-write.lock"):
                _write_live(live, 3)
            writer_done.set()
        engine._embed = _fake_embed
        with patch.object(recall, "rows_from_live_index", side_effect=scheduled_rows), \
                ThreadPoolExecutor(max_workers=1) as pool:
            writer = pool.submit(update_live)
            engine.build(force=True)
            writer.result(timeout=5)
        cached = _fake_load(cache)
        assert cached["stamp"]["size"] == old_size, "stamp came from a different source snapshot"
        assert engine.stats()["index_source_path"] == str(live)
        assert engine.stats()["indexed_records"] == 2

        # A slow embedding must release the authoritative Shiguan lock first.
        def unlocked_embed(texts):
            if len(texts) > 1:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    def acquire():
                        with file_lock(references / "court-runtime/shiguan-write.lock", timeout=0.3):
                            return True
                    assert pool.submit(acquire).result(timeout=1)
            return _fake_embed(texts)
        engine._embed = unlocked_embed
        engine.build(force=True)
        with patch.object(recall, "atomic_write_bytes", side_effect=PermissionError("isolated cache denial"),
                          create=True):
            engine.build(force=True)
        assert engine.stats()["index_cache"].startswith("unavailable:")
        assert engine.recall("query-beta", 1)["matches"]
        assert engine.recall("主题：beta-1", 1, same_top=True)["matches"][0]["court_code"] == "isolated-1"
        fresh = recall.ShiguanRecall(device="cpu")
        fresh._embed = failed_embed
        fresh.build()  # A matching complete cache needs no embedding.
        assert fresh.stats()["indexed_records"] == 3
        previous = fresh.stats()
        try:
            fresh.build(force=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError("forced failure unexpectedly succeeded")
        assert fresh.stats() == previous, "failed rebuild erased a published snapshot"
        corpus = root / "corpus.jsonl"
        corpus.write_text(json.dumps({"source": "index", "id": "development", "state": "alpha",
            "group": "alpha", "gold": {}}) + "\n", encoding="utf-8")
        with patch.object(recall, "live_index_path", return_value=None), patch.object(recall, "CORPUS", corpus):
            fresh._embed = _fake_embed
            fresh.build(force=True)
        assert fresh.stats()["index_source"] == "local_corpus" and len(fresh.rows) == 1
    return {"evidence_level": "ISOLATED_FAKE_EMBEDDING", "cold_builds": 1,
            "retry_after_failure": True, "force_serialized": True, "query_snapshot": True,
            "actual_source_rows_stamp_lock": True, "embedding_releases_shiguan_lock": True,
            "cache_write_failure_usable": True}


def _recall_cache_worker(root: str, cache: str, start: Any) -> None:
    with patch.dict(os.environ, {"SHIGUAN_REFERENCES_ROOT": root, "SHIGUAN_RECALL_CACHE": cache}), \
            _fake_recall_module() as recall:
        engine = recall.ShiguanRecall(device="cpu")
        engine._embed = _fake_embed
        assert start.wait(10)
        for _ in range(4):
            engine.build(force=True)


def check_recall_model_initialization(root: Path) -> dict[str, object]:
    root.mkdir()
    live, cache = root / "references/shiguan-index.jsonl", root / "cache.pt"
    _write_live(live, 2)

    class MemoryModelPath:
        def __truediv__(self, _name):
            return self

        def read_text(self, **_kwargs):
            return "{}"

    entered, duplicate, release = threading.Event(), threading.Event(), threading.Event()
    calls, failure = [], []
    calls_lock = threading.Lock()

    class FakeModel:
        def load_state_dict(self, *_args, **_kwargs):
            pass

        def to(self, *_args):
            return self

        def eval(self):
            if failure:
                failure.pop()
                raise RuntimeError("isolated model initialization failure")
            return self

    def tokenizer(*_args, **_kwargs):
        with calls_lock:
            calls.append("tokenizer")
            if calls.count("tokenizer") == 2:
                duplicate.set()
        entered.set()
        assert release.wait(4)
        return object()

    def factory(*_args, **_kwargs):
        with calls_lock:
            calls.append("model")
        return FakeModel()

    modules = {name: types.ModuleType(name)
               for name in ("safetensors", "safetensors.torch", "laya", "laya.common")}
    modules["safetensors.torch"].load_file = lambda *_args: {}
    modules["laya.common"].build_model = factory
    with patch.dict(os.environ, {"SHIGUAN_REFERENCES_ROOT": str(root),
                                "SHIGUAN_RECALL_CACHE": str(cache)}), \
            _fake_recall_module() as recall, patch.dict(sys.modules, modules), \
            patch.object(recall, "MODEL_DIR", MemoryModelPath()), \
            patch.object(recall, "AutoTokenizer", SimpleNamespace(from_pretrained=tokenizer)):
        engine = recall.ShiguanRecall(device="cpu")
        engine._embed = _fake_embed
        engine.build(force=True)
        warm = recall.ShiguanRecall(device="cpu")
        warm.build()
        assert warm._model is None and warm._tok is None and warm.vecs is not None

        def query_embed(texts):
            # Only numerical embedding is fake. The real recall, cache build and
            # lazy initializer still execute with fake tokenizer/model factories.
            warm._ensure_model()
            assert warm._model is not None and warm._tok is not None
            return _fake_embed(texts)
        warm._embed = query_embed
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(warm.recall, "query-alpha", 1)
            assert entered.wait(3)
            second = pool.submit(warm.recall, "query-beta", 1)
            duplicate.wait(0.2)
            release.set()
            results = [first.result(timeout=5), second.result(timeout=5)]
        assert calls.count("model") == calls.count("tokenizer") == 1, calls
        assert [result["matches"][0]["court_code"] for result in results] == ["isolated-0", "isolated-1"]

        retry = recall.ShiguanRecall(device="cpu")
        retry.build()  # Another warm-cache engine, with no initialized model.
        def retry_embed(texts):
            retry._ensure_model()
            return _fake_embed(texts)
        retry._embed = retry_embed
        failure.append(True)
        try:
            retry.recall("query-alpha", 1)
        except RuntimeError:
            pass
        else:
            raise AssertionError("failed model initialization unexpectedly succeeded")
        assert retry._model is None and retry._tok is None, "initializer leaked a half-published tokenizer"
        assert retry.recall("query-beta", 1)["matches"][0]["court_code"] == "isolated-1"
        assert retry._model is not None and retry._tok is not None

        # A cold build calls embedding -> real _ensure_model while holding its
        # build lock. A non-reentrant shared lock must fail this bounded check.
        cold = recall.ShiguanRecall(device="cpu")
        def cold_embed(texts):
            cold._ensure_model()
            return _fake_embed(texts)
        cold._embed = cold_embed
        completed, errors = threading.Event(), []
        def cold_build():
            try:
                cold.build(force=True)
            except Exception as exc:
                errors.append(exc)
            finally:
                completed.set()
        worker = threading.Thread(target=cold_build, daemon=True)
        worker.start()
        assert completed.wait(3), "cold build nested model initialization deadlocked"
        worker.join(1)
        assert not errors, errors
        assert cold.vecs.shape[0] == 2 and cold._model is not None and cold._tok is not None
    return {"evidence_level": "ISOLATED_FAKE_FACTORIES_AND_EMBEDDING",
            "warm_cache_model_factories": 1, "warm_cache_tokenizer_factories": 1,
            "failed_initialization_publishes_nothing": True, "failed_initialization_retry": True,
            "cold_build_nested_initialization": True}


def _probe_cache_read(path: Path) -> dict[str, object] | None:
    """Separate Windows open denial from reading/decoding a published cache."""
    try:
        handle = path.open("rb")
    except PermissionError as exc:
        if os.name != "nt":
            raise
        return {"errno": exc.errno, "winerror": getattr(exc, "winerror", None)}
    with handle:
        pickle.load(handle)  # Every decoding error, including PermissionError, propagates.
    return None


def check_recall_cache_and_import(root: Path) -> dict[str, object]:
    root.mkdir()
    live = root / "references/shiguan-index.jsonl"
    cache = root / "cache.pt"
    _write_live(live, 2)
    cache.write_bytes(pickle.dumps({"complete": True}))
    # Bounded negative controls: only Windows PermissionError while opening is
    # a denial; no read/decode failure may be relabeled as a busy reader.
    negative_controls = {}
    for stage, error in (("open_oserror", OSError(errno.EIO, "isolated cache open failure")),
                         ("decode_eof", EOFError("isolated truncated cache")),
                         ("decode_pickle", pickle.UnpicklingError("isolated corrupt cache")),
                         ("decode_oserror", OSError(errno.EIO, "isolated cache read failure")),
                         ("decode_permission", PermissionError(errno.EACCES, "isolated decode denial"))):
        fault = (patch.object(Path, "open", side_effect=error) if stage.startswith("open_")
                 else patch.object(pickle, "load", side_effect=error))
        with fault:
            try:
                _probe_cache_read(cache)
            except type(error) as exc:
                assert exc is error
            else:
                raise AssertionError(f"{stage} was misclassified as an open denial")
        negative_controls[stage] = True
    open_denial = PermissionError(errno.EACCES, "isolated open denial")
    with patch.object(Path, "open", side_effect=open_denial):
        if os.name == "nt":
            assert _probe_cache_read(cache) == {"errno": errno.EACCES, "winerror": None}
        else:
            try:
                _probe_cache_read(cache)
            except PermissionError as exc:
                assert exc is open_denial
            else:
                raise AssertionError("non-Windows open denial was swallowed")
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    workers = [context.Process(target=_recall_cache_worker, args=(str(root), str(cache), start))
               for _ in range(2)]
    for child in workers:
        child.start()
    start.set()
    attempts, complete_reads = 0, 0
    read_denials, read_errors = [], []
    deadline = time.monotonic() + 20
    try:
        while any(child.is_alive() for child in workers) and time.monotonic() < deadline:
            attempts += 1
            try:
                denial = _probe_cache_read(cache)
            except (OSError, EOFError, pickle.UnpicklingError) as exc:
                read_errors.append({"type": type(exc).__name__, "errno": getattr(exc, "errno", None),
                                    "winerror": getattr(exc, "winerror", None), "error": str(exc)})
            else:
                if denial is None:
                    complete_reads += 1
                else:
                    read_denials.append(denial)
            time.sleep(0.002)
    finally:
        join_processes(workers, timeout=10)
    assert all(child.exitcode == 0 for child in workers), [child.exitcode for child in workers]
    assert complete_reads > 0 and not read_errors, {"attempts": attempts, "complete_reads": complete_reads,
                                                   "read_denials": read_denials, "errors": read_errors[:8]}
    assert _fake_load(cache)["vecs"].shape[0] == 2
    assert not list(root.glob(".cache.pt.*.tmp"))
    service = Path(__file__).resolve().parents[2] / "training/laya-shiguan/service"
    # The independent entry points add only service/, never scripts/. Python -I
    # removes ambient cwd/PYTHONPATH so the checker cannot hide a missing helper.
    script = """
import sys, types
torch, nn, functional = (types.ModuleType(name) for name in ('torch', 'torch.nn', 'torch.nn.functional'))
torch.nn, nn.functional = nn, functional
transformers = types.ModuleType('transformers')
transformers.AutoTokenizer = object
sys.modules.update({'torch': torch, 'torch.nn': nn, 'torch.nn.functional': functional, 'transformers': transformers})
sys.path.insert(0, sys.argv[1])
import shiguan_recall
from pathlib import Path
assert Path(sys.modules['court_file_lock'].__file__).resolve() == Path(sys.argv[2]).resolve()
print('ISOLATED_SERVICE_IMPORT_OK')
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(service),
                             str(Path(__file__).resolve().parents[1] / "court_file_lock.py")],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "ISOLATED_SERVICE_IMPORT_OK" in result.stdout
    return {"evidence_level": "ISOLATED_FAKE_DEPENDENCIES", "cache_processes": 2,
            "read_attempts": attempts, "complete_reads": complete_reads,
            "read_denials": read_denials, "partial_reads": len(read_errors), "read_errors": read_errors,
            "negative_controls": negative_controls, "service_only_import": True}


def _sync_result_probe(worker_result: object) -> tuple[dict[str, object], str, str]:
    import archive_checkpoint

    def fake_worker(argv: list[str], **_: object) -> SimpleNamespace:
        result_path = Path(argv[argv.index("--result-json") + 1])
        result_path.write_text(json.dumps(worker_result), encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(archive_checkpoint.subprocess, "run", fake_worker):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returned = archive_checkpoint.realtime_obsidian_sync_best_effort(timeout=5)
    return returned, stdout.getvalue(), stderr.getvalue()


def check_sync_worker_result_ok_contract() -> None:
    invalid_results: dict[str, object] = {
        "missing": {},
        "wrong_type": {"ok": "true"},
        "false": {
            "ok": False,
            "transaction_state": "committed_unverified_source",
        },
        "wrong_top_level": [],
    }
    for label, worker_result in invalid_results.items():
        returned, stdout, stderr = _sync_result_probe(worker_result)
        assert returned.get("status") == "warning", (label, returned)
        assert "SHIGUAN_AUTOSYNC_OK" not in stdout, (label, stdout)
        assert "SHIGUAN_OBSIDIAN_SYNC_WARNING" in stderr, (label, stderr)
    successful_result = {
        "ok": True,
        "source_ref": "record://checkpoint-1",
        "source_revision": "r1",
        "producer_transaction_id": "producer-tx-1",
        "sync_transaction_id": "sync-tx-1",
        "transaction_state": "committed",
    }
    returned, stdout, stderr = _sync_result_probe(successful_result)
    assert returned == {"status": "synced", "result": successful_result}
    assert "SHIGUAN_AUTOSYNC_OK" in stdout
    assert stderr == ""


def checkpoint_worker(
    start_event: Any,
    shared_root: str,
    runtime_root: str,
    writer_id: int,
) -> None:
    os.environ["COURT_SHARED_SHIGUAN_ROOT"] = shared_root
    os.environ["COURT_RUNTIME_ROOT"] = runtime_root
    os.environ["COURT_DISABLE_AGENT_PRESENCE"] = "1"
    if not start_event.wait(20):
        raise TimeoutError("checkpoint concurrency start barrier timed out")

    from archive_checkpoint import append_checkpoint

    args = argparse.Namespace(
        topic="concurrency-integrity",
        phase=f"worker-{writer_id}",
        status="PASS",
        summary=f"concurrent checkpoint {writer_id}",
        evidence=f"writer={writer_id}",
        next="none",
        memory_decision="SKIP",
        memory_content="none",
        memory_reason="isolated concurrency self-test",
        risk_level="D",
        knowledge_value="C",
        priority_level="C",
        keywords="concurrency,integrity",
        key_actions=f"writer:{writer_id}",
        source_agent="generic-cli",
        full_record="",
        full_record_file=None,
        refresh_mode="async",
        no_refresh=False,
        refresh_tree=False,
        sync=False,
        sync_timeout=5,
        lock_timeout=CHECKPOINT_LOCK_TIMEOUT_SECONDS,
    )
    append_checkpoint(args)


def crash_lock_worker(acquired_event: Any, lock_path: str) -> None:
    with file_lock(Path(lock_path), timeout=5.0):
        acquired_event.set()
        os._exit(17)


def join_processes(processes: list[multiprocessing.Process], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    for process in processes:
        process.join(max(0.0, min(60.0, deadline - time.monotonic())))
    alive = [process for process in processes if process.is_alive()]
    for process in alive:
        process.terminate()
    for process in alive:
        process.join(5)
    if alive:
        raise AssertionError(f"workers timed out: {[process.pid for process in alive]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targeted-only", action="store_true",
                        help="run the bounded graph/recall regressions before the legacy 32-writer suite")
    parser.add_argument("--seed-only", action="store_true", help="run only the direct seed publication regressions")
    args = parser.parse_args()
    probes: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="shiguan-targeted-concurrency-") as raw:
        root = Path(raw)
        selected = (("seed_publication", check_seed_publication),) if args.seed_only else (
                            ("seed_publication", check_seed_publication),
                            ("graph_transaction", check_graph_transaction),
                            ("recall_snapshots", check_recall_snapshots),
                            ("recall_model_initialization", check_recall_model_initialization),
                            ("recall_cache_import", check_recall_cache_and_import))
        for name, probe in selected:
            try:
                probes[name] = {"ok": True, "evidence": probe(root / name)}
            except Exception as exc:
                probes[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print("SHIGUAN_TARGETED_CONCURRENCY " + json.dumps(probes, sort_keys=True), flush=True)
    if not all(result["ok"] for result in probes.values()):
        return 1
    if args.targeted_only or args.seed_only:
        return 0
    check_sync_worker_result_ok_contract()
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="court-shiguan-concurrency-") as temp_dir:
        temp_root = Path(temp_dir)
        shared_root = temp_root / "shared"
        runtime_root = temp_root / "runtime"

        atomic_target = temp_root / "atomic" / "request.json"
        with ThreadPoolExecutor(max_workers=ATOMIC_WRITERS) as executor:
            futures = [
                executor.submit(
                    atomic_write_text,
                    atomic_target,
                    json.dumps({"state": "complete", "writer": writer_id}, sort_keys=True) + "\n",
                )
                for writer_id in range(ATOMIC_WRITERS)
            ]
            for future in futures:
                future.result(timeout=10)
        atomic_value = json.loads(atomic_target.read_text(encoding="utf-8"))
        assert atomic_value["state"] == "complete"
        assert int(atomic_value["writer"]) in range(ATOMIC_WRITERS)
        assert not list(atomic_target.parent.glob(f".{atomic_target.name}.*.tmp"))

        crash_lock = temp_root / "crash-release.lock"
        acquired = context.Event()
        crashed = context.Process(target=crash_lock_worker, args=(acquired, str(crash_lock)))
        crashed.start()
        assert acquired.wait(15), "crash worker did not acquire the file lock"
        crashed.join(15)
        assert crashed.exitcode == 17, f"unexpected crash worker exit: {crashed.exitcode}"
        with file_lock(crash_lock, timeout=5.0):
            with file_lock(crash_lock, timeout=5.0):
                pass

        start_event = context.Event()
        workers = [
            context.Process(
                target=checkpoint_worker,
                args=(start_event, str(shared_root), str(runtime_root), writer_id),
            )
            for writer_id in range(CHECKPOINT_WRITERS)
        ]
        for worker in workers:
            worker.start()
        start_event.set()
        join_processes(workers, timeout=CHECKPOINT_JOIN_TIMEOUT_SECONDS)
        failures = [(worker.pid, worker.exitcode) for worker in workers if worker.exitcode != 0]
        assert not failures, f"checkpoint workers failed: {failures}"

        index_path = shared_root / "references" / "shiguan-index.jsonl"
        raw_lines = [line for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        entries = [json.loads(line) for line in raw_lines]
        assert len(entries) == CHECKPOINT_WRITERS
        assert len({str(entry.get("daily_sequence")) for entry in entries}) == CHECKPOINT_WRITERS
        assert len({str(entry.get("court_code")) for entry in entries}) == CHECKPOINT_WRITERS
        assert {str(entry.get("phase")) for entry in entries} == {
            f"worker-{writer_id}" for writer_id in range(CHECKPOINT_WRITERS)
        }

        archives = list((shared_root / "references" / "plan-archives").glob("plan-*-concurrency-integrity-1.md"))
        assert len(archives) == 1, f"unexpected archive files: {archives}"
        archive_text = archives[0].read_text(encoding="utf-8")
        assert archive_text.count("## Checkpoint:") == CHECKPOINT_WRITERS
        for entry in entries:
            assert f"- court_code: {entry['court_code']}" in archive_text
        from archive_checkpoint import build_archive_receipt

        receipt = build_archive_receipt(archives[0], entries[0], {})
        assert receipt["recorded_at"] == entries[0]["time"]
        assert receipt["record_ref"] == "shiguan:" + str(entries[0]["court_code"])
        refresh_request = shared_root / "references" / "obsidian-sync" / "refresh-request.json"
        refresh_value = json.loads(refresh_request.read_text(encoding="utf-8"))
        assert refresh_value["reason"] == "archive_checkpoint"
        assert refresh_value["court_code"] in {entry["court_code"] for entry in entries}
        assert not list(refresh_request.parent.glob(f".{refresh_request.name}.*.tmp"))

        os.environ["COURT_SHARED_SHIGUAN_ROOT"] = str(shared_root)
        os.environ["COURT_RUNTIME_ROOT"] = str(runtime_root)
        os.environ["COURT_DISABLE_AGENT_PRESENCE"] = "1"
        from shiguan_paths import ensure_shared_seed

        ensure_shared_seed()
        import serve_shiguan_tree as web

        web.ensure_shared_seed = lambda: shared_root / "references"
        web.refresh_tree = lambda: None

        def upsert(writer_id: int) -> dict[str, object]:
            return web.upsert_entry(
                {
                    "id": f"thread-entry-{writer_id}",
                    "topic": f"threaded upsert {writer_id}",
                    "phase": "concurrency-test",
                    "status": "PASS",
                    "summary": f"serialized web RMW {writer_id}",
                    "evidence": f"thread={writer_id}",
                    "memory_decision": "SKIP",
                    "risk_level": "D",
                    "knowledge_value": "C",
                    "priority_level": "C",
                }
            )

        with ThreadPoolExecutor(max_workers=WEB_UPSERT_THREADS) as executor:
            futures = [executor.submit(upsert, writer_id) for writer_id in range(WEB_UPSERT_THREADS)]
            web_entries = [future.result(timeout=30) for future in futures]
        assert len({str(entry.get("id")) for entry in web_entries}) == WEB_UPSERT_THREADS

        final_lines = [line for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        final_entries = [json.loads(line) for line in final_lines]
        web_ids = {
            str(entry.get("id"))
            for entry in final_entries
            if str(entry.get("id", "")).startswith("thread-entry-")
        }
        assert web_ids == {f"thread-entry-{writer_id}" for writer_id in range(WEB_UPSERT_THREADS)}
        manual_files = list((shared_root / "references" / "shiguan-tree" / "manual").glob("thread-entry-*.json"))
        assert len(manual_files) == WEB_UPSERT_THREADS

    print(
        "SHIGUAN_CONCURRENCY_SELF_TEST_OK "
        + json.dumps(
            {
                "checkpoint_writers": CHECKPOINT_WRITERS,
                "unique_sequences": CHECKPOINT_WRITERS,
                "crash_release": True,
                "atomic_replace": True,
                "atomic_replace_writers": ATOMIC_WRITERS,
                "web_upsert_threads": WEB_UPSERT_THREADS,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
