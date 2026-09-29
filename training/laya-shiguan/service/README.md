# 史馆对照决策检索服务 · shiguan-recall

**定位**：`advisory` 只读、无执行权。给定一条**待判定的史馆实录文本**，返回最相似的 N 条历史实录，
连同其诏令编号、五段谱系、记忆裁定、风险/知识/优先级等级、分类理由。

**用途**：诏令矩阵流程中的**部分对照决策**——判定前先看历史同类记录是怎么定的。

**不做什么**：不写史馆、不改 `CONTENT_TAXONOMY`、不替代门下裁定、不提供执行权威。

---

## 一、实测检索质量

参照集 = 901 条真实史馆记录（`source == index` 的 train 部分）；查询集 = 126 行 val（按 topic 分组切分，无泄漏）。

| k | 同谱系命中 | 同门命中（前两段）| 同志命中（首段）|
|---|---|---|---|
| 1 | 0.444 | 0.452 | 0.476 |
| **3** | **0.706** | 0.714 | 0.754 |
| 5 | **0.810** | 0.817 | 0.841 |
| 10 | 0.857 | 0.873 | 0.897 |
| 20 | 0.897 | 0.913 | 0.944 |

> 对照：训练 8 epoch 的决策头在同任务上**没跑赢多数类基线**，且输给本检索（见 `runs/small8-fixed-log.json`）。
> 因此当前版本**以检索为交付形态，微调挂起**。

## 二、三个接口

### 1. MCP stdio（推荐）

服务端：`service/mcp_server.py`，工具两个：

| 工具 | 入参 | 说明 |
|---|---|---|
| `shiguan_recall` | `state`(必填)、`k`(1-20，默认 5)、`same_topic`(bool) | 返回最相似历史实录及裁定 |
| `shiguan_recall_stats` | 无 | 索引统计 |

MCP 客户端配置（通用形状）：

```json
{
  "mcpServers": {
    "shiguan-recall": {
      "command": "<worktree>/training/laya-shiguan/.venv/Scripts/python.exe",
      "args": ["<worktree>/training/laya-shiguan/service/mcp_server.py"]
    }
  }
}
```

### 2. HTTP（本地只读）

```powershell
cd <worktree>\training\laya-shiguan
.venv\Scripts\python.exe -B service\serve_http.py --port 8767
```

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/stats` | 索引统计（首次调用会触发建索引）|
| POST | `/recall` | `{"state":"...","k":5,"same_topic":false}` |

### 3. 进程内调用

```python
import sys; sys.path.insert(0, "service")
from shiguan_recall import ShiguanRecall
eng = ShiguanRecall(); eng.build()
print(eng.recall("主题：...\n阶段：...\n摘要：...", k=5))
```

## 三、已知限制（重要）

1. **相似度绝对值不能当阈值**。mmBERT 句向量存在各向异性——不相关文本的余弦也有 0.93+。
   **只用相对排序（Top-k）**，不要写 `if sim > 0.9` 这类判断。
2. **启动约 15–25 秒**（torch/transformers 导入 + 模型加载）；首次建索引再加约 30 秒，
   之后走 `runs/recall-index.pt` 缓存（按语料 size+mtime 自动失效）。
3. 依赖 venv：`training/laya-shiguan/.venv`（Python 3.12 + torch 2.14.0+cu130 + laya 0.3.21）。
   **必须用该 venv 的 python**，系统 Python 无这些依赖。
4. 语料里 162 条合成/负例样本**不入索引**（只索引 `source == index` 的真实记录）。

## 四、与 decretum-matrix 强绑定的路径（待实施）

目前是**独立服务**（不侵入仓库核心）。要把它做成 1.1.5 的原生能力，需三步：

1. **命令面清单**：`references/manifests/cli-command-surface.v1.json` 增条目，
   参考既有 `shiguan.archive_dry_run` 形状（`domain: shiguan`、`public_api`、`receipt_schema`、`handler`）。
2. **MCP 注册**：`scripts/court_mcp_server.py` 的 `load_public_tools()` / `invoke_public_tool()` 注册新 tool，
   `list_tools()` 会自动带出（`annotations.readOnlyHint = True`）。
3. **强绑定点**：在 `archive_checkpoint.py` 写入前的口径校验处，
   以 advisory 形式附带 Top-3 对照记录（**只提示、不写入、不阻断**）。

> ⚠️ 第 3 步涉及改变核心流程行为，须走 court 派遣与门下复核，不能由本训练任务直接改。
