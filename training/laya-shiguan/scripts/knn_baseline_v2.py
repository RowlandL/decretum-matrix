r"""kNN 检索基线 v2：把「零训练能到多少」这条线钉死。

相比 v1 增加：
  1. 距离加权投票（w = cos^p）
  2. **平衡准确率**（各类召回均值）—— 原始准确率在 94%/99% 失衡头上完全失真
  3. 多种特征组合（state / state+topic / state+keywords）
  4. k 扫描
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer

from laya.common import build_model

OUT = Path(__file__).resolve().parents[1]
MODEL_DIR = OUT / "models" / "laya-multilingual"
CORPUS = OUT / "corpus" / "corpus-v2.jsonl"
QUESTIONS = ("memory_decision", "risk_level", "knowledge_value", "priority_level", "abstain", "should_new_class")


def feature_text(row: dict, mode: str) -> str:
    if mode == "state":
        return row["state"]
    if mode == "topic":
        return f"主题：{row['group']}\n{row['state']}"
    if mode == "topic_kw":
        kw = " ".join(row.get("meta", {}).get("keywords") or []) if isinstance(row.get("meta"), dict) else ""
        return f"主题：{row['group']}\n{kw}\n{row['state']}"
    return row["state"]


def embed(model, tok, texts, device, max_len, batch=16):
    vecs = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tok(texts[i : i + batch], padding=True, truncation=True, max_length=max_len, return_tensors="pt").to(device)
            with torch.amp.autocast("cuda", dtype=torch.bfloat16):
                out = model.encoder(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"])
            h = out.last_hidden_state.float()
            m = enc["attention_mask"].unsqueeze(-1).float()
            vecs.append(F.normalize((h * m).sum(1) / m.sum(1).clamp(min=1e-6), dim=-1).cpu())
    return torch.cat(vecs)


def balanced_acc(pairs: list[tuple]) -> float:
    """pairs = [(gold, pred)]，返回各类召回的均值。"""
    if not pairs:
        return float("nan")
    per: dict = defaultdict(lambda: [0, 0])
    for g, p in pairs:
        per[g][1] += 1
        if g == p:
            per[g][0] += 1
    return sum(c / t for c, t in per.values()) / len(per)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--k", type=int, nargs="+", default=[1, 3, 5, 10, 20, 40])
    ap.add_argument("--power", type=float, nargs="+", default=[0.0, 8.0], help="距离权重 cos^p，0=等权")
    ap.add_argument("--features", nargs="+", default=["state", "topic"], choices=["state", "topic", "topic_kw"])
    args = ap.parse_args()

    cfg = json.loads((MODEL_DIR / "rl_agent_config.json").read_text(encoding="utf-8"))
    cfg.update(max_len=args.max_len, head_max_len=192, gradient_checkpointing=False)
    device = torch.device("cuda")

    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR / "tokenizer"))
    model = build_model(cfg, encoder_dir=str(MODEL_DIR / "encoder"), pretrained=False)
    from safetensors.torch import load_file

    model.load_state_dict(load_file(str(MODEL_DIR / "model.safetensors")), strict=True)
    model.to(device)

    rows = [json.loads(l) for l in CORPUS.open(encoding="utf-8") if l.strip()]
    train = [r for r in rows if r.get("split") == "train" and r["source"] == "index"]
    val = [r for r in rows if r.get("split") == "val"]
    print(f"参照集(train/index)={len(train)}  查询集(val)={len(val)}\n")

    for mode in args.features:
        etr = embed(model, tok, [feature_text(r, mode) for r in train], device, args.max_len)
        eva = embed(model, tok, [feature_text(r, mode) for r in val], device, args.max_len)
        sim = eva @ etr.T
        print(f"===== 特征: {mode} =====")
        print(f"{'问题':<20}{'基线':>7}{'平衡基线':>9}" + "".join(f"{'k'+str(k)+'/p'+str(int(p)):>11}" for k in args.k[:3] for p in args.power) + "  最佳平衡准确率")
        print("-" * 92)
        for q in QUESTIONS:
            gv = [r["gold"].get(q) for r in val]
            valid = [g for g in gv if g is not None]
            if not valid:
                continue
            base = Counter(valid).most_common(1)[0][1] / len(valid)
            bbal = balanced_acc([(g, Counter(valid).most_common(1)[0][0]) for g in valid])
            line = f"{q:<20}{base:>7.3f}{bbal:>9.3f}"
            best = (-9.0, None)
            for k in args.k:
                topk = sim.topk(k, dim=1)
                for p in args.power:
                    pairs = []
                    for i, r in enumerate(val):
                        if gv[i] is None:
                            continue
                        votes: dict = defaultdict(float)
                        for j, s in zip(topk.indices[i].tolist(), topk.values[i].tolist()):
                            g = train[j]["gold"].get(q)
                            if g is not None:
                                votes[g] += max(s, 0.0) ** p if p else 1.0
                        if not votes:
                            continue
                        pairs.append((gv[i], max(votes, key=votes.get)))
                    b = balanced_acc(pairs)
                    if b > best[0]:
                        best = (b, (k, p))
            for k in args.k[:3]:
                for p in args.power:
                    topk = sim.topk(k, dim=1)
                    pairs = []
                    for i, r in enumerate(val):
                        if gv[i] is None:
                            continue
                        votes: dict = defaultdict(float)
                        for j, s in zip(topk.indices[i].tolist(), topk.values[i].tolist()):
                            g = train[j]["gold"].get(q)
                            if g is not None:
                                votes[g] += max(s, 0.0) ** p if p else 1.0
                        if votes:
                            pairs.append((gv[i], max(votes, key=votes.get)))
                    line += f"{balanced_acc(pairs):>11.3f}"
            line += f"   best={best[0]:.3f} @k{best[1][0]}/p{int(best[1][1])}"
            print(line, flush=True)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
