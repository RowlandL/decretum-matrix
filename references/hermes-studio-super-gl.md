# super GL Runtime / Hermes Studio 群聊官署联动

本卷治理 `super GL`：在 Hermes Studio 群聊房间内，利用同房间 `@profile` 提及与真实房间回复形成的并行多-agent 官署协同。它是本房间验证成功的协同形态，**不依赖 zellij 或 squad**，也不等同于 `superCC`。

## Definition

`super GL` = **super Group-Link / 群聊联动官署**。

- 运行面：Hermes Studio group chat room / 群聊房间。
- 传递机制：同房间自然语言消息中的 `@profile` 提及触发对应 profile/agent；证据以实际同房间回复、房间消息上下文、profile 名称、回复格式、时间与任务边界为准。
- 默认状态：当且仅当当前执行环境确认为 Hermes Studio 群聊房间时，court workflow 默认启用 `super GL` 作为房间内多-agent 协同模式。
- 非依赖项：不得要求 zellij、squad、Codex visible panes、`ENTER_DISPATCH`、physical Enter、squad task/message id 作为 `super GL` 成立条件。
- 非替代项：`super GL` 不提升安全权限，不覆盖 `approval`/`autonomous`/`super`，也不把普通房间唤醒伪装成 `superCC`。

## Room Environment Gate

启用或声称 `super GL` 前必须检查 `super_gl_room_gate`：

```text
super_gl_room_gate: PASSED | NOT_IN_ROOM | runtime_degraded | authority_blocked
super_gl_room_id: <room id or redacted/stable pointer>
super_gl_transport: hermes_studio_group_chat_mentions
super_gl_zellij_gate: NOT_APPLICABLE
super_gl_squad_gate: NOT_APPLICABLE
```

`PASSED` 的证据可来自以下任一组合：

- 当前运行上下文明确标注群聊房间、room id、room members、或“群聊系统”路由说明；
- session/request dump 或 Studio 上下文包含 `gc_<room_id>` / `group-chat` / room participant metadata；
- Hermes Studio group-chat REST/Socket.IO 或房间 UI 只读探针确认当前 room 与 agents；
- 用户在当前房间内直接发出旨意，且系统消息声明此消息已经提及当前 agent。

若无法确认当前执行环境为房间内，则 `super GL` 必须为 `NOT_IN_ROOM` 或 `runtime_degraded`，回退到普通 court/delegate_task/Hermes profile-native 协同；不得在私聊、CLI、非房间 session、或未知来源里默认启用同房间 @ 唤醒。

## Default Startup Behavior

在房间内开朝时：

1. 太子加载 Dercretum-Matrix（诏令矩阵）（`decretum-matrix` / `$decretum-matrix`）后，检查 `super_gl_room_gate`。
2. 若 `PASSED`，记录 `super_gl_enabled=true`，默认采用同房间 `@profile` bounded wake/dispatch 作为优先多-agent 协同路径。
3. 三省初始官署创建不再需要用户手工改配置：房间成员中存在 `zhongshu`、`menxia`、`shangshu` 时，可用一次 bounded wake 实证确认在线性；没有实际回复不得声称该 office 已履职。
4. 六部与史馆仍遵循尚书省差遣、任务边界、证据契约与释放规则；不得因 `super GL` 默认启用而无限 @all 或循环催促。
5. 若房间 wake 部分成功，记录 responders/non_responders，并以 `parallel_dispatch: USED | runtime_degraded` 继续；不得模拟未回复 agent。

## Dispatch Contract

`super GL` 下的房间派发包必须包含：

```text
runtime_client: hermes_studio_group_chat
source_agent_label: Hermes
calling_office: taizi | shangshu | ...
assigned_profile: zhongshu | menxia | shangshu | hubu | ...
dispatch_delivery_channel: GROUP_CHAT_MENTION
super_gl_room_gate: PASSED
super_gl_task_id: room-message-id | compact generated id
context_packet_complete: YES | PARTIAL | NO
expected_reply_format: compact office report or OK｜角色名｜一句状态
stop_conditions: no reply after bounded probe; 429/rate-limit; user boundary; safety/privacy gate
```

有效的 office 结果必须至少具备：

- 同房间真实回复，且发送者 profile/role 与 assigned_profile 匹配；
- 回复内容足以证明接收、审议、执行、复核或阻塞状态；
- 太子没有代写该 office 的结论；
- 史馆记录 responders/non_responders 与任何 sync/runtime caveat。

## Safety And Anti-loop Rules

- 不使用 `@all` 作为默认开朝或巡检方式；只点名本轮需要的 office。
- 不连续催促沉默 profile；一次 bounded wake/dispatch 后即可记录 non_responder。
- 不通过 agent-origin 消息无限递归触发 agent-to-agent 风暴。
- 不把房间消息、私密会话、tokens、agentSocketSecret、auth tokens、Obsidian API key 写入 Shiguan 或用户报告。
- 429/rate-limit 出现时退避、分批、记录 `runtime_degraded`，不得增加并发催醒。
- `super GL` 只提供协同传输形态；破坏性、付费、联网、外部状态、私密数据上传等仍由当前三权和门下省门禁控制。

## Closeout Fields

当 `super GL` 被启用或尝试启用时，完整史馆记录应包含：

```text
super_gl_enabled: true | false
super_gl_room_gate: PASSED | NOT_IN_ROOM | runtime_degraded | authority_blocked
super_gl_room_id: ...
super_gl_transport: hermes_studio_group_chat_mentions
super_gl_zellij_gate: NOT_APPLICABLE
super_gl_squad_gate: NOT_APPLICABLE
super_gl_wake_list: [...]
super_gl_responders: [...]
super_gl_non_responders: [...]
super_gl_dispatch_delivery_channel: GROUP_CHAT_MENTION | NOT_RUN
super_gl_office_duty_enforcement: PASSED | PARTIAL | FAILED | runtime_degraded
super_gl_anti_loop_policy: bounded_no_all_no_retry_storm
```

用户侧短结诏可在 `运行态与并行` 一行压缩呈现：`super GL=PASSED/PARTIAL；room_gate=PASSED；responders=...；zellij/squad=NOT_APPLICABLE`。
