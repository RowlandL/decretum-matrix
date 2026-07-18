# Usage

## 调用

```text
$decretum-matrix
```

调用后直接说明目标、允许的写入范围、停止条件和外部动作边界。最新用户旨意
优先于旧计划、历史记录或生成的下一步提示。

## 权限类

- `approval`：执行前逐步确认需要授权的动作。
- `autonomous`：在既有授权边界内持续执行。
- `super`：使用普通多 agent 并行，不启用 superCC pane。
- `superCC`：显式启用 CLI/zellij/squad 运行面，需额外环境门禁。

未选择权限类时，skill 会先确认一次。`super并行` 只是拓扑要求，不会自动打开
`superCC`。

## 层级

```text
user -> taizi -> zhongshu | menxia | shangshu
shangshu -> libu-hr | hubu | libu | bingbu | xingbu | gongbu
ministry -> its bounded workshops
```

太子不直派六部；中书省和门下省不执行六部职责；六部只管理本部子官署。

## 常用表达

```text
$decretum-matrix，以 autonomous 模式修复当前分支，禁止发布，完成后给出验证证据。
```

```text
$decretum-matrix，使用 super并行做只读审查，pending_body_access=NO。
```
