"""Pure, side-effect-free capability recruitment policy decisions."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tomllib
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit


sys.dont_write_bytecode = True

SCHEMA = "court.capability_recruitment.v1"
AUTHORITIES = {"approval", "autonomous", "super"}
NETWORK_AUTHORITIES = {"autonomous", "super"}
PUBLIC_PROVENANCE_FIELDS = (
    "kind",
    "name",
    "publisher",
    "source",
    "url",
    "immutable_ref",
    "content_hash",
    "version_date",
    "license",
    "permissions",
    "install_behavior",
    "postinstall",
    "binary_dependencies",
    "network_data_behavior",
    "maintenance_signal",
    "fit_score",
    "risk",
    "evidence_time",
    "requires_paid_action",
    "requires_login",
    "requires_private_upload",
)
CONSENT_SECURITY_FIELDS = (
    "requires_paid_action",
    "requires_login",
    "requires_private_upload",
    "trusted",
    "verified",
)
CANDIDATE_SNAPSHOT_FIELDS = (
    "kind",
    "name",
    "source",
    "publisher",
    "url",
    "immutable_ref",
    "content_hash",
    "version_date",
    "license",
    "permissions",
    "install_behavior",
    "postinstall",
    "binary_dependencies",
    "network_data_behavior",
    "maintenance_signal",
    "fit_score",
    "risk",
    "evidence_time",
    "purpose",
    "destination",
    *CONSENT_SECURITY_FIELDS,
)
SEARCHABLE_CANDIDATE_KINDS = frozenset({"mcp", "plugin", "skill"})
PUBLIC_CANDIDATE_KINDS = SEARCHABLE_CANDIDATE_KINDS
UNKNOWN_PROVENANCE_VALUES = frozenset(
    {"n/a", "na", "not known", "not_provided", "tbd", "undisclosed", "unknown", "unspecified"}
)
DECLARED_PROVENANCE_FIELDS = (
    "publisher",
    "license",
    "permissions",
    "install_behavior",
    "network_data_behavior",
    "maintenance_signal",
    "risk",
)
BASE_CONSENT_BINDING_FIELDS = (
    "action",
    "kind",
    "name",
    "purpose",
    "destination",
    "allowed_actions",
    "candidate_snapshot",
    "candidate_digest",
    "discovery_query",
    "discovery_status",
    "decree_id",
    "turn_id",
)
EXTERNAL_PROVENANCE_BINDING_FIELDS = (
    "source",
    "publisher",
    "immutable_ref",
    "content_hash",
)
CONSENT_BINDING_FIELDS = BASE_CONSENT_BINDING_FIELDS + EXTERNAL_PROVENANCE_BINDING_FIELDS
HARD_STOP_FLAGS = {
    "requires_paid_action": "CANDIDATE_REQUIRES_PAID_ACTION",
    "requires_login": "CANDIDATE_REQUIRES_LOGIN",
    "requires_credentials": "CANDIDATE_REQUIRES_CREDENTIALS",
    "requires_private_upload": "CANDIDATE_REQUIRES_PRIVATE_UPLOAD",
    "source_conflict": "CANDIDATE_SOURCE_CONFLICT",
    "tls_failed": "CANDIDATE_TLS_FAILED",
    "digest_failed": "CANDIDATE_DIGEST_FAILED",
    "cross_domain_redirect": "CANDIDATE_CROSS_DOMAIN_REDIRECT",
}


def _unique(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _normalized_actions(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted(_unique(str(item).upper() for item in value))


def _normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted(_unique(str(item).strip() for item in value))


def normalize_candidate_snapshot(candidate: Mapping[str, object] | None) -> dict[str, object]:
    """Return the bounded canonical candidate identity used for consent binding."""

    if not isinstance(candidate, Mapping):
        return {}
    normalized: dict[str, object] = {}
    for field in CANDIDATE_SNAPSHOT_FIELDS:
        if field not in candidate:
            continue
        value = candidate.get(field)
        if field in {"permissions", "binary_dependencies"}:
            normalized[field] = _normalized_string_list(value)
        elif field in CONSENT_SECURITY_FIELDS:
            normalized[field] = value if isinstance(value, bool) else str(value).strip()
        elif field == "fit_score" and isinstance(value, (int, float)) and not isinstance(value, bool):
            normalized[field] = value
        elif value is None:
            normalized[field] = ""
        else:
            normalized[field] = str(value).strip()
    return normalized


def candidate_snapshot_digest(candidate: Mapping[str, object] | None) -> str:
    normalized = normalize_candidate_snapshot(candidate)
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _binding_value(field: str, value: object) -> object:
    if field == "action":
        return str(value or "").upper()
    if field == "allowed_actions":
        return _normalized_actions(value)
    if field == "candidate_snapshot":
        return normalize_candidate_snapshot(value if isinstance(value, Mapping) else None)
    if field == "candidate_digest":
        return str(value or "").strip().casefold()
    return str(value or "").strip()


def redact_discovery_query(query: str, sensitive_terms: Sequence[str] = ()) -> str:
    """Return an abstract metadata-discovery query with private material removed."""

    redacted = str(query or "")
    for term in sorted((str(item) for item in sensitive_terms if str(item)), key=len, reverse=True):
        redacted = re.sub(re.escape(term), "[REDACTED]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(
        r"(?i)\bsk-(?:proj|live|svc|admin|org|user)?-?[A-Za-z0-9_-]{6,}\b",
        "[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|glpat-[A-Za-z0-9_-]{8,})(?![A-Za-z0-9])",
        "[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r'''(?ix)\b(?:api[_-]?key|access[_-]?token|token|secret|password|passwd)\s*[:=：]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)''',
        "[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+", "[REDACTED]", redacted)
    redacted = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED]", redacted, flags=re.IGNORECASE)
    identity_label = (
        r"username|user[_ -]?name|用户名|用户名称|账号|账户|"
        r"private[_ -]?(?:repository|repo)|私有(?:代码)?仓库|私人仓库"
    )
    redacted = re.sub(
        rf'''(?ix)(?<!\w)({identity_label})\s*[:=：]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)''',
        lambda match: f"{match.group(1)}:[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r'''(?i)(["'])(?:[A-Za-z]:[\\/]|\\\\|/)[^"'\r\n]+\1''',
        "[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(?<![\w:])[A-Za-z]:[\\/][^\r\n,;]*?\.[A-Za-z0-9]{1,16}(?=\s|$|[,;])",
        "[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"(?<![\w:])(?:[A-Za-z]:[\\/]|\\\\)[^\s,;]+", "[REDACTED]", redacted)
    redacted = re.sub(r"(?<![:\w])/(?:[^/\s]+/)*[^\s,;]*", "[REDACTED]", redacted)
    labelled = r"source code|source|log|prompt|path|路径|源码|日志|史馆正文|用户数据"
    redacted = re.sub(
        rf"(?is)(?<!\w)({labelled})\s*[:：]\s*.*?(?=\s+(?<!\w)(?:{labelled})\s*[:：]|$)",
        lambda match: f"{match.group(1)}:[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"(?:\[REDACTED\]\s*){2,}", "[REDACTED] ", redacted)
    return " ".join(redacted.split()).strip()


def codex_home() -> Path:
    return Path.home() / ".codex"


def default_source_roots() -> dict[str, tuple[Path, ...]]:
    home = Path.home()
    codex = codex_home()
    path_roots = tuple(
        Path(item).expanduser()
        for item in os.environ.get("PATH", "").split(os.pathsep)
        if item.strip()
    )
    return {
        "codex_skills": (codex / "skills",),
        "agent_fallback_skills": (home / ".agents" / "skills",),
        "codex_agents": (codex / "agents",),
        "codex_mcp": (codex / "config.toml",),
        "codex_plugin": (codex / "plugins" / "cache",),
        "local_skill": (codex / "skills", home / ".agents" / "skills"),
        "local_plugin": (codex / "plugins" / "cache",),
        "local_mcp": (codex / "config.toml",),
        "path": path_roots,
    }


def default_executable_inventory(names: Sequence[str]) -> dict[str, tuple[Path, ...]]:
    inventory: dict[str, tuple[Path, ...]] = {}
    for name in names:
        normalized = str(name).strip().casefold()
        if not normalized or normalized in inventory:
            continue
        resolved = shutil.which(str(name).strip())
        inventory[normalized] = (Path(resolved).resolve(),) if resolved else ()
    return inventory


def parse_manifest_payload(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        return {"status": "CORRUPT", "state": "CORRUPT", "records": [], "error": "manifest_root_not_object"}
    if "capabilities" not in data:
        return {"status": "CORRUPT", "state": "CORRUPT", "records": [], "error": "manifest_capabilities_missing"}
    records = data.get("capabilities")
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        return {"status": "CORRUPT", "state": "CORRUPT", "records": [], "error": "manifest_capabilities_not_object_list"}
    normalized = [dict(record) for record in records]
    return {
        "status": "VALID",
        "state": "EMPTY" if not normalized else "POPULATED",
        "records": normalized,
        "error": None,
    }


def load_manifest_records(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"status": "MISSING", "state": "MISSING", "records": [], "error": "manifest_missing"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "CORRUPT", "state": "CORRUPT", "records": [], "error": "manifest_json_invalid"}
    except OSError:
        return {"status": "CORRUPT", "state": "CORRUPT", "records": [], "error": "manifest_unreadable"}
    return parse_manifest_payload(data)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text.replace("-", " "))]


def score_record(record: Mapping[str, object], terms: list[str]) -> int:
    haystack = " ".join(
        [
            str(record.get("name", "")),
            str(record.get("kind", "")),
            str(record.get("source", "")),
            str(record.get("description", "")),
            str(record.get("path", "")),
            " ".join(str(item) for item in record.get("court_units", []) or []),
            " ".join(str(item) for item in record.get("primary_fit", []) or []),
        ]
    ).lower()
    return sum(3 if term in str(record.get("name", "")).lower() else 1 for term in terms if term in haystack)


def _mapping_paths(values: object) -> tuple[Path, ...]:
    if isinstance(values, (str, Path)):
        return (Path(values),)
    if not isinstance(values, Sequence):
        return ()
    return tuple(Path(item) for item in values if isinstance(item, (str, Path)))


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError:
        return path.expanduser().absolute()


def _within_declared_root(path: Path, root: Path) -> bool:
    resolved_path = _resolved(path)
    resolved_root = _resolved(root)
    if resolved_root.is_file():
        return resolved_path == resolved_root
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return False
    return True


def _inventory_contains(name: str, path: Path, executable_inventory: Mapping[str, object]) -> bool:
    expected = _mapping_paths(executable_inventory.get(name.casefold(), ()))
    resolved_path = str(_resolved(path)).casefold()
    return any(str(_resolved(item)).casefold() == resolved_path for item in expected)


def _executable_file_type(path: Path) -> bool:
    if path.suffix.casefold() in {".py", ".pyw"}:
        return False
    if os.name == "nt":
        allowed = {
            item.casefold()
            for item in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
            if item
        }
        return path.suffix.casefold() in allowed
    return os.access(path, os.X_OK)


def local_fit_evidence(record: Mapping[str, object], terms: list[str]) -> dict[str, object]:
    query_terms = list(dict.fromkeys(term.casefold() for term in terms if term))
    broad_text = " ".join(
        [
            str(record.get("name", "")),
            str(record.get("kind", "")),
            str(record.get("source", "")),
            str(record.get("description", "")),
            " ".join(str(item) for item in record.get("court_units", []) or []),
            " ".join(str(item) for item in record.get("primary_fit", []) or []),
        ]
    )
    strong_text = " ".join(
        [
            str(record.get("name", "")),
            str(record.get("kind", "")),
            " ".join(str(item) for item in record.get("court_units", []) or []),
            " ".join(str(item) for item in record.get("primary_fit", []) or []),
        ]
    )
    broad_tokens = set(tokenize(broad_text))
    strong_tokens = set(tokenize(strong_text))
    matched_terms = [term for term in query_terms if term in broad_tokens]
    strong_terms = [term for term in query_terms if term in strong_tokens]
    coverage = len(matched_terms) / len(query_terms) if query_terms else 0.0
    if len(query_terms) == 1:
        strong_fit = bool(strong_terms)
    else:
        strong_fit = len(matched_terms) >= 2 and (bool(strong_terms) or coverage >= 0.75)
    return {
        "fit_status": "STRONG_LOCAL_FIT" if strong_fit else "WEAK_LEXICAL_MATCH",
        "meets_requirements": strong_fit,
        "query_terms": query_terms,
        "matched_terms": matched_terms,
        "strong_field_terms": strong_terms,
        "fit_coverage": round(coverage, 4),
    }


def _frontmatter_name(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    match = re.search(r"(?m)^name\s*:\s*['\"]?([^'\"\r\n]+?)['\"]?\s*$", parts[1])
    return match.group(1).strip() if match else ""


def local_verification_evidence(
    record: Mapping[str, object],
    *,
    source_roots: Mapping[str, object] | None = None,
    executable_inventory: Mapping[str, object] | None = None,
) -> dict[str, object]:
    source = str(record.get("source") or "").strip().casefold()
    declared_kind = str(record.get("kind") or "").strip().casefold()
    name = str(record.get("name") or "").strip()
    path_text = str(record.get("path") or "").strip()
    path = Path(path_text) if path_text else None
    expected_kinds = {
        "codex_skills": "skill",
        "agent_fallback_skills": "skill",
        "codex_agents": "agent",
        "codex_mcp": "mcp",
        "local_skill": "skill",
        "local_plugin": "plugin",
        "local_mcp": "mcp",
        "path": "cli",
    }
    expected_kind = expected_kinds.get(source)
    evidence: list[str] = []
    roots = source_roots if source_roots is not None else default_source_roots()
    inventory = (
        executable_inventory
        if executable_inventory is not None
        else default_executable_inventory([name] if expected_kind == "cli" else [])
    )
    declared_roots = _mapping_paths(roots.get(source, ()))
    if path is not None and not path.is_absolute():
        resolved_candidates: list[Path] = []
        for root in declared_roots:
            if root.is_file() and (path.name.casefold() == root.name.casefold() or path_text == "config.toml"):
                resolved_candidates.append(root)
            else:
                resolved_candidates.append(root / path)
        path = next((candidate for candidate in resolved_candidates if candidate.exists()), path)
    if source == "codex_plugin" and declared_kind == "skill":
        expected_kind = declared_kind
    source_root_verified = False
    executable_identity_verified = False

    if expected_kind is None:
        evidence.append("SOURCE_NOT_TRUSTED_LOCAL_ROOT")
    if expected_kind is not None and declared_kind != expected_kind:
        evidence.append("DECLARED_KIND_SOURCE_MISMATCH")
    if expected_kind is not None:
        if not declared_roots:
            evidence.append("DECLARED_SOURCE_ROOT_MISSING")
        elif path is not None and any(_within_declared_root(path, root) for root in declared_roots):
            source_root_verified = True
        else:
            evidence.append("DECLARED_SOURCE_ROOT_MISMATCH")
            path = None
    if path is None or (expected_kind == "plugin" and not path.exists()) or (expected_kind != "plugin" and not path.is_file()):
        evidence.append("LOCAL_PATH_NOT_REGULAR_FILE")
    elif expected_kind == "skill":
        if path.name.casefold() != "skill.md":
            evidence.append("SKILL_ENTRYPOINT_NAME_MISMATCH")
        else:
            try:
                discovered_name = _frontmatter_name(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError):
                discovered_name = ""
            if not discovered_name:
                evidence.append("SKILL_FRONTMATTER_NAME_MISSING")
            elif discovered_name.casefold() != name.casefold():
                evidence.append("SKILL_FRONTMATTER_NAME_MISMATCH")
    elif expected_kind == "plugin":
        if path is None or not (path.is_dir() or path.is_file()):
            evidence.append("PLUGIN_ROOT_MISSING")
    elif expected_kind == "agent":
        if path.suffix.casefold() != ".toml" or path.stem.casefold() != name.casefold():
            evidence.append("AGENT_TOML_IDENTITY_MISMATCH")
        else:
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                content = ""
            if not re.search(r"(?m)^description\s*=\s*['\"]", content):
                evidence.append("AGENT_TOML_MARKER_MISSING")
    elif expected_kind == "cli":
        relative = str(record.get("relative_path") or "").strip().casefold()
        if relative != f"cli:{name.casefold()}" or path.stem.casefold() != name.casefold():
            evidence.append("CLI_PATH_IDENTITY_MISMATCH")
        if not _executable_file_type(path):
            evidence.append("CLI_EXECUTABLE_TYPE_INVALID")
        if not _inventory_contains(name, path, inventory):
            evidence.append("CLI_EXECUTABLE_IDENTITY_MISMATCH")
        else:
            executable_identity_verified = True
    elif expected_kind == "mcp":
        relative = str(record.get("relative_path") or "").strip().casefold()
        try:
            content = path.read_text(encoding="utf-8") if path is not None else ""
        except (OSError, UnicodeError):
            content = ""
        try:
            payload = tomllib.loads(content)
        except tomllib.TOMLDecodeError:
            payload = {}
        section_present = any(
            isinstance(payload.get(table), dict) and name in payload[table]
            for table in ("mcp_servers", "mcp")
        )
        if relative != f"mcp:{name.casefold()}" or not section_present:
            evidence.append("MCP_CONFIG_IDENTITY_MISMATCH")

    verified = expected_kind is not None and not evidence
    return {
        "verification_status": "VERIFIED_LOCAL" if verified else "UNVERIFIED",
        "kind_evidence_status": "VERIFIED" if verified else "FAILED",
        "verified_kind": expected_kind,
        "verification_evidence": ["STRUCTURAL_LOCAL_IDENTITY_VERIFIED"] if verified else evidence,
        "path_verified": path is not None and (path.exists() if expected_kind == "plugin" else path.is_file()),
        "source_root_verified": source_root_verified,
        "executable_identity_verified": executable_identity_verified if expected_kind == "cli" else None,
    }


def _normalized_route_state(value: object) -> str:
    if isinstance(value, Mapping):
        value = value.get("state") or value.get("status") or "corrupt"
    state = str(value or "corrupt").strip().casefold().replace("-", "_")
    if state in {"current", "fresh", "valid", "populated", "empty"}:
        return "current"
    if state in {"missing", "stale", "corrupt"}:
        return state
    return "corrupt"


def _tool_id(value: object) -> str:
    tool = str(value or "").strip().casefold().replace("_", "-")
    return {
        "claude": "claude-code",
        "claudecode": "claude-code",
        "hermescli": "hermes",
    }.get(tool, tool)


def _tool_compatibility(record: Mapping[str, object], current_tool: str) -> dict[str, object]:
    requested = _tool_id(current_tool)
    declared = record.get("compatible_tools", record.get("supported_tools"))
    explicit = declared is not None
    if isinstance(declared, str):
        values = [item for item in re.split(r"[,;\s]+", declared) if item]
    elif isinstance(declared, Sequence):
        values = [str(item) for item in declared]
    else:
        values = []
    compatible = {_tool_id(item) for item in values if _tool_id(item)}
    if not explicit:
        source = str(record.get("source") or "").strip().casefold()
        if source.startswith("codex_") or source in {"codex_plugin", "codex_agents", "codex_mcp"}:
            compatible = {"codex"}
        elif source in {"agent_fallback_skills", "local_skill", "local_plugin", "local_mcp", "path"}:
            compatible = {"codex", "claude-code", "hermes"}
    matches = bool(requested) and (requested in compatible or "*" in compatible or "any" in compatible)
    return {
        "current_tool": requested,
        "compatible_tools": sorted(compatible),
        "tool_compatibility_status": "VERIFIED" if matches else "INCOMPATIBLE",
        "tool_compatibility_evidence": "explicit_registry_metadata" if explicit else "registry_source_contract",
    }


def _resolved_record_path(record: Mapping[str, object], source_roots: Mapping[str, object]) -> Path | None:
    path_text = str(record.get("path") or "").strip()
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    roots = _mapping_paths(source_roots.get(str(record.get("source") or ""), ()))
    candidates = [
        root if root.is_file() and (path.name.casefold() == root.name.casefold() or path_text == "config.toml") else root / path
        for root in roots
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _hash_evidence(record: Mapping[str, object], source_roots: Mapping[str, object]) -> dict[str, object]:
    declared = str(record.get("content_hash") or "").strip().casefold()
    immutable_ref = str(record.get("immutable_ref") or "").strip().casefold()
    immutable_hash = immutable_ref.removeprefix("sha256:") if immutable_ref.startswith("sha256:") else ""
    declared_conflict = bool(declared and immutable_hash and declared != immutable_hash)
    expected = declared or immutable_hash
    path = _resolved_record_path(record, source_roots)
    actual = ""
    if path is not None and path.is_file():
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            actual = ""
    if declared_conflict:
        status = "DECLARED_CONFLICT"
    elif expected and actual:
        status = "MATCH" if expected == actual else "MISMATCH"
    elif expected:
        status = "SOURCE_UNAVAILABLE"
    elif actual:
        status = "ACTUAL_ONLY"
    else:
        status = "UNAVAILABLE"
    return {
        "hash_status": status,
        "declared_content_hash": expected,
        "observed_content_hash": actual,
        "immutable_ref": f"sha256:{actual}" if actual else immutable_ref,
    }


def _version_evidence(record: Mapping[str, object]) -> dict[str, object]:
    declared = str(record.get("version") or "").strip()
    observed = str(record.get("observed_version") or record.get("current_version") or "").strip()
    drift = record.get("version_drift") is True or bool(declared and observed and declared != observed)
    if drift:
        status = "MISMATCH"
    elif declared and observed:
        status = "MATCH"
    elif declared:
        status = "DECLARED"
    else:
        status = "UNVERSIONED"
    return {"version_status": status, "declared_version": declared, "observed_version": observed}


def route_registry_first(
    query: str,
    current_tool: str,
    manifest: Path | str,
    manifest_state: object,
    source_roots: Mapping[str, object],
    bounded_discovery: Callable[[dict[str, object]], object],
) -> dict[str, object]:
    """Select one verified registry record or invoke one bounded fallback.

    This production helper is read-only. It reads the injected manifest and
    declared source roots, does not write registry state, starts no daemon, and
    calls the bounded fallback at most once.
    """

    registry = Path(manifest)
    safe_query = redact_discovery_query(query)
    state = _normalized_route_state(manifest_state)
    selected: dict[str, object] | None = None
    considered: list[dict[str, object]] = []
    fallback_reason: str | None = state if state in {"missing", "stale", "corrupt"} else None

    if fallback_reason is None:
        loaded = load_manifest_records(registry)
        status = str(loaded.get("status") or "CORRUPT")
        if status != "VALID":
            fallback_reason = "missing" if status == "MISSING" else "corrupt"
        else:
            terms = tokenize(safe_query)
            records = [item for item in loaded.get("records", []) if isinstance(item, dict)]
            ranked = sorted(
                ((score_record(record, terms), record) for record in records),
                key=lambda item: (-item[0], str(item[1].get("kind", "")), str(item[1].get("name", ""))),
            )
            stale_match = False
            executable_inventory = source_roots.get("executable_inventory", {})
            if not isinstance(executable_inventory, Mapping):
                executable_inventory = {}
            for score, record in ranked:
                if score <= 0:
                    continue
                fit = local_fit_evidence(record, terms)
                verification = local_verification_evidence(
                    record,
                    source_roots=source_roots,
                    executable_inventory=executable_inventory,
                )
                compatibility = _tool_compatibility(record, current_tool)
                hash_evidence = _hash_evidence(record, source_roots)
                version_evidence = _version_evidence(record)
                stale = (
                    record.get("stale") is True
                    or str(record.get("state") or "").casefold() == "stale"
                    or record.get("hash_drift") is True
                    or hash_evidence["hash_status"] in {"MISMATCH", "DECLARED_CONFLICT", "SOURCE_UNAVAILABLE"}
                    or version_evidence["version_status"] == "MISMATCH"
                )
                stale_match = stale_match or stale
                dispatchable = (
                    verification["verification_status"] == "VERIFIED_LOCAL"
                    and compatibility["tool_compatibility_status"] == "VERIFIED"
                    and fit["meets_requirements"] is True
                    and record.get("enabled") is not False
                    and record.get("dispatchable") is not False
                    and record.get("verified") is not False
                    and record.get("requires_review") is not True
                    and not stale
                )
                candidate = {
                    "scope": "local",
                    "kind": record.get("kind", ""),
                    "name": record.get("name", ""),
                    "source": record.get("source", ""),
                    "relative_path": record.get("relative_path", ""),
                    "score": score,
                    "dispatchable": dispatchable,
                    "registry_verified": record.get("verified") is not False,
                    "registry_evidence": list(record.get("evidence", [])) if isinstance(record.get("evidence", []), list) else [],
                    **verification,
                    **compatibility,
                    **hash_evidence,
                    **version_evidence,
                    **fit,
                }
                considered.append(candidate)
                if dispatchable:
                    selected = candidate
                    break
            if selected is None:
                fallback_reason = "stale" if stale_match else "no_sufficient_match"

    discovery_invoked = fallback_reason is not None
    discovery_result: object = None
    discovery_error: dict[str, str] | None = None
    if discovery_invoked:
        request = {
            "query": safe_query,
            "current_tool": _tool_id(current_tool),
            "reason": fallback_reason,
            "source_roots": source_roots,
            "limit": 1,
            "offline": True,
            "allow_write": False,
        }
        try:
            discovery_result = bounded_discovery(request)
        except Exception as exc:
            discovery_error = {"exception_type": type(exc).__name__}

    return {
        "schema": "court.capability.registry_first.v1",
        "owner": "libu-hr",
        "query": safe_query,
        "current_tool": _tool_id(current_tool),
        "registry_path": str(manifest),
        "manifest_state": state,
        "selection_source": "registry" if selected is not None else "bounded_discovery",
        "fallback_reason": fallback_reason,
        "selected_candidate": selected,
        "registry_candidates_considered": considered,
        "dispatchable": selected is not None and selected.get("dispatchable") is True,
        "discovery_invoked": discovery_invoked,
        "discovery_call_count": 1 if discovery_invoked else 0,
        "discovery_result": discovery_result,
        "discovery_error": discovery_error,
        "second_registry": False,
        "daemon": False,
    }


def validate_action_consent(
    action_request: Mapping[str, object] | None,
    consent: Mapping[str, object] | None,
    actual_candidate: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate recheckable current-turn consent against the actual candidate."""

    if not action_request or not consent:
        return {"status": "NOT_PROVIDED", "reason_codes": ["CONSENT_NOT_PROVIDED"], "binding_fields": list(CONSENT_BINDING_FIELDS)}

    reasons: list[str] = []
    if consent.get("explicit") is not True:
        reasons.append("CONSENT_NOT_EXPLICIT")
    if consent.get("current_turn") is not True:
        reasons.append("CONSENT_NOT_CURRENT_TURN")

    requested_action = str(action_request.get("action") or "").upper()
    required_fields = list(BASE_CONSENT_BINDING_FIELDS)
    if requested_action != "CREATE":
        required_fields.extend(EXTERNAL_PROVENANCE_BINDING_FIELDS)
    binding_fields = list(required_fields)
    for field in EXTERNAL_PROVENANCE_BINDING_FIELDS:
        if field in action_request or field in consent:
            if field not in binding_fields:
                binding_fields.append(field)

    for field in binding_fields:
        requested = _binding_value(field, action_request.get(field))
        granted = _binding_value(field, consent.get(field))
        if requested != granted:
            reasons.append(f"CONSENT_BINDING_CHANGED:{field}")

    granted_action = str(consent.get("action") or "").upper()
    granted_actions = _normalized_actions(consent.get("allowed_actions"))
    if not requested_action or requested_action != granted_action or requested_action not in granted_actions:
        reasons.append("CONSENT_ACTION_NOT_ALLOWED")

    for field in required_fields:
        value = _binding_value(field, action_request.get(field))
        if value == "" or value == []:
            reasons.append(f"CONSENT_BINDING_MISSING:{field}")

    requested_snapshot = normalize_candidate_snapshot(
        action_request.get("candidate_snapshot") if isinstance(action_request.get("candidate_snapshot"), Mapping) else None
    )
    granted_snapshot = normalize_candidate_snapshot(
        consent.get("candidate_snapshot") if isinstance(consent.get("candidate_snapshot"), Mapping) else None
    )
    actual_snapshot = normalize_candidate_snapshot(actual_candidate)
    for label, snapshot in (
        ("REQUEST", requested_snapshot),
        ("CONSENT", granted_snapshot),
        ("ACTUAL", actual_snapshot),
    ):
        for field in CONSENT_SECURITY_FIELDS:
            if field not in snapshot:
                reasons.append(f"CONSENT_SECURITY_FIELD_MISSING:{label}:{field}")
            elif not isinstance(snapshot.get(field), bool):
                reasons.append(f"CONSENT_SECURITY_FIELD_TYPE_INVALID:{label}:{field}")
    computed_digest = candidate_snapshot_digest(requested_snapshot)
    requested_digest = str(action_request.get("candidate_digest") or "").strip().casefold()
    granted_digest = str(consent.get("candidate_digest") or "").strip().casefold()
    if not requested_snapshot:
        reasons.append("CONSENT_CANDIDATE_SNAPSHOT_MISSING")
    if not actual_snapshot:
        reasons.append("CONSENT_ACTUAL_CANDIDATE_MISSING")
    elif requested_snapshot != actual_snapshot:
        reasons.append("CONSENT_ACTUAL_CANDIDATE_CHANGED")
    if requested_snapshot != granted_snapshot:
        reasons.append("CONSENT_CANDIDATE_SNAPSHOT_CHANGED")
    if not _valid_hash(requested_digest) or requested_digest == "0" * 64 or requested_digest != computed_digest:
        reasons.append("CONSENT_CANDIDATE_DIGEST_INVALID")
    if granted_digest != computed_digest:
        reasons.append("CONSENT_CANDIDATE_DIGEST_CHANGED")

    decree_id = str(action_request.get("decree_id") or "").strip()
    turn_id = str(action_request.get("turn_id") or "").strip()
    if not decree_id or not turn_id:
        reasons.append("CONSENT_DECREE_TURN_MISSING")

    reasons = _unique(reasons)
    status = "INVALID" if reasons else "VALID"
    return {
        "status": status,
        "action": requested_action,
        "target": {
            "kind": str(action_request.get("kind") or ""),
            "name": str(action_request.get("name") or ""),
            "purpose": str(action_request.get("purpose") or ""),
            "destination": str(action_request.get("destination") or ""),
            "candidate_digest": computed_digest,
            "decree_id": decree_id,
            "turn_id": turn_id,
        },
        "reason_codes": reasons,
        "binding_fields": binding_fields,
        "execution_recheck": {
            "required": True,
            "status": "FAILED" if reasons else "PASSED",
            "candidate_digest": computed_digest,
            "decree_id": decree_id,
            "turn_id": turn_id,
        },
    }


def _valid_hash(value: object) -> bool:
    normalized = str(value or "").strip()
    return bool(re.fullmatch(r"[A-Fa-f0-9]{64}", normalized)) and normalized != "0" * 64


def _mutable_ref(value: object) -> bool:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return True
    if normalized in {"main", "master", "head", "latest", "trunk", "tip"}:
        return True
    if normalized.endswith(("/main", "/master", ":latest")):
        return True
    pinned_patterns = (
        r"[0-9a-f]{40}",
        r"[0-9a-f]{64}",
        r"sha256:[0-9a-f]{64}",
        r"v?\d+(?:\.\d+){1,3}(?:[-+][a-z0-9._-]+)?",
    )
    return not any(re.fullmatch(pattern, normalized) for pattern in pinned_patterns)


def _valid_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    return parsed.scheme.casefold() == "https" and bool(parsed.hostname)


def _provenance_type_errors(candidate: Mapping[str, object]) -> list[str]:
    boolean_fields = {
        "ambiguous",
        "meets_requirements",
        "stale",
        "trusted",
        "verified",
        *HARD_STOP_FLAGS,
    }
    text_fields = set(PUBLIC_PROVENANCE_FIELDS) - {
        "permissions",
        "binary_dependencies",
        "fit_score",
        *boolean_fields,
    }
    errors: list[str] = []
    for field in sorted(text_fields):
        if field in candidate and not isinstance(candidate.get(field), str):
            errors.append(f"PROVENANCE_FIELD_TYPE_INVALID:{field}")
    for field in ("permissions", "binary_dependencies"):
        value = candidate.get(field)
        if field in candidate and (
            not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            errors.append(f"PROVENANCE_FIELD_TYPE_INVALID:{field}")
    fit_score = candidate.get("fit_score")
    if "fit_score" in candidate and (
        isinstance(fit_score, bool)
        or not isinstance(fit_score, (int, float))
        or not 0 <= fit_score <= 1
    ):
        errors.append("PROVENANCE_FIELD_TYPE_INVALID:fit_score")
    for field in sorted(boolean_fields):
        if field in candidate and not isinstance(candidate.get(field), bool):
            errors.append(f"PROVENANCE_FIELD_TYPE_INVALID:{field}")
    return errors


def _unknown_provenance_value(field: str, value: object) -> bool:
    if field == "permissions":
        return isinstance(value, list) and any(
            isinstance(item, str) and item.strip().casefold() in UNKNOWN_PROVENANCE_VALUES
            for item in value
        )
    return isinstance(value, str) and value.strip().casefold() in UNKNOWN_PROVENANCE_VALUES


def _candidate_evidence(
    candidate: Mapping[str, object],
    scope: str,
    searched_kinds: Sequence[str],
) -> dict[str, object]:
    reasons: list[str] = []
    missing_fields: list[str] = []
    stale = candidate.get("stale") is True
    ambiguous = candidate.get("ambiguous") is True
    verified = candidate.get("verified") is True
    trusted = candidate.get("trusted") is True
    meets_requirements = candidate.get("meets_requirements") is True

    for flag, reason in HARD_STOP_FLAGS.items():
        if candidate.get(flag) is True:
            reasons.append(reason)

    reasons.extend(_provenance_type_errors(candidate))
    kind = candidate.get("kind")
    normalized_kind = kind.strip().casefold() if isinstance(kind, str) else ""
    if normalized_kind not in PUBLIC_CANDIDATE_KINDS:
        reasons.append("UNSUPPORTED_CANDIDATE_KIND")
    elif normalized_kind not in searched_kinds:
        reasons.append("CANDIDATE_KIND_NOT_SEARCHED")

    if scope == "local":
        source = candidate.get("source")
        if not isinstance(source, str) or not source.strip() or source.strip().casefold() in UNKNOWN_PROVENANCE_VALUES:
            reasons.append("LOCAL_PROVENANCE_SOURCE_MISSING_OR_UNKNOWN")
        if stale:
            reasons.append("LOCAL_CANDIDATE_STALE")
        if ambiguous:
            reasons.append("LOCAL_CANDIDATE_AMBIGUOUS")
        if not verified:
            reasons.append("LOCAL_CANDIDATE_UNVERIFIED")
        if not trusted:
            reasons.append("UNTRUSTED_SOURCE")
        if not meets_requirements:
            reasons.append("CANDIDATE_FIT_INSUFFICIENT")
        if _mutable_ref(candidate.get("immutable_ref")):
            reasons.append("UNPINNED_OR_MUTABLE_REF")
        if not _valid_hash(candidate.get("content_hash")):
            reasons.append("MISSING_OR_INVALID_CONTENT_HASH")
    else:
        for field in PUBLIC_PROVENANCE_FIELDS:
            value = candidate.get(field)
            if field not in candidate or value is None or value == "":
                missing_fields.append(field)
        if missing_fields:
            reasons.append("PROVENANCE_EVIDENCE_INCOMPLETE")
        for field in DECLARED_PROVENANCE_FIELDS:
            if _unknown_provenance_value(field, candidate.get(field)):
                reasons.append(f"PROVENANCE_VALUE_UNKNOWN:{field}")
        if not _valid_https_url(candidate.get("url")):
            reasons.append("INSECURE_PROVENANCE_URL")
        if not verified:
            reasons.append("CANDIDATE_UNVERIFIED")
        if not trusted:
            reasons.append("UNTRUSTED_SOURCE")
        if not meets_requirements:
            reasons.append("CANDIDATE_FIT_INSUFFICIENT")
        if _mutable_ref(candidate.get("immutable_ref")):
            reasons.append("UNPINNED_OR_MUTABLE_REF")
        if not _valid_hash(candidate.get("content_hash")):
            reasons.append("MISSING_OR_INVALID_CONTENT_HASH")
        if str(candidate.get("postinstall") or "").strip().casefold() in {"", "unknown", "unspecified"}:
            reasons.append("UNKNOWN_POSTINSTALL")

        install_behavior = str(candidate.get("install_behavior") or "").strip().casefold()
        network_behavior = str(candidate.get("network_data_behavior") or "").strip().casefold()
        permissions = candidate.get("permissions")
        permission_text = " ".join(permissions).casefold() if isinstance(permissions, list) else ""
        paid_declared = any(token in install_behavior for token in ("paid", "purchase", "subscription"))
        login_declared = any(
            token in f"{install_behavior} {network_behavior} {permission_text}"
            for token in ("authenticated", "credential", "login", "oauth", "sign_in", "signin")
        )
        private_upload_declared = any(
            token in f"{network_behavior} {permission_text}"
            for token in ("private_upload", "upload", "workspace_content")
        )
        if isinstance(candidate.get("requires_paid_action"), bool) and (
            candidate.get("requires_paid_action") is True
        ) != paid_declared:
            reasons.append("CANDIDATE_PAID_STATE_CONFLICT")
        if isinstance(candidate.get("requires_login"), bool) and (
            candidate.get("requires_login") is True
        ) != login_declared:
            reasons.append("CANDIDATE_LOGIN_STATE_CONFLICT")
        if isinstance(candidate.get("requires_private_upload"), bool) and (
            candidate.get("requires_private_upload") is True
        ) != private_upload_declared:
            reasons.append("CANDIDATE_PRIVATE_UPLOAD_STATE_CONFLICT")

    hard_stop_reasons = {
        "UNTRUSTED_SOURCE",
        "UNPINNED_OR_MUTABLE_REF",
        "MISSING_OR_INVALID_CONTENT_HASH",
        "LOCAL_PROVENANCE_SOURCE_MISSING_OR_UNKNOWN",
        "UNKNOWN_POSTINSTALL",
        "PROVENANCE_EVIDENCE_INCOMPLETE",
        "INSECURE_PROVENANCE_URL",
        "UNSUPPORTED_CANDIDATE_KIND",
        "CANDIDATE_KIND_NOT_SEARCHED",
        "CANDIDATE_PAID_STATE_CONFLICT",
        "CANDIDATE_LOGIN_STATE_CONFLICT",
        "CANDIDATE_PRIVATE_UPLOAD_STATE_CONFLICT",
        *HARD_STOP_FLAGS.values(),
    }
    hard_stop = any(
        reason in hard_stop_reasons
        or reason.startswith("PROVENANCE_FIELD_TYPE_INVALID:")
        or reason.startswith("PROVENANCE_VALUE_UNKNOWN:")
        for reason in reasons
    )
    dispatchable = scope == "local" and not reasons and verified and trusted and meets_requirements
    qualified_external = scope == "public" and not reasons and verified and trusted and meets_requirements

    if dispatchable:
        status = "DISPATCHABLE"
    elif qualified_external:
        status = "QUALIFIED_EXTERNAL"
    elif hard_stop:
        status = "HARD_STOP"
    elif stale:
        status = "STALE"
    elif ambiguous:
        status = "AMBIGUOUS"
    elif not verified:
        status = "UNVERIFIED"
    else:
        status = "INSUFFICIENT_FIT"

    evidence = {
        field: copy.deepcopy(candidate.get(field))
        for field in PUBLIC_PROVENANCE_FIELDS
        if field in candidate
    }
    evidence.update(
        {
            "scope": scope,
            "kind": str(candidate.get("kind") or "unknown"),
            "name": str(candidate.get("name") or "unnamed"),
            "status": status,
            "dispatchable": dispatchable,
            "qualified_external": qualified_external,
            "hard_stop": hard_stop,
            "missing_fields": missing_fields,
            "reason_codes": _unique(reasons),
        }
    )
    return evidence


def _validate_inputs(payload: Mapping[str, object]) -> dict[str, object]:
    errors: list[str] = []

    if payload.get("__invalid_context_type__") is True:
        errors.append("INVALID_CONTEXT_TYPE")

    capability_need_raw = payload.get("capability_need", "")
    if not isinstance(capability_need_raw, str):
        errors.append("INVALID_CAPABILITY_NEED_TYPE")
        capability_need = ""
    else:
        capability_need = capability_need_raw

    authority_raw = payload.get("authority", "unset")
    if not isinstance(authority_raw, str):
        errors.append("INVALID_AUTHORITY_TYPE")
        authority = "unset"
    else:
        authority = authority_raw.strip()
        if authority != "unset" and authority not in AUTHORITIES:
            errors.append("INVALID_AUTHORITY_VALUE")
            authority = "unset"

    attempted_raw = payload.get("network_attempted", False)
    if not isinstance(attempted_raw, bool):
        errors.append("INVALID_NETWORK_ATTEMPTED_TYPE")
        network_attempted = False
    else:
        network_attempted = attempted_raw

    status_raw = payload.get("network_status", "not_run")
    if not isinstance(status_raw, str):
        errors.append("INVALID_NETWORK_STATUS_TYPE")
        network_status = "not_run"
    else:
        network_status = status_raw.strip().casefold()
        if network_status not in {"not_run", "success", "failed"}:
            errors.append("INVALID_NETWORK_STATUS_VALUE")
            network_status = "not_run"

    steps_raw = payload.get("stable_steps", 0)
    if isinstance(steps_raw, bool) or not isinstance(steps_raw, int):
        errors.append("INVALID_STABLE_STEPS_TYPE")
        stable_steps = 0
    elif steps_raw < 0:
        errors.append("INVALID_STABLE_STEPS_VALUE")
        stable_steps = 0
    else:
        stable_steps = steps_raw

    for field, code in (
        ("explicit_no_network", "INVALID_EXPLICIT_NO_NETWORK_TYPE"),
        ("network_discovery_approved", "INVALID_NETWORK_APPROVAL_TYPE"),
        ("stable_io", "INVALID_STABLE_IO_TYPE"),
        ("stable_verification", "INVALID_STABLE_VERIFICATION_TYPE"),
        ("creation_benefit", "INVALID_CREATION_BENEFIT_TYPE"),
        ("existing_combination_sufficient", "INVALID_EXISTING_COMBINATION_TYPE"),
        ("contains_secret_or_private_content", "INVALID_PRIVATE_CONTENT_TYPE"),
        ("user_declined_creation", "INVALID_USER_DECLINED_TYPE"),
        ("proposal_asked_in_decree", "INVALID_PROPOSAL_ASKED_TYPE"),
    ):
        if field in payload and not isinstance(payload.get(field), bool):
            errors.append(code)

    searched_raw = payload.get("searched_kinds", [])
    searched_kinds: list[str] = []
    if not isinstance(searched_raw, list):
        errors.append("INVALID_SEARCHED_KINDS_TYPE")
    else:
        seen_kinds: set[str] = set()
        for index, item in enumerate(searched_raw):
            if not isinstance(item, str) or not item.strip():
                errors.append(f"INVALID_SEARCHED_KIND_TYPE:{index}")
                continue
            kind = item.strip().casefold()
            if kind not in SEARCHABLE_CANDIDATE_KINDS:
                errors.append(f"INVALID_SEARCHED_KIND:{kind}")
                continue
            if kind in seen_kinds:
                errors.append("DUPLICATE_SEARCHED_KIND")
                continue
            seen_kinds.add(kind)
            searched_kinds.append(kind)

    normalized_candidates: dict[str, list[Mapping[str, object]]] = {}
    for field, label in (
        ("local_candidates", "LOCAL"),
        ("discovered_candidates", "DISCOVERED"),
    ):
        raw_candidates = payload.get(field, [])
        normalized_group: list[Mapping[str, object]] = []
        if not isinstance(raw_candidates, list):
            errors.append(f"INVALID_{label}_CANDIDATES_TYPE")
        else:
            for index, candidate in enumerate(raw_candidates):
                if not isinstance(candidate, Mapping):
                    errors.append(f"INVALID_{label}_CANDIDATE_TYPE:{index}")
                else:
                    normalized_group.append(candidate)
        normalized_candidates[field] = normalized_group

    redaction_terms_raw = payload.get("redaction_terms", [])
    redaction_terms: list[str] = []
    if not isinstance(redaction_terms_raw, list):
        errors.append("INVALID_REDACTION_TERMS_TYPE")
    else:
        for index, term in enumerate(redaction_terms_raw):
            if not isinstance(term, str):
                errors.append(f"INVALID_REDACTION_TERM_TYPE:{index}")
            elif term:
                redaction_terms.append(term)

    task_complexity_raw = payload.get("task_complexity", "low")
    if not isinstance(task_complexity_raw, str):
        errors.append("INVALID_TASK_COMPLEXITY_TYPE")
        task_complexity = "low"
    else:
        task_complexity = task_complexity_raw.strip().casefold()
        if task_complexity not in {"critical", "high", "low", "medium", "trivial", "unknown"}:
            errors.append("INVALID_TASK_COMPLEXITY_VALUE")
            task_complexity = "low"

    reuse_value_raw = payload.get("reuse_value", "one_off")
    if not isinstance(reuse_value_raw, str):
        errors.append("INVALID_REUSE_VALUE_TYPE")
        reuse_value = "one_off"
    else:
        reuse_value = reuse_value_raw.strip().casefold()
        if reuse_value not in {"likely", "one_off", "recurring", "unknown"}:
            errors.append("INVALID_REUSE_VALUE_VALUE")
            reuse_value = "one_off"

    for field in ("action_request", "action_candidate", "consent"):
        if field in payload and payload.get(field) is not None and not isinstance(payload.get(field), Mapping):
            errors.append(f"INVALID_{field.upper()}_TYPE")

    return {
        "status": "INVALID" if errors else "VALID",
        "errors": _unique(errors),
        "normalized": {
            "network_attempted": network_attempted,
            "network_status": network_status,
            "stable_steps": stable_steps,
            "capability_need": redact_discovery_query(capability_need, redaction_terms),
            "authority": authority,
            "searched_kinds": searched_kinds,
            "local_candidates": normalized_candidates["local_candidates"],
            "discovered_candidates": normalized_candidates["discovered_candidates"],
            "redaction_terms": redaction_terms,
            "task_complexity": task_complexity,
            "reuse_value": reuse_value,
        },
    }


def _invalid_input_result(payload: Mapping[str, object], validation: Mapping[str, object]) -> dict[str, object]:
    normalized = validation.get("normalized") if isinstance(validation.get("normalized"), Mapping) else {}
    authority = str(normalized.get("authority") or "unset")
    searched_kinds = list(normalized.get("searched_kinds") or [])
    safe_terms = list(normalized.get("redaction_terms") or [])
    errors = [str(item) for item in validation.get("errors", [])]
    return {
        "schema": SCHEMA,
        "recruitment_needed": True,
        "authority": authority,
        "discovery_status": "INVALID_INPUT",
        "discovery_query": redact_discovery_query(str(normalized.get("capability_need") or ""), safe_terms),
        "searched_kinds": searched_kinds,
        "candidate_fit": {
            "status": "INSUFFICIENT",
            "candidate_count": 0,
            "dispatchable_count": 0,
            "qualified_external_count": 0,
            "hard_stop_count": 0,
            "best_candidate": None,
            "candidates": [],
        },
        "task_complexity": str(normalized.get("task_complexity") or "unknown"),
        "reuse_value": str(normalized.get("reuse_value") or "unknown"),
        "creation_recommendation": {
            "status": "NOT_RECOMMENDED",
            "next_action": "BLOCKED_BY_AUTHORITY",
            "proposal_only": True,
        },
        "question": None,
        "user_decision": {
            "status": "NOT_ASKED",
            "consent": {
                "status": "NOT_EVALUATED",
                "reason_codes": ["INVALID_INPUT"],
                "binding_fields": list(CONSENT_BINDING_FIELDS),
            },
        },
        "provenance_evidence": [],
        "reason_codes": errors,
        "network_policy": {"allowed": False, "status": "INVALID_INPUT"},
        "next_action": {"action": "BLOCKED_BY_AUTHORITY", "requires_user_contact": False},
        "input_validation": copy.deepcopy(dict(validation)),
        "side_effects": {"network_calls": 0, "write_calls": 0, "actions": []},
    }


def _creation_decision(
    context: Mapping[str, object],
    candidate_status: str,
    discovery_status: str,
    reasons: list[str],
) -> tuple[dict[str, object], dict[str, object] | None]:
    complexity = str(context.get("task_complexity") or "low").casefold()
    reuse = str(context.get("reuse_value") or "one_off").casefold()
    declined = context.get("user_declined_creation") is True
    asked = context.get("proposal_asked_in_decree") is True
    private_content = context.get("contains_secret_or_private_content") is True
    benefit = context.get("creation_benefit") is True
    stable_contract = (
        int(context.get("stable_steps") or 0) >= 4
        and context.get("stable_io") is True
        and context.get("stable_verification") is True
    )
    threshold = (
        (complexity == "medium" and reuse == "recurring")
        or (complexity in {"high", "critical"} and reuse in {"likely", "recurring"})
        or stable_contract
    )
    discovery_settled = discovery_status in {
        "PUBLIC_DISCOVERY_NO_QUALIFIED_CANDIDATE",
        "BLOCKED_BY_USER_NO_NETWORK",
    }

    if candidate_status in {"DISPATCHABLE_LOCAL", "QUALIFIED_EXTERNAL", "SATISFIED_BY_EXISTING_COMBINATION"}:
        return {"status": "NOT_NEEDED", "next_action": "NONE", "proposal_only": True}, None
    if declined:
        reasons.append("USER_DECLINED_CREATION")
        return {"status": "DECLINED", "next_action": "CONTINUE_TASK", "proposal_only": True}, None
    if private_content:
        reasons.append("CREATION_UNSAFE_PRIVATE_CONTENT")
        return {"status": "NOT_RECOMMENDED", "next_action": "CONTINUE_TASK", "proposal_only": True}, None
    if reuse == "one_off" or (complexity == "trivial" and not stable_contract):
        reasons.append("TRIVIAL_DIRECT")
        return {"status": "NOT_RECOMMENDED", "next_action": "CONTINUE_TASK", "proposal_only": True}, None
    if asked and threshold and benefit and discovery_settled:
        reasons.append("PROPOSAL_ALREADY_ASKED")
        return {"status": "ALREADY_ASKED", "next_action": "WAIT_USER", "proposal_only": True}, None
    if threshold and benefit and discovery_settled:
        reasons.append("CREATE_SKILL_PROPOSAL")
        question = {
            "type": "CREATE_SKILL_PROPOSAL",
            "prompt": "是否为该稳定、可复用能力创建专用 skill？",
            "options": [
                "创建可复用 skill（推荐）",
                "仅完成本次任务",
                "暂不创建",
            ],
            "max_questions_this_decree": 1,
        }
        return {"status": "CREATE_SKILL_PROPOSAL", "next_action": "ASK_USER", "proposal_only": True}, question
    return {"status": "NOT_RECOMMENDED", "next_action": "CONTINUE_TASK", "proposal_only": True}, None


def evaluate_recruitment(
    context: Mapping[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Evaluate recruitment policy without performing network or filesystem I/O."""

    if context is not None and not isinstance(context, Mapping):
        payload: dict[str, object] = {"__invalid_context_type__": True}
    else:
        payload = dict(context or {})
    payload.update(overrides)
    input_validation = _validate_inputs(payload)
    if input_validation["status"] == "INVALID":
        return _invalid_input_result(payload, input_validation)
    normalized_inputs = input_validation["normalized"]
    for field in (
        "authority",
        "capability_need",
        "discovered_candidates",
        "local_candidates",
        "redaction_terms",
        "reuse_value",
        "searched_kinds",
        "stable_steps",
        "task_complexity",
    ):
        payload[field] = copy.deepcopy(normalized_inputs[field])
    authority = str(normalized_inputs["authority"])
    explicit_no_network = payload.get("explicit_no_network") is True
    network_approved = payload.get("network_discovery_approved") is True
    network_attempted = normalized_inputs["network_attempted"] is True
    network_status = str(normalized_inputs["network_status"])
    searched_kinds = list(normalized_inputs["searched_kinds"])
    reasons: list[str] = []

    if explicit_no_network:
        network_policy = {"allowed": False, "status": "BLOCKED_BY_USER_NO_NETWORK"}
    elif authority == "unset":
        network_policy = {"allowed": False, "status": "AUTHORITY_REQUIRED"}
    elif authority == "approval" and not network_approved:
        network_policy = {"allowed": False, "status": "APPROVAL_REQUIRED"}
    elif authority in NETWORK_AUTHORITIES or (authority == "approval" and network_approved):
        network_policy = {"allowed": True, "status": "ALLOWED_READ_ONLY_METADATA"}
    else:
        network_policy = {"allowed": False, "status": "AUTHORITY_BLOCKED"}

    local_candidates = payload.get("local_candidates") or []
    discovered_candidates = payload.get("discovered_candidates") or []
    local_evidence = [
        _candidate_evidence(candidate, "local", searched_kinds)
        for candidate in local_candidates
        if isinstance(candidate, Mapping)
    ]
    public_evidence = [
        _candidate_evidence(candidate, "public", searched_kinds)
        for candidate in discovered_candidates
        if isinstance(candidate, Mapping)
    ]
    provenance = [*local_evidence, *public_evidence]
    for item in provenance:
        reasons.extend(str(reason) for reason in item.get("reason_codes", []))

    dispatchable = [item for item in local_evidence if item.get("dispatchable")]
    provenance_qualified_external = [item for item in public_evidence if item.get("qualified_external")]
    external_discovery_eligible = (
        network_policy["allowed"] is True
        and network_attempted
        and network_status == "success"
    )
    qualified_external = provenance_qualified_external if external_discovery_eligible else []
    if provenance_qualified_external and not external_discovery_eligible:
        reasons.append("EXTERNAL_CANDIDATE_REQUIRES_ALLOWED_COMPLETED_DISCOVERY")
    hard_stops = [item for item in provenance if item.get("hard_stop")]
    existing_combination_sufficient = payload.get("existing_combination_sufficient") is True

    if dispatchable:
        candidate_status = "DISPATCHABLE_LOCAL"
    elif qualified_external:
        candidate_status = "QUALIFIED_EXTERNAL"
    elif existing_combination_sufficient:
        candidate_status = "SATISFIED_BY_EXISTING_COMBINATION"
    else:
        candidate_status = "INSUFFICIENT"

    if dispatchable:
        discovery_status = "LOCAL_CANDIDATE_SUFFICIENT"
        reasons.append("LOCAL_CANDIDATE_DISPATCHABLE")
    elif existing_combination_sufficient:
        discovery_status = "LOCAL_CANDIDATE_SUFFICIENT"
        reasons.append("EXISTING_COMBINATION_SUFFICIENT")
    elif explicit_no_network:
        discovery_status = "BLOCKED_BY_USER_NO_NETWORK"
        reasons.append("BLOCKED_BY_USER_NO_NETWORK")
    elif network_attempted and network_status == "failed":
        discovery_status = "NETWORK_DISCOVERY_FAILED"
        reasons.extend(["NETWORK_DISCOVERY_FAILED", "RUNTIME_DEGRADED"])
    elif network_attempted and network_status == "success" and qualified_external:
        discovery_status = "PUBLIC_DISCOVERY_FOUND"
        reasons.append("QUALIFIED_EXTERNAL_CANDIDATE")
    elif network_attempted and network_status == "success":
        discovery_status = "PUBLIC_DISCOVERY_NO_QUALIFIED_CANDIDATE"
        reasons.append("PUBLIC_DISCOVERY_COMPLETED_NO_QUALIFIED_CANDIDATE")
    else:
        discovery_status = "UNKNOWN_NOT_SEARCHED"
        reasons.append("NETWORK_NOT_ATTEMPTED")

    if not local_evidence:
        reasons.append("LOCAL_CANDIDATES_EMPTY")
    if discovery_status == "UNKNOWN_NOT_SEARCHED":
        if network_policy["status"] == "AUTHORITY_REQUIRED":
            reasons.append("AUTHORITY_NOT_SELECTED")
        elif network_policy["status"] == "APPROVAL_REQUIRED":
            reasons.append("NETWORK_APPROVAL_REQUIRED")
        elif network_policy["allowed"]:
            reasons.append("NETWORK_DISCOVERY_ALLOWED")

    action_request = payload.get("action_request") if isinstance(payload.get("action_request"), Mapping) else None
    action_candidate = payload.get("action_candidate") if isinstance(payload.get("action_candidate"), Mapping) else None
    if action_candidate is None and action_request is not None:
        requested_kind = str(action_request.get("kind") or "").strip().casefold()
        requested_name = str(action_request.get("name") or "").strip().casefold()
        for candidate in [*local_candidates, *discovered_candidates]:
            if not isinstance(candidate, Mapping):
                continue
            if (
                str(candidate.get("kind") or "").strip().casefold() == requested_kind
                and str(candidate.get("name") or "").strip().casefold() == requested_name
            ):
                action_candidate = candidate
                break
    consent = validate_action_consent(
        action_request,
        payload.get("consent") if isinstance(payload.get("consent"), Mapping) else None,
        action_candidate,
    )
    creation, question = _creation_decision(payload, candidate_status, discovery_status, reasons)
    if consent["status"] == "VALID":
        user_decision_status = "ACCEPTED"
        reasons.append("BOUND_ACTION_CONSENT_VALID")
    elif payload.get("user_declined_creation") is True:
        user_decision_status = "DECLINED"
    elif payload.get("proposal_asked_in_decree") is True:
        user_decision_status = "PENDING"
    else:
        user_decision_status = "NOT_ASKED"

    consent_action = str(consent.get("action") or "").upper()
    bound_action_forwardable = False
    if consent["status"] == "VALID":
        if consent_action == "CREATE":
            bound_action_forwardable = payload.get("contains_secret_or_private_content") is not True
        elif candidate_status == "DISPATCHABLE_LOCAL":
            bound_action_forwardable = True
        elif candidate_status == "QUALIFIED_EXTERNAL" and external_discovery_eligible:
            bound_action_forwardable = True

    execution_recheck = copy.deepcopy(consent.get("execution_recheck", {"required": True, "status": "NOT_RUN"}))
    if bound_action_forwardable:
        rechecked = validate_action_consent(
            action_request,
            payload.get("consent") if isinstance(payload.get("consent"), Mapping) else None,
            action_candidate,
        )
        execution_recheck = copy.deepcopy(rechecked.get("execution_recheck", {"required": True, "status": "FAILED"}))
        if rechecked.get("status") != "VALID" or execution_recheck.get("status") != "PASSED":
            bound_action_forwardable = False
            reasons.append("EXECUTION_CONSENT_RECHECK_FAILED")

    if bound_action_forwardable and consent_action != "CREATE" and candidate_status == "DISPATCHABLE_LOCAL":
        next_action = "DISPATCH_LOCAL"
    elif candidate_status == "DISPATCHABLE_LOCAL":
        next_action = "DISPATCH_LOCAL"
    elif candidate_status == "SATISFIED_BY_EXISTING_COMBINATION":
        next_action = "CONTINUE_WITHOUT_RECRUITMENT"
    elif candidate_status == "QUALIFIED_EXTERNAL":
        next_action = "BLOCKED_BY_AUTHORITY"
    elif discovery_status == "NETWORK_DISCOVERY_FAILED":
        next_action = "CONTINUE_WITHOUT_RECRUITMENT"
    elif discovery_status == "BLOCKED_BY_USER_NO_NETWORK":
        next_action = "CONTINUE_WITHOUT_RECRUITMENT"
    elif network_policy["status"] == "AUTHORITY_REQUIRED":
        next_action = "BLOCKED_BY_AUTHORITY"
    elif network_policy["status"] == "APPROVAL_REQUIRED":
        next_action = "BLOCKED_BY_AUTHORITY"
    elif discovery_status == "UNKNOWN_NOT_SEARCHED" and network_policy["allowed"]:
        next_action = "DISCOVER_PUBLIC_METADATA"
    elif creation["status"] == "CREATE_SKILL_PROPOSAL":
        next_action = "ASK_USER"
    elif creation["status"] == "ALREADY_ASKED":
        next_action = "CONTINUE_WITHOUT_RECRUITMENT"
    else:
        next_action = "CONTINUE_WITHOUT_RECRUITMENT"

    best_candidate = dispatchable[0] if dispatchable else (qualified_external[0] if qualified_external else None)
    return {
        "schema": SCHEMA,
        "recruitment_needed": candidate_status not in {"DISPATCHABLE_LOCAL", "SATISFIED_BY_EXISTING_COMBINATION"},
        "authority": authority,
        "discovery_status": discovery_status,
        "discovery_query": redact_discovery_query(
            str(payload.get("capability_need") or ""),
            list(normalized_inputs["redaction_terms"]),
        ),
        "searched_kinds": searched_kinds,
        "candidate_fit": {
            "status": candidate_status,
            "candidate_count": len(provenance),
            "dispatchable_count": len(dispatchable),
            "qualified_external_count": len(qualified_external),
            "hard_stop_count": len(hard_stops),
            "best_candidate": copy.deepcopy(best_candidate),
            "candidates": copy.deepcopy(provenance),
        },
        "task_complexity": str(payload.get("task_complexity") or "low").casefold(),
        "reuse_value": str(payload.get("reuse_value") or "one_off").casefold(),
        "creation_recommendation": creation,
        "question": question,
        "user_decision": {
            "status": user_decision_status,
            "consent": consent,
            "execution_recheck": execution_recheck,
        },
        "provenance_evidence": copy.deepcopy(provenance),
        "reason_codes": _unique(reasons),
        "network_policy": network_policy,
        "next_action": {"action": next_action, "requires_user_contact": next_action.startswith("ASK_")},
        "input_validation": copy.deepcopy(input_validation),
        "side_effects": {"network_calls": 0, "write_calls": 0, "actions": []},
    }


__all__ = [
    "SCHEMA",
    "candidate_snapshot_digest",
    "default_executable_inventory",
    "default_source_roots",
    "evaluate_recruitment",
    "load_manifest_records",
    "local_fit_evidence",
    "local_verification_evidence",
    "normalize_candidate_snapshot",
    "route_registry_first",
    "redact_discovery_query",
    "score_record",
    "tokenize",
    "validate_action_consent",
]
