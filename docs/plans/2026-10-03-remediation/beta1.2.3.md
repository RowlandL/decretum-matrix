# beta1.2.3 独立计划 · 安装入口与锁生命周期

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.2](./beta1.2.2.md)｜下一版：[beta1.2.4](./beta1.2.4.md)
> 依赖：[beta1.1.9](./beta1.1.9.md)（F02 的锁范围是完整验收前置）｜被依赖：[beta1.2.4](./beta1.2.4.md)、[beta1.3.2](./beta1.3.2.md)
> 工单：`10-f10-f12-install-entry-lock`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F10、F12

## 1. 版本目标

安装入口的参数解析与锁生命周期不再互相干扰：**前置全局参数不影响 install 组定位**（F10）；**锁在异常退出后不残留**（F12）。两项均修复既有机制，不改变安装策略。

## 2. 修复条目

### 2.1 F10 · 前置全局 format 参数使新装入口误走 binding 分支（P2）

- 现象：全局 `format` 参数放在最前时，新装入口误走"必须已有 binding"的分支。
- 位置：`bin/decretum-matrix.py:386`。
- 修复要求：按已有格式规则定位 install 组；保持合法参数排列的兼容（前轮已用真实隔离子进程复现）。
- 验收（可测）：
  - [x] `format` 前置 / 置后 / 缺省三种排列均可正确进入 install 组；（隔离 HOME 实测：`install --help`、`--format text install --help`、`--format=json install --help`、`install --help --format text` 均 exit 0 并输出安装驱动帮助；回归 `check_launcher_install_group_location`）
  - [x] 非法排列仍报明确错误；（`--format xml install --help` 与裸 `--format` 均 exit 1 且报 `--format must be / requires text or json`，不再落到 binding 错误）
  - [x] 不改变既有参数契约与帮助文本结构（除必要的说明修正）；（非 install 组把调用方 argv 原样交给运行时 CLI，`--format json court status` 交付断言见 `check_install_current_agent_copy.py`；根帮助结构与 `court_cli_registry` 解析未改）
- 证据：隔离子进程调用对照（正/负例）。

### 2.2 F12 · binding O_EXCL sentinel 残留导致 busy（P2）

- 现象：binding 提交的 `O_EXCL` sentinel 在真实子进程异常退出后残留，下一次正常申请被持久拒绝 `busy`。
- 位置：`scripts/install_current_agent_copy.py:386`。
- 修复要求：复用现有 OS 锁释放机制；确认 sentinel 与持有进程身份/存活状态关联；与 F02 的"全过程锁范围"是两个根因，分别验收。
- 验收（可测）：
  - [x] 异常退出（kill/中断）后下一次正常申请成功（不出现持久 busy）；（真实持锁子进程 `kill()` 后基线为 `STALE_BUSY:installation_binding_busy`，修复后为成功重入；回归 `check_binding_commit_lock_lifecycle`）
  - [x] 真实持有中的并发申请仍被拒绝（正常互斥语义保留）；（真实子进程持锁期间第二申请得到 `installation_binding_busy`，属性 `live_holder_excluded=true`）
  - [x] 无僵尸锁残留（配合 1.1.9 的 F02 一并回归）；（锁归属改为活进程 OS 字节锁；锁文件持久存在不再被当作僵尸锁，且预植链接/硬链接在打开前失败关闭，外部目标字节不变）
- 证据：异常退出模拟脚本 + 前后对照；未执行真实安装时标注。

## 3. 版本出口（Exit Criteria）

- [x] F10/F12 负例与正例齐全；（F10：5 正例 + 2 非法取值负例 + 1 失败关闭对照；F12：live-holder 互斥、kill 释放、primitive 链接拒绝、open 窗口替换拒绝、F02 锁范围）
- [x] 与 1.1.9 的 F02 修复联合回归（锁范围 + 锁释放）；（HOME 级安装锁被真实子进程持有时，binding 提交在锁内以 `installation_busy` 失败关闭，未触碰文件）
- [x] 不改安装策略、不新建锁框架。（safe-open 是在既有 `court_file_lock.file_lock` 原语内部修复，未新增锁体系、未改安装策略、未放宽 300s 与断言）

## 4. 依赖与顺序

- F02（1.1.9）完成后本版验收更完整；F10 可独立先行。

## 5. 文档任务

- `CHANGELOG.md`：beta1.2.3 条目；
- 若参数约定写入 `docs/wiki/Installation.md` 或 README，同步必要说明（与 1.2.4 的首装说明合并更新）；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `10-f10-f12-install-entry-lock` | F10、F12 |

工单位置说明：计划指向本地 `.scratch/remediation-2026-10/issues/`，该目录不在本仓库版本库中（`.scratch` 目录在本工作区不存在）。按总纲「仓库外只读引用不参与仓库内链接校验」处理：此处只登记位置与缺失事实，不在仓库内另造工单权威。

## 7. 边界

- 全局边界按总纲第一节；不执行真实安装到用户环境（隔离 HOME 验证）；
- 不承诺跨平台锁完整验证（该项归 beta1.3.3 平台验收子项）。

## 8. 执行记录（实施时填写）

| 日期 | 动作 | 证据位置 | 结果 |
| --- | --- | --- | --- |
| 2026-11-02 | 基线复现（F10）：隔离 HOME 下 `install --help` exit=0 进入安装驱动；`--format text install --help` 与 `--format=json install --help` exit=1 `installation_binding_missing_or_invalid` | `scripts/checks/check_install_current_agent_copy.py` `check_launcher_install_group_location` | 复现 |
| 2026-11-02 | F10 修复：launcher 先按既有全局规则消费 `--format` / `--format=`，再定位子组；安装驱动只收组后参数 | `bin/decretum-matrix.py` | 已实现，5 个正例排列 + 2 个非法取值负例通过 |
| 2026-11-02 | 基线复现（F12）：真实持锁子进程被 kill 后 `.<binding>.lock` 残留，下一次提交 `STALE_BUSY:installation_binding_busy` | `check_binding_commit_lock_lifecycle` 隔离探针 | 复现 |
| 2026-11-02 | F12 修复：binding 提交锁改用既有 `court_file_lock.file_lock`；锁归属为活进程 OS 字节锁 | `scripts/install_current_agent_copy.py` | 已实现；kill 后下一次提交成功，活跃持有者仍 `installation_binding_busy` |
| 2026-11-02 | F02 联合回归：HOME 安装锁被真实子进程持有时 binding 提交在锁内失败关闭 | `check_binding_commit_lock_lifecycle` | 通过（`installation_busy`，未触碰文件） |
| 2026-11-02 | 版本标识 beta1.2.3 同步：VERSION/SKILL/plugin/SBOM/release-manifest/github release metadata/legal+metadata 常量/CHANGELOG/RELEASE-LOG | `scripts/checks/check_release_metadata.py --json` | PASSED |
| 2026-11-02 | R1 锁路径回归（复核 P2）：`os.open` 前预检 + 描述符/名称 inode 校验 + `O_EXCL` 创建 + 取锁后复核；`UnsafeLockPathError` 映射为 `installation_binding_lock_path_invalid`；并发合法创建者限次重试 | `scripts/court_file_lock.py`、`scripts/install_current_agent_copy.py`、`check_install_current_agent_copy.py`（新增 primitive 链接与 open 窗口替换负例） | 通过；判别性对照：去掉描述符校验后外部目标被写入 `00` |
| 2026-11-02 | R2 运行时门禁：按真实用例量化后，把 25 个独立用例改为各自 runtime root（保留原序/原断言/真实规模压力用例） | `scripts/checks/check_court_agent_lifecycle.py` | `check_court_agent_lifecycle` 86.68s rc0；`check_court_runtime` 135.61s rc0（原 300s 上限未改） |
| 2026-11-02 | npm 夹具耦合修复：合成夹具标签与 live VERSION 撞车（`fixtureVersionCore` 1.2.3 固定值） | `scripts/build_npm_package.mjs` | 改为 1.2.4 后 `npm test` 真实入口 356 行 PASS、rc0（起止/耗时未捕获，按 NOT_CAPTURED 记录） |
| 2026-11-02 | 独立复核：门下 STANDARDS 与中书 SPEC 两轮最终复核 | `menxia-standards-review.md`、`menxia-standards-final.md`、`zhongshu-spec-review.md`、`zhongshu-spec-final.md`（canonical receipts 平铺文件名） | 最终均无剩余 P1/P2，接受本地开发提交（不构成发布验收） |
| 2026-11-02 | 本地开发提交：单提交窗口 stage 29 个已测路径（staged 集与允许集完全一致） | `adf50f9356feb613be135b74d04f3f422700e6fb`，tree `d7e44dcf2f2a9ebd7648cfe0d1a918b21fdfb08a` | 提交后 staged=0、子仓干净；父提交 `4e83c76`，`release/beta1.2.2` 与 tag 未动 |
| 2026-11-02 | 清单与门禁收口：既有 `release_payload_manifest.py` 刷新 `files` 索引与 `integrity` | `release-manifest.json`（511 项） | `--check` exit 0、`check_release_manifest` exit 0（steps=53, negative_cases=14） |
| 2026-11-02 | 开发完成性核查（本轮）：逐项验收矩阵与文档状态回填，无源代码改动 | canonical `plan-completion-audit-20261102.json` | 源码相对 `adf50f9` 零差异；仅文档/状态收口 |

## 发布与 CI 验证（按总纲 26.1）

- 本版验收通过后执行：推送到 GitHub、GitHub Release、npm 包发布（版本号 = 本版号）；
- 以既有 GitHub Actions CI 验证；**CI 内容默认不改动**（不放宽门禁、不为过审修改检查集合）；
- 仅当 CI 验证确实不可行时提出调整并经用户同意；发布前核对 workspace.yaml 的 publication_gates；
- 发布证据（Release / npm / CI 回执）记入执行记录。

---

*本计划由总纲派生；修改需同步总纲第二节与交叉引用关系。*
