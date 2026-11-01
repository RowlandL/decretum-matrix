# 记忆、语义决策与网关：一手来源及选型依据

核验日期：2026-11-01。用途：支撑[增补计划](../plans/2026-11-01-memory-decision-gateway-roadmap.md)。本文仅为文档/源码研究，未部署或复现上游模型、延迟、吞吐、训练与产品效果。

## 1. 来源身份与固定快照

| 来源 | 固定提交 | 已查许可证文件 |
| --- | --- | --- |
| Tencent-Hunyuan/Hy-Memory | b2c91d9751d34d384f6016a346f47ec095ac4d37 | [Apache-2.0](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/LICENSE) |
| TencentCloud/TencentDB-Agent-Memory | ecc01a545da0b2ac6cae2f0f0af0d39d41469793 | [MIT](https://github.com/TencentCloud/TencentDB-Agent-Memory/blob/ecc01a545da0b2ac6cae2f0f0af0d39d41469793/LICENSE) |
| deepseek-ai/dsh-superagent-prototype | 6337fc823ce20251c8de8085948165c81aaa701e | [MIT](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/LICENSE) |
| deepseek-ai/deepseek-harness | ce7073d51254c26cd63b22a60835b8f948deb447 | [MIT](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/LICENSE) |
| vllm-project/semantic-router | 62c4f39e35aa2dfe929eb18223a7509ebeff6563 | [Apache-2.0](https://github.com/vllm-project/semantic-router/blob/62c4f39e35aa2dfe929eb18223a7509ebeff6563/LICENSE) |
| tensorzero/tensorzero | 62eb8f63e8ec62018d70420dbf1a8c5d1c026315 | [Apache-2.0](https://github.com/tensorzero/tensorzero/blob/62eb8f63e8ec62018d70420dbf1a8c5d1c026315/LICENSE) |

上表只记录文件事实，不将某一仓库许可证外推至模型权重、所有依赖、托管产品或本项目整个发行物。腾讯云托管服务、TencentDB 开源仓库和 Hy-Memory 是不同来源；本计划的记忆算法核验主要来自 Hy-Memory。

## 2. 腾讯记忆：事实与移植边界

- Hy-Memory 提供 chat、working、coding 场景；working 区分事实和经验，coding 增加真实 diff 的演化链。chat 文档层级中的 L4/L5 有保留位，不能据层号宣称全部实现。[固定架构说明](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/README.zh.md#L153-L207)
- strength 重排结合访问频次、闲置时间和相关度；默认时间常数为180天、开关默认关闭，仅作用于指定通道。它是排序衰减，不是满180天删除。[实现](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/hy_memory/pipelines/_retrieval/strength.py#L31-L85)、[默认配置](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/docs/env_reference.md#L154-L160)
- intention 检索处理 valid_until，将过期主动意图转为历史事实；该路径也含异步硬删复本。普通 dedup 则有 SHADOW 逻辑删除，不能将两者描述成统一软删除。[意图实现](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/hy_memory/pipelines/_retrieval/intention.py#L1-L21)、[去重实现](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/hy_memory/pipelines/_retrieval/dedup.py#L4-L24)
- 经验失效提示词要求明确否定、撤销或环境废弃证据，不能仅因陈旧而删除；这属于模型指令，不是确定性正确性证明。[reconciler](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/hy_memory/coding/reconciler.py#L48-L69)
- 检索支持向量与混合路径，具体后端可能降级；workspace/branch 过滤有缺省边界，不能直接当作本项目隔离门禁。[检索契约](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/docs/hy_memory_search_skill.md#L10-L111)、[场景作用域](https://github.com/Tencent-Hunyuan/Hy-Memory/blob/b2c91d9751d34d384f6016a346f47ec095ac4d37/docs/scene_coding_usage.md#L164-L200)

本项目取舍（设计建议）：采用用途分层、适用时间和演化关系；保留史馆权威原件。将降权、退出活跃通道、可恢复撤回、物理清理分开。来源与作用域先过滤，读请求不复制上游异步硬删行为。

## 3. DeepSeek：编排与上下文的职责分离

`dsh-superagent-prototype` 确在官方组织下，README 同时说明其为研究原型、非正式产品、部分公开设计未实现；不将它称为完整生产成品。[项目说明](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/README.md#L1-L5)

- Trigger、Eval、Ticket/Mandate、Assignment 有各自领域职责；上下文订阅不扩大授权。[领域模型](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/001-domain.md#L19-L40)
- 确定性 gate 与模型 assessment 分离；observe 默认只记录将接受的任务，auto 才实际接受。[policy 源码](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/src/policy.ts#L23-L85)
- 恢复要重验当前 policy；Engine 统一状态写入，事务提交后再执行副作用。[恢复授权](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/002-authorization.md#L93-L105)、[实现边界](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/007-architecture.md#L202-L218)
- Harness 使用插件、类型化事件与追加式 session log；其日志/上下文机制为编排底座的职责。[Harness 架构](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/docs/architecture.md#L5-L21)、[事件与日志](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/docs/architecture.md#L105-L118)

本项目取舍（设计建议）：复用当前 runtime 的唯一写入点、幂等与直接上级派遣。小模型、宿主模型和消息订阅只提供判断信息，不取得新的执行权限。

## 4. 成熟网关模式与候选比较

| 来源 | 已核事实 | 本项目采用方式 |
| --- | --- | --- |
| TensorZero | Rust gateway，提供统一供应商接口、schema、观测与可配置路由 | 自管模型代理场景优先做复用试点；托管宿主不强制插代理 |
| vLLM Semantic Router | signals / decisions / selectors 分离，harness仍持有任务循环与工具职责 | 采用职责分层；不承诺整套当前runtime或现成Laya加载 |
| LiteLLM | 超时、重试、冷却、provider/model备用路由 | 作为可靠性对照；不叠加第三个物理网关或新增默认Python服务 |

TensorZero 的[官方概览](https://github.com/tensorzero/tensorzero/blob/62eb8f63e8ec62018d70420dbf1a8c5d1c026315/docs/gateway/index.mdx)和[tool-use 契约](https://github.com/tensorzero/tensorzero/blob/62eb8f63e8ec62018d70420dbf1a8c5d1c026315/docs/gateway/guides/tool-use.mdx#L77-L83)说明网关返回 tool call，应用负责执行工具。provider routing、variant retries、variant fallbacks 有独立顺序和退避。[回退文档](https://github.com/tensorzero/tensorzero/blob/62eb8f63e8ec62018d70420dbf1a8c5d1c026315/docs/gateway/guides/retries-fallbacks.mdx#L114-L136)

TensorZero 认证/观测等功能有相应数据库依赖，不能将“Rust实现”直接推导为零依赖或更低本机成本。[部署说明](https://github.com/tensorzero/tensorzero/blob/62eb8f63e8ec62018d70420dbf1a8c5d1c026315/docs/deployment/tensorzero-gateway.mdx#L149-L155)、[认证配置](https://github.com/tensorzero/tensorzero/blob/62eb8f63e8ec62018d70420dbf1a8c5d1c026315/docs/gateway/configuration-reference.mdx#L37-L47)

VSR 的[harness边界](https://github.com/vllm-project/semantic-router/blob/62c4f39e35aa2dfe929eb18223a7509ebeff6563/website/docs/installation/agent-harness.md#L71-L93)明确路由与智能体任务不是同一个控制面；其[模型runtime设计](https://github.com/vllm-project/semantic-router/blob/62c4f39e35aa2dfe929eb18223a7509ebeff6563/src/model-runtime/docs/design.md#L10-L14)仍有未完成阶段，当前迁移方向含独立Python模型runtime。[架构细节](https://github.com/vllm-project/semantic-router/blob/62c4f39e35aa2dfe929eb18223a7509ebeff6563/src/model-runtime/docs/design.md#L60-L89) 不能用 Decision/System One 接口相似性证明某个 Laya 权重已经兼容。

LiteLLM 官方提供[可靠性路由](https://docs.litellm.ai/docs/routing)与[备用模型切换](https://docs.litellm.ai/docs/proxy/reliability)。这些供应商故障切换不等于宿主已能接续某个子智能体任务；本项目仍需自己的决策结果契约和宿主适配。

本项目结论（工程取舍）：采用统一逻辑入口、规则快路、可替换语义决策器和现有执行器。大量明确消息只需转发/规则；Laya不是每条消息的必经推理，更不是新权限中心。物理网关是否值得引入由兼容与净成本试点决定。

## 5. Laya 现状与决策可靠性

本项目 beta1.2.1 的[检索实现](../../training/laya-shiguan/service/shiguan_recall.py)使用 encoder 向量并做相似记录排序；[服务说明](../../training/laya-shiguan/service/README.md)记录决策头历史试验未超过基线，且相似度绝对值不可当校准阈值。该文档中的旧接口/运行状态必须结合本次源码核对，不能证明活动安装或所有宿主已可用。

Laya 官方模型卡提供类型化判断能力，同时明确当前多语权重未校准、零样本工作流存在质量限制，并列出长输入、候选数量与score/noul的限制。[官方模型卡](https://huggingface.co/convaiinnovations/laya-multilingual#limits) 本项目不照搬上游延迟或准确率；各决策位置均需基线、独立校准、拒答与宿主回退。

本项目取舍（设计建议）：Laya用于可验证的局部分类、候选排序与建议；复杂生成由宿主模型承担。若成熟兼容模型或规则更好，则替换对应provider，不把语言迁移或某模型名字当作成功标准。

## 6. 追加式上下文与缓存

用户要求是**新记忆在当前上下文末尾追加**。官方缓存文档说明缓存依赖一致前缀，工具、system、messages的前部改动会影响其后的复用。[一致前缀与缓存实践](https://platform.claude.com/docs/en/build-with-claude/prompt-caching#best-practices-for-effective-caching)

本项目取舍（设计建议）：保持历史前缀，记忆增量使用新消息或合法工具结果；不逐轮重写system、tools和旧记忆。缓存有效期、模型/端点切换、配置及宿主压缩仍会影响命中。以真实usage与连续请求对照验收，不承诺缓存永不失效；无新信息不重复追加，撤销以新版本说明，压缩建立新epoch。

## 7. 研究结论的效力

上述事实只证明指定上游快照/文档存在相关设计或实现，不能替代诏令矩阵自己的源码、安装、运行和宿主接受证据。所有移植、provider接入、缓存收益与Rust/Node改造均列PLANNED_UNVERIFIED。具体分批工作与验收见关联增补计划及各版本独立计划。

## 8. 官署职责史实与名称解耦依据

用户最新澄清是“具体职责参考历史史实，并对现代智能体进行适应化改造”；此前对中书、门下、尚书的口述例子不作为完整史实或不可修改的职责表。详见[职责增补计划](../plans/2026-11-01-office-duties-and-name-decoupling-plan.md)。

### 历史来源与适用范围

- 赵振华、王迪《读贞观十八年〈授滕王李元婴金州刺史诏〉》，《故宫学刊》2016：刊页34–35以文书实物及相关史料说明中书起草、门下审核封驳、尚书接收后分付六部的程序。这里只用来确定唐制政令分工，不外推每件事务都走同一程序。[PDF第6–7页](https://www.dpm.org.cn/Uploads/File/2020/04/10/u5e90203ee185a.pdf#page=6)
- 故宫博物院[中书省词条](https://www.dpm.org.cn/lemmas/244357.html)和[六部介绍](https://www.dpm.org.cn/court/system/236422.html)可支持机构职责概括及后世隶属演变；[六部词条](https://www.dpm.org.cn/lemmas/240651.html)说明明初改制，不能拿明清结构当唐制直属链。
- [中央纪委国家监委：三省六部制的配合与制约](https://www.ccdi.gov.cn/toutiao/201910/t20191031_203359.html)列举六部基本职掌。主线直取该页遇重定向循环，检索可得官方正文；具体细分不单凭搜索片段外推。礼部贡举、兵部军政与统军、刑部和其他司法机构的关系存在时代与职权限定，分别参考下列学术研究，不在计划中混作恒定职权。
- 礼部贡举转隶：[《唐史论丛》相关论文，2025年第2辑，第51–70页](https://tslc.cbpt.cnki.net/portal/journal/portal/client/paper/12364e05848b21fb5a13e812489f063d)；军事行政与指挥区别：[《中外法学》2016年第5期相关研究](https://ccj.pku.edu.cn/Article/DownLoad?id=331219562&type=ArticleFile)；刑部司法职责：[山东大学所载《唐代刑部尚书的法学素养》](https://www.lhp.sdu.edu.cn/images/201505.pdf)。本轮不做历代官制穷尽考证。

### 现有项目材料：可复用处与缺口

| 现有材料 | 可复用与待计划工作 |
| --- | --- |
| [department-map](../../references/department-map.md) | 已有按能力、任务差遣的职责图；历史职责和现代软件职责需分栏，专业边界需澄清，已禁Superpowers引用需清理 |
| [官署身份绑定](../../references/sections/court-office-name-profile-skill-binding.md) | 当前有role_key、上级、assignment及host实例绑定，并将sidebar/title限定为展示；前缀命名约束仍需有计划地迁移，不能称任意名称已开箱支持 |
| [中书profile](../../agents/standing-officials/zhongshu.toml)及同目录门下、尚书profile | 已有duty/can_do/cannot_do/procedure/report_contract；可沿此补统一任务语义骨架及动态扩展，不新增身份内核 |
| [2026-07-16身份包/DLC计划](../plans/2026-07-16-decretum-matrix-office-identity-pack-dlc-and-scope-plan.md) | 状态仍PLAN_ONLY；第4节已有skin/augmentation/replacement分层，第5节有作用域和跨宿主resolver设计，优先续接，不能另建一套或冒称已实现 |

本项目现代适配（设计建议）：保持拟定、审议、行政统筹及专业部门分工；角色按能力/任务启用，采用结构化任务、并行执行、宿主真实派遣、证据与故障恢复。CEO/COO/人名只改变显示，不能改变职责或授权；不固定企业职位与古官名的等号。适用性通过任务质量与成本衡量，不宣称历史制度普遍优于所有其他管理方式。
