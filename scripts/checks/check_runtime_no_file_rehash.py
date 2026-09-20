"""Normal identity preload and role generation retain required reads and case binding."""
from __future__ import annotations
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import zlib
from unittest.mock import patch
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import court_office_bootstrap as bootstrap
import sync_codex_agents_from_profiles as roles
from checks.installed_identity_fixture import write_identity, write_skill
from checks import check_codex_agent_roles as role_check


def rejected(action, text):
    try:
        action()
    except ValueError as exc:
        assert text in str(exc), str(exc)
        return
    raise AssertionError("missing rejection: " + text)


def main() -> int:
    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)
        # Fixture construction pins the installed identity before the normal
        # runtime no-rehash monitor is active. The existing fixture hash call
        # is exercised below as a sensitivity negative control.
        write_skill(root)
        for name in ("new", "md5", "sha1", "sha224", "sha256", "sha384", "sha512", "blake2b", "blake2s"):
            stack.enter_context(patch.object(hashlib, name, side_effect=AssertionError("normal identity calculation")))
        stack.enter_context(patch.object(zlib, "crc32", side_effect=AssertionError("normal identity calculation")))
        normal_manifest_builder = bootstrap.build_preload_manifest

        def injected_preload(*args, **kwargs):
            manifest = normal_manifest_builder(*args, **kwargs)
            # Inject the existing identity writer only for this one normal
            # preload call. Its existing hashlib.sha256 path must be caught by
            # the active monitor, then the patch is removed before 14-role run.
            write_identity(root, ["sensitivity-negative-control"])
            return manifest

        try:
            with patch.object(bootstrap, "build_preload_manifest", side_effect=injected_preload):
                bootstrap.build_preload_manifest(
                    "taizi", skill_root=root, court_code="COURT-FIXTURE-1"
                )
        except AssertionError as exc:
            assert str(exc) == "normal identity calculation"
        else:
            raise AssertionError("hash monitor failed to catch existing preload identity call")
        stack.enter_context(patch.object(roles, "agent_template_skill_root", return_value=root))
        stack.enter_context(patch.object(role_check, "validate_codex_multi_agent_config", return_value={"ok": True}))
        cards = root / "native-roles"
        cards.mkdir()
        for name in roles.REQUIRED_PROFILE_FILES:
            role = Path(name).stem
            template = root / "agents" / "standing-officials" / name
            rendered = roles.render_agent_toml(template)
            assert not re.search(r"hash|digest|sha256|摘要", rendered, re.IGNORECASE)
            assert "court.office.preload_ack.v1" in rendered and "PENDING" in rendered and "court_code" in rendered
            order = [rendered.index(value) for value in ("1. installed_skill_full_read", "2. own_profile_dossier_full_read", "3. child_preload_acceptance_returned", "4. parent_preload_ack_accepted", "5. business_cli_mcp")]
            assert order == sorted(order)
            (cards / name).write_text(rendered, encoding="utf-8")
            assert not role_check.schema_errors(cards / name)
            manifest = bootstrap.build_preload_manifest(role, skill_root=root, court_code="COURT-FIXTURE-1")
            assert manifest.preload_ack_schema == "court.office.preload_ack.v1"
            assert set(asdict(manifest)) == {"role_key", "carrier_kind", "office_zh", "direct_superior", "profile_source", "dossier_path", "court_skill_name", "court_skill_path", "startup_guide_path", "court_code", "preload_ack_schema"}
            ack = {"schema": manifest.preload_ack_schema, "preload_status": "PASSED", "role_key": role, "office_zh": manifest.office_zh, "direct_superior": manifest.direct_superior, "profile_source": manifest.profile_source, "dossier_path": manifest.dossier_path, "court_skill_path": manifest.court_skill_path, "startup_guide_path": manifest.startup_guide_path, "startup_guide_loaded": "YES", "court_code": manifest.court_code, "agent_dossier_loaded": "YES", "loaded_skills": ["decretum-matrix"]}
            bootstrap.validate_preload_ack(manifest, ack)
            rejected(lambda: bootstrap.validate_preload_ack(manifest, {**ack, "court_code": "wrong-case"}), "court_code")
            rejected(lambda: bootstrap.validate_preload_ack(manifest, {**ack, "agent_dossier_loaded": "NO"}), "agent_dossier_loaded")
            rejected(lambda: bootstrap.validate_preload_ack(bootstrap.build_preload_manifest(role, skill_root=root), ack), "preload_court_code_required")
        check = role_check.validate_installed_agents(cards, root / "agents" / "standing-officials")
        assert check["ok"] and check["required_count"] == 14, check
    print("RUNTIME_NO_FILE_REHASH_OK ordinary_anchors=14 schema_preserved=true wrong_case_rejected=true reads_required=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
