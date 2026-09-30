# Validation And Packaging / 校验与包装

使用当前 host 的 Python 3，所有入口带 `-B`；active skill root 不保留 `__pycache__`/`.pyc`。安装版保留 native/superCC 运行、史馆/GBrain、官署语义和安装更新所需的公开接口。安装/发布检查仅存在于源码与安装源，不保留在活动副本，也不进入启动、预载或普通同步的判定链。

安装器仅在安装时对安装源运行结构校验。成功后活动投影不保留安装/发布检查脚本，也不保留它们的命令注册或清单条目。旧副本中的对应受管文件须先保存实际前像、核验备份，再清理；失败恢复文件与清单。运行时同步仅作用于显式授权目标，并使用相同活动投影规则。

源码树发布门再运行 package/release/portability gates。包装仅限发布、安装或 handoff。`package-ready` 须过全部 gates，排除 secrets、private/pending 正文、raw/runtime 记录、凭证和无关项目。安装仅覆盖 manifest 公开文件，显式 prune 旧投影残留，先备份（逐文件 SHA256 持久备份）、失败回滚并回执路径；外部发布仍需授权与 fastpath 门。

## 安装末段与候选验收边界

投影应用后，生成/保存 installation binding 或安装回执发生进程内异常时，安装器必须尝试恢复投影与旧绑定；只有全部恢复成功才返回 `ROLLED_BACK`，否则返回 `RECOVERY_REQUIRED` 并保留备份位置。回执复用既有原子 JSON 写入器。本规则不声称覆盖断电、强制终止或并发安装。

本地候选与发布形态均须保留各自契约中的 installer-only 文件；它们不进入活动投影。候选烟测必须从包内安装入口启动，不能调用源码树安装器后把结果称为包可独立安装。缺失安装成员必须使烟测失败。候选通过不代表远端发布或用户生产环境安装完成。

精简 Python 的快速 frontmatter 检查只支持标量字段和 metadata 字符串映射；复杂 YAML 使用 PyYAML。未知嵌套、重复键和无效字段必须拒绝，不得通过扁平化“修正”。
