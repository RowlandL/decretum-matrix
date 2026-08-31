# 契约 A — IKU 占位符治理（FR-A，draft-0.1 · 2026-08-28.beta1.0.8）

> 归属：阶段 1（本契约）→ 阶段 2（P2-2 domain API 接入）→ 阶段 3（A2 受控修复 CLI）。
> 权威：devspec §3.2 FR-A；manifest 草案：cli-command-surface-projection-draft.json。

## 1. 候选输出字段（只读探测器，dry_run=true）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| record_path | str | 相对仓库的 plan-archive 记录路径 |
| record_id | str | 记录编号（TP 谱系） |
| field | str | 命中字段：`诏令编号` / `古制谱系` / `正文` |
| fragment_sha256 | str | 占位片段 SHA-256（不复制正文） |
| placeholder_kind | str | `IKU` / `PENDING_GENERATED` / `PENDING_REFILL` |
| nearest_court_code | str?null | 最近有效 court_code（无则 null） |
| nearest_lineage | str?null | 最近有效谱系 display（无则 null） |
| receipt_hint | str?null | 最近 receipt 引用（无则 null） |
| suggested_action | str | `NOOP` / `REVIEW` / `REPAIR_CANDIDATE` |
| reason | str | 稳定 reason code |

## 2. 三态语义

- NOOP：IKU 出现在非编号字段或语义不明 → 不动。
- REVIEW：无最近有效 receipt / 来源冲突 / 语义不明 / 非唯一谱系 → 只读上奏。
- REPAIR_CANDIDATE：编号字段 + 可安全回填（唯一近源、无冲突）→ 仅候选（不写）。
- 写权限：`--apply` 显式 + `--yes` + 原文指纹 + 回滚前像；两次 `--apply` 幂等。MCP 永不触发写入（A2 能力预留）。
- 隐私：不读/不复制 pending/private 正文；片段仅 SHA-256。

## 3. MCP 边界

- 工具 `shiguan.iku_candidates`：只读域名调用 public/domain API；输入 `scope`（默认 plan-archives）、`limit`；输出 candidates[]（dry_run=true, write_enabled=false）。
- 接受：dry-run 前后目录字节级不变；相同输入两次调用 JSON 字节级一致；三态覆盖（fixture）。

## 4. 验收指针

- fixture：references/fixtures/iku-candidates.json（3 态样本）。
- P2-2 public_iku_candidates() – 复用 repair_archive_placeholders 只读探针。
- P3 A2：--dry-run/--apply 受权路径。
