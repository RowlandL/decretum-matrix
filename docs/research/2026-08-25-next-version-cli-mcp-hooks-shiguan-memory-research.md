# Decretum Matrix 下一版本开发调研报告

**日期**：2026-08-25
**项目**：`decretum-matrix`（诏令矩阵）
**当前工作树**：`release/beta1.0.7`，HEAD `956f3e0`
**控制面版本声明**：`O:\gitmirror\workspace.yaml` 仍声明 `beta1.0.6`。这是 checkout-version drift，不能通过下调 `workspace.yaml` 解决；本报告只记录并提出后续治理动作。
**报告性质**：开发调研与下一版本方向，不是发布批准，不是 capability evidence receipt，也不把计划描述提升为已实现能力。

## 1. 调研目标

本次调研回答四个问题：

1. 已建立图谱能否为下一版本提供真实方向，而不是只做展示。
2. 现行脚本/CLI 为什么仍可能被错误调用，如何降低误路由、错 cwd、错 receipt、错身份标签。
3. MCP 或 hooks 是否应取代现有方案，还是应作为受限适配层。
4. 史馆的记忆架构如何从“设计完备、落地感不足”推进到可验证闭环。

调研遵循当前已安装的 `C:\Users\32893\.agents\skills\decretum-matrix\SKILL.md`、graphify 产物和仓库内的治理参考。所有产品能力判断均按以下分类：

- `[CONTROL_PLANE]`：工作区、层级、分支、证据与授权约束。
- `[PLANNED_UNVERIFIED]`：需要实现或补证的产品行为。
- `[VERIFIED_CAPABILITY]`：只有绑定当前代码、typed tests、install projection、runtime receipt 的 hash-bound receipt 才能使用。本报告没有新增此类声明。

## 2. 结论先行

### 2.1 下一版本的主方向

下一版本应采用 **“typed CLI resolver first，MCP facade second，hooks advisory only，Shiguan end-to-end evidence third”** 的路线：

1. **先收紧统一 CLI 路由**：`scripts/court_cli.py` 继续是公开入口，`court_cli_registry.py` 继续是唯一解析器；脚本只做内部 handler，不再成为平行语义入口。
2. **再提供本地 MCP 薄适配器**：MCP 只调用已经通过 registry 解析的 typed command，不建立第二套 authority、ledger、memory store 或 dispatch hierarchy。
3. **hooks 只做提示和派生刷新**：可用于 Git commit 后的 graph/index refresh marker 或一致性检查，但不能授予执行权、写入记忆、代替门下审批，也不能被当作必达触发器。
4. **把史馆记忆闭环做成可验收的五段式流水线**：`scan -> adjudicate -> apply -> verify -> reconcile`。当前 metadata-only bridge 保留，内容级写回必须经过 Menxia receipt、原生存储复读和双侧 transaction receipt。

### 2.2 MCP 与 hooks 的选择

**不建议把现有方案整体改造成 MCP 或 hooks。建议混合形态：**

| 方案 | 适合的职责 | 主要优点 | 主要风险 | 结论 |
|---|---|---|---|---|
| 直接脚本 | 内部实现、一次性检查、兼容旧入口 | 成本低、便于逐步收敛 | 入口多、参数/cwd/身份易错 | 保留为内部 handler |
| Typed CLI | 人工、CI、自动化的规范入口 | 可审计、可复现、容易做 receipt | 需要清理 legacy 兼容面 | **下一版本基线** |
| 本地 MCP | 宿主 agent 的结构化调用 | 参数 schema、工具发现、结果结构稳定 | 容易形成第二入口或越权写入 | **P1 薄适配器** |
| Git hooks | commit 后提示、派生索引刷新 | 自动化、低侵入 | 可绕过、只覆盖 Git 事件、环境差异大 | **P1 advisory** |
| 全面 MCP 化 | 替代 CLI/脚本 | 表面统一 | authority 分裂、安装与宿主耦合、难回滚 | **不采用** |

## 3. 图谱给出的方向

### 3.1 已建立图谱的有效信息

`graphs/workspace-overview/` 当前记录 95 个节点、152 条边、8 个社区；报告标注约 31% 关系为 inferred，并存在少量 ambiguous 边。最有用的不是“节点数量”，而是跨域桥接：

- **Codex Probe Logs** 连接了技能加载器遍历限制、上下文预算预警和 provider/model 配置。
- **CCSwitch Codex Deep Reset Record** 连接 Codex 运维、API 恢复和探针实验，说明运行时恢复问题不能只在单一脚本里修。
- **Shiguan Record Series / Archive Checkpoint Receipt** 与 Codex/CCSwitch 事件相连，说明史馆应承担跨项目证据索引，但不能反过来成为运行时执行权威。
- 图谱中存在史馆归档 checkpoint 与 Obsidian 同步的模糊桥接；这提示下一版本应把“来源、receipt、投影状态、回读状态”拆成 typed edges，而不是仅用标签相似度推断关系。

### 3.2 图谱的边界

当前图谱主要覆盖工作区报告、探针日志、恢复记录和包清单，**没有直接证明当前 Decretum 脚本已经具备 MCP server 或 Git hook 产品能力**。因此：

- 图谱可以给出风险聚类与研究优先级；
- 图谱不能证明某个脚本“已被正确调用”；
- graphify 的边和社区不能替代 capability evidence receipt；
- 下一版本应把 CLI/MCP/史馆 receipt 作为可被 graphify 读取的结构化来源。

当前 child repo 也没有可作为 A02 恢复权威的 `docs/project-memory.md`；该文件缺失应标记为恢复证据缺口，不应靠旧路径或旧版本假设补全。

## 4. 现行实现诊断

### 4.1 统一 CLI 已存在，但兼容面仍过宽

现有 `scripts/court_cli.py -> scripts/court_cli_registry.py` 已经具备 registry-first 形态，manifest 也记录了 `handler`、`legacy_path`、`receipt_schema`、`side_effect` 等字段。但风险仍在：

1. registry 为兼容旧命令保留 `_legacy_runtime` fallback，未知或无法解析的 court 命令可能回落到旧 runtime。
2. `command_cwd()` 会按 group 改变工作目录；同一用户输入在不同 group 下解析到不同相对路径，增加 cwd-sensitive bug。
3. manifest 同时存在 `decretum.cli.result.v1`、`legacy.entrypoint.result.v1`、`court.shiguan_archive_checkpoint_receipt.v1` 等 receipt schema；这对老脚本兼容有价值，但对调用方形成 schema 分支。
4. handler 同时包含 `python_module:` 和 `isolated_subprocess:`；参数序列化、环境继承、退出码和 stdout 结构不完全同构。
5. 公开帮助文本仍展示部分 legacy top-level commands，容易让调用者把内部脚本路径当成长期 API。

**判断**：问题不是“缺一个更漂亮的打包格式”，而是缺一个强制的 **command identity + typed input + typed output + cwd policy + authority binding** 合同。

### 4.2 已有缺陷记录证明“调用错”不是假设

`docs/issues/2026-08-01-local-issue-source-agent-label-fourteen-line-closeout.md` 已记录：

- `archive_checkpoint.py --source-agent "Taizi"` 接受了朝廷角色名，污染 `closeout_identity`、索引 keyword 和后续 writer 检索；
- runtime writer 白名单未在显式参数路径上强制执行；
- 用户侧结诏遗漏十四行模板；
- install projection 漏收 `court-closeout-memorial-format.md`；
- 旧一轮 super-parallel 测试的空 payload 被正确拒绝，补充最小只读 payload 后 9/9 成功。

这说明下一版本必须同时修 **调用契约** 与 **证据/安装投影契约**，单纯把脚本包成一个新 transport 不会消除错误。

### 4.3 MCP 现状

仓库目前有 MCP capability registry、配置解析、招聘/选择逻辑和文档，但未发现一个由 Decretum Matrix 自己提供、可作为产品入口的 MCP server。`references/court-capability-registry.md` 也明确 MCP 是官籍中的一种工坊技艺，必须经过官籍、铨选、差遣、考课。

所以：

- `[PLANNED_UNVERIFIED]` “Decretum MCP server 已可用”不能成立；
- MCP 研究应先做本地 stdio adapter 的 contract prototype；
- adapter 不得绕过 `court_cli_registry` 或直接操作 shared Shiguan。

### 4.4 hooks 现状

仓库没有 Decretum 自己的 `core.hooksPath`、`post-commit`、`post-receive` 或安装型 hook 产品路径。现有 `post-commit` 字样主要出现在测试/发布后校验和事务回调，不构成 Git hook 能力。

因此 hooks 只能作为可选的派生自动化：

- 允许：写一个不可执行的 refresh marker、触发 `graphify --update` 的受控队列、运行只读检查。
- 禁止：直接写入 memory body、改变 authority、替代 Menxia receipt、启动跨项目 agent、把 hook 成功等同于 closeout 完成。
- 必须说明：Git hooks 可被绕过，非 Git 事件不会触发，工作树/网络共享上的 hook 安装还会受到宿主差异影响。

### 4.5 运行载体和准备态边界

日常调用链是 `bin/decretum-matrix.js -> bin/decretum-matrix.py -> scripts/court_cli.py -> court_cli_registry.py -> manifest adapter/runtime`。`bin/decretum-matrix.py` 是 release launcher，不能被误当成日常 CLI；其 postinstall 分支属于安装变更边界。`court open --fast` 是 preparation-only，不能被当成真实 host dispatch 或 office reply。

下一版本的 receipt 应显式区分：

- `phase=PREPARATION_ONLY` 与真实 host delivery；
- machine fact、host delivery、office reply、`serial_inline` 四种 evidence class；
- `canonical` 与 `legacy` route；
- release/install/check 维护命令与 runtime 命令。

hash checker 等 repository-only 门禁不得被 runtime loader、startup、preload 或 sync 导入。superCC 也必须携带 runtime selector、transport、直属上级和 task evidence；裸命令或 readiness profile 不能冒充正常派遣。

### 4.6 本次验证中复现的失败

以下结果是当前工作树的事实，不是理论风险：

- `python -B scripts/court_cli.py --format json help` 进入 legacy runtime，最终报 `help` 不是合法的 `court_runtime` command；`python -B scripts/court_cli.py --format json court --help` 才能得到统一 CLI help。
- `python -B scripts/check_unified_cli.py` 在网络共享的 dubious ownership 下无法读取 Git inventory；使用临时 `safe.directory=*` 环境变量后，CLI coverage、legacy parity、external cwd、archive receipt binding、npm stdio 等检查均 PASS。
- `python -B scripts/check_governance_framework.py --only gbrain --json` 当前失败，原因是 `build_recall_context()` 不接受 `current_decree_sha256` 参数。这是治理检查与 GBrain API 的参数漂移，不能被报告成 GREEN。
- `check_court_dispatch_hierarchy.py` 与 `check_court_result_semantics.py` PASS，但它们只覆盖层级和结果语义，不等于 MCP、hooks 或记忆闭环已完成。

## 5. 史馆记忆审查

### 5.1 已经落地的部分

当前实现已经有几个正确的护栏：

- `internal_memory_shiguan_bridge.py` 默认 metadata-only，记录路径、hash、大小、mtime、表计数、body table 状态，不复制任意原始私密正文。
- `memory_decision.py` 使用 `WRITE | PROPOSE | SKIP | DEFERRED`，可在原生 Codex memories 不可用时留下可追踪的决定记录。
- `query_shiguan_index.py` 默认经 GBrain 查询，GBrain 被定义为 advisory，不拥有执行权。
- Architecture 文档明确：native memory 仍由 Codex/Hermes 各自负责，史馆保存 metadata、裁定、registry 和引用，不把多个原生仓库伪装成一个原子事务。

这些是好的底座，但它们主要证明了 **隐私和权限边界**，还没有证明 **记忆内容能可靠沉淀并在未来被正确召回**。

### 5.2 “没落地”的具体缺口

当前计划文件中仍有未勾选的闭环任务：

1. `court memory scan`、`court memory adjudicate` 尚未形成统一 JSON agent-first 命令族的完整验收证据。
2. `court memory apply`、`court memory verify`、`court memory reconcile` 的 native writeback、复读、双侧 receipt 尚未以当前代码和当前宿主证明。
3. 记忆历史的 `supersedes` 追加修正、`decision_id`、`menxia_receipt` 和 `transaction_id` 需要 RED/GREEN 证明，不能只依赖计划文字。
4. 现有 metadata-only bridge 的 `content_recall_status=metadata_only` 是有意的安全状态，不应被误报成内容级记忆已打通。
5. graph/index/Obsidian 投影属于派生视图，不能作为“记忆已写入”或“语义裁定已批准”的替代证据。
6. A02 execution book 仍把 `A02_RED_EXPECTED_FAILURES=43`、`entries=1033/changed_candidates=493` 和 `GLOBAL_MEMORY_INDEX=FAIL_PENDING_INGESTION` 作为待关闭的 RED/积压证据；逐工具 native Git reciprocal links 也还不能提升为 `MIGRATION_LINKS_VERIFIED`。

### 5.3 建议的可验收记忆模型

```text
native store
    |
    v
memory scan (read-only facts, privacy, dedup, conflict, freshness)
    |
    v
Menxia adjudicate -> decision_id + adjudication_status + menxia_receipt
    |
    v
memory apply -> only approved current-tool/explicit target writeback
    |
    v
native reread + shared/native transaction receipts
    |
    v
memory verify -> recall probe + provenance + content_recall_status
    |
    v
memory reconcile -> complete or rollback partial paired transaction
```

最低字段建议：

`memory_store_id`、`tool_class`、`source_id`、`source_fingerprint`、`content_origin`、`decision_id`、`adjudication_status`、`application_status`、`conflict_status`、`resolution`、`menxia_receipt`、`transaction_id`、`derived_from_record`、`evidence_refs`、`supersedes`、`expires_at`。

`WRITE` 只有在 `adjudication_status=approved`、最新写回授权、适配器能力证据、native reread 和匹配 transaction receipts 同时存在时才合法。任何 tidy/re-evaluation 工具不得原地改写历史裁定。

## 6. 下一版本目标架构

```text
caller (human / agent / CI / optional MCP)
                 |
                 v
        typed command resolver
        - command id
        - schema version
        - authority
        - cwd policy
        - side effect
        - receipt schema
                 |
       +---------+----------+
       |                    |
       v                    v
 court-runtime        shiguan adapters
 state/events         scan/adjudicate/apply/verify/reconcile
       |                    |
       +---------+----------+
                 v
         append-only receipts
                 |
       +---------+----------+
       |                    |
       v                    v
 optional local MCP    optional Git hook
 stdio facade           advisory refresh only
```

约束：

- CLI resolver 是唯一语义入口；
- MCP 只映射 allowlisted command id，不暴露任意脚本路径；
- hook 只能排队/提示派生任务，不能直接形成有效 closeout；
- runtime event store 仍是状态与证据权威；
- Shiguan 是记录/召回层，不是第二 runtime ledger；
- native memory body 保持工具权威，默认不复制到 shared Shiguan。

## 7. 开发路线与优先级

### P0：消除误调用面

1. 为每个公开 command 建立不可变 `command_id`，输入/输出 schema 和 side-effect enum。
2. 普通表面默认拒绝未知 group/command；将 legacy fallback 限定为显式 `--compat legacy` 或 `court legacy`，并在 receipt 中标明。
3. 把 cwd policy 变成 manifest 字段并在 resolver 中输出 `resolved_cwd`；禁止隐式按 group 猜 cwd。
4. 统一 envelope：`decretum.cli.result.v2`，旧 schema 只在兼容边界转换一次。
5. receipt 记录 `route_kind`（canonical/legacy）、manifest id/hash、原始 argv、resolved script、cwd 和 authority。
6. 对 `--source-agent` 做受控 writer 白名单校验；朝廷角色名必须拒收。
7. 把十四行 closeout 模板加入 install projection gate，并为模板漂移添加 RED。
8. 为每个 handler 增加 golden test：命令、参数、cwd、authority、stdout schema、退出码、receipt identity。

### P1：MCP 薄适配器与 hooks 试点

1. 新增本地 stdio MCP adapter（建议独立于核心 runtime 的可选包），只暴露：
   - `court.status`
   - `court.command_help`
   - `shiguan.query`
   - `shiguan.archive_dry_run`
   - `memory.scan`
2. MCP tool schema 必须从同一 manifest 生成；禁止手写第二份参数表。
3. 所有写操作先保持 disabled 或 dry-run；真正的 archive/apply 仍由 CLI authority 和 Menxia receipt 驱动。
4. hooks 先只实现 refresh marker 与只读 gate；触发失败不得伪造成功 receipt。
5. 对 MCP/hook 做 capability registry、install projection、runtime probe 三件套；没有三件套就标 `[PLANNED_UNVERIFIED]`。

### P1：史馆记忆闭环

1. 为五段式 memory pipeline 建立 synthetic native-store fixture。
2. 覆盖空库、重复候选、冲突候选、过期候选、缺 Menxia receipt、native write 部分成功、复读不一致。
3. 强制 append-only correction：新决定必须带 `supersedes`。
4. verify 必须包含原生复读和 recall probe；graph/index 只作为派生证据。
5. 用一份可重放的 typed receipt 证明“候选 -> 裁定 -> 写回 -> 复读 -> 召回”，而不是只证明文件存在。

### P2：宿主适配

1. 只对已被 runtime probe 证明的 Codex/Hermes memory store 开启 native adapter。
2. 每个 `tool_class` 保持独立 native repository、独立 projection namespace 和独立 transaction receipt。
3. 对不支持 native writeback 的宿主保持 `PROPOSE` 或 `DEFERRED`，不创造伪 `WRITE`。
4. 未来如需内容级桥接，另立 explicit decree 和 Menxia privacy review；本报告不授权 body mirroring。

## 8. 验收门槛

### 必须 GREEN

- `python -B scripts/court_cli.py --format json help`
- `python -B scripts/check_unified_cli.py`
- `python -B scripts/check_court_dispatch_hierarchy.py`
- `python -B scripts/check_court_result_semantics.py`
- `python -B scripts/check_governance_framework.py --only gbrain --json`
- 新增 command-resolver golden tests、source-agent whitelist tests、closeout-template install-projection tests。
- 新增 memory synthetic fixture 的 scan/adjudicate/apply/verify/reconcile tests。
- `git diff --check`，根工作树和 child index 均保持清洁；本次报告之外的既有未跟踪文件不触碰。

### 必须保持阻塞或降级

- workspace `beta1.0.6` 与 child checkout `release/beta1.0.7` 的版本漂移未治理前，不进行版本号回退或发布宣称。
- 宿主无法提供真实 agent spawn/reuse/wake receipt 时，结论标记 `runtime_degraded`，不能把串行分析冒充 super parallel 实证。
- MCP server 未完成 manifest、install projection、runtime probe、typed receipt 四件套前，不宣称“已打包成 MCP”。
- hook 只能视为 advisory；绕过 hook、非 Git 事件或 hook 环境失败时，主流程仍必须可审计。

## 9. 研究资料与本地证据

### 本地权威材料

- `graphs/workspace-overview/GRAPH_REPORT.md`
- `scripts/court_cli_registry.py`
- `references/manifests/cli-command-surface.v1.json`
- `docs/issues/2026-08-01-local-issue-source-agent-label-fourteen-line-closeout.md`
- `scripts/internal_memory_shiguan_bridge.py`
- `scripts/memory_decision.py`
- `scripts/query_shiguan_index.py`
- `docs/wiki/Architecture.md`
- `docs/plans/2026-07-14-court-capability-router-shiguan-install-remediation-plan.md`
- `references/court-capability-registry.md`
- `references/court-closeout-validation.md`

### 外部规范入口（仅作为设计对照）

- MCP latest specification (2026-07-28): <https://modelcontextprotocol.io/specification/2026-07-28>
- MCP latest tools specification: <https://modelcontextprotocol.io/specification/2026-07-28/server/tools>
- MCP latest stdio transport: <https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio>
- MCP versioning and legacy fallback: <https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning>
- Git hooks documentation: <https://git-scm.com/docs/githooks>

外部规范不能替代本项目的官籍、直属层级、receipt、安装投影和 runtime evidence。

## 10. 史馆实录与结诏字段

以下是本次研究的 metadata-first 结诏摘要，供 `archive_checkpoint.py --full-record-file` 使用；不包含原始私密 memory body、凭据、完整 prompt 或未授权 runtime 日志。

```text
诏令编号：NEXT-VERSION-CLI-MCP-HOOKS-SHIGUAN-20260825
任务标题：下一版本 CLI 路由、MCP/hooks 边界与史馆记忆闭环调研
上游旨意：读取既有图谱，以 super 并行方向准备下一版本，审查脚本误调用、MCP/hooks 与史馆记忆落地
当前阶段：调研结诏
执行主体：Agents（运行时 writer，由 archive_checkpoint 自动识别）
直属上级：太子
变更范围：仅新增 docs/research 调研报告；不改 runtime authority、版本声明、既有未跟踪文件
证据摘要：workspace-overview 图谱；CLI registry/manifest；source-agent/十四行 closeout issue；memory bridge/decision/query；architecture 与 A02 计划
运行结果：方向已确立；MCP 定为薄适配器；hooks 定为 advisory；记忆闭环列为 P1；当前无新增 VERIFIED_CAPABILITY
记忆裁定：PROPOSE
风险与阻塞：workspace beta1.0.6 与 child beta1.0.7 漂移；MCP server/hooks 未有当前 capability receipt；native memory end-to-end 仍待 RED/GREEN
后续行动：先做 P0 typed resolver 与身份/模板门禁，再做 P1 MCP dry-run 与 memory synthetic fixture
回滚锚点：本报告文件可单独删除；既有 child HEAD 956f3e0 与未跟踪文件保持不变
结诏状态：DONE_WITH_CONCERNS
```

## 11. 最终判定

**[CONTROL_PLANE]** 当前应继续以 `court-runtime`、append-only events、现有 court hierarchy 和 registry-first CLI 为唯一治理骨架。
**[PLANNED_UNVERIFIED]** 本地 MCP facade、advisory hooks、memory 五段式闭环、native reread/paired receipts 均是下一版本工作项，尚未由本报告证明为已实现产品能力。
**结论**：下一版本不是“把所有东西打包成 MCP”，而是先把调用身份、命令 schema、cwd、receipt 和记忆证据链收紧；MCP 作为受限宿主适配，hooks 作为可绕过的派生提示，史馆记忆以可重放闭环作为审查点。
