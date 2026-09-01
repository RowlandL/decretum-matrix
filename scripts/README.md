# Decretum Matrix scripts 分层与整合纪律（A+B 结构整理）

> 2026-09-01 · 分支 release/beta1.0.8 · 依据：结构审查评估（A+B 方案，用户批准）
> 权威入口：`court_cli.py`（CLI）与 `court_mcp_server.py`（MCP）；权威注册表：
> `references/manifests/cli-command-surface.v1.json`（domain/group/command 分层）。

## 1. 为什么有这份文档

`scripts/` 现有 198 个 `.py`（152 入口 + 46 库），历史上平铺在根目录，入口/库/门禁/
服务混放，人眼难以看出"递进层级"。本文件固化**四层逻辑分层**与**新增/迁移纪律**，
统一入口（CLI/MCP）与"一个命令一条注册"的硬门禁（`check_unified_cli`）。

## 2. 四层逻辑分层（权威层级）

```
L0 入口层   court_cli.py / court_mcp_server.py           —— 唯一对外调用面
L1 适配层   court_cli_registry / court_public_api /
            domain_ledger_api / court_diagnostics        —— 注册/投影/适配
L2 领域层   court_* / shiguan_* / supercc_* / ensure_*   —— 命令与服务实现
L3 门禁层   check_*                                      —— 回归/门禁（CLI check 组 + release gate）
L4 库层     无 __main__ 的模块（46 个）                   —— 共享库，禁止直接当命令运行
```

层间依赖只允许**自上而下**（L0→L1→L2→L3→L4），禁止下层反向依赖上层；
`L4 库层` 保持 `scripts/` 根（全部脚本 `from <lib> import ...`，物理移动会破坏 import）。
入口脚本（L2/L3 中带 `__main__` 的）可按方案 B 迁移到子目录
（`scripts/commands/`、`scripts/checks/`、`scripts/services/`），根目录保留兼容壳。

### 目录现状（B 全量迁移后，2026-09-01）

```
scripts/
  README.md
  court_cli.py / court_cli_registry.py / court_mcp_server.py   L0/L1 根驻留（自举/入口）
  check_unified_cli.py                                          L3 根驻留（自举门禁）
  court_runtime.py / court_session_closeout.py / archive_checkpoint.py  L2 根驻留（python_module 特殊 handler）
  <入口名>.py（约 145 个）                                       根兼容壳（转发到子目录真身）
  checks/    （86 个 check_* 真身）                            L3 门禁
  commands/  （47 个命令真身）                                   L2 命令
  services/  （12 个守护/服务真身，RETIRED 不注册命令）           L2 服务
  其余 46 个无 __main__ 模块                                     L4 库（保持根，禁止移动）
```

## 3. 新增/迁移纪律（硬性）

1. **新增脚本必须注册**：`check_unified_cli --all` 的 `CLI_ENTRYPOINT_COVERAGE`
   会把未注册入口判 FAIL；新增入口必须 `--write-manifest` 后随提交落盘。
2. **对外调用只走 CLI/MCP**：操作/查询走 `court_cli.py <group> <command>`
   （或 `python -B scripts/court_cli.py ...`）；agent 走 MCP 工具；门禁走
   `court check <name>`（等价 `python scripts/check_<name>.py`）。
3. **门禁调用迁移**（从直接 `python scripts/check_x.py` 切到 CLI check 组）：
   见 §4 清单；历史交接文档中的直接调用路径作为历史记录保留不改。
4. **物理迁移（B）规则**：
   - 只迁移**入口脚本**（带 `__main__`）；库模块不动。
   - 真身进子目录后必须注入 `scripts/` 根到 `sys.path`（否则根库 import 失败）。
   - 根目录保留兼容壳（转发 `main()`），壳路径必须加入
     `check_unified_cli.RETIRED_COMPATIBILITY_ENTRYPOINTS`，避免被重复发现。
   - 迁移后同步重生成：CLI surface manifest、install-projection、source-state-budget
     （source_lines 键）、release-payload manifest，并 `sync_active_copies --write`。
5. **共享抽取**：check_* 中重复的 fixture/工具抽到 L4 库（如已有 `shiguan_entry_utils`、
   `court_file_lock` 先例），禁止在门禁内联大段复制。
6. **路径纪律（强制）**：任何路径定位一律相对——`Path(__file__).resolve()` /
   `parents[N]`（子目录真身已注入 `scripts/` 根）、`Path.home()`、环境变量
   （如 `COURT_TOOL_INSTALL_DIR`）；**禁止新增写死绝对路径**（如 `C:\...`）。
   测试中故意构造的"绝对路径负例"（验证不得泄漏/必须拒绝）除外，但须注释说明。
   壳与注入块统一使用 `Path(__file__).resolve().parent/parents[1]` 模板，不得引入
   机器特定路径。

## 4. 门禁调用迁移清单（逐步切到 CLI check 组）

`court check <full-command-name>`（命令全名带 `check-` 前缀）与
`python scripts/check_<name>.py` 等价（isolated_subprocess）。
建议发布/交接文档命令清单统一写为 `python -B scripts/court_cli.py check <name> [args]`，
例如：

| 直接调用（旧） | CLI 等价（新） |
| --- | --- |
| `python scripts/check_shiguan_recall_precision.py --json` | `python -B scripts/court_cli.py check check-shiguan-recall-precision --json` |
| `python scripts/check_governance_framework.py --json` | `python -B scripts/court_cli.py check check-governance-framework --json` |
| `python scripts/check_court_mcp_server.py --json` | `python -B scripts/court_cli.py check check-court-mcp-server --json` |
| `python scripts/check_source_state_budget.py --json` | `python -B scripts/court_cli.py check check-source-state-budget --json` |

迁移节奏：新文档一律用 CLI 形式；旧文档历史记录不改；CI/脚本批量替换在发布后统一执行。

## 5. 与既有契约的关系

- `cli-command-surface.v1.json`：唯一权威命令注册表（domain/group/command/handler）。
- `install-projection.v1.json` / `source-state-budget.v1.json` / `release-manifest.json`：
  路径绑定在 B 迁移时同步重生成，禁止手工漏改。
- `check_unified_cli.py`：入口覆盖/重复/漂移门禁，迁移必须保持 `--all` PASS。
