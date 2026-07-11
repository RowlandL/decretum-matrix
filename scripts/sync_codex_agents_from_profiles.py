"""Render structured standing-official profiles into Codex agent role files."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]

from shiguan_paths import reference_path


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

PROFILE_FIELDS = (
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

COMPACT_PROFILE_FIELDS = (
    "role_key",
    "office_zh",
    "direct_superior",
    "duty",
    "can_do",
    "report_contract",
    "evidence_contract",
    "heartbeat_contract",
    "profile_version",
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

AGENT_DOSSIER_ROOT = Path("agents") / "supercc-dossiers"
AGENT_DOSSIER_FILE = "AGENTS.md"
PRELOAD_CONTRACT_VERSION = "court.office.preload_ack.v1"
AGENT_DOSSIER_POLICY = (
    "Installed .codex/agents TOML files are native auto-discovered role files and must remain "
    "one-file-per-agent and model-neutral. Use the referenced AGENTS.md dossier as the long role "
    "mandate for ordinary and visible transports. If it cannot be read and "
    "acknowledged as agent_dossier_loaded=YES, preload fails and the office "
    "must not enter running."
)
OFFICE_VOICE_POLICY = (
    "Office voice: act autonomously only inside this office mandate; report "
    "upward through the direct superior; refer to the acting subject by "
    "office_zh/官署代称, not first person (`我`, `我会`, `我已经`, `I`) or a generic "
    "`assistant` label."
)


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def codex_skill_root() -> Path:
    return codex_home() / "skills" / "court-capability-router"


def agent_template_skill_root() -> Path:
    normative = Path.home() / ".agents" / "skills" / "court-capability-router"
    return normative if (normative / "agents" / "standing-officials").exists() else skill_root()


def template_root() -> Path:
    return agent_template_skill_root() / "agents" / "standing-officials"


def installed_agents_root() -> Path:
    return codex_home() / "agents"


def backup_root() -> Path:
    return reference_path("host-capability-backups", "codex-agent-roles")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_toml(path: Path) -> dict[str, object]:
    if tomllib is None:
        raise RuntimeError("tomllib unavailable; Python 3.11+ required")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def agent_dossier_path(role: str) -> Path:
    return agent_template_skill_root() / AGENT_DOSSIER_ROOT / role / AGENT_DOSSIER_FILE


def render_agent_dossier_block(role: str) -> list[str]:
    path = agent_dossier_path(role)
    skill = agent_template_skill_root() / "SKILL.md"
    exists = path.exists()
    return [
        "Office dossier / mode-neutral preload manifest:",
        f"- preload_contract_version: {PRELOAD_CONTRACT_VERSION}",
        f"- agent_dossier_path: {path}",
        f"- agent_dossier_hash: {sha256_file(path) if exists else 'missing'}",
        f"- court_skill_path: {skill}",
        f"- court_skill_hash: {sha256_file(skill) if skill.exists() else 'missing'}",
        "- preload_ack: required before the office lifecycle may enter running.",
        "- agent_dossier_loaded: report exactly YES or NO; only YES with matching hashes passes preload.",
        "- loaded_skills: must include court-capability-router in the preload ack.",
        f"- ordinary_super_agent_md_policy: {AGENT_DOSSIER_POLICY}",
        f"- office_voice_policy: {OFFICE_VOICE_POLICY}",
        "- superCC: terminal-visible Codex offices start with this dossier directory as cwd, so AGENTS.md is auto-loaded.",
        "- ordinary super: `/root/*` is only a collaboration thread address. The parent must dispatch an explicit role_key plus this dossier/profile/skill manifest and require the first preload ack.",
        "- Codex model route: V1 binds agent_type only; V2 hides reserved metadata; both inherit the main model/effort and keep this role file model-neutral.",
        "- Claude Code model route: no office override; inherit the main thread model.",
        "- Hermes model route: no office override in this phase; inherit the main profile model and defer detailed profile design.",
    ]


def render_profile_block(template_path: Path, profile: dict[str, object]) -> str:
    computed_hash = sha256_file(template_path)
    role = str(profile.get("role_key", template_path.stem)).strip() or template_path.stem
    lines = [
        "Standing profile/soul compact manifest:",
        f"- profile_source: {template_path}",
        f"- profile_hash: {computed_hash}",
    ]
    for field in COMPACT_PROFILE_FIELDS:
        value = str(profile.get(field, "")).strip()
        lines.append(f"- {field}: {value}")
    lines.extend(
        [
            "",
            *render_agent_dossier_block(role),
            "",
            "",
            "Installed Codex role schema:",
            "- This file is a native auto-discovered Codex agent role file rendered with identity and developer instructions only.",
            "- Keep it model-neutral: task evaluation records a recommendation, while the compatible V2 model-visible spawn inherits the main thread model and effort; do not fix a model in this file.",
            "- Do not add [profile] or other tables under .codex/agents.",
            "- Do not merge multiple Codex custom agents into one TOML; Codex role discovery expects separate role files.",
            "- The structured profile source remains agents/standing-officials/*.toml.",
        ]
    )
    return "\n".join(lines)


def rendered_agent_data(template_path: Path) -> dict[str, str]:
    data = read_toml(template_path)
    profile = data.get("profile")
    if not isinstance(profile, dict):
        raise ValueError(f"{template_path.name}: missing [profile]")
    name = data.get("name")
    description = data.get("description")
    developer_instructions = data.get("developer_instructions")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{template_path.name}: missing string name")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{template_path.name}: missing string description")
    if not isinstance(developer_instructions, str) or not developer_instructions.strip():
        raise ValueError(f"{template_path.name}: missing string developer_instructions")
    rendered_instructions = (
        developer_instructions.rstrip()
        + "\n\n"
        + render_profile_block(template_path, profile)
        + "\n"
    )
    return {
        "name": name,
        "description": description,
        "developer_instructions": rendered_instructions,
    }


def render_agent_toml(template_path: Path) -> str:
    data = rendered_agent_data(template_path)
    return "".join(f"{key} = {toml_string(data[key])}\n" for key in ("name", "description", "developer_instructions"))


def expected_rendered_hash(template_path: Path) -> str:
    return sha256_bytes(render_agent_toml(template_path).encode("utf-8"))


def unique_backup_dir(root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = root / f"agents-backup-{stamp}"
    suffix = 2
    while candidate.exists():
        candidate = root / f"agents-backup-{stamp}-{suffix}"
        suffix += 1
    return candidate


def backup_toml_tree(source: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=False)
    count = 0
    try:
        for path in sorted(source.glob("*.toml")) if source.exists() else []:
            target = destination / path.name
            data = path.read_bytes()
            with target.open("xb") as handle:
                handle.write(data)
            if target.read_bytes() != data:
                raise OSError(f"backup verification failed: {target}")
            target.chmod(stat.S_IREAD)
            if target.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                raise OSError(f"backup is not read-only: {target}")
            count += 1
    except Exception:
        for target in destination.glob("*.toml"):
            target.chmod(stat.S_IREAD)
        raise
    return count


def sync_agents(write: bool, only: set[str] | None = None) -> dict[str, object]:
    templates = template_root()
    agents = installed_agents_root()
    if not templates.exists():
        raise FileNotFoundError(f"standing profile root missing: {templates}")
    selected_profiles = [
        name for name in REQUIRED_PROFILE_FILES if only is None or name in only or Path(name).stem in only
    ]
    unknown_profiles = sorted(only - set(selected_profiles) - {Path(name).stem for name in selected_profiles}) if only else []
    if unknown_profiles:
        raise ValueError("unknown profile(s) for --only: " + ", ".join(unknown_profiles))

    backup_path: Path | None = None
    backed_up = 0
    source_profiles_backed_up = 0
    if write:
        agents.mkdir(parents=True, exist_ok=True)
        backup_path = unique_backup_dir(backup_root())
        backed_up = backup_toml_tree(agents, backup_path / "installed")
        source_profiles_backed_up = backup_toml_tree(templates, backup_path / "source-profiles")

    rows: list[dict[str, object]] = []
    written = 0
    unchanged = 0
    missing_templates: list[str] = []
    for name in selected_profiles:
        template = templates / name
        installed = agents / name
        if not template.exists():
            missing_templates.append(name)
            rows.append({"agent": name, "status": "missing_template", "template": str(template)})
            continue
        rendered = render_agent_toml(template)
        rendered_hash = sha256_bytes(rendered.encode("utf-8"))
        installed_hash = sha256_file(installed) if installed.exists() else None
        needs_write = installed_hash != rendered_hash
        if write and needs_write:
            installed.write_text(rendered, encoding="utf-8", newline="\n")
            written += 1
            installed_hash = rendered_hash
        else:
            unchanged += 0 if needs_write else 1
        rows.append(
            {
                "agent": name,
                "template": str(template),
                "installed": str(installed),
                "expected_rendered_hash": rendered_hash,
                "installed_hash": installed_hash,
                "status": "synced" if installed_hash == rendered_hash else "would_update",
            }
        )
    if missing_templates:
        raise FileNotFoundError("missing standing profile templates: " + ", ".join(missing_templates))
    return {
        "ok": True,
        "mode": "write" if write else "dry-run",
        "template_count": len(selected_profiles),
        "written": written,
        "unchanged": unchanged,
        "backup_path": str(backup_path) if backup_path else None,
        "backed_up": backed_up,
        "source_profiles_backed_up": source_profiles_backed_up,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write rendered roles into CODEX_HOME\\agents.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--only",
        nargs="*",
        help="Restrict sync to these profile filenames or stems, for example patrol-inspector.toml.",
    )
    args = parser.parse_args()
    try:
        result = sync_agents(write=args.write, only=set(args.only) if args.only else None)
    except Exception as exc:
        print(f"CODEX_AGENT_SYNC_FAILED {exc}")
        return 1
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "CODEX_AGENT_SYNC_OK "
            f"mode={result['mode']} template_count={result['template_count']} "
            f"written={result['written']} unchanged={result['unchanged']} "
            f"backed_up={result['backed_up']} backup_path={result['backup_path']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
