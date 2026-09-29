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
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "laya-multilingual"
CORPUS = ROOT / "corpus" / "corpus-v2.jsonl"
CACHE = ROOT / "runs" / "recall-index.pt"
SERVICE_VERSION = "1.0.0"


class ShiguanRecall:
    def __init__(self, max_len: int = 512, device: str | None = None) -> None:
        self.max_len = max_len
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self._model = None
        self._tok = None
        self.rows: list[dict] = []
        self.vecs: torch.Tensor | None = None
        self.built_at: float = 0.0
        self.build_seconds: float = 0.0

    # ---------- 模型 ----------
    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        from safetensors.torch import load_file
        from laya.common import build_model

        cfg = json.loads((MODEL_DIR / "rl_agent_config.json").read_text(encoding="utf-8"))
        cfg.update(max_len=self.max_len, head_max_len=192, gradient_checkpointing=False)
        self._tok = AutoTokenizer.from_pretrained(str(MODEL_DIR / "tokenizer"))
        model = build_model(cfg, encoder_dir=str(MODEL_DIR / "encoder"), pretrained=False)
        model.load_state_dict(load_file(str(MODEL_DIR / "model.safetensors")), strict=True)
        model.to(self.device).eval()
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
    def _corpus_stamp(self) -> dict:
        stat = CORPUS.stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def build(self, force: bool = False) -> None:
        rows = [json.loads(l) for l in CORPUS.open(encoding="utf-8") if l.strip()]
        # 只索引真实史馆记录（index 来源），合成负例与夹具不作为对照样本
        self.rows = [r for r in rows if r["source"] == "index"]
        stamp = self._corpus_stamp()
        if not force and CACHE.exists():
            cached = torch.load(CACHE, weights_only=False)
            if cached.get("stamp") == stamp:
                self.vecs = cached["vecs"]
                self.built_at = cached.get("built_at", 0.0)
                return
        t0 = time.time()
        self.vecs = self._embed([r["state"] for r in self.rows])
        self.build_seconds = time.time() - t0
        self.built_at = time.time()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"stamp": stamp, "vecs": self.vecs, "built_at": self.built_at}, CACHE)

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
        if self.vecs is None:
            self.build()
        assert self.vecs is not None
        q = self._embed([state])
        sim = (q @ self.vecs.T)[0]
        pool = range(len(self.rows))
        if same_top:
            head = state.splitlines()[0].replace("主题：", "").strip()
            pool = [i for i, r in enumerate(self.rows) if r["group"] == head]
            if not pool:
                pool = range(len(self.rows))
        idx = sorted(pool, key=lambda i: -float(sim[i]))[: max(1, k)]
        matches = [{"similarity": round(float(sim[i]), 4), **self._record(self.rows[i])} for i in idx]
        return {
            "matches": matches,
            "stats": {
                "indexed_records": len(self.rows),
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
        paths = [self._record(r)["stored_path"] for r in self.rows] if self.rows else []
        return {
            "service_version": SERVICE_VERSION,
            "model": "convaiinnovations/laya-multilingual (mmBERT-base 322M)",
            "indexed_records": len(self.rows),
            "distinct_lineages": len({p for p in paths if p}),
            "embedding_dim": int(self.vecs.shape[1]) if self.vecs is not None else None,
            "index_cache": str(CACHE),
            "built_at": self.built_at,
            "device": str(self.device),
        }
