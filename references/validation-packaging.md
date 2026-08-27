# Validation And Packaging / 校验与包装

使用当前 host 的 Python 3，所有入口带 `-B`；active skill root 出现 `__pycache__`/`.pyc` 是 hard failure，不直接删除。安装版投影 native/superCC 运行、史馆/GBrain、官署语义、安装启动、五根同步，以及 manifest 声明的统一 CLI handler。校验/发布 handler 可供显式 CLI 调用，但不得进入 startup、preload、普通同步决策或 eager import；明确退休的深度门禁仍只留在源码树与发布包。

安装时（仅安装时）从发布包/安装源运行结构校验：

```sh
python -B scripts/quick_validate.py .
```

校验通过后校验脚本自删，安装根不保留任何校验脚本。运行时同步沿用五根同步工具（`sync_active_copies.py --json`，仅显式授权目标）。

源码树发布门再运行 package/release/portability gates。包装仅限发布、安装或 handoff。`package-ready` 须过全部 gates，排除 secrets、private/pending 正文、raw/runtime 记录、凭证和无关项目。安装仅覆盖 manifest 公开文件，显式 prune 旧投影残留，先备份（逐文件 SHA256 持久备份）、失败回滚并回执路径；外部发布仍需授权与 fastpath 门。
