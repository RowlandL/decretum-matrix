"""Check Shiguan recall source selection: empty/invalid live index must fall back.

Regression gate for beta1.2.3-hotfix-v3 (Linux bring-up finding #2,
.scratch/linux-bringup-20261111/issues/01-linux-bringup-findings.md section 2):
- (a) a 0-byte live index file is not a data source: fall back to the local
  corpus and emit an explicit stderr warning naming the live path.
- (b) a live index whose lines all fail to parse is equally invalid: same
  fallback and warning.
- (c) a live index with at least one valid row stays authoritative, mixed
  broken/blank lines notwithstanding (current behavior preserved).
- (d) when the live index is unusable and the corpus is missing too, source
  selection stays fail-closed with an error naming both paths.

The torch/transformers dependencies of shiguan_recall are stubbed in-process
(the established pattern of check_shiguan_concurrency._fake_recall_module);
no model, GPU or real corpus is touched, so this gate is hermetic and
CI-safe.
"""

from __future__ import annotations

import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
from contextlib import contextmanager, redirect_stderr
import importlib.util
import io
import json
import os
import pickle
sys.dont_write_bytecode = True
import tempfile
import types
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


class _FakeTensor:
    """Deterministic stand-in; source selection never touches real embeddings."""

    def __init__(self, values):
        self.values = values

    @property
    def shape(self):
        return (len(self.values), 2)


def _fake_embed(texts):
    return _FakeTensor([[1.0, 0.0] for _ in texts])


@contextmanager
def _isolated_recall_module():
    torch = types.ModuleType("torch")
    torch.device = lambda value: SimpleNamespace(type=value)
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    torch.save = lambda value, target: target.write(pickle.dumps(value))
    torch.load = lambda target, **_kwargs: pickle.loads(Path(target).read_bytes())
    nn, functional = types.ModuleType("torch.nn"), types.ModuleType("torch.nn.functional")
    torch.nn, nn.functional = nn, functional
    transformers = types.ModuleType("transformers")
    transformers.AutoTokenizer = object
    path = Path(__file__).resolve().parents[2] / "training/laya-shiguan/service/shiguan_recall.py"
    spec = importlib.util.spec_from_file_location("isolated_shiguan_recall_source_fallback", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"torch": torch, "torch.nn": nn, "torch.nn.functional": functional,
                                 "transformers": transformers, spec.name: module}):
        spec.loader.exec_module(module)
        yield module


def _corpus_row() -> str:
    """rows_from_corpus 只保留 source == 'index' 的行。"""
    return json.dumps({"source": "index", "id": "corpus-row", "state": "主题：语料回退",
                       "group": "语料回退", "gold": {}}) + "\n"


def _scenario_env(root: Path) -> dict[str, str]:
    """Hermetic overrides: the real ~/.agents live index is never read."""
    return {"SHIGUAN_REFERENCES_ROOT": str(root), "SHIGUAN_RECALL_CACHE": str(root / "cache" / "recall-index.pt")}


def _check_empty_live_file(recall, root: Path) -> dict[str, Any]:
    """(a) 0 字节占位文件不得静默生效：回退语料并显式告警。"""
    root.mkdir()
    references = root / "references"
    references.mkdir()
    live = references / "shiguan-index.jsonl"
    live.write_bytes(b"")
    corpus = root / "corpus-v2.jsonl"
    corpus.write_text(_corpus_row(), encoding="utf-8")
    engine = recall.ShiguanRecall(device="cpu")
    with patch.dict(os.environ, _scenario_env(root)), \
            patch.object(recall, "CORPUS", corpus), \
            redirect_stderr(io.StringIO()) as stderr:
        source, kind = engine._source()
        assert kind == "local_corpus", f"0 字节实时索引被静默采信: {kind}"
        assert source == corpus, str(source)
        engine._embed = _fake_embed
        engine.build()
        warning = stderr.getvalue()
    stats = engine.stats()
    assert stats["index_source"] == "local_corpus", stats
    assert stats["indexed_records"] == 1, stats
    assert str(live) in warning, f"告警未注明 live 路径: {warning!r}"
    assert "回退" in warning, f"告警未注明回退原因: {warning!r}"
    return {"fallback": "local_corpus", "indexed_records": stats["indexed_records"],
            "warning_names_live_path": True}


def _check_invalid_live_lines(recall, root: Path) -> dict[str, Any]:
    """(b) 全部行解析失败（含空行）同样无效：回退语料并显式告警。"""
    root.mkdir()
    references = root / "references"
    references.mkdir()
    live = references / "shiguan-index.jsonl"
    live.write_text("{broken json\n\n   \nnot-json-at-all\n{\"truncated\":\n", encoding="utf-8")
    corpus = root / "corpus-v2.jsonl"
    corpus.write_text(_corpus_row(), encoding="utf-8")
    engine = recall.ShiguanRecall(device="cpu")
    with patch.dict(os.environ, _scenario_env(root)), \
            patch.object(recall, "CORPUS", corpus), \
            redirect_stderr(io.StringIO()) as stderr:
        source, kind = engine._source()
        assert kind == "local_corpus", f"0 有效行的实时索引被静默采信: {kind}"
        assert source == corpus, str(source)
        engine._embed = _fake_embed
        engine.build()
        warning = stderr.getvalue()
    stats = engine.stats()
    assert stats["index_source"] == "local_corpus", stats
    assert stats["indexed_records"] == 1, stats
    assert str(live) in warning, f"告警未注明 live 路径: {warning!r}"
    assert "回退" in warning, f"告警未注明回退原因: {warning!r}"
    return {"fallback": "local_corpus", "indexed_records": stats["indexed_records"],
            "warning_names_live_path": True}


def _check_valid_live_row(recall, root: Path) -> dict[str, Any]:
    """(c) ≥1 有效行即采信 live（坏行/空行混入不改变现行为），且无告警。"""
    root.mkdir()
    references = root / "references"
    references.mkdir()
    live = references / "shiguan-index.jsonl"
    live.write_text(
        "{definitely-not-json\n"
        + json.dumps({"court_code": "live-1", "topic": "live-row", "summary": "live record",
                      "memory_decision": "SKIP"}) + "\n"
        + "\n",
        encoding="utf-8")
    corpus = root / "corpus-v2.jsonl"
    corpus.write_text(_corpus_row(), encoding="utf-8")
    engine = recall.ShiguanRecall(device="cpu")
    with patch.dict(os.environ, _scenario_env(root)), \
            patch.object(recall, "CORPUS", corpus), \
            redirect_stderr(io.StringIO()) as stderr:
        source, kind = engine._source()
        assert kind == "live_shiguan_index", kind
        assert source == live, str(source)
        engine._embed = _fake_embed
        engine.build()
        warning = stderr.getvalue()
    stats = engine.stats()
    assert stats["index_source"] == "live_shiguan_index", stats
    assert stats["indexed_records"] == 1, stats
    assert warning.strip() == "", f"有效 live 索引不应产生告警: {warning!r}"
    return {"source": "live_shiguan_index", "indexed_records": stats["indexed_records"]}


def _check_missing_corpus_fails_closed(recall, root: Path) -> dict[str, Any]:
    """(d) live 与语料都不可用时保持 fail-closed，错误注明两条路径。"""
    root.mkdir()
    references = root / "references"
    references.mkdir()
    live = references / "shiguan-index.jsonl"
    live.write_bytes(b"")
    missing = root / "missing-corpus-v2.jsonl"
    engine = recall.ShiguanRecall(device="cpu")
    with patch.dict(os.environ, _scenario_env(root)), \
            patch.object(recall, "CORPUS", missing), \
            redirect_stderr(io.StringIO()) as stderr:
        try:
            engine._source()
        except FileNotFoundError as exc:
            message = str(exc)
            assert str(live) in message, f"错误未注明 live 路径: {message!r}"
            assert str(missing) in message, f"错误未注明语料路径: {message!r}"
            warning = stderr.getvalue()
            assert str(live) in warning and "回退" in warning, f"fail-closed 前应显式告警: {warning!r}"
        else:
            raise AssertionError("live 与语料都不可用时未保持 fail-closed")
    return {"fail_closed": True, "warning_before_failure": True}


def evaluate() -> dict[str, Any]:
    failures: list[str] = []
    metrics: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="shiguan-recall-source-fallback-") as raw:
        root = Path(raw)
        with _isolated_recall_module() as recall:
            scenarios = (
                ("empty_live_file_falls_back", _check_empty_live_file),
                ("invalid_live_lines_fall_back", _check_invalid_live_lines),
                ("valid_live_row_stays_live", _check_valid_live_row),
                ("missing_corpus_fails_closed", _check_missing_corpus_fails_closed),
            )
            for name, probe in scenarios:
                try:
                    metrics[name] = probe(recall, root / name)
                except Exception as exc:
                    failures.append(f"{name}:{type(exc).__name__}:{exc}")
    ok = not failures
    return {
        "schema": "court.shiguan_recall_source_fallback_check.v1",
        "contract": "SHIGUAN_RECALL_SOURCE_FALLBACK",
        "status": "PASSED" if ok else "FAILED",
        "ok": ok,
        "metrics": metrics,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "court.shiguan_recall_source_fallback_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "SHIGUAN_RECALL_SOURCE_FALLBACK",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"SHIGUAN_RECALL_SOURCE_FALLBACK={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
