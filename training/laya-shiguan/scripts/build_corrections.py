r"""从审计结论生成纠错集（corrections.jsonl），供语料作为负例 / 新类正例消费。

判定规则（全部可复现，不含人工臆断）：
  R1 覆盖待审  存量志 = 待审 而重推判 classified
               -> 分类器越权，应弃权。负例（abstain=True）
  R2 词表缺类  存量志 不在 CONTENT_TAXONOMY 的志集合内（实测有「项目」）
               -> taxonomy gap，应开新一级类的正例
  R3 自查污染  重推志 = 典藏 而存量志 != 典藏
               -> 记录因自身含「史馆/实录/索引」词汇被吸附进典藏分支。
                  负例（abstain=True）+ 保留存量谱系作为对照
  R4 真实分歧  reason=matched 且存量谱系 != 重推谱系
               -> 两者必有一错，标为待人工裁定，不入训练集
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shiguan_paths import REPO_ROOT as REPO, TRAINING_ROOT as OUT, shiguan_index_path  # noqa: E402

SHIGUAN_INDEX = shiguan_index_path()


def load_index() -> list[dict]:
    rows = []
    with SHIGUAN_INDEX.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def stored_parts(entry: dict) -> dict:
    parts = entry.get("lineage_parts")
    return parts if isinstance(parts, dict) else {}


def stored_path(entry: dict) -> str:
    parts = stored_parts(entry)
    order = ["zhi", "men", "gang", "mu", "tiao"]
    return "/".join(str(parts.get(k) or "") for k in order).strip("/")


def main() -> int:
    sys.path.insert(0, str(REPO / "scripts"))
    import shiguan_entry_utils as utils

    vocabulary_zhi = {row[0] for row in utils.CONTENT_TAXONOMY}
    entries = load_index()
    corrections = []
    counts: Counter[str] = Counter()

    for entry in entries:
        code = str(entry.get("court_code") or "")
        try:
            result = utils.content_lineage_parts(dict(entry))
        except Exception:  # noqa: BLE001
            continue
        cands = result.get("candidates") or []
        derived = str((cands[0] if cands else {}).get("path") or "")
        stored = stored_path(entry)
        zhi_stored = (stored.split("/")[0] if stored else "")
        zhi_derived = (derived.split("/")[0] if derived else "")
        common = {
            "id": code,
            "topic": entry.get("topic"),
            "stored_path": stored,
            "derived_path": derived,
            "derived_reason": result.get("classification_reason"),
            "state": "\n".join(
                [
                    f"主题：{str(entry.get('topic') or '')[:60]}",
                    f"阶段：{str(entry.get('phase') or '')} / 状态：{str(entry.get('status') or '')}",
                    f"摘要：{str(entry.get('summary') or '')[:300]}",
                    f"要点：{str(entry.get('key_actions') or '')[:160]}",
                ]
            ),
        }

        if zhi_stored == "待审" and result.get("classification_status") == "classified":
            corrections.append({**common, "rule": "R1_override_review", "verdict": "classifier_wrong",
                                "note": "存量已判待审，重推仍强行归类；应弃权"})
            counts["R1_override_review"] += 1
        elif zhi_stored and zhi_stored not in vocabulary_zhi:
            corrections.append({**common, "rule": "R2_taxonomy_gap", "verdict": "should_new_class",
                                "note": f"存量志「{zhi_stored}」不在当前词表 {sorted(vocabulary_zhi)} 内"})
            counts["R2_taxonomy_gap"] += 1
        elif zhi_derived == "典藏" and zhi_stored != "典藏":
            corrections.append({**common, "rule": "R3_shiguan_self_contamination", "verdict": "classifier_wrong",
                                "note": "因文本含史馆/实录/索引词汇被吸附进典藏分支"})
            counts["R3_shiguan_self_contamination"] += 1
        elif result.get("classification_reason") == "matched" and stored and stored != derived:
            corrections.append({**common, "rule": "R4_real_disagreement", "verdict": "needs_human",
                                "note": "分类器与存量都有定论且不一致，两者必有一错"})
            counts["R4_real_disagreement"] += 1

    OUT.joinpath("corpus").mkdir(parents=True, exist_ok=True)
    with OUT.joinpath("corpus", "corrections.jsonl").open("w", encoding="utf-8") as handle:
        for item in corrections:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    summary = {
        "total": sum(counts.values()),
        "by_rule": dict(counts),
        "vocabulary_zhi": sorted(vocabulary_zhi),
        "note": "R1/R3 -> 负例(abstain=True)；R2 -> 新类正例；R4 -> 待人工裁定，不入训练集",
    }
    OUT.joinpath("corpus", "corrections-stats.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
