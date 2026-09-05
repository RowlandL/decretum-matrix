# beta1.0.8 / beta1.0.9 本机隔离安装验证

## 结论

两版未修改的生产安装入口均在创建目标目录前拒绝安装：
`projection_manifest_invalid / repository_only_overlap`。
共同冲突项为 `scripts/install_codex_plugin_projection.py`。
本次完成了实际安装入口验证并确认阻塞，未获得成功安装副本。

| 来源 | plan | apply | 目标目录／文件 | 安装后冒烟 |
| --- | --- | --- | --- | --- |
| beta1.0.8，`37df40da5232f230cde578599c8030982188bbd7` | REJECTED | REJECTED | 未创建，前后清单均空 | NOT_RUN_NO_INSTALLED_COPY |
| beta1.0.9，`0003b3800cd245abf870a82ff464a802cc0faeaf` | REJECTED | REJECTED | 未创建，前后清单均空 | NOT_RUN_NO_INSTALLED_COPY |

## 方法

从干净固定提交的独立源码副本加载 `scripts/install_current_agent_copy.py`，直接调用
`install_current_agent_copy`。输入为各版真实的 install-projection manifest、
独立 `home_root` 和该 home 内的 `.codex/skills/decretum-matrix`；先 `write=False`，
再对同一明确目标调用 `write=True`。未提供宿主 configuration adapter，也未修改
manifest 或模拟安装函数的结果。

两个版本都通过 `_load_projection_contract` 检出 portable 与 repository_only
集合交集，在目标选择／写入阶段之前返回拒绝。回执中 targets 为空，
pending_body_accessed=false，real_host_configuration_accessed=false。
未下载依赖、启动服务或覆盖活动安装。两个源码副本保持干净。

这与安装器 fixture 是不同证据：fixture 验证合成输入下的行为，真实 manifest
验证证明当前版本交付清单是否可被实际安装入口接受。不能用前者的通过覆盖后者的拒绝。

## 修复后的必要验收

1. 统一 source-only、公开 CLI 与安装投影分类；保持真实 manifest，通过原入口安装。
2. 安装完成后回读版本、安装 receipt、实际文件和 selected_roots。
3. 从两个安装目标及外部 cwd 调用 CLI 帮助／版本、MCP 列表与只读工具。
4. 验证公开入口导入闭包、三省／六部预载、重复安装及冻结文件替换。
5. 在隔离目标中验证失败恢复与回滚，不以修改活动安装作为测试前提。

任务书将本安装阻塞与依赖闭包作为先行任务，后续不得把“验证已运行”写成“安装成功”。

证据：[结构化摘要](beta109-review-20260905/evidence-summary.json)、
[本机原始回执与复现入口](beta109-review-20260905/README.md)。
