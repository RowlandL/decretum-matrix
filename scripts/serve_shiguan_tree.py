"""Serve the local Shiguan growth-tree management UI."""

from __future__ import annotations

from datetime import datetime, timedelta
import argparse
import hashlib
import hmac
import io
import ipaddress
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import zipfile
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock, shiguan_write_lock_path
from obsidian_config_state import (
    patch_config as patch_obsidian_sync_config,
    read_config_snapshot as read_obsidian_sync_config_snapshot,
)
from shiguan_entry_utils import enrich_entry
from shiguan_security import (
    ADMIN_TOKEN_ENV,
    MAX_JSON_BODY_BYTES,
    admin_auth_public_state,
    client_is_local,
)
from shiguan_paths import (
    code_root,
    default_obsidian_cache_vault,
    default_obsidian_inbox,
    default_obsidian_parent_vault,
    default_obsidian_shared_vault,
    ensure_shared_seed,
    reference_path,
    references_root as shared_references_root,
    shared_root as shiguan_shared_root,
)
from shiguan_peer_state import (
    CAESAR_SHIFT,
    PEER_STATE_FIELDS,
    PEER_STATE_MAX_BYTES,
    PEER_STATE_SCHEMA,
    PeerStateError,
    caesar_transform,
    decode_peer_key,
    encode_peer_key,
    ensure_node_identity,
    imported_peers,
    imported_peers_path,
    issued_keys,
    issued_keys_path,
    node_identity_path,
    peer_root,
    peer_state_lock_path,
    peer_state_path,
    peer_state_snapshot,
    public_peer,
    read_node_identity,
    read_peer_state,
    save_imported_peers,
    save_issued_keys,
    stable_machine_uid,
    token_hash,
    update_peer_state,
)
from shiguan_peer_downloads import (
    PEER_PENDING_DOWNLOAD_SECONDS,
    PENDING_KEY_DOWNLOADS,
    PENDING_KEY_DOWNLOADS_LOCK,
    cleanup_pending_key_downloads,
    credential_transition_gate,
    download_pending_key,
    key_expired,
    latest_pending_key_download,
    mark_pending_key_delivery,
    pending_downloads,
    pending_key_download,
    peer_transaction,
    public_issued_key,
    remember_pending_key_download,
)
from shiguan_web_pending import (
    PENDING_IMPORT_METADATA_FIELDS,
    PENDING_IMPORT_METADATA_MAX_BYTES,
    PENDING_IMPORT_METADATA_SUFFIX,
    PENDING_IMPORT_SHA256_RE,
    aggregate_import_metric,
    import_pending_root,
    import_processed_root,
    import_queue_root,
    import_queue_summary,
    import_seen_ids,
    import_seen_path,
    optional_nonnegative_int,
    pending_import_files,
    pending_import_metadata_path,
    public_pending_import,
    read_pending_import,
)


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\\/-]{2,}|[\u4e00-\u9fff]{2,}")
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}
SERVER_BIND_HOST = "127.0.0.1"
SERVER_PORT = 8765
PEER_TIMEOUT_SECONDS = 1.8
PEER_KEY_ID_BYTES = 24
PEER_KEY_TOKEN_BYTES = 96
ADMIN_REQUEST_HEADER = "X-Shiguan-Admin-Request"
PUBLIC_STATE_LIMIT = 200
MAX_OBSIDIAN_IMPORT_FILES = 200
MAX_OBSIDIAN_IMPORT_FILE_BYTES = 2 * 1024 * 1024
MAX_OBSIDIAN_IMPORT_TOTAL_BYTES = 8 * 1024 * 1024
MAX_OBSIDIAN_CONFIG_IMPORT_PATHS = 50
MAX_OBSIDIAN_WATCH_PATHS = 8
REMOTE_OBSIDIAN_ENDPOINT_ENV = "SHIGUAN_ALLOW_REMOTE_OBSIDIAN_ENDPOINT"
PUBLIC_ENTRY_FIELDS = {
    "id",
    "court_code",
    "ancient_lineage",
    "lineage_display",
    "topic",
    "phase",
    "status",
    "time",
    "record_type",
    "risk_level",
    "knowledge_value",
    "priority_level",
    "court_code_parts",
    "display_summary_zh",
    "display_keywords_zh",
    "source_agent_label",
}
PUBLIC_STATE_FIELDS = {
    "service",
    "version",
    "entries",
    "count",
    "local_count",
    "peer_count",
    "shown",
    "shown_total",
    "knowledge_graph",
    "port",
    "read_only",
    "admin_auth",
}
PUBLIC_HEALTH_FIELDS = {
    "ok",
    "service",
    "version",
    "port",
    "read_only",
    "admin_auth_required",
}
PUBLIC_GRAPH_KINDS = {"root", "record"}
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"(?i)(?:\b[A-Z]:[\\/]|\\\\)[^\s\"'<>|]+")
POSIX_PRIVATE_PATH_RE = re.compile(r"(?i)(?<![A-Za-z0-9:])/(?:home|users|mnt|tmp|var/tmp)/[^\s\"'<>]+")
PUBLIC_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|cookie|token|secret|password)\s*[:=]\s*([^\s,;]+)"
)
ADMIN_GET_PATHS = {
    "/api/health/private",
    "/api/key/export-file",
    "/api/keys",
    "/api/obsidian-sync/status",
}
ADMIN_POST_PATHS = {
    "/api/security-check",
    "/api/entry",
    "/api/rebuild",
    "/api/grow",
    "/api/export",
    "/api/import-obsidian",
    "/api/import-text",
    "/api/obsidian-sync/config",
    "/api/obsidian-sync/preview",
    "/api/obsidian-sync/import",
    "/api/obsidian-sync/export",
    "/api/obsidian-sync/filesystem",
    "/api/key/generate",
    "/api/key/export",
    "/api/key/import",
    "/api/key/manage",
    "/api/key/expire",
    "/api/peer/save",
}


def sanitize_public_text(value: object, limit: int = 500) -> str:
    text = str(value or "")
    text = WINDOWS_ABSOLUTE_PATH_RE.sub("[LOCAL_PATH]", text)
    text = POSIX_PRIVATE_PATH_RE.sub("[LOCAL_PATH]", text)
    text = PUBLIC_SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return text[:limit]


def sanitize_public_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): sanitize_public_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_public_value(item) for item in value[:40]]
    if isinstance(value, str):
        return sanitize_public_text(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return sanitize_public_text(value)


def public_entry_projection(entry: dict[str, object]) -> dict[str, object]:
    return {
        key: sanitize_public_value(entry.get(key))
        for key in PUBLIC_ENTRY_FIELDS
        if key in entry
    }


def public_entry_score(entry: dict[str, object], terms: list[str]) -> int:
    if not terms:
        return 0
    searchable = "\n".join(
        str(entry.get(key) or "")
        for key in PUBLIC_ENTRY_FIELDS
        if key not in {"court_code_parts"}
    ).lower()
    return sum(1 for term in terms if term.lower() in searchable)


def select_public_entries(query: str, limit: int) -> tuple[list[dict[str, object]], int]:
    projected = [public_entry_projection(entry) for entry in load_entries()]
    terms = [term for term in re.split(r"\s+", query.strip()) if term]
    if terms:
        scored = [(public_entry_score(entry, terms), entry) for entry in projected]
        projected = [entry for score, entry in scored if score > 0]
        projected.sort(
            key=lambda entry: (public_entry_score(entry, terms), str(entry.get("time") or "")),
            reverse=True,
        )
    else:
        projected.sort(key=lambda entry: str(entry.get("time") or ""), reverse=True)
    return projected[: max(1, min(limit, PUBLIC_STATE_LIMIT))], len(projected)


def public_graph_projection(graph: dict[str, object]) -> dict[str, object]:
    raw_nodes = graph.get("nodes") if isinstance(graph, dict) else []
    nodes: list[dict[str, object]] = []
    allowed_ids: set[str] = set()
    for node in raw_nodes if isinstance(raw_nodes, list) else []:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("kind") or "")
        if kind not in PUBLIC_GRAPH_KINDS and not kind.startswith("lineage:"):
            continue
        node_id = str(node.get("id") or "")
        if not node_id or WINDOWS_ABSOLUTE_PATH_RE.search(node_id) or POSIX_PRIVATE_PATH_RE.search(node_id):
            continue
        projected = {
            key: sanitize_public_value(node.get(key))
            for key in ("id", "kind", "label", "count", "level")
            if key in node
        }
        nodes.append(projected)
        allowed_ids.add(node_id)
    raw_edges = graph.get("edges") if isinstance(graph, dict) else []
    edges = [
        {
            key: sanitize_public_value(edge.get(key))
            for key in ("source", "target", "relation", "weight")
            if key in edge
        }
        for edge in raw_edges if isinstance(raw_edges, list) and isinstance(edge, dict)
        if str(edge.get("source") or "") in allowed_ids and str(edge.get("target") or "") in allowed_ids
    ]
    schema = graph.get("schema") if isinstance(graph, dict) and isinstance(graph.get("schema"), dict) else {}
    return {
        "schema": {key: schema.get(key) for key in ("name", "version") if key in schema},
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "nodes": nodes,
        "edges": edges,
    }


def public_health_projection(port: int) -> dict[str, object]:
    result = {
        "ok": True,
        "service": "shiguan-tree",
        "version": "1.1",
        "port": int(port),
        "read_only": True,
        "admin_auth_required": True,
    }
    return {key: result[key] for key in PUBLIC_HEALTH_FIELDS}


def public_state_projection(query: str, limit: int, port: int) -> dict[str, object]:
    entries, total = select_public_entries(query, limit)
    result = {
        "service": "shiguan-tree",
        "version": "1.1",
        "entries": entries,
        "count": total,
        "local_count": total,
        "peer_count": 0,
        "shown": len(entries),
        "shown_total": len(entries),
        "knowledge_graph": public_graph_projection(load_knowledge_graph()),
        "port": int(port),
        "read_only": True,
        "admin_auth": {"required": True, "authenticated": False},
    }
    return {key: result[key] for key in PUBLIC_STATE_FIELDS}


def normalized_host(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")].rstrip(".")
    if text.count(":") == 1:
        host, port = text.rsplit(":", 1)
        if port.isdigit():
            text = host
    return text.rstrip(".")


def host_port(value: str, default_port: int) -> tuple[str, int]:
    text = str(value or "").strip()
    host = normalized_host(text)
    if text.startswith("[") and "]" in text:
        suffix = text[text.index("]") + 1:]
        return host, int(suffix[1:]) if suffix.startswith(":") and suffix[1:].isdigit() else default_port
    if text.count(":") == 1:
        _host, port = text.rsplit(":", 1)
        if port.isdigit():
            return host, int(port)
    return host, default_port


def safe_request_hosts() -> set[str]:
    hosts = {"127.0.0.1", "::1", "localhost"}
    hosts.update(address.lower() for address in local_ipv4_addresses())
    for value in (socket.gethostname(), socket.getfqdn()):
        if value:
            hosts.add(str(value).strip().lower().rstrip("."))
    if SERVER_BIND_HOST and not is_wildcard_host(SERVER_BIND_HOST):
        hosts.add(normalized_host(SERVER_BIND_HOST))
    return {host for host in hosts if host}


def request_host_allowed(host_header: str) -> bool:
    return normalized_host(host_header) in safe_request_hosts()


def origin_matches_host(origin: str, host_header: str) -> bool:
    try:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        request_host, request_port = host_port(host_header, SERVER_PORT)
        origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return parsed.hostname.lower().rstrip(".") == request_host and origin_port == request_port
    except ValueError:
        return False


def obsidian_endpoint_is_loopback(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost":
            return True
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_obsidian_endpoint(endpoint: object, verify_ssl: bool) -> str:
    text = str(endpoint or "").strip().rstrip("/")
    try:
        parsed = urlparse(text)
        valid_base = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError as exc:
        raise ValueError("Obsidian endpoint 格式无效") from exc
    if not valid_base:
        raise ValueError("Obsidian endpoint 必须是无凭据、无 query/fragment 的 http(s) 地址")
    if obsidian_endpoint_is_loopback(text):
        return text
    if not truthy(os.environ.get(REMOTE_OBSIDIAN_ENDPOINT_ENV)):
        raise ValueError(
            f"远程 Obsidian endpoint 默认禁用；确需启用时设置 {REMOTE_OBSIDIAN_ENDPOINT_ENV}=1"
        )
    if parsed.scheme != "https" or not verify_ssl:
        raise ValueError("远程 Obsidian endpoint 必须使用 HTTPS 且 verify_ssl=true")
    return text


def path_is_same_or_ancestor(candidate: Path, protected: Path) -> bool:
    return candidate == protected or candidate in protected.parents


def validate_local_content_root(value: object, label: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} 不能为空")
    raw = Path(text).expanduser()
    if not raw.is_absolute():
        raise ValueError(f"{label} 必须是绝对路径")
    resolved = raw.resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError(f"{label} 不允许使用磁盘或文件系统根目录")
    home = Path.home().resolve()
    if path_is_same_or_ancestor(resolved, home):
        raise ValueError(f"{label} 不允许指向用户 home 或其祖先")
    dedicated_ingress = default_obsidian_inbox().resolve()
    for protected in (skill_root().resolve(), shiguan_shared_root().resolve()):
        if resolved == dedicated_ingress and protected == shiguan_shared_root().resolve():
            continue
        if (
            path_is_same_or_ancestor(resolved, protected)
            or protected in resolved.parents
        ):
            raise ValueError(f"{label} 不允许指向 skill/shared 根、其祖先或后代")
    return resolved


def validate_obsidian_import_note_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        raise ValueError("Obsidian import_path 不能为空")
    if text.startswith("/") or re.match(r"(?i)^[a-z]:/", text) or text.startswith("//"):
        raise ValueError("Obsidian import_path 必须是 vault 内相对路径")
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("Obsidian import_path 不允许为空或包含上级目录")
    return "/".join(parts)


def validated_obsidian_import_paths(raw_paths: object) -> list[str]:
    if isinstance(raw_paths, str):
        candidates = [part.strip() for part in re.split(r"[\n,，]+", raw_paths) if part.strip()]
    elif isinstance(raw_paths, list):
        candidates = [str(item).strip() for item in raw_paths if str(item).strip()]
    else:
        candidates = []
    if len(candidates) > MAX_OBSIDIAN_CONFIG_IMPORT_PATHS:
        raise ValueError(f"Obsidian import_paths 最多允许 {MAX_OBSIDIAN_CONFIG_IMPORT_PATHS} 项")
    return unique([validate_obsidian_import_note_path(item) for item in candidates], MAX_OBSIDIAN_CONFIG_IMPORT_PATHS)


def validated_obsidian_watch_paths(raw_paths: object, defaults: list[str] | None = None) -> list[str]:
    if isinstance(raw_paths, str):
        candidates = [part.strip() for part in re.split(r"[\n,，]+", raw_paths) if part.strip()]
    elif isinstance(raw_paths, list):
        candidates = [str(item).strip() for item in raw_paths if str(item).strip()]
    else:
        candidates = []
    if not candidates:
        candidates = list(defaults or [])
    if len(candidates) > MAX_OBSIDIAN_WATCH_PATHS:
        raise ValueError(f"Obsidian watch_paths 最多允许 {MAX_OBSIDIAN_WATCH_PATHS} 项")
    normalized = [str(validate_local_content_root(item, "Obsidian watch_path")) for item in candidates]
    return unique(normalized, MAX_OBSIDIAN_WATCH_PATHS)


def skill_root() -> Path:
    return code_root()


def web_root() -> Path:
    return skill_root() / "web" / "shiguan-tree"


def references_root() -> Path:
    return shared_references_root()


def server_lock_path(port: int) -> Path:
    return reference_path("court-runtime", f"shiguan-web-{port}.lock")


def acquire_server_lock(port: int):
    path = server_lock_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError(f"another Shiguan WebUI process already holds {path}") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()).encode("ascii"))
    handle.flush()
    return handle


def index_path() -> Path:
    return references_root() / "shiguan-index.jsonl"


def tree_root() -> Path:
    return references_root() / "shiguan-tree"


def agent_presence_root() -> Path:
    return references_root() / "court-runtime" / "agente-presence"


def obsidian_sync_root() -> Path:
    return references_root() / "obsidian-sync"


def obsidian_sync_config_path() -> Path:
    return obsidian_sync_root() / "config.json"


def autosync_status_path() -> Path:
    return obsidian_sync_root() / "autosync-daemon.json"


def knowledge_graph_path() -> Path:
    return references_root() / "shiguan-knowledge-graph.json"


def web_state_lock_path() -> Path:
    """Serialize WebUI state read-modify-write transactions across threads/processes."""

    return reference_path("court-runtime", "shiguan-web-state.lock")


def service_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/"


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


def manual_root() -> Path:
    return tree_root() / "manual"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return value[:64] or "entry"


def stable_id(entry: dict[str, object]) -> str:
    material = "|".join(
        str(entry.get(key, ""))
        for key in ("record_type", "source", "time", "topic", "phase", "status", "summary")
    )
    return hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]


def split_terms(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "")
    parts = re.split(r"[,;，；\n]+", text)
    return [part.strip() for part in parts if part.strip()]


def unique(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def derive_keywords(entry: dict[str, object]) -> list[str]:
    manual = split_terms(entry.get("keywords"))
    text = "\n".join(
        str(entry.get(key, ""))
        for key in ("topic", "phase", "status", "summary", "evidence", "memory_content")
    )
    automatic = [token.strip("`'\".,:()[]{}<>") for token in TOKEN_RE.findall(text)]
    return unique(manual + automatic, 32)


def load_entries() -> list[dict[str, object]]:
    path = index_path()
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            enrich_entry(value)
            entries.append(value)
    return entries


def write_entries(entries: list[dict[str, object]]) -> None:
    path = index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(entries, key=lambda entry: (str(entry.get("time", "")), str(entry.get("id", ""))))
    text = "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in ordered)
    atomic_write_text(path, text)


def write_manual_entry(entry: dict[str, object]) -> None:
    manual_root().mkdir(parents=True, exist_ok=True)
    path = manual_root() / f"{entry['id']}.json"
    atomic_write_text(
        path,
        json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def score_entry(entry: dict[str, object], terms: list[str]) -> int:
    if not terms:
        return 0
    weighted_parts: list[tuple[int, str]] = []
    for key in ("topic", "phase", "status", "court_code", "ancient_lineage", "lineage_display", "lineage_key"):
        weighted_parts.append((4, str(entry.get(key, ""))))
    parts = entry.get("lineage_parts")
    if isinstance(parts, dict):
        weighted_parts.extend((4, str(value)) for value in parts.values())
    facets = entry.get("facet_dimensions")
    if isinstance(facets, dict):
        for values in facets.values():
            if isinstance(values, list):
                weighted_parts.extend((4, str(value)) for value in values)
            else:
                weighted_parts.append((4, str(values)))
    for key in ("keywords", "keywords_zh", "keywords_en", "key_actions"):
        value = entry.get(key)
        if isinstance(value, list):
            weighted_parts.extend((5, str(item)) for item in value)
    for key in (
        "display_labels_zh",
        "display_summary_zh",
        "display_reason_zh",
        "keyword_summary_zh",
        "keyword_summary_en",
        "summary",
        "memory_content",
        "memory_reason",
    ):
        weighted_parts.append((2, str(entry.get(key, ""))))
    for key in ("evidence", "next", "source"):
        weighted_parts.append((1, str(entry.get(key, ""))))
    score = 0
    for weight, value in weighted_parts:
        lowered = value.lower()
        score += sum(weight for term in terms if term.lower() in lowered)
    return score


def select_entries(query: str, limit: int) -> list[dict[str, object]]:
    entries = load_entries()
    terms = [term for term in re.split(r"\s+", query.strip()) if term]
    if terms:
        scored = [(score_entry(entry, terms), entry) for entry in entries]
        entries = [entry for score, entry in scored if score > 0]
        entries.sort(key=lambda entry: (score_entry(entry, terms), str(entry.get("time", ""))), reverse=True)
    else:
        entries.sort(key=lambda entry: str(entry.get("time", "")), reverse=True)
    return entries[: max(limit, 1)]


def refresh_tree() -> None:
    from grow_shiguan_tree import grow_tree

    grow_tree()
    from build_shiguan_knowledge_graph import build_and_write

    build_and_write()


def rebuild_index() -> int:
    from rebuild_shiguan_index import rebuild_index as rebuild

    count, _ = rebuild()
    return count


def load_knowledge_graph() -> dict[str, object]:
    path = knowledge_graph_path()
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def export_obsidian(out: str | None, zip_output: bool) -> dict[str, object]:
    from export_shiguan_obsidian import check_export, copy_tree, safe_out, zip_dir

    default_out = Path(tempfile.gettempdir()) / "Court Shiguan"
    target = safe_out(out or str(default_out))
    copy_tree(target)
    errors = check_export(target)
    zip_path = str(zip_dir(target)) if zip_output else ""
    return {"out": str(target), "zip": zip_path, "errors": errors}


def read_json_file(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json_file(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def background_python() -> str:
    candidate = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = candidate.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(candidate)


def hidden_run_kwargs() -> dict[str, object]:
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def parse_presence_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def agent_presence_statuses() -> list[dict[str, object]]:
    root = agent_presence_root()
    if not root.exists():
        return []
    now = datetime.now()
    statuses: list[dict[str, object]] = []
    for path in sorted(root.glob("*.json")):
        value = read_json_file(path, {})
        if not isinstance(value, dict):
            continue
        last_seen = parse_presence_time(value.get("last_seen") or value.get("updated_at"))
        ttl = int(value.get("ttl_seconds") or 180)
        age = int((now - last_seen).total_seconds()) if last_seen else None
        online = age is not None and age <= max(30, ttl)
        statuses.append(
            {
                "agent_id": str(value.get("agent_id") or value.get("source_agent") or path.stem),
                "label": str(value.get("label") or value.get("source_agent_label") or path.stem),
                "status": "online" if online else "offline",
                "last_seen": str(value.get("last_seen") or value.get("updated_at") or ""),
                "age_seconds": age,
                "event": str(value.get("event") or ""),
                "host": str(value.get("host") or ""),
                "pid": value.get("pid"),
                "skill_root": str(value.get("source_agent_skill_root") or ""),
            }
        )
    statuses.sort(key=lambda item: (str(item.get("status")) != "online", str(item.get("label")).lower()))
    return statuses


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def estimate_tokens(text: str) -> int:
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    non_cjk_count = max(0, len(text) - cjk_count)
    # Startup提示只需要粗估：中文约0.8 token/字，非中文约1 token/4字符，另加处理开销。
    return max(1, int(cjk_count * 0.8 + non_cjk_count / 4 + 120))


def parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def first_share_host() -> str:
    if is_wildcard_host(SERVER_BIND_HOST):
        addresses = local_ipv4_addresses()
        return addresses[0] if addresses else "127.0.0.1"
    return SERVER_BIND_HOST


def default_share_port() -> int:
    return SERVER_PORT


def default_share_endpoint() -> str:
    return service_url(first_share_host(), default_share_port())


def obsidian_sync_config(
    include_secret: bool = False,
    stored_override: dict[str, object] | None = None,
) -> dict[str, object]:
    stored = stored_override if stored_override is not None else read_obsidian_sync_config_snapshot()
    cache_vault = str(stored.get("cache_vault_path") or stored.get("vault_path") or default_obsidian_cache_vault())
    watch_paths = stored.get("watch_paths")
    if not isinstance(watch_paths, list):
        watch_paths = [cache_vault, str(default_obsidian_inbox())]
    config = {
        "endpoint": str(stored.get("endpoint") or "https://127.0.0.1:27124").rstrip("/"),
        "has_api_key": bool(stored.get("api_key")),
        "verify_ssl": bool(stored.get("verify_ssl", False)),
        "sync_mode": str(stored.get("sync_mode") or "filesystem_preserve_only"),
        "import_query": str(stored.get("import_query") or ""),
        "import_paths": (
            [str(item) for item in stored.get("import_paths", []) if str(item).strip()]
            if isinstance(stored.get("import_paths"), list)
            else []
        )[:MAX_OBSIDIAN_CONFIG_IMPORT_PATHS],
        "output_folder": str(stored.get("output_folder") or "Court Shiguan"),
        "auto_enabled": bool(stored.get("auto_enabled", stored.get("autosync_enabled", True))),
        "autosync_enabled": bool(stored.get("autosync_enabled", stored.get("auto_enabled", True))),
        "autosync_interval_seconds": bounded_int(stored.get("autosync_interval_seconds"), 20, 5, 3600),
        "autosync_script": str(stored.get("autosync_script") or skill_root() / "scripts" / "shiguan_autosync_daemon.py"),
        "filesystem_sync_script": str(stored.get("filesystem_sync_script") or skill_root() / "scripts" / "sync_shiguan_obsidian_vault.py"),
        "vault_path": str(stored.get("vault_path") or cache_vault),
        "cache_vault_path": cache_vault,
        "source_vault_path": str(stored.get("source_vault_path") or default_obsidian_shared_vault()),
        "parent_vault_path": str(stored.get("parent_vault_path") or default_obsidian_parent_vault()),
        "watch_paths": [str(item) for item in watch_paths if str(item).strip()][:MAX_OBSIDIAN_WATCH_PATHS],
        "shared_shiguan_root": str(stored.get("shared_shiguan_root") or references_root()),
        "updated_at": str(stored.get("updated_at") or ""),
        "schema": str(stored.get("schema") or ""),
        "revision": int(stored.get("revision") or 0),
        "transaction_id": str(stored.get("transaction_id") or ""),
    }
    if include_secret:
        config["api_key"] = str(stored.get("api_key") or "")
    return config


def save_obsidian_sync_config(payload: dict[str, object]) -> dict[str, object]:
    base = read_obsidian_sync_config_snapshot()
    current = obsidian_sync_config(include_secret=True, stored_override=base)
    raw_paths = payload.get("import_paths", current.get("import_paths", []))
    import_paths = validated_obsidian_import_paths(raw_paths)
    api_key = str(payload.get("api_key") or current.get("api_key") or "").strip()
    cache_vault = str(
        validate_local_content_root(
            payload.get("cache_vault_path")
            or payload.get("vault_path")
            or current.get("cache_vault_path")
            or current.get("vault_path")
            or default_obsidian_cache_vault(),
            "Obsidian cache_vault_path",
        )
    )
    raw_watch_paths = payload.get("watch_paths", current.get("watch_paths", []))
    watch_paths = validated_obsidian_watch_paths(
        raw_watch_paths,
        [cache_vault, str(default_obsidian_inbox())],
    )
    auto_enabled = truthy(payload.get("auto_enabled")) if "auto_enabled" in payload else bool(current.get("auto_enabled", True))
    autosync_enabled = truthy(payload.get("autosync_enabled")) if "autosync_enabled" in payload else auto_enabled
    verify_ssl = truthy(payload.get("verify_ssl")) if "verify_ssl" in payload else bool(current.get("verify_ssl", False))
    endpoint = validate_obsidian_endpoint(
        payload.get("endpoint") or current.get("endpoint") or "https://127.0.0.1:27124",
        verify_ssl,
    )
    config = {
        "endpoint": endpoint,
        "api_key": api_key,
        "verify_ssl": verify_ssl,
        "sync_mode": str(payload.get("sync_mode") or current.get("sync_mode") or "manual"),
        "import_query": str(payload.get("import_query", current.get("import_query", "")) or ""),
        "import_paths": import_paths,
        "output_folder": str(payload.get("output_folder") or current.get("output_folder") or "Court Shiguan").strip().strip("/") or "Court Shiguan",
        "auto_enabled": auto_enabled,
        "autosync_enabled": autosync_enabled,
        "autosync_interval_seconds": bounded_int(payload.get("autosync_interval_seconds") or current.get("autosync_interval_seconds"), 20, 5, 3600),
        "vault_path": str(
            validate_local_content_root(
                payload.get("vault_path") or current.get("vault_path") or cache_vault,
                "Obsidian vault_path",
            )
        ),
        "cache_vault_path": cache_vault,
        "source_vault_path": str(
            Path(
                str(payload.get("source_vault_path") or current.get("source_vault_path") or default_obsidian_shared_vault())
            ).expanduser().resolve()
        ),
        "parent_vault_path": str(
            validate_local_content_root(
                payload.get("parent_vault_path") or current.get("parent_vault_path") or default_obsidian_parent_vault(),
                "Obsidian parent_vault_path",
            )
        ),
        "watch_paths": watch_paths,
        "autosync_script": str(payload.get("autosync_script") or current.get("autosync_script") or skill_root() / "scripts" / "shiguan_autosync_daemon.py"),
        "filesystem_sync_script": str(payload.get("filesystem_sync_script") or current.get("filesystem_sync_script") or skill_root() / "scripts" / "sync_shiguan_obsidian_vault.py"),
        "shared_shiguan_root": str(references_root()),
    }
    requested_fields = {str(key) for key in payload if str(key) in config}
    if {"cache_vault_path", "vault_path"}.intersection(payload):
        requested_fields.update({"cache_vault_path", "vault_path", "watch_paths"})
    if "auto_enabled" in payload and "autosync_enabled" not in payload:
        requested_fields.add("autosync_enabled")
    if "verify_ssl" in payload or "endpoint" in payload:
        requested_fields.update({"verify_ssl", "endpoint"})
    for invariant in ("shared_shiguan_root", "autosync_script", "filesystem_sync_script"):
        if not base.get(invariant):
            requested_fields.add(invariant)
    changes = {field: config[field] for field in requested_fields}
    result = patch_obsidian_sync_config(changes, base_snapshot=base)
    if result.get("conflict"):
        raise ValueError("Obsidian 同步配置并发冲突：" + ", ".join(result.get("conflict_fields", [])))
    return obsidian_sync_config(include_secret=False)


def obsidian_api_request(
    path: str,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str = "application/json",
    timeout: float = 10,
) -> tuple[int, bytes, str]:
    config = obsidian_sync_config(include_secret=True)
    endpoint = str(config.get("endpoint") or "").rstrip("/")
    api_key = str(config.get("api_key") or "")
    if not endpoint or not api_key:
        raise ValueError("缺少 Obsidian REST API endpoint 或 API key")
    endpoint = validate_obsidian_endpoint(endpoint, bool(config.get("verify_ssl")))
    url = endpoint + (path if path.startswith("/") else f"/{path}")
    headers = {"Authorization": f"Bearer {api_key}"}
    if body is not None:
        headers["Content-Type"] = content_type
    request = Request(url, data=body, method=method, headers=headers)
    context = None if bool(config.get("verify_ssl")) else ssl._create_unverified_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        return response.status, response.read(), response.headers.get("Content-Type", "")


def obsidian_path(path: str) -> str:
    parts = [part for part in str(path).replace("\\", "/").strip("/").split("/") if part]
    return "/".join(quote(part, safe="") for part in parts)


def normalize_obsidian_search_results(value: object, limit: int) -> list[str]:
    paths: list[str] = []

    def add(candidate: object) -> None:
        text = str(candidate or "").strip()
        if text and text not in paths:
            paths.append(text)

    def walk(node: object) -> None:
        if len(paths) >= limit:
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for key in ("path", "filename", "file", "name"):
                if key in node:
                    add(node.get(key))
                    break
            for key in ("matches", "results", "children"):
                if key in node:
                    walk(node.get(key))
        elif isinstance(node, str) and node.lower().endswith((".md", ".txt")):
            add(node)

    walk(value)
    return paths[:limit]


def obsidian_sync_status() -> dict[str, object]:
    config = obsidian_sync_config(include_secret=False)
    if not config.get("has_api_key"):
        return {"ok": False, "message": "尚未保存 API key", "config": config, "autosync": autosync_public_status()}
    try:
        status, body, _ = obsidian_api_request("/", timeout=2.5)
        return {
            "ok": 200 <= status < 300,
            "status": status,
            "message": body.decode("utf-8", errors="replace")[:240],
            "config": obsidian_sync_config(False),
            "autosync": autosync_public_status(),
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc), "config": obsidian_sync_config(False), "autosync": autosync_public_status()}


def autosync_public_status() -> dict[str, object]:
    status = read_json_file(autosync_status_path(), {})
    if isinstance(status, dict) and status:
        return {key: value for key, value in status.items() if key != "snapshot"}
    return {
        "ok": False,
        "message": "autosync daemon 尚未运行",
        "status_path": str(autosync_status_path()),
        "shared_shiguan_root": str(references_root()),
    }


def obsidian_sync_public_state() -> dict[str, object]:
    config = obsidian_sync_config(False)
    return {
        "ok": False,
        "message": "未测试连接",
        "config": config,
        "autosync": autosync_public_status(),
    }


def read_obsidian_note(path: str) -> dict[str, str]:
    safe_path = validate_obsidian_import_note_path(path)
    _, body, _ = obsidian_api_request(f"/vault/{obsidian_path(safe_path)}")
    return {
        "filename": Path(safe_path).name or "obsidian-note.md",
        "path": safe_path,
        "text": body.decode("utf-8", errors="replace"),
    }


def obsidian_sync_preview(payload: dict[str, object]) -> dict[str, object]:
    if payload.get("save_config"):
        save_obsidian_sync_config(payload)
    config = obsidian_sync_config(False)
    limit = max(1, min(int(payload.get("limit") or 20), 100))
    raw_paths = payload.get("paths") or config.get("import_paths") or []
    paths = validated_obsidian_import_paths(raw_paths)
    query = str(payload.get("query") or config.get("import_query") or "").strip()
    errors: list[str] = []
    if query:
        try:
            _, raw, _ = obsidian_api_request(f"/search/simple/?{urlencode({'query': query})}", "POST", b"")
            try:
                search_value = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                search_value = raw.decode("utf-8", errors="replace")
            for candidate in normalize_obsidian_search_results(search_value, limit):
                try:
                    paths.append(validate_obsidian_import_note_path(candidate))
                except ValueError:
                    continue
        except Exception as exc:
            errors.append(str(exc))
    paths = unique(paths, min(limit, MAX_OBSIDIAN_CONFIG_IMPORT_PATHS))
    samples: list[dict[str, object]] = []
    for path in paths:
        try:
            note = read_obsidian_note(path)
            samples.append({
                "path": note["path"],
                "filename": note["filename"],
                "char_count": len(note["text"]),
                "estimated_tokens": estimate_tokens(note["text"]),
            })
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    return {
        "config": obsidian_sync_config(False),
        "paths": paths,
        "found": len(samples),
        "estimated_tokens": sum(int(item.get("estimated_tokens") or 0) for item in samples),
        "char_count": sum(int(item.get("char_count") or 0) for item in samples),
        "samples": samples[:8],
        "errors": errors[:10],
    }


def obsidian_sync_import(payload: dict[str, object]) -> dict[str, object]:
    preview = obsidian_sync_preview(payload)
    files: list[dict[str, object]] = []
    for path in preview.get("paths", []):
        try:
            note = read_obsidian_note(str(path))
            files.append({
                "filename": note["filename"],
                "text": note["text"],
                "source": f"obsidian-api:{note['path']}",
            })
        except Exception:
            continue
    queued = queue_import_text({"files": files, "source_prefix": "obsidian-api"})
    return {"preview": preview, "queue": queued}


def obsidian_sync_export(payload: dict[str, object]) -> dict[str, object]:
    if payload.get("save_config"):
        save_obsidian_sync_config(payload)
    config = obsidian_sync_config(False)
    target_folder = str(payload.get("output_folder") or config.get("output_folder") or "Court Shiguan").strip().strip("/") or "Court Shiguan"
    max_files = max(1, min(int(payload.get("max_files") or 300), 2000))
    with tempfile.TemporaryDirectory(prefix="shiguan-obsidian-export-") as temp_dir:
        local_out = Path(temp_dir) / "Court Shiguan"
        exported = export_obsidian(str(local_out), False)
        files = [
            path
            for path in sorted(local_out.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".md", ".json", ".jsonl", ".txt"}
        ][:max_files]
        written = 0
        errors: list[str] = []
        for path in files:
            relative = path.relative_to(local_out).as_posix()
            target = f"{target_folder}/{relative}"
            try:
                obsidian_api_request(
                    f"/vault/{obsidian_path(target)}",
                    "PUT",
                    path.read_bytes(),
                    "text/plain; charset=utf-8",
                )
                written += 1
            except Exception as exc:
                errors.append(f"{relative}: {exc}")
        return {
            "local_export": exported,
            "target_folder": target_folder,
            "written": written,
            "errors": errors[:20],
            "truncated": len(files) >= max_files,
        }


def default_obsidian_vault_path() -> Path:
    config = obsidian_sync_config(False)
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH") or str(config.get("vault_path") or default_obsidian_cache_vault())).expanduser().resolve()


def obsidian_filesystem_sync(payload: dict[str, object] | None = None) -> dict[str, object]:
    payload = payload or {}
    vault = validate_local_content_root(
        Path(str(payload.get("vault_path") or default_obsidian_vault_path())).expanduser().resolve(),
        "Obsidian vault_path",
    )
    autosync_script = skill_root() / "scripts" / "shiguan_autosync_daemon.py"
    if not autosync_script.exists():
        raise ValueError(f"autosync script missing: {autosync_script}")
    base = read_obsidian_sync_config_snapshot()
    current = obsidian_sync_config(include_secret=True, stored_override=base)
    api_key = str(payload.get("api_key") or current.get("api_key") or "")
    verify_ssl = truthy(payload.get("verify_ssl")) if "verify_ssl" in payload else bool(current.get("verify_ssl", False))
    endpoint = validate_obsidian_endpoint(
        payload.get("endpoint") or current.get("endpoint") or "https://127.0.0.1:27124",
        verify_ssl,
    )
    watch_paths = validated_obsidian_watch_paths(
        [str(vault), str(default_obsidian_inbox())]
    )
    config = {
        "sync_mode": "filesystem_preserve_only",
        "auto_enabled": True,
        "autosync_enabled": True,
        "autosync_interval_seconds": bounded_int(payload.get("autosync_interval_seconds") or current.get("autosync_interval_seconds"), 20, 5, 3600),
        "vault_path": str(vault),
        "cache_vault_path": str(vault),
        "source_vault_path": str(payload.get("source_vault_path") or current.get("source_vault_path") or default_obsidian_shared_vault()),
        "parent_vault_path": str(payload.get("parent_vault_path") or current.get("parent_vault_path") or default_obsidian_parent_vault()),
        "watch_paths": watch_paths,
        "output_folder": str(payload.get("output_folder") or "Court Shiguan"),
        "autosync_script": str(autosync_script),
        "filesystem_sync_script": str(skill_root() / "scripts" / "sync_shiguan_obsidian_vault.py"),
        "shared_shiguan_root": str(references_root()),
        "endpoint": endpoint,
        "verify_ssl": verify_ssl,
        "api_key": api_key,
        "rest_api_note": "Independent autosync daemon is active. Obsidian Local REST API is optional for push/pull.",
    }
    config_result = patch_obsidian_sync_config(config, base_snapshot=base)
    if config_result.get("conflict"):
        raise ValueError("Obsidian 同步配置并发冲突：" + ", ".join(config_result.get("conflict_fields", [])))
    if not autosync_script.exists():
        raise ValueError(f"autosync script missing: {autosync_script}")
    timeout = bounded_int(payload.get("timeout_seconds"), 240, 30, 600)
    with tempfile.NamedTemporaryFile(prefix="shiguan-autosync-result-", suffix=".json", delete=False) as handle:
        result_path = Path(handle.name)
    try:
        proc = subprocess.run(
            [background_python(), str(autosync_script), "--once", "--result-json", str(result_path)],
            cwd=str(skill_root()),
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=timeout,
            **hidden_run_kwargs(),
        )
        if proc.returncode != 0:
            raise ValueError((proc.stderr or "autosync failed")[-1200:])
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("autosync returned non-JSON output") from exc
    finally:
        try:
            result_path.unlink()
        except OSError:
            pass
    return {
        "config": obsidian_sync_config(False),
        "config_transaction": {
            "revision": config_result.get("committed_revision"),
            "transaction_id": config_result.get("transaction_id"),
            "post_write_verified": config_result.get("post_write_verified"),
        },
        "autosync": result,
        "filesystem_sync": result.get("filesystem_sync", result),
    }


def role_allows(actual: str, required: str) -> bool:
    ranks = {"read": 1, "edit": 2}
    return ranks.get(actual, 0) >= ranks.get(required, 0)


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "permanent", "永久"}


def bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def verify_peer_access(headers, required_role: str) -> dict[str, object]:
    auth = headers.get("Authorization", "")
    prefix = "Bearer "
    token = auth[len(prefix):].strip() if auth.startswith(prefix) else headers.get("X-Shiguan-Token", "").strip()
    key_id = headers.get("X-Shiguan-Key-Id", "").strip()
    if not token or not key_id:
        raise PermissionError("缺少 peer 密钥")
    hashed = token_hash(token)
    for record in issued_keys():
        if str(record.get("key_id", "")) != key_id:
            continue
        if not hmac.compare_digest(str(record.get("token_hash", "")), hashed):
            continue
        if record.get("revoked_at"):
            raise PermissionError("密钥已吊销")
        if key_expired(record):
            raise PermissionError("密钥已过期")
        role = str(record.get("role", "read"))
        if not role_allows(role, required_role):
            raise PermissionError("密钥无编辑权限")
        return record
    raise PermissionError("密钥无效")


def _export_peer_key_with_snapshot(
    payload: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    role = str(payload.get("role") or "read").strip().lower()
    if role not in {"read", "edit"}:
        raise ValueError("role must be read or edit")
    permanent = truthy(payload.get("permanent"))
    days = bounded_int(payload.get("days"), 7, 1, 3650)
    share_host = str(payload.get("share_host") or first_share_host()).strip() or first_share_host()
    share_port = bounded_int(payload.get("share_port"), default_share_port(), 1, 65535)
    endpoint = str(payload.get("endpoint") or service_url(share_host, share_port)).strip()
    if not endpoint.endswith("/"):
        endpoint += "/"
    key_id = secrets.token_hex(PEER_KEY_ID_BYTES)
    token = secrets.token_urlsafe(PEER_KEY_TOKEN_BYTES)
    created_at = now_text()
    regenerate_from = str(payload.get("regenerate_from") or "").strip()
    expires_at = "" if permanent else datetime.fromtimestamp(datetime.now().timestamp() + days * 86400).isoformat(timespec="seconds")
    ttl_seconds = 0 if permanent else days * 86400
    clock = {
        "issued_at": created_at,
        "expires_at": expires_at,
        "server_time": created_at,
        "ttl_seconds": ttl_seconds,
        "pending_download_seconds": PEER_PENDING_DOWNLOAD_SECONDS,
        "renewal_authority": "sharing_server",
    }
    node = ensure_node_identity()
    key_payload = {
        "type": "shiguan_peer_key",
        "version": 2,
        "format": "SHIGUAN-PEER-KEY-v2",
        "decoder": "shiguan-tree-web",
        "encoding": f"caesar-{CAESAR_SHIFT}-base64-json",
        "role": role,
        "key_id": key_id,
        "token": token,
        "file_nonce": secrets.token_urlsafe(96),
        "file_guard": secrets.token_hex(64),
        "created_at": created_at,
        "expires_at": expires_at,
        "clock": clock,
        "endpoint": endpoint,
        "node": node,
        "note": str(payload.get("note") or ""),
        "regenerate_from": regenerate_from,
    }
    key_record = {
        "key_id": key_id,
        "role": role,
        "token_hash": token_hash(token),
        "created_at": created_at,
        "expires_at": expires_at,
        "clock": clock,
        "ttl_seconds": ttl_seconds,
        "permanent": permanent,
        "endpoint": endpoint,
        "revoked_at": "",
        "note": str(payload.get("note") or ""),
        "regenerate_from": regenerate_from,
    }

    def append_key(state: dict[str, object]) -> None:
        keys = state.get("issued_keys")
        if not isinstance(keys, list):
            raise PeerStateError("issued_keys state is invalid")
        keys.append(key_record)

    text = encode_peer_key(key_payload)
    file_name = f"shiguan-{role}-{key_id}.shiguan-key"
    result = {
        "key_id": key_id,
        "role": role,
        "expires_at": expires_at,
        "endpoint": endpoint,
        "filename": file_name,
        "key_text": text,
        "delivery": "browser_download",
        "warning": "凯撒算法仅作密钥文件包装；权限以各节点服务端验签、过期和吊销为准。",
    }
    remember_pending_key_download(result)
    try:
        committed, _ = update_peer_state(append_key)
    except Exception:
        with PENDING_KEY_DOWNLOADS_LOCK:
            PENDING_KEY_DOWNLOADS.pop(key_id, None)
        raise
    result["transaction"] = peer_transaction(committed)
    return result, committed


def export_peer_key(payload: dict[str, object]) -> dict[str, object]:
    result, _snapshot = _export_peer_key_with_snapshot(payload)
    return result


def generate_peer_key(payload: dict[str, object]) -> dict[str, object]:
    regenerate_from = str(payload.get("regenerate_from") or "").strip()
    revocation_transaction: dict[str, object] | None = None
    if regenerate_from:
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", regenerate_from):
            raise ValueError("regenerate_from is invalid")
        revoked_at = now_text()

        def revoke_predecessor(state: dict[str, object]) -> int:
            keys = state.get("issued_keys")
            if not isinstance(keys, list):
                raise PeerStateError("issued_keys state is invalid")
            predecessor = next(
                (record for record in keys if str(record.get("key_id") or "") == regenerate_from),
                None,
            )
            if not isinstance(predecessor, dict):
                raise ValueError("regenerate_from key does not exist")
            active_replacements = [
                record
                for record in keys
                if str(record.get("regenerate_from") or "") == regenerate_from
                if not record.get("revoked_at")
                if not key_expired(record)
            ]
            if active_replacements:
                raise ValueError("an active replacement already exists for regenerate_from")
            changed = 0
            if not predecessor.get("revoked_at"):
                predecessor["revoked_at"] = revoked_at
                predecessor["revoked_reason"] = "revoke_before_regenerate"
                predecessor["regeneration_requested_at"] = revoked_at
                predecessor["updated_at"] = revoked_at
                changed = 1
            return changed

        revoked_snapshot, _changed = update_peer_state(revoke_predecessor)
        predecessor = next(
            (
                record
                for record in issued_keys(revoked_snapshot)
                if str(record.get("key_id") or "") == regenerate_from
            ),
            None,
        )
        if not isinstance(predecessor, dict) or not predecessor.get("revoked_at"):
            raise PeerStateError("predecessor revocation was not durably verified")
        with PENDING_KEY_DOWNLOADS_LOCK:
            PENDING_KEY_DOWNLOADS.pop(regenerate_from, None)
        revocation_transaction = peer_transaction(revoked_snapshot)

    issue_payload = dict(payload)
    issue_payload["regenerate_from"] = regenerate_from
    result, snapshot = _export_peer_key_with_snapshot(issue_payload)
    key_id = str(result.get("key_id") or "")
    keys = issued_keys(snapshot)
    record = next((item for item in keys if str(item.get("key_id") or "") == key_id), {})
    response = {
        "key": public_issued_key(record, keys),
        "pending_downloads": pending_downloads(keys),
        "transaction": result.get("transaction"),
    }
    if revocation_transaction is not None:
        response["revocation_transaction"] = revocation_transaction
        response["regenerate_from"] = regenerate_from
    return response


def manage_key(payload: dict[str, object]) -> dict[str, object]:
    action = str(payload.get("action") or "").strip().lower()
    key_id = str(payload.get("key_id") or "").strip()
    if not key_id:
        raise ValueError("缺少 key_id")
    if action not in {"delete", "remove", "revoke", "renew", "extend", "permanent"}:
        raise ValueError("action must be renew, permanent, or revoke")

    def mutate(state: dict[str, object]) -> int:
        keys = state.get("issued_keys")
        if not isinstance(keys, list):
            raise PeerStateError("issued_keys state is invalid")
        changed = 0
        if action in {"delete", "remove", "revoke"}:
            changed_at = now_text()
            for record in keys:
                if str(record.get("key_id") or "") != key_id or record.get("revoked_at"):
                    continue
                record["revoked_at"] = changed_at
                record["revoked_reason"] = "operator_revoke"
                record["updated_at"] = changed_at
                changed += 1
        elif action in {"renew", "extend", "permanent"}:
            permanent = action == "permanent" or truthy(payload.get("permanent"))
            days = bounded_int(payload.get("days"), 7, 1, 3650)
            updated_at = now_text()
            expires_at = "" if permanent else (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
            ttl_seconds = 0 if permanent else days * 86400
            for record in keys:
                if str(record.get("key_id") or "") != key_id or record.get("revoked_at"):
                    continue
                record["expires_at"] = expires_at
                record["ttl_seconds"] = ttl_seconds
                record["permanent"] = permanent
                clock = record.get("clock") if isinstance(record.get("clock"), dict) else {}
                clock.update({
                    "expires_at": expires_at,
                    "server_time": updated_at,
                    "ttl_seconds": ttl_seconds,
                    "pending_download_seconds": PEER_PENDING_DOWNLOAD_SECONDS,
                    "renewal_authority": "sharing_server",
                })
                if not clock.get("issued_at"):
                    clock["issued_at"] = str(record.get("created_at") or updated_at)
                record["clock"] = clock
                record["updated_at"] = updated_at
                changed += 1
        return changed

    committed, changed = update_peer_state(mutate)
    keys = issued_keys(committed)
    if action in {"delete", "remove", "revoke"}:
        with PENDING_KEY_DOWNLOADS_LOCK:
            PENDING_KEY_DOWNLOADS.pop(key_id, None)
    return {
        "changed": changed,
        "issued_keys": [public_issued_key(record, keys) for record in keys],
        "pending_downloads": pending_downloads(keys),
        "transaction": peer_transaction(committed),
    }


def import_peer_key(payload: dict[str, object]) -> dict[str, object]:
    key_text = str(payload.get("key_text") or "")
    if not key_text:
        raise ValueError("请在网页中选择 .shiguan-key 密钥文件导入")
    value = decode_peer_key(key_text)
    node = value.get("node") if isinstance(value.get("node"), dict) else {}
    key_id = str(value.get("key_id") or "")
    peer_id = f"{node.get('node_id', 'unknown')}:{key_id}"
    record = {
        "peer_id": peer_id,
        "key_id": key_id,
        "role": str(value.get("role") or "read"),
        "token": str(value.get("token") or ""),
        "endpoint": str(value.get("endpoint") or ""),
        "node": node,
        "created_at": str(value.get("created_at") or ""),
        "expires_at": str(value.get("expires_at") or ""),
        "clock": value.get("clock") if isinstance(value.get("clock"), dict) else {},
        "imported_at": now_text(),
        "disabled": False,
    }
    if not record["key_id"] or not record["token"] or not record["endpoint"]:
        raise ValueError("密钥缺少 key_id、token 或 endpoint")
    def import_peer(state: dict[str, object]) -> None:
        current = state.get("imported_peers")
        if not isinstance(current, list):
            raise PeerStateError("imported_peers state is invalid")
        peers = [peer for peer in current if str(peer.get("peer_id")) != peer_id]
        peers.append(record)
        state["imported_peers"] = peers

    committed, _ = update_peer_state(import_peer)
    result = public_peer(record)
    result["transaction"] = peer_transaction(committed)
    return result


def expire_key(payload: dict[str, object]) -> dict[str, object]:
    key_id = str(payload.get("key_id") or "").strip()
    peer_id = str(payload.get("peer_id") or "").strip()
    changed_at = now_text()

    def expire(state: dict[str, object]) -> int:
        changed = 0
        keys = state.get("issued_keys")
        peers = state.get("imported_peers")
        if not isinstance(keys, list) or not isinstance(peers, list):
            raise PeerStateError("peer state records are invalid")
        if key_id:
            for record in keys:
                if str(record.get("key_id", "")) == key_id and not record.get("revoked_at"):
                    record["revoked_at"] = changed_at
                    changed += 1
        if peer_id:
            for peer in peers:
                if str(peer.get("peer_id", "")) == peer_id and not peer.get("disabled"):
                    peer["disabled"] = True
                    peer["disabled_at"] = changed_at
                    changed += 1
        if not key_id and not peer_id:
            for record in keys:
                if key_expired(record) and not record.get("revoked_at"):
                    record["revoked_at"] = changed_at
                    changed += 1
        return changed

    committed, changed = update_peer_state(expire)
    if key_id:
        with PENDING_KEY_DOWNLOADS_LOCK:
            PENDING_KEY_DOWNLOADS.pop(key_id, None)
    return {"changed": changed, "transaction": peer_transaction(committed)}


def ping_peer(peer: dict[str, object]) -> dict[str, object]:
    peer_public = public_peer(peer)
    peer_public["checked_at"] = now_text()
    if peer.get("disabled"):
        peer_public["status"] = "disabled"
        return peer_public
    try:
        data = call_peer(peer, "/api/peer/ping")
        peer_public["status"] = "online"
        peer_public["count"] = data.get("count", 0)
        peer_public["server_time"] = data.get("server_time", "")
        if isinstance(data.get("node"), dict):
            peer_public.update(public_peer({"node": data["node"]}))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        peer_public["status"] = "offline"
        peer_public["error"] = str(exc)
    return peer_public


def check_peer_statuses(peers: list[dict[str, object]] | None = None) -> list[dict[str, object]]:
    return [ping_peer(peer) for peer in (imported_peers() if peers is None else peers)]


def peer_headers(peer: dict[str, object]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {peer.get('token', '')}",
        "X-Shiguan-Key-Id": str(peer.get("key_id") or ""),
        ADMIN_REQUEST_HEADER: "1",
        "Content-Type": "application/json",
    }


def call_peer(peer: dict[str, object], path: str, method: str = "GET", payload: dict[str, object] | None = None) -> dict[str, object]:
    endpoint = str(peer.get("endpoint") or "").rstrip("/")
    if not endpoint:
        raise ValueError("peer endpoint missing")
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint + path, data=data, headers=peer_headers(peer), method=method)
    with urlopen(request, timeout=PEER_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8")
    value = json.loads(raw or "{}")
    return value if isinstance(value, dict) else {}


def peer_display_name(peer: dict[str, object]) -> str:
    node = peer.get("node") if isinstance(peer.get("node"), dict) else {}
    return str(node.get("node_name") or node.get("node_id") or peer.get("peer_id") or "共享史馆")


def peer_machine_keywords(peer: dict[str, object]) -> list[str]:
    name = peer_display_name(peer)
    node = peer.get("node") if isinstance(peer.get("node"), dict) else {}
    node_id = str(node.get("node_id") or "").strip()
    machine_uid = str(node.get("machine_uid") or node_id).strip()
    return unique(
        [
            name,
            f"机器:{name}",
            f"机器码:{machine_uid}",
            f"机器码:{node_id}" if node_id and node_id != machine_uid else "",
            node_id,
        ],
        8,
    )


def fetch_peer_entries(
    query: str,
    limit: int,
    selected_peer_id: str = "",
    ui_collapsed: bool = False,
    peers: list[dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    entries: list[dict[str, object]] = []
    statuses: list[dict[str, object]] = []
    for peer in (imported_peers() if peers is None else peers):
        peer_public = public_peer(peer)
        if peer.get("disabled"):
            peer_public["status"] = "disabled"
            peer_public["checked_at"] = now_text()
            statuses.append(peer_public)
            continue
        if selected_peer_id and str(peer.get("peer_id")) != selected_peer_id:
            peer_public = ping_peer(peer)
            if peer_public.get("status") == "online":
                peer_public["status_detail"] = "collapsed"
            statuses.append(peer_public)
            continue
        if ui_collapsed and not selected_peer_id:
            peer_public = ping_peer(peer)
            if peer_public.get("status") == "online":
                peer_public["status_detail"] = "collapsed"
            statuses.append(peer_public)
            continue
        try:
            params = urlencode({"q": query, "limit": str(max(1, min(limit, 120)))})
            data = call_peer(peer, f"/api/peer/state?{params}")
            machine_keywords = peer_machine_keywords(peer)
            machine_name = peer_display_name(peer)
            node = peer.get("node") if isinstance(peer.get("node"), dict) else {}
            machine_uid = str(node.get("machine_uid") or node.get("node_id") or "").strip()
            for entry in data.get("entries", []) if isinstance(data.get("entries"), list) else []:
                if isinstance(entry, dict):
                    entry = dict(entry)
                    entry["id"] = f"{peer.get('peer_id')}::{entry.get('id', '')}"
                    entry["origin_id"] = str(entry.get("origin_id") or entry.get("id", "")).split("::")[-1]
                    entry["peer_id"] = peer.get("peer_id")
                    entry["peer_role"] = peer.get("role")
                    entry["peer_endpoint"] = peer.get("endpoint")
                    entry["peer_machine_name"] = machine_name
                    entry["peer_machine_uid"] = machine_uid
                    entry["read_only"] = str(peer.get("role")) != "edit"
                    entry["keywords"] = unique(split_terms(entry.get("keywords")) + machine_keywords, 36)
                    entry["keywords_zh"] = unique(split_terms(entry.get("keywords_zh")) + machine_keywords, 36)
                    entries.append(entry)
            peer_public["status"] = "online"
            peer_public["shown"] = data.get("shown", len(entries))
            peer_public["count"] = data.get("count", 0)
            peer_public["checked_at"] = now_text()
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            peer_public["status"] = "offline"
            peer_public["error"] = str(exc)
            peer_public["checked_at"] = now_text()
        statuses.append(peer_public)
    return entries, statuses


def save_peer_entry(payload: dict[str, object]) -> dict[str, object]:
    peer_id = str(payload.get("peer_id") or "").strip()
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        raise ValueError("entry must be an object")
    for peer in imported_peers():
        if str(peer.get("peer_id")) != peer_id:
            continue
        if peer.get("disabled"):
            raise PermissionError("peer 密钥不可用")
        if str(peer.get("role")) != "edit":
            raise PermissionError("普通密钥只读；需要编辑密钥")
        entry = dict(entry)
        if entry.get("origin_id"):
            entry["id"] = str(entry.get("origin_id"))
        elif "::" in str(entry.get("id", "")):
            entry["id"] = str(entry.get("id")).split("::", 1)[1]
        for key in (
            "peer_id",
            "peer_role",
            "peer_endpoint",
            "peer_machine_name",
            "peer_machine_uid",
            "read_only",
            "origin_id",
        ):
            entry.pop(key, None)
        return call_peer(peer, "/api/peer/entry", method="POST", payload=entry)
    raise ValueError("peer not found")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta, parts[2].strip()


def obsidian_entry(relative_path: str, text: str) -> dict[str, object]:
    meta, body = parse_frontmatter(text)
    title = meta.get("title") or Path(relative_path).stem
    tags = meta.get("tags") or meta.get("keywords") or ""
    material = f"obsidian|{relative_path}|{hashlib.sha1(text.encode('utf-8')).hexdigest()}"
    entry = {
        "id": hashlib.sha1(material.encode("utf-8")).hexdigest()[:16],
        "record_type": "obsidian_note",
        "topic": title,
        "phase": "Obsidian导入",
        "status": meta.get("status") or "DONE",
        "time": meta.get("time") or meta.get("date") or now_text(),
        "keywords": split_terms(tags),
        "key_actions": ["obsidian-import"],
        "summary": body[:4000],
        "evidence": f"obsidian:{relative_path}",
        "next": "",
        "memory_decision": meta.get("memory_decision") or "DEFERRED",
        "risk_level": meta.get("risk_level") or "",
        "knowledge_value": meta.get("knowledge_value") or "",
        "priority_level": meta.get("priority_level") or "",
        "memory_content": "",
        "memory_reason": "",
        "source": f"obsidian:{relative_path}",
    }
    entry["keywords"] = derive_keywords(entry)
    enrich_entry(entry)
    return entry


def checked_import_text(name: str, data: bytes, total_bytes: int) -> tuple[str, int]:
    size = len(data)
    if size > MAX_OBSIDIAN_IMPORT_FILE_BYTES:
        raise ValueError(f"导入文件超过单文件上限：{Path(name).name}")
    total = total_bytes + size
    if total > MAX_OBSIDIAN_IMPORT_TOTAL_BYTES:
        raise ValueError("导入内容超过总大小上限")
    return data.decode("utf-8", errors="replace"), total


def load_obsidian_files(source: Path) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    total_bytes = 0
    if source.is_dir():
        for path in source.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            if any(part.startswith(".") for part in path.relative_to(source).parts):
                continue
            if len(files) >= MAX_OBSIDIAN_IMPORT_FILES:
                raise ValueError("导入文件数量超过上限")
            relative = str(path.relative_to(source)).replace("\\", "/")
            if path.stat().st_size > MAX_OBSIDIAN_IMPORT_FILE_BYTES:
                raise ValueError(f"导入文件超过单文件上限：{Path(relative).name}")
            text, total_bytes = checked_import_text(relative, path.read_bytes(), total_bytes)
            files.append({"filename": Path(relative).name, "text": text, "source": f"obsidian-path:{relative}"})
        return files
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            candidates = [
                item for item in archive.infolist()
                if item.filename.lower().endswith((".md", ".txt"))
                and "/." not in item.filename
                and not item.filename.startswith(".")
                and not item.is_dir()
            ]
            if len(candidates) > MAX_OBSIDIAN_IMPORT_FILES:
                raise ValueError("导入压缩包文件数量超过上限")
            oversized = next(
                (item for item in candidates if max(0, int(item.file_size)) > MAX_OBSIDIAN_IMPORT_FILE_BYTES),
                None,
            )
            if oversized is not None:
                raise ValueError(f"导入文件超过单文件上限：{Path(oversized.filename).name}")
            if sum(max(0, int(item.file_size)) for item in candidates) > MAX_OBSIDIAN_IMPORT_TOTAL_BYTES:
                raise ValueError("导入压缩包解压总量超过上限")
            for item in candidates:
                name = item.filename
                if not name.lower().endswith((".md", ".txt")) or "/." in name or name.startswith("."):
                    continue
                text, total_bytes = checked_import_text(name, archive.read(item), total_bytes)
                files.append({"filename": Path(name).name, "text": text, "source": f"obsidian-zip:{name}"})
        return files
    if source.is_file() and source.suffix.lower() in {".md", ".txt"}:
        if source.stat().st_size > MAX_OBSIDIAN_IMPORT_FILE_BYTES:
            raise ValueError(f"导入文件超过单文件上限：{source.name}")
        text, _ = checked_import_text(source.name, source.read_bytes(), 0)
        files.append({"filename": source.name, "text": text, "source": f"obsidian-path:{source.name}"})
        return files
    raise ValueError("只支持 Obsidian 目录、.zip、.md 或 .txt 文件")


def load_obsidian_entries(source: Path) -> list[dict[str, object]]:
    return [obsidian_entry(item["source"], item["text"]) for item in load_obsidian_files(source)]


def import_obsidian(payload: dict[str, object]) -> dict[str, object]:
    source_text = str(payload.get("path") or "").strip()
    if not source_text:
        raise ValueError("缺少 Obsidian 路径")
    source = validate_local_content_root(
        Path(source_text).expanduser().resolve(),
        "Obsidian import path",
    )
    files = load_obsidian_files(source)
    entries = [obsidian_entry(item["source"], item["text"]) for item in files]
    existing_ids = {str(entry.get("id")) for entry in load_entries()}
    new_entries = [entry for entry in entries if str(entry.get("id")) not in existing_ids]
    update_entries = [entry for entry in entries if str(entry.get("id")) in existing_ids]
    preview = {
        "source": str(source),
        "found": len(entries),
        "new": len(new_entries),
        "updates": len(update_entries),
        "samples": [
            {
                "id": entry.get("id"),
                "topic": entry.get("topic"),
                "source": entry.get("source"),
            }
            for entry in entries[:8]
        ],
    }
    queued = queue_import_text({"files": files, "source_prefix": "obsidian-path"})
    preview["commit_requested"] = bool(payload.get("commit"))
    preview["committed"] = False
    preview["status"] = "pending_review"
    preview["policy"] = "all Obsidian imports enter shiguan-imports/pending before 三省会审 and 门下复核"
    preview["queue"] = queued
    return preview


def queue_import_text(payload: dict[str, object]) -> dict[str, object]:
    files = payload.get("files")
    if not isinstance(files, list):
        files = [
            {
                "filename": str(payload.get("filename") or "import.md"),
                "text": str(payload.get("text") or ""),
            }
        ]
    pending_root = import_pending_root()
    pending_root.mkdir(parents=True, exist_ok=True)
    imported: list[dict[str, object]] = []
    duplicates: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for item in files:
        if not isinstance(item, dict):
            skipped.append({"reason": "文件载荷不是对象"})
            continue
        filename = Path(str(item.get("filename") or "import.md")).name
        suffix = Path(filename).suffix.lower()
        text = str(item.get("text") or "")
        if suffix not in {".md", ".txt"}:
            skipped.append({"filename": filename, "reason": "只支持 .md 或 .txt"})
            continue
        if not text.strip():
            skipped.append({"filename": filename, "reason": "文件为空"})
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        import_id = hashlib.sha1(f"codex-import|{filename}|{digest}".encode("utf-8")).hexdigest()[:20]
        path = pending_root / f"{import_id}.json"
        source_prefix = str(payload.get("source_prefix") or "browser-upload").strip() or "browser-upload"
        item_source = str(item.get("source") or "").strip()
        record = {
            "id": import_id,
            "filename": filename,
            "source_type": suffix.lstrip("."),
            "status": "pending",
            "imported_at": now_text(),
            "char_count": len(text),
            "estimated_tokens": estimate_tokens(text),
            "sha256": digest,
            "suggested_processor": "codex",
            "source": item_source or f"{source_prefix}:{filename}",
            "text": text,
        }
        metadata = {
            key: record[key]
            for key in (
                "id",
                "filename",
                "source_type",
                "status",
                "imported_at",
                "char_count",
                "estimated_tokens",
                "sha256",
                "suggested_processor",
            )
        }
        metadata_path = pending_import_metadata_path(path)
        public = public_pending_import(record)
        if path.exists():
            existing_metadata = read_json_file(metadata_path, {})
            if (
                not isinstance(existing_metadata, dict)
                or "text" in existing_metadata
                or "raw_text" in existing_metadata
                or any(existing_metadata.get(key) != value for key, value in metadata.items())
            ):
                write_json_file(metadata_path, metadata)
            duplicates.append(public)
            continue
        # The body is durable first; the metadata sidecar is the commit marker
        # for metadata-only queue inspection. A duplicate retry repairs a
        # missing or invalid sidecar without opening the pending body.
        write_json_file(path, record)
        write_json_file(metadata_path, metadata)
        imported.append(public)
    summary = import_queue_summary()
    return {
        "imported": imported,
        "duplicates": duplicates,
        "skipped": skipped,
        "new": len(imported),
        "duplicate_count": len(duplicates),
        "skipped_count": len(skipped),
        "queue": summary,
    }


def _upsert_entry_unlocked(payload: dict[str, object]) -> dict[str, object]:
    entries = load_entries()
    entry_id = str(payload.get("id") or "").strip()
    now = datetime.now().isoformat(timespec="seconds")
    source = str(payload.get("source") or "").strip()
    entry: dict[str, object] = {
        "id": entry_id,
        "record_type": str(payload.get("record_type") or "manual_note"),
        "topic": str(payload.get("topic") or "manual"),
        "phase": str(payload.get("phase") or "手动修订"),
        "status": str(payload.get("status") or "DRAFT"),
        "time": str(payload.get("time") or now),
        "keywords": split_terms(payload.get("keywords")),
        "key_actions": split_terms(payload.get("key_actions")),
        "summary": str(payload.get("summary") or ""),
        "evidence": str(payload.get("evidence") or "local shiguan web"),
        "next": str(payload.get("next") or ""),
        "memory_decision": str(payload.get("memory_decision") or "DEFERRED"),
        "risk_level": str(payload.get("risk_level") or ""),
        "knowledge_value": str(payload.get("knowledge_value") or ""),
        "priority_level": str(payload.get("priority_level") or ""),
        "memory_content": str(payload.get("memory_content") or ""),
        "memory_reason": str(payload.get("memory_reason") or ""),
        "source": source,
    }
    if source and not source.startswith("references/shiguan-tree/manual/"):
        entry["origin_source"] = source
    entry["keywords"] = derive_keywords(entry)
    if not entry["key_actions"]:
        entry["key_actions"] = [
            f"phase:{entry['phase']}",
            f"status:{entry['status']}",
            f"memory:{entry['memory_decision']}",
        ]
    enrich_entry(entry)
    if not entry_id:
        entry["id"] = stable_id(entry)
        entry["source"] = f"references/shiguan-tree/manual/{entry['id']}.json"
        enrich_entry(entry)
        entries.append(entry)
    else:
        entry["source"] = f"references/shiguan-tree/manual/{entry_id}.json"
        enrich_entry(entry)
        updated = False
        for index, existing in enumerate(entries):
            if str(existing.get("id", "")) == entry_id:
                entries[index] = entry
                updated = True
                break
        if not updated:
            entries.append(entry)
    write_manual_entry(entry)
    write_entries(entries)
    refresh_tree()
    return entry


def upsert_entry(payload: dict[str, object]) -> dict[str, object]:
    with file_lock(shiguan_write_lock_path(), timeout=15.0):
        return _upsert_entry_unlocked(payload)


class Handler(SimpleHTTPRequestHandler):
    server_version = "ShiguanTree/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def client_is_local(self) -> bool:
        host = self.client_address[0] if self.client_address else ""
        return client_is_local(str(host))

    def request_host_allowed(self) -> bool:
        return request_host_allowed(self.headers.get("Host", ""))

    def admin_token_valid(self) -> bool:
        token = os.environ.get(ADMIN_TOKEN_ENV, "")
        if not token:
            return False
        supplied = self.headers.get("X-Shiguan-Admin-Token", "")
        return bool(supplied) and hmac.compare_digest(str(supplied), str(token))

    def admin_reader(self) -> bool:
        return self.client_is_local() or self.admin_token_valid()

    def require_admin(self) -> None:
        if not self.request_host_allowed():
            raise PermissionError("请求 Host 不在本机史馆允许列表")
        if self.client_is_local():
            return
        if not os.environ.get(ADMIN_TOKEN_ENV, ""):
            raise PermissionError(f"局域网管理操作需要在服务端设置 {ADMIN_TOKEN_ENV}")
        if not self.admin_token_valid():
            raise PermissionError("局域网管理令牌无效")

    def require_json_write(self) -> None:
        if not self.request_host_allowed():
            raise PermissionError("请求 Host 不在本机史馆允许列表")
        if self.headers.get(ADMIN_REQUEST_HEADER, "") != "1":
            raise PermissionError(f"管理写请求必须显式设置 {ADMIN_REQUEST_HEADER}: 1")
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise PermissionError("管理写请求必须使用 application/json")
        origin = self.headers.get("Origin", "").strip()
        if origin and not origin_matches_host(origin, self.headers.get("Host", "")):
            raise PermissionError("跨源管理写请求被拒绝")
        fetch_site = self.headers.get("Sec-Fetch-Site", "").strip().lower()
        if fetch_site in {"cross-site", "same-site"} and origin:
            raise PermissionError("非同源浏览器管理写请求被拒绝")

    def require_admin_write(self) -> None:
        self.require_json_write()
        if not self.client_is_local() and not self.admin_token_valid():
            raise PermissionError("局域网管理写请求缺少有效管理令牌")

    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        super().end_headers()

    def send_safe_error(self, status: int, message: str, code: str = "ERROR") -> None:
        self.send_json({"error": message, "code": code}, status=status)

    def send_json(self, value: object, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_key_file(self, filename: str, text: str) -> None:
        body = text.encode("utf-8")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", filename) or "shiguan-peer-key.shiguan-key"
        self.send_response(200)
        self.send_header("Content-Type", "application/x-shiguan-key; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0:
            raise ValueError("Content-Length 不能为负数")
        if length > MAX_JSON_BODY_BYTES:
            raise ValueError(f"JSON 请求体超过上限 {MAX_JSON_BODY_BYTES} bytes")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if not self.request_host_allowed():
            self.send_safe_error(403, "请求 Host 不在本机史馆允许列表", "HOST_NOT_ALLOWED")
            return
        if parsed.path == "/api/key/export-file":
            try:
                self.require_admin()
                params = parse_qs(parsed.query)
                with file_lock(peer_state_lock_path(), timeout=15.0):
                    snapshot_keys = issued_keys(peer_state_snapshot())
                    pending = download_pending_key(
                        params.get("key_id", [""])[0],
                        params.get("download_nonce", [""])[0],
                        snapshot_keys,
                    )
                key_id = str(pending.get("key_id") or "")
                try:
                    self.send_key_file(str(pending["filename"]), str(pending["key_text"]))
                except BaseException:
                    mark_pending_key_delivery(key_id, delivered=False)
                    raise
                else:
                    mark_pending_key_delivery(key_id, delivered=True)
            except ValueError as exc:
                self.send_safe_error(404, str(exc), "NOT_FOUND")
            except PermissionError as exc:
                self.send_safe_error(403, str(exc), "ADMIN_AUTH_REQUIRED")
            except Exception:
                self.send_safe_error(500, "导出共享密钥失败；详细信息仅保留在本机服务日志。", "KEY_EXPORT_FAILED")
            return
        if parsed.path == "/api/health":
            self.send_json(public_health_projection(SERVER_PORT))
            return
        if parsed.path == "/api/health/private":
            try:
                self.require_admin()
                self.send_json(
                    {
                        **public_health_projection(SERVER_PORT),
                        "shared_shiguan_root": str(references_root()),
                        "tree_root": str(tree_root()),
                        "index_path": str(index_path()),
                        "web_root": str(web_root()),
                        "bind_host": SERVER_BIND_HOST,
                    }
                )
            except PermissionError as exc:
                self.send_safe_error(403, str(exc), "ADMIN_AUTH_REQUIRED")
            return
        if parsed.path == "/api/state":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            limit = bounded_int(params.get("limit", ["50"])[0], 50, 1, PUBLIC_STATE_LIMIT)
            if not self.admin_reader():
                self.send_json(public_state_projection(query, limit, SERVER_PORT))
                return
            selected_peer_id = params.get("peer_id", [""])[0]
            ui_collapsed = params.get("ui_collapsed", ["0"])[0] in {"1", "true", "yes"}
            entries = select_entries(query, limit)
            try:
                peer_snapshot = peer_state_snapshot()
            except PeerStateError:
                self.send_safe_error(500, "Peer 状态不可用；请在本机检查 canonical peer-state。", "PEER_STATE_INVALID")
                return
            snapshot_keys = issued_keys(peer_snapshot)
            snapshot_peers = imported_peers(peer_snapshot)
            peer_entries, peer_statuses = fetch_peer_entries(
                query,
                max(10, limit // 2),
                selected_peer_id,
                ui_collapsed,
                snapshot_peers,
            )
            merged_entries = entries + peer_entries
            self.send_json(
                {
                    "entries": merged_entries,
                    "count": len(load_entries()),
                    "local_count": len(load_entries()),
                    "peer_count": len(peer_entries),
                    "shown": len(entries),
                    "shown_total": len(merged_entries),
                    "knowledge_graph": load_knowledge_graph(),
                    "shared_shiguan_root": str(references_root()),
                    "tree_root": str(tree_root()),
                    "index_path": str(index_path()),
                    "web_root": str(web_root()),
                    "bind_host": SERVER_BIND_HOST,
                    "port": SERVER_PORT,
                    "local_url": service_url("127.0.0.1", SERVER_PORT),
                    "lan_urls": lan_urls(SERVER_BIND_HOST, SERVER_PORT),
                    "default_share_host": first_share_host(),
                    "default_share_port": default_share_port(),
                    "default_share_endpoint": default_share_endpoint(),
                    "node": read_node_identity(),
                    "peers": peer_statuses,
                    "peer_state_transaction": peer_transaction(peer_snapshot),
                    "agent_presence": agent_presence_statuses(),
                    "issued_keys": [
                        public_issued_key(record, snapshot_keys)
                        for record in snapshot_keys
                    ],
                    "pending_downloads": pending_downloads(snapshot_keys),
                    "import_queue": import_queue_summary(),
                    "obsidian_sync": obsidian_sync_public_state(),
                    "admin_auth": admin_auth_public_state(),
                }
            )
            return
        if parsed.path == "/api/agent-presence":
            try:
                self.require_admin()
                self.send_json({"agents": agent_presence_statuses()})
            except PermissionError as exc:
                self.send_safe_error(403, str(exc), "ADMIN_AUTH_REQUIRED")
            return
        if parsed.path == "/api/import-queue":
            try:
                self.require_admin()
                self.send_json(import_queue_summary())
            except PermissionError as exc:
                self.send_safe_error(403, str(exc), "ADMIN_AUTH_REQUIRED")
            return
        if parsed.path == "/api/keys":
            try:
                self.require_admin()
            except PermissionError as exc:
                self.send_safe_error(403, str(exc), "ADMIN_AUTH_REQUIRED")
                return
            try:
                peer_snapshot = peer_state_snapshot()
            except PeerStateError:
                self.send_safe_error(500, "Peer 状态不可用；请在本机检查 canonical peer-state。", "PEER_STATE_INVALID")
                return
            snapshot_keys = issued_keys(peer_snapshot)
            snapshot_peers = imported_peers(peer_snapshot)
            self.send_json(
                {
                    "node": read_node_identity(),
                    "default_share_host": first_share_host(),
                    "default_share_port": default_share_port(),
                    "default_share_endpoint": default_share_endpoint(),
                    "peers": check_peer_statuses(snapshot_peers),
                    "peer_state_transaction": peer_transaction(peer_snapshot),
                    "issued_keys": [
                        public_issued_key(record, snapshot_keys)
                        for record in snapshot_keys
                    ],
                    "pending_downloads": pending_downloads(snapshot_keys),
                }
            )
            return
        if parsed.path == "/api/obsidian-sync/status":
            try:
                self.require_admin()
            except PermissionError as exc:
                self.send_safe_error(403, str(exc), "ADMIN_AUTH_REQUIRED")
                return
            self.send_json(obsidian_sync_status())
            return
        if parsed.path == "/api/peer/ping":
            try:
                verify_peer_access(self.headers, "read")
                self.send_json(
                    {
                        "ok": True,
                        "node": read_node_identity(),
                        "server_time": now_text(),
                        "count": len(load_entries()),
                    }
                )
            except PermissionError as exc:
                self.send_safe_error(403, str(exc), "PEER_AUTH_REQUIRED")
            return
        if parsed.path == "/api/peer/state":
            try:
                verify_peer_access(self.headers, "read")
                params = parse_qs(parsed.query)
                query = params.get("q", [""])[0]
                limit = bounded_int(params.get("limit", ["50"])[0], 50, 1, PUBLIC_STATE_LIMIT)
                entries = select_entries(query, limit)
                self.send_json(
                    {
                        "entries": entries,
                        "count": len(load_entries()),
                        "shown": len(entries),
                        "node": read_node_identity(),
                    }
                )
            except PermissionError as exc:
                self.send_safe_error(403, str(exc), "PEER_AUTH_REQUIRED")
            return

        path_text = parsed.path.lstrip("/") or "index.html"
        target = (web_root() / path_text).resolve()
        root = web_root().resolve()
        if root not in target.parents and target != root:
            self.send_error(403)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            if path in ADMIN_POST_PATHS:
                self.require_admin_write()
            elif path == "/api/peer/entry":
                self.require_json_write()
            elif path.startswith("/api/"):
                self.require_json_write()
            if self.path == "/api/security-check":
                self.send_json({"ok": True, "write_gate": "passed"})
                return
            if self.path == "/api/entry":
                self.require_admin()
                self.send_json({"entry": upsert_entry(self.read_json())})
                return
            if self.path == "/api/peer/entry":
                verify_peer_access(self.headers, "edit")
                self.send_json({"entry": upsert_entry(self.read_json())})
                return
            if self.path == "/api/rebuild":
                self.require_admin()
                self.send_json({"entries": rebuild_index(), "status": "rebuilt"})
                return
            if self.path == "/api/grow":
                self.require_admin()
                refresh_tree()
                self.send_json({"status": "grown", "tree_root": str(tree_root())})
                return
            if self.path == "/api/export":
                self.require_admin()
                payload = self.read_json()
                result = export_obsidian(
                    str(payload.get("out") or ""),
                    bool(payload.get("zip", True)),
                )
                self.send_json(result, status=200 if not result["errors"] else 422)
                return
            if self.path == "/api/import-obsidian":
                self.require_admin()
                self.send_json(import_obsidian(self.read_json()))
                return
            if self.path == "/api/import-text":
                self.require_admin()
                self.send_json(queue_import_text(self.read_json()))
                return
            if self.path == "/api/obsidian-sync/config":
                self.require_admin()
                self.send_json({"config": save_obsidian_sync_config(self.read_json())})
                return
            if self.path == "/api/obsidian-sync/preview":
                self.require_admin()
                self.send_json(obsidian_sync_preview(self.read_json()))
                return
            if self.path == "/api/obsidian-sync/import":
                self.require_admin()
                self.send_json(obsidian_sync_import(self.read_json()))
                return
            if self.path == "/api/obsidian-sync/export":
                self.require_admin()
                self.send_json(obsidian_sync_export(self.read_json()))
                return
            if self.path == "/api/obsidian-sync/filesystem":
                self.require_admin()
                self.send_json(obsidian_filesystem_sync(self.read_json()))
                return
            if self.path == "/api/key/generate":
                self.require_admin()
                self.send_json(generate_peer_key(self.read_json()))
                return
            if self.path == "/api/key/export":
                self.require_admin()
                self.send_json(export_peer_key(self.read_json()))
                return
            if self.path == "/api/key/import":
                self.require_admin()
                self.send_json({"peer": import_peer_key(self.read_json())})
                return
            if self.path == "/api/key/manage":
                self.require_admin()
                self.send_json(manage_key(self.read_json()))
                return
            if self.path == "/api/key/expire":
                self.require_admin()
                self.send_json(expire_key(self.read_json()))
                return
            if self.path == "/api/peer/save":
                self.require_admin()
                self.send_json(save_peer_entry(self.read_json()))
                return
            self.send_error(404)
        except PermissionError as exc:
            self.send_safe_error(403, str(exc), "AUTH_REQUIRED")
        except ValueError as exc:
            self.send_safe_error(400, str(exc), "BAD_REQUEST")
        except Exception:
            self.send_safe_error(500, "管理操作失败；详细信息仅保留在本机服务日志。", "SERVER_ERROR")

    def do_OPTIONS(self) -> None:
        self.send_safe_error(403, "跨源预检未获授权", "CORS_PREFLIGHT_REJECTED")


class SingleBindThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    allow_reuse_port = False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    global SERVER_BIND_HOST, SERVER_PORT
    SERVER_BIND_HOST = args.host
    SERVER_PORT = args.port

    ensure_shared_seed()
    try:
        lock_handle = acquire_server_lock(args.port)
    except RuntimeError as exc:
        print(f"SHIGUAN_TREE_WEB_ALREADY_RUNNING {exc}", file=sys.stderr)
        return 0
    try:
        web_root().mkdir(parents=True, exist_ok=True)
        rebuild_index()
        server = SingleBindThreadingHTTPServer((args.host, args.port), Handler)
        print(f"SHIGUAN_TREE_WEB {service_url('127.0.0.1', args.port)}")
        for url in lan_urls(args.host, args.port):
            print(f"SHIGUAN_TREE_WEB_LAN {url}")
        print(f"SHIGUAN_TREE_WEB_PATH {web_root() / 'index.html'}")
        try:
            server.serve_forever()
        finally:
            server.server_close()
    except KeyboardInterrupt:
        return 0
    finally:
        lock_handle.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
