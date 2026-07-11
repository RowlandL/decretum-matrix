#!/usr/bin/env python3
"""Bridge Codex/Hermes built-in memory state into Shiguan.

Default behavior is metadata-only. It records configuration state, file hashes,
sizes, timestamps, and SQLite table counts without copying raw memory bodies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys

sys.dont_write_bytecode = True
from pathlib import Path
from typing import Any

from court_platform import user_data_base

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ expected.
    tomllib = None  # type: ignore[assignment]


MISSING = object()
HERMES_MEMORY_KEYS = frozenset(
    {
        "memory_enabled",
        "user_profile_enabled",
        "write_approval",
        "memory_char_limit",
        "user_char_limit",
        "provider",
    }
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def user_home() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("USERPROFILE") or Path.home())
    return Path(os.environ.get("HOME") or Path.home())


def iso_mtime(path: Path) -> str | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def sha256_file(path: Path, *, limit_bytes: int | None = None) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    remaining = limit_bytes
    with path.open("rb") as fh:
        while True:
            chunk_size = 1024 * 1024
            if remaining is not None:
                if remaining <= 0:
                    break
                chunk_size = min(chunk_size, remaining)
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return h.hexdigest()


def file_meta(path: Path, *, hash_file: bool = True) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if path.exists():
        stat = path.stat()
        meta.update(
            {
                "is_file": path.is_file(),
                "size": stat.st_size,
                "mtime": iso_mtime(path),
            }
        )
        if hash_file and path.is_file():
            meta["sha256"] = sha256_file(path)
    return meta


def bounded_redacted_excerpt(path: Path, max_chars: int) -> str | None:
    del path, max_chars
    raise ValueError(
        "generic redacted excerpts are disabled; the bridge is metadata-only because arbitrary text cannot be proven secret-free"
    )


def _sanitize_report_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_report_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_report_value(item) for item in value]
    if not isinstance(value, str):
        return value
    sanitized = value
    home = str(user_home().resolve())
    for variant in {home, home.replace("\\", "/")}:
        sanitized = re.sub(re.escape(variant), "$USER_HOME", sanitized, flags=re.IGNORECASE)
    if re.search(r"(?i)(?:[a-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+)", sanitized):
        digest = hashlib.sha256(sanitized.encode("utf-8", errors="surrogatepass")).hexdigest()[:16]
        return f"<local-path:{digest}>"
    return sanitized


def load_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        return {}
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - diagnostic bridge should not crash on malformed config.
        return {"_parse_error": str(exc)}


def inspect_sqlite(path: Path) -> dict[str, Any]:
    result = file_meta(path)
    result["tables"] = []
    if not path.exists():
        result["status"] = "missing"
        return result
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            rows = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            tables: list[dict[str, Any]] = []
            for (name,) in rows:
                table: dict[str, Any] = {"name": name}
                try:
                    table["row_count"] = int(con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                except Exception as exc:  # noqa: BLE001
                    table["row_count_error"] = str(exc)
                try:
                    columns = con.execute(f'PRAGMA table_info("{name}")').fetchall()
                    table["columns"] = [col[1] for col in columns]
                except Exception as exc:  # noqa: BLE001
                    table["columns_error"] = str(exc)
                tables.append(table)
            result["tables"] = tables
            result["status"] = "ok"
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["error"] = str(exc)
    return result


def sqlite_table_row_count(store: dict[str, Any], table_name: str) -> int | None:
    for table in store.get("tables") or []:
        if table.get("name") == table_name and isinstance(table.get("row_count"), int):
            return int(table["row_count"])
    return None


def sqlite_total_row_count(store: dict[str, Any]) -> int:
    total = 0
    for table in store.get("tables") or []:
        if isinstance(table.get("row_count"), int):
            total += int(table["row_count"])
    return total


def sqlite_table_columns(store: dict[str, Any], table_name: str) -> list[str]:
    for table in store.get("tables") or []:
        if table.get("name") == table_name:
            return [str(column) for column in table.get("columns") or []]
    return []


def quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sqlite_nonempty_text_count(path: Path, table_name: str, column_name: str) -> int | None:
    if not path.exists():
        return None
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            table = quote_sqlite_identifier(table_name)
            column = quote_sqlite_identifier(column_name)
            row = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND length(trim(CAST({column} AS TEXT))) > 0"
            ).fetchone()
            return int(row[0]) if row else None
        finally:
            con.close()
    except Exception:
        return None


def codex_content_recall_status(store: dict[str, Any], body_rows: int | None, nonempty_rows: int | None, content_mode: str) -> str:
    status = store.get("status")
    if status != "ok":
        return f"sqlite_{status or 'unknown'}"
    if body_rows is None:
        return "body_table_missing"
    if body_rows == 0:
        return "empty_store_no_body_rows"
    if nonempty_rows == 0:
        return "body_rows_present_but_empty_text"
    if content_mode == "redacted":
        return "body_rows_present_not_excerpted_by_bridge"
    return "body_rows_present_metadata_only"


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {"'", '"'} and value[-1:] == value[0]:
        return value[1:-1]
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in {"null", "none", "~"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def safe_bool(value: Any = MISSING) -> tuple[bool | None, str]:
    if value is MISSING:
        return None, "missing"
    if type(value) is bool:
        return value, "valid"
    return None, "invalid_type"


def safe_positive_int(value: Any = MISSING) -> tuple[int | None, str]:
    if value is MISSING:
        return None, "missing"
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value, "valid"
    return None, "invalid_type"


def safe_string_presence(value: Any = MISSING) -> tuple[bool, str]:
    if value is MISSING:
        return False, "missing"
    if isinstance(value, str) and value.strip():
        return True, "configured"
    return False, "invalid_type"


def parse_simple_yaml_section(
    path: Path,
    section: str,
    *,
    allowed_keys: frozenset[str] = HERMES_MEMORY_KEYS,
) -> dict[str, Any]:
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    result: dict[str, Any] = {}
    in_section = False
    base_indent = 0
    child_indent: int | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if not in_section:
            if stripped == f"{section}:":
                in_section = True
                base_indent = indent
            continue
        if indent <= base_indent:
            break
        if ":" not in stripped:
            continue
        if child_indent is None:
            child_indent = indent
        if indent != child_indent:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        if key not in allowed_keys:
            continue
        if raw_value.strip() == "":
            continue
        result[key] = parse_scalar(raw_value)
    return result


def inspect_codex(content_mode: str, excerpt_chars: int) -> dict[str, Any]:
    codex_home = Path(os.environ.get("CODEX_HOME") or (user_home() / ".codex"))
    config_path = codex_home / "config.toml"
    config = load_toml(config_path)
    features = config.get("features", {}) if isinstance(config, dict) else {}
    memories = config.get("memories", {}) if isinstance(config, dict) else {}
    db_path = codex_home / "memories_1.sqlite"
    memory_store = inspect_sqlite(db_path)
    body_table = "stage1_outputs"
    body_rows = sqlite_table_row_count(memory_store, body_table)
    body_columns = sqlite_table_columns(memory_store, body_table)
    body_column = "raw_memory" if "raw_memory" in body_columns else None
    body_nonempty_rows = sqlite_nonempty_text_count(db_path, body_table, body_column) if body_column else None
    body_empty = None
    if body_rows is not None:
        body_empty = body_rows == 0 or body_nonempty_rows == 0
    features_memories, features_memories_status = safe_bool(
        features.get("memories", MISSING) if isinstance(features, dict) else MISSING
    )
    generate_memories, generate_memories_status = safe_bool(
        memories.get("generate_memories", MISSING) if isinstance(memories, dict) else MISSING
    )
    use_memories, use_memories_status = safe_bool(
        memories.get("use_memories", MISSING) if isinstance(memories, dict) else MISSING
    )
    goals, goals_status = safe_bool(features.get("goals", MISSING) if isinstance(features, dict) else MISSING)
    report: dict[str, Any] = {
        "agent": "codex",
        "home": str(codex_home),
        "config": file_meta(config_path),
        "feature_flags": {
            "features.memories": features_memories,
            "features.memories_status": features_memories_status,
            "memories.generate_memories": generate_memories,
            "memories.generate_memories_status": generate_memories_status,
            "memories.use_memories": use_memories,
            "memories.use_memories_status": use_memories_status,
            "features.goals": goals,
            "features.goals_status": goals_status,
            "deprecated_disable_response_storage_present": bool(
                isinstance(config, dict) and "disable_response_storage" in config
            ),
            "response_storage_request_contract": "live_client_store_false_probe_required",
        },
        "memory_store": memory_store,
        "memory_body_candidate_table": body_table,
        "memory_body_rows": body_rows,
        "memory_body_nonempty_rows": body_nonempty_rows,
        "body_table_state": {
            "table": body_table,
            "candidate_text_column": body_column,
            "row_count": body_rows,
            "nonempty_count": body_nonempty_rows,
            "empty": body_empty,
            "policy": "counts_only_no_raw_sqlite_body",
        },
        "memory_total_rows": sqlite_total_row_count(memory_store),
        "content_recall_status": codex_content_recall_status(memory_store, body_rows, body_nonempty_rows, content_mode),
    }
    report["effective_internal_memory"] = bool(
        features_memories is True and generate_memories is True and use_memories is True
    )
    if content_mode == "redacted":
        if body_rows == 0:
            report["redacted_excerpt"] = "Codex sqlite stage1_outputs has 0 rows; no Codex memory body exists to excerpt. Metadata/counts remain indexed."
        else:
            report["redacted_excerpt"] = "Codex sqlite bodies are not excerpted by this bridge; use metadata/counts and official memory recall only."
    return report


def default_hermes_config_path() -> Path:
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        candidate = Path(env_home) / "config.yaml"
        if candidate.exists():
            return candidate
    candidate = user_data_base() / "hermes" / "config.yaml"
    if candidate.exists():
        return candidate
    return user_home() / ".hermes" / "config.yaml"


def collect_markdown_memory_files(root: Path, content_mode: str, excerpt_chars: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for name in ("MEMORY.md", "USER.md"):
        path = root / name
        meta = file_meta(path)
        meta["kind"] = name
        if content_mode == "redacted" and path.exists():
            meta["redacted_excerpt"] = bounded_redacted_excerpt(path, excerpt_chars)
        files.append(meta)
    return files


def redacted_excerpt_count(files: list[dict[str, Any]]) -> int:
    return sum(1 for file in files if file.get("redacted_excerpt") is not None)


def inspect_hermes(content_mode: str, excerpt_chars: int, hermes_config: Path | None = None) -> dict[str, Any]:
    config_path = hermes_config or default_hermes_config_path()
    hermes_home = config_path.parent
    memory_config = parse_simple_yaml_section(config_path, "memory")
    memory_root = hermes_home / "memories"
    profile_root = hermes_home / "profiles"
    profiles: list[dict[str, Any]] = []
    profile_excerpt_count = 0
    profile_file_count = 0
    if profile_root.exists():
        for profile_dir in sorted(p for p in profile_root.iterdir() if p.is_dir()):
            memory_dir = profile_dir / "memories"
            files = collect_markdown_memory_files(memory_dir, content_mode, excerpt_chars)
            existing = [f for f in files if f.get("exists")]
            profile_file_count += len(existing)
            profile_excerpt_count += redacted_excerpt_count(files)
            profiles.append(
                {
                    "profile": profile_dir.name,
                    "memory_dir": str(memory_dir),
                    "file_count": len(existing),
                    "files": files,
                }
            )
    root_memory_files = collect_markdown_memory_files(memory_root, content_mode, excerpt_chars)
    root_file_count = len([f for f in root_memory_files if f.get("exists")])
    root_excerpt_count = redacted_excerpt_count(root_memory_files)
    memory_enabled, memory_enabled_status = safe_bool(memory_config.get("memory_enabled", MISSING))
    user_profile_enabled, user_profile_enabled_status = safe_bool(
        memory_config.get("user_profile_enabled", MISSING)
    )
    write_approval, write_approval_status = safe_bool(memory_config.get("write_approval", MISSING))
    memory_char_limit, memory_char_limit_status = safe_positive_int(
        memory_config.get("memory_char_limit", MISSING)
    )
    user_char_limit, user_char_limit_status = safe_positive_int(
        memory_config.get("user_char_limit", MISSING)
    )
    provider_configured, provider_status = safe_string_presence(memory_config.get("provider", MISSING))
    if not config_path.exists():
        built_in_provider = "unavailable"
    elif memory_enabled is True:
        built_in_provider = "active"
    elif memory_enabled is False:
        built_in_provider = "inactive"
    else:
        built_in_provider = "unknown"
    report: dict[str, Any] = {
        "agent": "hermes",
        "home": str(hermes_home),
        "config": file_meta(config_path),
        "memory_config": {
            "memory_enabled": memory_enabled,
            "memory_enabled_status": "config_missing" if not config_path.exists() else memory_enabled_status,
            "user_profile_enabled": user_profile_enabled,
            "user_profile_enabled_status": user_profile_enabled_status,
            "write_approval": write_approval,
            "write_approval_status": write_approval_status,
            "memory_char_limit": memory_char_limit,
            "memory_char_limit_status": memory_char_limit_status,
            "user_char_limit": user_char_limit,
            "user_char_limit_status": user_char_limit_status,
            "provider_configured": provider_configured,
            "provider_status": provider_status,
        },
        "built_in_provider": built_in_provider,
        "root_memory_files": root_memory_files,
        "memory_file_count": root_file_count + profile_file_count,
        "profile_memory_count": len(profiles),
        "profiles": profiles,
    }
    if content_mode == "redacted":
        report["redacted_excerpt_count"] = root_excerpt_count + profile_excerpt_count
        report["content_recall_status"] = "redacted_excerpts_indexed" if report["redacted_excerpt_count"] else "no_redacted_excerpts_available"
    else:
        report["content_recall_status"] = "metadata_only"
    report["effective_internal_memory"] = bool(config_path.exists() and memory_enabled is True)
    return report


def select_agents(agent_arg: str) -> list[str]:
    if agent_arg == "all":
        return ["codex", "hermes"]
    agents = [a.strip().lower() for a in agent_arg.split(",") if a.strip()]
    if not agents:
        raise ValueError("at least one bridge agent is required")
    unknown = sorted(set(agents) - {"codex", "hermes"})
    if unknown:
        raise ValueError("unknown agent: " + ", ".join(unknown))
    return list(dict.fromkeys(agents))


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.content_mode != "metadata":
        raise ValueError("internal-memory Shiguan bridge is metadata-only")
    agents = select_agents(args.agents)
    report: dict[str, Any] = {
        "schema": "court.internal_memory_shiguan_bridge.v1",
        "generated_at": now_iso(),
        "content_mode": args.content_mode,
        "raw_memory_body_included": False,
        "agents": {},
    }
    if args.content_mode == "redacted":
        report["raw_memory_body_included"] = False
        report["content_note"] = "Only bounded redacted excerpts are included; no full raw memory body is copied."
    else:
        report["content_note"] = "Metadata-only bridge; no memory body excerpts are included."
    if "codex" in agents:
        report["agents"]["codex"] = inspect_codex(args.content_mode, args.excerpt_chars)
    if "hermes" in agents:
        report["agents"]["hermes"] = inspect_hermes(args.content_mode, args.excerpt_chars, Path(args.hermes_config) if args.hermes_config else None)
    sanitized = _sanitize_report_value(report)
    if not isinstance(sanitized, dict):
        raise TypeError("sanitized bridge report must remain an object")
    return sanitized


def compact_agent_summary(report: dict[str, Any]) -> str:
    parts: list[str] = []
    codex = report.get("agents", {}).get("codex")
    if codex:
        store = codex.get("memory_store", {})
        table_count = len(store.get("tables") or [])
        row_count = 0
        for table in store.get("tables") or []:
            if isinstance(table.get("row_count"), int):
                row_count += table["row_count"]
        parts.append(
            "Codex memories={mem} generate={gen} use={use} sqlite={sqlite} tables={tables} rows={rows} body_rows={body_rows} body_nonempty={body_nonempty} content_status={content_status}".format(
                mem=codex.get("feature_flags", {}).get("features.memories"),
                gen=codex.get("feature_flags", {}).get("memories.generate_memories"),
                use=codex.get("feature_flags", {}).get("memories.use_memories"),
                sqlite=store.get("status"),
                tables=table_count,
                rows=row_count,
                body_rows=codex.get("memory_body_rows"),
                body_nonempty=codex.get("memory_body_nonempty_rows"),
                content_status=codex.get("content_recall_status"),
            )
        )
    hermes = report.get("agents", {}).get("hermes")
    if hermes:
        root_files = [f for f in hermes.get("root_memory_files", []) if f.get("exists")]
        parts.append(
            "Hermes built_in={built_in} memory_enabled={enabled} provider_configured={provider} root_files={root} profile_count={profiles} memory_files={memory_files} redacted_excerpts={redacted_excerpts} content_status={content_status}".format(
                built_in=hermes.get("built_in_provider"),
                enabled=hermes.get("memory_config", {}).get("memory_enabled"),
                provider=hermes.get("memory_config", {}).get("provider_configured"),
                root=len(root_files),
                profiles=hermes.get("profile_memory_count"),
                memory_files=hermes.get("memory_file_count"),
                redacted_excerpts=hermes.get("redacted_excerpt_count"),
                content_status=hermes.get("content_recall_status"),
            )
        )
    return "; ".join(parts)


def build_full_record(report: dict[str, Any]) -> str:
    summary = compact_agent_summary(report)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    status_lines: list[str] = []
    codex = report.get("agents", {}).get("codex")
    if codex:
        body_state = codex.get("body_table_state", {})
        status_lines.append(
            "Codex正文候选表：{table}; rows={rows}; nonempty={nonempty}; policy={policy}; status={status}".format(
                table=body_state.get("table"),
                rows=body_state.get("row_count"),
                nonempty=body_state.get("nonempty_count"),
                policy=body_state.get("policy"),
                status=codex.get("content_recall_status"),
            )
        )
    hermes = report.get("agents", {}).get("hermes")
    if hermes:
        status_lines.append(
            "Hermes脱敏样本：memory_files={files}; redacted_excerpt_count={count}; status={status}".format(
                files=hermes.get("memory_file_count"),
                count=hermes.get("redacted_excerpt_count"),
                status=hermes.get("content_recall_status"),
            )
        )
    return "\n".join(
        [
            "内置记忆史馆桥接记录",
            f"时间：{report.get('generated_at')}",
            "范围：Codex/Hermes 内置记忆状态与本地文件元数据",
            f"内容模式：{report.get('content_mode')}；原始记忆正文写入：否",
            f"摘要：{summary}",
            *status_lines,
            "门下隐私裁定：默认仅桥接元数据、哈希、mtime、大小和计数；未经明示不复制原始记忆正文。",
            "后续：内容级桥接已禁用；本脚本只允许 metadata-only。",
            "",
            "结构化证据：",
            payload,
        ]
    )


def run_archive(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    script = Path(__file__).resolve().with_name("archive_checkpoint.py")
    if not script.exists():
        raise FileNotFoundError(f"archive_checkpoint.py not found beside {__file__}")
    full_record = build_full_record(report)
    summary = "已桥接 Codex/Hermes 内置记忆状态到史馆；默认仅写元数据、哈希、计数与启用状态，未写原始记忆正文。"
    evidence = compact_agent_summary(report)
    cmd = [
        sys.executable,
        str(script),
        "--topic",
        "Codex Hermes 内置记忆史馆桥接",
        "--phase",
        "桥接",
        "--status",
        "DONE",
        "--summary",
        summary,
        "--evidence",
        evidence,
        "--next",
        "等待用户另旨是否打包；内容级桥接须另行明示并脱敏复核。",
        "--memory-decision",
        "PROPOSE",
        "--memory-content",
        "Codex/Hermes 内置记忆桥接到史馆默认 metadata-only，不镜像原始私密记忆正文；内容级桥接需另行明示并脱敏复核。",
        "--memory-reason",
        "这是稳定的跨 agente 记忆治理规则，适合进入史馆召回并由门下决定是否写长期记忆。",
        "--risk-level",
        "B",
        "--knowledge-value",
        "A",
        "--priority-level",
        "A",
        "--keywords",
        "内置记忆,史馆桥接,Codex memories,Hermes built-in memory,metadata-only,privacy,no Hindsight,codex_body_table,body_table_state,memory_body_rows,empty_store_no_body_rows,content_recall_status,redacted_excerpt_count",
        "--key-actions",
        "enable codex native memories,inspect hermes built-in memory,archive metadata bridge,record body_table_state,record content_recall_status,avoid raw memory bodies",
        "--source-agent",
        args.source_agent,
        "--full-record",
        full_record,
        "--refresh-mode",
        args.refresh_mode,
    ]
    if args.result_json:
        cmd.extend(["--result-json", args.result_json])
    proc = subprocess.run(cmd, cwd=str(script.parent), text=True, capture_output=True, encoding="utf-8", errors="replace")
    return {
        "command_shape": ["python", "archive_checkpoint.py", "--topic", "..."],
        "command_sha256": hashlib.sha256("\0".join(cmd).encode("utf-8", errors="surrogatepass")).hexdigest(),
        "returncode": proc.returncode,
        "stdout_bytes": len(proc.stdout.encode("utf-8", errors="replace")),
        "stderr_bytes": len(proc.stderr.encode("utf-8", errors="replace")),
        "stdout_sha256": hashlib.sha256(proc.stdout.encode("utf-8", errors="replace")).hexdigest(),
        "stderr_sha256": hashlib.sha256(proc.stderr.encode("utf-8", errors="replace")).hexdigest(),
        "stdout_archived": False,
        "stderr_archived": False,
    }


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agents", default="all", help="all, codex, hermes, or comma-separated list. Default: all.")
    parser.add_argument("--content-mode", choices=["metadata", "redacted"], default="metadata")
    parser.add_argument("--allow-redacted-content", action="store_true", help="Required when --content-mode redacted is used.")
    parser.add_argument("--excerpt-chars", type=int, default=500, help="Max chars per redacted excerpt when explicitly enabled.")
    parser.add_argument("--hermes-config", help="Optional explicit Hermes config.yaml path.")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Bridge Codex/Hermes built-in memory metadata to Shiguan.")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Inspect built-in memory state without writing Shiguan.")
    add_common_args(inspect_p)
    inspect_p.add_argument("--format", choices=["json", "text"], default="text")

    record_p = sub.add_parser("record", help="Write a Shiguan checkpoint for built-in memory state.")
    add_common_args(record_p)
    record_p.add_argument("--format", choices=["json", "text"], default="text")
    record_p.add_argument("--source-agent", default="codex", help="archive_checkpoint source-agent override; default codex.")
    record_p.add_argument("--refresh-mode", choices=["async", "none", "tree", "sync"], default="async")
    record_p.add_argument("--result-json", help="Optional archive_checkpoint result JSON path.")

    args = parser.parse_args(argv)
    if args.content_mode == "redacted":
        parser.error("--content-mode redacted is disabled; this bridge is metadata-only")
    try:
        report = build_report(args)
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == "inspect":
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(compact_agent_summary(report))
            print(f"content_mode={report['content_mode']} raw_memory_body_included={report['raw_memory_body_included']}")
        return 0
    archive = run_archive(report, args)
    output = {"bridge_report": report, "archive": archive}
    if args.format == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(compact_agent_summary(report))
        print(
            f"archive_returncode={archive['returncode']} "
            f"stdout_sha256={archive['stdout_sha256']} stderr_sha256={archive['stderr_sha256']}"
        )
    return int(archive["returncode"])


if __name__ == "__main__":
    raise SystemExit(main())
