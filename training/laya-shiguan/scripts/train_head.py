r"""Laya 决策头微调（单卡 · 冻结 encoder）。

基于官方 notebook 内联的 train_ddp.py 改写：
  - 去掉 DDP / nccl，改单卡
  - 冻结 encoder，只训决策头（26M），适配 8GB 显存
  - 语料换成史馆 corpus-v2.jsonl
  - 损失只用 soft cross-entropy 项（官方 RLCD 的 policy-gradient 项需要教师分布，
    当前语料只有硬标签 → one-hot 目标时 PG 项退化，故先关掉；等有 LLM 教师分布再开）

用法：
  python train_head.py --overfit 32 --epochs 200     # 过拟合冒烟测试
  python train_head.py --epochs 4                    # 小量正式训
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

import torch
from transformers import AutoTokenizer

from laya.common import QTYPES, build_model, build_sequence, render_options

OUT = Path(__file__).resolve().parents[1]
MODEL_DIR = OUT / "models" / "laya-multilingual"
CORPUS = OUT / "corpus" / "corpus-v2.jsonl"
QUESTIONS = json.loads((OUT / "schema" / "questions.json").read_text(encoding="utf-8"))
RUNS = OUT / "runs"

# 语料里的 gold 值 → 选项下标
GOLD_INDEX = {
    "memory_decision": {"WRITE": 0, "PROPOSE": 1, "SKIP": 2, "DEFERRED": 3},
    "abstain": {False: 0, True: 1},
    "should_new_class": {False: 0, True: 1},
}


def norm_q(name: str, spec: dict) -> dict:
    """schema 用的是 instructions；laya 内部 API 要 ins。"""
    return {"t": spec["type"], "ins": spec["instructions"], "crit": spec.get("criteria", {})}


def make_item(tok, state: str, name: str, spec: dict, cfg: dict, gold_value):
    t = spec["type"]
    crit = spec.get("criteria", {})
    q = {"t": t, "ins": spec["instructions"], "crit": crit}
    k = len(render_options(q))

    if name in GOLD_INDEX:
        given = gold_value
        if given is None:
            return None
        idx = GOLD_INDEX[name].get(given)
        if idx is None or idx >= k:
            return None
    elif spec["type"] == "score":
        # score 的 gold 是 0..k-1
        if gold_value is None:
            return None
        idx = int(gold_value)
        if not 0 <= idx < k:
            return None
    else:
        return None

    seq, markers = build_sequence(tok, state, q, cfg["max_len"], cfg["head_max_len"])
    if len(markers) != k:
        return None

    target = [0.0] * k
    target[idx] = 1.0
    return {"ids": seq, "markers": markers, "qtype": QTYPES[t], "target": target, "label": idx, "qname": name}


def collate(items, pad_id):
    n, L = len(items), max(len(it["ids"]) for it in items)
    kmax = max(len(it["markers"]) for it in items)
    ids = torch.full((n, L), pad_id, dtype=torch.long)
    att = torch.zeros((n, L), dtype=torch.long)
    mpos = torch.zeros((n, kmax), dtype=torch.long)
    mmask = torch.zeros((n, kmax), dtype=torch.bool)
    target = torch.zeros((n, kmax), dtype=torch.float32)
    for i, it in enumerate(items):
        ids[i, : len(it["ids"])] = torch.tensor(it["ids"])
        att[i, : len(it["ids"])] = 1
        k = len(it["markers"])
        mpos[i, :k] = torch.tensor(it["markers"])
        mmask[i, :k] = True
        target[i, : len(it["target"])] = torch.tensor(it["target"], dtype=torch.float32)
    return {
        "input_ids": ids,
        "attention_mask": att,
        "marker_pos": mpos,
        "marker_mask": mmask,
        "target": target,
        "qtype": torch.tensor([it["qtype"] for it in items]),
        "label": torch.tensor([it["label"] for it in items]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overfit", type=int, default=0, help="只取前 N 条的 item 做过拟合冒烟测试")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--lr-head", type=float, default=1e-4)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--head-max-len", type=int, default=192)
    ap.add_argument("--eight-bit", action="store_true")
    ap.add_argument("--tag", default="run")
    args = ap.parse_args()

    cfg = json.loads((MODEL_DIR / "rl_agent_config.json").read_text(encoding="utf-8"))
    cfg["max_len"] = args.max_len
    cfg["head_max_len"] = args.head_max_len
    cfg["gradient_checkpointing"] = False

    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR / "tokenizer"))
    device = torch.device("cuda")

    # ---- 语料 ----
    all_rows = [json.loads(l) for l in CORPUS.open(encoding="utf-8") if l.strip()]

    def build_items(rows):
        out, skip = [], 0
        for row in rows:
            for name, spec in QUESTIONS.items():
                it = make_item(tok, row["state"], name, spec, cfg, row["gold"].get(name))
                if it is None:
                    skip += 1
                else:
                    out.append(it)
        return out, skip

    train_rows = [r for r in all_rows if r.get("split") == "train"]
    if args.overfit:
        train_rows = train_rows[: args.overfit]
    val_rows = [] if args.overfit else [r for r in all_rows if r.get("split") == "val"]
    items, skipped = build_items(train_rows)
    val_items, _ = build_items(val_rows)
    print(f"train rows={len(train_rows)} items={len(items)} skipped={skipped} | val items={len(val_items)}")

    random.seed(0)
    random.shuffle(items)

    # ---- 模型 ----
    model = build_model(cfg, encoder_dir=str(MODEL_DIR / "encoder"), pretrained=False)
    from safetensors.torch import load_file

    model.load_state_dict(load_file(str(MODEL_DIR / "model.safetensors")), strict=True)

    trainable = list(model.head.parameters()) if hasattr(model, "head") else []
    if not trainable:
        trainable = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    n_head = sum(p.numel() for p in trainable)
    n_enc = sum(p.numel() for p in model.encoder.parameters())
    for p in model.encoder.parameters():
        p.requires_grad = False
    model.to(device)
    model.train()
    print(f"encoder params (frozen)={n_enc/1e6:.1f}M  head params (trainable)={n_head/1e6:.1f}M")

    if args.eight_bit:
        import bitsandbytes as bnb

        opt = bnb.optim.AdamW8bit(trainable, lr=args.lr_head)
    else:
        opt = torch.optim.AdamW(trainable, lr=args.lr_head)

    amp_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    RUNS.mkdir(parents=True, exist_ok=True)
    log = []

    def evaluate():
        if not val_items:
            return None, None
        model.eval()
        per_q: dict[str, list[int]] = {}
        correct = tot = 0
        with torch.no_grad():
            for i in range(0, len(val_items), args.batch):
                chunk = val_items[i : i + args.batch]
                batch = {k: v.to(device) for k, v in collate(chunk, tok.pad_token_id or 0).items()}
                with torch.amp.autocast("cuda", dtype=amp_dtype):
                    lg, _ = model(
                        batch["input_ids"], batch["attention_mask"],
                        batch["marker_pos"], batch["marker_mask"], batch["qtype"],
                    )
                ok = lg.float().masked_fill(~batch["marker_mask"], -1e4).argmax(-1) == batch["label"]
                correct += int(ok.sum().item())
                tot += len(chunk)
                for j, it in enumerate(chunk):
                    slot = per_q.setdefault(it["qname"], [0, 0])
                    slot[0] += int(ok[j].item())
                    slot[1] += 1
        model.train()
        return correct / max(tot, 1), {k: round(v[0] / v[1], 3) for k, v in per_q.items()}

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        random.shuffle(items)
        tot, correct, nloss, nb = 0, 0, 0.0, 0
        for i in range(0, len(items), args.batch):
            batch = collate(items[i : i + args.batch], tok.pad_token_id or 0)
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.amp.autocast("cuda", dtype=amp_dtype):
                logits, _act = model(
                    batch["input_ids"],
                    batch["attention_mask"],
                    batch["marker_pos"],
                    batch["marker_mask"],
                    batch["qtype"],
                )
                logits = logits.float()
                mask = batch["marker_mask"]
                loss = -(
                    batch["target"] * torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)
                ).sum(-1).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)

            with torch.no_grad():
                pred = logits.masked_fill(~mask, -1e4).argmax(-1)
                keep = batch["label"] >= 0
                correct += (pred[keep] == batch["label"][keep]).sum().item()
                tot += int(keep.sum().item())
            nloss += loss.item()
            nb += 1

        acc = correct / max(tot, 1)
        avg = nloss / max(nb, 1)
        vacc, per_q = evaluate()
        log.append({"epoch": epoch, "loss": avg, "acc": acc, "val_acc": vacc, "per_q": per_q,
                    "sec": round(time.time() - t0, 1)})
        line = f"epoch {epoch:>3}/{args.epochs}  loss={avg:.4f}  train={acc:.4f}"
        if vacc is not None:
            line += f"  val={vacc:.4f}"
        print(line, flush=True)
        if args.overfit and acc == 1.0 and avg < 0.05:
            print(">>> 过拟合达成：训练集 100% 命中")
            break

    (RUNS / f"{args.tag}-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    head_state = {k: v for k, v in model.state_dict().items() if not k.startswith("encoder.")}
    torch.save(head_state, RUNS / f"{args.tag}-head.pt")
    print(f"head state saved: {sum(v.numel() for v in head_state.values())/1e6:.1f}M params")
    print("done ->", RUNS / f"{args.tag}-log.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
