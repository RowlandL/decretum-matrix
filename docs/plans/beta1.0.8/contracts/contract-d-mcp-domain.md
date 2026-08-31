# 契约 D — MCP 领域能力面（FR-D，draft-0.1 · 2026-08-28.beta1.0.8）

> 权威：devspec §3.5 FR-D、§3.6 Q23 采纳；manifest 投影草案：cli-command-surface-projection-draft.json。

## 1. 工具矩阵 manifest 契约（P2-1）

每个工具条目必须含：
- command_id（稳定 id）
- public/domain API（court_public_api / 领域模块函数名）
- closed input_schema（additionalProperties:false；属性带 description ≤200 字）
- side_effect（read_only | write | request_dependent）
- receipt_schema（输出 receipt schema id）
- Agent envelope 说明（actor/role/authority/write_set 语义）

复用既存 public_*：public_intake_validation_payload / public_capsule_validation_payload / public_semantic_context_validation_payload；新增领域 API（P2-2）：
- public_dispatch_plan_validation（authority/behavior 缺省按 approval/serial 校验，不引入 super+parallel 默认）
- public_closeout_checklist（对齐十四行 memorial）
- public_shiguan_entries_query（元数据投影，无 pending/private 正文）
- public_iku_candidates（只读，dry_run=true）
- 领域化 memory/capability ledger Create/Read/Update、GBrain recall/evaluate/propose、能力索引 query/refresh 状态、统一编号生成器适配

## 2. 审计（D2）

- tools/call 前后写 `court_operation_journal`：operation_id=uuid4().hex；payload_digest=payload_sha256({"tool","args"})；receipt={"ok", "result_sha256"}；journal 不含 args 原文。
- MCP 不通过 subprocess 调 CLI；现代/legacy 同构。

## 3. 账册与技能加载（D2a/D2b）

- 领域化 Create/Read/Update（Delete/整理/合并/去重/清退不纳入本版本）。
- 能力索引：常规首查 + 特例主动重查；命中后宿主加载最小多 skill 集合；记录 actor/role/authority/write_set/skill 路径·哈希/选择理由。
- 记忆裁定仍按 V2 语义层（adjudication/application/native 三层），WRITE 仅限 adjudication_status=approved。

## 4. 非核心

- Streamable HTTP /mcp + Resources：非本版本必需（保留备注），只做边界断言。

## 5. 验收指针

- P2-1 manifest 与 registry 一致；P2-3 审计探针；P2-4 全 schema description；P2-5 check_court_mcp_server 全绿；P2-6 官署 MCP 调用与多 skill 编排。
