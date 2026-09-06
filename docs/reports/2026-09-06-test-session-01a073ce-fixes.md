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

## 扩展安装依赖审计

继续按实际读取关系核对，而非仅比较清单与自身。除启动指引外，确认另四份运行分卷
漏装：运行结果/能力招募契约、回复 few-shot、官署口吻、上下文压缩恢复。这四份分卷
补入 shared/portable；运行索引、Markdown 链接和普通 backtick 路径均加入闭包检查。

能力校验和安装/包装两个混合分卷保留为源码维护资料；其运行语义留在原 parent 中，
运行索引不再要求加载未安装的源码校验分卷。README 的 Wiki、架构原稿和发布清单是
源码资料，已明确范围，不把它们或 checker/fixture 自动复制进运行副本。

普通官署的 14 个 profile、14 个 dossier 及其查询入口均存在。运行命令的动态资源、
A+B 兼容入口和公开 CLI/MCP handler 经独立核对；派生官籍、史馆和会话数据由对应
运行接口生成，不将真实用户数据倒灌进包。源码 CRLF 与发布 ZIP 的 LF 差异不当作功能缺失。

另以真实公开 CLI 复现了编码问题：Windows 子进程使用 CP936 输出，父进程按 UTF-8
解码，中文损坏成 U+FFFD 仍返回成功。已在统一子进程入口固定 UTF-8 编码，新增 CP936
环境下实际非 ASCII help 输出回归，保留完整中文，不逐个脚本打补丁。

最终运行文档闭包每套覆盖 51 项、缺失为零，运行入口核对 49 项。旧 preload 检查器
另有 4 个假报警：仍依赖已经移除的 Overview 分界，以及读取 A+B 兼容壳代替实现真身。
检查器已按当前短入口、直链语义和 canonical 模块修正，22 项检查全部通过，未为消除
报警而删减生产门禁。文档、源码测试和安装态的证据继续分开，不据此宣称完整新会话通过。
