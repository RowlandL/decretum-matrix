"""Regression fixtures for candidate-owned npm staging and compensation."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from commands import fix_decretum_matrix as fix


class CandidateInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="decretum-owned-npm-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / "prefix"
        self.caller = self.root / "caller"
        self.home = self.root / "home"
        for directory in (self.prefix, self.caller, self.home):
            directory.mkdir()
        self.tgz = self.root / "candidate.tgz"
        self.tgz.write_bytes(b"fixture; npm process replaced, filesystem real")

    def link_directory(self, path, target):
        path.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(path), str(target)],
                           check=True, capture_output=True)
        else:
            path.symlink_to(target, target_is_directory=True)

    def fake_npm(self, command, **kwargs):
        stage = Path(command[command.index("--prefix") + 1])
        self.assertNotEqual(stage, self.prefix)
        package = stage / "node_modules" / "@rowlandl" / "decretum-matrix"
        package.mkdir(parents=True)
        (package / "cli.js").write_text("candidate-cli", encoding="utf-8")
        if getattr(self, "internal_link", None):
            (package / "outside").symlink_to(self.internal_link, target_is_directory=True)
        shim = stage / "node_modules" / ".bin" / "decretum-matrix"
        shim.parent.mkdir()
        if self.symlink_bin:
            shim.symlink_to(getattr(self, "bin_target", Path("..") / "@rowlandl" / "decretum-matrix" / "cli.js"))
        else:
            shim.write_text("candidate shim", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    def install(self, symlink_bin=False):
        self.symlink_bin = symlink_bin
        with patch.object(fix.subprocess, "run", side_effect=self.fake_npm):
            return fix._install_candidate_npm(candidate_tgz=self.tgz, npm_prefix=self.prefix,
                                             home=self.home, caller_cwd=self.caller)

    def rollback(self):
        return fix._rollback_candidate_npm(npm_prefix=self.prefix, home=self.home,
                                           caller_cwd=self.caller)

    def test_install_rejects_linked_target_ancestors_before_writing(self):
        for parent in ("node_modules", "node_modules/@rowlandl", "node_modules/.bin"):
            with self.subTest(parent=parent):
                self.prefix = self.root / parent.replace("/", "-")
                self.prefix.mkdir()
                external = self.root / (self.prefix.name + "-foreign")
                self.link_directory(self.prefix / parent, external)
                sentinel = external / "sentinel"
                sentinel.write_text("unrelated", encoding="utf-8")
                result = self.install()
                self.assertFalse(result["ok"], result)
                self.assertEqual(list(external.iterdir()), [sentinel])
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "unrelated")

    def test_rollback_rejects_linked_parent_without_deleting_foreign_files(self):
        for parent in ("node_modules", "node_modules/@rowlandl", "node_modules/.bin"):
            with self.subTest(parent=parent):
                self.prefix = self.root / parent.replace("/", "-")
                self.prefix.mkdir()
                external = self.root / (self.prefix.name + "-foreign")
                self.link_directory(self.prefix / parent, external)
                target = (self.prefix / "node_modules" / ".bin" / "decretum-matrix"
                          if parent.endswith(".bin") else
                          self.prefix / "node_modules" / "@rowlandl" / "decretum-matrix" / "sentinel")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("foreign", encoding="utf-8")
                result = self.rollback()
                self.assertFalse(result["ok"], result)
                self.assertEqual(result["status"], "RECOVERY_REQUIRED")
                self.assertEqual(target.read_text(encoding="utf-8"), "foreign")

    def test_valid_relative_bin_link_survives_staging_and_owned_rollback(self):
        sentinel = self.prefix / "unrelated"
        sentinel.write_text("preserved", encoding="utf-8")
        result = self.install(symlink_bin=True)
        self.assertTrue(result["ok"], result)
        shim = self.prefix / "node_modules" / ".bin" / "decretum-matrix"
        self.assertTrue(shim.is_symlink())
        self.assertEqual(shim.read_text(encoding="utf-8"), "candidate-cli")
        self.assertTrue(self.rollback()["ok"])
        self.assertFalse(shim.is_symlink())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserved")

    def test_regular_shim_and_unrelated_content_survive_commit(self):
        sentinel = self.prefix / "unrelated"
        sentinel.write_text("preserved", encoding="utf-8")
        self.assertTrue(self.install()["ok"])
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserved")
        self.assertTrue(self.rollback()["ok"])
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserved")

    def test_publication_uses_destination_read_permissions(self):
        if os.name == "nt":
            subprocess.run(["icacls.exe", str(self.prefix), "/grant",
                            "*S-1-5-32-545:(OI)(CI)RX"], check=True, capture_output=True)
        self.assertTrue(self.install()["ok"])
        files = {self.prefix / "node_modules/.bin/decretum-matrix": "candidate shim",
                 self.prefix / "node_modules/@rowlandl/decretum-matrix/cli.js": "candidate-cli"}
        for path, expected in files.items():
            self.assertEqual(path.read_text(encoding="utf-8"), expected)
            if os.name == "nt":
                quoted = path.as_posix().replace("'", "''")
                script = (f"$acl=Get-Acl -LiteralPath '{quoted}'; [bool]($acl.Access | Where-Object {{ "
                          "$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value "
                          "-eq 'S-1-5-32-545' -and $_.IsInherited -and $_.AccessControlType -eq 'Allow' })")
                result = subprocess.run([shutil.which("pwsh") or "powershell.exe", "-NoProfile", "-Command", script],
                                        check=True, capture_output=True, text=True)
                self.assertEqual(result.stdout.strip(), "True", f"public read access lost: {path}")
        if os.name == "nt":
            self.internal_link = self.root / "foreign-package-body"
            self.internal_link.mkdir()
            sentinel = self.internal_link / "sentinel"
            sentinel.write_text("preserved", encoding="utf-8")
            self.prefix = self.root / "linked-prefix"
            self.prefix.mkdir()
            self.assertFalse(self.install()["ok"])
            self.assertFalse((self.prefix / "node_modules/@rowlandl/decretum-matrix/outside").exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserved")

    def test_staged_bin_link_outside_package_is_rejected(self):
        self.bin_target = self.root / "foreign"
        self.bin_target.write_text("preserved", encoding="utf-8")
        self.assertFalse(self.install(symlink_bin=True)["ok"])
        self.assertFalse((self.prefix / "node_modules").exists())
        self.assertEqual(self.bin_target.read_text(encoding="utf-8"), "preserved")

    def test_rollback_does_not_follow_foreign_bin_link(self):
        target = self.root / "foreign"
        target.write_text("preserved", encoding="utf-8")
        shim = self.prefix / "node_modules" / ".bin" / "decretum-matrix"
        shim.parent.mkdir(parents=True)
        shim.symlink_to(target)
        self.assertEqual(self.rollback()["status"], "RECOVERY_REQUIRED")
        self.assertTrue(shim.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "preserved")


def verify(errors):
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(CandidateInstallTests).run(result)
    errors.extend(text for _, text in result.errors + result.failures)
    return result.testsRun - len(result.errors) - len(result.failures)


if __name__ == "__main__":
    unittest.main()
