"""Validate superCC standing-official profile contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = ROOT / "agents" / "standing-officials"
DOSSIER_ROOT = ROOT / "agents" / "supercc-dossiers"

REQUIRED_PROFILE_FILES = (
    "taizi.toml",
    "zhongshu.toml",
    "menxia.toml",
    "shangshu.toml",
    "libu-hr.toml",
    "hubu.toml",
    "libu.toml",
    "bingbu.toml",
    "xingbu.toml",
    "gongbu.toml",
    "shiguan.toml",
    "shiguan-hermes.toml",
    "zaochao.toml",
    "patrol-inspector.toml",
)

REQUIRED_PROFILE_FIELDS = (
    "role_key",
    "office_zh",
    "direct_superior",
    "duty",
    "can_do",
    "cannot_do",
    "procedure",
    "authority_basis",
    "report_contract",
    "evidence_contract",
    "heartbeat_contract",
    "dispatch_channel_policy",
    "release_policy",
    "profile_version",
    "profile_hash",
    "preload_contract_version",
    "dispatch_selection_policy",
    "capacity_admission_policy",
    "runtime_visibility_policy",
    "ordinary_parallel_policy",
    "startup_latency_contract",
    "codex_model_routing_policy",
    "claude_model_inheritance_policy",
    "hermes_model_inheritance_policy",
)

EXPECTED_SUPERIORS = {
    "taizi": "user",
    "zhongshu": "taizi",
    "menxia": "taizi",
    "shangshu": "taizi",
    "libu-hr": "shangshu",
    "hubu": "shangshu",
    "libu": "shangshu",
    "bingbu": "shangshu",
    "xingbu": "shangshu",
    "gongbu": "shangshu",
    "shiguan": "taizi/menxia",
    "shiguan-hermes": "taizi/menxia",
    "zaochao": "taizi",
    "patrol-inspector": "taizi",
}

REQUIRED_TEXT = (
    "court-capability-router",
    "query_shiguan_index.py",
    "court-shiguan",
    "Office voice:",
)


FORBIDDEN_DOSSIER_TEXT = (
    "<truncated",
    "Default state: AWAKE_STATUS_ONLY for continuous inspection",
    "Show only a compact Markdown status table in the visible pane",
    "Default state: AWAKE for evidence indexing and memory bridge checks",
)


def read_toml(path: Path) -> dict[str, object]:
    if tomllib is None:
        raise AssertionError("tomllib unavailable; Python 3.11+ required")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise AssertionError(f"{path.name}: invalid TOML: {exc}") from exc


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_profile(path: Path) -> dict[str, object]:
    if not path.exists():
        raise AssertionError(f"{path.name}: missing")
    data = read_toml(path)
    profile = data.get("profile")
    if not isinstance(profile, dict):
        raise AssertionError(f"{path.name}: missing [profile]")
    missing = [field for field in REQUIRED_PROFILE_FIELDS if not str(profile.get(field, "")).strip()]
    if missing:
        raise AssertionError(f"{path.name}: missing profile fields: {', '.join(missing)}")
    if "Luna max" not in str(profile["codex_model_routing_policy"]):
        raise AssertionError(f"{path.name}: Codex model policy must preserve Luna's highest supported effort=max")
    if "inherit the main thread model" not in str(profile["claude_model_inheritance_policy"]):
        raise AssertionError(f"{path.name}: Claude model inheritance boundary missing")
    if "inherits the main profile model" not in str(profile["hermes_model_inheritance_policy"]):
        raise AssertionError(f"{path.name}: Hermes model inheritance boundary missing")

    role_key = str(profile["role_key"])
    expected_role = path.stem
    if role_key != expected_role:
        raise AssertionError(f"{path.name}: role_key {role_key!r} != {expected_role!r}")
    expected_superior = EXPECTED_SUPERIORS.get(role_key)
    if expected_superior and str(profile["direct_superior"]) != expected_superior:
        raise AssertionError(f"{path.name}: direct_superior {profile['direct_superior']!r} != {expected_superior!r}")

    text = path.read_text(encoding="utf-8", errors="replace")
    missing_text = [term for term in REQUIRED_TEXT if term not in text]
    if missing_text:
        raise AssertionError(f"{path.name}: missing capability access text: {', '.join(missing_text)}")
    if role_key == "patrol-inspector":
        for term in (
            "监察使",
            "silent_supervisor",
            "supercc_watchdog",
            "watchdog_process",
            "watchdog_log_jsonl",
            "watchdog_pid_file",
            "watchdog_daemon_start",
            "watchdog_daemon_stop",
            "watchdog_no_visible_window",
            "watchdog_actions",
            "watchdog_abnormal_roles",
            "legacy_patrol_visible_pane",
            "expected_silenced_roles",
            "taizi_stale_explanation",
        ):
            if term not in text:
                raise AssertionError(f"patrol-inspector.toml: missing {term} silent-supervisor contract")
    if role_key in {"taizi", "zhongshu", "menxia", "shangshu"} and "idle_receive" not in text:
        raise AssertionError(f"{path.name}: missing post-closeout idle_receive contract")
    if role_key == "shangshu" and "step plan" not in text:
        raise AssertionError("shangshu.toml: missing six-ministry step plan contract")
    if role_key == "taizi" and "fourteen-label" not in text:
        raise AssertionError("taizi.toml: missing superCC fourteen-label closeout contract")
    if role_key == "taizi" and "Do not speak directly to the user" in str(profile.get("cannot_do", "")):
        raise AssertionError("taizi.toml: cannot_do must not prohibit the user-facing Taizi from speaking to the user")
    return {
        "path": str(path),
        "role_key": role_key,
        "direct_superior": profile["direct_superior"],
        "profile_version": profile["profile_version"],
        "profile_hash": sha256_file(path),
    }


def validate_dossier(role_key: str) -> dict[str, object]:
    path = DOSSIER_ROOT / role_key / "AGENTS.md"
    if not path.exists():
        raise AssertionError(f"{role_key}: missing superCC dossier {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    for term in (
        "Mode-neutral Office Dossier",
        "preload_contract_version",
        "preload_ack",
        "agent_dossier_loaded=YES",
        "loaded_skills",
        "/root/",
    ):
        if term not in text:
            raise AssertionError(f"{role_key}: dossier missing mode-neutral preload term {term}")
    for term in FORBIDDEN_DOSSIER_TEXT:
        if term in text:
            raise AssertionError(f"{role_key}: forbidden dossier text: {term}")
    if role_key == "taizi":
        if "Do not address the user directly" in text:
            raise AssertionError("taizi dossier must preserve Taizi as the user-facing liaison")
        if "Do not call clarify for authority selection" in text:
            raise AssertionError("taizi dossier must allow Taizi to relay clarification questions")
        for term in (
            "user-facing",
            "三权",
            "approval/autonomous/super",
            "enter superCC only through its explicit separate runtime",
            "relay one plain clarification question",
        ):
            if term not in text:
                raise AssertionError(f"taizi dossier missing {term}")
    if role_key == "patrol-inspector":
        for term in (
            "idle_receive",
            "silent",
            "explicit bounded diagnostic",
            "routine supervision is silent supercc_watchdog.py evidence",
        ):
            if term not in text:
                raise AssertionError(f"patrol-inspector dossier missing {term}")
        if "AWAKE_NO_SILENCE assignment=none" in text:
            raise AssertionError("patrol-inspector dossier must not send AWAKE_NO_SILENCE without assignment")
    if role_key in {"shiguan", "shiguan-hermes"}:
        for term in ("non-visible", "silent", "until explicitly dispatched"):
            if term not in text:
                raise AssertionError(f"{role_key} dossier missing {term}")
        if "AWAKE_NO_SILENCE assignment=none" in text:
            raise AssertionError(f"{role_key} dossier must not send AWAKE_NO_SILENCE without assignment")
        if role_key == "shiguan-hermes" and "role: shiguan-hermes" not in text:
            raise AssertionError("shiguan-hermes dossier must preserve distinct role_key")
    return {
        "path": str(path),
        "role_key": role_key,
        "dossier_hash": sha256_file(path),
    }


def validate_all() -> dict[str, object]:
    profiles = [validate_profile(PROFILE_ROOT / name) for name in REQUIRED_PROFILE_FILES]
    dossiers = [validate_dossier(str(profile["role_key"])) for profile in profiles]
    return {
        "ok": True,
        "profile_root": str(PROFILE_ROOT),
        "profile_count": len(profiles),
        "profiles": profiles,
        "dossier_root": str(DOSSIER_ROOT),
        "dossier_count": len(dossiers),
        "dossiers": dossiers,
    }


def main() -> int:
    try:
        result = validate_all()
    except AssertionError as exc:
        print(f"SUPERCC_PROFILES_FAILED {exc}")
        return 1
    print(f"SUPERCC_PROFILES_OK count={result['profile_count']} root={result['profile_root']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
