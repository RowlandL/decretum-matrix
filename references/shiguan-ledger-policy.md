# Shiguan Ledger Policy

史馆 keeps durable evidence, checkpoint records, rejected options, verification,
memory candidates, and 考课. It is 三省共监、门下主审.

- Official records are created by `archive_checkpoint.py` and indexed by
  `rebuild_shiguan_index.py` / `grow_shiguan_tree.py`.
- Draft imports and private notes remain pending until reviewed; importing a
  Markdown, TXT, or Obsidian note does not make it official.
- Memory candidates require `memory_decision`, `memory_content`, and
  `memory_reason`. 史馆 records candidates only; 门下省 owns final durable
  writeback approval.
- Host-local records, plan archives, private memories, generated trees, runtime
  logs, and Obsidian configuration are not release-package authority.
- `shiguan-hermes` must record its distinct role key and transport evidence. It
  must not claim external Hermes runtime execution unless verified in the
  current environment.
