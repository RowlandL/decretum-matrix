"""Isolated install production path followed by runtime no-rehash checks."""

from __future__ import annotations

import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import tempfile
from unittest.mock import patch

import court_office_bootstrap as bootstrap
import sync_codex_agents_from_profiles as roles
from checks.check_codex_agent_roles import validate_installed_agents
from checks.check_install_current_agent_copy import _fixture_manifest, _write_fixture_source
from checks.installed_identity_fixture import write_skill
from install_current_agent_copy import install_current_agent_copy
from court_open_fastpath import _role_preload


def rejected(action, text):
    try:
        action()
    except ValueError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError("missing rejection: " + text)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="no-file-rehash-") as temp:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        contract = _fixture_manifest()
        dossier = "agents/office-dossiers/gongbu/AGENTS.md"
        for name in ("shared_agents", "portable_current_tool"):
            for role in bootstrap.OFFICE_ASSIGNMENT_IDENTITIES:
                for relative in (f"agents/standing-officials/{role}.toml", f"agents/office-dossiers/{role}/AGENTS.md"):
                    if relative not in contract["projections"][name]:
                        contract["projections"][name].append(relative)
        projection = _write_fixture_source(source, manifest=contract)
        write_skill(source)
        # Exercise the real renderer and installer on synthetic files only.
        home = root / "home"
        result = install_current_agent_copy(
            source_root=source, home_root=home, current_tool="codex",
            explicit_tools=[], tool_roots={"codex": home / ".codex" / "skills" / "decretum-matrix"},
            projection_manifest=projection, write=True,
        )
        assert result["ok"], result
        active = home / ".agents" / "skills" / "decretum-matrix"
        identity_path = active / bootstrap.INSTALLED_PRELOAD_IDENTITY
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        assert bootstrap.INSTALLED_PRELOAD_IDENTITY not in identity["file_sha256"]
        assert result["install_receipt"]["preload_identity_manifest"] == bootstrap.INSTALLED_PRELOAD_IDENTITY
        active_contract = json.loads((active / "references/manifests/install-projection.v1.json").read_text(encoding="utf-8"))
        assert bootstrap.INSTALLED_PRELOAD_IDENTITY in active_contract["projections"]["shared_agents"]
        with patch.object(Path, "read_bytes", side_effect=AssertionError("runtime file bytes/hash read")), patch.object(bootstrap, "sha256_file", side_effect=AssertionError("bootstrap rehash")), patch.object(roles, "sha256_file", side_effect=AssertionError("role rehash")), patch.object(roles, "sha256_bytes", side_effect=AssertionError("rendered file rehash")), patch.object(roles, "agent_template_skill_root", return_value=active):
            # Pin consumption cannot disguise an installation recheck as a
            # canonical JSON object digest. No serialization or hash is needed.
            with patch.object(bootstrap.json, "dumps", side_effect=AssertionError("runtime pin serialization")), patch.object(bootstrap.hashlib, "sha256", side_effect=AssertionError("runtime pin rehash")):
                manifest = bootstrap.build_preload_manifest("gongbu", skill_root=active)
                assert bootstrap.installed_file_sha256(active / "SKILL.md", skill_root=active, expected_identity_sha256=identity["identity_sha256"]) == manifest.court_skill_hash
                rejected(lambda: bootstrap.installed_file_sha256(active / "SKILL.md", skill_root=active, expected_identity_sha256="0" * 64), "identity_binding_mismatch")
            assert manifest.court_skill_hash == identity["file_sha256"]["SKILL.md"]
            ack = {"schema": manifest.preload_ack_schema, "preload_status": "PASSED", "role_key": "gongbu", "office_zh": "工部", "direct_superior": "shangshu", "profile_hash": manifest.profile_hash, "dossier_hash": manifest.dossier_hash, "court_skill_hash": manifest.court_skill_hash, "agent_dossier_loaded": "YES", "loaded_skills": ["decretum-matrix"]}
            bootstrap.validate_preload_ack(manifest, ack)
            rejected(lambda: bootstrap.validate_preload_ack(manifest, {**ack, "profile_hash": "0" * 64}), "mismatch")
            template = active / manifest.profile_source
            rendered = roles.render_agent_toml(template)
            assert manifest.profile_hash in rendered and "do not run Get-FileHash" in rendered
            agent_files = root / "roles"
            agent_files.mkdir()
            expected_order = (
                "installed_skill_full_read", "own_profile_dossier_full_read",
                "child_preload_acceptance_returned", "parent_preload_ack_accepted",
                "business_cli_mcp",
            )
            for role in bootstrap.OFFICE_ASSIGNMENT_IDENTITIES:
                role_text = roles.render_agent_toml(template.parent / f"{role}.toml")
                data = roles.tomllib.loads(role_text)
                assert set(data) == {"name", "description", "developer_instructions"}
                assert data["name"] == role
                instructions = data["developer_instructions"]
                assert instructions.count("ORDINARY_PRELOAD_ANCHOR") == 1
                positions = [instructions.index(marker) for marker in expected_order]
                assert positions == sorted(positions)
                for required in (
                    "read the exact installed court_skill_path in full",
                    "profile_source and agent_dossier_path in full",
                    "using only the existing declared digest strings",
                    "Remain PENDING until both child preload acceptance has returned and parent preload ack has been accepted",
                    "only then enter running and invoke business CLI/MCP",
                    "do not run Get-FileHash, hashlib",
                    "pin JSON serialization/self-hash",
                    "Keep business P00, case, plan and receipt digests",
                ):
                    assert required in instructions, (role, required)
                (agent_files / f"{role}.toml").write_text(role_text, encoding="utf-8")
            assert len(list(agent_files.glob("*.toml"))) == len(bootstrap.OFFICE_ASSIGNMENT_IDENTITIES)
            role_result = validate_installed_agents(agent_files, template.parent)
            assert role_result["ok"], role_result
            row = next(row for row in role_result["sync_rows"] if row["agent"] == "gongbu.toml")
            assert row["status"] == "synced"
            with patch.object(roles, "template_root", return_value=template.parent), patch.object(roles, "installed_agents_root", return_value=agent_files):
                assert roles.sync_agents(False, only={"gongbu"})["rows"][0]["status"] == "synced"
            (active / "SKILL.md").write_bytes(b"# CRLF fixture\r\n")
            size = (active / "SKILL.md").stat().st_size
            preload = _role_preload(active, "gongbu", size, {"canonical_roles": {"gongbu": {"direct_superior": "shangshu"}}, "allowed_edges": []})
            assert preload.skill_bytes == len(b"# CRLF fixture\r\n")
            assert preload.profile_bytes == template.stat().st_size
            assert preload.dossier_bytes == (active / dossier).stat().st_size
            # Reads remain required; content changes do not trigger a hidden rehash.
            (active / "SKILL.md").write_text("# Changed fixture bytes\n", encoding="utf-8")
            assert bootstrap.build_preload_manifest("gongbu", skill_root=active).court_skill_hash == manifest.court_skill_hash
            identity["file_sha256"]["SKILL.md"] = "0" * 64
            identity_path.write_text(json.dumps(identity), encoding="utf-8")
            with patch.object(bootstrap.hashlib, "sha256", side_effect=AssertionError("runtime pin self-digest recheck")):
                declared_manifest = bootstrap.build_preload_manifest("gongbu", skill_root=active)
            assert declared_manifest.court_skill_hash == "0" * 64
            rejected(lambda: bootstrap.validate_preload_ack(declared_manifest, ack), "court_skill_hash")
            identity["file_sha256"] = []
            identity_path.write_text(json.dumps(identity), encoding="utf-8")
            rejected(lambda: bootstrap.build_preload_manifest("gongbu", skill_root=active), "identity_invalid")
            identity_path.write_text("{}", encoding="utf-8")
            rejected(lambda: bootstrap.build_preload_manifest("gongbu", skill_root=active), "identity_invalid")
            identity_path.unlink()
            rejected(lambda: bootstrap.build_preload_manifest("gongbu", skill_root=active), "identity_missing")
    print(f"RUNTIME_NO_FILE_REHASH_OK installation_fixture=production_renderer_and_transaction runtime_bytes_reads=0 mismatch_ack_rejected=true missing_pin_rejected=true ordinary_anchors={len(bootstrap.OFFICE_ASSIGNMENT_IDENTITIES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
