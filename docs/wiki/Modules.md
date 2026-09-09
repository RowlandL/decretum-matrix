# 功能模块

本页说明 Decretum Matrix 的七个功能大模块**分别用于干什么**。模块划分与统一 CLI
的命令组一一对应，并与五层架构逐层落位。

> 阅读顺序建议：先看「模块总览」，再按需要跳到具体模块。日常使用只需要 `court` 与
> `office`；其余模块按任务阶段调用。

## 模块总览

| 模块 | 一句话用途 | 主要使用时机 | 是否日常必需 |
| --- | --- | --- | --- |
| `court` | 任务治理主线：开朝、受理、语义门禁、计划复核、状态、结诏 | 每次任务全程 | 是 |
| `office` | 官署生命周期：派遣准入、预载、回奏、原生派遣与捕获 | 需要多官署协作时 | 是 |
| `shiguan` | 史馆与记忆：归档、索引检索、记忆裁定、台账整理 | 任务收口与知识复用 | 按需 |
| `supercc` | 独立 superCC runtime（zellij + squad 协作面） | 显式选择 superCC 时 | 否 |
| `install` | 安装、迁移、更新与修复 | 首次安装与版本升级 | 按需 |
| `release` | 打包与发布产物构建 | 源码仓库发布阶段 | 否（源码阶段） |
| `check` | 只读门禁与诊断 | 源码仓库验收与排错 | 否（源码阶段） |

---

## 1. court —— 任务治理主线

**用途**：把一次任务从「受理」到「结诏」的全过程固定成可追溯状态机，承载 P00 语义
门禁、权限绑定、计划与复核、以及最终结果裁定。

日常命令：

| 命令 | 作用 |
| --- | --- |
| `court open` | 开朝：给出有界指引与 CLI/MCP 路由 |
| `court intake-template` | 生成受理模板（`--charter` 必填） |
| `court plan` | 计划与复核：`template / submit / review / status / show` |
| `court status` | 读取当前运行时状态（默认文本，`--format json` 结构化） |
| `court workflow-status` | 读取任务/会话/编号与计划复核绑定 |
| `court closeout-session` | 显式关闭一次会话中仍开放的内容 |

要点：

- 开朝后按固定层级推进：用户 → 太子 → 三省；尚书 → 六部；六部 → 工坊/工匠。
- `court semantic checkpoint/verify` 的 VERIFIED/DISPATCHABLE **只证明 P00 语义门禁**，
  不证明三省已履职；官署回奏需要真实宿主证据或显式 `serial_inline`。
- 状态变更走 receipt-bound CLI；`court open --fast` 只是 preparation。

---

## 2. office —— 官署生命周期

**用途**：管理每个官署实例从派遣准入到结差的完整生命周期，并把真实宿主派遣与回奏
证据绑定到同一任务语义上。

日常命令：

| 命令 | 作用 |
| --- | --- |
| `office start` | 启动官署生命周期记录 |
| `office admit` | 派遣准入：校验直接上级、写集、预算与层级 |
| `office preload-ack` | 预载确认（身份预载回执） |
| `office native-request` | 生成宿主原生派遣请求（`--request-file`） |
| `office native-capture` | 捕获宿主原生执行证据 |
| `office report` | 官署回奏 |
| `office finish` / `office close` | 结差与关闭 |

要点：

- 派遣层级受硬约束：太子只派三省；只有尚书可派六部；六部只能派自己的下级。
- 父级 `shangshu/` 与子级 `ministries/<role>/` 的写入集必须互不重叠。
- 回奏必须来自当前宿主 trace；不得编造宿主 ID 或结果。证据缺失保持可重试的 PENDING。

---

## 3. shiguan —— 史馆与记忆

**用途**：把任务事实、决策、验证结果和可复用经验归档为可检索记录，并提供
metadata-first 的长期认知召回。史馆是 advisory / preserve-only，没有执行权。

日常命令：

| 命令 | 作用 |
| --- | --- |
| `shiguan archive-runtime-task` | 标准任务结诏归档（首选） |
| `shiguan archive-checkpoint` | 独立记录归档（非标准任务） |
| `shiguan query-shiguan-index` | 检索史馆索引（`--format compact/detail/json`） |
| `shiguan memory-decision` | 记忆裁定：WRITE / PROPOSE / SKIP / DEFERRED |
| `shiguan grow-shiguan-tree` | 生长史馆树 |
| `shiguan tidy-shiguan-records` | 台账整理 |

要点：

- 默认数据根：`<home>/.agents/court-shiguan/decretum-matrix/references`。
- 安装与升级不得读取、打包或覆盖 private/pending 正文，也不得覆盖史馆实录。
- 没有不可伪造的主机授权，不得读取、移动、删除或标记 pending/private 正文。
- 不得保存 secrets、原始私密日志、瞬态输出、猜测或未获批个人数据。

---

## 4. supercc —— 独立 superCC runtime

**用途**：承载 super-execution（superCC）协作面。它是**独立 runtime 与独立入口**，
不是第四种权限，与 native 互斥、不探测候选、不切换、不回退。

日常命令：

| 命令 | 作用 |
| --- | --- |
| `supercc supercc-squad` | superCC squad 入口 |

要点：

- 正常 superCC 需要当前明确选择，以及 `zellij` + `squad` / client 证据。
- 缺少 `zellij` 或 `squad` 时必须如实报告为降级或不可进入正常 superCC，
  不得伪造成功。
- 普通 `super parallel` 不加载 superCC pane/watchdog/show-delay/closeout-silence 流程。

---

## 5. install —— 安装与迁移

**用途**：把源码或发布产物投影到受治理的 skill 根，并支持迁移、更新与回滚。

日常命令：

| 命令 | 作用 |
| --- | --- |
| `install update` | 更新安装投影 |
| `install migrate` | 迁移（含旧 locator 兼容） |
| `install rollback` | 按回执回滚 |
| `install fix` | 修复安装状态（默认只读计划，写入需 `--apply`） |

要点：

- `fix` 默认是只读计划，任何写入都需要显式 `--apply`。
- 每次调用都会在 `<git-mirror>/.repo-control/events/decretum-matrix/` 下写入
  `workspace.operation_event.v1` 的 intent/result 对。
- 安装默认只投影共享 `.agents` 与 current-tool 根；额外根需要显式授权。

---

## 6. release —— 打包与发布

**用途**：构建可发布产物（ZIP / npm 包 / 发布清单），并生成发布元数据。
属于**源码仓库阶段**命令，不在安装后的运行面内。

| 命令 | 作用 |
| --- | --- |
| `release package-skill` | 打包 skill ZIP |
| `release build-npm-package-mjs` | 构建 npm 包 |
| `release build-release-artifacts` | 构建发布产物 |
| `release release-payload-manifest` | 生成发布载荷清单 |

要点：

- 打包前必须确认包内没有本机私有史馆正文、原始日志、密钥、运行账本或未清洗导入队列。
- 正式 ZIP 名为 `decretum-matrix-<version>.zip`，内部 canonical 根为 `decretum-matrix/`。
- 打包、tag、GitHub Release、npm 发布和活动安装分别由独立回执或远端回读证明。

---

## 7. check —— 只读门禁与诊断

**用途**：源码仓库的只读校验面。统一入口收敛为 `doctor` / `debug` / `all`，
底层保留上百个细粒度只读检查。

| 命令 | 作用 |
| --- | --- |
| `check doctor` | 比对源码契约、Git 身份、完整受管投影、Codex MCP 配置/运行时探测与硬编码路径策略 |
| `check debug` | 在 doctor 基础上追加 Python/平台/Git/源码解析证据，全程只读 |
| `check all` | 运行全量门禁 |

要点：

- 两个命令都会脱敏 secrets，且从不读取 private/pending 正文。
- 需要源码检出（source checkout）；在安装副本外运行会返回
  `source_checkout_required`，这是预期行为而非故障。
- 单个细粒度检查仍可显式调用，例如
  `python -B scripts/check_portability.py .`。

---

## 五层架构落位

| 层 | 承担模块 | 说明 |
| --- | --- | --- |
| 1. 通用任务治理框架 | `court`、`office` | 默认实现为 `three-departments-six-ministries` |
| 2. 史馆 GBrain | `shiguan` | 共享但无执行权的长期认知 |
| 3. 治理实现 | 清单驱动 | `references/manifests/governance-implementations.v1.json` |
| 4. 能力与运行适配层 | `install`、`check` | 投影、迁移、宿主适配与只读门禁 |
| 5. 呈现层 | `release`、`docs/` | 对外文档与发布产物 |

## 模块选择速查

| 你的目标 | 用哪个模块 |
| --- | --- |
| 开始一次多步骤任务 | `court open` → `court plan` |
| 需要多官署协作 | `office admit` → `office native-request` |
| 只想看当前状态 | `court status --view compact --limit 1` |
| 任务收口并留档 | `shiguan archive-runtime-task` |
| 查历史经验 | `shiguan query-shiguan-index <关键词>` |
| 换机器 / 升级版本 | `install update` / `install migrate` |
| 打包发布 | `release package-skill` |
| 怀疑环境不对 | `check doctor`（源码检出内） |
