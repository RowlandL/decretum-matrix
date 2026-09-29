r"""史馆对照决策 · HTTP API（本地只读服务）。

端点：
  GET  /health          健康检查
  GET  /stats           索引统计
  POST /recall          {"state": "...", "k": 5, "same_topic": false}

只读、无执行权。默认绑定 127.0.0.1:8767。
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shiguan_recall import SERVICE_VERSION, ShiguanRecall  # noqa: E402

ENGINE = ShiguanRecall()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 静默
        pass

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            self._send(200, {"ok": True, "service": "shiguan-recall", "version": SERVICE_VERSION})
        elif self.path.startswith("/stats"):
            if ENGINE.vecs is None:
                ENGINE.build()
            self._send(200, {"ok": True, **ENGINE.stats()})
        else:
            self._send(404, {"ok": False, "problem": "not_found"})

    def do_POST(self):  # noqa: N802
        if not self.path.startswith("/recall"):
            self._send(404, {"ok": False, "problem": "not_found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
            state = str(payload.get("state") or "").strip()
            if not state:
                self._send(400, {"ok": False, "problem": "state_required"})
                return
            k = max(1, min(int(payload.get("k") or 5), 20))
            out = ENGINE.recall(state, k=k, same_top=bool(payload.get("same_topic")))
            self._send(200, {"ok": True, "dry_run": True, "write_enabled": False, **out})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"ok": False, "problem": f"{type(exc).__name__}: {exc}"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8767)
    args = ap.parse_args()
    print(f"shiguan-recall {SERVICE_VERSION} -> http://{args.host}:{args.port}", flush=True)
    print(json.dumps(ENGINE.stats(), ensure_ascii=False), flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
