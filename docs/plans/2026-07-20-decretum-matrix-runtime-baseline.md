# Decretum Matrix 运行基线记录

对应计划任务 1。此文件记录整改前的可复现实测，不把当前隔离改动视为已经验收。

机器可读证据：`.repo-control/evidence/decretum-matrix/objective-remediation/runtime-baseline.json`

## 1. 测量边界

| 项 | 内容 |
| --- | --- |
| 当前分支 | `release/beta1.0.2` |
| 目标版本 | `beta1.0.2` |
| 当前基线 HEAD | `9774a1415b906b357985e462e74efaf842f45602` |
| 历史基线 | `beta0.5.9^{commit}=040f707e5acc7c12cfcf50afcfc111a7e49a2f00` |
| 历史提取目录 | `H:\TEMP_~1\decretum-beta059-2a5eab94d50f4a14a4caf12ec6da6146` |
| 测量方式 | `python -B` 子进程外包计时；读取主输出和源码调用链，不声称完成 syscall 级文件读取追踪 |
| 状态写入 | 使用临时 JSON、临时 `COURT_RUNTIME_ROOT` 或临时史馆根；不写产品源 |

## 2. 低复杂度场景组

当前 `court intake-validate` 使用结构化事实输入，不直接读取自然语言文本。因此本次测量验证的是“相同结构化语义选择相同流程层级”，不是为 `OK` 写特例。

| 变体 | 结构类别 | 路由 | 耗时 ms | 结果 |
| --- | --- | --- | ---: | --- |
| `OK` canary | `CASUAL_CHAT` | `CASUAL_REPLY` | 572.03 | PASS |
| `好` | `CASUAL_CHAT` | `CASUAL_REPLY` | 564.91 | PASS |
| 长闲聊 | `CASUAL_CHAT` | `CASUAL_REPLY` | 525.57 | PASS |
| 简短直接回答 | `TRIVIAL_DIRECT` | `DIRECT_ANSWER` | 457.81 | PASS |
| 短正式任务 | `FORMAL_TASK` | `THREE_DEPARTMENTS` | 478.73 | PASS |
| 长正式任务 | `FORMAL_TASK` | `THREE_DEPARTMENTS` | 485.93 | PASS |
| 待澄清任务 | `TASK_CANDIDATE` | `SINGLE_QUESTION` | 501.59 | PASS |
| 主动结诏 | `EXPLICIT_CLOSEOUT` | `SESSION_CLOSEOUT` | 540.34 | PASS |

调用链：

```text
scripts/court_cli.py
-> scripts/court_cli_registry.py
-> isolated_runtime_process
-> scripts/court_runtime.py intake-validate
-> scripts/court_intake_gate.py
```

静态搜索：

```powershell
rg -n "OK|text ==|message_text|keyword|blacklist|whitelist|startswith\(|endswith\(|len\(" scripts/court_intake_gate.py scripts/court_open_fastpath.py scripts/court_cli_registry.py scripts/court_runtime.py
```

结论：

| 项 | 结果 |
| --- | --- |
| `OK` 精确文本路由 | 未发现 |
| 关键词黑白名单路由 | 未发现 |
| 长度驱动场景路由 | 未发现 |
| 当前主要问题 | 低复杂度结构化 gate 仍通过统一 adapter 和隔离子进程，约 0.46–0.57 秒 |

## 3. 正式开朝路径

### 3.1 focused ready-path 测量

`prepare_fast_open()` 的 focused harness 可进入 READY：

| 行为 | 耗时 ms | 状态 | 差遣数 | 三省包 | 六部包 | Git 调用 |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| serial | 515.30 | READY | 0 | 3 | 0 | 4 |
| parallel | 292.59 | READY | 9 | 3 | 0 | 4 |

Git 调用为：

```text
git branch --show-current
git rev-parse HEAD
git diff --cached --name-only
git status --short --untracked-files=no
```

### 3.2 真实 CLI 临时 runtime 测量

使用临时 `COURT_RUNTIME_ROOT` 创建 task 后，通过真实 CLI 进入 `court open --fast`：

| 阶段 | 耗时 ms | 结果 |
| --- | ---: | --- |
| create task | 543.44 | returncode 0 |
| open serial | 788.77 | `FAST_PATH_MISS:semantic_not_dispatchable`，差遣 0 |
| open parallel | 827.93 | `FAST_PATH_MISS:semantic_not_dispatchable`，差遣 0 |

结论：真实 CLI 在缺少可差遣语义状态时 fail-closed，且差遣为零。后续修复不得破坏此安全语义。

## 4. 史馆记录和查询

| 场景 | beta0.5.9 ms | 当前 ms | 差值 ms | 当前新增/变化 |
| --- | ---: | ---: | ---: | --- |
| `query_shiguan_index.py --help` | 458.79 | 362.08 | -96.71 | 当前查询实现关联 `shiguan_gbrain.py` |
| 查询不存在词 | 2853.16 | 2914.06 | +60.90 | 当前查询仍可用，但未提速 |
| `archive_checkpoint.py --no-refresh --format json` | 261.62 | 379.75 | +118.13 | 当前输出新增 `archive_sha256`、`receipt_sha256`、`closeout_identity` |

结论：

- 史馆基础查询、记录能力不得删除。
- GBrain 是史馆查询、召回与整理/沉淀候选层；可作为默认智能查询层，但不得取得当前任务执行权或写权，基础 scorer 必须保留为显式 fallback。
- 当前 receipt/hash 相关字段是 `beta0.5.9` 后增内容；是否保留、合并或简化必须经过脚本价值评估和历史数据读取验证，不能直接删除。

## 5. 项目目录外 CLI 路径

外部临时目录内存在 `request.json` 时：

| 命令形态 | 结果 | 含义 |
| --- | --- | --- |
| `--request-file request.json` | `request_file_invalid` | 相对路径未按调用者目录解析 |
| `--request-file <absolute-temp-path>` | `task_id_required` | 文件实际可读，失败原因不是文件不存在 |

源码证据：`scripts/court_cli_registry.py` 当前以 `cwd=ROOT` 启动 `court open` 子进程。

结论：这是任务 5 的明确 RED 对象。修复方向只能是让用户输入路径按调用者目录或明确上下文解析，不得新增第二个总入口。

## 6. 当前 focused checker 结果

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -B scripts/check_court_intake_gate.py` | PASS | 当前隔离候选的 focused 结果；不是最终保全验收 |
| `python -B scripts/check_unified_cli.py --inventory-only --json` | PASS | manifest 发现/注册 127 项；另有有效 registry 126 项证据 |
| `python -B scripts/check_court_open_fastpath.py --json` | PASS | focused harness 通过 |
| `python -B scripts/check_startup_fastpath_contract.py --json` | PASS | serial 差遣 0，parallel 差遣 9，fail-closed 差遣 0 |
| `python -B scripts/check_court_session_closeout.py` | PASS | 未跟踪候选实现；未进入接受方案 |

## 7. 任务 1 结论

| 编号 | 结论 | 下一步 |
| --- | --- | --- |
| F1 | 低复杂度路径未发现文本特例，但统一 adapter + 隔离子进程成本明显。 | 写场景成本 RED，优化路径但保留 gate 和诏令绑定。 |
| F2 | 项目目录外相对 `request-file` 解析错误。 | 写外部 cwd RED，再修 `court_cli_registry.py` 路径处理。 |
| F3 | 史馆归档新增证明字段且耗时增加。 | 进入脚本价值评估，不直接删除。 |
| F4 | 正式 CLI 开朝在语义不可差遣时 fail-closed，差遣为零。 | 优化 ready path 时保留 fail-closed。 |
| F5 | focused/project checker 有价值，但不应进入普通 Skill 运行链。 | 任务 2 将项目级 checker 与 Skill runtime 分离。 |
