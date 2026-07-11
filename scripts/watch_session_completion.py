"""Watch a Hermes session until it stops/ends and print one concise status line.

Environment variables:
  SESSION_ID   required
  DB_PATH      optional, defaults to ~/.hermes/state.db under the current user

Exit codes:
  0 = the session is no longer active / has ended
  2 = the session is still active (silent)
  1 = unexpected error
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SESSION_ID = os.environ.get("SESSION_ID", "").strip()
if not SESSION_ID:
    raise SystemExit("SESSION_ID is required")

DEFAULT_DB = Path.home() / ".hermes" / "state.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(DEFAULT_DB)))

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
row = con.execute(
    "select id, ended_at, end_reason, message_count, tool_call_count from sessions where id=?",
    (SESSION_ID,),
).fetchone()

if row is None:
    print(f"任务停止/完成，摘要：会话 {SESSION_ID} 已不存在于活动会话表中。")
    raise SystemExit(0)

if row["ended_at"] is not None:
    reason = row["end_reason"] or "unknown"
    print(
        f"任务停止/完成，摘要：会话 {SESSION_ID} 已结束，原因={reason}，消息数={row['message_count']}，工具调用={row['tool_call_count']}。"
    )
    raise SystemExit(0)

raise SystemExit(2)
