# Obsidian Autosync REST / 史馆 Obsidian 实时同步

本卷治理 Decretum Matrix（诏令矩阵）（`decretum-matrix` / `$decretum-matrix`）史馆与本机 Obsidian
vault 的同步、Local REST API、插件和父 vault 入口规则。现存
`court-capability-router` 目录段仅是受保护的共享史馆与安装 locator，不是当前产品名。

## Authority

用户最新纠正优先：史馆↔Obsidian freshness 不应依赖 Hermes cron；共享史馆应由本机独立 `shiguan_service_daemon.py` 常驻维护。该守护进程由 `ensure_shiguan_service_daemon.py` 安装为隐藏的用户登录启动任务 `CourtShiguanDaemon`，统一确保单一 8765 史馆 WebUI 与 preserve-only autosync daemon 运行。结诏/checkpoint 的前台路径只负责快速写入归档、索引和刷新请求；全量生长树/Obsidian 镜像刷新由后台 daemon 在检测到史馆源变更后异步执行，除非本轮明确需要阻塞式验证。

权威史馆数据根由 `scripts/shiguan_paths.py` 决定。默认路径继续保留受保护的
`court-capability-router` 共享史馆 namespace：
`%LOCALAPPDATA%\court-shiguan\court-capability-router\references`，可由
`COURT_SHARED_SHIGUAN_ROOT` 或 `SHIGUAN_SHARED_ROOT` 覆盖。Codex、Hermes 与
Agent Skills 的 skill-local `references/` 不是运行时权威库。

Portable install bootstrap:

```powershell
python -B scripts/ensure_portable_court_bootstrap.py --apply
```

This creates the shared Shiguan seed, registers the shared
`references\shiguan-tree` as an Obsidian vault without making it the open vault
by default, updates the preserve-only sync config, and ensures the Shiguan
service daemon. Use `--set-open-obsidian` only when the newest decree wants the
shared vault opened by Obsidian. The bootstrap does not make Obsidian the
authority, does not package API keys, and does not promote Obsidian edits into
official records.

## Independent Autosync Gates

- 开朝：加载 `$decretum-matrix` 后、进入实质任务前，若 filesystem tool 可用，`approval` 仅运行 `scripts/ensure_shiguan_service_daemon.py --check-only`，除非最新旨意明确允许服务写入；`autonomous`/`super` 仅在任务范围内运行 `scripts/ensure_shiguan_service_daemon.py`，确保隐藏登录任务 `CourtShiguanDaemon` 已注册并启动。该服务守护进程负责复用/启动 `scripts/serve_shiguan_tree.py --host 0.0.0.0 --port 8765` 与 `scripts/shiguan_autosync_daemon.py`。`scripts/ensure_shiguan_autosync.py` 保留为底层诊断/手动修复入口，不再作为唯一 freshness 机制。
- 若 Windows 拒绝 XML 方式导入计划任务，`ensure_shiguan_service_daemon.py` 可降级为当前用户 `ONLOGON` 简式任务，任务名仍为 `CourtShiguanDaemon`，动作仍是同一个隐藏 `ShiguanServiceDaemon.vbs` wrapper；撤销命令不变。
- 静默运行：所有长驻后台进程必须优先使用 `pythonw.exe`，并在 Windows 上设置无窗口启动标志。autosync/WebUI/结诏触发的短时同步子进程也必须通过 `pythonw.exe` 加临时 JSON 文件回传结果，不能周期性弹出控制台窗口。
- 后台存活探测不得通过会生成控制台宿主的外部命令实现，例如 `tasklist.exe`、未隐藏的 `powershell.exe` 或 `cmd.exe`。Windows PID 检查应使用进程内 API（例如 `OpenProcess`/`GetExitCodeProcess`）或等价无窗口机制；确需调用系统工具时必须设置 `CREATE_NO_WINDOW`。
- 结诏：`archive_checkpoint.py` 默认使用快路径：append archive -> append index -> return current `court_code`/`ancient_lineage`/`source_agent_label` -> write `obsidian-sync/refresh-request.json` for the daemon。不要在默认结诏路径里阻塞运行 `grow_shiguan_tree.py`、`sync_shiguan_obsidian_vault.py` 或其他全量刷新脚本；这些刷新由后台 daemon 异步完成。只有发布验收、迁移验证或用户明确要求“同步完成后再结诏”时，才使用 `archive_checkpoint.py --sync` 或 `shiguan_autosync_daemon.py --once --force-sync`。
- 不以 Hermes cron 作为 freshness 机制；daemon 可以按本机配置循环运行，但它属于共享史馆自身的后台程序，而非 Hermes 计划任务。撤销自启使用 `schtasks /Delete /TN CourtShiguanDaemon /F`。
- 结诏 full_record 的生成身份字段由字段标签而非占位文案驱动：任何以 `诏令编号：`、`古制谱系：` 或 `作业AI：` 开头的 full_record 行，都必须由归档脚本用本次生成的 `court_code`、`lineage_display`/`ancient_lineage` 和 `source_agent_label` 重写；若调用前未提供这些行，归档脚本应自动插入。摘要、证据、next、memory 字段里的同类占位文本也必须改写为非误导性表述。

## Preserve-only Rule

同步必须 preserve-only：

- 允许：新增生成文件、更新同名生成文件、保留 `.obsidian/` 配置、刷新 `Auto Sync Status.md`。
- 禁止：删除原文、旧导出文本、用户笔记、目标 vault 中已存在但本轮导出缺失的文本。
- 目标 vault 中不在本轮导出的旧文件应计为 `preserved`，结果中 `removed` 必须保持 `0`。
- 缓存镜像的反向监听必须区分“用户编辑”和“本机同步器自己的生成输出”。`sync_shiguan_obsidian_vault.py` 在复制前为全部生成文件（包括 Markdown、JSON/JSONL 与图谱索引）写入 `.court-shiguan-sync-manifest.json`（`applying`），复制完成后原子提交为 `committed`；`shiguan_autosync_daemon.py` 的反向监听仍只接收 `.md`/`.txt`，并在重启或上次同步中断后，对与该 manifest 哈希一致的文本只更新快照，不得重新送入 pending。前向覆盖必须执行三方比较：上一版 committed 生成哈希、当前目标哈希、新生成哈希；当前目标若既不同于上一版生成哈希、又不同于新生成哈希，则记为 `user_modified_conflict`，保留用户文本、不覆盖，并将可审核文本送入 pending。`Auto Sync Status.md` 也只能按 manifest 精确哈希识别，不得按文件名无条件吞掉用户改动。
- Preserve-only cache 带有 `.court-shiguan-sync-manifest.json`，不得再被 `export_shiguan_obsidian.py --out <cache>` 当作普通 managed export 进行整目录替换；该入口必须拒绝并提示改用 `sync_shiguan_obsidian_vault.py`。同步器不得把临时 export 的 `.court-shiguan-managed.json` 复制进 cache；已有且 schema 合法的机器 marker 只可在 sync manifest 已建立后移除，用户笔记和 `.obsidian/` 不受影响。
- `autosync-state.json` 缺失、损坏或首次接管既有 vault 时，不得把当前文件静默收编为“已见基线”。若 legacy cache 尚无有效 sync manifest，先执行 preserve-only 前向同步建立 provenance，再对 post-sync 快照分流，避免把整座旧 cache 洪泛入队；cache 中与 manifest 精确匹配的生成文本只记快照，未受管理或已偏离 manifest 的 `.md`/`.txt`，以及专用 `Obsidian 回传` 根中的既有文本，均以 `bootstrap_untracked` 进入 pending 并生成 sidecar。
- 从旧 `.court-shiguan-managed.json` cache 迁移到 sync manifest 时，只可把有效 `autosync-state.json` 中与同一 cache 路径匹配的文本 snapshot hash 作为上一生成版本；JSON/JSONL 等非反向监听机器文件可从合法 managed cache 的当前 hash 建立基线。缺少这两类 provenance 的同路径文本仍按 conflict 保留，不能为避免首轮告警而盲目覆盖。
- daemon、Web 手动 filesystem sync 与 CLI `--once` 必须共享 `court-runtime/obsidian-autosync-cycle.lock`，所有直接前向复制必须再共享 `court-runtime/obsidian-filesystem-sync.lock`；不得让两个 cycle 或两个 vault copy 同时改写 snapshot、manifest 与 cache。单文件更新先复制到目标同目录 staging 文件，替换前二次验证目标 hash 仍等于先前观察值，再用原子 `os.replace` 提交；若用户在 hash→replace 期间修改目标，则转为 `user_modified_conflict`，不得覆盖。
- 所有 `obsidian-sync/config.json` 写入必须通过 `obsidian_config_state.py` 与固定 `court-runtime/obsidian-config.lock`。事务在锁内重读，按调用方 base snapshot 做字段级三方 CAS：互不相关字段合并，同字段并发漂移 fail closed；每次提交递增 revision、生成 transaction_id、原子替换后重读并核对 digest。公开投影只报告 `has_api_key`，绝不返回 key。autosync cycle 在读取配置至完成该轮期间持有配置锁，避免一轮同步使用混合配置。
- WebUI 的 `auto` / `manual` 只表示 autosync 调度开关，分别映射到一致的 `auto_enabled` / `autosync_enabled` 布尔值；后端 `sync_mode` 始终为 `filesystem_preserve_only`。读取或保存旧版 `sync_mode=auto|manual` 时必须归一迁移，未知 mode fail closed，不得让 UI 调度词覆盖 preserve-only 数据契约。
- daemon `starting` / `running` 只表示精确进程仍在执行一轮同步，必须报告 `ok=false`；`fresh_for_seconds` 只用于判定该进行中状态是否仍可复用，不是成功健康证明。仅完成的 daemon cycle 可报告 `ok=true`。`mode=once` 只保存 `last_cycle_ok` 回执，并以 `ok=false`、`phase=stopped` 明确不提供常驻健康保证。
- 单文件 staging copy 必须在替换前 fsync staging 并验证其 hash；替换后重新验证目标 hash并尝试同步父目录。Windows 不支持目录 fsync 时应如实报告 best-effort，而不是伪称已经获得断电级目录耐久性。替换失败必须保留原目标。
- 服务守护进程复用 autosync 子进程时，不得只信状态文件中的 PID。Windows PID 存活检查必须使用正确的 64 位 HANDLE/exit-code API；状态还必须在 `max(60s, 3×interval)` 内刷新。陈旧 PID 即使数值仍可打开，也不能报告 `REUSED`；先做一次精确脚本进程发现，找不到才启动新 daemon。
- Obsidian -> Shiguan 的回传不得直接覆盖正式 `plan-archives` 或
  `memory-decisions`。所有 Obsidian 编辑、REST 拉取、文件上传、Markdown/TXT
  导入先进入共享 `shiguan-imports/pending/`，再由 三省会审、门下复核和
  `archive_checkpoint.py`/`memory_decision.py` 转成正式记录。
- 新增 pending 正文必须先持久化正文，再写同 stem 的 `.metadata.json` 作为元数据提交标记；sidecar 只含 id、文件名、类型、状态、导入时间、字符数、token 估算、sha256、建议处理器，不得含 `text`/`raw_text`。重复导入若发现 sidecar 缺失或无效，只修复 sidecar，不打开既有 pending 正文。历史 pending 不得在普通检查或同步时自动迁移、读取或删除。

## Portable Host Paths

- 默认权威共享史馆数据根（受保护兼容 locator）：`%LOCALAPPDATA%\court-shiguan\court-capability-router\references`
- 默认权威史馆树（受保护兼容 locator）：`%LOCALAPPDATA%\court-shiguan\court-capability-router\references\shiguan-tree`
- 默认父 Obsidian vault：`%USERPROFILE%\Documents\Obsidian Vault`
- 默认父 vault 入口：`%USERPROFILE%\Documents\Obsidian Vault\史馆入口.md`
- 默认 Obsidian 缓存镜像：`%USERPROFILE%\Documents\Obsidian Vault\Court Shiguan`
- 独立 autosync 脚本：当前安装的 `scripts\shiguan_autosync_daemon.py`
- 史馆服务守护脚本：当前安装的 `scripts\shiguan_service_daemon.py`
- 史馆服务自启确保脚本：当前安装的 `scripts\ensure_shiguan_service_daemon.py`
- 便携首启脚本：当前安装的 `scripts\ensure_portable_court_bootstrap.py`
- preserve-only 镜像脚本：当前安装的 `scripts\sync_shiguan_obsidian_vault.py`
- 本机配置：共享根下 `obsidian-sync\config.json`；API key 仅本机保存，不入包、不入史馆正文。

实际主机路径由 `scripts/shiguan_paths.py` 和 `scripts/sync_shiguan_obsidian_vault.py`
在运行时解析；便携包不得硬编码某台机器的绝对用户目录。

## Parent-vault Source-reference Architecture

采用“父 vault 引用源目录 + preserve-only 缓存镜像”：

1. 权威来源为共享史馆根下的 `references\shiguan-tree`。
2. 父 vault 的 `史馆入口.md` 说明权威源目录、缓存镜像、删除边界和快速入口。
3. `Court Shiguan` 文件夹只是 Obsidian 图谱/标签/wikilink 可浏览缓存。
4. Obsidian 不能可靠地把 vault 外部目录直接纳入图谱；若用户要求直接图谱化源目录，应另开源目录为独立 vault，而不是静默复制或删除。

## Local REST API And Plugins

- Obsidian Local REST API: `https://127.0.0.1:27124`，仅作可选 push/pull 辅助；默认 freshness 机制是 preserve-only filesystem sync。
- API key 只保存在本机配置中，不打印、不写入史馆正文或 Obsidian note。
- Obsidian Terminal plugin manifest id: `terminal`；Local REST API plugin id: `obsidian-local-rest-api`。
- Terminal plugin 属高风险命令执行能力，只在明确授权边界内启用/使用。

## Verification

每次相关变更至少验证：

```bash
# `court-capability-router` is the protected physical install locator.
cd "$HOME/.agents/skills/court-capability-router"
python -B scripts/ensure_shiguan_service_daemon.py --check-only
python -B scripts/shiguan_autosync_daemon.py --once --force-sync
```

期望关键字段：`ok=true`、`preserve_only=true`、`removed=0`、`index_exists=true`、`obsidian_config_preserved=true`。

若同步脚本或导出脚本报错，不得假装 Obsidian 已刷新；应在结诏中标明 `verification_state: PARTIAL` 或 `runtime_degraded`。
