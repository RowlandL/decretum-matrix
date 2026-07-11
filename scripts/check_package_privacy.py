"""Regression tests for portable-package privacy and archive hardening."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile


sys.dont_write_bytecode = True

import package_skill


ROOT_NAME = package_skill.ROOT_NAME


def write_zip(path: Path, members: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in members:
            archive.writestr(name, body)


def scan_bytes(scanner, body: bytes, *, name: str = "payload.txt") -> bool:
    with tempfile.TemporaryDirectory(prefix="court-package-scan-") as tmp_text:
        archive_path = Path(tmp_text) / "scan.zip"
        write_zip(archive_path, [(name, body)])
        with zipfile.ZipFile(archive_path) as archive:
            return bool(scanner(archive, name))


def validation_problems(members: list[tuple[str, bytes]]) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="court-package-zip-") as tmp_text:
        archive_path = Path(tmp_text) / "candidate.zip"
        write_zip(archive_path, members)
        return package_skill.validate_zip(archive_path)[1]


class SourceTreePrivacyTests(unittest.TestCase):
    def test_sensitive_directories_are_case_insensitive_at_any_depth(self) -> None:
        cases = (
            "Sessions/private.jsonl",
            "scripts/LoGs/private.jsonl",
            "references/BACKUPS/private.zip",
            "references/shiguan-tree/RuNtImE/state.json",
            "references/Imports/pending.md",
            "references/Peers/state.json",
            "references/AuDiTs/report.md",
            "references/shiguan-tree/.ObSiDiAn/workspace.json",
            "references/PLAN-ARCHIVES/private.md",
            "references/MEMORY-DECISIONS/private.md",
            "references/AGENTE-LOGS/private.jsonl",
        )
        for value in cases:
            with self.subTest(path=value):
                self.assertTrue(package_skill.should_skip(Path(value), is_dir=False))

    def test_sensitive_directories_are_pruned_without_copying_their_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-package-source-") as tmp_text:
            tmp = Path(tmp_text)
            src = tmp / "src"
            dst = tmp / "dst"
            (src / "scripts" / "sessions").mkdir(parents=True)
            (src / "scripts" / "ok.py").write_text("print('ok')\n", encoding="utf-8")
            (src / "scripts" / "sessions" / "private.jsonl").write_text(
                '{"private": true}\n', encoding="utf-8"
            )

            package_skill.copy_portable_tree(src, dst)

            self.assertTrue((dst / "scripts" / "ok.py").is_file())
            self.assertFalse((dst / "scripts" / "sessions").exists())

    def test_unknown_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-package-source-") as tmp_text:
            tmp = Path(tmp_text)
            src = tmp / "src"
            dst = tmp / "dst"
            (src / "mystery").mkdir(parents=True)
            (src / "mystery" / "README.md").write_text("unknown\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                package_skill.copy_portable_tree(src, dst)

    def test_binary_defaults_to_reject_but_known_docx_is_excluded(self) -> None:
        self.assertTrue(package_skill.should_skip(Path("references/user-manual-zh.docx"), is_dir=False))
        self.assertFalse(package_skill.should_scan_content(f"{ROOT_NAME}/scripts/blob.bin"))
        self.assertFalse(package_skill.should_scan_content(f"{ROOT_NAME}/scripts/blob.unknown"))
        self.assertTrue(package_skill.should_scan_content(f"{ROOT_NAME}/scripts/check.py"))
        self.assertTrue(package_skill.should_scan_content(f"{ROOT_NAME}/scripts/wrapper.sh"))
        self.assertTrue(package_skill.should_scan_content(f"{ROOT_NAME}/scripts/wrapper.cmd"))

        for filename in ("nested.zip", "blob.bin", "blob.unknown"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(
                prefix="court-package-source-"
            ) as tmp_text:
                tmp = Path(tmp_text)
                src = tmp / "src"
                dst = tmp / "dst"
                (src / "scripts").mkdir(parents=True)
                (src / "scripts" / filename).write_bytes(b"not portable text")
                with self.assertRaises(ValueError):
                    package_skill.copy_portable_tree(src, dst)

    def test_symlink_or_reparse_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-package-source-") as tmp_text:
            tmp = Path(tmp_text)
            src = tmp / "src"
            dst = tmp / "dst"
            outside = tmp / "outside"
            outside.mkdir()
            (outside / "outside.py").write_text("print('outside')\n", encoding="utf-8")
            (src / "scripts").mkdir(parents=True)
            link = src / "scripts" / "linked"
            try:
                os.symlink(outside, link)
            except OSError as exc:
                if os.name != "nt":
                    self.skipTest(f"symlink creation unavailable on this host: {exc}")
                completed = subprocess.run(
                    ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
                if completed.returncode != 0:
                    self.skipTest(
                        "symlink and junction creation unavailable: "
                        f"{exc}; {completed.stdout.strip()} {completed.stderr.strip()}"
                    )

            try:
                with self.assertRaises(ValueError):
                    package_skill.copy_portable_tree(src, dst)
            finally:
                if link.exists() or link.is_symlink():
                    os.rmdir(link)

    def test_portable_seed_does_not_create_obsidian_workspace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-package-seed-") as tmp_text:
            root = Path(tmp_text) / ROOT_NAME
            package_skill.write_core_shiguan_files(root)
            self.assertFalse((root / "references" / "shiguan-tree" / ".obsidian").exists())


class ZipStructurePrivacyTests(unittest.TestCase):
    def assert_problem(self, problems: list[str], needle: str) -> None:
        self.assertTrue(
            any(needle in problem for problem in problems),
            f"expected {needle!r} in validation problems, got {problems[:12]!r}",
        )

    def test_zip_slip_member_is_rejected(self) -> None:
        problems = validation_problems([("../escape.md", b"escape\n")])
        self.assert_problem(problems, "unsafe-member-path")

    def test_absolute_and_unc_member_paths_are_rejected(self) -> None:
        for name in (
            "/absolute.md",
            "C:/absolute.md",
            "C:\\absolute.md",
            "\\\\server\\share\\private.md",
        ):
            with self.subTest(name=name):
                problems = validation_problems([(name, b"private\n")])
                self.assert_problem(problems, "unsafe-member-path")

    def test_exact_duplicate_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-package-zip-") as tmp_text:
            archive_path = Path(tmp_text) / "duplicate.zip"
            name = f"{ROOT_NAME}/scripts/duplicate.py"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(name, b"first\n")
                    archive.writestr(name, b"second\n")
            problems = package_skill.validate_zip(archive_path)[1]
            self.assert_problem(problems, "duplicate-member")

    def test_case_colliding_members_are_rejected(self) -> None:
        problems = validation_problems(
            [
                (f"{ROOT_NAME}/scripts/Case.py", b"one\n"),
                (f"{ROOT_NAME}/scripts/case.py", b"two\n"),
            ]
        )
        self.assert_problem(problems, "case-collision")

    def test_zip_symlink_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-package-zip-") as tmp_text:
            archive_path = Path(tmp_text) / "symlink.zip"
            info = zipfile.ZipInfo(f"{ROOT_NAME}/scripts/linked.py")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(info, "outside.py")
            problems = package_skill.validate_zip(archive_path)[1]
            self.assert_problem(problems, "symlink-or-reparse")

    def test_sensitive_and_unknown_archive_directories_are_rejected(self) -> None:
        cases = (
            (f"{ROOT_NAME}/References/SeSsIoNs/private.jsonl", "sensitive-directory"),
            (f"{ROOT_NAME}/references/shiguan-tree/.ObSiDiAn/workspace.json", "sensitive-directory"),
            (f"{ROOT_NAME}/mystery/readme.md", "unknown-directory"),
            (f"{ROOT_NAME}/.GiT/config", "sensitive-directory"),
        )
        for name, expected in cases:
            with self.subTest(name=name):
                problems = validation_problems([(name, b"private\n")])
                self.assert_problem(problems, expected)

    def test_nested_archives_and_non_text_members_are_rejected(self) -> None:
        cases = (
            (f"{ROOT_NAME}/scripts/nested.zip", "nested-package"),
            (f"{ROOT_NAME}/scripts/blob.bin", "unsupported-binary"),
            (f"{ROOT_NAME}/scripts/blob.unknown", "unsupported-binary"),
            (f"{ROOT_NAME}/references/user-manual-zh.docx", "unsupported-binary"),
        )
        for name, expected in cases:
            with self.subTest(name=name):
                problems = validation_problems([(name, b"binary\x00payload")])
                self.assert_problem(problems, expected)

    def test_high_compression_ratio_is_rejected(self) -> None:
        problems = validation_problems(
            [(f"{ROOT_NAME}/scripts/compression-bomb.txt", b"A\n" * (1024 * 1024))]
        )
        self.assert_problem(problems, "compression-bomb")

    def test_root_release_allowlist_accepts_known_files_and_rejects_unknown(self) -> None:
        allowed = validation_problems(
            [
                (f"{ROOT_NAME}/VERSION", b"beta0.5.8\n"),
                (f"{ROOT_NAME}/CHANGELOG.md", b"# Changelog\n"),
                (f"{ROOT_NAME}/RELEASE-LOG.md", b"# Release log\n"),
                (f"{ROOT_NAME}/release-manifest.json", b'{"schema":"court.release.v1"}\n'),
                (f"{ROOT_NAME}/.gitignore", b"dist/\n"),
            ]
        )
        for filename in ("VERSION", "CHANGELOG.md", "RELEASE-LOG.md", "release-manifest.json", ".gitignore"):
            self.assertFalse(
                any(filename in problem and "not-allowed" in problem for problem in allowed),
                f"known optional root file rejected: {filename}: {allowed[:12]!r}",
            )

        rejected = validation_problems([(f"{ROOT_NAME}/private-notes.md", b"private\n")])
        self.assert_problem(rejected, "root-file-not-allowed")

    def test_optional_release_metadata_is_validated_when_present(self) -> None:
        bad_version = validation_problems([(f"{ROOT_NAME}/VERSION", b"bad version with spaces\n")])
        self.assert_problem(bad_version, "invalid-version")

        bad_manifest = validation_problems([(f"{ROOT_NAME}/release-manifest.json", b"[]\n")])
        self.assert_problem(bad_manifest, "invalid-release-manifest")


class ContentPrivacyTests(unittest.TestCase):
    def test_generic_host_paths_unc_and_home_paths_are_rejected(self) -> None:
        actual_user = b"ali" + b"ce"
        cases = (
            b"D:\\Users\\" + actual_user + b"\\project\\file.txt",
            b"C:/Users/" + actual_user + b"/project/file.txt",
            b"/mnt/c/Users/" + actual_user + b"/project/file.txt",
            b"/Users/" + actual_user + b"/project/file.txt",
            b"/home/" + actual_user + b"/project/file.txt",
            b"\\\\192.168.3.131\\Omina\\private\\file.txt",
            b"//" + b"nas-host/private/share/file.txt",
            b"smb:" + b"//" + b"nas-host/private/share/file.txt",
        )
        for body in cases:
            with self.subTest(body=body):
                self.assertTrue(scan_bytes(package_skill.has_host_absolute_path_content, body))

    def test_generic_example_users_and_regex_source_do_not_trigger_host_path_scan(self) -> None:
        allowed = (
            b"C:\\Users\\Example\\project\\file.txt",
            b"C:/Users/user/project/file.txt",
            b"/home/private-user/project/file.txt",
            b"/Users/<name>/project/file.txt",
        )
        for body in allowed:
            with self.subTest(body=body):
                self.assertFalse(scan_bytes(package_skill.has_host_absolute_path_content, body))

        source = Path(package_skill.__file__).read_bytes()
        self.assertFalse(
            scan_bytes(
                package_skill.has_host_absolute_path_content,
                source,
                name="package_skill.py",
            )
        )

    def test_common_real_token_shapes_are_rejected(self) -> None:
        github_token = b"gh" + b"p_" + (b"A" * 36)
        generic_api_key = b'{"api_key":"' + (b"Z" * 24) + b'"}'
        uri_credential = b"https://svc-user:" + (b"p" * 20) + b"@example.invalid/private"
        cases = (
            github_token,
            generic_api_key,
            uri_credential,
            b"Authorization: Bearer " + (b"B" * 32),
            (b"a" * 24) + b"." + (b"b" * 24) + b"." + (b"c" * 24),
        )
        for body in cases:
            with self.subTest(index=cases.index(body)):
                self.assertTrue(scan_bytes(package_skill.has_secret_like_content, body))

    def test_fixture_values_and_scanner_source_do_not_trigger_secret_scan(self) -> None:
        safe = (
            b'{"api_key":"fixture"}',
            b'token = "<TOKEN>"',
            b'password = "example"',
        )
        for body in safe:
            with self.subTest(body=body):
                self.assertFalse(scan_bytes(package_skill.has_secret_like_content, body))

        for source_path in (
            Path(package_skill.__file__),
            Path(package_skill.__file__).with_name("check_obsidian_sync_transaction.py"),
        ):
            self.assertFalse(
                scan_bytes(
                    package_skill.has_secret_like_content,
                    source_path.read_bytes(),
                    name=source_path.name,
                ),
                f"safe scanner/test fixture source was flagged: {source_path.name}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
