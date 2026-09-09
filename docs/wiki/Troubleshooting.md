# Troubleshooting

本页按「现象 → 原因 → 处置」组织。诊断命令默认只读；排错时不得读取或枚举
pending/private 正文。

## 1. `$decretum-matrix` 无法调用

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

## 2. `decretum-matrix` 命令找不到

先确认 npm 全局 prefix：

```sh
npm prefix -g
decretum-matrix --version
```

如果 PATH 缺失，直接解析当前 npm prefix 下的 `decretum-matrix.cmd`（Windows）或
`decretum-matrix`（macOS/Linux）。**不要**降级为内部 Python 业务脚本，否则会绕过
公开 CLI 的收据与门禁。

## 3. CLI 返回 `source_checkout_required`

`check`、`release` 与部分 `install` 命令需要源码检出（source checkout）。
在安装副本或普通工作目录里运行会返回该错误，这是**预期行为**，不是故障。

处置：切到源码检出后重试，例如：

```sh
cd <source-checkout>/decretum-matrix
decretum-matrix check doctor --format json
```

## 4. MCP 工具在宿主里看不到

按顺序确认：

1. 服务器入口是否正确：`scripts/court_mcp_server.py`。
2. 协议版本：现代客户端须发 `2026-07-28` 与所需 `_meta`；发 `initialize` 的
   客户端走 legacy `2025-11-25` 语义，须补 `notifications/initialized`。
3. `tools/list` 不分页：省略 `cursor` 或传空串；非空 cursor 返回 `-32602`。
4. 源码 wire 行为：

```sh
python -B scripts/probe_court_mcp_modern_wire.py --host-state source_checkout
```

探针只证明源码 wire；宿主可见性（Codex / CC Switch 已加载）需要单独回执，
不能用探针代替。

## 5. MCP 调用报参数错误

MCP 输入按闭合 schema 校验，错误码可直接定位：

| 错误 | 含义 | 处置 |
| --- | --- | --- |
| `unknown_arguments:<names>` | 传了 schema 未声明的参数 | 只传该工具声明的参数 |
| `missing_arguments:<names>` | 缺少必填参数 | 补上必填项 |
| `tool_not_allowed:<name>` | 工具名不在投影清单中 | 核对工具名拼写 |
| `*_must_be_one_of:...` | 枚举值非法 | 改用列出的取值 |

`write_enabled` 恒为 `false`；MCP 不执行任何写入，需要写入请改用 CLI。

## 6. 角色 projection 不同步

先运行只读检查：

```powershell
python -B scripts/check_codex_agent_roles.py
```

若 14 个 role 格式有效但全部 unsynced，先裁定 repository profiles 与当前
`.codex/agents` 哪个是 source of truth；不要直接用旧 profile `--write` 覆盖较新
配置。

## 7. 史馆或 Obsidian 路径异常

检查默认共享根是否为 `.agents\court-shiguan\decretum-matrix\references`，再运行：

```powershell
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
python -B scripts/ensure_shiguan_autosync.py --check-only
```

只检查公开配置和路径。不要用排错命令枚举或打开 pending/private 正文。

## 8. 发布 gate 失败

按 first-fail 修复单一 cluster。不要在 source gate 失败时构建 candidate，也不要
在 ZIP、manifest 或 accepted commit 漂移后复用旧 install receipt。

## 9. 还不知道从哪查

在源码检出内运行：

```sh
decretum-matrix check doctor --format json
decretum-matrix check debug  --format json
```

两个命令都会脱敏 secrets、全程只读，并输出结构化的判定依据。
