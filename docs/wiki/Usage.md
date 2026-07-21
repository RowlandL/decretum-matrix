# Usage

## 调用

```text
$decretum-matrix
```

调用后直接说明目标、允许的写入范围、停止条件和外部动作边界。最新用户旨意
优先于旧计划、历史记录或生成的下一步提示。

## 权限与行为

- `authority`：只能取 `approval（审批/默认只读）`、`autonomous（自主/范围内实施）`、`super（超级执行/范围内连续推进）`。
- `behavior`：只能取 `serial（串行）`、`parallel（并行）`，与 authority 正交。
- `runtime`：native 与 `superCC` 是互斥启动入口；`superCC` 不是第四种权限。

未选择 authority 时，skill 会先确认一次。`super并行` 只表示
`authority=super, behavior=parallel, runtime=native`，不会打开、探测或加载
`superCC`。`superCC` 必须从其独立 CLI/zellij/squad 入口启动。

## 层级

```text
user -> taizi -> zhongshu | menxia | shangshu
shangshu -> libu-hr | hubu | libu | bingbu | xingbu | gongbu
ministry -> its bounded workshops
```

太子不直派六部；中书省和门下省不执行六部职责；六部只管理本部子官署。
宿主侧边栏可能把线程平铺展示；产品 receipt、dispatch packet 和奏报仍必须把六部记录为尚书省子/孙 agente，而不是太子同层直派。

## 常用表达

```text
$decretum-matrix，以 autonomous 模式修复当前分支，禁止发布，完成后给出验证证据。
```

```text
$decretum-matrix，使用 super并行做只读审查，pending_body_access=NO。
```
