# Troubleshooting

## `$decretum-matrix` 无法调用

如果错误仍要求：

```text
C:\Users\<user>\.agents\skills\court-capability-router\SKILL.md
```

说明宿主 policy/index 仍引用迁移前路径。canonical path 应为：

```text
C:\Users\<user>\.agents\skills\decretum-matrix\SKILL.md
```

修复 root/global `AGENTS.md` 与 capability index 的 locator，并在全新只读会话中
真实调用 `$decretum-matrix`。不要复制第二份旧目录来绕过门禁。

## 角色 projection 不同步

先运行只读检查：

```powershell
python -B scripts/check_codex_agent_roles.py
```

若 14 个 role 格式有效但全部 unsynced，先裁定 repository profiles 与当前
`.codex/agents` 哪个是 source of truth；不要直接用旧 profile `--write` 覆盖较新
配置。

## 史馆或 Obsidian 路径异常

检查默认共享根是否为 `.agents\court-shiguan\decretum-matrix\references`，再运行：

```powershell
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
python -B scripts/ensure_shiguan_autosync.py --check-only
```

只检查公开配置和路径。不要用排错命令枚举或打开 pending/private 正文。

## 发布 gate 失败

按 first-fail 修复单一 cluster。不要在 source gate 失败时构建 candidate，也不要
在 ZIP、manifest 或 accepted commit 漂移后复用旧 install receipt。
