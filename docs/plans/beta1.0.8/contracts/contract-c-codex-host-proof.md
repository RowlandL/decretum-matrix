# 契约 C — Codex 指定模型 host proof（FR-C，draft-0.1 · 2026-08-28.beta1.0.8）

> 权威：devspec §3.4 FR-C；实现：agent_runtime_probe.py、court_model_router.py、check_court_model_router.py。

## 1. host probe 字段（agent_runtime_probe.py 扩展输出）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| codex_version | str | codex --version 输出（版本绑定） |
| codex_executable | str | 解析到的可执行路径 |
| supported_model_effort_pairs | list[{model,effort}] | 该版本支持的模型/effort 对 |
| config_exposes_model | bool | 配置是否暴露模型字段 |
| turn_context_model | str?null | fresh-session 回读的实际模型 |
| turn_context_effort | str?null | fresh-session 回读的 effort |

## 2. 路由契（court_model_router.py）

- `route_office_model_with_host_proof(route, host_probe)`：
  - 校验 host_probe 满足 route 的 recommended_model/effort（或显式继承）。
  - 满足 → `model_override_applied=YES` + `host_proof_sha256`。
  - 不满足 / 无证明 / 回读不一致 → 回退 `inherit_parent_model_and_effort`，`model_route_status=FAILED` / `runtime_degraded`（不伪报）。

## 3. 验收指针

- check_court_model_router.py 增加 host-proof 正/反例（阶段 4 P4-1..4 全量落地；本契约先冻结字段枚举与状态方向）。
- 版本绑定：每个 (probe, route) 组合必须携带 codex_version 绑定证据。
