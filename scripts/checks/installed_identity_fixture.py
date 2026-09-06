"""Pure, fixed-value install identities for isolated developer checks."""

import hashlib
import json
from pathlib import Path

from court_office_bootstrap import INSTALLED_PRELOAD_IDENTITY, OFFICE_ASSIGNMENT_IDENTITIES

FIXTURE_DIGEST = "a" * 64


def write_identity(root: Path, paths: list[str]) -> None:
    body = {
        "schema": "court.installed_preload_identity.v1",
        "authority": "installer",
        "status": "INSTALLATION_PINNED",
        "file_sha256": {path: FIXTURE_DIGEST for path in paths},
    }
    body["identity_sha256"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    path = root / INSTALLED_PRELOAD_IDENTITY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def write_skill(root: Path) -> None:
    (root / "SKILL.md").write_text("# Isolated skill fixture\n", encoding="utf-8")
    paths = ["SKILL.md"]
    for role, (_, _, _, office, superior) in OFFICE_ASSIGNMENT_IDENTITIES.items():
        relative = f"agents/standing-officials/{role}.toml"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'name = "{role}"\n[profile]\nrole_key = "{role}"\noffice_zh = "{office}"\ndirect_superior = "{superior}"\npreload_contract_version = "court.office.preload_ack.v1"\n', encoding="utf-8")
        paths.append(relative)
        for carrier in ("office-dossiers", "supercc-dossiers"):
            relative = f"agents/{carrier}/{role}/AGENTS.md"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# Fixture\n- role: {role}\n", encoding="utf-8")
            paths.append(relative)
    write_identity(root, paths)

