# Validation And Packaging / 校验与包装

使用当前 host 的 Python 3，所有入口带 `-B`；active skill root 出现 `__pycache__`/`.pyc` 是 hard failure，不直接删除。安装版只投影 native/superCC 运行、史馆/GBrain、官署语义、安装启动与五根同步必需脚本；发布/深度校验脚本留在源码树。安装根最小验证：

```sh
python -B scripts/quick_validate.py .
python -B scripts/sync_active_copies.py --json
```

源码树发布门再运行 package/release/portability gates。包装仅限发布、安装或 handoff。`package-ready` 须过全部 gates，排除 secrets、private/pending 正文、raw/runtime 记录、凭证和无关项目。安装仅覆盖 manifest 公开文件，显式 prune 旧投影残留，先备份、失败回滚并回执路径；外部发布仍需授权与 fastpath 门。
