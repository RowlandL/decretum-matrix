# Architecture

## 五层架构

```text
通用任务治理框架
├── 史馆 GBrain
├── 治理实现
│   ├── three-departments-six-ministries（默认官方实现）
│   └── direct-review（非默认参考实现）
├── 能力与运行适配层
└── 呈现层
```

### 通用任务治理框架

框架承担任务接收、边界确认、生命周期、能力协调、证据管理、验收、暂停、
恢复和回放。现有 court runtime、semantic receipt、operation journal 与 release /
install gates 仍是唯一状态和执行权威；治理注册表不写任务状态，也不创建第二
ledger、第二语义胶囊或第二状态机。

`references/manifests/governance-implementations.v1.json` 只选择治理语义。默认
实现固定为 `three-departments-six-ministries`。每个实现必须复用框架服务：
state/evidence 为 `court-runtime`，memory 为 `shiguan-gbrain`。

事实、解释、裁定、行动、验证、记忆与呈现使用
`decretum.semantic.record.v1` 建立可验证关系。它是纯验证合同，不是新存储：
事实不能由解释冒充，行动必须有裁定依据，验证必须绑定事实与行动，记忆和呈现
不得取得执行权。

新正式任务通过 `court.request_understanding.v1` 评估目标、使用场景、关键要求和
验收标准。低于 95 只进入单问题澄清；达到阈值后复述确认，或在旨意已经明确时
直接执行。`RESTATE_CONFIRM` 仅是待用户确认的前置态，不能创建正式任务；确认后
才转为 `DIRECT_EXECUTION`。该对象嵌入 conversation gate，不形成第二任务状态。

### 史馆 GBrain

史馆 GBrain 复用 shared Shiguan index、实录和既有 memory decision 工具，提供
经历实录、长期记忆、情境召回、冲突保留、时效判断与再裁定。召回 envelope 为
`decretum.gbrain.recall.v1`，固定 `authority=advisory`、
`execution_authority=false`、`current_decree_precedence=true`。因此不同治理实现
可以共用相同召回结果，但历史记忆不能覆盖最新用户旨意。

共享 `references` 根同时承载一个 local-only Git 管理 hub。它用稳定 registry、
工具 namespace、双向 managed link 和 paired receipt 连接 Codex、Claude Code、
Hermes 各自的原生记忆仓库；跨仓库提交不伪装成原子事务。GBrain 只读取裁剪后的
store/commit/transaction provenance，不暴露本机 native root 或 git-dir。
空白机的 probe 不写入；显式 apply 才创建 Codex、Claude Code、Hermes 的 canonical
memory root 与 entrypoint，并将三者全部登记到史馆。

### 治理实现

三省六部完整保留太子、三省、六部、工坊、会审、回奏、差遣、复核和古制表达。
官方适配器直接读取既有 `court-dispatch-hierarchy.v1.json`，不复制层级边。

`direct-review` 只证明有限替换性：coordinator 负责接收、解释、协调和呈现，
reviewer 负责裁定和验证，executor 负责行动。它不是默认实现，不启用动态代码、
远程发现、插件市场或新的运行服务。

### 能力与运行适配层

Codex、Hermes、CLI、superCC、skills、MCP 和 scripts 将有界差遣映射到当前宿主
能力，并回传既有结构化结果。适配器不能改变直接上级、权限、写集、安全门、
pending body 边界或治理实现的角色职责。

### 呈现层

CLI、用户侧结诏、史馆 Web 与 Obsidian 只呈现已绑定的事实、裁定和证据。
呈现文本不是任务状态、执行授权或记忆权威，派生视图不得反向覆盖源记录。

## 仓库与数据边界

```text
D:\project                         root control plane
decretum-matrix child repository   product source and releases
~\.agents\court-shiguan\...        shared local evidence/data
```

root 管 worktree/task 映射；child 管 skill、profiles、dossiers、scripts、package 与
release；shared Shiguan 管本机 records、indexes、memory decisions 与投影。三者不
双写成同一个 ledger。

Codex、Claude 与 Hermes 的 native memory 继续归各自 loader/store 管理。共享
史馆只保存 metadata、裁定、registry 和引用，不复制原生私有正文或 native Git
objects。共享仓库无 remote，native 仓库独立存在；不使用 submodule/subtree。

现有实现复用文件锁、原子替换、目录 fsync、generation/digest CAS、operation
marker、preimage、receipt、reconcile 与 rollback，不依赖新的 service、DB、MQ
或全局事件账本。
