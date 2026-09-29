r"""零训练 kNN 检索基线。

目的：用**同一个冻结 encoder** 抽特征 + 最近邻投票，不训练任何参数。
如果 kNN 打平或超过「只训决策头」，说明头的训练没有带来超出表示本身的信息。

方法：
  1. 用 laya-multilingual 的 encoder（306.9M，冻结）对每条 state 做 mean-pool 句向量
  2. val 行 → 在 train 行里找 k 近邻（余弦）
  3. 每个问题在近邻中按有效标签多数投票
  4. 与多数类基线对比
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer

from laya.common import build_model

OUT = Path(__file__).resolve().parents[1]
MODEL_DIR = OUT / "models" / "laya-multilingual"
CORPUS = OUT / "corpus" / "corpus-v2.jsonl"
QUESTIONS = ("memory_decision", "risk_level", "knowledge_value", "priority_level", "abstain", "should_new_class")


def embed(model, tok, texts, device, max_len, batch=16):
    vecs = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tok(
                texts[i : i + batch], padding=True, truncation=True, max_length=max_len, return_tensors="pt"
            ).to(device)
            with torch.amp.autocast("cuda", dtype=torch.bfloat16):
                out = model.encoder(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"])
            h = out.last_hidden_state.float()
            m = enc["attention_mask"].unsqueeze(-1).float()
            pooled = (h * m).sum(1) / m.sum(1).clamp(min=1e-6)
            vecs.append(F.normalize(pooled, dim=-1).cpu())
    return torch.cat(vecs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--k", type=int, nargs="+", default=[1, 3, 5, 10, 20])
    args = ap.parse_args()

    cfg = json.loads((MODEL_DIR / "rl_agent_config.json").read_text(encoding="utf-8"))
    cfg["max_len"] = args.max_len
    cfg["head_max_len"] = 192
    cfg["gradient_checkpointing"] = False
    device = torch.device("cuda")

    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR / "tokenizer"))
    model = build_model(cfg, encoder_dir=str(MODEL_DIR / "encoder"), pretrained=False)
    from safetensors.torch import load_file

    model.load_state_dict(load_file(str(MODEL_DIR / "model.safetensors")), strict=True)
    model.to(device)

    rows = [json.loads(l) for l in CORPUS.open(encoding="utf-8") if l.strip()]
    train = [r for r in rows if r.get("split") == "train" and r["source"] == "index"]
    val = [r for r in rows if r.get("split") == "val"]
    print(f"train(index)={len(train)}  val={len(val)}")

    etr = embed(model, tok, [r["state"] for r in train], device, args.max_len)
    eva = embed(model, tok, [r["state"] for r in val], device, args.max_len)

    sim = eva @ etr.T  # 已归一化 → 余弦

    print(f"\n{'问题':<20}{'基线':>8}" + "".join(f"{'k='+str(k):>8}" for k in args.k) + "   最佳增益")
    print("-" * 78)
    for q in QUESTIONS:
        gold_val = [r["gold"].get(q) for r in val]
        valid = [g for g in gold_val if g is not None]
        if not valid:
            continue
        base = Counter(valid).most_common(1)[0][1] / len(valid)
        line = f"{q:<20}{base:>8.3f}"
        best = -9.0
        for k in args.k:
            topk = sim.topk(k, dim=1).indices
            correct = tot = 0
            for i, r in enumerate(val):
                votes = Counter()
                for j in topk[i].tolist():
                    g = train[j]["gold"].get(q)
                    if g is not None:
                        votes[g] += 1
                if not votes or gold_val[i] is None:
                    continue
                tot += 1
                if votes.most_common(1)[0][0] == gold_val[i]:
                    correct += 1
            acc = correct / max(tot, 1)
            best = max(best, acc)
            line += f"{acc:>8.3f}"
        line += f"   {best - base:+.3f}"
        print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
