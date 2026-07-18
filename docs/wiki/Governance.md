# Governance

## 权威顺序

1. 最新用户旨意与明确授权。
2. 当前任务的执行书、语义胶囊和 receipt。
3. `SKILL.md` 与直接 governing references。
4. runtime task/event 状态。
5. 史馆、记忆、索引和历史记录，仅作证据与恢复锚点。

低层证据不得覆盖高层权威，也不得建立第二 ledger、第二胶囊或第二状态机。

## 写入与 Git

- 一个任务分支默认只有一个 writer。
- root 控制仓与 child 产品仓分离。
- 未经明确授权不得 push、tag、PR、GitHub Release、资产上传或 npm publish。
- 发布候选必须来自 clean accepted commit，publisher 不得重建候选。

## 隐私

- pending/private 正文默认不读、不哈希、不搬移、不删除、不标记已读。
- portable package 不包含本机史馆正文、原生记忆正文、凭据、日志或本地索引。
- Obsidian 是 preserve-only 派生视图，不是第二事实权威。

## 复杂度

优先复用既有 lock、CAS、atomic replace、receipt 与 rollback。新增机制必须消除
真实重复或风险；不能用更高预算掩盖不必要增长。
