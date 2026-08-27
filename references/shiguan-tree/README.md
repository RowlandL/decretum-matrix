# 史馆生长树

Portable seed tree. Local leaves, branches, and the knowledge graph grow from this host's own Shiguan records.

## Obsidian 父 vault 第2架构

权威源目录是共享史馆根下的 `references/shiguan-tree`，由
`scripts/shiguan_paths.py` 解析。默认位于平台用户数据目录下的
`court-shiguan/decretum-matrix/references/shiguan-tree`，例如 Windows
`%LOCALAPPDATA%`、macOS `~/Library/Application Support`、Linux
`$XDG_DATA_HOME` 或 `~/.local/share`。

父 Obsidian vault 入口默认位于用户主目录下的
`Documents/Obsidian Vault/史馆入口.md`。

`Documents/Obsidian Vault/Court Shiguan` 是为 Obsidian 图谱、标签和 wikilink
浏览生成的 preserve-only 缓存镜像；同步只能添加或更新生成内容，不得删除旧导出文本、原文或用户笔记，除非未来用户对具体项目明确批准删除。

- `leaves/`: local record leaves
- `branches/`: content-lineage branches
- `manual/`: web-manager manual entries
- `meta/schema.md`: field and lineage notes
- `sources/`: generated in-vault source mirrors for Obsidian Source links
- `capability-index/`: generated capability routing index visible in Obsidian
- `Obsidian 回传/`: Obsidian-created notes queued for court review by autosync

Run `python -B scripts/rebuild_shiguan_index.py` after install or archive import.
