"""Ensure the local Shiguan web manager is running."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

sys.dont_write_bytecode = True
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from shiguan_paths import code_root, ensure_shared_seed, references_root as shared_references_root


DEFAULT_BIND_HOST = "127.0.0.1"


def skill_root() -> Path:
    return code_root()


def serve_script() -> Path:
    return skill_root() / "scripts" / "serve_shiguan_tree.py"


def background_python() -> str:
    candidate = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = candidate.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(candidate)


def static_entry() -> Path:
    return skill_root() / "web" / "shiguan-tree" / "index.html"


def service_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/"


def probe_host(host: str) -> str:
    if host in {"0.0.0.0", "::", ""}:
        return "127.0.0.1"
    return host


def is_wildcard_host(host: str) -> bool:
    return host in {"0.0.0.0", "::"}


def local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = info[4][0]
            if address.startswith("127.") or address.startswith("169.254."):
                continue
            addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def lan_urls(bind_host: str, port: int) -> list[str]:
    if not is_wildcard_host(bind_host):
        return [] if bind_host.startswith("127.") else [service_url(bind_host, port)]
    return [service_url(address, port) for address in local_ipv4_addresses()]


def api_state_url(host: str, port: int) -> str:
    return f"{service_url(probe_host(host), port)}api/state"


def api_health_url(host: str, port: int) -> str:
    return f"{service_url(probe_host(host), port)}api/health/private"


def port_accepts_connection(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((probe_host(host), port), timeout=timeout):
            return True
    except OSError:
        return False


def read_json_url(url: str, timeout: float) -> dict[str, object] | None:
    with urlopen(url, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    value = json.loads(raw)
    return value if isinstance(value, dict) else None


def classify_payload(payload: dict[str, object]) -> tuple[str, dict[str, object]]:
    web_root = str(payload.get("web_root") or "")
    payload_shared = str(payload.get("shared_shiguan_root") or "").strip()
    expected_shared = str(shared_references_root())
    if str(payload.get("service") or "") == "shiguan-tree" or "shiguan-tree" in web_root.replace("\\", "/"):
        if payload_shared and Path(payload_shared).resolve() != shared_references_root().resolve():
            payload["expected_shared_shiguan_root"] = expected_shared
            return "wrong-root", payload
        if not payload_shared:
            payload["expected_shared_shiguan_root"] = expected_shared
            return "wrong-root", payload
        return "shiguan", payload
    return "unknown", payload


def probe_service(host: str, port: int, timeout: float) -> tuple[str, dict[str, object] | None]:
    for url in (api_health_url(host, port), api_state_url(host, port)):
        try:
            payload = read_json_url(url, timeout)
        except HTTPError as exc:
            if "/api/health" in url and exc.code == 404:
                continue
            return ("occupied", None) if port_accepts_connection(host, port, 0.5) else ("closed", None)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            return ("occupied", None) if port_accepts_connection(host, port, 0.5) else ("closed", None)
        if payload is None:
            return "unknown", None
        return classify_payload(payload)
    return ("occupied", None) if port_accepts_connection(host, port, 0.5) else ("closed", None)


def start_service(host: str, port: int) -> Path:
    if port_accepts_connection(host, port, 1.0):
        raise RuntimeError(f"port {port} already accepts connections; refusing to start a duplicate Shiguan WebUI")
    log_path = Path(tempfile.gettempdir()) / f"court-shiguan-tree-{port}.log"
    handle = log_path.open("a", encoding="utf-8")
    args = [background_python(), "-B", str(serve_script()), "--host", host, "--port", str(port)]
    env = os.environ.copy()
    env["COURT_DISABLE_AGENT_PRESENCE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    kwargs: dict[str, object] = {
        "cwd": str(skill_root()),
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)
    handle.close()
    return log_path


def result(
    status: str,
    host: str,
    port: int,
    reason: str = "",
    log_path: Path | None = None,
) -> dict[str, object]:
    local_url = service_url("127.0.0.1", port)
    urls = lan_urls(host, port)
    url = urls[0] if urls else local_url
    is_available = status in {"RUNNING", "REUSED", "STARTED"} or (status == "CHECK_ONLY" and not reason)
    return {
        "status": status,
        "url": url if is_available else "",
        "local_url": local_url if is_available else "",
        "lan_urls": urls if is_available else [],
        "bind_host": host,
        "explicit_lan_opt_in": is_wildcard_host(host),
        "host": host,
        "port": port,
        "reason": reason,
        "code_root": str(skill_root()),
        "shared_shiguan_root": str(shared_references_root()),
        "log_path": str(log_path) if log_path else "",
        "static_entry": str(static_entry()),
        "manual_command": f"{sys.executable} {serve_script()} --host {host} --port {port}",
    }


def ensure(args: argparse.Namespace) -> dict[str, object]:
    max_port = max(args.port, args.max_port)
    first_local_only: tuple[int, str] | None = None
    first_wrong_root: tuple[int, str] | None = None
    first_occupied: tuple[int, str] | None = None
    for port in range(args.port, max_port + 1):
        state, payload = probe_service(args.host, port, args.timeout)
        if state == "shiguan":
            payload_bind = str((payload or {}).get("bind_host") or "")
            if is_wildcard_host(args.host) and not is_wildcard_host(payload_bind):
                if first_local_only is None:
                    first_local_only = (port, "local-only Shiguan service already uses this port")
                continue
            return result("CHECK_ONLY" if args.check_only else "REUSED", args.host, port)
        if state == "wrong-root":
            if first_wrong_root is None:
                found = str((payload or {}).get("shared_shiguan_root") or "legacy-or-unknown-root")
                first_wrong_root = (port, f"Shiguan service uses another data root: {found}")
            continue
        if state == "occupied":
            if first_occupied is None:
                first_occupied = (port, "port already has a listener but did not return Shiguan health; refusing duplicate start")
            continue
        if state == "unknown":
            continue
        if args.check_only:
            return result("CHECK_ONLY", args.host, port, "service not running")

        ensure_shared_seed()
        try:
            log_path = start_service(args.host, port)
        except RuntimeError as exc:
            return result("FAILED", args.host, port, str(exc))
        for _ in range(args.attempts):
            time.sleep(args.sleep)
            state, _payload = probe_service(args.host, port, args.timeout)
            if state == "shiguan":
                return result("STARTED", args.host, port, log_path=log_path)
            if state == "unknown":
                break
        return result("FAILED", args.host, port, "service did not become ready", log_path)

    if args.check_only and first_local_only:
        port, reason = first_local_only
        return result("CHECK_ONLY", args.host, port, f"LAN service not running; {reason}")
    if args.check_only and first_wrong_root:
        port, reason = first_wrong_root
        return result("CHECK_ONLY", args.host, port, f"shared-root service not running; {reason}")
    if args.check_only and first_occupied:
        port, reason = first_occupied
        return result("CHECK_ONLY", args.host, port, reason)
    if first_wrong_root:
        port, reason = first_wrong_root
        return result("FAILED", args.host, port, f"shared-root service not running; {reason}")
    if first_local_only:
        port, reason = first_local_only
        return result("FAILED", args.host, port, f"LAN service not running; {reason}")
    if first_occupied:
        port, reason = first_occupied
        return result("FAILED", args.host, port, reason)

    return result("FAILED", args.host, args.port, "Shiguan WebUI is restricted to the requested port; no fallback port was started")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_BIND_HOST)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-port", type=int, default=8765)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    report = ensure(args)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] != "FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
