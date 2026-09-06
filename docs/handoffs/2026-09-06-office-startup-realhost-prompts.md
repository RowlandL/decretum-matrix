# 子官署真实启动验收提示词（供 Codex 低级模型执行）

> 用途：完成 ChatGPT 返回包中唯一未跑的“真实宿主派遣验收”（live_host_spawn=NOT_RUN）。
> 执行者：用户在真实宿主上用 Codex（低级模型）执行；本文件是可直接复制的提示词。

---

```text
你是 Decretum Matrix beta1.1.0 的验收执行官署（子官署/工坊视角）。只做“尚书省→礼部”一次
合法、已准入的真实启动验收与证据采集；不改产品源码、不提交、不 push、不 tag、不发布。

工作目录：D:\project\decretum-matrix（分支 release/beta1.1.0）
背景：已合入 office-startup 补丁（scripts/court_runtime.py 的 _native_bridge_identity_context
按 case_ref==case_reference(task) 识别父级；scripts/commands/court_native_bridge.py bootstrap
明确 read-and-ack only；新增 scripts/checks/check_office_decree_startup.py 七项回归）。
到目前为止全部验证都是 fixture/隔离环境；真实宿主必须完成下列验收并留痕。

目标：完成一次【真实】的 Shangshu→Libu（礼部）派遣启动：
  request → 真实宿主 spawn → 子官署真实读取材料 → child_acceptance → 上级接受 → 首个报告。

必须步骤（按次序）：
1. 用仓库公开 CLI（如 decretum-matrix 命令）或等价真实链路创建一个合法任务：
   - 标题 office-startup real-host acceptance；计划仅一个步骤 role=libu；
   - 走正常流程：Taizi → ThreeDepartments → plan submit → menxia approved →
     shangshu dispatchable → semantic checkpoint → verify → agent-admit
     （wave 仅 libu，calling_office=shangshu，direct_superior=shangshu/taizi 按契约）。
   - 不得用伪造回执代替真实准入；如某一步 CLI 不可用手动等价路径，须在报告中说明。
2. 真实启动子官署（用 Codex 低级模型/当前宿主）：
   - 子官署真实读取：SKILL.md、agents/standing-officials/libu.toml、
     agents/office-dossiers/libu/AGENTS.md；
   - 返回 child_acceptance（schema court.child_preload_acceptance.v1）；
   - 等待上级（shangshu）接受后再执行业务 CLI/MCP。
3. 证据落盘到：
   D:\project\.staging\dm110-20260905\t08-bingbu\office-startup-real-host\acceptance-<utc>.json
   字段（只填真实可观测值）：
   - request: task_id / wave_id / instance_id / case_ref / office_capsule_ref / role
   - spawn: spawned_agent_id / thread_id / session_id
   - reads: 三个材料路径 + 字节数 + 是否成功
   - acceptance: child acceptance receipt（含 receipt_id / task_id / role_key）
   - superior_acceptance: shangshu 接受证据（事件或回执 id）
   - first_report: event action + evidence
   - 外部调用统计：子官署启动到首报告之间 subprocess/工具调用次数、耗时（只报实测）
4. 结束前跑并记录（exit code + 首错，如失败）：
   python -B scripts/checks/check_office_decree_startup.py
   python -B scripts/checks/check_court_native_bridge.py
   python -B scripts/checks/check_native_opaque_capture.py
   python -B scripts/check_court_office_bootstrap.py
   python -B scripts/check_court_native_host_dispatch.py
   python -B scripts/checks/check_court_case_binding.py
   并输出 git status。

禁止：
- 用 fixture / mock / 模拟宿主代替真实子官署；不得把 PENDING 写成成功；
- 跳过准入、预载、上级接受或身份校验；
- 重写/关闭旧回执，不得重放已完成动作；
- 改动产品源码、提交、push、tag、发布；
- 声称 release-gate 通过或 T08 之外问题被顺带解决。

输出：一个 markdown 验收报告（事实、证据路径、结论 PASS / FAIL / NOT_RUN、
用时与外部调用统计）+ 上述 JSON 证据。结论只允许基于真实可观测结果。
```

---

### 执行者备忘
- “低级模型”仅影响生成成本，不影响契约：请用 `codex` CLI 的 `-m low`（或等价）运行，但**必须真实执行**，不得让模型只生成报告而不启动。
- 若当前宿主无法真实 spawn（无适配器/无权限），请返回 `NOT_RUN` 并写明缺失项，不要伪造。
- 完成后把报告与 JSON 放回：
  `D:\project\decretum-matrix\docs\handoff_packages\beta1.1.0-source-review-2026-09-06\evidence\office-startup-real-host\`
