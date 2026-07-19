# Governance

## 权威顺序

1. 最新用户旨意与明确授权。
2. 当前任务的执行书、语义胶囊和 receipt。
3. `SKILL.md` 与直接 governing references。
4. runtime task/event 状态与已验证证据。
5. 史馆 GBrain、记忆、索引和历史记录，仅作认知支持、证据与恢复锚点。

低层证据、治理解释和历史记忆不得覆盖高层权威，也不得建立第二 ledger、第二
胶囊、第二状态机、第二记忆权威或第二执行权威。

## 事实与解释

- fact 保留原始诏令、运行事件、能力结果、客观状态和验收证据。
- interpretation 必须标明解释主体并引用 fact。
- ruling 必须标明裁定主体、依据、范围和时效。
- action 必须引用 ruling，仍由当前任务权限和写集授权。
- validation 必须同时回指 action 与 fact。
- memory 与 presentation 永远没有执行权；冲突和过期记录保留来源并降级使用。

`decretum.semantic.record.v1` 只验证这些关系，不保存第二份任务历史。

## 理解充分度

非平凡任务在详细计划前评估目标、使用场景、关键要求和验收标准。低于 95 时，
只问一个会影响最终实现或验收的最高价值问题；必要时给 2–4 个互斥选项。达到
95 后先简要复述并确认，但初始旨意已经明确或明确免确认时可直接执行。已回答的
问题不重复，不为展示流程而制造问题。复述本身不授权创建正式任务；只有用户确认
后的 `DIRECT_EXECUTION` 状态，或明确旨意直接生成的同一状态，才通过创建门。

## 治理实现

`three-departments-six-ministries` 是完整默认官方治理实现。它继续使用现有官署
profiles、dossiers、governing references 与唯一层级 manifest。治理实现可替换
角色语义和呈现方式，但不能替换通用任务治理框架的状态、证据、权限、安全或
史馆 GBrain 服务。

`direct-review` 是本地非默认参考实现，只用于证明框架可在不依赖三省六部专有
名称时完成接收、复核、行动和呈现。它不构成开放插件平台或自动选择来源。

## 写入与 Git

- 一个任务分支默认只有一个 writer。
- root 控制仓与 child 产品仓分离。
- 未经明确授权不得 push、tag、PR、GitHub Release、资产上传或 npm publish。
- 发布候选必须来自 clean accepted commit，publisher 不得重建候选。

## 隐私

- pending/private 正文默认不读、不哈希、不搬移、不删除、不标记已读。
- portable package 不包含本机史馆正文、原生记忆正文、凭据、日志或本地索引。
- Obsidian 是 preserve-only 派生视图，不是第二事实权威。
- GBrain 召回采用 metadata-first；原始 memory body 不进入 recall envelope。

## 复杂度

优先复用既有 lock、CAS、atomic replace、receipt 与 rollback。新增机制必须消除
真实重复或风险；不能用更高预算掩盖不必要增长，也不能引入动态远程治理发现。
