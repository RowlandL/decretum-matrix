# Decretum Matrix beta1.0.7 阶段执行计划书

状态：CLOSED_SOURCE_BASELINE / HISTORICAL_PLAN
日期：2026-08-26
分支：release/beta1.0.7
适用范围：decretum-matrix 子仓库的新版本分支

## 一、定位

本计划承接 `docs/research/2026-08-25-next-version-cli-mcp-hooks-shiguan-memory-research.md` 的审查结论。beta1.0.7 的源码阶段已完成收尾，当前 `release/beta1.0.7` / HEAD `2571178` 作为 beta1.0.8 的开发基线。本文件保留历史阶段、写集、验证和停止门，不是新的发布批准，也不把未有四类证据绑定的 MCP、hooks 或史馆记忆闭环声明为已验证能力。

本轮路线固定为：

1. P0：先消除当前红项和误调用面。
2. P1：再做 typed CLI resolver 收窄和证据投影补齐。
3. P2：只在 P0/P1 绿色后试作本地 MCP 薄适配器。
4. P3：hooks 仅做 advisory marker，不进入权威链。
5. P4：史馆记忆闭环独立形成 scan -> adjudicate -> apply -> verify -> reconcile 证据。

## 二、不变量

- [CONTROL_PLANE] 所有修改只在 `release/beta1.0.7` 分支进行；不改 `workspace.yaml` 的 accepted version，不触碰外部发布、push、tag、PR。
- [CONTROL_PLANE] CLI、MCP、hooks 和脚本都是工具层，不替代三省六部层级、门下复核、史馆归档或 runtime event store。
- [PLANNED_UNVERIFIED] MCP server、Git hooks、内容级 memory writeback 当前均未被本计划提升为 VERIFIED_CAPABILITY。
- [CONTROL_PLANE] 每一阶段只在前一阶段最小验证通过后推进；失败时记录 blocker，不以后续外壳掩盖核心红项。

## 三、阶段计划

### P0：治理检查红项

目标：

- 修复 `check_governance_framework.py` 当前失败项。
- 统一 GBrain decree identity 参数契约。
- 恢复 official adapter 通过 generic dispatch path 的证据。

写集：

- `scripts/check_governance_framework.py`
- `scripts/shiguan_gbrain.py`
- 如确需，限量修改 `scripts/court_dispatch_hierarchy.py`

验证：

- `python -B scripts/check_governance_framework.py --only gbrain --json`
- `python -B scripts/check_governance_framework.py --only official-adapter --json`
- `python -B scripts/check_governance_framework.py --json`

停止门：

- 任一检查仍红，不进入 P1。

### P1：误调用面和证据投影边界

目标：

- 收窄 source-agent 显式输入白名单。
- 补齐 closeout 十四行模板的安装投影门。
- 为 CLI resolver 后续 v2 envelope 记录当前缺口，不一次性重写 121 个命令。

写集：

- `scripts/shiguan_paths.py`
- `references/manifests/install-projection.v1.json`
- 相关最小检查器或 fixture

验证：

- source-agent 白名单 RED/GREEN 检查。
- install projection 模板包含性检查。
- `python -B scripts/check_unified_cli.py --json`

停止门：

- 显式非法 writer 仍可进入 closeout identity，或模板仍未进入 install projection，不进入 P2。

### P2：MCP 薄适配器原型

目标：

- 只暴露 allowlisted read-only / dry-run 工具。
- schema 从同一 manifest 派生，不手写第二套命令表。
- 不开放 mutation，不建立第二 ledger。

首批候选工具：

- `court.status`
- `court.command_help`
- `shiguan.query`
- `shiguan.archive_dry_run`
- `memory.scan`

停止门：

- P0/P1 未绿时不写 MCP server。
- 不能证明 install projection、runtime probe、typed receipt 时，不宣称 MCP 产品能力。

### P3：advisory hooks

目标：

- 只做本地 refresh marker 或只读 gate。
- 不让 hook 形成 closeout、归档、记忆写入或发布证据。

停止门：

- 任何 hook 逻辑需要 authority、Menxia verdict、Shiguan archive 或外部发布时，停止并回到 CLI/runtime 权威路径。

### P4：史馆记忆闭环

目标：

- 建立 synthetic native-store fixture。
- 跑通 scan -> adjudicate -> apply -> verify -> reconcile。
- 用 paired transaction receipt 和 native reread 证明内容级写回。

停止门：

- 只有 metadata-only bridge 时，继续标记为 advisory，不宣称内容级 memory 已打通。

## 四、历史执行游标（已收尾）

当前游标：`beta1.0.7/source-closeout`

收尾结论：

```text
beta1.0.7 源码、阶段任务和发布工件收尾完成；后续工作转入 beta1.0.8 计划，不重开本文件历史阶段。外部发布状态仍以 tag、GitHub Release、npm 和安装回执分别核验。
```

P0、P1、P2、P3、P4 已在本轮完成最小实现与验证。P4 只证明 synthetic native-store fixture 的内容级闭环；不触碰真实 Codex/Hermes/Claude memory，不读取真实 private bodies，不自动提升产品能力。

### Beta1.0.7 Source Closeout (2026-08-29)

- `release/beta1.0.7` HEAD `257117867498be980deed9b5ed5ace835d637384` 已完成源码收尾，工作树除 beta1.0.8 规划文档外无意外改动。
- `VERSION=beta1.0.7`，`release-manifest.json` 的 artifact/release label/version_core 均绑定 beta1.0.7。
- 本收尾结论只证明源码基线完成；外部 tag、GitHub Release、npm dist-tag 和宿主加载状态仍必须由各自回执证明。

## 五、阶段执行记录

| 阶段 | 状态 | 证据 |
| --- | --- | --- |
| P0 | DONE | `python -B scripts/check_governance_framework.py --json` -> PASSED / `SEMANTIC_CLEANLINESS_GATE=PASS` |
| P1 | DONE | `python -B scripts/check_portability.py`、`check_install_projection_closure.py --json`、`check_unified_cli.py --json`、`quick_validate.py .` -> PASS |
| P2 | SOURCE_PASS_HOST_UNVERIFIED | `python -B scripts/check_court_mcp_server.py`（29 项）与 `python -B scripts/probe_court_mcp_modern_wire.py` -> PASS；官方最新协议目标 `2026-07-28` 为主路径（无 initialize/session、每请求 `_meta`、`server/discover`、`resultType`、缓存提示），`clientInfo` 可缺省但存在时校验 `Implementation.name/version`；unknown tool/invalid args 返回 `-32602`，malformed JSON/invalid request 分别为 `-32700/-32600`，`tools/list` 非空 cursor fail-closed；`2025-11-25` 仅为 legacy fallback；allowlist 精确为五个只读工具；独立 source receipt 不证明宿主加载 |
| P3 | DONE | `python -B scripts/check_court_hooks_advisory.py` -> PASS；新增 advisory report，不安装 `.git/hooks`，不设置 `core.hooksPath`，不形成归档、记忆写入、发布或验收权威 |
| P4 | DONE | `python -B scripts/check_memory_pipeline_fixture.py` -> PASS；synthetic native-store fixture 跑通 `scan -> adjudicate -> apply -> verify -> reconcile`，paired receipts 和 native reread 均验证；真实 memory mutation/body access 均为 false |
| P5 | PARTIAL_HOST_UNVERIFIED | 源码侧保留安装/运行契约与编码回归；宿主结论严格拆分为 `manager_registered=PASS`、`effective_config_projection=FAIL`、`process_loaded=NOT_OBSERVED`、`process_probe=PASS_OR_DRIFT`（独立 server 进程证据，source 与 installed 分开记 receipt）、`tool_visible=FAIL`。当前安装投影仍需 hash-bound 重签/复投影；CC Switch 辅助线已暂停为 `host_environment_drift / PARTIAL`，本阶段按 `host_degraded / effective_runtime_unverified` 回报，保留历史 2026-07-28 成功回执但不能以旧 result event 或静态配置文本宣称 active |

### Beta1.0.7 Scope Amendment (2026-08-28)

P3 is superseded by the current release boundary: Codex lifecycle hooks and
Git-hook advisory code are withdrawn from beta1.0.7 because of host
compatibility and configuration variance. The hook files, runtime scripts,
checker, and install projections are removed. The optional Codex plugin
activation metadata remains source-only and carries no hook behavior. The
shipped product surface is the skill plus read-only MCP; the historical P3
entry above remains an immutable record of the earlier implementation state.
