r"""史馆分类错误排查：产出可疑记录短名单，供人工/模型复核。

只读脚本，不修改史馆任何数据。信号全部来自索引 metadata + 当前分类器重推结果。

可疑信号：
  S1 存量谱系与当前分类器重推路径不一致        （两者至少一个错）
  S2 命中分数过低（top_score < MIN_SCORE）却判 classified
  S3 margin 过小 / 置信度低
  S4 状态文本中路径型 token 占比过高            （契约 B 禁止路径作为分类证据）
  S5 摘要过短，证据不足却仍判 classified
  S6 违反合同的组合：tie/low_confidence 却 classified
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shiguan_paths import REPO_ROOT as REPO, TRAINING_ROOT as OUT, shiguan_index_path  # noqa: E402

SHIGUAN_INDEX = shiguan_index_path()
MIN_SCORE = 2
PATH_TOKEN = re.compile(r"(?:[A-Za-z0-9_\-]+[\\/]){1,}|\.(?:py|json|md|txt|yml|yaml)\b")


def load_index() -> list[dict]:
    rows = []
    with SHIGUAN_INDEX.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def derived(entries: list[dict]) -> dict[str, dict]:
    sys.path.insert(0, str(REPO / "scripts"))
    import shiguan_entry_utils as utils

    out = {}
    for entry in entries:
        code = str(entry.get("court_code") or "")
        try:
            result = utils.content_lineage_parts(dict(entry))
        except Exception as exc:  # noqa: BLE001
            out[code] = {"status": "error", "reason": type(exc).__name__}
            continue
        cands = result.get("candidates") or []
        top = cands[0] if cands else {}
        out[code] = {
            "status": result.get("classification_status"),
            "reason": result.get("classification_reason"),
            "confidence": result.get("classification_confidence"),
            "margin": result.get("classification_margin"),
            "score": top.get("score"),
            "path": top.get("path"),
        }
    return out


def stored_path(entry: dict) -> str:
    parts = entry.get("lineage_parts")
    if isinstance(parts, dict):
        order = ["zhi", "men", "gang", "mu", "tiao"]
        return "/".join(str(parts.get(k) or "") for k in order).strip("/")
    return str(entry.get("ancient_lineage") or "")


def main() -> int:
    entries = load_index()
    lin = derived(entries)
    suspects = []

    for entry in entries:
        code = str(entry.get("court_code") or "")
        info = lin.get(code, {})
        text = " ".join(
            str(entry.get(k) or "") for k in ("topic", "summary", "evidence", "key_actions")
        )
        tokens = text.split()
        path_ratio = (
            sum(1 for t in tokens if PATH_TOKEN.search(t)) / len(tokens) if tokens else 0.0
        )
        summary_len = len(str(entry.get("summary") or ""))
        stored = stored_path(entry)
        derived_path = str(info.get("path") or "")
        signals = []

        if stored and derived_path and stored != derived_path:
            signals.append("S1_stored_vs_derived")
        if info.get("status") == "classified" and (info.get("score") or 0) < MIN_SCORE:
            signals.append("S2_low_score_classified")
        if info.get("status") == "classified" and (info.get("confidence") or 0) < 0.55:
            signals.append("S3_low_confidence")
        if path_ratio > 0.08:
            signals.append("S4_path_tokens")
        if summary_len < 40:
            signals.append("S5_short_summary")
        if info.get("reason") in ("tie", "low_confidence", "conflict") and info.get("status") == "classified":
            signals.append("S6_contract_violation")

        if signals:
            suspects.append(
                {
                    "id": code,
                    "topic": entry.get("topic"),
                    "signals": signals,
                    "stored_path": stored,
                    "derived_path": derived_path,
                    "derived_reason": info.get("reason"),
                    "score": info.get("score"),
                    "margin": info.get("margin"),
                    "confidence": info.get("confidence"),
                    "path_ratio": round(path_ratio, 3),
                    "summary_len": summary_len,
                    "state": "\n".join(
                        [
                            f"主题：{str(entry.get('topic') or '')[:60]}",
                            f"阶段：{str(entry.get('phase') or '')} / 状态：{str(entry.get('status') or '')}",
                            f"摘要：{str(entry.get('summary') or '')[:300]}",
                            f"要点：{str(entry.get('key_actions') or '')[:160]}",
                        ]
                    ),
                    "stored_reason": entry.get("classification_reason"),
                }
            )

    suspects.sort(key=lambda item: (-len(item["signals"]), item["confidence"] or 0))
    OUT.joinpath("corpus").mkdir(parents=True, exist_ok=True)
    with OUT.joinpath("corpus", "suspects.jsonl").open("w", encoding="utf-8") as handle:
        for item in suspects:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for item in suspects:
        for sig in item["signals"]:
            counts[sig] = counts.get(sig, 0) + 1
    print(json.dumps(
        {
            "total_records": len(entries),
            "suspects": len(suspects),
            "signal_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
            "multi_signal": sum(1 for s in suspects if len(s["signals"]) >= 2),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
