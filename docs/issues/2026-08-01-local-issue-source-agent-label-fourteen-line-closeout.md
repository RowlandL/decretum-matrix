# 本地 Issue：作业AI 标签未校验运行时 writer 白名单 + 结诏未按十四行模板渲染

- Date: 2026-08-01
- Branch: `work/beta1.0.6-local-issue-court-dispatch-memory`
- Scope: local only, no push/tag/PR/remote
- Skill 运行副本: `C:\Users\32893\.qoder\skills\decretum-matrix`（宿主 Qoder/Agents 环境）
- 关联史馆记录: `shiguan:SCOSZLSZU2J-20260801-1-DFEE`（缺陷发生）、`shiguan:SCOSZLSZUC9-20260801-2-DECC`（修正结诏）

## 运行完整记录（super并行联通自检 decree）

1. 旨意：`super并行 测试每个子官署只回复OK最后结诏`（authority=super, behavior=parallel, parallel_topology=native）。
2. 首波差遣：太子平铺并行差遣 9 署（中书/门下/尚书直属太子；吏/户/礼/兵/刑/工标记为尚书省 child agents），任务体为纯"只回复 OK"空载。宿主对 9 路全部返回 `intention_rejected`（error code 416 / inner 406），按门禁停 wave。
3. 单路探证：改用带最小只读探测载荷的任务（确认某文件存在后回奏 OK），单路 spawn 成功——判定宿主拒绝的是空载差遣意图，而非并行拓扑。
4. 重发波：其余 8 署以最小只读载荷并行重发，全部真实 spawn 成功；含补格式一次（首波探证的工部未输出字面 OK，补差一次），最终 9/9 署回奏末行均为 `OK`。
5. 结诏（缺陷发生点）：以 `archive_checkpoint.py --source-agent "Taizi"` 归档，receipt `closeout_identity` 生成 `作业AI：Taizi`；用户侧结诏采用自拟散文字段而非十四行模板。
6. 用户指正后修正：重载 `references/court-closeout-validation.md` 与 `references/sections/court-closeout-memorial-format.md`（源码树权威副本），以自动检测 writer 标签重新归档（`作业AI：Agents`，receipt `shiguan:SCOSZLSZUC9-20260801-2-DECC`，含 `--full-record-file` 完整史馆奏报），并按十四固定标签重发用户侧结诏，`hard_memorial_gate=DRIFT_CORRECTED`。

## 缺陷一：`--source-agent` 显式值缺少运行时 writer 白名单校验

规范（`references/sections/court-closeout-memorial-format.md`）规定 `作业AI` 是
"runtime writer label from archive_checkpoint.py, e.g. Codex/Hermes/Claude Code/Agents"，
`court-closeout-validation.md` 中 `source_agent_label: Codex | Hermes | Claude | GenericCLI | Agents,
matching the actual runtime writer`。但实现对显式传值不做任何白名单校验：

- `scripts/shiguan_paths.py:86-88` `canonical_source_agent()` 仅做小写/别名归一，未识别的值（如 `taizi`）原样透传。
- `scripts/shiguan_paths.py:1132-1133` 显式 `value` 存在时直接 `agent_id = canonical_source_agent(value)`，跳过全部运行时环境检测。
- `scripts/shiguan_paths.py:1147` `display = AGENT_LABELS.get(agent_id, value or agent_id)`——`AGENT_LABELS` 未命中时回退为原始输入，导致朝廷角色名 `Taizi` 成为 `source_agent_label` 并进入 `closeout_identity` 的 `作业AI：` 行。
- `scripts/archive_checkpoint.py` `detect_source_agent()` 直接 `return detect_runtime_agent(args.source_agent)`，CLI 层同样无校验。

复现（纯函数探针，无写入）：
`detect_runtime_agent('Taizi')` -> `{"source_agent": "taizi", "source_agent_label": "Taizi"}`；
`detect_runtime_agent()`（本宿主自动检测）-> `{"source_agent": "agents", "source_agent_label": "Agents"}`。

促成因素（agent 侧）：太子将朝廷角色名当作 `--source-agent` 传入。脚本契约本应
fail closed 或回退自动检测，而不是静默接受任意标签。

## 缺陷二：结诏未按十四行用户侧模板渲染

- 首次结诏为自拟散文字段（旨意/实际派遣/过程/写入情况/记忆裁定/史馆实录），
  缺失并重命名了十四固定标签（`诏令编号/古制谱系/状态/作业AI/旨意与边界/执行门禁/门下裁定/实际动作/验收证据/运行态与并行/史馆/余险/太子回奏/下一步`），
  也未写 `hard_memorial_gate` 裁定。按 shard 规则本应由门下省标记 `DRIFT_CORRECTED` 并重写后再发。
- 促成因素（投影侧）：安装投影 `C:\Users\32893\.qoder\skills\decretum-matrix\references\sections\`
  不含 `court-closeout-memorial-format.md`（install-projection 未收录该 shard），
  结诏时无法在运行副本内加载十四行模板，需回源码树读取。SKILL.md 轻量结诏条款
  （"不要求完整十四行"）与用户对完整格式的期待也存在歧义空间。

## 影响

- `作业AI` 失去"运行时 writer"审计语义：任意字符串可伪装 writer 身份，污染
  `closeout_identity`、史馆索引 keyword（`agent:taizi`）与后续按 writer 检索的召回。
- 用户侧结诏漂移为散文摘要，违反 `hard_memorial_gate`，削弱结诏的可机读性与一致性。

## 预期契约

- `detect_runtime_agent(explicit)`：显式值经归一后必须命中受控 writer 集合
  （`AGENT_LABELS` 键或其别名，可扩展 GenericCLI）；未命中时应 fail closed
  （报错并提示合法值）或忽略显式值回退自动检测，并在 receipt 中记录
  `source_agent_override_rejected` 之类的证据字段，不得静默采用任意标签。
- `archive_checkpoint.py --source-agent` 帮助文本应列出合法取值，拒收朝廷角色名。
- 安装投影应收录 `references/sections/court-closeout-memorial-format.md`
  （或在安装版 `court-closeout-validation.md` 内联十四行模板），保证结诏门禁
  在运行副本内可自足加载。
- 轻量结诏条款与十四行门禁的边界应在 SKILL.md 明示：用户明确要求完整结诏格式时，
  轻量路径不得豁免十四行渲染。

## beta1.0.7 处理状态

- Status: `RESOLVED_IN_SOURCE`
- Branch: `release/beta1.0.7`
- Evidence:
  - `scripts/shiguan_paths.py` 对显式 `--source-agent` 执行 writer 白名单校验，`Taizi` 等朝廷角色名 fail closed。
  - `scripts/archive_checkpoint.py` 帮助文本列出合法 writer，并以 `ARCHIVE_SOURCE_AGENT_INVALID` 拒收非法显式值。
  - `scripts/check_portability.py` 增加 `explicit source-agent override is writer-whitelisted` 回归项。
  - `references/manifests/install-projection.v1.json` 已投影 `references/sections/court-closeout-memorial-format.md`。
  - `SKILL.md` closeout 条款明确十四行 memorial 的当前引用与 archive receipt 约束。
