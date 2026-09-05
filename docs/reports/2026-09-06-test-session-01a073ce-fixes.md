# 01a073ce 测试任务回归修复

诊断对象为“测试并执行真实结诏”任务 `01a073ce-22e2-7983-90d6-1acdb50a66e2`，
修复基线 `d37b156`，继续在 `release/beta1.1.0` 本地提交。
该任务已经结束；本次没有重启它，也不修改其真实史馆记录。

| 问题 | 修复及边界 |
| --- | --- |
| SKILL 要求的 court-normal-startup.md 没有进入安装清单，三份活动副本全部缺失；之前的清单一致性检查误判完整 | 补 shared/portable/CLI support 声明，新增直接清单、展开清单、实际渲染安装副本的必读文档检查；删掉 guide 的负例必须失败 |
| 标准 create 接受绝对 write_set，直到 admission 才失败，导致无谓 revise-charter | 在编号分配和任何 runtime 写入前拒绝绝对/越界写集；公开 intake 模板说明相对路径基准与示例 |
| 缺失指引后转为直接运行 court_cli.py、猜参数、查源码 | 公开启动说明给出 CLI 解析方式、完整状态顺序和 native-request/capture/lifecycle 路径；Windows PATH 不可用时解析 npm prefix 中的公开命令入口 |
| 已创建的标准任务尚无真实 plan/reviews，却通过独立 archive-checkpoint 写入 case-bound DONE_WITH_CONCERNS | 对 live 标准任务的直接终态 checkpoint 拒绝并指向 archive-runtime-task；PASSED 类 producer 必须通过既有 runtime preflight，状态与 assessment/gaps 一致；检查在 Shiguan 锁及写入之前 |
| 正文有缺口但结构化 residual_gaps 为空 | 标准 producer 比对 assessment 的派生 gaps/digest；保留无 runtime 绑定的历史独立轻量记录，不回写或删除旧证据 |
| 用户目录旧规则让已点名的技能先全读 213,743 字符能力目录 | 本机该单行规则已备份后改为精确技能路径优先，未选择能力时才按名称做有限查询；索引路径以 CODEX_HOME 为基准 |

路径使用约定：写集相对当前 worktree；`--worktree .` 模板输入相对调用 cwd；请求文件
中的相对 worktree 以该文件目录为基准；文档链接相对技能根目录。精确宿主证据可在调用
边界解析为绝对路径，但不在产品模板中硬编码本机用户名和盘符。

归档预检只有请求派生 residual gaps 时才扩展返回数据，默认返回形状不变，避免改变旧
archive-runtime receipt cache 的键。继续使用原 runtime、评估、编号和史馆实现，没有第二套账本。

原测试使用过旧记忆，主体经内部 Python 入口调用；三个实际 ok 回奏与真实归档文件只能
证明对应动作发生，不能作为“无记忆新会话 + 公开 CLI/MCP + 完整官署链”的通过证据。
UTC 编号日期和谱系前缀沿用原 1.0.9 契约，本轮不更改历史编号。

本机证据根为 `D:/project/.staging/dm110-test-session-01a073ce`；RED/GREEN、部署回执和
公开 CLI/MCP 核验另行记录。总体架构、1.0.9 单核召回和既有 1.1.0 功能保持原边界。
