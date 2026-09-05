# Validation And Packaging / 校验与包装

使用当前 host 的 Python 3，所有入口带 `-B`；active skill root 不保留 `__pycache__`/`.pyc`。安装版保留 native/superCC 运行、史馆/GBrain、官署语义和安装更新所需的公开接口。安装/发布检查仅存在于源码与安装源，不保留在活动副本，也不进入启动、预载或普通同步的判定链。

安装器仅在安装时对安装源运行结构校验。成功后活动投影不保留安装/发布检查脚本，也不保留它们的命令注册或清单条目。旧副本中的对应受管文件须先保存实际前像、核验备份，再清理；失败恢复文件与清单。运行时同步仅作用于显式授权目标，并使用相同活动投影规则。

源码树发布门再运行 package/release/portability gates。包装仅限发布、安装或 handoff。`package-ready` 须过全部 gates，排除 secrets、private/pending 正文、raw/runtime 记录、凭证和无关项目。安装仅覆盖 manifest 公开文件，显式 prune 旧投影残留，先备份（逐文件 SHA256 持久备份）、失败回滚并回执路径；外部发布仍需授权与 fastpath 门。
