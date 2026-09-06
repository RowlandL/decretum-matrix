"""Temporary producer-shape fixtures for hash-free runtime compatibility."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import court_capability_recruitment as recruitment
import court_office_bootstrap as bootstrap
from commands import agent_runtime_probe as probe
from commands import sync_codex_agents_from_profiles as renderer
from checks.installed_identity_fixture import write_skill


@contextmanager
def no_file_hashes():
    original = hashlib.sha256
    def semantic_only(value=b"", *args, **kwargs):
        try:
            document = json.loads(value)
        except (UnicodeError, ValueError, TypeError):
            raise AssertionError("runtime hashed non-object/file material") from None
        if not isinstance(document, dict):
            raise AssertionError("runtime hashed non-object/file material")
        return original(value, *args, **kwargs)
    with patch.object(Path, "read_bytes", side_effect=AssertionError("runtime file bytes read")), patch.object(hashlib, "sha256", side_effect=semantic_only):
        yield


class InstallationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.root = self.area / "decretum-matrix"
        self.root.mkdir()
        # Matches the producer: SKILL.md, profiles and dossiers only. Native
        # role files, probe source, binaries and external capabilities get no pin.
        write_skill(self.root)
        self.templates = self.root / "agents" / "standing-officials"
        self.agents = self.area / ".codex" / "agents"
        self.agents.mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.object(probe, "skill_root", return_value=self.root).start()
        patch.object(renderer, "agent_template_skill_root", return_value=self.root).start()
        patch.object(recruitment, "__file__", str(self.root / "scripts" / "court_capability_recruitment.py")).start()
        patch.dict(sys.modules, {"check_codex_agent_roles": None}).start()
        with no_file_hashes():
            for template in self.templates.glob("*.toml"):
                (self.agents / template.name).write_text(renderer.render_agent_toml(template), encoding="utf-8")
        self.external = self.area / "external-capabilities"
        self.external.mkdir()
        self.capability = self.external / "SKILL.md"
        self.capability.write_text("---\nname: fixture\n---\nFixture capability", encoding="utf-8")

    def test_producer_shape_supports_external_native_roles(self):
        with no_file_hashes():
            result = probe.standing_profile_summary(self.agents, self.templates)
        self.assertTrue(result["validation"]["ok"])
        self.assertTrue(result["installed_role_schema"]["ok"])
        self.assertEqual(result["unsynced_count"], 0)
        for row in result["profile_install_sync_status"]:
            self.assertEqual(row["status"], "synced")
            self.assertIsNone(row["installed_hash"])
            self.assertEqual(row["hash_status"], "UNAVAILABLE_NOT_REHASHED")

    def test_native_content_drift_is_detected_without_hashing(self):
        with (self.agents / "gongbu.toml").open("a", encoding="utf-8") as stream:
            stream.write("# content changed\n")
        with no_file_hashes():
            result = probe.standing_profile_summary(self.agents, self.templates)
        self.assertEqual(result["unsynced_count"], 1)
        row = next(row for row in result["profile_install_sync_status"] if row["agent"] == "gongbu.toml")
        self.assertEqual(row["status"], "different")

    def test_model_override_still_rejected(self):
        with (self.agents / "gongbu.toml").open("a", encoding="utf-8") as stream:
            stream.write('model="fixed-model"\n')
        with no_file_hashes():
            result = probe.standing_profile_summary(self.agents, self.templates)
        self.assertEqual(result["malformed_count"], 1)
        self.assertFalse(result["installed_role_schema"]["ok"])

    def test_profile_superior_still_checked(self):
        profile = self.templates / "gongbu.toml"
        profile.write_text(profile.read_text(encoding="utf-8").replace('direct_superior = "shangshu"', 'direct_superior = "taizi"'), encoding="utf-8")
        with no_file_hashes():
            result = probe.standing_profile_summary(self.agents, self.templates)
        self.assertFalse(result["validation"]["ok"])

    def test_missing_native_file_still_unsynced(self):
        (self.agents / "gongbu.toml").unlink()
        with no_file_hashes():
            result = probe.standing_profile_summary(self.agents, self.templates)
        self.assertEqual(result["unsynced_count"], 1)
        row = next(row for row in result["profile_install_sync_status"] if row["agent"] == "gongbu.toml")
        self.assertEqual(row["status"], "missing_installed_agent")

    def test_external_binary_without_pin_keeps_path_version_result(self):
        executable = self.external / "codex.exe"
        executable.write_text("synthetic binary; never executed", encoding="utf-8")
        with patch.object(probe.shutil, "which", return_value=str(executable)), patch.object(probe, "_version_for_path", return_value="codex-cli 1.0"), patch.object(Path, "read_bytes", side_effect=AssertionError("binary rehash")):
            result = probe.resolve_codex_executable(include_binary_hash=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["version_match"])
        self.assertEqual(result["executable_hash_status"], "UNAVAILABLE_NOT_REHASHED")
        self.assertIsNone(result.get("executable_sha256"))
        self.assertEqual(result["errors"], [])

    def test_unpinned_harness_keeps_real_http_probe_observation(self):
        source = self.root / "scripts" / "commands" / "agent_runtime_probe.py"
        source.parent.mkdir(parents=True)
        source.write_text("# unpinned fixture harness\n", encoding="utf-8")
        original_read_bytes = Path.read_bytes
        def bounded_bytes(path):
            if path == source or path.suffix == ".exe":
                raise AssertionError("harness or binary file rehash")
            return original_read_bytes(path)
        for store, expected in ((False, "PASSED"), (True, "FAILED")):
            class Client:
                pid = 0
                returncode = 0
                def __init__(self, command, **kwargs):
                    self.url = next(item.split("=", 1)[1].strip('"') for item in command if item.startswith("model_providers.court_probe.base_url="))
                    self.token = kwargs["env"]["COURT_PROBE_API_KEY"]
                def communicate(self, input, timeout):
                    data = json.dumps({"model": "fixture", "store": store, "input": input}).encode("utf-8")
                    request = urllib.request.Request(self.url + "/responses", data=data, headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
                    with urllib.request.urlopen(request, timeout=timeout) as response:
                        response.read()
                    return "", ""
            with self.subTest(store=store), patch.object(probe, "__file__", str(source)), patch.object(probe.subprocess, "Popen", Client), patch.object(probe, "_windows_descendant_pids", return_value=[]), patch.object(probe, "_existing_pids", return_value=[]), patch.object(Path, "read_bytes", bounded_bytes):
                result = probe.run_store_false_probe(self.external / "codex.exe")
                self.assertEqual(result["overall_gate"], expected)
                self.assertEqual(result["responses_request_count"], 1)
                self.assertEqual(result["hash_status"], "UNAVAILABLE_NOT_REHASHED")
                self.assertIsNone(result["harness_sha256"])
                self.assertIsNone(result["verifier_sha256"])

    def test_capability_caller_digest_remains_declared(self):
        for value in ("c" * 64, "d" * 64):
            with self.subTest(value=value), no_file_hashes():
                result = recruitment._hash_evidence({"path": str(self.capability), "content_hash": value}, {})
                self.assertEqual(result["hash_status"], "DECLARED")
                self.assertEqual(result["declared_content_hash"], value)
                self.assertEqual(result["observed_content_hash"], "")
                self.assertFalse(result["file_content_verified"])

    def test_no_declared_capability_digest_is_unavailable_not_rehashed(self):
        with no_file_hashes():
            result = recruitment._hash_evidence({"path": str(self.capability)}, {})
        self.assertEqual(result["hash_status"], "UNAVAILABLE_NOT_REHASHED")
        self.assertEqual(result["observed_content_hash"], "")

    def test_unrelated_install_manifest_cannot_invalidate_external_capability(self):
        (self.root / bootstrap.INSTALLED_PRELOAD_IDENTITY).write_text("{}", encoding="utf-8")
        with no_file_hashes():
            result = recruitment._hash_evidence({"path": str(self.capability), "content_hash": "c" * 64}, {})
        self.assertEqual(result["hash_status"], "DECLARED")

    def route(self, record, roots):
        registry = self.area / "registry.json"
        registry.write_text(json.dumps({"capabilities": [record]}), encoding="utf-8")
        with no_file_hashes():
            return recruitment.route_registry_first("fixture capability", "codex", registry, "valid", roots, lambda request: {"status": "bounded-fixture"})

    def record(self, **changes):
        return {"kind": "skill", "name": "fixture", "description": "fixture capability", "source": "codex_skills", "path": str(self.capability), "primary_fit": ["fixture", "capability"], **changes}

    def test_external_skill_mcp_plugin_remain_eligible_without_decretum_pin(self):
        mcp = self.external / "config.toml"
        mcp.write_text('[mcp_servers.fixture]\ncommand="fixture"\n', encoding="utf-8")
        plugin = self.external / "plugin"
        plugin.mkdir()
        cases = [
            (self.record(), {"codex_skills": [self.external]}),
            (self.record(kind="mcp", source="codex_mcp", path=str(mcp), relative_path="mcp:fixture"), {"codex_mcp": [mcp]}),
            (self.record(kind="plugin", source="local_plugin", path=str(plugin)), {"local_plugin": [self.external]}),
        ]
        for record, roots in cases:
            for declared in (False, True):
                with self.subTest(kind=record["kind"], declared=declared):
                    selected = {**record, **({"content_hash": "d" * 64} if declared else {})}
                    result = self.route(selected, roots)
                    self.assertTrue(result["dispatchable"])
                    self.assertEqual(result["selection_source"], "registry")
                    self.assertFalse(result["discovery_invoked"])

    def test_original_verification_compatibility_and_conflict_gates_remain(self):
        for change in ({"verified": False}, {"compatible_tools": ["hermes"]}, {"stale": True}, {"path": str(self.external / "missing" / "SKILL.md")}, {"content_hash": "c" * 64, "immutable_ref": "sha256:" + "d" * 64}):
            with self.subTest(change=change):
                self.assertFalse(self.route(self.record(**change), {"codex_skills": [self.external]})["dispatchable"])


if __name__ == "__main__":
    unittest.main()
