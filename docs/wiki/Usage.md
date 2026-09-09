# Usage

本页说明**怎么用**。安装见 [Installation](Installation.md)；功能模块见
[Modules](Modules.md)；命令行与 MCP 见 [CLI and MCP](CLI-and-MCP.md)。

## 1. 调用

```text
$decretum-matrix
```

调用后直接说明目标、允许的写入范围、停止条件和外部动作边界。最新用户旨意优先于旧计划、
历史记录或生成的下一步提示。

## 2. 权限与行为

- `authority`：只能取 `approval（审批/默认只读）`、`autonomous（自主/范围内实施）`、
  `super（超级执行/范围内连续推进）`。
- `behavior`：只能取 `serial（串行）`、`parallel（并行）`，与 authority 正交。
- `runtime`：native 与 `superCC` 是互斥启动入口；`superCC` 不是第四种权限。

未选择 authority 时，skill 会先确认一次。`super并行` 只表示
`authority=super, behavior=parallel, runtime=native`，不会打开、探测或加载
`superCC`。`superCC` 必须从其独立 CLI/zellij/squad 入口启动。

## 3. 层级

```text
user -> taizi -> zhongshu | menxia | shangshu
shangshu -> libu-hr | hubu | libu | bingbu | xingbu | gongbu
ministry -> its bounded workshops
```

太子不直派六部；中书省和门下省不执行六部职责；六部只管理本部子官署。
宿主侧边栏可能把线程平铺展示；产品 receipt、dispatch packet 和奏报仍必须把六部记录为
尚书省子/孙 agent，而不是太子同层直派。

## 4. 一次标准流程

```text
太子定性 → 三省会审/上奏 → 太子回奏 → 尚书统合六部 → 工坊办差 → 门下复核 → 史馆实录
```

对应状态机：

```text
Pending → Taizi → ThreeDepartments → ThreeDepartmentsPetition → TaiziReply
→ ShangshuDispatch → SixMinistries → Workshops → MenxiaReview → ShiguanRecorded → Done
```

## 5. 常用表达

```text
$decretum-matrix，以 autonomous 模式修复当前分支，禁止发布，完成后给出验证证据。
```

```text
$decretum-matrix，使用 super并行做只读审查，pending_body_access=NO。
```

```text
$decretum-matrix，以 superCC 模式启动，并验证 zellij 与 squad 门禁。
```

## 6. 日常命令入口

| 你想做什么 | 命令 |
| --- | --- |
| 开朝 | `decretum-matrix court open` |
| 看状态 | `decretum-matrix court status --view compact --limit 1` |
| 拟计划 / 复核 | `decretum-matrix court plan template|submit|review` |
| 派遣官署 | `decretum-matrix office admit` → `office native-request` |
| 回奏 | `decretum-matrix office report` |
| 结诏归档 | `decretum-matrix shiguan archive-runtime-task` |
| 查历史 | `decretum-matrix shiguan query-shiguan-index <关键词>` |

完整命令面与 MCP 工具矩阵见 [CLI and MCP](CLI-and-MCP.md)。

## 7. 边界提醒

- `approval` 默认只读；`autonomous` 范围内实施；`super` 范围内连续推进。
- 三权均不自动授权破坏、泄密、付费、私密上传、公网暴露、未验证安装或无界树。
- 外部工具、额外安装目标、发布/推送须当前明确授权。
- MCP 面恒为只读；状态变更走 CLI，真实派遣走宿主。
