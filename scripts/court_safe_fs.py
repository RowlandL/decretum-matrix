"""Batch A safe filesystem primitives for Decretum Matrix.

The contract rejects lexical escapes, Windows aliases, links/reparse points,
special files, hardlinks, normalized-name collisions, and observable identity
drift.  Publication uses a flushed candidate plus an atomic same-filesystem
rename and explicit destination CAS.  POSIX names are anchored to verified
directory descriptors, but ``renameat`` remains name-based; Windows final
publish remains path-based.  Batch A therefore retains a same-privilege
concurrent namespace-race residual instead of claiming handle-relative publish.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path, PureWindowsPath
import secrets
import stat
import sys
from typing import BinaryIO, Iterator, Literal
import unicodedata


sys.dont_write_bytecode = True


_CHUNK_SIZE = 1024 * 1024
_REPARSE_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_POSIX_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_POSIX_READ_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CLOCK$",
    "CONIN$",
    "CONOUT$",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
    *(f"COM{index}" for index in ("\u00b9", "\u00b2", "\u00b3")),
    *(f"LPT{index}" for index in ("\u00b9", "\u00b2", "\u00b3")),
}
_WINDOWS_FORBIDDEN_CHARACTERS = frozenset('?*<>|"')


class SafeFilesystemError(RuntimeError):
    """A normalized failure with an explicit operation-commit outcome."""

    def __init__(
        self,
        code: str,
        relative: Path,
        detail: str = "",
        *,
        commit_state: Literal["not-committed", "committed"] = "not-committed",
    ) -> None:
        if commit_state not in {"not-committed", "committed"}:
            raise ValueError(f"unsupported commit state: {commit_state!r}")
        self.code = code
        self.relative = Path(relative)
        self.detail = detail
        self.commit_state = commit_state
        message = f"{code}:{self.relative.as_posix()}"
        if detail:
            message = f"{message}:{detail}"
        if commit_state != "not-committed":
            message = f"{message}:commit-state={commit_state}"
        super().__init__(message)


@dataclass(frozen=True)
class GeneratedFile:
    relative: Path
    sha256: str
    size_bytes: int
    snapshot: tuple[object, ...] | None = None


@dataclass(frozen=True)
class ExpectedDestination:
    mode: Literal["absent", "any", "sha256"]
    sha256: str = ""

    def __post_init__(self) -> None:
        if self.mode not in {"absent", "any", "sha256"}:
            raise ValueError(f"unsupported expected destination mode: {self.mode!r}")
        digest = self.sha256.lower()
        if self.mode == "sha256":
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("sha256 expected destination requires a 64-character hex digest")
            object.__setattr__(self, "sha256", digest)
        elif digest:
            raise ValueError(f"{self.mode} expected destination must not include sha256")


@dataclass
class SafeCandidateFile:
    relative: Path
    file_object: BinaryIO
    platform_handle: int | None


@dataclass
class _VerifiedPosixParent:
    root: Path
    relative: Path
    path: Path
    descriptor: int
    opened: os.stat_result
    leaf: str
    closed: bool = False

    def close(self) -> None:
        if not self.closed:
            os.close(self.descriptor)
            self.closed = True


@dataclass(frozen=True)
class _OpenRegularFile:
    root: Path
    relative: Path
    path: Path
    descriptor: int
    opened: os.stat_result
    parent: _VerifiedPosixParent | None = None
    platform_snapshot: tuple[object, ...] | None = None


@dataclass(frozen=True)
class _DestinationGeneration:
    exists: bool
    snapshot: tuple[object, ...] | None = None
    sha256: str = ""
    size_bytes: int = 0


def _raise(code: str, relative: Path, detail: str = "") -> None:
    raise SafeFilesystemError(code, relative, detail)


def _component_key(component: str) -> str:
    return unicodedata.normalize("NFC", component).casefold()


def _portable_parts(relative: Path) -> tuple[str, ...]:
    raw = os.fspath(relative)
    if not isinstance(raw, str):
        raw = os.fsdecode(raw)
    if not raw or raw == "." or "\x00" in raw:
        _raise("unsafe-relative-path", Path(raw or "."), "empty-or-nul")
    windows = PureWindowsPath(raw)
    if (
        Path(raw).is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or raw.startswith(("/", "\\"))
    ):
        _raise("unsafe-relative-path", Path(raw), "absolute-or-device-path")
    portable = raw.replace("\\", "/")
    parts = tuple(portable.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        _raise("unsafe-relative-path", Path(raw), "non-normal-component")
    return parts


def validate_relative_path(relative: Path) -> Path:
    source = Path(relative)
    normalized: list[str] = []
    for component in _portable_parts(source):
        value = unicodedata.normalize("NFC", component)
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            _raise("unsafe-relative-path", source, "control-character")
        if any(character in _WINDOWS_FORBIDDEN_CHARACTERS for character in value):
            _raise("unsafe-relative-path", source, "windows-forbidden-character")
        if value.endswith((".", " ")):
            _raise("unsafe-relative-path", source, "trailing-dot-or-space")
        if ":" in value:
            _raise("unsafe-relative-path", source, "alternate-data-stream")
        device_stem = value.split(".", 1)[0].upper()
        if device_stem in _WINDOWS_RESERVED_NAMES:
            _raise("unsafe-relative-path", source, "windows-device-name")
        normalized.append(value)
    return Path(*normalized)


def normalized_relative_key(relative: Path) -> str:
    normalized = validate_relative_path(relative)
    return "/".join(_component_key(component) for component in normalized.parts)


def _metadata_is_reparse(metadata: object) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    mode = int(getattr(metadata, "st_mode", 0) or 0)
    return bool(attributes & _REPARSE_FLAG) or stat.S_ISLNK(mode)


def is_link_or_reparse(path: Path, *, missing_ok: bool = False) -> bool:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        if missing_ok:
            return False
        raise
    if _metadata_is_reparse(metadata):
        return True
    junction = getattr(candidate, "is_junction", None)
    try:
        return bool(callable(junction) and junction())
    except OSError as exc:
        _raise("metadata-unavailable", candidate, str(exc))


def _stat_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _stat_snapshot(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    # Windows fstat/lstat expose incompatible creation-time values here.  Its
    # authoritative change time is compared through WindowsHandleInformation.
    change_time = 0 if os.name == "nt" else int(getattr(value, "st_ctime_ns", 0))
    return (
        *_stat_identity(value),
        value.st_size,
        value.st_mtime_ns,
        change_time,
    )


def _lstat(path: Path, relative: Path, *, missing_code: str = "missing-entry") -> os.stat_result:
    try:
        return path.lstat()
    except FileNotFoundError as exc:
        raise SafeFilesystemError(missing_code, relative) from exc
    except OSError as exc:
        raise SafeFilesystemError("metadata-unavailable", relative, str(exc)) from exc


def _assert_not_reparse(path: Path, relative: Path, metadata: os.stat_result | None = None) -> None:
    observed = metadata if metadata is not None else _lstat(path, relative)
    if _metadata_is_reparse(observed):
        _raise("symlink-or-reparse", relative)
    junction = getattr(path, "is_junction", None)
    try:
        if callable(junction) and junction():
            _raise("symlink-or-reparse", relative)
    except OSError as exc:
        raise SafeFilesystemError("metadata-unavailable", relative, str(exc)) from exc


def _assert_directory(path: Path, relative: Path, metadata: os.stat_result) -> None:
    _assert_not_reparse(path, relative, metadata)
    if not stat.S_ISDIR(metadata.st_mode):
        _raise("unsupported-special-file", relative, "expected-directory")


def _assert_regular(path: Path, relative: Path, metadata: os.stat_result) -> None:
    _assert_not_reparse(path, relative, metadata)
    if not stat.S_ISREG(metadata.st_mode):
        _raise("unsupported-special-file", relative)
    if metadata.st_nlink == 0:
        _raise("identity-drift", relative, "entry-unlinked")
    if metadata.st_nlink != 1:
        _raise("hardlink-rejected", relative, f"link-count={metadata.st_nlink}")


def _assert_directory_metadata(relative: Path, metadata: os.stat_result) -> None:
    if _metadata_is_reparse(metadata):
        _raise("symlink-or-reparse", relative)
    if not stat.S_ISDIR(metadata.st_mode):
        _raise("unsupported-special-file", relative, "expected-directory")


def _assert_regular_metadata(relative: Path, metadata: os.stat_result) -> None:
    if _metadata_is_reparse(metadata):
        _raise("symlink-or-reparse", relative)
    if not stat.S_ISREG(metadata.st_mode):
        _raise("unsupported-special-file", relative)
    if metadata.st_nlink == 0:
        _raise("identity-drift", relative, "entry-unlinked")
    if metadata.st_nlink != 1:
        _raise("hardlink-rejected", relative, f"link-count={metadata.st_nlink}")


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_root_chain(root: Path) -> None:
    anchor = Path(root.anchor)
    current = anchor
    remaining = root.parts[1:] if root.anchor else root.parts
    if root.anchor:
        anchor_metadata = _lstat(anchor, Path("."), missing_code="root-missing")
        _assert_directory(anchor, Path("."), anchor_metadata)
    for component in remaining:
        current = current / component
        metadata = _lstat(current, Path("."), missing_code="root-missing")
        _assert_not_reparse(current, Path("."), metadata)


def _verified_root(root: Path) -> Path:
    absolute = _absolute(Path(root))
    _assert_root_chain(absolute)
    before = _lstat(absolute, Path("."), missing_code="root-missing")
    _assert_directory(absolute, Path("."), before)
    try:
        resolved = absolute.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SafeFilesystemError("root-unavailable", Path("."), str(exc)) from exc
    verified = absolute
    if os.path.normcase(os.fspath(resolved)) != os.path.normcase(os.fspath(absolute)):
        if os.name != "nt":
            _raise("symlink-or-reparse", Path("."), "root-resolution-changed")
        resolved_metadata = _lstat(resolved, Path("."), missing_code="root-missing")
        _assert_directory(resolved, Path("."), resolved_metadata)
        if _stat_identity(before) != _stat_identity(resolved_metadata):
            _raise("symlink-or-reparse", Path("."), "root-resolution-changed")
        verified = resolved
    after = _lstat(absolute, Path("."), missing_code="root-missing")
    if _stat_snapshot(before) != _stat_snapshot(after):
        _raise("identity-drift", Path("."), "root-changed")
    return verified


def _stat_at(
    directory_descriptor: int,
    leaf: str,
    relative: Path,
    *,
    missing_code: str = "missing-entry",
) -> os.stat_result:
    try:
        return os.stat(leaf, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise SafeFilesystemError(missing_code, relative) from exc
    except OSError as exc:
        raise SafeFilesystemError("metadata-unavailable", relative, str(exc)) from exc


def _open_verified_parent_posix(root: Path, relative: Path) -> _VerifiedPosixParent:
    normalized = validate_relative_path(relative)
    verified_root = _verified_root(root)
    root_before = _lstat(verified_root, Path("."), missing_code="root-missing")
    _assert_directory_metadata(Path("."), root_before)
    try:
        descriptor = os.open(verified_root, _POSIX_DIRECTORY_OPEN_FLAGS)
    except OSError as exc:
        raise SafeFilesystemError("root-unavailable", Path("."), str(exc)) from exc
    current_relative = Path()
    current_path = verified_root
    try:
        opened = os.fstat(descriptor)
        _assert_directory_metadata(Path("."), opened)
        if _stat_identity(root_before) != _stat_identity(opened):
            _raise("identity-drift", Path("."), "root-name-and-handle-differ")
        for index, component in enumerate(normalized.parts[:-1], start=1):
            child_relative = Path(*normalized.parts[:index])
            before = _stat_at(
                descriptor,
                component,
                child_relative,
                missing_code="missing-parent",
            )
            _assert_directory_metadata(child_relative, before)
            try:
                child_descriptor = os.open(
                    component,
                    _POSIX_DIRECTORY_OPEN_FLAGS,
                    dir_fd=descriptor,
                )
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.EMLINK, errno.ENOTDIR}:
                    raise SafeFilesystemError("symlink-or-reparse", child_relative) from exc
                if exc.errno == errno.ENOENT:
                    raise SafeFilesystemError("missing-parent", child_relative) from exc
                raise SafeFilesystemError("open-failed", child_relative, str(exc)) from exc
            try:
                child_opened = os.fstat(child_descriptor)
                _assert_directory_metadata(child_relative, child_opened)
                if _stat_identity(before) != _stat_identity(child_opened):
                    _raise("identity-drift", child_relative, "name-and-handle-differ")
            except BaseException:
                os.close(child_descriptor)
                raise
            os.close(descriptor)
            descriptor = child_descriptor
            opened = child_opened
            current_relative = child_relative
            current_path = current_path / component
        return _VerifiedPosixParent(
            root=verified_root,
            relative=current_relative,
            path=current_path,
            descriptor=descriptor,
            opened=opened,
            leaf=normalized.name,
        )
    except BaseException:
        os.close(descriptor)
        raise


def _create_candidate_descriptor_posix(
    parent_descriptor: int,
    name: str,
    flags: int,
) -> int:
    return os.open(name, flags, 0o600, dir_fd=parent_descriptor)


def _replace_names_posix(
    source_descriptor: int,
    source_name: str,
    destination_descriptor: int,
    destination_name: str,
    *,
    relative: Path | None = None,
) -> None:
    os.replace(
        source_name,
        destination_name,
        src_dir_fd=source_descriptor,
        dst_dir_fd=destination_descriptor,
    )
    try:
        os.fsync(source_descriptor)
        if destination_descriptor != source_descriptor:
            os.fsync(destination_descriptor)
    except OSError as exc:
        if relative is None:
            raise
        raise SafeFilesystemError(
            "publish-durability-failed",
            relative,
            str(exc),
            commit_state="committed",
        ) from exc


def _verified_parent(root: Path, relative: Path) -> tuple[Path, Path, Path]:
    normalized = validate_relative_path(relative)
    verified_root = _verified_root(root)
    current = verified_root
    parent_parts = normalized.parts[:-1]
    for index, component in enumerate(parent_parts, start=1):
        current = current / component
        current_relative = Path(*normalized.parts[:index])
        metadata = _lstat(current, current_relative, missing_code="missing-parent")
        _assert_directory(current, current_relative, metadata)
    destination = current / normalized.name
    try:
        destination.relative_to(verified_root)
    except ValueError as exc:
        raise SafeFilesystemError("unsafe-relative-path", normalized, "escaped-root") from exc
    return verified_root, current, destination


def _assert_no_sibling_collision(root: Path, relative: Path) -> None:
    normalized = validate_relative_path(relative)
    parent_relative = Path(*normalized.parts[:-1])
    if os.name == "nt":
        import court_safe_fs_windows

        _, parent, _ = _verified_parent(root, normalized)
        names = court_safe_fs_windows.list_verified_directory_names(
            parent,
            parent_relative,
        )
    else:
        parent = _open_verified_parent_posix(root, normalized)
        try:
            try:
                with os.scandir(parent.descriptor) as scanner:
                    names = tuple(entry.name for entry in scanner)
            except OSError as exc:
                raise SafeFilesystemError(
                    "directory-scan-failed",
                    parent_relative,
                    str(exc),
                ) from exc
        finally:
            parent.close()
    target_key = _component_key(normalized.name)
    seen: dict[str, str] = {}
    for name in sorted(names, key=lambda value: (_component_key(value), value)):
        key = _component_key(name)
        previous = seen.get(key)
        if previous is not None and previous != name:
            collision = parent_relative / name if parent_relative.parts else Path(name)
            _raise("path-collision", collision, previous)
        seen[key] = name
        if key == target_key and name != normalized.name:
            _raise("path-collision", normalized, name)


def _open_regular_file(root: Path, relative: Path, *, verify_windows: bool) -> _OpenRegularFile:
    normalized = validate_relative_path(relative)
    if os.name != "nt" and not verify_windows:
        parent = _open_verified_parent_posix(root, normalized)
        try:
            before = _stat_at(parent.descriptor, parent.leaf, normalized)
            _assert_regular_metadata(normalized, before)
            try:
                descriptor = os.open(
                    parent.leaf,
                    _POSIX_READ_OPEN_FLAGS,
                    dir_fd=parent.descriptor,
                )
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.EMLINK}:
                    raise SafeFilesystemError("symlink-or-reparse", normalized) from exc
                if exc.errno == errno.ENOENT:
                    raise SafeFilesystemError(
                        "identity-drift",
                        normalized,
                        "entry-disappeared",
                    ) from exc
                raise SafeFilesystemError("open-failed", normalized, str(exc)) from exc
            try:
                opened = os.fstat(descriptor)
                _assert_regular_metadata(normalized, opened)
                if _stat_identity(before) != _stat_identity(opened):
                    _raise("identity-drift", normalized, "name-and-handle-differ")
                return _OpenRegularFile(
                    parent.root,
                    normalized,
                    parent.path / parent.leaf,
                    descriptor,
                    opened,
                    parent,
                )
            except BaseException:
                os.close(descriptor)
                raise
        except BaseException:
            parent.close()
            raise
    verified_root, _, path = _verified_parent(root, normalized)
    before = _lstat(path, normalized)
    _assert_regular(path, normalized, before)
    try:
        if verify_windows and os.name == "nt":
            import court_safe_fs_windows

            descriptor = court_safe_fs_windows.open_verified_regular_descriptor(path, normalized)
        else:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise SafeFilesystemError("symlink-or-reparse", normalized) from exc
        if exc.errno == errno.ENOENT:
            raise SafeFilesystemError("identity-drift", normalized, "entry-disappeared") from exc
        raise SafeFilesystemError("open-failed", normalized, str(exc)) from exc
    try:
        opened = os.fstat(descriptor)
        _assert_regular(path, normalized, opened)
        if _stat_identity(before) != _stat_identity(opened):
            _raise("identity-drift", normalized, "name-and-handle-differ")
        platform_snapshot: tuple[object, ...] | None = None
        if verify_windows and os.name == "nt":
            import court_safe_fs_windows

            information = court_safe_fs_windows.verify_open_descriptor(
                descriptor,
                path,
                opened,
                relative=normalized,
            )
            platform_snapshot = court_safe_fs_windows.handle_information_snapshot(
                information
            )
        return _OpenRegularFile(
            verified_root,
            normalized,
            path,
            descriptor,
            opened,
            platform_snapshot=platform_snapshot,
        )
    except BaseException:
        os.close(descriptor)
        raise


def _finish_regular_file(opened_file: _OpenRegularFile) -> None:
    current_handle = os.fstat(opened_file.descriptor)
    if opened_file.parent is not None:
        _assert_regular_metadata(opened_file.relative, current_handle)
    else:
        _assert_regular(opened_file.path, opened_file.relative, current_handle)
    if _stat_snapshot(opened_file.opened) != _stat_snapshot(current_handle):
        _raise("identity-drift", opened_file.relative, "handle-changed-during-read")
    if opened_file.parent is not None:
        try:
            current_name = _stat_at(
                opened_file.parent.descriptor,
                opened_file.parent.leaf,
                opened_file.relative,
            )
        except SafeFilesystemError as exc:
            if exc.code == "missing-entry":
                _raise("identity-drift", opened_file.relative, "entry-unlinked-during-read")
            raise
        _assert_regular_metadata(opened_file.relative, current_name)
        current_parent = os.fstat(opened_file.parent.descriptor)
        _assert_directory_metadata(opened_file.parent.relative, current_parent)
        if _stat_identity(opened_file.parent.opened) != _stat_identity(current_parent):
            _raise("identity-drift", opened_file.parent.relative, "parent-handle-changed")
    else:
        try:
            current_name = _lstat(opened_file.path, opened_file.relative)
        except SafeFilesystemError as exc:
            if exc.code == "missing-entry":
                _raise("identity-drift", opened_file.relative, "entry-unlinked-during-read")
            raise
        _assert_regular(opened_file.path, opened_file.relative, current_name)
    if _stat_snapshot(opened_file.opened) != _stat_snapshot(current_name):
        _raise("identity-drift", opened_file.relative, "name-changed-during-read")
    if opened_file.parent is None:
        if os.name == "nt":
            import court_safe_fs_windows

            information = court_safe_fs_windows.verify_open_descriptor(
                opened_file.descriptor,
                opened_file.path,
                current_handle,
                relative=opened_file.relative,
            )
            if (
                opened_file.platform_snapshot is not None
                and court_safe_fs_windows.handle_information_snapshot(information)
                != opened_file.platform_snapshot
            ):
                _raise(
                    "identity-drift",
                    opened_file.relative,
                    "windows-handle-changed-during-read",
                )
        _verified_parent(opened_file.root, opened_file.relative)


def _close_regular_file(opened_file: _OpenRegularFile) -> None:
    try:
        os.close(opened_file.descriptor)
    finally:
        if opened_file.parent is not None:
            opened_file.parent.close()


def _read_regular_file_platform(
    root: Path,
    relative: Path,
    max_bytes: int,
    *,
    verify_windows: bool,
) -> bytes:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        _raise("invalid-max-bytes", Path(relative), repr(max_bytes))
    opened_file = _open_regular_file(root, relative, verify_windows=verify_windows)
    try:
        if opened_file.opened.st_size > max_bytes:
            _raise(
                "file-too-large",
                opened_file.relative,
                f"limit={max_bytes};observed={opened_file.opened.st_size}",
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(opened_file.descriptor, min(_CHUNK_SIZE, max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                _raise("file-too-large", opened_file.relative, f"limit={max_bytes};observed>{max_bytes}")
            chunks.append(chunk)
        _finish_regular_file(opened_file)
        return b"".join(chunks)
    finally:
        _close_regular_file(opened_file)


def _hash_regular_file(root: Path, relative: Path, *, verify_windows: bool) -> GeneratedFile:
    opened_file = _open_regular_file(root, relative, verify_windows=verify_windows)
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = os.read(opened_file.descriptor, _CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        _finish_regular_file(opened_file)
        return GeneratedFile(
            opened_file.relative,
            digest.hexdigest(),
            size,
            (*_stat_snapshot(opened_file.opened), opened_file.platform_snapshot),
        )
    finally:
        _close_regular_file(opened_file)


def _walk_verified_directory(
    root: Path,
    directory: Path,
    relative_directory: Path,
    seen: dict[str, Path],
) -> Iterator[tuple[Path, Path]]:
    before_directory = _lstat(directory, relative_directory, missing_code="missing-entry")
    _assert_directory(directory, relative_directory, before_directory)
    try:
        with os.scandir(directory) as scanner:
            entries = sorted(
                list(scanner),
                key=lambda entry: (_component_key(entry.name), entry.name),
            )
    except OSError as exc:
        raise SafeFilesystemError("directory-scan-failed", relative_directory, str(exc)) from exc
    for entry in entries:
        raw_relative = relative_directory / entry.name
        normalized = validate_relative_path(raw_relative)
        key = normalized_relative_key(normalized)
        previous = seen.get(key)
        if previous is not None and os.fspath(previous) != os.fspath(raw_relative):
            _raise("path-collision", normalized, previous.as_posix())
        seen[key] = raw_relative
        path = Path(entry.path)
        metadata = _lstat(path, normalized)
        _assert_not_reparse(path, normalized, metadata)
        try:
            entry_metadata = path.lstat()
        except FileNotFoundError as exc:
            raise SafeFilesystemError("identity-drift", normalized, "entry-disappeared") from exc
        except OSError as exc:
            raise SafeFilesystemError("metadata-unavailable", normalized, str(exc)) from exc
        if _stat_snapshot(metadata) != _stat_snapshot(entry_metadata):
            _raise("identity-drift", normalized, "directory-entry-changed")
        if stat.S_ISDIR(metadata.st_mode):
            yield from _walk_verified_directory(root, path, normalized, seen)
        elif stat.S_ISREG(metadata.st_mode):
            _assert_regular(path, normalized, metadata)
            yield normalized, path
        else:
            _raise("unsupported-special-file", normalized)
    after_directory = _lstat(directory, relative_directory, missing_code="identity-drift")
    _assert_directory(directory, relative_directory, after_directory)
    if _stat_snapshot(before_directory) != _stat_snapshot(after_directory):
        _raise("identity-drift", relative_directory, "directory-changed-during-walk")


def _walk_verified_directory_posix(
    root: Path,
    descriptor: int,
    relative_directory: Path,
    seen: dict[str, Path],
) -> Iterator[tuple[Path, Path]]:
    before_directory = os.fstat(descriptor)
    _assert_directory_metadata(relative_directory, before_directory)
    try:
        with os.scandir(descriptor) as scanner:
            entries = sorted(
                list(scanner),
                key=lambda entry: (_component_key(entry.name), entry.name),
            )
    except OSError as exc:
        raise SafeFilesystemError("directory-scan-failed", relative_directory, str(exc)) from exc
    for entry in entries:
        raw_relative = relative_directory / entry.name
        normalized = validate_relative_path(raw_relative)
        key = normalized_relative_key(normalized)
        previous = seen.get(key)
        if previous is not None and os.fspath(previous) != os.fspath(raw_relative):
            _raise("path-collision", normalized, previous.as_posix())
        seen[key] = raw_relative
        metadata = _stat_at(descriptor, entry.name, normalized)
        if _metadata_is_reparse(metadata):
            _raise("symlink-or-reparse", normalized)
        if stat.S_ISDIR(metadata.st_mode):
            try:
                child_descriptor = os.open(
                    entry.name,
                    _POSIX_DIRECTORY_OPEN_FLAGS,
                    dir_fd=descriptor,
                )
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.EMLINK, errno.ENOTDIR}:
                    raise SafeFilesystemError("symlink-or-reparse", normalized) from exc
                if exc.errno == errno.ENOENT:
                    raise SafeFilesystemError(
                        "identity-drift",
                        normalized,
                        "entry-disappeared",
                    ) from exc
                raise SafeFilesystemError("open-failed", normalized, str(exc)) from exc
            try:
                child_opened = os.fstat(child_descriptor)
                _assert_directory_metadata(normalized, child_opened)
                if _stat_identity(metadata) != _stat_identity(child_opened):
                    _raise("identity-drift", normalized, "name-and-handle-differ")
                yield from _walk_verified_directory_posix(
                    root,
                    child_descriptor,
                    normalized,
                    seen,
                )
            finally:
                os.close(child_descriptor)
        elif stat.S_ISREG(metadata.st_mode):
            _assert_regular_metadata(normalized, metadata)
            yield normalized, root / raw_relative
        else:
            _raise("unsupported-special-file", normalized)
    after_directory = os.fstat(descriptor)
    _assert_directory_metadata(relative_directory, after_directory)
    if _stat_snapshot(before_directory) != _stat_snapshot(after_directory):
        _raise("identity-drift", relative_directory, "directory-changed-during-walk")


def iter_regular_files_beneath(root: Path) -> Iterator[tuple[Path, Path]]:
    if os.name != "nt":
        parent = _open_verified_parent_posix(root, Path("placeholder"))
        try:
            seen: dict[str, Path] = {}
            yield from _walk_verified_directory_posix(
                parent.root,
                parent.descriptor,
                Path(),
                seen,
            )
        finally:
            parent.close()
        return
    import court_safe_fs_windows

    yield from court_safe_fs_windows.iter_regular_files_handle(root)


def read_regular_file_beneath(root: Path, relative: Path, *, max_bytes: int) -> bytes:
    normalized = validate_relative_path(relative)
    if os.name == "nt":
        import court_safe_fs_windows

        return court_safe_fs_windows.read_regular_file_handle(root, normalized, max_bytes)
    return _read_regular_file_platform(root, normalized, max_bytes, verify_windows=False)


def _candidate_suffix(suffix: str) -> str:
    if not isinstance(suffix, str) or any(character in suffix for character in ("/", "\\", ":")):
        raise ValueError("candidate suffix must be a portable filename suffix")
    if any(ord(character) < 32 or ord(character) == 127 for character in suffix):
        raise ValueError("candidate suffix contains a control character")
    if suffix.endswith((".", " ")):
        raise ValueError("candidate suffix has an unsafe ending")
    validate_relative_path(Path(f"candidate{suffix}"))
    return suffix


def _create_candidate_in_directory(root: Path, relative_directory: Path, *, suffix: str) -> SafeCandidateFile:
    safe_suffix = _candidate_suffix(suffix)
    verified_root = _verified_root(root)
    directory = verified_root
    probe = validate_relative_path(relative_directory / "placeholder")
    posix_parent: _VerifiedPosixParent | None = None
    if os.name == "nt":
        if relative_directory.parts:
            _, directory, _ = _verified_parent(verified_root, probe)
    else:
        posix_parent = _open_verified_parent_posix(verified_root, probe)
        directory = posix_parent.path
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_RDWR
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        for _ in range(32):
            name = f".court-candidate-{secrets.token_hex(12)}{safe_suffix}"
            relative = relative_directory / name if relative_directory.parts else Path(name)
            path = directory / name
            _assert_no_sibling_collision(verified_root, relative)
            try:
                if os.name == "nt":
                    import court_safe_fs_windows

                    descriptor = court_safe_fs_windows.create_shared_candidate_descriptor(
                        path,
                        relative=relative,
                    )
                else:
                    assert posix_parent is not None
                    descriptor = _create_candidate_descriptor_posix(
                        posix_parent.descriptor,
                        name,
                        flags,
                    )
            except FileExistsError:
                continue
            except OSError as exc:
                raise SafeFilesystemError("candidate-create-failed", relative, str(exc)) from exc
            try:
                opened = os.fstat(descriptor)
                if posix_parent is not None:
                    _assert_regular_metadata(relative, opened)
                    named = _stat_at(posix_parent.descriptor, name, relative)
                    _assert_regular_metadata(relative, named)
                else:
                    _assert_regular(path, relative, opened)
                    named = _lstat(path, relative)
                    _assert_regular(path, relative, named)
                if _stat_identity(opened) != _stat_identity(named):
                    _raise("identity-drift", relative, "candidate-name-and-handle-differ")
                platform_handle: int | None = None
                if os.name == "nt":
                    import court_safe_fs_windows

                    platform_handle = court_safe_fs_windows.platform_handle_from_fd(descriptor)
                    court_safe_fs_windows.verify_open_descriptor(
                        descriptor,
                        path,
                        opened,
                        relative=relative,
                    )
                file_object = os.fdopen(descriptor, "w+b")
                return SafeCandidateFile(relative, file_object, platform_handle)
            except BaseException:
                os.close(descriptor)
                if posix_parent is not None:
                    try:
                        os.unlink(name, dir_fd=posix_parent.descriptor)
                    except FileNotFoundError:
                        pass
                else:
                    path.unlink(missing_ok=True)
                raise
        _raise("candidate-create-failed", relative_directory, "name-exhausted")
    finally:
        if posix_parent is not None:
            posix_parent.close()


def create_candidate_file_beneath(root: Path, *, suffix: str) -> SafeCandidateFile:
    return _create_candidate_in_directory(root, Path(), suffix=suffix)


def _candidate_generated_file(root: Path, candidate: SafeCandidateFile) -> tuple[Path, GeneratedFile]:
    if candidate.file_object.closed:
        _raise("candidate-closed", candidate.relative)
    normalized = validate_relative_path(candidate.relative)
    posix_parent: _VerifiedPosixParent | None = None
    if os.name == "nt":
        verified_root, _, path = _verified_parent(root, normalized)
    else:
        posix_parent = _open_verified_parent_posix(root, normalized)
        verified_root = posix_parent.root
        path = posix_parent.path / posix_parent.leaf
    try:
        try:
            candidate.file_object.flush()
            descriptor = candidate.file_object.fileno()
            os.fsync(descriptor)
        except (OSError, ValueError) as exc:
            raise SafeFilesystemError("candidate-flush-failed", normalized, str(exc)) from exc
        opened = os.fstat(descriptor)
        if posix_parent is not None:
            _assert_regular_metadata(normalized, opened)
            named = _stat_at(posix_parent.descriptor, posix_parent.leaf, normalized)
            _assert_regular_metadata(normalized, named)
        else:
            _assert_regular(path, normalized, opened)
            named = _lstat(path, normalized)
            _assert_regular(path, normalized, named)
        if _stat_identity(opened) != _stat_identity(named):
            _raise("identity-drift", normalized, "candidate-name-and-handle-differ")
        windows_snapshot: tuple[object, ...] | None = None
        if os.name == "nt":
            import court_safe_fs_windows

            actual_handle = court_safe_fs_windows.platform_handle_from_fd(descriptor)
            if candidate.platform_handle is not None and candidate.platform_handle != actual_handle:
                _raise("identity-drift", normalized, "candidate-platform-handle-changed")
            information = court_safe_fs_windows.verify_open_descriptor(
                descriptor,
                path,
                opened,
                relative=normalized,
            )
            windows_snapshot = court_safe_fs_windows.handle_information_snapshot(
                information
            )
        try:
            position = candidate.file_object.tell()
            candidate.file_object.seek(0)
        except (OSError, ValueError) as exc:
            raise SafeFilesystemError("candidate-read-failed", normalized, str(exc)) from exc
        digest = hashlib.sha256()
        size = 0
        try:
            while True:
                chunk = candidate.file_object.read(_CHUNK_SIZE)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    _raise("candidate-read-failed", normalized, "non-binary-file-object")
                digest.update(chunk)
                size += len(chunk)
        finally:
            candidate.file_object.seek(position)
        after = os.fstat(descriptor)
        if _stat_snapshot(opened) != _stat_snapshot(after):
            _raise("identity-drift", normalized, "candidate-changed-during-hash")
        if posix_parent is not None:
            current_name = _stat_at(posix_parent.descriptor, posix_parent.leaf, normalized)
            if _stat_snapshot(opened) != _stat_snapshot(current_name):
                _raise("identity-drift", normalized, "candidate-name-changed-during-hash")
        else:
            try:
                current_name = _lstat(path, normalized)
            except SafeFilesystemError as exc:
                if exc.code == "missing-entry":
                    _raise("identity-drift", normalized, "candidate-unlinked-during-hash")
                raise
            if _stat_snapshot(opened) != _stat_snapshot(current_name):
                _raise("identity-drift", normalized, "candidate-name-changed-during-hash")
            if os.name == "nt":
                current_information = court_safe_fs_windows.verify_open_descriptor(
                    descriptor,
                    path,
                    after,
                    relative=normalized,
                )
                if (
                    windows_snapshot is not None
                    and court_safe_fs_windows.handle_information_snapshot(current_information)
                    != windows_snapshot
                ):
                    _raise(
                        "identity-drift",
                        normalized,
                        "candidate-windows-handle-changed-during-hash",
                    )
        return verified_root, GeneratedFile(
            normalized,
            digest.hexdigest(),
            size,
            (*_stat_snapshot(opened), windows_snapshot),
        )
    finally:
        if posix_parent is not None:
            posix_parent.close()


def _capture_destination_generation(
    root: Path,
    relative: Path,
    *,
    verify_windows: bool,
) -> _DestinationGeneration:
    normalized = validate_relative_path(relative)
    try:
        opened_file = _open_regular_file(root, normalized, verify_windows=verify_windows)
    except SafeFilesystemError as exc:
        if exc.code == "missing-entry":
            return _DestinationGeneration(False)
        raise
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = os.read(opened_file.descriptor, _CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        _finish_regular_file(opened_file)
        return _DestinationGeneration(
            True,
            (*_stat_snapshot(opened_file.opened), opened_file.platform_snapshot),
            digest.hexdigest(),
            size,
        )
    finally:
        _close_regular_file(opened_file)


def _expected_destination_matches(
    expected: ExpectedDestination,
    generation: _DestinationGeneration,
) -> bool:
    if expected.mode == "absent":
        return not generation.exists
    if expected.mode == "any":
        return True
    return generation.exists and generation.sha256 == expected.sha256


def _destination_matches(root: Path, relative: Path, expected: ExpectedDestination) -> bool:
    generation = _capture_destination_generation(
        root,
        relative,
        verify_windows=os.name == "nt",
    )
    return _expected_destination_matches(expected, generation)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _raise_committed_failure(relative: Path, error: Exception) -> None:
    if isinstance(error, SafeFilesystemError):
        if error.commit_state == "committed":
            raise error
        raise SafeFilesystemError(
            error.code,
            error.relative,
            error.detail,
            commit_state="committed",
        ) from error
    raise SafeFilesystemError(
        "publish-post-commit-failed",
        relative,
        str(error),
        commit_state="committed",
    ) from error


def _publish_candidate_platform(
    root: Path,
    relative: Path,
    candidate: SafeCandidateFile,
    expected: ExpectedDestination,
    *,
    verify_windows: bool,
) -> bool:
    normalized = validate_relative_path(relative)
    verified_root = _verified_root(root)
    _assert_no_sibling_collision(verified_root, normalized)
    candidate_root, generated = _candidate_generated_file(verified_root, candidate)
    if candidate_root != verified_root:
        _raise("candidate-outside-root", candidate.relative)
    captured_destination = _capture_destination_generation(
        verified_root,
        normalized,
        verify_windows=verify_windows,
    )
    if not _expected_destination_matches(expected, captured_destination):
        return False
    candidate_root, repeated = _candidate_generated_file(verified_root, candidate)
    if candidate_root != verified_root or repeated != generated:
        _raise("identity-drift", candidate.relative, "candidate-changed-before-publish")
    _assert_no_sibling_collision(verified_root, normalized)
    current_destination = _capture_destination_generation(
        verified_root,
        normalized,
        verify_windows=verify_windows,
    )
    if current_destination != captured_destination:
        return False
    descriptor = candidate.file_object.fileno()
    if os.name != "nt" and not verify_windows:
        source_parent = _open_verified_parent_posix(verified_root, generated.relative)
        try:
            destination_parent = _open_verified_parent_posix(verified_root, normalized)
            try:
                candidate_named = _stat_at(
                    source_parent.descriptor,
                    source_parent.leaf,
                    generated.relative,
                )
                _assert_regular_metadata(generated.relative, candidate_named)
                candidate_handle = os.fstat(descriptor)
                _assert_regular_metadata(generated.relative, candidate_handle)
                if _stat_identity(candidate_named) != _stat_identity(candidate_handle):
                    _raise(
                        "identity-drift",
                        generated.relative,
                        "candidate-name-and-handle-differ",
                    )
                try:
                    _replace_names_posix(
                        source_parent.descriptor,
                        source_parent.leaf,
                        destination_parent.descriptor,
                        destination_parent.leaf,
                        relative=normalized,
                    )
                except OSError as exc:
                    raise SafeFilesystemError("publish-failed", normalized, str(exc)) from exc
                try:
                    published = _stat_at(
                        destination_parent.descriptor,
                        destination_parent.leaf,
                        normalized,
                        missing_code="publish-verification-failed",
                    )
                    _assert_regular_metadata(normalized, published)
                except Exception as exc:
                    _raise_committed_failure(normalized, exc)
            finally:
                destination_parent.close()
        finally:
            source_parent.close()
        destination = verified_root / normalized
    else:
        _, parent, destination = _verified_parent(verified_root, normalized)
        candidate_path = verified_root / generated.relative
        if verify_windows and os.name == "nt":
            import court_safe_fs_windows

            court_safe_fs_windows._verify_windows_parent_chain(destination, normalized)
        try:
            os.replace(candidate_path, destination)
        except OSError as exc:
            raise SafeFilesystemError("publish-failed", normalized, str(exc)) from exc
        try:
            _fsync_directory(parent)
            published = _lstat(
                destination,
                normalized,
                missing_code="publish-verification-failed",
            )
            _assert_regular(destination, normalized, published)
        except Exception as exc:
            _raise_committed_failure(normalized, exc)
    try:
        handle_metadata = os.fstat(descriptor)
        if _stat_identity(published) != _stat_identity(handle_metadata):
            _raise("identity-drift", normalized, "published-name-and-handle-differ")
        if verify_windows and os.name == "nt":
            import court_safe_fs_windows

            court_safe_fs_windows.verify_open_descriptor(
                descriptor,
                destination,
                handle_metadata,
                relative=normalized,
            )
        observed = _hash_regular_file(
            verified_root,
            normalized,
            verify_windows=verify_windows,
        )
        if observed.sha256 != generated.sha256 or observed.size_bytes != generated.size_bytes:
            _raise("publish-verification-failed", normalized, "digest-or-size-mismatch")
    except Exception as exc:
        _raise_committed_failure(normalized, exc)
    return True


def _replace_bytes_platform(
    root: Path,
    relative: Path,
    data: bytes,
    expected: ExpectedDestination,
    *,
    verify_windows: bool,
) -> bool:
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    normalized = validate_relative_path(relative)
    verified_root = _verified_root(root)
    _assert_no_sibling_collision(verified_root, normalized)
    parent_relative = Path(*normalized.parts[:-1])
    candidate = _create_candidate_in_directory(verified_root, parent_relative, suffix=".tmp")
    publication_committed = False
    primary_error: Exception | None = None
    try:
        candidate.file_object.write(data)
        publication_committed = _publish_candidate_platform(
            verified_root,
            normalized,
            candidate,
            expected,
            verify_windows=verify_windows,
        )
        return publication_committed
    except Exception as exc:
        primary_error = exc
        raise
    finally:
        close_error: OSError | None = None
        try:
            candidate.file_object.close()
        except OSError as exc:
            close_error = exc

        cleanup_error: Exception | None = None
        try:
            if os.name == "nt":
                candidate_path = verified_root / candidate.relative
                candidate_path.unlink(missing_ok=True)
            else:
                try:
                    candidate_parent = _open_verified_parent_posix(
                        verified_root,
                        candidate.relative,
                    )
                except SafeFilesystemError as exc:
                    if exc.code != "missing-entry":
                        raise
                else:
                    try:
                        os.unlink(candidate_parent.leaf, dir_fd=candidate_parent.descriptor)
                    except FileNotFoundError:
                        pass
                    finally:
                        candidate_parent.close()
        except Exception as exc:
            cleanup_error = exc

        primary_committed = (
            isinstance(primary_error, SafeFilesystemError)
            and primary_error.commit_state == "committed"
        )
        if not primary_committed:
            if close_error is not None:
                raise SafeFilesystemError(
                    "candidate-close-failed",
                    candidate.relative,
                    str(close_error),
                    commit_state="committed" if publication_committed else "not-committed",
                ) from close_error
            if cleanup_error is not None:
                raise cleanup_error


def atomic_replace_bytes_beneath(
    root: Path,
    relative: Path,
    data: bytes,
    *,
    expected: ExpectedDestination,
) -> bool:
    normalized = validate_relative_path(relative)
    if os.name == "nt":
        import court_safe_fs_windows

        return court_safe_fs_windows.replace_bytes_handle(root, normalized, data, expected)
    return _replace_bytes_platform(root, normalized, data, expected, verify_windows=False)


def atomic_publish_file_beneath(
    root: Path,
    relative: Path,
    candidate: SafeCandidateFile,
    *,
    expected: ExpectedDestination,
) -> bool:
    normalized = validate_relative_path(relative)
    if os.name == "nt":
        import court_safe_fs_windows

        return court_safe_fs_windows.publish_candidate_handle(root, normalized, candidate, expected)
    return _publish_candidate_platform(
        root,
        normalized,
        candidate,
        expected,
        verify_windows=False,
    )


__all__ = [
    "ExpectedDestination",
    "GeneratedFile",
    "SafeCandidateFile",
    "SafeFilesystemError",
    "atomic_publish_file_beneath",
    "atomic_replace_bytes_beneath",
    "create_candidate_file_beneath",
    "is_link_or_reparse",
    "iter_regular_files_beneath",
    "normalized_relative_key",
    "read_regular_file_beneath",
    "validate_relative_path",
]
