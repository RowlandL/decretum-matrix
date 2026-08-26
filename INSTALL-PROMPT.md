# Decretum Matrix（诏令矩阵）离线安装提示词

请安装与本文件同一发布包中的 Decretum Matrix（诏令矩阵）。规范 skill 名与调用为
`decretum-matrix` / `$decretum-matrix`；包根与物理安装目录均为
`decretum-matrix`。旧 `court-capability-router` 只可作为指向同一物理 authority
的 deprecated locator；旧 `$court-capability-router` 输入在宿主 alias 未经探测
证明前不得声称可用。

```text
INSTALL_POLICY
required_target = .agents
default_optional_target = current_agent_tool_only
extra_targets = explicit_latest_user_request_only
fanout = forbidden
delete = forbidden
network = forbidden
```

1. 从本文件所在目录、当前附件或同批文件中定位唯一发布 ZIP 或已解压的包根；包根必须同时包含 `SKILL.md`、`VERSION`、`release-manifest.json`、`references/manifests/skill-identity.v1.json` 和 `scripts/`。找不到完整载荷时报告 `SOURCE_MISSING`，不要联网获取。
2. 必须安装到当前用户真实 HOME 下的 `.agents/skills/decretum-matrix`；加载后必须显示 `Decretum Matrix（诏令矩阵）` / `decretum-matrix`。旧 `.agents/skills/court-capability-router` 只能不存在，或作为经过验证且指向该 canonical 目录的兼容 locator；不得保留第二份可写副本。`.agents` 是唯一可主动创建的工具根。
3. 识别当前正在执行本提示词的 `CURRENT_AGENT_TOOL`，并从该工具的运行时、环境变量、CLI 或现有配置中证明其 `CURRENT_TOOL_SKILL_ROOT`。只把这个当前工具根作为默认可选目标；无法证明时仅安装 `.agents`，并报告 `CURRENT_TOOL_ROOT_UNPROVEN`。
4. 默认目标严格为 `.agents + 当前工具`，解析绝对路径后去重：
   - 当前是 Codex：只安装 `.agents` 和 Codex；不得安装 Claude 或 Hermes。
   - 当前是 Claude：只安装 `.agents` 和 Claude；不得安装 Codex 或 Hermes。
   - 当前是 Hermes：只安装 `.agents` 和 Hermes；不得安装 Codex 或 Claude。
   - 其他工具：只安装 `.agents` 和该工具已证明的 skill 根。
5. 只有用户最新指令明确点名其他工具时，才可增加对应目标；仍须证明工具已安装及其真实 skill 根。不得扫描后自动向所有工具分发。
6. 核对 `release-manifest.json`、`VERSION`、`references/manifests/skill-identity.v1.json` 和安装投影；身份清单必须声明规范产品、skill 与调用为 `Decretum Matrix（诏令矩阵）`、`decretum-matrix`、`$decretum-matrix`。已有目标先备份将被替换的受管公开文件（逐文件 SHA256 持久备份），再执行原子覆盖；目标独有文件、史馆实录、private/pending 正文和用户配置均不得读取、移动、删除或覆盖。写入失败必须自动回滚；成功回执必须保留 `backup_root` 和显式 rollback 路径。
7. 如遇旧物理目录 `.agents/skills/court-capability-router` 与 canonical 目录冲突，先运行 `python -B scripts/migrate_legacy_skill_locator.py plan --json` 取得只读计划；只有最新明确授权迁移时才运行 `python -B scripts/migrate_legacy_skill_locator.py apply --write --json`，并保留其 `receipt_path` 供 `rollback --receipt <path> --write` 使用。不得手动删除旧目录。
8. 若当前工具根被安装器以 `protected_anchor_wrong_target` 拒绝，说明该根是旧式完整副本且含只允许位于 `.agents` 的史馆锚点。不得手动删除或覆盖；从受控源使用 `migrate_current_tool_replica.py plan --package <release_zip> --json`，并在最新明确授权后执行 `apply --package <release_zip> --write --json`。它会保留整目录 preimage 和受管文件备份；回滚使用同一 ZIP 与返回的 `receipt_path`。
9. 不得运行会向未点名工具扩散的 `sync_active_copies.py --write`。校验仅在安装时进行：从发布包/安装源运行 `python -B scripts/quick_validate.py .`，通过后校验脚本自删，安装根不得保留校验脚本；并核对各实际目标的受管文件是否来自当前投影。
10. 最终报告规范产品名、载荷版本、实际安装 locator、跳过目标、备份根、rollback 请求、验证结果及保留文件；不得把候选路径写成已安装路径。
