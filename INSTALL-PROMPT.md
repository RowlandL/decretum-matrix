# Decretum Matrix（诏令矩阵）离线安装提示词

请安装与本文件同一发布包中的 Decretum Matrix（诏令矩阵）。规范 skill 名与调用为
`decretum-matrix` / `$decretum-matrix`；`court-capability-router` 仅保留为受保护的
物理安装目录与 ZIP 内根 locator，不是当前产品名。旧 `$court-capability-router`
输入已 deprecated，且在宿主 alias 未经探测证明前不得声称可用。

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
2. 必须安装到当前用户真实 HOME 下的 `.agents/skills/court-capability-router`；该目录名是兼容 locator，加载后必须显示 `Decretum Matrix（诏令矩阵）` / `decretum-matrix`。`.agents` 是唯一可主动创建的工具根。
3. 识别当前正在执行本提示词的 `CURRENT_AGENT_TOOL`，并从该工具的运行时、环境变量、CLI 或现有配置中证明其 `CURRENT_TOOL_SKILL_ROOT`。只把这个当前工具根作为默认可选目标；无法证明时仅安装 `.agents`，并报告 `CURRENT_TOOL_ROOT_UNPROVEN`。
4. 默认目标严格为 `.agents + 当前工具`，解析绝对路径后去重：
   - 当前是 Codex：只安装 `.agents` 和 Codex；不得安装 Claude 或 Hermes。
   - 当前是 Claude：只安装 `.agents` 和 Claude；不得安装 Codex 或 Hermes。
   - 当前是 Hermes：只安装 `.agents` 和 Hermes；不得安装 Codex 或 Claude。
   - 其他工具：只安装 `.agents` 和该工具已证明的 skill 根。
5. 只有用户最新指令明确点名其他工具时，才可增加对应目标；仍须证明工具已安装及其真实 skill 根。不得扫描后自动向所有工具分发。
6. 校验 `release-manifest.json`、`VERSION`、`references/manifests/skill-identity.v1.json` 和载荷哈希；身份清单必须声明规范产品、skill 与调用为 `Decretum Matrix（诏令矩阵）`、`decretum-matrix`、`$decretum-matrix`。已有目标先做逐文件 SHA256 备份，再无删除覆盖；不得移动或删除目标独有文件、史馆文件或用户配置。
7. 不得运行会向未点名工具扩散的 `sync_active_copies.py --write`。安装后从 `.agents` 根运行 `python -B scripts/quick_validate.py .` 和 `python -B scripts/check_install_prompt.py`，并核对各实际目标的受管文件哈希。
8. 最终报告规范产品名、载荷版本、实际安装 locator、跳过目标、备份、验证结果及保留文件；不得把候选路径写成已安装路径。
