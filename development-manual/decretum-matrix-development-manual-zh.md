# Decretum Matrix（诏令矩阵）开发手册

版本：2026-07-16  
适用范围：Decretum Matrix（诏令矩阵）skill 的维护、验证、打包、迁移与历史追溯；规范 skill 名与调用为 `decretum-matrix` / `$decretum-matrix`。  
写作依据：当前 `SKILL.md`、governing references、共享史馆索引与本机 memory/rollout 摘要。  
边界：本手册只写可迁移的开发结论和证据索引；不收录原始私密史馆正文、完整会话、memory body、密钥、运行日志或主机绝对路径。

## 1. 这个 skill 的本质

Decretum Matrix（诏令矩阵）不是普通“选择工具”的路由表。它已经演进为一个面向 CLI Agent 的三省六部协作内核：用最小入口文件承载硬门禁，用 governing references 承载细节规则，用脚本承载可验证运行态，用史馆承载可回放证据，用 portable package 承载迁移发布。

开发时要坚持四个底层判断：

- 最新用户旨意高于旧史馆、旧 memory 和旧包名。
- `/court` 是唯一正式工作流；旧 `/plan`、`/execute`、`/debug` 等只作为内部意图。
- 普通并行不是 `superCC`；只有显式选择并通过运行态门禁时，才可声称 `superCC`。
- 史馆记录是证据与召回锚点，不是可打包的私密内容仓库。

## 2. 源码结构

主要结构如下：

```text
decretum-matrix/
  SKILL.md
  README.md
  development-manual/
  references/
  scripts/
  agents/
  web/
```

上面的 `decretum-matrix/` 是 ZIP 内根与 canonical 物理安装目录；旧
`court-capability-router/` 只可作为指向同一 authority 的 deprecated locator。
当前产品、skill、调用与发行产物标识分别使用
`Decretum Matrix（诏令矩阵）`、`decretum-matrix`、`$decretum-matrix` 与
`decretum-matrix-*`。

各目录职责：

- `SKILL.md`：语义入口、触发、三权、硬门禁、加载地图、十四行结诏模板。
- `references/`：可迁移 governing references、fixtures、section shards、portable seed。
- `scripts/`：校验、打包、史馆、superCC、Hermes、squad wrapper、跨平台 helper。
- `agents/`：standing officials 和 superCC dossiers。
- `web/`：史馆本地 Web UI 静态资源。
- `development-manual/`：本手册所在目录，必须保持 portable。

不要把共享史馆运行根、`plan-archives/` 原文、memory decisions、导入队列、runtime ledgers、logs 或 Obsidian 本地配置塞回 portable skill 源树。

## 3. 从早到近的开发脉络

### 2026-06-05：从技能选择器变成朝廷路由

关键节点：

- 补齐三省六部中文输出语义和阶段归档脚本。
- 加入“中书省请太子逐项转问”的澄清机制。
- 将 `/court` 从线性流程改成多 agente 官署协作。
- 明确 `/court` 下并行官署默认开启，不需要用户额外声明“并行”。
- 把 Codex memories 接入为选择性长期记忆门，而不是默认乱写记忆。

开发含义：早期目标是把“工具选择”提升为“职责路由”。这一天确定了太子、中书、门下、尚书、六部、史馆这些标签必须对应真实职责，而不是装饰性文本。

### 2026-06-06：确立单一 `/court` 与史馆体系

关键节点：

- 用户确认只保留 `/court`，旧模式成为 court 内部功能。
- 史馆制度定为“实录为体，史记为纲”。
- 研究并采用更严格的历史三省六部模型：三省审议，尚书统六部。
- 引入 mandatory multi-agente 和 bounded recursive delegation 的早期规则。
- 建立“官籍 -> 铨选 -> 差遣 -> 考课”的能力任用链。
- 区分 `.codex/.agents skills`、standing custom agents、史馆职责。
- 加入三权：`approval`、`autonomous`、`super`。
- 建立史馆 growth tree、stable court code、中文关键词/摘要/理由、多维知识图谱与 Web UI。

开发含义：这一天完成了从“路由器”到“制度内核”的跃迁。后续所有脚本和包都应服务于这个制度：职责可验证、证据可回放、记录可检索。

### 2026-06-07 至 2026-06-10：史馆整理、打包门禁与结诏入本

关键节点：

- 新增史馆深整理流程：先 dry-run，再 apply，自动备份，重建 index/tree/graph。
- 修复史馆图谱中文展示、分类、动效、移动端和局域网展示。
- 固化递归失败、部分失败、太子代摄、真实 agente 边界、心跳和生命周期证据规则。
- 2026-06-10 用户朱批：结诏应写入本 skill，打包前必须有完整史馆记录，打包后再写最终包校验。

开发含义：打包不是复制目录。发布前必须先有完整可回放记录；包内只带 durable source rule 和 portable seed，不带本机史馆正文。

### 2026-06-17：开朝三权与能力索引硬门禁

关键节点：

- 开朝必须确认三权，未明确权限时先问。
- 官籍、能力目录、导入队列、YOLO 启动任务、史馆 recall 都进入 startup gate。
- 非明确任务需要反问，不把模糊输入直接扩大成执行任务。

开发含义：后续所有“自动推进”都必须建立在最新用户授权上，不能用旧记忆继承权限。

### 2026-06-21：渐进加载重构

关键节点：

- 将短 `SKILL.md` 定位为 semantic nucleus。
- 旧顶层长文拆入 `references/court-*.md` governing references。
- 包校验补齐 governing references 必需项。
- portable 包继续排除本机史馆、记忆、运行态、能力账册。

开发含义：长规则不能堆在入口里。入口只保存硬门禁和直接加载地图；细节放到可按需加载的引用卷。修改行为时，必须判断该规则属于入口硬门禁还是某个 governing reference。

### 2026-06-24 至 2026-06-26：Hermes、Obsidian、共享史馆与看板链路

关键节点：

- Hermes 三省六部多 agent 配置开始接入。
- Obsidian preserve-only 管理面接入史馆。
- 史馆共享根迁移为跨 Codex、Agent Skills、Hermes 的统一本地数据层。
- WebUI 和本地服务形成可重用管理面。
- 史馆即操作记忆规则被强化：史馆记录发生了什么，长期 memory 另走裁定门。

开发含义：skill 源树不是运行时数据库。所有运行时史馆写入应走共享根；Obsidian 是管理表面，不是源权威。

### 2026-06-27：superCC 成形

关键节点：

- 引入并验证 `superCC` 模式，同时明确“并行不是 superCC”。
- 修复 Codex 子窗启动、zellij + squad、三省 receive 等候。
- `archive_checkpoint.py` 默认快写索引，树和 Obsidian 刷新改为异步。
- 固化“六部创建只能由尚书省 dispatch，不从太子主 pane 刷新六部”。
- 加入 no-Taizi-substitution、office-duty enforcement、native-enter/profile、no-silence、429 patrol、direct-superior、profile sync 等 hard gates。

开发含义：`superCC` 是运行态，不是措辞。它要求可见 pane、squad 身份、角色唯一、任务证据、profile hash、直接上级、心跳/回执证据。

### 2026-06-28：运行时族与唯一性

关键节点：

- `superCC` 从 Codex-only 扩展为 runtime-family selector。
- Codex 分支保留 zellij+squad+Codex visible core。
- Hermes CLI/desktop 分支加入 readiness gate；desktop 不因缺少 zellij 失败，但 readiness 不能冒充 normal superCC。
- 角色唯一性扩展为 role-wide：显性与非显性身份都不能重复。
- ENTER_DISPATCH 需要 structured squad task evidence，不能只靠 freeform send。
- patrol-inspector 明确为 status-only/read-only，可见输出只保留 compact status table。

开发含义：同一规则要同时约束 launch、wake、enter-dispatch、patrol、closeout 和 package validation，不能只改一个入口。

### 2026-06-29 至 2026-06-30：副作用审计、相位轮转与抗 429

关键节点：

- `check_supercc_functional.py` 默认改为 `read_only_audit`。
- 旧的 live turn-start/patrol/closeout 路径只允许在 `--live-mutating` 下运行。
- `ensure_supercc_court.py` 输出 `court.supercc.side_effects.v1`，明确 mutates_runtime。
- blocked dry-run 的 `FAILED_OFFICE_UNIQUENESS_GATE` 可以作为有效只读审计证据。
- 相位轮转、inspector wake CC、429 fanout、dossier light bootstrap、layout prompt 等逐步补齐。

开发含义：验证脚本默认不应改变运行态。自检要先证明“没有副作用”，再谈功能覆盖。

### 2026-07-01：压缩生存、碎片化引用与结诏 shard

关键节点：

- context compression survival 规则强化。
- court voice、response fewshot、closeout installation validation 等被拆成更细 section shards。
- package/catalog 变成 shard-aware。

开发含义：长上下文中最容易丢失的是最新旨意、权限边界和结诏格式。最终答复前必须进行 semantic reload。

### 2026-07-02 至 2026-07-03：super GL 群聊联动与太子代工纠偏

关键节点：

- Hermes Studio group-chat 被单独建模为 `super GL`。
- `super GL` 不依赖 zellij/squad，不等于 normal superCC。
- 只有同房间真实 responder 才算官署履职。
- 不模拟沉默官署，不默认 `@all`，不循环催促沉默 profile。
- 对太子代工、office_duty_enforcement 不足、429 和 sync warning 做 DONE_WITH_CONCERNS 记录。

开发含义：多 agent 证据必须来自真实通信面。太子可以统合裁断，但不能替三省六部写履职记录。

### 2026-07-05：包内史馆排除与 Claude/zellij+squad 正常门

关键节点：

- 发现旧包夹带根部生成页中最新史馆索引，修复 `package_skill.py` 排除并重新打包。
- normal superCC 明确要求 Codex、Hermes、Claude 都通过 zellij+squad；Hermes desktop/profile 只是 readiness-only。
- Claude Code client 环境、workspace trust 和 role dossier 启动问题被修复。

开发含义：package exclusion 是硬门禁。包内若出现本机最新叶子、生成索引、raw 史馆、私密日志，应立即门下封驳、删旧包、修排除、重包。

### 2026-07-06：跨平台 wrapper、通用 CLI、手册、squad-first receive 与用量门禁

关键节点：

- superCC receive 从宿主绝对路径修为跨平台 wrapper。
- 修复 wrapper/cwd/env、平台路径、终端 helper、Hermes/Obsidian/Shiguan 路径假设。
- 加强 Claude/generic CLI robust startup hard gates。
- 加入 universal CLI silent supervisor。
- 完成中文使用手册和包内/独立副本。
- 将 visible pane 调度改成 squad task/send mirror 先行，再输入 wrapper receive 命令并自然 Enter。
- 新增 decree-level token/time estimate 与 closeout usage rollup，作为 gate behavior 而非新 office。

开发含义：2026-07-06 的主线是 portable 和 evidence-first。跨平台命令不能写死本机路径；pane 执行不能绕过 squad task evidence；用量统计不能伪装成 provider 精确值。

## 4. 开发流程

### 4.1 开朝

每次维护开始时先确认：

- 最新用户旨意和三权。
- 是否是 `super`、`superCC` 或 `super GL`。
- 任务边界、非目标、允许动作、禁止动作。
- 需要读取的 governing references。
- 史馆导入队列是否有 pending。
- 本轮是否需要写史馆、同步 active copies、打包。
- `decree_usage_estimate` 是否已记录或可说明为 estimated fallback。

### 4.2 读源

普通修改只读最小相关引用。以下情形必须更广加载：

- 改 hard gate、触发、三权、source-of-truth、loading map。
- 改 superCC、super GL、史馆、memory、打包、closeout。
- 发生语义争议或用户纠偏。
- 要发布 portable package。
- 长上下文 final closeout。

### 4.3 修改

常见职责归属：

- 入口硬门禁：改 `SKILL.md`。
- 详细流程：改对应 `references/court-*.md`。
- 运行态行为：改 `scripts/ensure_supercc_court.py`、`supercc_squad.py`、watchdog 或 wrapper。
- Hermes readiness：改 `scripts/ensure_hermes_supercc.py`。
- 包规则：改 `scripts/package_skill.py`。
- 回归验证：改 `scripts/check_*.py` 或 fixtures。
- 角色模板：改 `agents/standing-officials/` 或 `agents/supercc-dossiers/`，再同步渲染。

不要只改文档不改脚本，也不要只改脚本不改 governing reference。行为规则需要文档、实现、验证三处闭环。

### 4.4 验证

推荐最小验证：

```powershell
python -B scripts/quick_validate.py .
python -B scripts/check_catalog.py --strict
python -B scripts/check_portability.py
python -B scripts/ensure_court_agent_config.py --check
```

涉及 superCC 时加：

```powershell
python -B scripts/check_supercc_functional.py --workspace .
python -B scripts/check_supercc_ministry_dispatch.py
python -B scripts/check_supercc_no_silence_429_patrol.py
python -B scripts/ensure_supercc_court.py --check-only --no-auto-install-deps --format json
```

涉及 Hermes 时加：

```powershell
python -B scripts/ensure_hermes_supercc.py --surface cli --format json
python -B scripts/ensure_hermes_supercc.py --surface desktop --format json
```

涉及史馆/Obsidian 时加：

```powershell
python -B scripts/check_shiguan_import_queue.py --format json
python -B scripts/rebuild_shiguan_index.py
python -B scripts/grow_shiguan_tree.py
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
```

Windows UTF-8 风险：

```powershell
$env:PYTHONUTF8='1'
python -X utf8 scripts/quick_validate.py .
```

### 4.5 打包

打包命令：

```powershell
$version = (Get-Content VERSION -Raw).Trim()
python -B scripts/package_skill.py --out "decretum-matrix-$version.zip"
```

包内必须有：

- `SKILL.md`
- governing references
- required scripts
- superCC/Hermes/Claude/generic CLI 相关 gate 脚本
- portable Shiguan seed
- `development-manual/`

包内不得有：

- raw `plan-archives/` 正文
- memory decisions 正文
- generated leaves/branches/latest pages
- runtime ledgers
- logs
- import queues
- Obsidian sync config/API keys
- local capability catalogs
- host absolute paths
- secrets、tokens、cookies、private keys

如果发现包夹带私密史馆或 host-local artifacts，处理顺序是：

1. 删除问题包。
2. 修 `package_skill.py` 排除规则。
3. 重跑验证。
4. 重新打包。
5. 写史馆记录说明封驳和修复。

## 5. 关键设计规则

### 5.1 普通并行

普通并行可以并发读取文件、跑只读检查、整理史馆索引、写不同的草案，但共享写入、打包、版本同步、服务注册、GUI/HTTP 外部状态必须串行。

### 5.2 superCC

normal superCC 的最低条件：

- 用户最新旨意明确说 `superCC`。
- 选定 runtime family/client。
- zellij + squad normal gate 通过。
- 太子与三省 visible core 具备证据。
- 每个 canonical role 唯一。
- 任务有 structured task evidence。
- 不允许太子代替健康官署履职。

read-only audit 不应触发 live wake。需要真实唤醒时，必须明确使用 live-mutating 或进入真实 superCC 开朝。

### 5.3 super GL

super GL 只在 Hermes Studio group-chat room gate 通过时成立。它不是 normal superCC。履职证据来自同房间真实 profile 回复。沉默者列为 non_responder 或 runtime_degraded，不得模拟。

### 5.4 史馆和 memory

史馆记录的是本轮事实。durable memory 记录的是未来要复用的偏好、规则、环境事实或纠偏。每个 formal decree 都需要 `记忆裁定`，但不一定写 memory。

低风险可写 memory 的前提：

- 用户最新旨意允许或明确要求。
- 门下省批准。
- 不包含密钥、个人私密、raw log、完整会话、未经核实推测。

### 5.5 active copy 同步

常见活跃副本包括 Codex、Agent Skills、Hermes、desktop Hermes skill root。修 gate、脚本、角色模板或打包逻辑后，必须同步 active copies 并用 SHA-256 或专用检查证明一致。不要依赖 git，因为这些 skill 树常常不是 git 仓库。

## 6. 常见故障与处理

### 故障：把并行误称为 superCC

处理：回到最新旨意。若用户只说 `super` 或 `super并行`，不得启动 zellij/squad 官署，不得报告 normal superCC。

### 故障：自检改变了运行态

处理：默认用 `check_supercc_functional.py` read-only audit。只有明确 live mutation 时才使用 `--live-mutating`。检查 `court.supercc.side_effects.v1`。

### 故障：重复 office 身份或重复 pane

处理：让 `office_uniqueness_gate` 阻断 dispatch。不要让太子绕过重复身份代工。修复后用 `check_supercc_ministry_dispatch.py`。

### 故障：Hermes desktop 被 zellij gate 错杀

处理：Hermes desktop readiness 是独立 surface，可记录 `hermes_desktop_zellij_gate=SKIPPED_DESKTOP`；但 readiness 不能冒充 normal superCC。

### 故障：包里混入史馆生成页

处理：门下封驳，删旧包，修排除规则，重包，验包，写史馆。

### 故障：Windows 编码导致校验失败

处理：先用 UTF-8 环境重跑，不要立即判定源文件损坏。

### 故障：`squad` 报 `HOME` 缺失

处理：Windows PowerShell 下为当前命令设置 HOME，值取当前用户 profile 目录；不要把这个临时环境设置写入 portable 文档、配置或启动项：

```powershell
# Set HOME to the current user profile directory for this one command.
```

## 7. 发布前检查清单

- [ ] 最新旨意和权限已确认。
- [ ] semantic charter 已明确。
- [ ] 三省会审和太子回奏已完成或有 NOT_APPLICABLE 理由。
- [ ] 修改点已落在正确 source of truth。
- [ ] 代码、reference、测试/脚本已闭环。
- [ ] active copies 已同步或明确不适用。
- [ ] 史馆 checkpoint 已写入。
- [ ] memory decision 已裁定。
- [ ] package exclusion 通过。
- [ ] zip 内含本手册。
- [ ] final closeout 做过 semantic reload。

## 8. 证据索引

本手册的历史脉络来自以下摘要层证据：

- 共享史馆索引：`references/shiguan-index.jsonl` 的相关记录摘要。
- 共享史馆计划档：`references/plan-archives/` 中与本 skill 相关的 stage records。
- 共享史馆记忆裁定：`references/memory-decisions/` 中经门下裁定的候选或写入记录。
- 本机 memory registry：`MEMORY.md` 中历史 `court-capability-router` task group；
  该旧名只用于定位既有证据，不是当前产品身份。
- 本机 rollout summaries：superCC uniqueness、dual runtime、patrol、startup roundtrip、fast closeout、no-Taizi-substitution、profile sync、read-only audit 等摘要。

关键史馆 topic：

- `court-router-semantics-archive`
- `court-router-clarification-loop`
- `court-router-collaborative-court`
- `court-router-default-parallel`
- `court-router-single-mode-shiji-archive`
- `court-router-recursive-codex-court`
- `court-router-strict-history-recruitment`
- `court-router-capability-registry-upgrade`
- `court-router-custom-agents-three-roots`
- `court-router-three-authorities-package`
- `court-router-shiguan-growth-tree-web`
- `court-router-shiguan-court-code`
- `court-router-shiguan-content-taxonomy`
- `court-router-shiguan-multidimensional-graph-ui`
- `史馆深整理内容重分类与记忆重判`
- `结诏写入本skill并打包前门禁`
- `court-router-progressive-loading-refactor`
- `共享史馆迁移与便携打包`
- `superCC Codex 官署升级与启动修复`
- `shiguan-fast-closeout-optimization`
- `superCC-six-ministry-shangshu-dispatch-gate`
- `supercc-office-uniqueness-and-delegated-task-dispatch`
- `super GL 太子代工纠偏与流程优化`
- `court package shiguan exclusion repack`
- `superCC zellij+squad normal gate sync`
- `court-router-platform-portability-package-20260706`
- `superCC squad-first receive-command wake`
- 历史 topic：`court-capability-router decree usage gate`（保留作既有证据 locator）

关键 memory/rollout 主题：

- role-wide office uniqueness and delegated task dispatch
- Codex/Hermes dual-runtime superCC packaging
- patrol-inspector status-only duty
- superCC startup and three-province roundtrip
- fast Shiguan closeout and async Obsidian sync
- no-Taizi-substitution and office-duty enforcement
- no-silence, 429 patrol, direct-superior routing
- multiround validation and portable seed packaging
- read-only superCC functional audit and side-effects manifest

## 9. 维护原则摘要

后续开发可以记住这组短规则：

- 先定权，再开朝。
- 先读入口，再读相关引用。
- 先证据，再声称。
- 先 structured task，再 pane receive。
- 先史馆记录，再 package-ready。
- 先排除私密，再验包。
- 先 semantic reload，再结诏。
