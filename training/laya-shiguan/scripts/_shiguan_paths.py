"""史馆源路径的可移植解析（训练/服务侧共用）。

设计约束：**不含任何绝对路径、不硬编码机器布局**，换机器无需改动。

解析顺序（与 scripts/shiguan_paths.py 的官方覆盖约定对齐）：
  1. `SHIGUAN_REFERENCES_ROOT`                 —— 训练管线专用覆盖
  2. `COURT_SHARED_SHIGUAN_ROOT` / `SHIGUAN_SHARED_ROOT` —— 官方共享根（自动补 references）
  3. `Path.home() / ".agents/court-shiguan/decretum-matrix/references"`

`Path.home()` 跨平台（Windows 读 USERPROFILE，POSIX 读 HOME），
因此不再直接依赖 `os.environ["USERPROFILE"]`，也不会在非 Windows 上 KeyError。
"""

from __future__ import annotations

import os
from pathlib import Path

# .../training/laya-shiguan/scripts/_shiguan_paths.py
TRAINING_ROOT = Path(__file__).resolve().parents[1]  # .../training/laya-shiguan
REPO_ROOT = Path(__file__).resolve().parents[3]  # 仓库根
CORPUS_DIR = TRAINING_ROOT / "corpus"
MODEL_DIR = TRAINING_ROOT / "models" / "laya-multilingual"
RUNS_DIR = TRAINING_ROOT / "runs"

REFERENCES_ENV = "SHIGUAN_REFERENCES_ROOT"
SHARED_ROOT_ENVS = ("COURT_SHARED_SHIGUAN_ROOT", "SHIGUAN_SHARED_ROOT")
DEFAULT_SUFFIX = Path(".agents") / "court-shiguan" / "decretum-matrix" / "references"


def shiguan_references_root() -> Path:
    """返回史馆 references 根目录（可被环境变量覆盖，无绝对路径硬编码）。"""

    override = os.environ.get(REFERENCES_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    for key in SHARED_ROOT_ENVS:
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        base = Path(value).expanduser()
        return base if base.name == "references" else base / "references"
    return Path.home() / DEFAULT_SUFFIX


def shiguan_index_path() -> Path:
    """返回 shiguan-index.jsonl 的路径。"""

    return shiguan_references_root() / "shiguan-index.jsonl"


def reference_fixture(name: str) -> Path:
    """返回仓库内 references/fixtures/<name> 的路径。"""

    return REPO_ROOT / "references" / "fixtures" / name
