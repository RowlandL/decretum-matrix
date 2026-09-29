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

**`refresh_transaction` 的产生者**：**在交付物中不存在**（2026-09-29 核实）。

- `scripts/court_capability_recruitment.py` 共 45 个函数，其中**只有 `_refresh_transaction_errors`** 与本 schema 相关 —— 它是**纯校验器**，无构造器、无写盘。
- 该模块**没有任何 CLI/entrypoint**，只被两个检查器导入：`check_capability_index_gate.py`、`check_court_capability_recruitment.py`。
- 命令面 162 条里与本主题相关的仅 4 条，其中 3 条为 `read_only` 检查器，唯一可写的是 `refresh-capability-registry`（即消费者本身）。
- 全机扫描：**没有任何文件包含 `capability.refresh_transaction` 这一 schema** —— 该事务在本机从未被产出过。
- ⚠️ 本文件早先版本曾写"产生者是 `court_capability_recruitment.py`"，那是**未经验证的推断，已证伪并更正**。

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
- 之所以不能"顺手造一个"：校验器要求 `registry_generation`、`source_paths`（必须**精确等于** 818 条记录源路径的排序列表）、`installation_id` 三者同时精确匹配（`refresh_capability_registry.py:768-777`）。这是**设计上的循环绑定**——事务只能由一次**真实已提交**的招募事务产出，而该产出流程不在交付物内。
- 本能力为 **advisory / read_only / `execution_authority=false`**：刷新只决定它能否被检索到，不授予任何执行权威。
- 刷新不改动 `CONTENT_TAXONOMY`，不写史馆记录。

## 五点五、这意味着什么

| 事实 | 影响 |
| --- | --- |
| 能力**已可用**：CLI `query-shiguan-recall` + MCP `shiguan.recall` / `shiguan.recall_stats` 均已注册并通过 CI | 未登记**不影响调用** |
| 未登记于 `installed-capabilities-manifest.json`（577 条）| 仅影响**能力索引/开朝/派遣检索的可发现性** |
| 写入路径在本版本**结构不可达** | 需求方需二选一：**实现产出者**（bounded 产品变更）或**接受不登记** |

## 六、附带说明（供派遣时知情）

| 事实 | 影响 |
| --- | --- |
| 召回引擎需 torch + 322M 编码器 | 作为本地只读服务运行（默认 `http://127.0.0.1:8767`）；服务未启动时 CLI/MCP **fail-closed** |
| 模型与 venv **不入安装投影** | 换机器需本地 bootstrap，否则服务无法启动（会明确报错，不静默降级）|
| 相似度绝对值不可作阈值 | mmBERT 句向量各向异性，不相关文本余弦亦达 0.93+；只使用 Top-k 相对排序 |
| 实测质量 | 参照集 901 条 / 查询集 126 行：同谱系命中 @1 0.444、@3 0.706、@5 0.810 |

## 七、已解决（2026-09-29）

产出者已补齐并实跑通过；前文第三、五、五点五节描述的阻塞**已不再成立**，保留作变更记录。

**新增产出者**：`scripts/authorize_capability_refresh.py`（命令 `authorize-capability-refresh`）
发 `court.capability.refresh_transaction.v1`，`status: AUTHORIZED`，绑定 managed installation binding
与实时扫描的精确 `source_paths`；**它不写注册表**。

**消费侧同时修掉三个缺陷**（否则即使回执完全正确也永远无法提交）：

| # | 缺陷 | 影响 |
| --- | --- | --- |
| 1 | `refresh()` 把 `codex_home()`（`~/.codex`）当 binding 的 `home_root` | 任何绑定都报 `CANONICAL_ROOT_INVALID` |
| 2 | 事务加载未传 `expected_path`，而该参数实为必填 | 恒返回 `None`，`--apply` 永久 `BLOCKED` |
| 3 | 写字路径校验未传 `home_root` | 恒抛 `PermissionError: HOME_ROOT_REQUIRED` |

**实跑结果**（本机）：

```
authorize-capability-refresh --apply            -> AUTHORIZED, 818 records, 446 source_paths
refresh-capability-registry --apply --yes ...   -> COMMITTED, 818 records, 5 产物
installed-capabilities-manifest.json            -> 含 shiguan-recall x2
check-capability-index-gate --query ...         -> 命中 shiguan-recall,
                                                   court_units ["Shiguan"],
                                                   fit_status STRONG_LOCAL_FIT,
                                                   dispatchable false   ← advisory 能力正确不可派遣
```

**职责分离仍然成立**：授权命令只发回执、不写注册表；刷新命令只消费回执，并在落盘前把回执升格为
`COMMITTED`。两者是不同命令、不同职责，任一方都不自证。

