# beta1.1.9 独立计划 · 数据与进程边界

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.1.8](./beta1.1.8.md)｜下一版：[beta1.2.0](./beta1.2.0.md)
> 依赖：无（可在 1.1.8 期间并行准备）｜被依赖：[beta1.2.3](./beta1.2.3.md)（F02 的锁范围是安装入口验收的前置）
> 工单：`06-f01-f02-f03-transaction-process-boundaries`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F01、F02、F03

## 1. 版本目标

三类 P1 边界在并发/异常注入下不再互相破坏：

1. **恢复不删除后续合法任务**（F01）；
2. **安装补偿不覆盖他人成功投影**（F02）；
3. **停止进程前核验身份**（F03）。

本版是 P1 清零版本；三项修复都必须保留正常路径正例，不得引入新的事务/锁框架。

## 2. 修复条目

### 2.1 F01 · 完成事务恢复覆盖后续合法任务（P1）

- 现象：`court_runtime.py:4454` 只有 `EVENT_WRITTEN` 且当前整份账本与预期完全一致时才 finalize；其他情况在 4470 附近直接恢复整份 tasks/events 前像，未先判定后续合法写入。正常运行锁只处理另一个 paired-ledger marker，不阻止 completion 尚未恢复时的新任务写入。
- 隔离证据（已有）：TASK_WRITTEN 场景（SystemExit 故障注入留下 marker）与 EVENT_WRITTEN 场景（模拟保留已完成事务的 marker）；随后独立 case B 正常创建，恢复 A 返回 `ROLLED_BACK` 并删除 marker，使 B 与其事件丢失。事件数 5→3、6→3。
- 修复要求：恢复前复用前/后像与代次冲突校验；当前数据不属该 marker 可恢复范围时，**保留当前数据与 marker 并报告冲突**；新写入门禁与未恢复的 completion pair 保持一致；复用既有 CAS 语义，不重建事务框架。
- 验收（可测）：
  - [ ] TASK_WRITTEN / EVENT_WRITTEN 两场景下，后续 case B 的数据与其事件不丢失（冲突被报告而非静默回滚）；
  - [ ] 无后续写入的正常恢复仍执行原有回滚控制；
  - [ ] 未新增事务框架或第二套 ledger。
- 证据：repro 脚本 + 修复前后 JSON 对照（现有 repro 在 `_diag/decretum-beta117-full-review-20261003/menxia-completion-repro.json`）。
- 边界：故障为 SystemExit 注入，非真实生产事故或硬杀验证；不得据此宣称崩溃一致性已解决。

### 2.2 F02 · 并发安装补偿覆盖另一项成功投影（P1）

- 现象：`install_current_agent_copy.py:2888` 的投影/补偿没有同目标全过程互斥；1929 附近恢复旧前像时不确认其他事务已更新目标；最后 binding commit 的窄锁不保护该区间。
- 隔离证据（已有）：临时 HOME 先装 base；A 在既有提交 checkpoint 暂停，B 用默认 adapter 成功返回 INSTALLED（两份投影为 B）；A 故障补偿后两份投影回到 base，B 的成功结果丢失。公开 update/migrate、fix、replica、sync 调用链未发现覆盖整个同目标事务的外层锁。
- 修复要求：按实际 HOME/目标在 preflight、投影、验收、补偿范围复用既有跨进程锁；恢复仍核验代次；不能只给最后 binding 步骤加锁。
- 验收（可测）：
  - [ ] 临时 HOME 并发 A/B 对照：B 的 INSTALLED 不被 A 的补偿清除；
  - [ ] 单进程正常安装/更新/修复/迁移不受影响；
  - [ ] 锁超时/异常路径不产生僵尸锁（与 1.2.3 的 F12 分别验收）。
- 证据：并发对照 JSON（现有 repro 在 `_diag/.../shangshu-install-overlap-repro.json`）+ 修复后对照。
- 边界：未执行最终 COMMITTED/public npm 完整并发事务前，不得声明"正式安装并发已安全"。

### 2.3 F03 · watchdog 按 PID 停止进程，未核目标身份（P1 风险）

- 现象：`supercc_watchdog.py:235` 读取正 PID 后直接请求停止，未核脚本、工作区、进程创建时间等身份；Windows 分支忽略停止错误，POSIX 发信号后不确认退出，随后删除记录并报 `PASSED`；公开 main 与 compat 壳没有上层补验。
- 证据（已有）：陈旧时间和不相干命令的合成 PID 记录仍生成停止请求、删记录并 `PASSED`；门下独立核对调用链确认身份/退出保护不存在。
- 修复要求：复用既有精确进程检查；身份不符时**保留记录并拒绝停止**；匹配后有限等待并确认退出（或已不存在）才清记录与标成功；不新建守护框架或身份体系。
- 验收（可测）：
  - [ ] 陈旧 PID、不相干命令合成记录被拒绝（记录保留、不标 PASSED）；
  - [ ] 身份匹配的合法停止在有限等待内确认退出后才清记录；
  - [ ] 无真实进程被误停止的证据要求：合成/隔离环境对照即可，不得对真实进程做破坏性验证。
- 证据：repro JSON（现有在 `_diag/.../shangshu-watchdog-pid-repro.json`）+ 修复后对照。

## 3. 版本出口（Exit Criteria）

- [ ] F01/F02/F03 均有失败注入对照与修复后对照；
- [ ] 正常恢复 / 合法并发 / 合法退出三类正例不受影响；
- [ ] 未引入新事务/锁框架；未新增哈希校验脚本（摘要复用既有机制）；
- [ ] 执行记录（第 8 节）与总纲执行记录同步。

## 4. 依赖与顺序

- 无前置版本；F01/F02/F03 相互独立，可并行。
- 与 1.1.8 无文件冲突（不同模块）；若同轮开发，各自单分支/单工作树。

## 5. 文档任务

- `CHANGELOG.md`：beta1.1.9 条目（含"未验证边界"声明：故障注入对照 ≠ 生产事故验证）；
- 若 F02 的锁语义进入 governing 文档（安装流程说明），同步对应 `references/` 段落；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `06-f01-f02-f03-transaction-process-boundaries` | F01、F02、F03（三项独立验收，可拆子项） |

## 7. 边界

- 全局边界按总纲第一节；
- 不把隔离反例升格为真实生产事故结论；不新增摘要/校验脚本。

## 8. 执行记录（实施时填写）

| 日期 | 动作 | 证据位置 | 结果 |
| --- | --- | --- | --- |
| 2026-10-09 | 接续副本 `beta119-closeout-20261009`，保留原 beta118 工作副本；普通协作、唯一源码 writer | 共享 `D:/project/decretum-matrix/tasks/handoffs/TASK-001-20261009-codex-closeout-readback.md` | 已实际读回；本工程 lane 不提交/安装/外部发布 |
| 2026-10-09 | F03 命令解析与真实创建标记、明确死亡确认 RED/GREEN | `.scratch/beta119-closeout/f03-token-red.log`、`f03-token-green.log`、`f03-creation-red.log`、`f03-creation-green.log`、`f03-death-red.log`、`f03-death-confirmation-green.log` | RED exit 1；GREEN exit 0。Windows FILETIME 单位 100 ns，Linux boot_id + clock ticks；其他不可可靠比较的 POSIX 仅 watchdog fail-closed，无真实 daemon 停止 |
| 2026-10-09 | F01 生产 create B 前恢复 A、外部代次漂移拒绝、phase marker 落后拒绝、只读语义 | `.scratch/beta119-closeout/f01-writer-red.log`、`f01-writer-green.log`、`regression-completion.log` | RED exit 1；GREEN exit 0；completion 整文件 24 cases 通过 |
| 2026-10-09 | F02 两个空 HOME planner 零写、安全锁路径、短超时/异常释放及已有并发安装回归 | `.scratch/beta119-closeout/f02-planning-red.log`、`f02-lockpath-red.log`、`f02-boundaries-green.log`、`regression-install.log` | RED exit 1；GREEN exit 0；安装 75 cases、配置 31 cases，errors=[]；隔离 fixture 范围 |
| 2026-10-09 | 真实 Windows 创建时间 API 只读样本 | `.scratch/beta119-closeout/windows-creation-sample.json` 与独立 `.exit.txt` | exit 0；只输出隔离 Python 样本 PID/CreationDate，非 daemon 启动或停止 |

本轮源码候选边界：账本写入而下一 phase marker 落盘失败时保留账本和 marker，拒绝新业务写入，需人工恢复；不扩自动恢复框架。stage3 `KeyError: charter_sha256` 保持既有基线归因，归 TASK-023。CI 未改；SOURCE/CI 检查不替代 native host/full acceptance。

当前发布目标为 beta1.1.9 的 GitHub 与本机 private candidate。工程 lane 未执行提交、安装、push、tag、Release 或 npm publish；npm beta1.1.8 快照保持。后续状态以实际 commit、候选、安装和远端回读记录补充，不将本计划的历史发布条款作为 npm publish 的本轮授权。

上述状态为 2026-10-09 本轮构建前工程记录。冻结产品 tree 后的实际发布/安装/CI 回读由 root 写入共享 `D:/project/decretum-matrix/tasks` 与根控制面的 `audits/`；以其具体外部回执为准，不回写 tag 对应产品 tree 或预填线上 CI 成功。

## 发布与 CI 验证（按总纲 26.1）

- 本版验收通过后执行：推送到 GitHub、GitHub Release、npm 包发布（版本号 = 本版号）；
- 以既有 GitHub Actions CI 验证；**CI 内容默认不改动**（不放宽门禁、不为过审修改检查集合）；
- 仅当 CI 验证确实不可行时提出调整并经用户同意；发布前核对 workspace.yaml 的 publication_gates；
- 发布证据（Release / npm / CI 回执）记入执行记录。

---

*本计划由总纲派生；修改需同步总纲第二节与交叉引用关系。*
