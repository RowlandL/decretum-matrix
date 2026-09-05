# 验证证据索引

[evidence-summary.json](evidence-summary.json) 是本次提交文档保留的结构化证据摘要。
数据来自同一会话的实际命令结果，不由计划中的预期输出替代。

本机原始证据（未纳入安装投影）：

- 1.0.8 独立源码：`D:\project\.staging\dm108-review-20260905\decretum-matrix`，HEAD `37df40d`。
- 32 项完整输出：`D:\project\.staging\dm108-review-20260905\evidence\`。
- 串行驱动：`D:\project\.staging\dm108-review-20260905\review_suite.py`。
- 边界复现：`D:\project\.staging\dm108-review-20260905\boundary_probes.py`。
- 1.0.9 独立源码：`D:\project\.staging\dm-install-audit-20260905\decretum-matrix`，HEAD `0003b38`。
- 实际安装驱动：`D:\project\.staging\dm-install-audit-20260905\verify_install.py`。
- 实际安装原始回执：`D:\project\.staging\dm-install-audit-20260905\isolated-install-results.json`。

这些路径用于本机复现与交接，不是产品运行时路径。代码修复后的验证应创建新的
隔离目标或按已核实边界复用，保留本轮失败证据，不覆写成修复后成功。

已有审查覆盖边界：源码、合成 fixture、实际安装器入口与真实源码 manifest。
未完成：安装后 CLI/MCP 运行验证（安装被拒绝，无有效副本）、真实模型 worker、
活动配置修改和任何外部发布。
