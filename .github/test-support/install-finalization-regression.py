"""Filesystem-real regression tests; all installation targets are temporary."""

from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import install_current_agent_copy as installer
from checks import check_install_current_agent_copy as fixtures
from commands import quick_validate as validator


class FrontmatterTests(unittest.TestCase):
    def validate(self, body):
        with tempfile.TemporaryDirectory(prefix="qv-") as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text("---\n" + body + "\n---\n", encoding="utf-8")
            with patch.object(validator, "yaml", None):
                return validator.validate_skill(root)

    def test_minimal_python_accepts_repository_skill(self):
        root = Path(__file__).resolve().parents[2]
        with patch.object(validator, "yaml", None):
            self.assertTrue(validator.validate_skill(root)[0])

    def test_metadata_keeps_its_mapping(self):
        with patch.object(validator, "yaml", None):
            value, error = validator.parse_frontmatter(
                '---\nname: fixture\ndescription: useful\nmetadata:\n  author: test\n  version: "1.0"\n---\n')
        self.assertIsNone(error)
        self.assertEqual(value["metadata"], {"author": "test", "version": "1.0"})
        self.assertNotIn("author", value)

    def test_duplicate_keys_are_rejected_without_yaml(self):
        for body in ("name: fixture\nname: second\ndescription: useful",
                     "name: fixture\ndescription: useful\nmetadata:\n  author: first\n  author: second"):
            with self.subTest(body=body):
                self.assertFalse(self.validate(body)[0])

    def test_unknown_nested_structure_is_not_flattened(self):
        for prefix in ("  ", "\t"):
            with self.subTest(prefix=prefix):
                self.assertFalse(self.validate("name: fixture\n" + prefix + "description: useful")[0])
        with patch.object(validator, "yaml", None):
            self.assertIsNotNone(validator.parse_frontmatter("---\nname: fixture\n---suffix")[1])

    def test_empty_description_is_rejected(self):
        self.assertFalse(self.validate('name: fixture\ndescription: ""')[0])

    def test_compatibility_has_spec_bounds(self):
        self.assertTrue(self.validate("name: fixture\ndescription: useful\ncompatibility: Python 3.11+")[0])
        self.assertFalse(self.validate("name: fixture\ndescription: useful\ncompatibility: " + "x" * 501)[0])

    def test_metadata_must_be_a_mapping(self):
        self.assertFalse(self.validate("name: fixture\ndescription: useful\nmetadata: not-a-map")[0])


class InstallFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ifn-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.home = self.root / "source", self.root / "home"
        self.home.mkdir()
        self.manifest = fixtures._write_fixture_source(self.source)
        self.roots = fixtures._target_roots(self.home)
        self.binding = self.home / Path(installer.INSTALLATION_BINDING_RELATIVE)
        self.metadata = dict(source_commit="fixture-source", release_label="beta1.1.7",
                             artifact_ref="fixture.zip", build_id="fixture-build",
                             installation_id="fixture-install", transaction_id="fixture-transaction")

    def install(self, metadata=None):
        return installer.install_current_agent_copy(
            source_root=self.source, home_root=self.home, current_tool="codex",
            explicit_tools=[], tool_roots=self.roots, projection_manifest=self.manifest,
            write=True, installation_binding=metadata)

    def seed(self):
        result = self.install()
        self.assertTrue(result["ok"], result)
        self.targets = [Path(item) for item in result["targets"]]
        self.before = {path: path.read_bytes() for root in self.targets
                       for path in root.rglob("*") if path.is_file()}
        installer._write_json_atomic(self.binding, {
            "schema": installer.INSTALLATION_BINDING_SCHEMA, "generation": 7,
            "completion": "COMMITTED", "installation_id": "previous-fixture"})
        self.old_binding = self.binding.read_bytes()
        (self.source / "SKILL.md").write_text("# Changed fixture\n", encoding="utf-8")

    def fail_write(self, kind, *, recovery_fails=False):
        atomic, direct = installer._write_json_atomic, Path.write_text
        fired = False

        def reject(path):
            nonlocal fired
            hit = Path(path) == self.binding if kind == "binding" else Path(path).name.startswith("install-")
            if hit and not fired:
                fired = True
                raise OSError("injected metadata persistence failure")

        def atomic_write(path, value):
            reject(path)
            return atomic(path, value)

        def direct_write(path, *args, **kwargs):
            reject(path)
            return direct(path, *args, **kwargs)

        with patch.object(installer, "_write_json_atomic", side_effect=atomic_write), \
                patch.object(Path, "write_text", new=direct_write):
            if recovery_fails:
                with patch.object(installer, "rollback_install_backup", return_value={
                        "ok": False, "status": "RECOVERY_REQUIRED", "reason": "injected restore failure"}):
                    result = self.install(self.metadata)
            else:
                result = self.install(self.metadata)
        self.assertTrue(fired, "fixture failed to reach the metadata write")
        return result

    def assert_restored(self, result):
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["status"], "ROLLED_BACK", result)
        self.assertEqual(self.binding.read_bytes(), self.old_binding)
        current = {path: path.read_bytes() for root in self.targets
                   for path in root.rglob("*") if path.is_file()}
        self.assertEqual(current, self.before)
        self.assertTrue(result["compensation"]["ok"], result)

    def test_pending_binding_write_failure_restores_previous_install(self):
        self.seed()
        self.assert_restored(self.fail_write("binding"))

    def test_receipt_write_failure_restores_previous_install(self):
        self.seed()
        self.assert_restored(self.fail_write("receipt"))

    def test_preimage_staging_failure_restores_projection(self):
        self.seed()
        with patch.object(installer, "_stage_binding_preimage", side_effect=OSError("injected backup failure")):
            result = self.install(self.metadata)
        self.assert_restored(result)

    def test_post_projection_contract_failure_restores_projection(self):
        self.seed()
        with patch.object(installer, "_build_installation_binding", side_effect=installer._InstallContractError("injected_contract_failure")):
            result = self.install(self.metadata)
        self.assert_restored(result)

    def test_fresh_install_receipt_failure_removes_pending_binding(self):
        result = self.fail_write("receipt")
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["status"], "ROLLED_BACK", result)
        self.assertFalse(self.binding.exists())
        for target in result["targets"]:
            self.assertFalse((Path(target) / "SKILL.md").exists())

    def test_recovery_failure_is_never_reported_as_rolled_back(self):
        self.seed()
        result = self.fail_write("receipt", recovery_fails=True)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["status"], "RECOVERY_REQUIRED", result)
        self.assertFalse(result["compensation"]["ok"])
        self.assertTrue(Path(result["backup"]["backup_root"]).is_dir())
        self.assertEqual(self.binding.read_bytes(), self.old_binding)


def verify(errors):
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                               for cls in (FrontmatterTests, InstallFinalizationTests))
    result = unittest.TestResult()
    suite.run(result)
    errors.extend(text for _, text in result.errors + result.failures)
    return result.testsRun - len(result.errors) - len(result.failures)


if __name__ == "__main__":
    unittest.main()
