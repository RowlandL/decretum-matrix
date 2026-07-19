"""Mode-neutral office profile/dossier/skill preload manifests and acknowledgements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from types import MappingProxyType
from typing import Mapping

sys.dont_write_bytecode = True

from court_model_router import route_office_model, validate_model_route_ack

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = ROOT / "agents" / "standing-officials"
ORDINARY_DOSSIER_ROOT = ROOT / "agents" / "office-dossiers"
SKILL_PATH = ROOT / "SKILL.md"
ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PRELOAD_ACK_SCHEMA = "court.office.preload_ack.v1"
COURT_SKILL_NAME = "decretum-matrix"
LEGACY_TECHNICAL_LOCATOR_NAME = "court-capability-router"
ORDINARY_CARRIERS = frozenset({"child_agent", "worktree_thread"})
SUPERCC_CLI_CARRIER = "supercc_cli_office"
MINISTRY_ROLES = frozenset({"libu-hr", "libu", "hubu", "gongbu", "xingbu", "bingbu"})


OFFICE_ASSIGNMENT_IDENTITIES = MappingProxyType(
    {
        "taizi": ("TaiZi", "taizi", "taizi", "太子", "user"),
        "zhongshu": ("ZhongShu", "zhongshu", "zhongshu", "中书省", "taizi"),
        "menxia": ("MenXia", "menxia", "menxia", "门下省", "taizi"),
        "shangshu": ("ShangShu", "shangshu", "shangshu", "尚书省", "taizi"),
        "libu-hr": ("LiBuHR", "libu_hr", "libu-hr", "吏部", "shangshu"),
        "libu": ("LiBu", "libu", "libu", "礼部", "shangshu"),
        "hubu": ("HuBu", "hubu", "hubu", "户部", "shangshu"),
        "gongbu": ("GongBu", "gongbu", "gongbu", "工部", "shangshu"),
        "xingbu": ("XingBu", "xingbu", "xingbu", "刑部", "shangshu"),
        "bingbu": ("BingBu", "bingbu", "bingbu", "兵部", "shangshu"),
        "shiguan": ("ShiGuan", "shiguan", "shiguan", "史馆", "taizi/menxia"),
        "shiguan-hermes": ("ShiGuanHermes", "shiguan_hermes", "shiguan-hermes", "史馆", "taizi/menxia"),
        "zaochao": ("ZaoChao", "zaochao", "zaochao", "早朝", "taizi"),
        "patrol-inspector": ("PatrolInspector", "patrol_inspector", "patrol-inspector", "监察使", "taizi"),
    }
)


@dataclass(frozen=True)
class OfficePreloadManifest:
    role_key: str
    carrier_kind: str
    office_zh: str
    direct_superior: str
    profile_source: str
    profile_hash: str
    dossier_path: str
    dossier_hash: str
    court_skill_name: str
    court_skill_path: str
    court_skill_hash: str
    preload_ack_schema: str = PRELOAD_ACK_SCHEMA


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not SHA256_RE.fullmatch(text):
        raise ValueError(f"{field} must be a SHA256 digest")
    return text.lower()


def load_standing_profile_binding(
    role_key: str,
    *,
    profile_root: Path = PROFILE_ROOT,
) -> dict[str, str]:
    root = Path(profile_root).resolve()
    candidate = root / f"{role_key}.toml"
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("standing_profile_path_escape") from exc
    if role_key not in OFFICE_ASSIGNMENT_IDENTITIES:
        raise ValueError("standing_profile_identity_mismatch")
    if not resolved.is_file():
        raise ValueError("standing_profile_missing")
    if tomllib is None:
        raise ValueError("standing_profile_invalid")
    try:
        document = tomllib.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("standing_profile_invalid") from exc
    profile = document.get("profile")
    if not isinstance(profile, dict) or profile.get("role_key") != role_key:
        raise ValueError("standing_profile_identity_mismatch")
    office_zh = profile.get("office_zh")
    direct_superior = profile.get("direct_superior")
    if not isinstance(office_zh, str) or not office_zh.strip() or not isinstance(direct_superior, str) or not direct_superior.strip():
        raise ValueError("standing_profile_fields_missing")
    _, _, _, canonical_office_zh, canonical_direct_superior = OFFICE_ASSIGNMENT_IDENTITIES[role_key]
    if office_zh.strip() != canonical_office_zh or direct_superior.strip() != canonical_direct_superior:
        raise ValueError("standing_profile_identity_mismatch")
    profile_source = (
        PurePosixPath("agents", "standing-officials", f"{role_key}.toml").as_posix()
        if root == PROFILE_ROOT.resolve()
        else str(resolved)
    )
    return {
        "profile_source": profile_source,
        "profile_hash": sha256_file(resolved).lower(),
        "office_zh": office_zh.strip(),
        "direct_superior": direct_superior.strip(),
    }


def validate_skill_requirements(requirements: list[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(requirements, list):
        raise ValueError("skill_binding_invalid")
    validated: list[dict[str, str]] = []
    by_name: dict[str, dict[str, str]] = {}
    required_fields = ("name", "source", "sha256", "purpose", "ack_name", "ack_sha256")
    for raw in requirements:
        if not isinstance(raw, dict) or any(not isinstance(raw.get(field), str) or not raw[field].strip() for field in required_fields):
            raise ValueError("skill_ack_incomplete")
        item = {field: raw[field].strip() for field in required_fields}
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("skill_ack_incomplete")
        source = Path(item["source"])
        if not source.is_absolute() or str(source.resolve()) != item["source"]:
            raise ValueError("skill_source_not_resolved")
        if not source.is_file():
            raise ValueError("required_skill_missing")
        if sha256_file(source).lower() != item["sha256"]:
            raise ValueError("required_skill_hash_mismatch")
        if item["ack_name"] != item["name"] or item["ack_sha256"] != item["sha256"]:
            raise ValueError("skill_ack_incomplete")
        if item["name"] == LEGACY_TECHNICAL_LOCATOR_NAME:
            item["name"] = COURT_SKILL_NAME
            item["ack_name"] = COURT_SKILL_NAME
        previous = by_name.get(item["name"])
        if previous is not None:
            if previous != item:
                raise ValueError("skill_binding_conflict")
            continue
        by_name[item["name"]] = item
        validated.append(item)
    if COURT_SKILL_NAME not in by_name:
        raise ValueError("required_court_skill_missing")
    court = by_name[COURT_SKILL_NAME]
    authoritative_court = SKILL_PATH.resolve()
    if Path(court["source"]).resolve() != authoritative_court:
        raise ValueError("court_skill_source_mismatch")
    authoritative_hash = sha256_file(authoritative_court).lower()
    if court["sha256"] != authoritative_hash or court["ack_sha256"] != authoritative_hash:
        raise ValueError("required_skill_hash_mismatch")
    return validated


def _bounded_profile_paths(value: object, field: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{field}_unbounded")
    normalized: list[str] = []
    for raw in value:
        if not isinstance(raw, str) or raw != raw.strip() or not raw:
            raise ValueError(f"{field}_unbounded")
        if (
            "\\" in raw
            or "\x00" in raw
            or raw.startswith("/")
            or re.match(r"^[A-Za-z]:", raw)
        ):
            raise ValueError(f"{field}_unbounded")
        parts = PurePosixPath(raw).parts
        if not parts or any(part in {"", ".", ".."} or ":" in part for part in parts):
            raise ValueError(f"{field}_unbounded")
        normalized.append("/".join(parts))
    if len({item.casefold() for item in normalized}) != len(normalized):
        raise ValueError(f"{field}_unbounded")
    return normalized


def _canonical_child_binding_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("child_office_binding_digest_non_canonical_value")
            normalized[key] = _canonical_child_binding_value(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonical_child_binding_value(item) for item in value]
    raise ValueError("child_office_binding_digest_non_canonical_value")


def canonical_child_office_binding_sha256(binding: Mapping[str, object]) -> str:
    """Hash every field of one complete child-office binding as canonical JSON."""

    if not isinstance(binding, Mapping) or not binding:
        raise ValueError("child_office_binding_digest_binding_required")
    child_profile = binding.get("child_profile")
    if (
        not isinstance(child_profile, Mapping)
        or child_profile.get("schema") != "court.child_office_profile.v1"
    ):
        raise ValueError("child_office_binding_digest_child_profile_required")
    normalized = _canonical_child_binding_value(binding)
    try:
        payload = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "child_office_binding_digest_non_canonical_value"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def build_child_office_profile(
    binding: Mapping[str, object],
    *,
    child_role: str,
    profile_sha256: str,
    dossier_sha256: str,
    skill_sha256: str,
    dispatch_context_packet_sha256: str,
    semantic_receipt_sha256: str,
    invariant_capsule_sha256: str,
    expires_at_utc: str,
) -> dict[str, object]:
    """Generate one bounded non-canonical ministry child profile."""

    if not isinstance(binding, Mapping):
        raise ValueError("child_profile_binding_required")
    forbidden = {
        "second_invariant_capsule",
        "second_semantic_receipt",
        "child_charter",
        "charter_override",
        "semantic_authority_override",
    }
    if forbidden.intersection(str(key) for key in binding):
        raise ValueError("child_profile_semantic_authority_override")
    role = str(binding.get("role") or "").strip().lower()
    owner = str(binding.get("owner_role") or "").strip().lower()
    superior = str(binding.get("direct_superior") or "").strip().lower()
    instance_kind = str(binding.get("instance_kind") or "").strip().lower()
    if role not in MINISTRY_ROLES or owner != role or superior != owner:
        raise ValueError("child_profile_owner_mismatch")
    if binding.get("canonical_authority") is not False:
        raise ValueError("child_profile_canonical_authority_forbidden")
    if instance_kind not in {"worker", "craftsman", "office_worker_instance"}:
        raise ValueError("child_profile_instance_kind_invalid")
    normalized_child_role = str(child_role or "").strip()
    if (
        not normalized_child_role
        or normalized_child_role.casefold() in OFFICE_ASSIGNMENT_IDENTITIES
        or normalized_child_role.casefold() == "user"
    ):
        raise ValueError("child_profile_role_invalid")
    text_fields = {
        "office_instance_id": binding.get("office_instance_id")
        or binding.get("instance_id"),
        "bounded_mandate": binding.get("bounded_mandate"),
        "expected_result": binding.get("expected_result"),
        "task_id": binding.get("task_id"),
        "dispatch_uid": binding.get("dispatch_uid"),
        "shard_id": binding.get("shard_id"),
        "terminal_condition": binding.get("terminal_condition"),
        "expires_at_utc": expires_at_utc,
    }
    normalized_text: dict[str, str] = {}
    for field, raw in text_fields.items():
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"child_profile_{field}_required")
        normalized_text[field] = raw.strip()
    attempt = binding.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("child_profile_attempt_invalid")
    return {
        "schema": "court.child_office_profile.v1",
        "child_role": normalized_child_role,
        "role_key": role,
        "office_instance_id": normalized_text["office_instance_id"],
        "owner_role": owner,
        "direct_superior": superior,
        "canonical_authority": False,
        "instance_kind": instance_kind,
        "bounded_mandate": normalized_text["bounded_mandate"],
        "expected_result": normalized_text["expected_result"],
        "read_scope": _bounded_profile_paths(binding.get("read_scope"), "read_scope"),
        "write_set": _bounded_profile_paths(binding.get("write_set"), "write_set"),
        "task_id": normalized_text["task_id"],
        "dispatch_uid": normalized_text["dispatch_uid"],
        "shard_id": normalized_text["shard_id"],
        "attempt": attempt,
        "profile_sha256": _canonical_sha256(profile_sha256, "profile_sha256"),
        "dossier_sha256": _canonical_sha256(dossier_sha256, "dossier_sha256"),
        "skill_sha256": _canonical_sha256(skill_sha256, "skill_sha256"),
        "expires_at_utc": normalized_text["expires_at_utc"],
        "terminal_condition": normalized_text["terminal_condition"],
        "dispatch_context_packet_schema": "court.semantic.dispatch_context_packet.v1",
        "dispatch_context_packet_sha256": _canonical_sha256(
            dispatch_context_packet_sha256,
            "dispatch_context_packet_sha256",
        ),
        "semantic_receipt_sha256": _canonical_sha256(
            semantic_receipt_sha256,
            "semantic_receipt_sha256",
        ),
        "invariant_capsule_schema": "court.semantic.invariant_capsule.v1",
        "invariant_capsule_sha256": _canonical_sha256(
            invariant_capsule_sha256,
            "invariant_capsule_sha256",
        ),
    }


def build_office_assignment_binding(
    *,
    role_key: str,
    collaboration_task_name: str,
    court_agent_id: str,
    requires_gongjiang: bool,
    skill_requirements: list[dict[str, str]],
    profile_root: Path = PROFILE_ROOT,
) -> dict[str, object]:
    profile = load_standing_profile_binding(role_key, profile_root=profile_root)
    official_head, task_prefix, agent_prefix, _, _ = OFFICE_ASSIGNMENT_IDENTITIES[role_key]
    office_name_token = task_prefix
    if requires_gongjiang:
        if role_key != "gongbu":
            raise ValueError("missing_gongjiang")
        official_head += "-GongJiang"
        office_name_token += "_gongjiang"
        agent_prefix += "-gongjiang"
    task_suffix = collaboration_task_name[len(office_name_token) + 1 :] if isinstance(collaboration_task_name, str) and collaboration_task_name.startswith(office_name_token + "_") else ""
    if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", task_suffix):
        raise ValueError("missing_gongjiang" if requires_gongjiang else "office_name_mismatch")
    agent_suffix = court_agent_id[len(agent_prefix) + 1 :] if isinstance(court_agent_id, str) and court_agent_id.startswith(agent_prefix + "-") else ""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", agent_suffix):
        raise ValueError("office_name_mismatch")
    skills = validate_skill_requirements(skill_requirements)
    assignment_direct_superior = "gongbu" if requires_gongjiang else profile["direct_superior"]
    return {
        "role_key": role_key,
        "official_name_head": official_head,
        "office_name_token": office_name_token,
        "task_name_prefix": office_name_token,
        "agent_id_prefix": agent_prefix,
        "collaboration_task_name": collaboration_task_name,
        "court_agent_id": court_agent_id,
        "name_binding": "PASSED",
        "profile_binding": "PASSED",
        "skill_binding": "PASSED",
        **profile,
        "direct_superior": assignment_direct_superior,
        "required_skill_bindings": skills,
        "office_execution_ready": True,
    }


def _normalized_role(role: str) -> str:
    normalized = str(role).strip().lower()
    if normalized != role or not ROLE_RE.fullmatch(normalized):
        raise ValueError("role identity must be an exact standing profile key, not a task/thread path")
    if normalized not in OFFICE_ASSIGNMENT_IDENTITIES:
        raise ValueError(f"standing profile unavailable: {normalized}")
    return normalized


def resolve_office_dossier_locator(
    role: str,
    *,
    carrier_kind: str = "child_agent",
    supercc_enabled: bool = False,
) -> PurePosixPath:
    normalized = _normalized_role(role)
    carrier = str(carrier_kind).strip()
    if carrier in ORDINARY_CARRIERS:
        return PurePosixPath("agents", "office-dossiers", normalized, "AGENTS.md")
    if carrier == SUPERCC_CLI_CARRIER:
        if not supercc_enabled:
            raise ValueError("supercc_experimental_cli_explicit_enable_required")
        return PurePosixPath("agents", "supercc-dossiers", normalized, "AGENTS.md")
    raise ValueError(f"unsupported office carrier: {carrier}")


def _profile(role: str, *, skill_root: Path = ROOT) -> tuple[Path, dict[str, object]]:
    normalized = _normalized_role(role)
    path = Path(skill_root).resolve() / "agents" / "standing-officials" / f"{normalized}.toml"
    if not path.is_file() or tomllib is None:
        raise ValueError(f"standing profile unavailable: {normalized}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    profile = data.get("profile")
    if not isinstance(profile, dict) or str(profile.get("role_key") or "") != normalized:
        raise ValueError(f"standing profile identity mismatch: {normalized}")
    return path, profile


def build_preload_manifest(
    role: str,
    *,
    carrier_kind: str = "child_agent",
    supercc_enabled: bool = False,
    skill_root: Path = ROOT,
) -> OfficePreloadManifest:
    dossier_locator = resolve_office_dossier_locator(
        role,
        carrier_kind=carrier_kind,
        supercc_enabled=supercc_enabled,
    )
    root = Path(skill_root).resolve()
    profile_path, profile = _profile(role, skill_root=root)
    dossier = root.joinpath(*dossier_locator.parts)
    skill_path = root / "SKILL.md"
    if not dossier.is_file():
        raise ValueError(
            "supercc_office_dossier_missing"
            if carrier_kind == SUPERCC_CLI_CARRIER
            else "ordinary_office_dossier_missing"
        )
    if not skill_path.is_file():
        raise ValueError("court_skill_missing")
    office_zh = str(profile.get("office_zh") or "").strip()
    direct_superior = str(profile.get("direct_superior") or "").strip()
    if not office_zh or not direct_superior:
        raise ValueError(f"profile identity fields missing for {role}")
    return OfficePreloadManifest(
        role_key=role,
        carrier_kind=carrier_kind,
        office_zh=office_zh,
        direct_superior=direct_superior,
        profile_source=PurePosixPath("agents", "standing-officials", f"{role}.toml").as_posix(),
        profile_hash=sha256_file(profile_path),
        dossier_path=dossier_locator.as_posix(),
        dossier_hash=sha256_file(dossier),
        court_skill_name=COURT_SKILL_NAME,
        court_skill_path="SKILL.md",
        court_skill_hash=sha256_file(skill_path),
    )


def build_spawn_contract(
    role: str,
    *,
    carrier_kind: str = "child_agent",
    assignment: str,
    task_focus: str,
    complexity: str,
    risk: str,
    ambiguity: str,
    transport: str,
    allowed_actions: list[str] | tuple[str, ...],
    forbidden_actions: list[str] | tuple[str, ...],
    evidence_contract: str,
    stop_conditions: list[str] | tuple[str, ...],
) -> dict[str, object]:
    manifest = build_preload_manifest(role, carrier_kind=carrier_kind)
    normalized_assignment = str(assignment).strip()
    if not normalized_assignment or not str(evidence_contract).strip():
        raise ValueError("assignment and evidence_contract are required")
    if role in MINISTRY_ROLES:
        folded_assignment = normalized_assignment.casefold()
        forbidden_authority_claim = any(
            (
                "三省" in normalized_assignment and "审计" in normalized_assignment,
                "门下" in normalized_assignment and "最终复核" in normalized_assignment,
                "代太子" in normalized_assignment and "统筹全局" in normalized_assignment,
                "three departments" in folded_assignment and "audit" in folded_assignment,
                "menxia" in folded_assignment and "final review" in folded_assignment,
                "taizi" in folded_assignment and "global coordinator" in folded_assignment,
            )
        )
        if forbidden_authority_claim:
            raise PermissionError("ministry_assignment_exceeds_office_authority")
    contract = asdict(manifest)
    model_route = route_office_model(
        transport=transport,
        role=role,
        assignment=normalized_assignment,
        task_focus=task_focus,
        complexity=complexity,
        risk=risk,
        ambiguity=ambiguity,
    )
    contract.update(
        current_assignment=normalized_assignment,
        task_focus=str(task_focus).strip(),
        task_evaluation={"complexity": complexity, "risk": risk, "ambiguity": ambiguity},
        transport=str(transport).strip(),
        model_route=model_route,
        allowed_actions=[str(item).strip() for item in allowed_actions if str(item).strip()],
        forbidden_actions=[str(item).strip() for item in forbidden_actions if str(item).strip()],
        evidence_contract=str(evidence_contract).strip(),
        stop_conditions=[str(item).strip() for item in stop_conditions if str(item).strip()],
        preload_ack_required=True,
    )
    if not contract["allowed_actions"] or not contract["forbidden_actions"] or not contract["stop_conditions"]:
        raise ValueError("allowed_actions, forbidden_actions, and stop_conditions are required")
    return contract


def validate_preload_ack(
    manifest: OfficePreloadManifest,
    ack: dict[str, object],
    *,
    model_route: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized_ack = dict(ack)
    for field in ("profile_hash", "dossier_hash", "court_skill_hash"):
        normalized_ack[field] = _canonical_sha256(normalized_ack.get(field), field)
    expected = {
        "schema": manifest.preload_ack_schema,
        "preload_status": "PASSED",
        "role_key": manifest.role_key,
        "office_zh": manifest.office_zh,
        "direct_superior": manifest.direct_superior,
        "profile_hash": manifest.profile_hash,
        "dossier_hash": manifest.dossier_hash,
        "court_skill_hash": manifest.court_skill_hash,
        "agent_dossier_loaded": "YES",
    }
    mismatched = [key for key, value in expected.items() if normalized_ack.get(key) != value]
    loaded = normalized_ack.get("loaded_skills")
    if isinstance(loaded, list):
        loaded = [
            COURT_SKILL_NAME
            if item == LEGACY_TECHNICAL_LOCATOR_NAME
            else item
            for item in loaded
        ]
        loaded = list(dict.fromkeys(loaded))
        normalized_ack["loaded_skills"] = loaded
    if not isinstance(loaded, list) or manifest.court_skill_name not in loaded:
        mismatched.append("loaded_skills")
    if mismatched:
        raise ValueError("preload ack mismatch: " + ", ".join(sorted(set(mismatched))))
    if model_route is not None:
        validate_model_route_ack(model_route, normalized_ack)
    return {**normalized_ack, "loaded_skills": list(loaded)}
