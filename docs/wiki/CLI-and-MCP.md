# CLI 与 MCP 说明书

Decretum Matrix 对外提供两个**并列**的传输面：统一 CLI 与只读 stdio MCP。二者共用
`scripts/court_public_api.py` 与同一份命令权威清单，因此语义一致，不互为包装。

```text
references/manifests/cli-command-surface.v1.json   ← 唯一命令权威
        │
        ├── CLI  : scripts/court_cli.py → court_cli_registry.py
        └── MCP  : scripts/court_mcp_server.py → court_public_registry.py
                        └── 共用 court_public_api.py
```

MCP **不 spawn CLI、不解析 stdout**；CLI **不依赖 MCP 进程**。

---

## 第一部分：CLI

### 1.1 入口与调用约定

| 项目 | 值 |
| --- | --- |
| 公开命令 | `decretum-matrix` |
| 源码等价入口 | `python -B scripts/court_cli.py` |
| 命令权威 | `references/manifests/cli-command-surface.v1.json` |
| 注册表实现 | `scripts/court_cli_registry.py` |

```sh
decretum-matrix [--format text|json] <group> <command> [args...]
```

- `--format` 默认 `text`；自动化与验收一律显式用 `--format json`。
- 兼容期内，旧的顶层 court 命令（如 `decretum-matrix status`）仍被接受。
- 若 PATH 里没有 `decretum-matrix`，解析 `npm prefix -g` 下的
  `decretum-matrix.cmd`，**不要**降级为内部 Python 业务脚本。

### 1.2 命令组

| 组 | 用途 | 日常面（默认帮助展示） |
| --- | --- | --- |
| `court` | 开朝、受理、语义门禁、计划复核、状态、结诏 | `open` `status` `plan` `intake-template` `workflow-status` `closeout-session` |
| `office` | 官署生命周期与原生派遣 | `start` `admit` `preload-ack` `native-request` `native-capture` `report` `finish` `close` |
| `shiguan` | 史馆归档、索引、记忆裁定 | `archive-runtime-task` `archive-checkpoint` `query-shiguan-index` `memory-decision` `grow-shiguan-tree` `tidy-shiguan-records` |
| `supercc` | 独立 superCC runtime | `supercc-squad` |
| `install` | 安装、迁移、更新、修复 | `update` `migrate` `rollback` `fix` |
| `check` | 只读门禁与诊断（源码检出） | `doctor` `debug` `all` |
| `release` | 打包与发布产物（源码检出） | 项目阶段命令，按显式命令调用 |

清单中共有 156 条命令，其中大部分是 `unified_compatibility_adapter` 兼容适配器。
默认帮助只展示日常 Skill 面；兼容适配器仍可显式调用，但不应被当作启动依赖。

### 1.3 常用命令速查

```sh
# 开朝与状态
decretum-matrix court open --fast --request-template \
  --task-id <id> --authority <approval|autonomous|super> \
  --behavior <serial|parallel> --worktree <worktree> --task-focus <focus>

decretum-matrix court status --view compact --limit 1 --format json
decretum-matrix court workflow-status --task-id <id> --format json

# 受理与计划
decretum-matrix court intake-template --charter <charter> --format json
decretum-matrix court plan template --task-id <id> --format json
decretum-matrix court plan submit  --task-id <id> --request-file <plan.json> --format json
decretum-matrix court plan review  --task-id <id> --request-file <review.json> --format json
decretum-matrix court plan show    --task-id <id> --format json

# 官署派遣
decretum-matrix office admit --request-file <admit.json> --format json
decretum-matrix office native-request --request-file <selector.json> --format json
decretum-matrix office native-capture --request-file <selector.json> --format json
decretum-matrix office report --request-file <report.json> --format json

# 史馆
decretum-matrix shiguan query-shiguan-index <关键词> --limit 5 --format compact
decretum-matrix shiguan archive-runtime-task --request-file <archive.json> --format json

# 维护（源码检出内）
decretum-matrix check doctor --format json
decretum-matrix install fix --format json          # 只读计划
decretum-matrix install fix --apply --format json  # 显式写入
```

### 1.4 关键参数约定

| 参数 | 约定 |
| --- | --- |
| `--task-id` | 绑定当前任务；跨任务复用会失败 |
| `--request-file` | 请求体为 UTF-8 JSON，**不带 BOM** |
| `--worktree` | 写集为 worktree 相对路径；绝对路径或目录穿越直接失败 |
| `--authority` | 只能取 `approval` / `autonomous` / `super` |
| `--behavior` | 只能取 `serial` / `parallel` |
| `--format` | `text`（默认）或 `json` |

模板参数的作用域不同：`--worktree .` 按 cwd 解析，request-file 里的 worktree 按文件
解析，文档类路径按 skill 根解析。宿主证据可以记录解析后的路径与基准。

### 1.5 退出与错误

- 需要源码检出的命令在安装副本外运行会返回 `source_checkout_required`，
  这是**预期行为**，不是故障。
- 校验失败返回结构化 problem 字符串（如 `missing_arguments:...`、
  `unknown_arguments:...`），用 `--format json` 读取。
- 状态变更必须走 receipt-bound CLI；检查 domain success，不要只检查命令是否打印帮助。

---

## 第二部分：MCP

### 2.1 服务器与协议

| 项目 | 值 |
| --- | --- |
| 服务器入口 | `scripts/court_mcp_server.py` |
| 传输 | stdio |
| 投影实现 | `scripts/court_public_registry.py` |
| 主协议版本 | `2026-07-28`（现代、无状态） |
| 兼容协议版本 | `2025-11-25` |
| 工具数 | 13（全部 `read_only`） |
| 服务器身份 | `decretum-matrix` |

现代 wire 要求每个请求携带
`_meta.io.modelcontextprotocol/protocolVersion` 与
`_meta.io.modelcontextprotocol/clientCapabilities`；`clientInfo` 可省略，但存在时
必须是带非空 `name` / `version` 的 Implementation 对象。

- `server/discover` 已实现，返回支持的版本、tools 能力、服务器身份与公共缓存提示。
- `tools/list` / `tools/call` 返回 `resultType=complete` 加自描述服务器元数据。
- `tools/list` **不分页**：省略 `cursor` 或传空串；非空 cursor 返回 `-32602`。
- 畸形 JSON 为 `-32700`；非法 JSON-RPC 请求（含缺失或 null id）为 `-32600`。

发送 `initialize` 的客户端选择 legacy 每进程语义，须再发
`notifications/initialized`，之后可不用现代 `_meta` 调用 `tools/list` / `tools/call`。
现代与 legacy 回执分别记录。

### 2.2 工具矩阵（13 个，全部只读）

| 工具 | 用途 | 参数（`*` 为必填） |
| --- | --- | --- |
| `court.capsule_validate` | 校验 P00 不变量胶囊 | `charter*` `value*` |
| `court.closeout_checklist` | 返回十四行结诏清单与缺失项 | `task_id` |
| `court.command_help` | 返回公开 court 命令帮助 | 无 |
| `court.dispatch_plan_validate` | 只读校验派遣计划 | `entries*` `authority` `behavior` |
| `court.intake_validate` | 校验受理载荷（会话门禁 + 胶囊） | `charter*` `intake_value*` `capsule_value` |
| `court.semantic_context_validate` | 校验绑定诏令编号的语义上下文 | `value*` |
| `court.status` | 读取当前 court 运行时状态 | `view` `limit` |
| `court.workflow_status` | 读取任务/会话/编号与计划复核绑定 | `task_id*` |
| `memory.scan` | 报告记忆扫描边界（不读私有正文） | 无 |
| `shiguan.archive_dry_run` | 报告归档边界，不写史馆 | 无 |
| `shiguan.entries_query` | 元数据投影查询史馆条目 | `query*` `limit` |
| `shiguan.iku_candidates` | 扫描 IKU 占位候选（dry-run） | `scope` `limit` |
| `shiguan.query` | 查询公开史馆索引记录 | `terms` `limit` |

参数枚举：

- `court.status.view`：`compact` | `full`（默认 `full`，`limit` 默认 12）
- `court.dispatch_plan_validate.authority`：`approval` | `autonomous` | `super`
  （默认 `approval`）
- `court.dispatch_plan_validate.behavior`：`serial` | `parallel`（默认 `serial`）
- `shiguan.iku_candidates.scope`：`plan-archives`（默认）

### 2.3 调用示例

```json
{ "name": "court.status", "arguments": { "view": "compact", "limit": 1 } }
```

```json
{
  "name": "court.dispatch_plan_validate",
  "arguments": {
    "authority": "autonomous",
    "behavior": "serial",
    "entries": []
  }
}
```

成功返回形如：

```json
{
  "ok": true,
  "tool": "court.status",
  "command_id": "court.court-runtime",
  "api": { "...": "工具自身载荷" },
  "dry_run": false,
  "write_enabled": false
}
```

失败返回 `{"ok": false, "problem": "<bounded error code>"}` 且 `isError=true`。
`write_enabled` 恒为 `false`，这是 MCP 面的硬保证。

### 2.4 只读保证与审计

- MCP 只投影命令清单中显式标记 `mcp` 且 `side_effect=read_only` 的条目；
  非只读投影在加载时直接报错。
- 输入参数按闭合 schema 校验：未知参数返回 `unknown_arguments:*`，
  缺参数返回 `missing_arguments:*`。
- 每次 `tools/call` 都会尽力写一条 metadata-only 审计 journal 到 court-runtime 根。
  审计只记录工具名、协议、成功/错误码与 actor，**不记录参数与结果正文**，
  也不记录其摘要；审计失败不会中断工具调用。
- `court.status` 会附带 `transport_corruption` 标记，用于发现编码损坏。

### 2.5 边界

MCP 面**只做只读校验、状态读取与史馆检索**。任何状态变更、归档写入、安装或发布都必须
走 CLI 或宿主入口；MCP 永远不会替你执行写入。

### 2.6 验证 MCP 面

源码检出内可用 wire 探针：

```sh
python -B scripts/probe_court_mcp_modern_wire.py --host-state source_checkout
python -B scripts/check_court_mcp_server.py
```

探针只证明源码 wire 行为；它**不证明** Codex / CC Switch 已加载服务器或工具已可见。
宿主可见性需要单独的宿主回执。
