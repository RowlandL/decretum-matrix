"""Regression tests for portable-package privacy and archive hardening."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import warnings
import zipfile


sys.dont_write_bytecode = True

import package_skill
import court_safe_fs
import court_safe_fs_windows


ROOT_NAME = package_skill.ROOT_NAME
LEGAL_REQUIRED = {
    f"{ROOT_NAME}/LICENSE",
    f"{ROOT_NAME}/NOTICE",
    f"{ROOT_NAME}/THIRD_PARTY_NOTICES.md",
    f"{ROOT_NAME}/PROVENANCE.md",
    f"{ROOT_NAME}/COMMERCIAL-LICENSE.md",
    f"{ROOT_NAME}/CLA.md",
    f"{ROOT_NAME}/TRADEMARKS.md",
    f"{ROOT_NAME}/AUTHORS.md",
    f"{ROOT_NAME}/SECURITY.md",
    f"{ROOT_NAME}/PRIVACY.md",
    f"{ROOT_NAME}/CONTRIBUTING.md",
    f"{ROOT_NAME}/SBOM.spdx.json",
}
BRAND_REQUIRED = {
    f"{ROOT_NAME}/assets/brand/decretum-matrix-icon.svg",
    f"{ROOT_NAME}/assets/brand/decretum-matrix-icon-256.png",
    f"{ROOT_NAME}/assets/brand/decretum-matrix-icon.ico",
    f"{ROOT_NAME}/assets/brand/README.md",
}
PACKAGE_IDENTITY_REQUIRED = {
    f"{ROOT_NAME}/bin/decretum-matrix.js",
    f"{ROOT_NAME}/bin/decretum-matrix.py",
    f"{ROOT_NAME}/release-manifest.json",
    f"{ROOT_NAME}/references/manifests/court-dispatch-hierarchy.v1.json",
    f"{ROOT_NAME}/references/manifests/skill-identity.v1.json",
}


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


class CommonSafeFilesystemTests(unittest.TestCase):
    @staticmethod
    def _fake_stat(mode: int, inode: int = 1) -> SimpleNamespace:
        return SimpleNamespace(
            st_dev=1,
            st_ino=inode,
            st_mode=mode,
            st_nlink=1,
            st_size=0,
            st_mtime_ns=0,
            st_ctime_ns=0,
        )

    def _make_directory_link(self, target: Path, link: Path) -> None:
        try:
            os.symlink(target, link, target_is_directory=True)
            return
        except OSError as symlink_error:
            if os.name != "nt":
                self.skipTest(f"directory symlink creation unavailable: {symlink_error}")
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                text=True,
                capture_output=True,
                timeout=10,
            )
            if completed.returncode != 0:
                self.fail(
                    "native Windows reparse fixture unavailable: "
                    f"symlink={symlink_error}; "
                    f"junction={completed.stdout.strip()} {completed.stderr.strip()}"
                )

    def _remove_directory_link(self, link: Path) -> None:
        if link.is_symlink():
            link.unlink()
        elif link.exists() or getattr(link, "is_junction", lambda: False)():
            os.rmdir(link)

    def test_common_safe_fs_rejects_reparse_attributes(self) -> None:
        fake = SimpleNamespace(st_file_attributes=0x400)
        with mock.patch.object(Path, "lstat", return_value=fake):
            self.assertTrue(court_safe_fs.is_link_or_reparse(Path("fixture")))

    def test_common_safe_fs_rejects_unsafe_relative_components(self) -> None:
        cases = (
            Path(),
            Path("..") / "escape.txt",
            Path("CON"),
            Path("NUL.txt"),
            Path("name."),
            Path("name "),
            Path("stream:secret"),
            Path("control\x01name"),
            Path("C:\\absolute.txt"),
            Path("\\\\server\\share\\private.txt"),
            Path("\\\\?\\C:\\private.txt"),
            Path("/absolute.txt"),
        )
        for relative in cases:
            with self.subTest(relative=str(relative)):
                with self.assertRaisesRegex(
                    court_safe_fs.SafeFilesystemError,
                    "unsafe-relative-path",
                ):
                    court_safe_fs.validate_relative_path(relative)

    def test_common_safe_fs_rejects_windows_forbidden_and_extended_devices(self) -> None:
        cases = (
            Path("question?.txt"),
            Path("star*.txt"),
            Path("less<than.txt"),
            Path("greater>than.txt"),
            Path('quote"name.txt'),
            Path("pipe|name.txt"),
            Path("CONIN$"),
            Path("conout$.txt"),
            Path("COM\u00b9"),
            Path("com\u00b2.txt"),
            Path("LPT\u00b3"),
        )
        for relative in cases:
            with self.subTest(relative=str(relative)):
                with self.assertRaisesRegex(
                    court_safe_fs.SafeFilesystemError,
                    "unsafe-relative-path",
                ):
                    court_safe_fs.validate_relative_path(relative)

    def test_common_safe_fs_normalizes_nfc_and_case_collision_keys(self) -> None:
        decomposed = Path("Folder") / "e\u0301.txt"
        composed = Path("folder") / "\u00e9.txt"
        self.assertEqual(
            court_safe_fs.validate_relative_path(decomposed),
            Path("Folder") / "\u00e9.txt",
        )
        self.assertEqual(
            court_safe_fs.normalized_relative_key(decomposed),
            court_safe_fs.normalized_relative_key(composed),
        )

    def test_common_safe_fs_rejects_native_reparse_tree_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            base = Path(raw)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "private.txt").write_text("private\n", encoding="utf-8")
            link = root / "linked"
            self._make_directory_link(outside, link)
            try:
                self.assertTrue(court_safe_fs.is_link_or_reparse(link))
                with self.assertRaisesRegex(
                    court_safe_fs.SafeFilesystemError,
                    "symlink-or-reparse",
                ):
                    list(court_safe_fs.iter_regular_files_beneath(root))
            finally:
                self._remove_directory_link(link)

    def test_common_safe_fs_rejects_normalization_collision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            first = root / "\u00e9.txt"
            second = root / "e\u0301.txt"
            first.write_text("first\n", encoding="utf-8")
            second.write_text("second\n", encoding="utf-8")
            self.assertEqual(len(list(root.iterdir())), 2)
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "path-collision",
            ):
                list(court_safe_fs.iter_regular_files_beneath(root))

    def test_common_safe_walk_rejects_windows_case_collision(self) -> None:
        if os.name != "nt":
            self.skipTest("WindowsPath equality semantics are Windows-specific")
        root = Path(r"C:\fixture")
        directory_metadata = self._fake_stat(stat.S_IFDIR | 0o700, inode=10)
        file_metadata = self._fake_stat(stat.S_IFREG | 0o600, inode=11)
        entries = [
            SimpleNamespace(name="Folder.txt", path=os.fspath(root / "Folder.txt")),
            SimpleNamespace(name="folder.txt", path=os.fspath(root / "folder.txt")),
        ]
        scanner = mock.MagicMock()
        scanner.__enter__.return_value = entries
        scanner.__exit__.return_value = False

        def fake_lstat(
            path: Path,
            relative: Path,
            *,
            missing_code: str = "missing-entry",
        ) -> SimpleNamespace:
            del path, missing_code
            return directory_metadata if relative == Path() else file_metadata

        with (
            mock.patch.object(court_safe_fs.os, "scandir", return_value=scanner),
            mock.patch.object(court_safe_fs, "_lstat", side_effect=fake_lstat),
            mock.patch.object(Path, "lstat", return_value=file_metadata),
            mock.patch.object(Path, "is_junction", return_value=False),
        ):
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "path-collision",
            ):
                list(court_safe_fs._walk_verified_directory(root, root, Path(), {}))

    def test_common_safe_read_rejects_missing_and_special_entries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            (root / "directory").mkdir()
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "missing-entry",
            ):
                court_safe_fs.read_regular_file_beneath(
                    root,
                    Path("missing.txt"),
                    max_bytes=1024,
                )
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "unsupported-special-file",
            ):
                court_safe_fs.read_regular_file_beneath(
                    root,
                    Path("directory"),
                    max_bytes=1024,
                )

    def test_common_safe_read_rejects_hardlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            source = root / "source.txt"
            alias = root / "alias.txt"
            source.write_text("private\n", encoding="utf-8")
            os.link(source, alias)
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "hardlink-rejected",
            ):
                court_safe_fs.read_regular_file_beneath(
                    root,
                    Path("alias.txt"),
                    max_bytes=1024,
                )

    def test_common_safe_read_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            (root / "large.bin").write_bytes(b"12345")
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "file-too-large",
            ):
                court_safe_fs.read_regular_file_beneath(
                    root,
                    Path("large.bin"),
                    max_bytes=4,
                )

    def test_common_safe_read_detects_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            source = root / "source.txt"
            replacement = root / "replacement.txt"
            source.write_text("safe\n", encoding="utf-8")
            replacement.write_text("replacement\n", encoding="utf-8")
            replaced = False

            if os.name == "nt":
                real_open = court_safe_fs_windows.open_verified_regular_descriptor

                def racing_windows_open(path: Path, relative: Path) -> int:
                    nonlocal replaced
                    if not replaced and os.path.samefile(path, source):
                        os.replace(replacement, source)
                        replaced = True
                    return real_open(path, relative)

                patcher = mock.patch.object(
                    court_safe_fs_windows,
                    "open_verified_regular_descriptor",
                    side_effect=racing_windows_open,
                )
            else:
                real_open = court_safe_fs.os.open

                def racing_posix_open(
                    path: object,
                    flags: int,
                    mode: int = 0o777,
                    *,
                    dir_fd: int | None = None,
                ) -> int:
                    nonlocal replaced
                    if not replaced and os.fspath(path) == source.name and dir_fd is not None:
                        os.replace(replacement, source)
                        replaced = True
                    if dir_fd is None:
                        return real_open(path, flags, mode)
                    return real_open(path, flags, mode, dir_fd=dir_fd)

                patcher = mock.patch.object(
                    court_safe_fs.os,
                    "open",
                    side_effect=racing_posix_open,
                )

            with patcher:
                with self.assertRaisesRegex(
                    court_safe_fs.SafeFilesystemError,
                    "identity-drift",
                ):
                    court_safe_fs.read_regular_file_beneath(
                        root,
                        Path("source.txt"),
                        max_bytes=1024,
                    )

    def test_common_safe_read_classifies_unlink_during_read_as_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            source = root / "source.txt"
            source.write_bytes(b"read-before-unlink")
            real_read = court_safe_fs.os.read
            unlinked = False

            def unlinking_read(descriptor: int, count: int) -> bytes:
                nonlocal unlinked
                chunk = real_read(descriptor, count)
                if chunk and not unlinked:
                    source.unlink()
                    unlinked = True
                return chunk

            with mock.patch.object(court_safe_fs.os, "read", side_effect=unlinking_read):
                with self.assertRaisesRegex(
                    court_safe_fs.SafeFilesystemError,
                    "identity-drift",
                ) as raised:
                    court_safe_fs.read_regular_file_beneath(
                        root,
                        Path("source.txt"),
                        max_bytes=1024,
                    )
            self.assertEqual(raised.exception.code, "identity-drift")

    def test_common_safe_stat_snapshot_tracks_only_authoritative_change_time(self) -> None:
        before = self._fake_stat(stat.S_IFREG | 0o600, inode=31)
        after = SimpleNamespace(**vars(before))
        after.st_ctime_ns = before.st_ctime_ns + 1
        if os.name == "nt":
            self.assertEqual(
                court_safe_fs._stat_snapshot(before),
                court_safe_fs._stat_snapshot(after),
            )
        else:
            self.assertNotEqual(
                court_safe_fs._stat_snapshot(before),
                court_safe_fs._stat_snapshot(after),
            )

    def test_posix_parent_walk_uses_verified_directory_descriptors(self) -> None:
        root = Path("/verified-root")
        directory_metadata = self._fake_stat(stat.S_IFDIR | 0o700, inode=20)
        with (
            mock.patch.object(court_safe_fs, "_verified_root", return_value=root),
            mock.patch.object(court_safe_fs, "_lstat", return_value=directory_metadata),
            mock.patch.object(court_safe_fs.os, "open", side_effect=(41, 42)) as open_mock,
            mock.patch.object(court_safe_fs.os, "stat", return_value=directory_metadata),
            mock.patch.object(court_safe_fs.os, "fstat", return_value=directory_metadata),
            mock.patch.object(court_safe_fs.os, "close") as close_mock,
        ):
            parent = court_safe_fs._open_verified_parent_posix(
                root,
                Path("nested") / "target.txt",
            )
            try:
                self.assertEqual(parent.descriptor, 42)
                self.assertEqual(parent.leaf, "target.txt")
                self.assertIn(
                    mock.call(
                        "nested",
                        court_safe_fs._POSIX_DIRECTORY_OPEN_FLAGS,
                        dir_fd=41,
                    ),
                    open_mock.call_args_list,
                )
            finally:
                parent.close()
        close_mock.assert_any_call(41)
        close_mock.assert_any_call(42)

    def test_posix_candidate_create_and_publish_are_dir_fd_anchored(self) -> None:
        with mock.patch.object(court_safe_fs.os, "open", return_value=51) as open_mock:
            descriptor = court_safe_fs._create_candidate_descriptor_posix(
                17,
                ".candidate.tmp",
                0x1234,
            )
        self.assertEqual(descriptor, 51)
        open_mock.assert_called_once_with(
            ".candidate.tmp",
            0x1234,
            0o600,
            dir_fd=17,
        )

        with (
            mock.patch.object(court_safe_fs.os, "replace") as replace_mock,
            mock.patch.object(court_safe_fs.os, "fsync") as fsync_mock,
        ):
            court_safe_fs._replace_names_posix(
                17,
                ".candidate.tmp",
                18,
                "target.txt",
            )
        replace_mock.assert_called_once_with(
            ".candidate.tmp",
            "target.txt",
            src_dir_fd=17,
            dst_dir_fd=18,
        )
        fsync_mock.assert_has_calls([mock.call(17), mock.call(18)])

    def test_common_safe_replace_is_failure_atomic_on_cas_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            destination = root / "target.txt"
            destination.write_bytes(b"original")
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            changed = court_safe_fs.atomic_replace_bytes_beneath(
                root,
                Path("target.txt"),
                b"replacement",
                expected=court_safe_fs.ExpectedDestination("sha256", "0" * 64),
            )
            self.assertFalse(changed)
            self.assertEqual(
                {path.name: path.read_bytes() for path in root.iterdir()},
                before,
            )

    def test_common_safe_replace_rejects_hardlinked_destination(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            source = root / "source.txt"
            destination = root / "target.txt"
            source.write_bytes(b"original")
            os.link(source, destination)
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "hardlink-rejected",
            ):
                court_safe_fs.atomic_replace_bytes_beneath(
                    root,
                    Path("target.txt"),
                    b"replacement",
                    expected=court_safe_fs.ExpectedDestination("any"),
                )
            self.assertEqual(source.read_bytes(), b"original")
            self.assertEqual(destination.read_bytes(), b"original")

    def test_common_safe_replace_any_rejects_destination_generation_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            destination = root / "target.txt"
            competitor = root / "competitor.txt"
            destination.write_bytes(b"original")
            competitor.write_bytes(b"competing-generation")
            real_candidate_generated_file = court_safe_fs._candidate_generated_file
            candidate_checks = 0

            def racing_candidate_generated_file(
                checked_root: Path,
                candidate: court_safe_fs.SafeCandidateFile,
            ) -> tuple[Path, court_safe_fs.GeneratedFile]:
                nonlocal candidate_checks
                result = real_candidate_generated_file(checked_root, candidate)
                candidate_checks += 1
                if candidate_checks == 2:
                    os.replace(competitor, destination)
                return result

            with mock.patch.object(
                court_safe_fs,
                "_candidate_generated_file",
                side_effect=racing_candidate_generated_file,
            ):
                changed = court_safe_fs.atomic_replace_bytes_beneath(
                    root,
                    Path("target.txt"),
                    b"replacement",
                    expected=court_safe_fs.ExpectedDestination("any"),
                )
            self.assertFalse(changed)
            self.assertEqual(destination.read_bytes(), b"competing-generation")

    def test_common_safe_replace_publishes_only_on_expected_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            destination = root / "target.txt"
            destination.write_bytes(b"original")
            self.assertFalse(
                court_safe_fs.atomic_replace_bytes_beneath(
                    root,
                    Path("target.txt"),
                    b"wrong",
                    expected=court_safe_fs.ExpectedDestination("absent"),
                )
            )
            self.assertEqual(destination.read_bytes(), b"original")
            expected = hashlib.sha256(b"original").hexdigest()
            self.assertTrue(
                court_safe_fs.atomic_replace_bytes_beneath(
                    root,
                    Path("target.txt"),
                    b"replacement",
                    expected=court_safe_fs.ExpectedDestination("sha256", expected),
                )
            )
            self.assertEqual(destination.read_bytes(), b"replacement")

    def test_common_safe_create_and_replace_reject_sibling_nfc_collision(self) -> None:
        for mode in ("create", "replace"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
                    root = Path(raw)
                    decomposed = root / "e\u0301.txt"
                    composed = root / "\u00e9.txt"
                    decomposed.write_bytes(b"decomposed-sibling")
                    if mode == "replace":
                        composed.write_bytes(b"composed-target")
                    expected = court_safe_fs.ExpectedDestination(
                        "absent" if mode == "create" else "any"
                    )
                    with self.assertRaisesRegex(
                        court_safe_fs.SafeFilesystemError,
                        "path-collision",
                    ):
                        court_safe_fs.atomic_replace_bytes_beneath(
                            root,
                            Path("\u00e9.txt"),
                            b"replacement",
                            expected=expected,
                        )
                    self.assertEqual(decomposed.read_bytes(), b"decomposed-sibling")
                    if mode == "replace":
                        self.assertEqual(composed.read_bytes(), b"composed-target")

    def test_common_safe_replace_rejects_sibling_casefold_collision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            existing = root / "Target.txt"
            existing.write_bytes(b"case-preserved")
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "path-collision",
            ):
                court_safe_fs.atomic_replace_bytes_beneath(
                    root,
                    Path("target.txt"),
                    b"replacement",
                    expected=court_safe_fs.ExpectedDestination("any"),
                )
            self.assertEqual(existing.read_bytes(), b"case-preserved")

    def test_common_safe_candidate_publish_rejects_sibling_nfc_collision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            (root / "e\u0301.bin").write_bytes(b"decomposed-sibling")
            candidate = court_safe_fs.create_candidate_file_beneath(root, suffix=".bin")
            candidate.file_object.write(b"candidate")
            try:
                with self.assertRaisesRegex(
                    court_safe_fs.SafeFilesystemError,
                    "path-collision",
                ):
                    court_safe_fs.atomic_publish_file_beneath(
                        root,
                        Path("\u00e9.bin"),
                        candidate,
                        expected=court_safe_fs.ExpectedDestination("absent"),
                    )
            finally:
                candidate.file_object.close()
                (root / candidate.relative).unlink(missing_ok=True)

    def test_common_safe_post_commit_failure_reports_committed_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            destination = root / "target.bin"
            destination.write_bytes(b"original")
            with mock.patch.object(
                court_safe_fs,
                "_hash_regular_file",
                side_effect=OSError("forced post-commit verification failure"),
            ):
                with self.assertRaises(court_safe_fs.SafeFilesystemError) as raised:
                    court_safe_fs.atomic_replace_bytes_beneath(
                        root,
                        Path("target.bin"),
                        b"replacement",
                        expected=court_safe_fs.ExpectedDestination("any"),
                    )
            self.assertEqual(destination.read_bytes(), b"replacement")
            self.assertEqual(raised.exception.code, "publish-post-commit-failed")
            self.assertEqual(raised.exception.commit_state, "committed")
            self.assertIn("commit-state=committed", str(raised.exception))

    def test_common_safe_replace_close_failure_preserves_commit_outcome(self) -> None:
        cases = (
            (
                "published",
                court_safe_fs.ExpectedDestination("any"),
                None,
                "candidate-close-failed",
                "committed",
                b"replacement",
            ),
            (
                "not-published",
                court_safe_fs.ExpectedDestination("absent"),
                None,
                "candidate-close-failed",
                "not-committed",
                b"original",
            ),
            (
                "primary-post-commit-error",
                court_safe_fs.ExpectedDestination("any"),
                court_safe_fs.SafeFilesystemError(
                    "publish-post-commit-failed",
                    Path("target.bin"),
                    "forced primary committed failure",
                    commit_state="committed",
                ),
                "publish-post-commit-failed",
                "committed",
                b"replacement",
            ),
        )
        real_create_candidate = court_safe_fs._create_candidate_in_directory
        real_hash_regular_file = court_safe_fs._hash_regular_file

        for name, expected, verification_error, error_code, commit_state, body in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
                    root = Path(raw)
                    destination = root / "target.bin"
                    destination.write_bytes(b"original")

                    def create_candidate_with_failing_close(*args, **kwargs):
                        candidate = real_create_candidate(*args, **kwargs)
                        real_file = candidate.file_object
                        failing_file = mock.Mock(wraps=real_file)
                        failing_file.closed = False

                        def fail_close() -> None:
                            real_file.close()
                            raise OSError("forced candidate close failure")

                        failing_file.close.side_effect = fail_close
                        candidate.file_object = failing_file
                        return candidate

                    hash_side_effect = verification_error or real_hash_regular_file
                    with (
                        mock.patch.object(
                            court_safe_fs,
                            "_create_candidate_in_directory",
                            side_effect=create_candidate_with_failing_close,
                        ),
                        mock.patch.object(
                            court_safe_fs,
                            "_hash_regular_file",
                            side_effect=hash_side_effect,
                        ),
                    ):
                        with self.assertRaises(court_safe_fs.SafeFilesystemError) as raised:
                            court_safe_fs._replace_bytes_platform(
                                root,
                                Path("target.bin"),
                                b"replacement",
                                expected,
                                verify_windows=os.name == "nt",
                            )

                    self.assertEqual(destination.read_bytes(), body)
                    self.assertEqual(raised.exception.code, error_code)
                    self.assertEqual(raised.exception.commit_state, commit_state)
                    if isinstance(verification_error, court_safe_fs.SafeFilesystemError):
                        self.assertIs(raised.exception, verification_error)

    def test_common_safe_candidate_flush_error_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            candidate = court_safe_fs.create_candidate_file_beneath(root, suffix=".bin")
            candidate.file_object.write(b"candidate")
            failing_file = mock.Mock(wraps=candidate.file_object)
            failing_file.closed = False
            failing_file.flush.side_effect = OSError("forced flush failure")
            failing_candidate = court_safe_fs.SafeCandidateFile(
                candidate.relative,
                failing_file,
                candidate.platform_handle,
            )
            try:
                with self.assertRaises(court_safe_fs.SafeFilesystemError) as raised:
                    court_safe_fs.atomic_publish_file_beneath(
                        root,
                        Path("published.bin"),
                        failing_candidate,
                        expected=court_safe_fs.ExpectedDestination("absent"),
                    )
                self.assertEqual(raised.exception.code, "candidate-flush-failed")
                self.assertEqual(raised.exception.commit_state, "not-committed")
            finally:
                candidate.file_object.close()
                (root / candidate.relative).unlink(missing_ok=True)

    def test_common_safe_candidate_publish_is_failure_atomic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            destination = root / "target.bin"
            destination.write_bytes(b"original")
            candidate = court_safe_fs.create_candidate_file_beneath(root, suffix=".bin")
            candidate.file_object.write(b"candidate")
            candidate.file_object.flush()
            try:
                self.assertFalse(
                    court_safe_fs.atomic_publish_file_beneath(
                        root,
                        Path("target.bin"),
                        candidate,
                        expected=court_safe_fs.ExpectedDestination("sha256", "f" * 64),
                    )
                )
                self.assertEqual(destination.read_bytes(), b"original")
                self.assertFalse(candidate.file_object.closed)
                self.assertTrue((root / candidate.relative).is_file())
            finally:
                candidate.file_object.close()
                (root / candidate.relative).unlink(missing_ok=True)

    def test_common_safe_candidate_publish_succeeds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            candidate = court_safe_fs.create_candidate_file_beneath(root, suffix=".bin")
            candidate.file_object.write(b"candidate")
            try:
                self.assertTrue(
                    court_safe_fs.atomic_publish_file_beneath(
                        root,
                        Path("published.bin"),
                        candidate,
                        expected=court_safe_fs.ExpectedDestination("absent"),
                    )
                )
                self.assertEqual(
                    court_safe_fs.read_regular_file_beneath(
                        root,
                        Path("published.bin"),
                        max_bytes=1024,
                    ),
                    b"candidate",
                )
                self.assertFalse(candidate.file_object.closed)
            finally:
                candidate.file_object.close()

    def test_windows_module_exposes_batch_a_handle_contract(self) -> None:
        for name in (
            "iter_regular_files_handle",
            "read_regular_file_handle",
            "replace_bytes_handle",
            "publish_candidate_handle",
        ):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(court_safe_fs_windows, name)))

    @unittest.skipUnless(os.name == "nt", "Windows handle traversal is Windows-specific")
    def test_windows_tree_walk_never_uses_path_only_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="court-safe-fs-") as raw:
            root = Path(raw)
            (root / "nested").mkdir()
            (root / "nested" / "file.txt").write_bytes(b"safe")
            with mock.patch.object(
                court_safe_fs,
                "_walk_verified_directory",
                side_effect=AssertionError("path-only Windows traversal used"),
            ):
                files = list(court_safe_fs.iter_regular_files_beneath(root))
        self.assertEqual([relative.as_posix() for relative, _ in files], ["nested/file.txt"])

    def test_windows_handle_snapshot_tracks_change_time(self) -> None:
        before = court_safe_fs_windows.WindowsHandleInformation(
            final_path=os.fspath(Path("/verified-root/file.txt")),
            volume_serial_number=7,
            file_id=0x1234,
            file_attributes=0x80,
            number_of_links=1,
            file_size=4,
            last_write_time=10,
            change_time=20,
        )
        after = court_safe_fs_windows.WindowsHandleInformation(
            final_path=before.final_path,
            volume_serial_number=before.volume_serial_number,
            file_id=before.file_id,
            file_attributes=before.file_attributes,
            number_of_links=before.number_of_links,
            file_size=before.file_size,
            last_write_time=before.last_write_time,
            change_time=before.change_time + 1,
        )
        self.assertNotEqual(
            court_safe_fs_windows.handle_information_snapshot(before),
            court_safe_fs_windows.handle_information_snapshot(after),
        )

    def test_windows_authoritative_link_count_rejects_hardlink(self) -> None:
        expected_path = Path("/verified-root/target.txt")
        relative = Path("target.txt")
        opened = self._fake_stat(stat.S_IFREG | 0o600, inode=0x1234)
        hardlinked = court_safe_fs_windows.WindowsHandleInformation(
            final_path=os.fspath(expected_path),
            volume_serial_number=7,
            file_id=0x1234,
            file_attributes=0x80,
            number_of_links=2,
        )
        with (
            mock.patch.object(court_safe_fs_windows.os, "name", "nt"),
            mock.patch.object(court_safe_fs_windows, "platform_handle_from_fd", return_value=63),
            mock.patch.object(
                court_safe_fs_windows,
                "_windows_handle_information",
                return_value=hardlinked,
            ),
        ):
            with self.assertRaisesRegex(
                court_safe_fs.SafeFilesystemError,
                "hardlink-rejected",
            ):
                court_safe_fs_windows.verify_open_descriptor(
                    62,
                    expected_path,
                    opened,
                    relative=relative,
                )

    def test_windows_verified_open_uses_reparse_safe_flags(self) -> None:
        expected_path = Path("/verified-root/nested/target.txt")
        relative = Path("nested") / "target.txt"
        opened = self._fake_stat(stat.S_IFREG | 0o600, inode=0x1234)
        information = court_safe_fs_windows.WindowsHandleInformation(
            final_path=os.fspath(expected_path),
            volume_serial_number=7,
            file_id=0x1234,
            file_attributes=0x80,
            number_of_links=1,
        )
        with (
            mock.patch.object(court_safe_fs_windows.os, "name", "nt"),
            mock.patch.object(court_safe_fs_windows, "_verify_windows_parent_chain"),
            mock.patch.object(court_safe_fs_windows, "_create_file_handle", return_value=61) as create_mock,
            mock.patch.object(court_safe_fs_windows, "_descriptor_from_handle", return_value=62),
            mock.patch.object(court_safe_fs_windows.os, "fstat", return_value=opened),
            mock.patch.object(
                court_safe_fs_windows,
                "verify_open_descriptor",
                return_value=information,
            ) as verify_mock,
        ):
            descriptor = court_safe_fs_windows.open_verified_regular_descriptor(
                expected_path,
                relative,
            )
        self.assertEqual(descriptor, 62)
        flags = create_mock.call_args.kwargs["flags_and_attributes"]
        self.assertEqual(
            flags
            & (
                court_safe_fs_windows.FILE_FLAG_OPEN_REPARSE_POINT
                | court_safe_fs_windows.FILE_FLAG_BACKUP_SEMANTICS
            ),
            court_safe_fs_windows.FILE_FLAG_OPEN_REPARSE_POINT
            | court_safe_fs_windows.FILE_FLAG_BACKUP_SEMANTICS,
        )
        verify_mock.assert_called_once_with(
            62,
            expected_path,
            opened,
            relative=relative,
        )

    def test_windows_handle_information_mocks_final_path_and_file_id(self) -> None:
        expected_path = Path("/verified-root/nested/target.txt")
        relative = Path("nested") / "target.txt"
        opened = self._fake_stat(stat.S_IFREG | 0o600, inode=0x1234)
        matching = court_safe_fs_windows.WindowsHandleInformation(
            final_path=os.fspath(expected_path),
            volume_serial_number=7,
            file_id=0x1234,
            file_attributes=0x80,
            number_of_links=1,
        )
        with (
            mock.patch.object(court_safe_fs_windows.os, "name", "nt"),
            mock.patch.object(court_safe_fs_windows, "platform_handle_from_fd", return_value=63),
            mock.patch.object(
                court_safe_fs_windows,
                "_windows_handle_information",
                return_value=matching,
            ),
        ):
            self.assertEqual(
                court_safe_fs_windows.verify_open_descriptor(
                    62,
                    expected_path,
                    opened,
                    relative=relative,
                ),
                matching,
            )

        for information, detail in (
            (
                court_safe_fs_windows.WindowsHandleInformation(
                    final_path=os.fspath(expected_path.with_name("raced.txt")),
                    volume_serial_number=7,
                    file_id=0x1234,
                    file_attributes=0x80,
                    number_of_links=1,
                ),
                "opened-handle-final-path-mismatch",
            ),
            (
                court_safe_fs_windows.WindowsHandleInformation(
                    final_path=os.fspath(expected_path),
                    volume_serial_number=7,
                    file_id=0x9999,
                    file_attributes=0x80,
                    number_of_links=1,
                ),
                "opened-handle-file-id-mismatch",
            ),
        ):
            with self.subTest(detail=detail):
                with (
                    mock.patch.object(court_safe_fs_windows.os, "name", "nt"),
                    mock.patch.object(
                        court_safe_fs_windows,
                        "platform_handle_from_fd",
                        return_value=63,
                    ),
                    mock.patch.object(
                        court_safe_fs_windows,
                        "_windows_handle_information",
                        return_value=information,
                    ),
                ):
                    with self.assertRaisesRegex(
                        court_safe_fs.SafeFilesystemError,
                        detail,
                    ) as raised:
                        court_safe_fs_windows.verify_open_descriptor(
                            62,
                            expected_path,
                            opened,
                            relative=relative,
                        )
                self.assertEqual(raised.exception.relative, relative)


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

    def test_exact_npm_harness_paths_are_repository_only_case_insensitive(self) -> None:
        cases = (
            "package.json",
            "PACKAGE-LOCK.JSON",
            "Scripts/Build_NPM_Package.MJS",
            "scripts/CHECK_NPM_PACKAGE.mjs",
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
            (src / "scripts" / "quick_validate.py").write_text("print('ok')\n", encoding="utf-8")
            (src / "scripts" / "ok.py").write_text("print('not projected')\n", encoding="utf-8")
            (src / "scripts" / "sessions" / "private.jsonl").write_text(
                '{"private": true}\n', encoding="utf-8"
            )

            package_skill.copy_portable_tree(src, dst)

            self.assertTrue((dst / "scripts" / "quick_validate.py").is_file())
            self.assertFalse((dst / "scripts" / "ok.py").exists())
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
        self.assertTrue(package_skill.should_skip(Path("scripts/blob.bin"), is_dir=False))
        self.assertTrue(package_skill.should_skip(Path("scripts/blob.unknown"), is_dir=False))
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
                package_skill.copy_portable_tree(src, dst)
                self.assertFalse((dst / "scripts" / filename).exists())

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

    def test_repository_only_npm_members_are_rejected_explicitly(self) -> None:
        cases = (
            "package.json",
            "PACKAGE-LOCK.JSON",
            "Scripts/Build_NPM_Package.MJS",
            "scripts/CHECK_NPM_PACKAGE.mjs",
        )
        for relative in cases:
            with self.subTest(path=relative):
                self.assertEqual(
                    package_skill.archive_member_policy_problem(
                        f"{ROOT_NAME}/{relative}",
                        is_dir=False,
                    ),
                    "repository-only-file",
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
                (f"{ROOT_NAME}/VERSION", b"beta1.0.1\n"),
                (f"{ROOT_NAME}/CHANGELOG.md", b"# Changelog\n"),
                (f"{ROOT_NAME}/RELEASE-LOG.md", b"# Release log\n"),
                (
                    f"{ROOT_NAME}/release-manifest.json",
                    (
                        '{"name":"decretum-matrix","display_name":"Decretum Matrix（诏令矩阵）",'
                        '"package_name":"decretum-matrix",'
                        '"release_label":"beta1.0.1","artifact_name":"decretum-matrix-beta1.0.1.zip",'
                        '"archive_root":"decretum-matrix/","license":{"declared":"AGPL-3.0-only",'
                        '"file":"LICENSE"}}\n'
                    ).encode("utf-8"),
                ),
                (f"{ROOT_NAME}/.gitignore", b"dist/\n"),
                (f"{ROOT_NAME}/LICENSE", b"GNU AFFERO GENERAL PUBLIC LICENSE\n"),
                (f"{ROOT_NAME}/NOTICE", "Decretum Matrix（诏令矩阵）\n".encode("utf-8")),
                (f"{ROOT_NAME}/THIRD_PARTY_NOTICES.md", b"# Third-party notices\n"),
                (f"{ROOT_NAME}/PROVENANCE.md", b"# Provenance\n"),
                (f"{ROOT_NAME}/COMMERCIAL-LICENSE.md", b"# Commercial license notice\n"),
                (f"{ROOT_NAME}/CLA.md", b"# Contributor License Agreement\n"),
                (f"{ROOT_NAME}/TRADEMARKS.md", b"# Trademarks\n"),
                (f"{ROOT_NAME}/AUTHORS.md", b"# Authors\n"),
                (f"{ROOT_NAME}/SECURITY.md", b"# Security\n"),
                (f"{ROOT_NAME}/PRIVACY.md", b"# Privacy\n"),
                (f"{ROOT_NAME}/CONTRIBUTING.md", b"# Contributing\n"),
                (
                    f"{ROOT_NAME}/SBOM.spdx.json",
                    b'{"spdxVersion":"SPDX-2.3","packages":[{"name":"decretum-matrix",'
                    b'"versionInfo":"beta1.0.1","licenseDeclared":"AGPL-3.0-only"}]}\n',
                ),
            ]
        )
        for filename in (
            "VERSION", "CHANGELOG.md", "RELEASE-LOG.md", "release-manifest.json", ".gitignore",
            "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "PROVENANCE.md",
            "COMMERCIAL-LICENSE.md", "CLA.md", "TRADEMARKS.md", "AUTHORS.md",
            "SECURITY.md", "PRIVACY.md", "CONTRIBUTING.md", "SBOM.spdx.json",
        ):
            self.assertFalse(
                any(filename in problem and "not-allowed" in problem for problem in allowed),
                f"known optional root file rejected: {filename}: {allowed[:12]!r}",
            )

        rejected = validation_problems([(f"{ROOT_NAME}/private-notes.md", b"private\n")])
        self.assert_problem(rejected, "root-file-not-allowed")

    def test_optional_release_metadata_is_validated_when_present(self) -> None:
        bad_version = validation_problems([(f"{ROOT_NAME}/VERSION", b"bad version with spaces\n")])
        self.assert_problem(bad_version, "invalid-version")

        stale_version = validation_problems([(f"{ROOT_NAME}/VERSION", b"beta0.5.9\n")])
        self.assert_problem(stale_version, "invalid-version")

        bad_manifest = validation_problems([(f"{ROOT_NAME}/release-manifest.json", b"[]\n")])
        self.assert_problem(bad_manifest, "invalid-release-manifest")

        bad_sbom = validation_problems(
            [
                (
                    f"{ROOT_NAME}/SBOM.spdx.json",
                    b'{"spdxVersion":"SPDX-2.3","packages":[{"name":"decretum-matrix",'
                    b'"versionInfo":"beta1.0.1","licenseDeclared":"Apache-2.0"}]}\n',
                )
            ]
        )
        self.assert_problem(bad_sbom, "invalid-sbom")


@unittest.skipIf(
    os.environ.get("COURT_PACKAGE_STAGE_VALIDATION") == "1",
    "avoid recursive package builds during staged package validation",
)
class PackageBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="court-package-build-")
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_existing_output_is_preserved(self) -> None:
        out = self.temp_path / "existing.zip"
        out.write_bytes(b"sentinel")
        before = hashlib.sha256(out.read_bytes()).hexdigest()
        _, _, problems = package_skill.build(out)
        self.assertIn("output-already-exists", "\n".join(problems))
        self.assertEqual(before, hashlib.sha256(out.read_bytes()).hexdigest())

    def test_release_identity_license_and_locator_contract(self) -> None:
        self.assertEqual(getattr(package_skill, "PRODUCT_NAME", None), "decretum-matrix")
        self.assertEqual(
            getattr(package_skill, "DISPLAY_NAME", None),
            "Decretum Matrix（诏令矩阵）",
        )
        release_label = getattr(package_skill, "RELEASE_LABEL", None)
        self.assertRegex(str(release_label), r"^beta\d+\.\d+\.\d+(?:-hotfix-v[1-9]\d*)?$")
        self.assertEqual(getattr(package_skill, "LICENSE_ID", None), "AGPL-3.0-only")
        self.assertEqual(package_skill.ROOT_NAME, "decretum-matrix")
        self.assertEqual(
            package_skill.default_out().name,
            f"decretum-matrix-{release_label}.zip",
        )
        self.assertTrue(package_skill.should_skip(Path(".github"), is_dir=True))

    def test_legal_governance_files_are_mandatory_package_members(self) -> None:
        self.assertEqual(package_skill.LEGAL_REQUIRED_MEMBERS, LEGAL_REQUIRED)
        self.assertEqual(getattr(package_skill, "BRAND_REQUIRED_MEMBERS", set()), BRAND_REQUIRED)
        self.assertEqual(
            getattr(package_skill, "PACKAGE_IDENTITY_REQUIRED_MEMBERS", set()),
            PACKAGE_IDENTITY_REQUIRED,
        )
        out = self.temp_path / "legal.zip"
        self.assertEqual(package_skill.build(out)[2], [])
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(
                (LEGAL_REQUIRED | BRAND_REQUIRED | PACKAGE_IDENTITY_REQUIRED)
                - set(archive.namelist()),
                set(),
            )
        for index, missing_member in enumerate(
            (
                sorted(BRAND_REQUIRED)[0],
                f"{ROOT_NAME}/references/manifests/court-dispatch-hierarchy.v1.json",
                f"{ROOT_NAME}/references/manifests/skill-identity.v1.json",
            )
        ):
            missing_archive = self.temp_path / f"missing-required-{index}.zip"
            with zipfile.ZipFile(out) as archive, zipfile.ZipFile(missing_archive, "w") as altered:
                for info in archive.infolist():
                    if info.filename != missing_member:
                        altered.writestr(info, archive.read(info))
            self.assertIn(missing_member, package_skill.validate_zip(missing_archive)[1])

    def test_two_clean_builds_are_byte_identical(self) -> None:
        first = self.temp_path / "first.zip"
        second = self.temp_path / "second.zip"
        self.assertEqual(package_skill.build(first)[2], [])
        self.assertEqual(package_skill.build(second)[2], [])
        self.assertEqual(
            hashlib.sha256(first.read_bytes()).digest(),
            hashlib.sha256(second.read_bytes()).digest(),
        )
        with zipfile.ZipFile(first) as archive:
            file_members = [info for info in archive.infolist() if not info.is_dir()]
            self.assertTrue(file_members)
            for info in file_members:
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.date_time, package_skill.ZIP_TIMESTAMP)
                self.assertEqual((info.external_attr >> 16) & 0xFFFF, 0o100644)

    def test_late_competing_output_is_preserved(self) -> None:
        out = self.temp_path / "late.zip"
        sentinel = b"late competing writer"
        original_validate = package_skill.validate_zip

        def create_competing_output(candidate: Path) -> tuple[int, list[str]]:
            result = original_validate(candidate)
            out.write_bytes(sentinel)
            return result

        with mock.patch.object(package_skill, "validate_zip", side_effect=create_competing_output):
            _, _, problems = package_skill.build(out)

        self.assertIn("output-already-exists", "\n".join(problems))
        self.assertEqual(out.read_bytes(), sentinel)
        self.assertEqual(list(self.temp_path.glob(f".{out.name}.*.candidate")), [])

    # ---- M3 RED（R-PA1a）：web/shiguan-tree 必须随 package 打包（manifest 投影成员）----
    def test_web_shiguan_tree_is_packaged(self) -> None:
        out = self.temp_path / "web-tree.zip"
        _, _, problems = package_skill.build(out)
        self.assertEqual(problems, [])
        with zipfile.ZipFile(out) as archive:
            names = set(archive.namelist())
        expected = f"{ROOT_NAME}/web/shiguan-tree/index.html"
        self.assertIn(expected, names)

    # ---- M3 RED（R-PA1b）：web/shiguan-tree 白名单有界（其余 web 子目录仍排除）----
    def test_web_allowlist_is_bounded_to_shiguan_tree(self) -> None:
        from pathlib import Path as _Path
        probe = _Path("web/other-dir/placeholder.txt")
        self.assertTrue(package_skill.should_skip(probe, is_dir=False))
        allowed = _Path("web/shiguan-tree/index.html")
        self.assertFalse(package_skill.should_skip(allowed, is_dir=False))

    def test_source_replacement_during_open_is_rejected(self) -> None:
        source_root = self.temp_path / "source"
        source_root.mkdir()
        source = source_root / "README.md"
        replacement = self.temp_path / "replacement.md"
        source.write_text("safe\n", encoding="utf-8")
        replacement.write_text("replacement\n", encoding="utf-8")
        real_open = os.open
        replaced = False

        def racing_open(path: object, flags: int, mode: int = 0o777) -> int:
            nonlocal replaced
            candidate = Path(path)
            if not replaced and candidate == source:
                os.replace(replacement, source)
                replaced = True
            return real_open(path, flags, mode)

        with mock.patch.object(package_skill.os, "open", side_effect=racing_open):
            with self.assertRaisesRegex(package_skill.PackagePolicyError, "source-changed-during-read"):
                package_skill.read_source_file_stable(source, Path("README.md"), source_root)

    def test_text_payload_normalizes_mixed_newlines(self) -> None:
        source_root = self.temp_path / "newline-source"
        source_root.mkdir()
        source = source_root / "README.md"
        source.write_bytes(b"one\r\ntwo\rthree\nfour")
        self.assertEqual(
            package_skill.read_source_file_stable(source, Path("README.md"), source_root),
            b"one\ntwo\nthree\nfour",
        )
        svg = source_root / "icon.svg"
        svg.write_bytes(b"<svg>\r\n<path>\r</svg>\n")
        self.assertEqual(
            package_skill.read_source_file_stable(svg, Path("icon.svg"), source_root),
            b"<svg>\n<path>\n</svg>\n",
        )


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
