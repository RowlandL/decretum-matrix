# Decretum Matrix（诏令矩阵）使用手册

## 1. 这是什么

Decretum Matrix（诏令矩阵）是一个面向 CLI Agent 的任务路由与协作编排
skill，规范 skill 名与调用为 `decretum-matrix` / `$decretum-matrix`。它把复杂
任务拆成可管理的职责区：太子总领目标，中书省起草与规划，门下省审查与驳正，
尚书省执行与分派，六部承担不同专业方向。

它的目标不是增加形式，而是让 Agent 在空白环境中也能快速知道：

- 当前任务该由谁判断、谁执行、谁复核。
- 什么时候可以直接做，什么时候必须先检查。
- 普通并行、super 并行、superCC 有什么不同。
- Codex、Claude、Hermes 或其他 CLI Agent 应该怎样选择与启动。
- 史馆应该记录什么，哪些本地内容不能进入便携包。

## 2. 适合什么场景

适合以下任务：

- 多步骤代码修复、打包、验证、复盘。
- 需要多个 Agent 或多个终端协作的任务。
- 需要明确只读、可写、可变更边界的任务。
- 需要跨平台运行的脚本、配置、skill、CLI 启动器维护。
- 需要把过程记录到史馆，但又不能泄露本机日志、密钥、私有记录的任务。

不适合以下任务：

- 一句话能回答的简单问题。
- 不需要协作、不需要状态机、不需要记录的小改动。
- 用户明确要求只给结论、不要动文件的场景。

## 3. 核心概念

### 三省

- 太子：总目标、边界、最终取舍。需要保证任务方向不跑偏。
- 中书省：起草方案、拆解步骤、组织执行计划。
- 门下省：审查方案、发现风险、指出不符合约束的地方。
- 尚书省：把方案落实到具体命令、脚本、文件、包和验证。

### 六部

- 吏部：人员、能力目录、CLI 工具识别、角色分派。
- 户部：资源、预算、上下文、令牌、运行成本。
- 礼部：格式、文档、对外表达、手册、用户可读结果。
- 兵部：执行、进程、并行、守护、恢复。
- 刑部：安全、门禁、权限、错误处理、回滚边界。
- 工部：代码、脚本、构建、打包、跨平台适配。

### 三权

三权是开朝时的权限姿态：

- `approval`：先请示再做高风险动作。
- `autonomous`：在明确目标内自主推进。
- `super`：允许更强并行和更完整的执行链。

### super 并行与 superCC

`super 并行` 表示主流程可以并行调度多个检查、读取、执行或复核工作。

`superCC` 是更严格的协作模式。正常 superCC 要求具备 `zellij` 和 `squad`，并且角色唯一、消息可追踪、终端或会话状态可验证。没有满足这些条件时，不能假装已经进入正常 superCC，应当降级说明。

### 史馆

史馆用于记录任务事实、决策、验证结果和可复用经验。便携包不应包含本机原始史馆正文、原始日志、密钥、会话记录、运行账本或私有导入队列。包内只保留可公开复用的索引、说明和结构化参考。

## 4. 快速开始

### 触发方式

在 Codex、Claude、Hermes 或其他支持 skill 的 CLI Agent 中，优先使用规范调用：

```text
调用 `$decretum-matrix`，按 super 并行执行，先制定计划，再实施、验证、打包。
```

如果只需要审查，不希望改文件，可以说：

```text
调用 `$decretum-matrix`，只读审查，不做安装、不改文件、不杀进程。
```

如果需要 superCC，可以说：

```text
调用 `$decretum-matrix`，以 superCC 模式启动，并验证 zellij 与 squad 门禁。
```

旧 `$court-capability-router` 输入已 deprecated；只有宿主 alias 探测明确通过时，
才可把它作为兼容输入解析到同一物理 skill authority，不得复制第二份 skill。

### 第一次检查

进入 skill 目录后，优先执行只读检查：

```powershell
python -B scripts/check_catalog.py --strict
python -B scripts/check_portability.py .
python -B scripts/sync_active_copies.py --json
python -B scripts/check_supercc_functional.py
```

说明：

- `check_supercc_functional.py` 默认应保持只读审查。
- 只有明确需要真实唤醒、发送任务或改变运行状态时，才使用 `--live-mutating`。
- Windows、PowerShell、CMD、WSL、Linux、macOS 都应避免写死主机绝对路径，优先依靠脚本自身位置、环境变量和 `PATH`。

## 5. 初级使用

### 普通任务

普通任务按以下顺序处理：

1. 读用户目标和边界。
2. 读取 `SKILL.md`。
3. 根据需要打开 `references/README.md` 中最小相关参考。
4. 制定简短计划。
5. 执行。
6. 验证。
7. 汇报结果。

### 只读审查

只读审查只能读取文件、运行不会改变状态的检查命令、总结风险。不要安装、删除、移动、杀进程、写配置、启动持久服务。

推荐命令：

```powershell
python -B scripts/check_catalog.py --strict
python -B scripts/check_portability.py .
python -B scripts/check_response_draft_fixtures.py
python -B scripts/check_context_compression_survival.py
```

### 写代码或修脚本

写代码时优先遵守三条规则：

- 先找已有脚本和参考，不重写已有机制。
- 跨平台逻辑使用脚本位置、环境变量、可执行文件发现，不使用固定主机路径。
- 修改后必须跑最小验证，再跑打包前检查。

### 记录史馆

适合记录：

- 用户明确要求记入史馆的上下文。
- 重要修复原因、复现方式、验证结果。
- 对未来任务有复用价值的决策。

不适合记录：

- 原始密钥、完整私有日志、会话全文。
- 临时目录、一次性进程号、无复用价值的噪声。
- 未经确认的推测。

## 6. 进阶使用

### 能力路由

当任务涉及未知工具或未知 CLI Agent 时，先把未知变成已知：

1. 发现当前 shell、操作系统、终端、可执行文件。
2. 探测 CLI 的名称、版本、帮助输出和可用参数。
3. 记录到临时能力判断中。
4. 再决定由 Codex、Claude、Hermes 或其他 CLI 执行。

常见思路：

```powershell
python -B scripts/cli_probe.py --json
python -B scripts/build_office_command.py --office shangshu --print
```

如果用户指定 CLI，应尊重用户指定。用户没有指定时，默认选择当前正在运行的 CLI 家族；识别不到时，再按可用性和任务适配度选择。

### superCC 启动

正常 superCC 的最低要求：

- `squad` 可用。
- `zellij` 可用。
- 每个官署角色唯一，不能重复冒名。
- 中书、门下、尚书等角色可以通过 squad 收发任务。
- 太子不能替代所有官署执行，除非明确标记为降级。

检查示例：

```powershell
python -B scripts/ensure_supercc_court.py --check-only
python -B scripts/check_supercc_ministry_dispatch.py
```

如果环境缺少 `zellij` 或 `squad`，应报告为降级或不可进入正常 superCC，而不是伪造成功。

### 泛 CLI 选择

Decretum Matrix（诏令矩阵） 的三省六部协作能力不应只绑定 Codex、Claude、Hermes。
它应支持泛 CLI Agent：

- 当前 CLI 可识别时，默认使用当前 CLI。
- 用户指定 CLI 时，按指定工具启动。
- 未知 CLI 先探测，再形成命令模板。
- 无法确定安全启动方式时，进入只读或半自动降级。

典型场景：

```text
用 Claude 启动尚书省。
用当前 CLI 启动门下省。
如果可用，用 Hermes 启动礼部；否则使用当前 CLI。
```

### 静默监督

静默监督用于发现异常静默、异常关闭、429、长时间无响应等问题，并在后台尝试恢复。

基本要求：

- 默认后台静默运行。
- 不弹出干扰窗口。
- 有停止方式。
- 有日志或状态文件。
- 不要无限重启。

示例：

```powershell
python -B scripts/supercc_watchdog.py --daemon --quiet --status-json
python -B scripts/supercc_watchdog.py --stop-daemon
```

### 打包

打包前应检查：

- 包内没有本机私有史馆正文。
- 包内没有原始日志、密钥、运行账本、导入队列。
- 文档和脚本不含过时命名。
- 活跃副本哈希一致。

打包命令：

```powershell
python -B scripts/package_skill.py --out "%USERPROFILE%\decretum-matrix-skill.zip"
```

## 7. 高阶使用

### 空白环境启动

在一个没有记忆、没有历史记录、没有额外配置的 CLI Agent 中，应按以下顺序恢复能力：

1. 读取 `SKILL.md`。
2. 读取 `references/README.md`。
3. 运行只读环境探测。
4. 判断当前平台和 shell。
5. 判断当前 CLI Agent。
6. 选择最小可行模式。
7. 再决定是否进入 super、superCC 或只读降级。

这样可以避免依赖旧上下文、旧路径或旧会话。

### 跨平台原则

脚本应兼容：

- Windows PowerShell。
- Windows CMD。
- WSL。
- Linux shell。
- macOS shell。

实现原则：

- 使用 `Path.home()`、`os.environ`、`shutil.which()`、脚本相对路径。
- 不把 `C:\Users\...`、`/mnt/c/...`、`/Users/...` 写死进脚本。
- 需要 shell 命令时，优先用参数数组或 Python 标准库，减少转义错误。
- 路径进入 bash、PowerShell、CMD 前必须经过对应环境的合法转换。

### 门禁和降级

高风险动作包括：

- 删除、覆盖、批量移动文件。
- 杀进程或关闭窗口。
- 改用户全局配置。
- 启动持久后台进程。
- 发送真实 squad 任务或唤醒官署。

如果用户只授权检查，应保持只读。如果用户授权执行，也要保留可验证证据和失败降级说明。

### 史馆与包边界

便携包应包含：

- skill 入口。
- 公开参考文档。
- 脚本。
- 示例夹具。
- 安装说明。
- 本手册。

便携包不应包含：

- 本机史馆正文。
- 原始会话日志。
- 密钥、令牌、Cookie。
- 本机运行账本。
- 未清洗的导入队列。
- 私有能力目录正文。

### 代码审查闭环

高阶任务结束前建议执行：

```powershell
python -m py_compile scripts/*.py
python -B scripts/check_catalog.py --strict
python -B scripts/check_portability.py .
python -B scripts/sync_active_copies.py --json
python -B scripts/package_skill.py --out "%USERPROFILE%\decretum-matrix-skill.zip"
```

如果发现问题，应先列出修复计划，再按计划修复，最后重新验证。

## 8. 常用命令速查

### 读取入口

```powershell
Get-Content SKILL.md
Get-Content references/README.md
```

### 能力与目录检查

```powershell
python -B scripts/check_catalog.py --strict
python -B scripts/sync_active_copies.py --json
python -B scripts/refresh_capability_registry.py --help
```

### superCC 检查

```powershell
python -B scripts/ensure_supercc_court.py --check-only
python -B scripts/check_supercc_functional.py
python -B scripts/check_supercc_ministry_dispatch.py
```

### 便携性检查

```powershell
python -B scripts/check_portability.py .
```

### 打包

```powershell
python -B scripts/package_skill.py --out "%USERPROFILE%\decretum-matrix-skill.zip"
```

### 静默监督

```powershell
python -B scripts/supercc_watchdog.py --daemon --quiet --status-json
python -B scripts/supercc_watchdog.py --stop-daemon
```

## 9. 常见问题

### 为什么 Claude 启动时没有进入 Claude 对应官署？

通常是 CLI 家族识别、命令模板或启动参数没有被正确探测。应先运行 CLI 探测脚本，确认当前进程到底是 Codex、Claude、Hermes 还是其他 CLI，再生成对应官署命令。

### 为什么出现 Windows 路径在 bash 中失效？

常见原因是把 `C:\...` 直接拼进 bash，导致反斜杠被吃掉。正确做法是不要依赖固定绝对路径，而是让脚本通过自身位置、环境变量和可执行文件发现来定位资源。

### 为什么 superCC 被判定不正常？

正常 superCC 需要 `zellij` 和 `squad`。只有 Hermes 可用、只有普通终端可用、只有单 Agent 可用，都不能算完整 superCC。

### 能不能在没有任何历史记忆的环境运行？

可以，但必须从 `SKILL.md` 和 `references/README.md` 开始，通过只读探测重建当前环境判断，不能依赖旧对话里的路径、进程或配置。

### 打包会不会带上史馆正文？

正常打包不应带上本机史馆正文。打包脚本会排除多类本地目录，并执行便携性和敏感内容检查。打包后仍应抽查 zip 清单。

## 10. 推荐工作流

### 初始工作流

1. 读 `SKILL.md`。
2. 读 `references/README.md`。
3. 判断任务是否需要调用 `$decretum-matrix` 及启用其三省六部协作模式。
4. 做最小计划。
5. 执行并验证。
6. 汇报结果。

### 进阶工作流

1. 明确用户授权边界。
2. 识别平台、shell、CLI Agent。
3. 选择普通、super 并行或 superCC。
4. 分派中书、门下、尚书或六部职责。
5. 跑只读门禁。
6. 修改、验证、复核、打包。

### 高阶工作流

1. 空白环境重建上下文。
2. 泛 CLI 探测和命令模板生成。
3. superCC 门禁确认。
4. 静默监督后台化。
5. 跨平台路径和 shell 转义审查。
6. 史馆记录清洗。
7. 便携包边界审查。
8. 最终 code review 和重新打包。

## 11. 维护原则

- 用户边界优先于默认流程。
- 只读就是只读，不能偷偷改状态。
- superCC 失败要明确降级，不要伪装成功。
- 所有 CLI Agent 都应先探测再使用。
- 脚本应依靠相对路径和标准库，不依赖本机绝对路径。
- 包内只放可复用材料，不放本机私有记录。
- 每次重要更改后都要验证、复核、再打包。
