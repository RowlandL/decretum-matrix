# Architecture

## 三层边界

```text
D:\project                         root control plane
decretum-matrix child repository   product source and releases
~\.agents\court-shiguan\...        shared local evidence/data
```

root 管 worktree/task 映射；child 管 skill、profiles、dossiers、scripts、package 与
release；shared Shiguan 管本机 records、indexes、memory decisions 与投影。三者不
双写成同一个 ledger。

## 单一 skill authority

canonical skill 名与调用为 `decretum-matrix` / `$decretum-matrix`。各宿主投影必须
逐文件一致，旧 `court-capability-router` 只允许作为历史或受控技术 locator。

## Decree Kernel

内核由 `SKILL.md`、直接 governing references、standing profiles、ordinary
dossiers、dispatch hierarchy 和安装/发布 manifests 共同约束。carrier 或未来
Office Pack 只能补充身份与展示，不能覆盖权限、语义、隐私或收口门禁。

## 数据与工具

Codex、Claude 与 Hermes 的 native memory 继续归各自 loader/store 管理。共享
史馆只保存 metadata、裁定和引用，不复制原生私有正文或 Git objects。

## 安全原语

现有实现复用文件锁、原子替换、目录 fsync、generation/digest CAS、operation
marker、preimage、receipt、reconcile 与 rollback，不依赖新的 service、DB、MQ
或全局事件账本。
