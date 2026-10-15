r"""史馆对照决策检索引擎（Shiguan Recall）。

用途：给定一条**待判定的史馆实录文本**，返回最相似的 N 条历史实录，
连同它们当时的：诏令编号、五段谱系、记忆裁定、风险/知识/优先级、分类理由。

定位：**advisory / 只读 / 无执行权**——只提供对照参考，不写任何史馆数据。

接口：
    engine = ShiguanRecall()
    engine.recall(state_text, k=5)   -> {"matches": [...], "stats": {...}}
    engine.stats()                   -> {"records": n, "model": ..., ...}
"""

from __future__ import annotations

import json
import io
import os
import pickle
import re
import sys
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
# The HTTP/stdio entry points add service/ only. Resolve the existing helper
# from this installation's scripts/, without depending on the caller's cwd.
_SCRIPTS_ROOT = ROOT.parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
from court_file_lock import atomic_write_bytes, file_lock

MODEL_DIR = ROOT / "models" / "laya-multilingual"
CORPUS = ROOT / "corpus" / "corpus-v2.jsonl"
SERVICE_VERSION = "1.0.0"


def cache_path() -> Path:
    """索引缓存的运行期位置（**永不写回安装态**）。

    安装态是只读投影；缓存放用户可写缓存目录，可用 SHIGUAN_RECALL_CACHE 覆盖。
    默认 `%LOCALAPPDATA%`（POSIX 用 `$XDG_CACHE_HOME`，缺失时退回临时目录）。
    ⚠️ 受限沙箱下可能全部不可写；缓存不可写**不影响服务可用性**，只是每次启动
    重新编码（实测 1129 条约 11 秒）。
    """

    override = os.environ.get("SHIGUAN_RECALL_CACHE", "").strip()
    if override:
        return Path(override).expanduser()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else (Path(os.environ.get("TEMP") or "/tmp"))
    return root / "decretum-matrix" / "shiguan-recall" / "recall-index.pt"

# 标签泄漏：索引的 key_actions 形如 ['phase:..','status:..','memory:SKIP','next:..']，
# memory:<枚举> 就是 memory_decision 的答案本身，必须从检索文本里抹掉。
_LABEL_LEAK = re.compile(r"memory\s*[:=]\s*(WRITE|PROPOSE|SKIP|DEFERRED)", re.IGNORECASE)


def live_index_path() -> Path | None:
    """实时史馆索引；可用 SHIGUAN_REFERENCES_ROOT / COURT_SHARED_SHIGUAN_ROOT 覆盖。"""

    override = os.environ.get("SHIGUAN_REFERENCES_ROOT", "").strip()
    if override:
        base = Path(override).expanduser()
        base = base if base.name == "references" else base / "references"
        return base / "shiguan-index.jsonl"
    for key in ("COURT_SHARED_SHIGUAN_ROOT", "SHIGUAN_SHARED_ROOT"):
        value = os.environ.get(key, "").strip()
        if value:
            base = Path(value).expanduser()
            base = base if base.name == "references" else base / "references"
            return base / "shiguan-index.jsonl"
    return Path.home() / ".agents" / "court-shiguan" / "decretum-matrix" / "references" / "shiguan-index.jsonl"


def _strip(value: object) -> str:
    text = _LABEL_LEAK.sub("memory:<redacted>", str(value or ""))
    return " ".join(tok for tok in text.split() if "/" not in tok and "\\" not in tok).strip()


def state_from_entry(entry: dict) -> str:
    """与 build_corpus.build_state 同构：抹掉标签与路径，保留内容信号。"""

    return "\n".join(
        [
            f"主题：{_strip(entry.get('topic'))[:60]}",
            f"阶段：{str(entry.get('phase') or '').strip()[:20]} / 状态：{str(entry.get('status') or '').strip()[:24]}",
            f"摘要：{_strip(entry.get('summary'))[:400]}",
            f"要点：{_strip(entry.get('key_actions'))[:200]}",
        ]
    )


def rows_from_live_index(path: Path) -> list[dict]:
    """把实时史馆索引映射成检索行（只索引真实史馆记录，不引入合成样本）。"""

    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            parts = entry.get("lineage_parts") if isinstance(entry.get("lineage_parts"), dict) else {}
            rows.append(
                {
                    "id": str(entry.get("court_code") or ""),
                    "group": str(entry.get("topic") or "").strip() or "(no-topic)",
                    "state": state_from_entry(entry),
                    "meta": {
                        "stored_path": "/".join(
                            str(parts.get(k) or "") for k in ("zhi", "men", "gang", "mu", "tiao")
                        ).strip("/"),
                        "stored_reason": entry.get("classification_reason"),
                        "taxonomy_version": entry.get("taxonomy_version"),
                    },
                    "gold": {
                        "memory_decision": _enum(entry.get("memory_decision")),
                        "risk_level": _grade(entry.get("risk_level")),
                        "knowledge_value": _grade(entry.get("knowledge_value")),
                        "priority_level": _grade(entry.get("priority_level")),
                        "abstain": entry.get("classification_status") == "review",
                    },
                }
            )
    return rows


_ENUM = ("WRITE", "PROPOSE", "SKIP", "DEFERRED")
_GRADE = {"S": 3, "A": 3, "B": 2, "C": 1, "D": 0, "E": 0, "F": 0}


def _enum(value: object) -> str | None:
    text = str(value or "").replace("`", "").strip()
    return next((e for e in _ENUM if text.startswith(e)), None)


def _grade(value: object) -> int | None:
    text = str(value or "").replace("`", "").strip().upper()
    return _GRADE.get(text[:1]) if text else None


def rows_from_corpus(path: Path) -> list[dict]:
    """回退路径：本地训练语料（仅仓库开发态存在）。"""

    rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    return [r for r in rows if r["source"] == "index"]


@dataclass(frozen=True)
class _IndexSnapshot:
    rows: list[dict] = field(default_factory=list)
    vecs: torch.Tensor | None = None
    stamp: dict = field(default_factory=dict)
    built_at: float = 0.0
    build_seconds: float = 0.0
    source_kind: str = ""
    source_path: str = ""
    cache_path: str = ""


class ShiguanRecall:
    def __init__(self, max_len: int = 512, device: str | None = None) -> None:
        self.max_len = max_len
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self._model = None
        self._tok = None
        self._build_lock = threading.RLock()
        self._snapshot = _IndexSnapshot()

    # Keep the existing read interface used by the standalone entry points.
    @property
    def rows(self):
        return self._snapshot.rows

    @property
    def vecs(self):
        return self._snapshot.vecs

    @property
    def built_at(self):
        return self._snapshot.built_at

    @property
    def build_seconds(self):
        return self._snapshot.build_seconds

    @property
    def source_kind(self):
        return self._snapshot.source_kind

    @property
    def source_path(self):
        return self._snapshot.source_path

    @property
    def cache_path(self):
        return self._snapshot.cache_path

    # ---------- 模型 ----------
    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        # A warm vector cache skips embedding during build, so the first queries
        # can reach model initialization together. Reuse the engine lock; it is
        # reentrant because a cold build also calls this through _embed.
        with self._build_lock:
            if self._model is not None:
                return
            from safetensors.torch import load_file
            from laya.common import build_model

            cfg = json.loads((MODEL_DIR / "rl_agent_config.json").read_text(encoding="utf-8"))
            cfg.update(max_len=self.max_len, head_max_len=192, gradient_checkpointing=False)
            tok = AutoTokenizer.from_pretrained(str(MODEL_DIR / "tokenizer"))
            model = build_model(cfg, encoder_dir=str(MODEL_DIR / "encoder"), pretrained=False)
            model.load_state_dict(load_file(str(MODEL_DIR / "model.safetensors")), strict=True)
            model.to(self.device).eval()
            # _model is the ready flag. Failed initialization publishes neither
            # half, releases the lock and leaves the next query free to retry.
            self._tok = tok
            self._model = model

    def _embed(self, texts: list[str], batch: int = 16) -> torch.Tensor:
        self._ensure_model()
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), batch):
                enc = self._tok(
                    texts[i : i + batch], padding=True, truncation=True,
                    max_length=self.max_len, return_tensors="pt",
                ).to(self.device)
                with torch.amp.autocast(self.device.type, dtype=torch.bfloat16):
                    h = self._model.encoder(
                        input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]
                    ).last_hidden_state.float()
                mask = enc["attention_mask"].unsqueeze(-1).float()
                out.append(F.normalize((h * mask).sum(1) / mask.sum(1).clamp(min=1e-6), dim=-1).cpu())
        return torch.cat(out)

    # ---------- 索引 ----------
    def _source(self) -> tuple[Path, str]:
        """优先实时史馆索引；仅开发态回退本地语料。"""

        live = live_index_path()
        if live is not None and live.is_file():
            return live, "live_shiguan_index"
        return CORPUS, "local_corpus"

    def _stamp(self, path: Path) -> dict:
        stat = path.stat()
        return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def build(self, force: bool = False) -> None:
        # Per-engine single-flight; force rebuilds wait for one another. Failed
        # builds leave the last published generation intact and may be retried.
        with self._build_lock:
            source, kind = self._source()
            # Bind the lock to the actual source, including a references override.
            # Capture rows and stamp together, then release before slow embedding.
            guard = (file_lock(source.parent / "court-runtime/shiguan-write.lock", shared=True)
                     if kind == "live_shiguan_index" else nullcontext())
            with guard:
                rows = rows_from_live_index(source) if kind == "live_shiguan_index" else rows_from_corpus(source)
                stamp = self._stamp(source)
            current = self._snapshot
            if not force and current.vecs is not None and current.stamp == stamp:
                return
            cache = cache_path()
            if not force and cache.exists():
                try:
                    cached = torch.load(cache, weights_only=False)
                except (OSError, RuntimeError, EOFError, pickle.UnpicklingError):
                    cached = None
                if (isinstance(cached, dict) and cached.get("stamp") == stamp
                        and getattr(cached.get("vecs"), "shape", (None,))[0] == len(rows)):
                    self._snapshot = _IndexSnapshot(rows=rows, vecs=cached["vecs"], stamp=stamp,
                        built_at=cached.get("built_at", 0.0), source_kind=kind,
                        source_path=str(source), cache_path=str(cache))
                    return
            t0 = time.time()
            vecs = self._embed([r["state"] for r in rows])
            build_seconds, built_at = time.time() - t0, time.time()
            cache_location = str(cache)
            try:
                buffer = io.BytesIO()
                torch.save({"stamp": stamp, "vecs": vecs, "built_at": built_at}, buffer)
                atomic_write_bytes(cache, buffer.getvalue())
            except (OSError, RuntimeError):
                # 缓存不可写不应影响服务可用性；下次启动重新编码即可。
                cache_location = f"unavailable:{cache}"
            self._snapshot = _IndexSnapshot(rows=rows, vecs=vecs, stamp=stamp, built_at=built_at,
                build_seconds=build_seconds, source_kind=kind, source_path=str(source), cache_path=cache_location)

    # ---------- 检索 ----------
    @staticmethod
    def _record(row: dict) -> dict:
        meta = row.get("meta") or {}
        return {
            "court_code": row["id"],
            "topic": row["group"],
            "stored_path": meta.get("stored_path"),
            "classification_reason": meta.get("stored_reason"),
            "taxonomy_version": meta.get("taxonomy_version"),
            "memory_decision": row["gold"].get("memory_decision"),
            "risk_level": row["gold"].get("risk_level"),
            "knowledge_value": row["gold"].get("knowledge_value"),
            "priority_level": row["gold"].get("priority_level"),
            "abstain": row["gold"].get("abstain"),
            "summary": next(
                (l[3:] for l in row["state"].splitlines() if l.startswith("摘要：")), ""
            )[:200],
        }

    def recall(self, state: str, k: int = 5, same_top: bool = False) -> dict:
        snapshot = self._snapshot
        if snapshot.vecs is None:
            self.build()
            snapshot = self._snapshot
        assert snapshot.vecs is not None
        q = self._embed([state])
        sim = (q @ snapshot.vecs.T)[0]
        pool = range(len(snapshot.rows))
        if same_top:
            head = state.splitlines()[0].replace("主题：", "").strip()
            pool = [i for i, r in enumerate(snapshot.rows) if r["group"] == head]
            if not pool:
                pool = range(len(snapshot.rows))
        idx = sorted(pool, key=lambda i: -float(sim[i]))[: max(1, k)]
        matches = [{"similarity": round(float(sim[i]), 4), **self._record(snapshot.rows[i])} for i in idx]
        return {
            "matches": matches,
            "stats": {
                "indexed_records": len(snapshot.rows),
                "k": k,
                "top_similarity": matches[0]["similarity"] if matches else None,
            },
            "advisory": {
                "authority": "advisory",
                "execution_authority": False,
                "note": "仅作对照参考；不得据以写入史馆或替代门下裁定",
            },
        }

    def stats(self) -> dict:
        snapshot = self._snapshot
        paths = [self._record(r)["stored_path"] for r in snapshot.rows]
        return {
            "service_version": SERVICE_VERSION,
            "model": "convaiinnovations/laya-multilingual (mmBERT-base 322M)",
            "index_source": snapshot.source_kind or None,
            "index_source_path": snapshot.source_path or None,
            "indexed_records": len(snapshot.rows),
            "distinct_lineages": len({p for p in paths if p}),
            "embedding_dim": int(snapshot.vecs.shape[1]) if snapshot.vecs is not None else None,
            "index_cache": snapshot.cache_path or str(cache_path()),
            "built_at": snapshot.built_at,
            "device": str(self.device),
        }
