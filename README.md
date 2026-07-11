# Court Capability Router / 朝廷能力路由器

## 发布 / Release

当前版本：`beta0.5.9`

- 发布包：`court-capability-router-beta0.5.9.zip`
- SHA256：`court-capability-router-beta0.5.9.zip.sha256`
- ZIP 内唯一根目录：`court-capability-router/`
- 包内版本与逐文件摘要：[release-manifest.json](release-manifest.json)
- 项目许可证：[Apache License 2.0](LICENSE)
- 安全策略：[SECURITY.md](SECURITY.md)
- 安装与包校验：[references/install.md](references/install.md)
- 简明变更：[CHANGELOG.md](CHANGELOG.md)
- 详细记录：[RELEASE-LOG.md](RELEASE-LOG.md)

维护约定：后续发版须同步更新 `VERSION`、本节、`CHANGELOG.md`、`RELEASE-LOG.md` 与 `release-manifest.json`。ZIP 自身摘要只写在外部 sidecar，避免清单自引用。

### 能做什么

- 把复杂任务路由为太子、三省、尚书省、六部、工坊、门下复核与史馆实录的可验证责任链。
- 按任务调用本地 skills、MCP、CLI、脚本与 agente，并受权限、容量、深度、请求预算和安全门禁约束。
- 提供 portable bootstrap、共享史馆 seed、metadata-only 记忆桥、本地/LAN 管理与发布校验。

### beta0.5.9 更新、修复与新增

- 更新：生产配置统一为 Multi-Agent V2；整棵会话树 16 槽、根计槽、最大深度 4。
- 修复：移除 V2 文档中的 legacy `agents.max_threads` 推荐，并明确六部默认非显性、静默，仅在尚书差遣后启用。
- 修复：公共包不再包含或宣称包含 `plan-archives`、`memory-decisions`、个人史馆正文、日志、会话、备份、peer/import/runtime 状态或本机索引。
- 修复：打包器改为大小写无关的 fail-closed 路径 allowlist，拒绝未知目录、reparse/symlink、嵌套包、Zip Slip、重复/大小写碰撞、异常压缩比与秘密/宿主路径。
- 新增：版本文件、详细发布日志、逐文件 SHA256 manifest、外部 ZIP SHA256 sidecar，以及 Git tree—ZIP 精确一致性验收。

详见 `RELEASE-LOG.md`。

## 中文说明

### 这是什么

`court-capability-router` 是一个 Codex skill，用来把本机 Codex 的任务执行、能力选择、并行 agente、脚本工具、史馆记录和最终复核统一到一套“三省六部”工作流里。它不是单纯的输出风格模板，而是一个语义路由器：当用户点名 `$court-capability-router` 或任务需要能力分派时，它会把请求转成可执行的朝廷流程。

标准流程是：

```text
太子定性 -> 三省会审 -> 三省上奏 -> 太子回奏 -> 尚书统六部 -> 工坊办差 -> 门下复核 -> 史馆实录
```

它的主要目标是让 Codex 在复杂任务中做到：

- 明确任务边界、非目标、允许动作、禁止动作和停止门禁。
- 在执行前由中书省拟旨、门下省封驳、尚书省评估分派。
- 根据任务需要选择本地 skills、MCP、CLI、脚本、Codex custom agents 或并行 sub-agents。
- 在执行后保留验收证据、风险判断、回滚/下一步和史馆记录。
- 在长任务、安装、外部下载、文件修改、记忆写入、包装发布等场景中减少语义漂移。

### 当前功能

#### 1. 固定 `/court` 工作流

本 skill 把旧式的 `/plan`、`/execute`、`/research`、`/debug`、`/catalog`、`/memories` 等模式都收束为内部朝廷职能。用户不需要选择多个模式；太子会先定性，三省会审后再由尚书省统六部执行。

#### 1b. 渐进式加载

入口 `SKILL.md` 只保留触发语义、硬门禁、最小流程和 governing reference 路由表。普通任务只读取入口和当前行为所属的引用卷；涉及 skill 行为更改、史馆/记忆架构、安装打包、语义争议或长上下文结诏时，才加载所有直接相关引用卷。这样另一台 Codex 复刻后也能按同一套规则减少上下文占用，同时不把硬门禁藏到生成记录里。

当前入口采用碎片化索引结构：`Core Metadata Index` 只留最中心的身份、权限、token、runtime、史馆和验证元数据；`Reference Index` 按行为域指向各 governing reference。主机/Windows/Hermes/本地 GUI-HTTP 边界坑位已移入 `references/court-host-platform-pitfalls.md`，superCC 细则、状态机、史馆和 closeout 也只在对应引用卷按需加载。`check_catalog.py --strict` 会检查入口行数上限、索引术语和新引用是否完整，防止入口重新膨胀成全文规则库。

Token 三级优化是硬规则：先写精准元数据（诏令编号、谱系、关键词、`key_actions`、路径、hash、任务/证据指针），再用精简正文引用（摘要、路径+行号、短摘录、证据句柄），最后按需加载（先查 compact index，再打开必要引用卷、史馆命中、源文件范围或运行态产物）。不得为方便把完整对话、原始日志、私有史馆正文、完整 skill dump 或大导入材料直接塞进上下文，除非最新旨意明确要求且门下复核通过。

#### 2. 三权执行权限

开朝时可使用四种执行权限：

- `approval`：只读权。默认只做只读勘验、检索、读档、审议；命令执行、写入、安装、联网、配置变更前先问。
- `autonomous`：管理权。在用户给定范围内自主执行；遇到破坏性、泄密、付费、未验证安装、私密上传或越界操作再问。
- `super`：完全控制权。在任务范围内自动执行命令、写入、联网、安装、配置、并行 agente 调度和跨路径操作，但仍不能绕过硬安全门禁。
- `superCC`：官署运行形态。它和普通并行 subagent 官署指向同一个官署本体，只是实现和证据门不同：`superCC` 是 `super` 加经选择的 Codex/Hermes/Claude/generic CLI 可见 runtime；正常环境只认 zellij+squad 显示传输门和所选 office client 证据，Hermes desktop/profile-native 只能作为补充 readiness 证据，不能跳过 zellij+squad。默认显性核心是太子+三省；六部默认非显性且静默，只有尚书省按已批准步骤差遣后才启用，显性六部/史馆还需最新旨意明确批准 bounded visibility。只读审计使用 `--check-only --no-auto-install-deps`；`--turn-start`、启动 panes、wake、closeout silence 和 bootstrap apply 都是 live/state-changing 动作；429/异常关闭/异常静默监督走静默脚本证据而不是可见监察窗。

#### 3. 三省六部责任模型

本 skill 使用明确的责任边界：

- 太子：唯一面向用户的路由和回奏层。
- 中书省：拟旨、拆解、考据、验收标准。
- 门下省：封驳、风险、完整性、语义漂移和最终复核。
- 尚书省：执行统筹，向六部发差遣并整合结果。
- 吏部：官籍、铨选、技能/agent/MCP/CLI 适任评估。
- 户部：资源、依赖、版本、路径、预算、能力库存。
- 礼部：报告体例、引用、说明文案、输出契约。
- 兵部：调度、事故响应、迁移、并发和运行战术。
- 刑部：安全、隐私、破坏性操作、未验证安装、回滚风险。
- 工部：工程实现、构建、测试、部署、浏览器/GUI/外部应用操作。
- 史馆：三省共监、门下主审，记录实录、记忆裁定和考课证据。

#### 4. 官籍与能力路由

skill 会维护本地能力目录，按“官籍 -> 铨选 -> 差遣 -> 考课”选择能力。能力可以来自：

- `%USERPROFILE%\.codex\skills`
- `%USERPROFILE%\.agents\skills`
- `%USERPROFILE%\.codex\agents`
- 本地 CLI、脚本、MCP 和 standing-official templates

轻量 catalog refresh 会检查 skill、agent、MCP、CLI 和脚本根是否变化；必要时重建本地能力目录。

#### 5. 并行 agente 与递归调度

正式任务默认尝试并行或多 agente 调度。运行时支持时，三省和六部可以成为独立 agente；这些普通 spawned subagent 与 `superCC` 可见官署/Hermes readiness 证据是同一官署抽象的不同物化方式。普通并行不自动开启 `superCC`，Hermes profile-native 或 Claude 普通会话也不自动成为 normal `superCC`；只有 zellij+squad 环境门通过后才算正常 superCC。只要保留角色、直辖上级、dossier/profile、任务和回奏证据，普通并行仍是真官署办差。运行时不支持时，skill 会明确记录 `runtime_degraded`，并由太子代摄官署流程。

用户明确要求串行时不得派生或复用 child agente。普通并行先执行 `court_cli.py agent-admit`，默认 `fork_turns=none`，并按职责、依赖和证据价值动态选角。V2 整棵会话树共 16 槽且根计槽，故最多 15 个 child；这是容量门禁而非并发目标，容量、占用、终态节点保留/回收或深度未知时 fail closed。

Multi-Agent V2 配置目标为：

```toml
[agents]
max_depth = 4

[features.multi_agent_v2]
enabled = true
max_concurrent_threads_per_session = 16
hide_spawn_agent_metadata = true
```

V2 不得设置 legacy `[agents].max_threads`；16 是含根上限，实际并发仍按可证容量收紧。

配置脚本：

```powershell
python -B scripts/ensure_court_agent_config.py --managed-overlay --write --protocol v2
```

#### 6. 史馆记录、记忆裁定和生长树

史馆是本 skill 的审计与记忆层。它会记录：

- 开朝状态
- 三省会审
- 太子回奏
- 尚书分派
- 六部执行证据
- 门下复核
- 语义再载入
- 记忆裁定
- 最终结诏

相关脚本包括：

```powershell
python -B scripts/migrate_shared_shiguan.py ...
python -B scripts/archive_checkpoint.py ...
python -B scripts/ensure_portable_court_bootstrap.py --check-only
python -B scripts/ensure_portable_court_bootstrap.py --apply
python -B scripts/internal_memory_shiguan_bridge.py inspect --format json
python -B scripts/internal_memory_shiguan_bridge.py record --content-mode metadata
python -B scripts/memory_decision.py ...
python -B scripts/query_shiguan_index.py ...
python -B scripts/rebuild_shiguan_index.py
python -B scripts/grow_shiguan_tree.py
```

史馆运行时数据使用共享根：

```text
%LOCALAPPDATA%\court-shiguan\court-capability-router\references
```

`COURT_SHARED_SHIGUAN_ROOT` 或 `SHIGUAN_SHARED_ROOT` 可覆盖该位置。Codex、Hermes 与 Agent Skills 的安装副本共用这个根；skill-local `references/` 主要保存治理文档和 portable seed。

Codex/Hermes 的内置记忆可通过 `internal_memory_shiguan_bridge.py` 接入史馆。默认桥接只写启用状态、文件清单、大小、mtime、sha256、SQLite 表/行数等元数据，不镜像 `MEMORY.md`、`USER.md` 或 Codex SQLite 原始记忆正文。如果 Codex 的候选正文表 `stage1_outputs` 为空，记录 `content_recall_status=empty_store_no_body_rows` 和 `memory_body_rows=0`；如果存在正文行，只写 `body_table_state` 的表名、候选正文列、行数、非空计数和 `counts_only_no_raw_sqlite_body` 策略，仍不得手工写入 Codex SQLite 来制造召回。内容级桥接必须另有明确旨意，并使用脱敏模式与门下复核。

完整复刻目标机时优先运行 `ensure_portable_court_bootstrap.py --apply`：它会创建共享史馆 seed，注册史馆源目录到 Obsidian，确保史馆守护服务，自动启用 Codex/Hermes 原生记忆配置，并写入 metadata-only 史馆桥接记录。它不会复制私有记忆正文、不会改 Codex SQLite、不会自动安装 Hindsight/ScopeRecall 等第三方记忆提供器。

如果只需要让内容“可被记忆索引到”，优先使用索引级内容桥接：史馆节点/叶子必须包含古制谱系、诏令编号、双语关键词、key_actions、能力谱系向量字段和可用源路径。能力谱系向量围绕三省六部、官籍、能力类型、skill/script/agent/CLI/MCP、史馆谱系和执行行为生成，不是普通全文 embedding。这样未来可通过史馆检索命中能力上下文与原文来源，再按当轮权限读取，不需要把完整对话或私密记忆正文复制进史馆。

公共打包版只包含 portable seed，不包含本机私有的 `plan-archives`、`memory-decisions`、生成的本地索引或本地知识图谱正文。ZIP 中不会创建 `references/plan-archives/` 或 `references/memory-decisions/`，也不会放入这两个目录的 README；目标机首次初始化共享史馆根时才创建对应私有目录。

#### 7. 本地/LAN 史馆 Web 管理页

skill 包含本地 Web 管理页：

```text
web/shiguan-tree/index.html
```

开朝时默认只启动或复用 `127.0.0.1` 回环服务：

```powershell
python -B scripts/ensure_shiguan_service_daemon.py
python -B scripts/ensure_shiguan_web.py
```

只有明确需要同一局域网访问时，才显式执行：

```powershell
python -B scripts/serve_shiguan_tree.py --host 0.0.0.0 --port 8765
```

同机通常使用：

```text
http://127.0.0.1:8765/
```

只有显式 LAN opt-in 才会返回 `lan_urls`。管理端点需要本地 admin token，不能把 token、API key、cookie 或私密二维码写进报告、图谱或日志。peer endpoint 不得内嵌凭据、query 或 fragment；非回环 peer 必须使用 HTTPS，重定向会被拒绝，bearer token 不会转发到其他 origin。`.shiguan-key` 只是混淆，不是加密；下载后应立即限制为仅当前用户可读写（POSIX `chmod 600`）。默认守护任务名为 `CourtShiguanDaemon`，隐藏登录启动，负责同时维护 8765 WebUI 与 preserve-only Obsidian autosync；后台进程使用 `pythonw.exe` 静默运行，不应弹出周期性控制台窗口；撤销命令为 `schtasks /Delete /TN CourtShiguanDaemon /F`。

#### 8. 直接导入队列

Obsidian、Markdown、TXT 等外部导入会先进入共享 `shiguan-imports\pending` queue，而不是自动成为正式史馆记录。开朝时会检查：

```powershell
python -B scripts/check_shiguan_import_queue.py --format json
```

只有经过三省会审、门下复核和史馆实录，导入内容才会转为正式记录或记忆候选。

#### 8b. Obsidian preserve-only 同步

Obsidian 是阅读和管理界面，不是权威源。默认同步是共享史馆源到 Obsidian 缓存的 preserve-only 刷新：

```powershell
python -B scripts/ensure_shiguan_service_daemon.py
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
python -B scripts/sync_shiguan_obsidian_vault.py
```

同步只添加或更新生成文件，保留用户笔记，要求 `preserve_only=true` 且 `removed=0`。Obsidian REST API key 只留在本机共享配置中，不进入包、日志、报告或史馆正文。
共享树内的 `sources/` 是 Obsidian 可打开 Source 链接所需的本机生成镜像；便携包只带 README seed，目标机运行 `grow_shiguan_tree.py` 后自动生成实际源文件镜像。

#### 9. 危险 YOLO 自启任务保护

skill 可以生成 Codex no-sandbox 自启任务的审阅材料，但不会仅因 `super` 或安装 skill 就注册危险自启。实际注册需要额外明确确认：

```powershell
python -B scripts/ensure_codex_yolo_startup_task.py
```

生成的注册/撤销脚本位于 `references/startup-tasks/`。默认只生成审阅材料，不注册 Windows Task Scheduler 任务。
这些草稿是目标 root 的本机审阅产物，不是 portable 权威源；同步多个 skill 副本时不要跨 root 复制注册脚本，必要时在目标副本用生成器重新生成。发布包仍只包含 `references/startup-tasks/README.md`。

#### 9b. Codex agents 安装防呆

不要把 `agents/standing-officials/*.toml` 直接复制进 `%CODEX_HOME%\agents`。standing profile 含结构化 `[profile]` 档案，只能作为源模板；已安装的 Codex agent 文件必须由以下命令渲染为 string-only TOML：

```powershell
python -B scripts/sync_codex_agents_from_profiles.py --write
python -B scripts/check_codex_agent_roles.py
```

如果 `.codex/agents/*.toml` 出现直接复制模板，检查会报 `TEMPLATE_COPIED_DIRECTLY`。

#### 10. 最终结诏与语义再载入

正式任务完成、暂停、阻塞、取消或交接前，skill 会重载核心语义章节并做门下复核。用户侧最终报告固定为十四行短结诏，包含跟随实际办差运行时的 `作业AI` 标签；史馆侧保留完整结诏。这样可以避免长上下文后输出变成普通项目总结而丢失朝廷责任链。

### 这个 ZIP 包包含什么

典型结构：

```text
court-capability-router/
  README.md
  SKILL.md
  agents/openai.yaml
  agents/standing-officials/*.toml
  references/install.md
  references/department-map.md
  references/manifests/release-gates.v1.json
  references/shiguan-index.jsonl
  references/shiguan-knowledge-graph.json
  references/shiguan-tree/...
  references/startup-tasks/README.md
  scripts/*.py
  web/shiguan-tree/index.html
  web/shiguan-tree/app.js
  web/shiguan-tree/styles.css
```

这个包是 portable core package。它包含 skill 语义、standing official templates、脚本、Web 管理器和空白/种子史馆结构；不包含当前机器的私有史馆实录正文、私有记忆正文、Obsidian sync config/API key、生成的本地能力目录或本地导入材料。`plan-archives` 与 `memory-decisions` 整个目录都不在 ZIP 中；空白安装首次运行史馆脚本时，才在目标机共享史馆根创建这些私有目录和 seed，而且不会静默合并旧机器数据。

### 安装方式概览

解压后把 `court-capability-router` 目录复制到 Codex skills 目录：

```python
from pathlib import Path
import os
import shutil

src = Path("court-capability-router")
skills_root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "skills"
dst = skills_root / "court-capability-router-beta0.5.9"
if dst.exists():
    raise SystemExit(f"refusing to overwrite existing install: {dst}")
shutil.copytree(src, dst)
```

然后重启 Codex。安装后先运行只读基线：

```sh
python -B scripts/ensure_portable_court_bootstrap.py --check-only --format text
python -B scripts/check_catalog.py
python -B scripts/ensure_court_agent_config.py --check
python -B scripts/check_supercc_functional.py --workspace .
python -B scripts/ensure_hermes_supercc.py --surface cli --format json
python -B scripts/ensure_hermes_supercc.py --surface desktop --format json
```

在明确允许写本地状态或初始化目标主机时，再运行：

```powershell
python -B scripts/ensure_portable_court_bootstrap.py --apply --format text
python -B scripts/refresh_capability_registry.py
python -B scripts/rebuild_shiguan_index.py
python -B scripts/grow_shiguan_tree.py
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
```

如需写入推荐递归 agente 配置：

```powershell
python -B scripts/ensure_court_agent_config.py --write
```

### 曾经的主要更新

以下是本 package 已包含的主要演进内容，按功能域归纳。

#### 1. 从能力选择器升级为语义路由器

早期能力选择只负责找 skill、CLI 或脚本；后续升级为完整的 `/court` 语义工作流。现在三省六部标签不是装饰文字，而是责任合约、状态门禁和证据要求。

#### 2. 固定 `/court`，废止多模式入口

旧的 `/plan`、`/execute`、`/research`、`/debug`、`/catalog`、`/memories` 被改为内部职能。用户只需发出任务，太子和三省负责判断是否规划、执行、研究、调试、查目录或写记忆。

#### 3. 增加三权权限模型

新增 `approval`、`autonomous`、`super` 三权，分别对应只读权、管理权和完全控制权。更新后，权限不再简单等于工具是否能运行，而是由任务边界、风险类别、路径、服务、成本、隐私和外部状态共同决定。

#### 4. 强化三省六部职责

多次更新后，中书省、门下省、尚书省和六部职责被拆清楚：中书省不直接命令六部，门下省不执行实现，尚书省不擅自改旨，六部只在差遣范围内办差。

#### 5. 引入逐一上奏、待朱批

当存在实质问题、风险选择、未批准边界、破坏性动作、未验证安装、私密上传或外部状态变化时，太子会逐项上奏，不会把多个关键问题混成一问。

#### 6. 增加并行 agente 与递归治理

新增 standing official templates 和 Codex-only agente 语义，支持三省、六部、史馆等独立 agente 的调度、汇报、关闭、日志和递归限制。并行是正式任务的默认姿态，但必须有明确证据价值。

`superCC` terminal-visible 官署必须在当前 zellij 中显性显示，不能只依赖 `squad agents` 里的身份。默认 visible core 是太子+三省；三省用 `ensure_supercc_court.py --launch-visible-core --reclaim-existing` 修复，每个中间回合入口用 `ensure_supercc_court.py --turn-start --reclaim-existing` 检查当前 zellij 复用、简单响应、非当前静止官署释放和缺失官署重开。需要六部/史馆显性显示时，由尚书差遣上下文使用 bounded `--launch-offices <roles>`，并用 `zellij action list-panes` 记录 pane 标题和 id。批量启动时子 Codex 使用异步错峰和退避重试，避免同一秒并发打出 429；六部默认写入 `supercc-office-state.json` 为 `silent`，由尚书省 `--wake-offices` 差遣后工作，结诏后 `--closeout-silence` 静默非未完成官署；同步到 Codex、Agent Skills、Claude、Hermes 安装副本后再打包。Hermes CLI 复刻使用 `--office-client hermescli --hermescli-command <path>`；Claude 使用 `--office-client claude`；未知 CLI 可直接 `--office-client <tool>` 或 per-office map，必须记录 `cli_probe`，命令不可用时标记 runtime_degraded。`supercc_watchdog.py --daemon --quiet` 是静默监督路径，关闭时用 `--stop-daemon` 记录证据。

#### 7. 增加 court runtime 状态机

新增 `scripts/court_runtime.py` 和 `scripts/court_cli.py`，用文件账本记录任务状态、事件、pause/resume/cancel、agent lifecycle 和 heartbeat。状态迁移有合法路径，`Done` 需要证据。

#### 8. 增加 agente terminal 与日志规则

新增 agente 终端可观察性、AGLOG 编号、日志保存、敏感信息常规脱敏、关闭/保留策略，以及 stale/blocked/orphaned agente 的处理规则。

#### 9. 扩展史馆为完整审计层

史馆从简单归档升级为完整 replayable audit chain：记录 intake、三省会审、执行证据、门下复核、语义再载入、记忆裁定和最终结诏。

#### 10. 增加史馆生长树和知识图谱

新增 `shiguan-tree`、`shiguan-knowledge-graph.json`、Markdown leaves、lineage 分类、关键词/行动索引和 Web 星图/树图。分类规则改为内容谱系为主，状态、风险、记忆价值等作为 facet。

#### 11. 增加本地/LAN 史馆 Web 管理器

新增 `serve_shiguan_tree.py`、`ensure_shiguan_web.py` 和 Web 前端。支持本机和 LAN 查看史馆图谱，同时区分 read/state endpoints 和需要 admin token 的 management endpoints。

#### 12. 增加导入队列安全规则

Markdown、TXT、Obsidian 直导材料不再自动进入官方史馆。它们先进入 pending queue，开朝报告数量、样本和 token 估算；处理前需三省会审和门下复核。

#### 13. 增加长期记忆门禁

新增 `memory_decision.py` 和 Memory Decision Gate。史馆实录和长期记忆分离，记忆写入需要判断稳定性、隐私、安全、价值和用户意图。

#### 14. 强化最终结诏模板

最终输出更新为用户侧十四行短结诏加史馆完整结诏，并在用户侧显示跟随实际办差运行时的 `作业AI` 标签。完成、暂停、阻塞、取消、交接前必须语义再载入，避免长上下文漂移。

#### 15. 增加 portable package 规则

公共 ZIP 现在必须排除本机私有史馆记录正文、私有记忆、生成索引、本地能力目录和启动任务草案，只保留 portable core、脚本、模板、Web 管理器和空白种子。

#### 16. 增加安装与校验脚本

新增或强化了 `check_catalog.py`、`ensure_court_agent_config.py`、`refresh_capability_registry.py`、`rebuild_shiguan_index.py`、`export_shiguan_obsidian.py`、`package_skill.py` 等脚本，用于安装后检查、能力登记、史馆重建和打包。

#### 17. 增加危险 YOLO 自启保护

新增 `ensure_codex_yolo_startup_task.py`。它可生成危险自启任务审阅材料，但实际注册必须用户额外确认，不能被 `super` 或安装动作自动触发。

#### 18. 增加双语召回字段

史馆索引条目开始携带中文和英文的摘要、关键词和行动字段，方便用户阅读，也方便 agente 和工具检索。

#### 19. 增加安全与隐私硬门禁

多次更新后，skill 明确禁止未经批准的秘密回显、token/API key/cookie 暴露、私密二维码输出、付费动作、私密上传、公共暴露、破坏性操作和无界代理树。

#### 20. ZIP 双语说明更新

此前向已打包的 `court-capability-router-skill.zip` 添加了这份中英双语 `README.md`，说明当前功能和历史更新摘要。

#### 21. 本次结构整理与重打包

本次对 `SKILL.md` 的顶层章节做结构审查和顺序整理，新增“语义结构与阅读顺序”导读，把总纲、入口权限、朝廷职责、状态调度、agente/能力官籍、史馆记忆、收尾发布按治理链排序。此次整理保留既有硬门禁和行为规则，不改变三权、安全、史馆、记忆或结诏语义。

### 常用入口

```powershell
# 检查 catalog 和依赖
python -B scripts/check_catalog.py

# 检查/写入递归 agente 配置
python -B scripts/ensure_court_agent_config.py --check
python -B scripts/ensure_court_agent_config.py --write

# 启动或复用史馆 Web
python -B scripts/ensure_shiguan_web.py

# 查询史馆
python -B scripts/query_shiguan_index.py "关键词"

# 写入史馆 checkpoint
python -B scripts/archive_checkpoint.py --topic "topic" --phase "复核" --status "DONE" --summary "..." --evidence "..." --next "..."

# 写入记忆裁定
python -B scripts/memory_decision.py --topic "topic" --decision "SKIP" --content "..." --reason "..."
```

### 使用建议

- 复杂任务、安装、调试、研究、打包、记忆写入和多 agente 工作优先使用 `$court-capability-router`。
- GitHub 或 GitHub Releases 下载速度慢时，优先使用 `aria2c` 多线程下载；下载后仍需校验 digest、哈希或签名。
- 不要把 token、API key、cookie、私密二维码、微信用户 ID 或其他敏感信息写入报告、图谱、日志或长期记忆。
- 对外发布 ZIP 前使用 `scripts/package_skill.py`，不要手工把本机私有史馆记录打进公共包。
- 迁移已有 `.codex`、`.agents`、Hermes 史馆时，先运行 `migrate_shared_shiguan.py --dry-run`，再显式执行迁移。

---

## English Documentation

### What This Is

`court-capability-router` is a Codex skill that routes local Codex work through a structured Three Departments and Six Ministries court workflow. It coordinates task interpretation, capability selection, parallel agents, local scripts, audit records, memory decisions, and final review.

It is not just a response style. It is a semantic router: when the user invokes `$court-capability-router`, or when a task needs capability routing, the skill turns the request into an executable court process.

The standard flow is:

```text
Taizi intake -> Three Departments review -> Three Departments petition -> Taizi reply -> Shangshu dispatch -> Six Ministries execution -> Menxia review -> Shiguan record
```

Its main goals are to make Codex:

- State the task boundary, non-goals, allowed actions, forbidden actions, and stop gates.
- Require Zhongshu drafting, Menxia review, and Shangshu dispatch before execution.
- Select local skills, MCP servers, CLIs, scripts, Codex custom agents, or parallel sub-agents when useful.
- Preserve verification evidence, risk review, rollback or next steps, and Shiguan audit records.
- Reduce semantic drift during long tasks, installations, external downloads, file edits, memory writes, packaging, and release work.

### Current Capabilities

#### 1. Fixed `/court` Workflow

The skill folds older user-facing modes such as `/plan`, `/execute`, `/research`, `/debug`, `/catalog`, and `/memories` into internal court functions. The user does not need to choose multiple modes. Taizi classifies the request, the Three Departments review it, and Shangshu dispatches the Six Ministries after approval.

#### 1b. Progressive Loading And Token Policy

`SKILL.md` keeps trigger semantics, hard gates, the minimal workflow, and direct governing-reference links. Ordinary tasks read the entrypoint plus only the reference volume that owns the active behavior. Skill-behavior edits, Shiguan/memory architecture, installation/packaging, semantic disputes, and long-context closeouts load all directly relevant governing references.

Token optimization has three hard levels: precise metadata first (`court_code`, lineage, keywords, key actions, source paths, hashes, task/evidence pointers), compact body references second (summaries, path+line anchors, short excerpts, evidence handles), and on-demand loading third (compact index first, then only the needed reference, Shiguan hit, source range, or runtime artifact). Full transcripts, raw logs, private Shiguan bodies, complete skill dumps, and large imports are not loaded or copied by default.

#### 2. Three Execution Authorities

The court supports three authority levels:

- `approval`: read-only authority. The court can inspect, search, read files, and deliberate, but asks before commands, writes, installs, network access, or configuration changes.
- `autonomous`: management authority. The court may execute inside the user-approved scope, but asks before destructive actions, secret handling, paid actions, unverified installs, private uploads, or scope expansion.
- `super`: full-control authority inside the task boundary. It may run commands, write files, use the network, install tools, change configuration, dispatch parallel agents, and work across approved paths, but it still cannot bypass hard safety gates.

#### 3. Three Departments and Six Ministries Responsibility Model

The skill uses explicit office responsibilities:

- Taizi: the only user-facing router and reply layer.
- Zhongshu: drafting, decomposition, research, and acceptance criteria.
- Menxia: veto/review, risk, completeness, semantic drift, and final review.
- Shangshu: execution coordination, ministry mandates, and integration.
- Libu-HR: capability registry, selection, recruitment, and fitness scoring.
- Hubu: resources, dependencies, versions, paths, budgets, and capability inventory.
- Libu: report style, citations, documentation, teaching, and output contracts.
- Bingbu: operations, incidents, migrations, concurrency, and runtime tactics.
- Xingbu: security, privacy, destructive actions, unverified installs, and rollback risk.
- Gongbu: engineering implementation, builds, tests, deployment, browser/GUI/external app work.
- Shiguan: audit records, memory decisions, evidence chain, and capability performance records.

#### 4. Capability Registry and Routing

The skill keeps a local capability registry and routes work through:

```text
registry -> selection -> task mandate -> performance record
```

Capabilities may come from:

- `%USERPROFILE%\.codex\skills`
- `%USERPROFILE%\.agents\skills`
- `%USERPROFILE%\.codex\agents`
- local CLIs, scripts, MCP servers, and standing-official templates

A light catalog refresh checks whether skill, agent, MCP, CLI, or script roots changed. When needed, it rebuilds the local capability catalog.

#### 5. Parallel Agents and Recursive Dispatch

Formal tasks default to attempting useful parallel or multi-agent dispatch. When the runtime supports it, the Three Departments and Six Ministries can be separate agents. Ordinary spawned subagents, `superCC` visible offices, and Hermes readiness evidence are different materializations of the same office abstraction. Ordinary parallelism, Hermes profile-native readiness, and ordinary Claude Code sessions do not automatically open normal `superCC`; zellij+squad is the normal environment gate. The work is still real office work when role, direct superior, dossier/profile, task, and report evidence are preserved. When the runtime does not support it, the skill records `runtime_degraded` and Taizi temporarily acts on behalf of the offices.

An explicit serial instruction disables child spawn/reuse. Ordinary parallel work first runs `court_cli.py agent-admit` and selects useful roles dynamically. V2 has 16 slots for the whole tree including the root, so at most 15 children; this is a capacity gate, not a target, and unknown capacity, occupancy, retained/reclaimed state, or depth fails closed.

The recommended recursive agent settings are:

```toml
[agents]
max_depth = 4

[features.multi_agent_v2]
enabled = true
max_concurrent_threads_per_session = 16
hide_spawn_agent_metadata = true
```

Do not set legacy `[agents].max_threads`; the 16-slot V2 ceiling includes the root and admission still clamps to proven capacity.

Configuration command:

```powershell
python -B scripts/ensure_court_agent_config.py --managed-overlay --write --protocol v2
```

#### 6. Shiguan Records, Memory Decisions, and Growth Tree

Shiguan is the audit and memory layer. It records:

- startup state
- Three Departments review
- Taizi replies
- Shangshu dispatch
- Six Ministries execution evidence
- Menxia review
- semantic reload
- memory decisions
- final memorials

Related scripts include:

```powershell
python -B scripts/migrate_shared_shiguan.py ...
python -B scripts/archive_checkpoint.py ...
python -B scripts/internal_memory_shiguan_bridge.py inspect --format json
python -B scripts/internal_memory_shiguan_bridge.py record --content-mode metadata
python -B scripts/memory_decision.py ...
python -B scripts/query_shiguan_index.py ...
python -B scripts/rebuild_shiguan_index.py
python -B scripts/grow_shiguan_tree.py
```

Runtime Shiguan data uses the shared root:

```text
%LOCALAPPDATA%\court-shiguan\court-capability-router\references
```

`COURT_SHARED_SHIGUAN_ROOT` or `SHIGUAN_SHARED_ROOT` can override it. Codex,
Hermes, and Agent Skills installs share this root; skill-local `references/`
mainly holds governing references and portable seed files.

Codex/Hermes built-in memories can be connected to Shiguan through
`internal_memory_shiguan_bridge.py`. The default bridge writes metadata only:
enablement state, inventory, size, mtime, sha256, and SQLite table/row counts.
It does not mirror `MEMORY.md`, `USER.md`, or raw Codex SQLite memory bodies.
Content-level bridging requires a separate explicit decree, redaction mode, and
Menxia privacy review.

When the goal is only to make content discoverable by memory recall, prefer an
index-level content bridge: the Shiguan node/leaf should carry ancient lineage,
court_code, bilingual keywords, key_actions, capability-lineage vector fields,
and available source paths. The capability-lineage vector is built around court
departments, capability registry terms, skill/script/agent/CLI/MCP tooling,
Shiguan lineage, and execution behavior; it is not a generic full-text
embedding. For live append-only sources such as the active Codex session JSONL,
record a prefix fingerprint (`live_prefix_size`, `live_prefix_sha256`,
`live_prefix_mtime_utc`) and verify only that prefix later; do not treat the
whole-file sha256 as durable while the file is still being appended. Future
sessions can find both the capability context and the source path through
Shiguan, then read the source under the current authority instead of duplicating
complete private transcripts or memory bodies into Shiguan.

Public packages include only portable Shiguan seed state. They do not include the `references/plan-archives/` or `references/memory-decisions/` directories at all, including placeholder READMEs, and they do not include generated local indexes or local knowledge graph bodies. The target host creates those private shared directories during first-run Shiguan initialization.

#### 7. Local/LAN Shiguan Web Manager

The package includes a local web manager:

```text
web/shiguan-tree/index.html
```

The default service starts or reuses a loopback-only `127.0.0.1` listener:

```powershell
python -B scripts/ensure_shiguan_web.py
```

Only for an explicit same-LAN opt-in, run:

```powershell
python -B scripts/serve_shiguan_tree.py --host 0.0.0.0 --port 8765
```

On the same machine, it usually runs at:

```text
http://127.0.0.1:8765/
```

`lan_urls` are returned only after explicit LAN opt-in. Management endpoints require a local admin token. Peer endpoints may not contain credentials, queries, or fragments; non-loopback peers require HTTPS, redirects are rejected, and bearer tokens are never forwarded to another origin. A `.shiguan-key` is obfuscation, not encryption; restrict a downloaded file to its owner (POSIX `chmod 600`). Tokens, API keys, cookies, private QR codes, and private identifiers must not appear in reports, graph labels, or logs.

#### 8. Direct Import Queue

External Obsidian, Markdown, and TXT imports enter the shared pending queue first. They do not automatically become official Shiguan records. Startup checks use:

```powershell
python -B scripts/check_shiguan_import_queue.py --format json
```

Imported material becomes an official record or memory candidate only after Three Departments review, Menxia review, and Shiguan recording.

#### 8b. Obsidian Preserve-only Sync

Obsidian is a reading and management surface, not the authority. The default
sync refreshes an Obsidian cache from the shared Shiguan source:

```powershell
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
python -B scripts/sync_shiguan_obsidian_vault.py
```

The sync may add or update generated files, preserves user notes, and must
report `preserve_only=true` and `removed=0`. Obsidian REST API keys stay only in
host-local shared config and are excluded from packages, logs, reports, and
Shiguan record bodies.

#### 9. Dangerous YOLO Startup Protection

The skill can generate review artifacts for a Codex no-sandbox startup task, but it will not register that dangerous startup task merely because `super` was selected or the skill was installed.

Command:

```powershell
python -B scripts/ensure_codex_yolo_startup_task.py
```

Generated register/unregister scripts live under `references/startup-tasks/`. By default, the script generates review material only and does not register a Windows Task Scheduler entry.
These drafts are local review artifacts for the target root, not portable authority. Do not copy register scripts across skill roots; regenerate them in the target root when review material is needed. Portable packages include only `references/startup-tasks/README.md`.

#### 9b. Codex Agents Installation Guard

Do not copy `agents/standing-officials/*.toml` directly into `%CODEX_HOME%\agents`. Standing profiles contain structured `[profile]` data and are source templates only. Installed Codex agent files must be rendered as string-only TOML:

```powershell
python -B scripts/sync_codex_agents_from_profiles.py --write
python -B scripts/check_codex_agent_roles.py
```

If a template is copied directly into `.codex/agents`, the check reports `TEMPLATE_COPIED_DIRECTLY`.

#### 10. Final Memorials and Semantic Reload

Before a formal task is completed, paused, blocked, cancelled, or handed off, the skill reloads its core semantic sections and performs Menxia review. The user-facing final answer uses a fixed fourteen-line short memorial with a runtime `作业AI` label, while the Shiguan side keeps the complete memorial. This prevents long-context drift into a generic project-manager summary.

### What This ZIP Contains

Typical structure:

```text
court-capability-router/
  README.md
  SKILL.md
  agents/openai.yaml
  agents/standing-officials/*.toml
  references/install.md
  references/department-map.md
  references/manifests/release-gates.v1.json
  references/shiguan-index.jsonl
  references/shiguan-knowledge-graph.json
  references/shiguan-tree/...
  references/startup-tasks/README.md
  scripts/*.py
  web/shiguan-tree/index.html
  web/shiguan-tree/app.js
  web/shiguan-tree/styles.css
```

This is a portable core package. It includes the skill semantics, standing-official templates, scripts, web manager, and empty or seed Shiguan structure. It does not include private records from this host, private memory bodies, Obsidian sync config/API keys, generated local capability catalogs, or local imported material. The entire `plan-archives` and `memory-decisions` directories are absent from the ZIP; first-run initialization creates them only in the target host's shared Shiguan root and does not silently merge legacy host data.

### Installation Overview

After extracting the ZIP, copy `court-capability-router` into the Codex skills directory:

```python
from pathlib import Path
import os
import shutil

src = Path("court-capability-router")
skills_root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "skills"
dst = skills_root / "court-capability-router-beta0.5.9"
if dst.exists():
    raise SystemExit(f"refusing to overwrite existing install: {dst}")
shutil.copytree(src, dst)
```

Restart Codex. Then run:

```sh
python -B scripts/check_catalog.py
python -B scripts/ensure_court_agent_config.py --check
python -B scripts/refresh_capability_registry.py
python -B scripts/rebuild_shiguan_index.py
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
```

To write the recommended recursive agent settings:

```powershell
python -B scripts/ensure_court_agent_config.py --write
```

### Major Past Updates

The package includes the following major functional updates.

#### 1. From Capability Selector to Semantic Router

The early capability selector mainly located skills, CLIs, or scripts. It was upgraded into a full `/court` semantic workflow. Office labels are now responsibility contracts, state gates, and evidence requirements, not decorative wording.

#### 2. Fixed `/court` and Removed Multiple User-Facing Modes

Former modes such as `/plan`, `/execute`, `/research`, `/debug`, `/catalog`, and `/memories` became internal court functions. The user issues the request; Taizi and the Three Departments decide whether the task needs planning, execution, research, debugging, catalog work, or memory writing.

#### 3. Added Three Authority Levels

The skill added `approval`, `autonomous`, and `super`. Authority is no longer treated as a simple tool switch; it is evaluated against task boundary, risk class, paths, services, cost, privacy, and external state.

#### 4. Strengthened Office Responsibilities

Zhongshu, Menxia, Shangshu, and the Six Ministries were separated more strictly. Zhongshu does not directly command the ministries, Menxia does not implement, Shangshu does not invent user intent, and the ministries act only within their mandates.

#### 5. Added One-by-One Petitions and User Approval

When there are substantive questions, risk choices, unapproved boundaries, destructive actions, unverified installs, private uploads, or external-state changes, Taizi asks one issue at a time instead of bundling critical decisions into a single vague question.

#### 6. Added Parallel Agents and Recursive Governance

The package added standing-official templates and Codex-only agent semantics for dispatch, reports, closure, logs, and bounded recursion. Parallel execution is the default posture for formal tasks when it adds evidence or speed.

#### 7. Added the Court Runtime State Machine

`scripts/court_runtime.py` and `scripts/court_cli.py` were added to store task state, events, pause/resume/cancel transitions, agent lifecycle, and heartbeat in a file-backed ledger. Legal transitions are enforced, and `Done` requires evidence.

#### 8. Added Agent Terminal and Log Rules

The package added agent terminal observability, AGLOG identifiers, saved logs, routine secret redaction, close/preserve rules, and handling for stale, blocked, or orphaned agents.

#### 9. Expanded Shiguan into a Full Audit Layer

Shiguan evolved from simple archiving into a replayable audit chain covering intake, Three Departments review, execution evidence, Menxia review, semantic reload, memory decisions, and final memorials.

#### 10. Added Shiguan Growth Tree and Knowledge Graph

The package added `shiguan-tree`, `shiguan-knowledge-graph.json`, Markdown leaves, lineage classification, keyword/action indexes, and web star/tree views. Classification now uses content lineage as the trunk, while status, risk, and memory value are facets.

#### 11. Added the Local/LAN Shiguan Web Manager

`serve_shiguan_tree.py`, `ensure_shiguan_web.py`, and the web frontend were added. The web manager supports local and LAN views while separating read/state endpoints from admin-token-protected management endpoints.

#### 12. Added Import Queue Safety

Markdown, TXT, and Obsidian imports no longer become official records automatically. They enter a pending queue first; startup reports the count, samples, and token estimate. Processing requires Three Departments review and Menxia review.

#### 13. Added Long-Term Memory Gates

`memory_decision.py` and the Memory Decision Gate were added. Shiguan records and long-term memory are separated. Memory writes require stable value, privacy review, safety review, and clear user intent.

#### 14. Strengthened Final Memorial Format

Final output now uses a fourteen-line user-facing short memorial with a runtime `作业AI` label plus a complete Shiguan memorial. Completion, pause, block, cancellation, and handoff require semantic reload before the final answer.

#### 15. Added Portable Package Rules

Public ZIP packages must exclude host-private Shiguan record bodies, private memories, generated indexes, local capability catalogs, and startup-task drafts. They ship only the portable core, scripts, templates, web manager, and empty seed state.

#### 16. Added Installation and Validation Scripts

Scripts such as `check_catalog.py`, `ensure_court_agent_config.py`, `refresh_capability_registry.py`, `rebuild_shiguan_index.py`, `export_shiguan_obsidian.py`, and `package_skill.py` were added or strengthened for installation checks, capability registration, Shiguan rebuilds, and packaging.

#### 17. Added Dangerous YOLO Startup Safeguards

`ensure_codex_yolo_startup_task.py` was added. It can generate review artifacts for a dangerous no-sandbox autostart, but actual registration requires explicit extra confirmation and is not triggered by `super` or by installation alone.

#### 18. Added Bilingual Recall Fields

Shiguan index entries now carry Chinese and English summaries, keywords, and key-action fields for both user readability and agent/tool retrieval.

#### 19. Added Stronger Security and Privacy Gates

The skill now explicitly blocks unauthorized secret exposure, token/API key/cookie leakage, private QR code exposure, paid actions, private uploads, public exposure, destructive operations, and unbounded agent trees.

#### 20. ZIP Bilingual Documentation Update

An earlier package update added this bilingual `README.md` to `court-capability-router-skill.zip`. It explains the current functionality and summarizes past updates.

#### 21. This Structural Reorganization and Repackage

This update reviews and reorganizes the top-level order of `SKILL.md`, adds a “Semantic Structure And Reading Order” guide, and orders the document by governance flow: overview, entry and authority, court responsibilities, state and dispatch, agents and capability registry, Shiguan and memory, then closeout and release. The reorganization preserves existing hard gates and behavior rules; it does not weaken authority, safety, Shiguan, memory, or final memorial semantics.

### Common Entry Points

```powershell
# Check catalog and dependencies
python -B scripts/check_catalog.py

# Check or write recursive agent configuration
python -B scripts/ensure_court_agent_config.py --check
python -B scripts/ensure_court_agent_config.py --write

# Start or reuse the Shiguan web manager
python -B scripts/ensure_shiguan_web.py

# Query Shiguan
python -B scripts/query_shiguan_index.py "keyword"

# Write a Shiguan checkpoint
python -B scripts/archive_checkpoint.py --topic "topic" --phase "复核" --status "DONE" --summary "..." --evidence "..." --next "..."

# Write a memory decision
python -B scripts/memory_decision.py --topic "topic" --decision "SKIP" --content "..." --reason "..."
```

### Usage Recommendations

- Use `$court-capability-router` for complex tasks, installs, debugging, research, packaging, memory writes, and multi-agent work.
- For slow GitHub or GitHub Releases downloads, prefer `aria2c` multi-thread downloading, then still verify digest, hash, or signature.
- Do not write tokens, API keys, cookies, private QR codes, WeChat IDs, or other sensitive data into reports, graphs, logs, or long-term memory.
- Use `scripts/package_skill.py` before public release. Do not manually package host-private Shiguan records into a public ZIP.
- When migrating existing `.codex`, `.agents`, or Hermes Shiguan archives, run `migrate_shared_shiguan.py --dry-run` first, then explicitly run the migration.
