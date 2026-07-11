"""Mode-neutral office profile/dossier/skill preload manifests and acknowledgements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from court_model_router import route_office_model, validate_model_route_ack

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = ROOT / "agents" / "standing-officials"
DOSSIER_ROOT = ROOT / "agents" / "supercc-dossiers"
SKILL_PATH = ROOT / "SKILL.md"
ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PRELOAD_ACK_SCHEMA = "court.office.preload_ack.v1"


@dataclass(frozen=True)
class OfficePreloadManifest:
    role_key: str
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


def _profile(role: str) -> tuple[Path, dict[str, object]]:
    normalized = str(role).strip().lower()
    if normalized != role or not ROLE_RE.fullmatch(normalized):
        raise ValueError("role identity must be an exact standing profile key, not a task/thread path")
    path = PROFILE_ROOT / f"{normalized}.toml"
    if not path.is_file() or tomllib is None:
        raise ValueError(f"standing profile unavailable: {normalized}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    profile = data.get("profile")
    if not isinstance(profile, dict) or str(profile.get("role_key") or "") != normalized:
        raise ValueError(f"standing profile identity mismatch: {normalized}")
    return path, profile


def build_preload_manifest(role: str) -> OfficePreloadManifest:
    profile_path, profile = _profile(role)
    dossier = DOSSIER_ROOT / role / "AGENTS.md"
    if not dossier.is_file() or not SKILL_PATH.is_file():
        raise ValueError(f"profile/dossier/skill preload source missing for {role}")
    office_zh = str(profile.get("office_zh") or "").strip()
    direct_superior = str(profile.get("direct_superior") or "").strip()
    if not office_zh or not direct_superior:
        raise ValueError(f"profile identity fields missing for {role}")
    return OfficePreloadManifest(
        role_key=role,
        office_zh=office_zh,
        direct_superior=direct_superior,
        profile_source=str(profile_path.resolve()),
        profile_hash=sha256_file(profile_path),
        dossier_path=str(dossier.resolve()),
        dossier_hash=sha256_file(dossier),
        court_skill_name="court-capability-router",
        court_skill_path=str(SKILL_PATH.resolve()),
        court_skill_hash=sha256_file(SKILL_PATH),
    )


def build_spawn_contract(
    role: str,
    *,
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
    manifest = build_preload_manifest(role)
    if not str(assignment).strip() or not str(evidence_contract).strip():
        raise ValueError("assignment and evidence_contract are required")
    contract = asdict(manifest)
    model_route = route_office_model(
        transport=transport,
        role=role,
        assignment=assignment,
        task_focus=task_focus,
        complexity=complexity,
        risk=risk,
        ambiguity=ambiguity,
    )
    contract.update(
        current_assignment=str(assignment).strip(),
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
    if not isinstance(loaded, list) or manifest.court_skill_name not in loaded:
        mismatched.append("loaded_skills")
    if mismatched:
        raise ValueError("preload ack mismatch: " + ", ".join(sorted(set(mismatched))))
    if model_route is not None:
        validate_model_route_ack(model_route, normalized_ack)
    return {**normalized_ack, "loaded_skills": list(loaded)}
