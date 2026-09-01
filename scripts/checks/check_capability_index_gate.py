"""Select candidate capabilities from the local court capability index."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib
from typing import Callable, Mapping, Sequence

sys.dont_write_bytecode = True

from shiguan_paths import reference_path
from court_capability_recruitment import (
    AUTHORITIES,
    SEARCHABLE_CANDIDATE_KINDS,
    evaluate_recruitment,
    redact_discovery_query,
)


def skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def codex_home() -> Path:
    return Path.home() / ".codex"


def manifest_path() -> Path:
    return reference_path("installed-capabilities-manifest.json")


def catalog_path() -> Path:
    return reference_path("installed-capabilities-catalog.md")


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


def load_records(path: Path) -> list[dict[str, object]]:
    return list(load_manifest_records(path).get("records", []))


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text.replace("-", " "))]


def score_record(record: dict[str, object], terms: list[str]) -> int:
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


def local_fit_evidence(record: dict[str, object], terms: list[str]) -> dict[str, object]:
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


def prerequisite_status(
    manifest: Path,
    catalog: Path,
    shared_capability_index: Path,
) -> dict[str, object]:
    home = codex_home()
    find_skills = home / "skills" / "find-skills" / "SKILL.md"
    skill_creator = home / "skills" / ".system" / "skill-creator" / "SKILL.md"
    quick_validate = home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    return {
        "find_skills": find_skills.exists(),
        "skill_creator": skill_creator.exists(),
        "quick_validate": quick_validate.exists(),
        "catalog": catalog.exists(),
        "manifest_path": str(manifest),
        "catalog_path": str(catalog),
        "shared_shiguan_capability_index": shared_capability_index.exists(),
        "shared_shiguan_capability_index_path": str(shared_capability_index),
    }


def _frontmatter_name(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    match = re.search(r"(?m)^name\s*:\s*['\"]?([^'\"\r\n]+?)['\"]?\s*$", parts[1])
    return match.group(1).strip() if match else ""


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


def _inventory_contains(
    name: str,
    path: Path,
    executable_inventory: Mapping[str, object],
) -> bool:
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


def local_verification_evidence(
    record: dict[str, object],
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


def select_candidates(
    query: str,
    top: int,
    manifest: Path,
    records: list[dict[str, object]] | None = None,
    *,
    source_roots: Mapping[str, object] | None = None,
    executable_inventory: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    terms = tokenize(query)
    source_records = load_records(manifest) if records is None else records
    ranked: list[tuple[int, dict[str, object]]] = []
    for record in source_records:
        score = score_record(record, terms)
        if score:
            ranked.append((score, record))
    ranked.sort(key=lambda item: (item[0], str(item[1].get("kind", "")), str(item[1].get("name", ""))), reverse=True)
    selected: list[dict[str, object]] = []
    for score, record in ranked[:top]:
        fit = local_fit_evidence(record, terms)
        path_text = str(record.get("path", ""))
        try:
            content_hash = hashlib.sha256(Path(path_text).read_bytes()).hexdigest()
        except OSError:
            content_hash = ""
        verification = local_verification_evidence(
            record,
            source_roots=source_roots,
            executable_inventory=executable_inventory,
        )
        source = str(record.get("source", ""))
        trusted_local_source = verification["verification_status"] == "VERIFIED_LOCAL"
        ambiguous = record.get("requires_review") is True
        dispatchable = (
            verification["verification_status"] == "VERIFIED_LOCAL"
            and trusted_local_source
            and record.get("enabled") is not False
            and record.get("dispatchable") is not False
            and record.get("verified") is not False
            and ("evidence" not in record or isinstance(record.get("evidence"), list))
            and not ambiguous
            and fit["meets_requirements"] is True
        )
        selected.append(
            {
                "scope": "local",
                "score": score,
                "kind": record.get("kind", ""),
                "name": record.get("name", ""),
                "source": source,
                "immutable_ref": f"sha256:{content_hash}" if content_hash else "",
                "content_hash": content_hash,
                "court_units": record.get("court_units", []),
                "primary_fit": record.get("primary_fit", []),
                "relative_path": record.get("relative_path", ""),
                "path": path_text,
                "description": record.get("description", ""),
                "requires_review": ambiguous,
                "trusted": trusted_local_source,
                "dispatchable": dispatchable,
                **verification,
                **fit,
            }
        )
    return selected


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

    The function reads only the injected manifest and source roots. It never
    writes a registry, starts a daemon, or retries the discovery callback.
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


def build_recruitment_next_action(
    gate_result: dict[str, object],
    *,
    authority: str = "unset",
    explicit_no_network: bool = False,
    network_discovery_approved: bool = False,
) -> dict[str, object]:
    local_candidates: list[dict[str, object]] = []
    gate_passed = gate_result.get("capability_index_skill_gate") == "PASSED"
    for candidate in gate_result.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        kind = str(candidate.get("kind") or "").strip().casefold()
        if kind not in SEARCHABLE_CANDIDATE_KINDS:
            continue
        local_candidates.append(
            {
                "scope": "local",
                "kind": kind,
                "name": candidate.get("name", "unnamed"),
                "source": candidate.get("source", "unknown"),
                "immutable_ref": candidate.get("immutable_ref", ""),
                "content_hash": candidate.get("content_hash", ""),
                "verified": gate_passed and candidate.get("verification_status") == "VERIFIED_LOCAL",
                "trusted": candidate.get("trusted") is True,
                "meets_requirements": (
                    candidate.get("meets_requirements") is True
                    and candidate.get("fit_status") == "STRONG_LOCAL_FIT"
                ),
                "stale": False,
                "ambiguous": candidate.get("requires_review") is True,
                "fit_score": candidate.get("fit_coverage", 0),
                "risk": "unknown" if not gate_passed else "local_index",
                "evidence_time": "local_manifest",
            }
        )
    decision = evaluate_recruitment(
        {
            "capability_need": redact_discovery_query(str(gate_result.get("query") or "capability index query")),
            "authority": authority,
            "explicit_no_network": explicit_no_network,
            "network_discovery_approved": network_discovery_approved,
            "network_attempted": False,
            "network_status": "not_run",
            "searched_kinds": _unique_candidate_kinds(gate_result.get("candidates", [])),
            "local_candidates": local_candidates,
            "discovered_candidates": [],
            "task_complexity": "unknown",
            "reuse_value": "unknown",
        }
    )
    return {
        "schema": decision["schema"],
        "action": decision["next_action"]["action"],
        "discovery_status": decision["discovery_status"],
        "searched_kinds": decision["searched_kinds"],
        "candidate_fit": decision["candidate_fit"]["status"],
        "network_policy": decision["network_policy"],
        "reason_codes": decision["reason_codes"],
        "dispatchable": decision["candidate_fit"]["dispatchable_count"] > 0,
    }


def _unique_candidate_kinds(candidates: object) -> list[str]:
    output: list[str] = []
    if not isinstance(candidates, list):
        return output
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        kind = str(candidate.get("kind") or "").strip().casefold()
        if kind in SEARCHABLE_CANDIDATE_KINDS and kind not in output:
            output.append(kind)
    return output


def dispatch_exit_code(result: dict[str, object], require_dispatchable: bool = False) -> int:
    gate = result.get("capability_index_skill_gate")
    if require_dispatchable:
        dispatchable_count = int(result.get("dispatchable_candidate_count") or 0)
        candidates = result.get("candidates", []) or []
        has_verified_dispatchable = any(
            isinstance(candidate, dict)
            and candidate.get("scope") == "local"
            and candidate.get("dispatchable") is True
            and candidate.get("verification_status") == "VERIFIED_LOCAL"
            and candidate.get("trusted") is True
            and candidate.get("fit_status") == "STRONG_LOCAL_FIT"
            for candidate in candidates
        )
        return 0 if gate == "PASSED" and dispatchable_count > 0 and has_verified_dispatchable else 2
    return 0 if gate in {"PASSED", "PARTIAL"} else 2


def evaluate(query: str, top: int) -> dict[str, object]:
    safe_query = redact_discovery_query(query)
    try:
        manifest = manifest_path()
        catalog = catalog_path()
        shared_capability_index = reference_path("shiguan-tree", "capability-index", "_index.md")
    except (OSError, RuntimeError) as exc:
        result = {
            "capability_index_skill_gate": "FAILED",
            "query": safe_query,
            "manifest": None,
            "manifest_state": "UNAVAILABLE",
            "catalog": None,
            "prerequisites": {},
            "candidate_count": 0,
            "dispatchable_candidate_count": 0,
            "candidates": [],
            "error": {
                "code": "shared_shiguan_path_error",
                "exception_type": type(exc).__name__,
            },
            "invocation_rule": "index_first_select_one_or_bounded_set; do_not_invoke_all_candidates",
        }
        result["recruitment_next_action"] = build_recruitment_next_action(result)
        return result
    manifest_result = load_manifest_records(manifest)
    prereq = prerequisite_status(manifest, catalog, shared_capability_index)
    manifest_status = str(manifest_result.get("status") or "CORRUPT")
    manifest_state = str(manifest_result.get("state") or "CORRUPT")
    if manifest_status != "VALID":
        code = "manifest_missing" if manifest_status == "MISSING" else "manifest_corrupt"
        result = {
            "capability_index_skill_gate": "FAILED",
            "query": safe_query,
            "manifest": str(manifest),
            "manifest_state": manifest_state,
            "catalog": str(catalog),
            "prerequisites": prereq,
            "candidate_count": 0,
            "dispatchable_candidate_count": 0,
            "candidates": [],
            "error": {
                "code": code,
                "detail": str(manifest_result.get("error") or code),
            },
            "invocation_rule": "index_first_select_one_or_bounded_set; do_not_invoke_all_candidates",
        }
        result["recruitment_next_action"] = build_recruitment_next_action(result)
        return result
    records = [record for record in manifest_result.get("records", []) if isinstance(record, dict)]
    candidates = select_candidates(safe_query, top, manifest, records=records)
    prerequisites_ready = all(bool(prereq[key]) for key in ("find_skills", "skill_creator", "quick_validate", "catalog"))
    if not prerequisites_ready:
        for candidate in candidates:
            candidate["dispatchable"] = False
            candidate["verification_status"] = "PREREQUISITE_PARTIAL"
    dispatchable_count = sum(1 for candidate in candidates if candidate.get("dispatchable") is True)
    if not prerequisites_ready:
        gate = "PARTIAL"
    elif not candidates or dispatchable_count == 0:
        gate = "PARTIAL"
    else:
        gate = "PASSED"
    result = {
        "capability_index_skill_gate": gate,
        "query": safe_query,
        "manifest": str(manifest),
        "manifest_state": manifest_state,
        "catalog": str(catalog),
        "prerequisites": prereq,
        "candidate_count": len(candidates),
        "dispatchable_candidate_count": dispatchable_count,
        "candidates": candidates,
        "invocation_rule": "index_first_select_one_or_bounded_set; do_not_invoke_all_candidates",
    }
    result["recruitment_next_action"] = build_recruitment_next_action(result)
    return result


def run_self_test() -> dict[str, object]:
    global reference_path
    original_reference_path = reference_path

    def broken_reference_path(*_parts: str) -> Path:
        raise RuntimeError("simulated shared-root resolution loop")

    try:
        reference_path = broken_reference_path
        result = evaluate("release manifest", 3)
    finally:
        reference_path = original_reference_path
    assert result["capability_index_skill_gate"] == "FAILED"
    assert result["error"]["code"] == "shared_shiguan_path_error"
    partial = {
        "capability_index_skill_gate": "PARTIAL",
        "candidate_count": 0,
        "dispatchable_candidate_count": 0,
        "candidates": [],
        "prerequisites": {},
        "query": "fixture",
    }
    next_action = build_recruitment_next_action(partial, authority="autonomous")
    assert next_action["discovery_status"] == "UNKNOWN_NOT_SEARCHED"
    assert next_action["action"] == "DISCOVER_PUBLIC_METADATA"
    assert dispatch_exit_code(partial, require_dispatchable=True) == 2
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        config = root / "config.toml"
        config.write_text('[mcp_servers.alpha]\ncommand="x"\n[mcp_servers.alpha.env]\nFAKE="x"\n', encoding="utf-8")
        plugin_skill = root / "plugins" / "fixture" / "skills" / "embedded" / "SKILL.md"
        plugin_skill.parent.mkdir(parents=True)
        plugin_skill.write_text('---\nname: embedded\ndescription: fixture\n---\n', encoding="utf-8")
        roots = {"codex_mcp": (config,), "codex_plugin": (root / "plugins",)}
        mcp = {
            "kind": "mcp", "source": "codex_mcp", "name": "alpha",
            "path": "config.toml", "relative_path": "mcp:alpha", "enabled": True,
        }
        plugin = {
            "kind": "skill", "source": "codex_plugin", "name": "embedded",
            "path": "fixture/skills/embedded/SKILL.md",
            "relative_path": "plugin:fixture:embedded/SKILL.md", "enabled": True,
        }
        disabled = dict(mcp, name="disabled", relative_path="mcp:disabled", enabled=False)
        assert local_verification_evidence(mcp, source_roots=roots)["verification_status"] == "VERIFIED_LOCAL"
        assert local_verification_evidence(plugin, source_roots=roots)["verification_status"] == "VERIFIED_LOCAL"
        selected = select_candidates(
            "disabled", 1, root / "unused.json", records=[disabled], source_roots=roots,
        )
        assert selected[0]["dispatchable"] is False
    return {
        "ok": True,
        "shared_shiguan_path_error": True,
        "unknown_not_searched": True,
        "require_dispatchable_fail_closed": True,
        "plugin_skill_verified": True,
        "disabled_non_dispatchable": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--authority", choices=["unset", *sorted(AUTHORITIES)], default="unset")
    parser.add_argument("--network-discovery-approved", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--require-dispatchable", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        result = run_self_test()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not args.query:
        parser.error("--query is required unless --self-test is used")

    safe_query = redact_discovery_query(args.query)
    result = evaluate(safe_query, max(1, args.top))
    result["query"] = redact_discovery_query(str(result.get("query") or safe_query))
    result["recruitment_next_action"] = build_recruitment_next_action(
        result,
        authority=args.authority,
        explicit_no_network=args.no_network,
        network_discovery_approved=args.network_discovery_approved,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "CAPABILITY_INDEX_GATE "
            f"{result['capability_index_skill_gate']} "
            f"query={result['query']!r} candidates={result['candidate_count']} "
            f"dispatchable={result['dispatchable_candidate_count']} "
            f"next={result['recruitment_next_action']['action']}"
        )
        for candidate in result["candidates"]:
            print(
                f"- {candidate['kind']}:{candidate['name']} "
                f"score={candidate['score']} units={candidate['court_units']} "
                f"path={candidate['relative_path']}"
            )
    return dispatch_exit_code(result, require_dispatchable=args.require_dispatchable)


if __name__ == "__main__":
    sys.exit(main())



