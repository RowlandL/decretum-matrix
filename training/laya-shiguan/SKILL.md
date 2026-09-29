---
name: shiguan-recall
description: 史馆对照决策检索（Laya advisory）。给定一条待判定的史馆实录文本，用本地 mmBERT 编码器在 1129 条历史实录中做 kNN 检索，返回最相似的记录及其诏令编号、五段谱系、记忆裁定、风险/知识/优先级等级。只读、无执行权，供诏令矩阵流程中的对照决策使用。
license: AGPL-3.0
metadata:
  version: beta1.1.5
  author: RowlandL
---

# 史馆对照决策检索 · shiguan-recall

## 何时用

- 判定一条新史馆实录的**谱系 / 记忆裁定 / 三级等级**之前，先看历史同类记录是怎么定的
- 需要回答「这条内容历史上有没有先例」
- 分类器给出 `low_confidence` / `tie` / `unknown` 时，作为人工或门下裁定的参照

## 不做什么

- `authority=advisory`、`execution_authority=false`：**只提供对照参考**
- 不写史馆、不改 `CONTENT_TAXONOMY`、不替代门下裁定、不提供执行权威
- ⚠️ **相似度绝对值不可当阈值**（mmBERT 句向量各向异性，不相关文本余弦也有 0.93+），只用 Top-k 相对排序

## 接口

### MCP（诏令矩阵自带服务器，非独立注册）

| 工具 | 入参 | 返回 |
| --- | --- | --- |
| `shiguan.recall` | `state`(必填)、`k`(1-20，默认 5)、`same_topic`(bool) | 最相似历史记录及裁定 |
| `shiguan.recall_stats` | 无 | 索引统计 |

### CLI

```bash
python -B scripts/query_shiguan_recall.py --state "<实录文本>" --k 5
python -B scripts/query_shiguan_recall.py --state-file <utf8 文件> --format text
python -B scripts/query_shiguan_recall.py --stats
```

## 运行前提

召回引擎需要 torch + 322M 编码器，作为**本地只读服务**运行（默认 `http://127.0.0.1:8767`）：

```bash
python -B training/laya-shiguan/service/serve_http.py --port 8767
```

MCP 服务亦可用 `training/laya-shiguan/service/mcp_server.py`（stdio）直接接入任意 MCP 客户端。

服务未启动时 CLI/MCP **fail-closed**，返回 `recall_service_unavailable` 并附启动提示，不静默降级。

## 索引与资产

| 项 | 位置 |
| --- | --- |
| 语料 | `training/laya-shiguan/corpus/corpus-v2.jsonl`（1291 条，其中 **1129 条真实史馆记录入索引**）|
| 向量缓存 | `training/laya-shiguan/runs/recall-index.pt`（按语料 size+mtime 自动失效）|
| 编码器 | `training/laya-shiguan/models/laya-multilingual/`（0.63GB，**不入库**，需本地 bootstrap）|
| 虚拟环境 | `training/laya-shiguan/.venv`（Python 3.12 + torch 2.14.0+cu130 + laya 0.3.21）|

> ⚠️ **安装态不含大件资产**（模型与 venv 均不入投影）。换机器需先本地 bootstrap 模型与 venv，否则服务无法启动——CLI 会 fail-closed 提示。

## 实测质量

参照集 901 条真实史馆记录，查询集 126 行 val（按 topic 分组切分，无泄漏）：

| k | 同谱系命中 | 同门命中 | 同志命中 |
| --- | --- | --- | --- |
| 1 | 0.444 | 0.452 | 0.476 |
| **3** | **0.706** | 0.714 | 0.754 |
| **5** | **0.810** | 0.817 | 0.841 |
| 10 | 0.857 | 0.873 | 0.897 |

## 环境变量（全部可选，便于移植）

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `SHIGUAN_RECALL_URL` | 召回服务地址 | `http://127.0.0.1:8767` |
| `SHIGUAN_RECALL_TIMEOUT` | 请求超时秒数 | `60` |
| `SHIGUAN_REFERENCES_ROOT` | 史馆 references 根（语料构建用）| 见 `_shiguan_paths.py` |
| `COURT_SHARED_SHIGUAN_ROOT` / `SHIGUAN_SHARED_ROOT` | 官方共享根（自动补 references）| 同上 |

## 相关文档

- 检索能力实现与限制：`training/laya-shiguan/service/README.md`
- 新分类判定规则（动态增长）：`training/laya-shiguan/docs/new-class-rule.md`
- 分类错误审计与纠错集：`training/laya-shiguan/corpus/audit-report.md`、`corpus/r4-adjudication.md`
