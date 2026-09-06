"""Exercise transactional sync main with isolated installed profiles and real role writes."""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sync_active_copies as sync
import sync_codex_agents_from_profiles as roles
from checks import installed_identity_fixture as fixture


class TransactionalRolesTests(unittest.TestCase):
    def run_branch(self, failure: str = "") -> None:
        with tempfile.TemporaryDirectory(prefix="transactional-roles-") as temporary:
            root = Path(temporary)
            home, source, staged = root / "home", root / "source", root / "staged"
            source.mkdir()
            staged.mkdir()

            def fixed_identity(path: Path, paths: list[str]) -> None:
                destination = path / fixture.INSTALLED_PRELOAD_IDENTITY
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps({
                    "schema": "court.installed_preload_identity.v1", "authority": "installer",
                    "status": "INSTALLATION_PINNED", "identity_sha256": "a" * 64,
                    "file_sha256": {name: "a" * 64 for name in paths},
                }), encoding="utf-8")

            with patch.object(fixture, "write_identity", side_effect=fixed_identity):
                fixture.write_skill(staged)
            canonical = home / ".agents" / "skills" / "decretum-matrix"
            codex = home / ".codex" / "skills" / "decretum-matrix"
            targets = [canonical, codex]
            for target in targets:
                manifest = target / sync.PROJECTION_MANIFEST_RELATIVE
                manifest.parent.mkdir(parents=True)
                manifest.write_text("{}", encoding="utf-8")
            cards = home / ".codex" / "agents"
            cards.mkdir(parents=True)
            originals = {}
            for name in roles.REQUIRED_PROFILE_FILES:
                originals[name] = f"# previous role {name}\n".encode()
                (cards / name).write_bytes(originals[name])
            backups = root / "existing-role-backups"
            install_backup = root / "installer-backup"
            install_backup.mkdir()
            (install_backup / "manifest.json").write_text("{}", encoding="utf-8")
            installer_result = {
                "ok": True, "projection_counts": {"create": 1, "replace": 1, "delete": 0},
                "backup_root": str(install_backup), "backup_manifest": str(install_backup / "manifest.json"),
            }
            receipt = {"selection_policy": "receipt", "selected_roots": [str(p) for p in targets],
                       "current_tool": "codex", "current_tool_root": str(codex), "explicit_extra_targets": []}
            events = []

            def install(**request):
                self.assertEqual(request["home_root"], home)
                self.assertFalse((canonical / "agents" / "standing-officials").exists())
                shutil.copytree(staged, canonical, dirs_exist_ok=True)
                events.append("installed")
                return installer_result

            real_sync = roles.sync_agents
            real_write = Path.write_text
            writes = 0

            def interrupted_write(path, *args, **kwargs):
                nonlocal writes
                if path.parent == cards:
                    writes += 1
                    if writes == 2:
                        raise KeyError("injected second role write failure")
                return real_write(path, *args, **kwargs)

            def role_sync(*, write):
                self.assertTrue(events and events[0] == "installed")
                events.append("write" if write else "plan")
                if write and failure == "exception":
                    with patch.object(Path, "write_text", interrupted_write):
                        return real_sync(write=True)
                result = real_sync(write=write)
                return {**result, "ok": False} if write and failure == "returned_failure" else result

            output = io.StringIO()
            with ExitStack() as stack:
                stack.enter_context(patch.object(Path, "home", return_value=home))
                stack.enter_context(patch.object(roles, "codex_home", return_value=home / ".codex"))
                stack.enter_context(patch.object(roles, "backup_root", return_value=backups))
                stack.enter_context(patch.object(sync, "codex_role_backup_root", return_value=backups))
                stack.enter_context(patch.object(sync, "_load_verified_selected_roots", return_value=targets))
                stack.enter_context(patch.object(sync, "_latest_install_receipt", return_value=receipt))
                stack.enter_context(patch.object(sync, "install_current_agent_copy", side_effect=install))
                stack.enter_context(patch.object(sync, "sync_codex_agent_roles", side_effect=role_sync))
                stack.enter_context(patch.object(sync, "rendered_active_files", return_value={Path("SKILL.md"): b"fixture"}))
                stack.enter_context(patch.object(hashlib, "sha256", side_effect=AssertionError("installed file/pin rehash forbidden")))
                stack.enter_context(patch.object(sys, "argv", ["sync-active-copies", "--source", str(source), "--write", "--prune-obsolete", "--json"]))
                stack.enter_context(redirect_stdout(output))
                exit_status = sync.main()
            result = json.loads(output.getvalue())
            self.assertEqual(events, ["installed", "plan", "write"])
            self.assertEqual(result["installer_transaction"], installer_result)
            if failure:
                self.assertEqual(exit_status, 1)
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "FAIL_PARTIAL_APPLIED")
                self.assertTrue(result["partial_applied"] and result["recovery_required"])
                self.assertEqual(result["codex_agent_roles"]["status"], "FAIL")
                self.assertTrue(result["codex_agent_roles"]["backup_paths"])
                self.assertEqual(result["codex_agent_roles"]["backup_base"], str(backups))
                for backup in result["codex_agent_roles"]["backup_paths"]:
                    for name, previous in originals.items():
                        self.assertEqual((Path(backup) / "installed" / name).read_bytes(), previous)
            else:
                self.assertEqual(exit_status, 0)
                self.assertTrue(result["ok"])
                self.assertEqual(result["codex_agent_roles"]["status"], "APPLIED")
                self.assertEqual(result["codex_agent_roles"]["written"], 14)
                for name in roles.REQUIRED_PROFILE_FILES:
                    self.assertIn("ORDINARY_PRELOAD_ANCHOR", (cards / name).read_text(encoding="utf-8"))

    def test_transactional_main_syncs_installed_canonical_roles(self):
        self.run_branch()

    def test_role_write_exception_preserves_partial_state_and_existing_backups(self):
        self.run_branch("exception")

    def test_role_false_result_is_not_pass(self):
        self.run_branch("returned_failure")


if __name__ == "__main__":
    unittest.main()
