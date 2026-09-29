r"""史馆对照决策 · MCP stdio 服务。

暴露两个只读工具：
  shiguan_recall       给定待判定实录文本，返回最相似的历史实录及其裁定
  shiguan_recall_stats 返回索引统计

协议：JSON-RPC 2.0 over stdio（MCP 基线方法 initialize / tools/list / tools/call）。
本服务只读、无执行权，不写任何史馆数据。

用法（MCP 客户端配置）：
  command: <venv>\Scripts\python.exe
  args:    <this file>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shiguan_recall import SERVICE_VERSION, ShiguanRecall  # noqa: E402

ENGINE: ShiguanRecall | None = None

TOOLS = [
    {
        "name": "shiguan_recall",
        "description": (
            "史馆对照决策检索：给定一条待判定的史馆实录文本，返回最相似的历史实录，"
            "连同其诏令编号、五段谱系、记忆裁定、风险/知识/优先级等级。仅作对照参考，"
            "advisory 只读，不得据以写入史馆或替代门下裁定。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "待判定的实录文本（主题/阶段/摘要/要点）"},
                "k": {"type": "integer", "description": "返回条数，默认 5，上限 20", "minimum": 1, "maximum": 20},
                "same_topic": {"type": "boolean", "description": "true 时只在同主题记录内检索"},
            },
            "required": ["state"],
        },
    },
    {
        "name": "shiguan_recall_stats",
        "description": "返回史馆对照决策检索服务的索引统计（记录数、谱系数、向量维度、模型）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def engine() -> ShiguanRecall:
    global ENGINE
    if ENGINE is None:
        ENGINE = ShiguanRecall()
        ENGINE.build()
    return ENGINE


def _text(payload: object) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]}


def call(name: str, args: dict) -> dict:
    try:
        if name == "shiguan_recall":
            state = str(args.get("state") or "").strip()
            if not state:
                return _text({"ok": False, "problem": "state_required"})
            k = max(1, min(int(args.get("k") or 5), 20))
            out = engine().recall(state, k=k, same_top=bool(args.get("same_topic")))
            return _text({"ok": True, "tool": name, "dry_run": True, "write_enabled": False, **out})
        if name == "shiguan_recall_stats":
            out = engine().stats()
            return _text({"ok": True, "tool": name, "dry_run": True, "write_enabled": False, **out})
    except Exception as exc:  # noqa: BLE001
        return _text({"ok": False, "tool": name, "problem": f"{type(exc).__name__}: {exc}"})
    return _text({"ok": False, "problem": f"tool_not_allowed:{name}"})


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    rid = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "shiguan-recall", "version": SERVICE_VERSION},
            },
        }
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        return {"jsonrpc": "2.0", "id": rid, "result": call(str(params.get("name")), params.get("arguments") or {})}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method_not_found:{method}"}}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
