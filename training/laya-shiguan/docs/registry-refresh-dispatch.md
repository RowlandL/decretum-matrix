# 能力索引刷新 · 派遣说明

> 目的：把 `shiguan-recall` 能力写入能力注册表。本文件是**派遣输入**，不是执行回执。

## 一、目标

在 `installed-capabilities-manifest.json` 中登记 `shiguan-recall` 能力，使其可被诏令矩阵的能力索引 / 开朝 / 派遣检索到。

| 项 | 值 |
| --- | --- |
| 注册表路径 | `~/.agents/court-shiguan/decretum-matrix/references/installed-capabilities-manifest.json` |
| 当前条目数 | **577**（经查 **不含** `shiguan-recall` / `query-shiguan-recall` / `laya`）|

## 二、当前已完成（无需重做）

| 项 | 状态 |
| --- | --- |
| 能力声明件 `training/laya-shiguan/SKILL.md`（`name: shiguan-recall`）| ✅ 已提交（`f2bd9a5`）|
| 命令面条目 `shiguan.query-shiguan-recall`（`side_effect: read_only`）| ✅ 已生成 |
| MCP 投影 `shiguan.recall` / `shiguan.recall_stats` | ✅ 已注册（MCP 工具数 13 → 15）|
| 安装投影（`shared_agents` / `portable_current_tool` = 410 条）| ✅ 闭环校验 PASS |
| 安装态同步（2 个根：`.agents` / `.codex`）| ✅ 已应用，文件已验证 |

## 三、阻塞点与所需引用

```
python -B scripts/commands/refresh_capability_registry.py --apply --yes
→ BLOCKED / BOUND_INSTALLATION_AND_REFRESH_REFERENCES_REQUIRED
→ {"count": 0, "write_enabled": false}
```

该命令要求**两个**绑定引用同时有效：

| 引用 | Schema | 现状 |
| --- | --- | --- |
| `installation_binding` | `court.installation_binding.v2` | ✅ 已有：`~/.agents/install-receipts/decretum-matrix/installation-binding-v2.json` |
| **`refresh_transaction`** | `court.capability.refresh_transaction.v1` | ❌ **缺** |

**`refresh_transaction` 的产生者**：`scripts/court_capability_recruitment.py`（吏部/户部能力招募 registry pass，全仓 27 处引用该 schema）。

## 四、执行步骤（须由 court 派遣，不得由训练任务代办）

1. **吏部/户部 registry pass**：由能力招募流程产出 `court.capability.refresh_transaction.v1` 回执。
2. **携带两引用执行刷新**：

   ```bash
   python -B scripts/commands/refresh_capability_registry.py --apply --yes \
     --installation-binding <installation-binding-v2.json 路径> \
     --refresh-transaction <refresh_transaction 路径>
   ```

3. **验收判据**（三条全中才算完成）：
   - `installed-capabilities-manifest.json` 中含 `shiguan-recall`
   - `python -B scripts/check_unified_cli.py` 仍全 PASS
   - `python -B scripts/check_install_projection_closure.py` = `INSTALL_PROJECTION_TRANSITIVE_CLOSURE=PASS`

## 五、硬边界

- ⛔ **不得伪造 `refresh_transaction`**。手工构造该回执等于伪造治理证据，会使 registry pass 失去可追溯性。
- 本能力为 **advisory / read_only / `execution_authority=false`**：刷新只决定它能否被检索到，不授予任何执行权威。
- 刷新不改动 `CONTENT_TAXONOMY`，不写史馆记录。

## 六、附带说明（供派遣时知情）

| 事实 | 影响 |
| --- | --- |
| 召回引擎需 torch + 322M 编码器 | 作为本地只读服务运行（默认 `http://127.0.0.1:8767`）；服务未启动时 CLI/MCP **fail-closed** |
| 模型与 venv **不入安装投影** | 换机器需本地 bootstrap，否则服务无法启动（会明确报错，不静默降级）|
| 相似度绝对值不可作阈值 | mmBERT 句向量各向异性，不相关文本余弦亦达 0.93+；只使用 Top-k 相对排序 |
| 实测质量 | 参照集 901 条 / 查询集 126 行：同谱系命中 @1 0.444、@3 0.706、@5 0.810 |
