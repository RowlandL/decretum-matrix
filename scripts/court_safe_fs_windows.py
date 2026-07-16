"""Windows handle checks for :mod:`court_safe_fs` Batch A primitives.

Every static parent and file boundary is opened with ``CreateFileW`` using
``FILE_FLAG_OPEN_REPARSE_POINT`` and ``FILE_FLAG_BACKUP_SEMANTICS``.  The open
handle is checked for reparse attributes, final path, and file identity.  Final
directory names are path-enumerated while the verified directory handle stays
open, and every discovered entry is independently opened and revalidated by
handle.  Enumeration and final publication are not handle-relative, so a
same-privilege concurrent namespace race remains until a reviewed Batch B
backend is available.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import sys
from typing import TYPE_CHECKING, Iterator


sys.dont_write_bytecode = True


if TYPE_CHECKING:
    from court_safe_fs import ExpectedDestination, SafeCandidateFile


GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_READ_ATTRIBUTES = 0x00000080
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
CREATE_NEW = 1
OPEN_EXISTING = 3
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_ATTRIBUTE_TEMPORARY = 0x00000100
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_SHARE_ALL = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
_VERIFIED_OPEN_FLAGS = FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS


@dataclass(frozen=True)
class WindowsHandleInformation:
    final_path: str
    volume_serial_number: int
    file_id: int
    file_attributes: int
    number_of_links: int
    file_size: int = 0
    last_write_time: int = 0
    change_time: int = 0


def handle_information_snapshot(
    information: WindowsHandleInformation,
) -> tuple[object, ...]:
    return (
        _normalized_final_path(information.final_path),
        information.volume_serial_number,
        information.file_id,
        information.file_attributes,
        information.number_of_links,
        information.file_size,
        information.last_write_time,
        information.change_time,
    )


def platform_handle_from_fd(descriptor: int) -> int:
    if os.name != "nt":
        return descriptor
    import msvcrt

    return int(msvcrt.get_osfhandle(descriptor))


def _descriptor_from_handle(handle: int, flags: int) -> int:
    import msvcrt

    return int(msvcrt.open_osfhandle(handle, flags))


def _close_file_handle(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    close_handle(wintypes.HANDLE(handle))


def _create_file_handle(
    path: Path,
    *,
    desired_access: int,
    share_mode: int,
    creation_disposition: int,
    flags_and_attributes: int,
) -> int:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        os.fspath(path),
        desired_access,
        share_mode,
        None,
        creation_disposition,
        flags_and_attributes,
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle in {None, invalid_handle}:
        error = ctypes.get_last_error()
        if error in {2, 3}:
            raise FileNotFoundError(error, os.strerror(error), os.fspath(path))
        if error in {80, 183}:
            raise FileExistsError(error, os.strerror(error), os.fspath(path))
        raise ctypes.WinError(error)
    return int(handle)


def _normalized_final_path(value: str) -> str:
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return os.path.normcase(os.path.abspath(value))


def _windows_handle_information(handle: int) -> WindowsHandleInformation:
    import ctypes
    from ctypes import wintypes

    class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    class FILE_BASIC_INFO(ctypes.Structure):
        _fields_ = [
            ("CreationTime", ctypes.c_longlong),
            ("LastAccessTime", ctypes.c_longlong),
            ("LastWriteTime", ctypes.c_longlong),
            ("ChangeTime", ctypes.c_longlong),
            ("FileAttributes", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = [wintypes.HANDLE, ctypes.POINTER(BY_HANDLE_FILE_INFORMATION)]
    get_information.restype = wintypes.BOOL
    get_information_ex = kernel32.GetFileInformationByHandleEx
    get_information_ex.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    get_information_ex.restype = wintypes.BOOL
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_final_path.restype = wintypes.DWORD

    information = BY_HANDLE_FILE_INFORMATION()
    if not get_information(wintypes.HANDLE(handle), ctypes.byref(information)):
        raise ctypes.WinError(ctypes.get_last_error())
    basic_information = FILE_BASIC_INFO()
    if not get_information_ex(
        wintypes.HANDLE(handle),
        0,
        ctypes.byref(basic_information),
        ctypes.sizeof(basic_information),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    required = get_final_path(wintypes.HANDLE(handle), None, 0, 0)
    if required == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = get_final_path(wintypes.HANDLE(handle), buffer, len(buffer), 0)
    if written == 0 or written >= len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    file_id = (int(information.nFileIndexHigh) << 32) | int(information.nFileIndexLow)
    file_size = (int(information.nFileSizeHigh) << 32) | int(information.nFileSizeLow)
    return WindowsHandleInformation(
        final_path=buffer.value,
        volume_serial_number=int(information.dwVolumeSerialNumber),
        file_id=file_id,
        file_attributes=int(basic_information.FileAttributes),
        number_of_links=int(information.nNumberOfLinks),
        file_size=file_size,
        last_write_time=int(basic_information.LastWriteTime),
        change_time=int(basic_information.ChangeTime),
    )


def _validate_handle_information(
    information: WindowsHandleInformation,
    expected_path: Path,
    relative: Path,
    *,
    expect_directory: bool,
) -> None:
    import court_safe_fs

    if information.file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise court_safe_fs.SafeFilesystemError(
            "symlink-or-reparse",
            relative,
            "opened-handle-reparse-attribute",
        )
    if _normalized_final_path(information.final_path) != _normalized_final_path(
        os.fspath(expected_path)
    ):
        raise court_safe_fs.SafeFilesystemError(
            "identity-drift",
            relative,
            "opened-handle-final-path-mismatch",
        )
    is_directory = bool(information.file_attributes & FILE_ATTRIBUTE_DIRECTORY)
    if is_directory != expect_directory:
        detail = "expected-directory" if expect_directory else "expected-regular-file"
        raise court_safe_fs.SafeFilesystemError("unsupported-special-file", relative, detail)
    if not expect_directory:
        if information.number_of_links == 0:
            raise court_safe_fs.SafeFilesystemError(
                "identity-drift",
                relative,
                "opened-handle-unlinked",
            )
        if information.number_of_links != 1:
            raise court_safe_fs.SafeFilesystemError(
                "hardlink-rejected",
                relative,
                f"link-count={information.number_of_links}",
            )


def _verify_windows_parent_chain(expected_path: Path, relative: Path) -> None:
    if os.name != "nt":
        return
    normalized = Path(relative)
    root = Path(expected_path)
    for _ in normalized.parts:
        root = root.parent
    paths: list[tuple[Path, Path]] = [(root, Path("."))]
    current = root
    for index, component in enumerate(normalized.parts[:-1], start=1):
        current = current / component
        paths.append((current, Path(*normalized.parts[:index])))
    for path, current_relative in paths:
        try:
            named = path.lstat()
        except FileNotFoundError as exc:
            code = "root-missing" if current_relative == Path(".") else "missing-parent"
            import court_safe_fs

            raise court_safe_fs.SafeFilesystemError(code, current_relative) from exc
        except OSError as exc:
            import court_safe_fs

            raise court_safe_fs.SafeFilesystemError(
                "metadata-unavailable",
                current_relative,
                str(exc),
            ) from exc
        try:
            handle = _create_file_handle(
                path,
                desired_access=FILE_READ_ATTRIBUTES,
                share_mode=_SHARE_ALL,
                creation_disposition=OPEN_EXISTING,
                flags_and_attributes=_VERIFIED_OPEN_FLAGS,
            )
        except FileNotFoundError as exc:
            code = "root-missing" if current_relative == Path(".") else "missing-parent"
            import court_safe_fs

            raise court_safe_fs.SafeFilesystemError(code, current_relative) from exc
        except OSError as exc:
            import court_safe_fs

            raise court_safe_fs.SafeFilesystemError(
                "windows-handle-verification-failed",
                current_relative,
                str(exc),
            ) from exc
        try:
            information = _windows_handle_information(handle)
            _validate_handle_information(
                information,
                path,
                current_relative,
                expect_directory=True,
            )
            named_file_id = int(named.st_ino) & 0xFFFFFFFFFFFFFFFF
            if information.file_id and named_file_id and information.file_id != named_file_id:
                import court_safe_fs

                raise court_safe_fs.SafeFilesystemError(
                    "identity-drift",
                    current_relative,
                    "opened-handle-file-id-mismatch",
                )
        finally:
            _close_file_handle(handle)


def _open_verified_path_handle(
    path: Path,
    relative: Path,
) -> tuple[int, WindowsHandleInformation]:
    import court_safe_fs

    _verify_windows_parent_chain(path, relative)
    try:
        handle = _create_file_handle(
            path,
            desired_access=FILE_READ_ATTRIBUTES,
            share_mode=_SHARE_ALL,
            creation_disposition=OPEN_EXISTING,
            flags_and_attributes=_VERIFIED_OPEN_FLAGS,
        )
    except FileNotFoundError as exc:
        raise court_safe_fs.SafeFilesystemError("missing-entry", relative) from exc
    except OSError as exc:
        raise court_safe_fs.SafeFilesystemError(
            "windows-handle-verification-failed",
            relative,
            str(exc),
        ) from exc
    try:
        information = _windows_handle_information(handle)
        expect_directory = bool(
            information.file_attributes & FILE_ATTRIBUTE_DIRECTORY
        )
        _validate_handle_information(
            information,
            path,
            relative,
            expect_directory=expect_directory,
        )
        return handle, information
    except BaseException:
        _close_file_handle(handle)
        raise


def _confirm_path_still_names_handle(
    path: Path,
    relative: Path,
    information: WindowsHandleInformation,
) -> None:
    import court_safe_fs

    try:
        confirmation_handle, confirmation = _open_verified_path_handle(path, relative)
    except court_safe_fs.SafeFilesystemError as exc:
        if exc.code == "missing-entry":
            raise court_safe_fs.SafeFilesystemError(
                "identity-drift",
                relative,
                "verified-handle-name-disappeared",
            ) from exc
        raise
    try:
        if (
            confirmation.volume_serial_number,
            confirmation.file_id,
        ) != (
            information.volume_serial_number,
            information.file_id,
        ):
            raise court_safe_fs.SafeFilesystemError(
                "identity-drift",
                relative,
                "verified-handle-name-changed",
            )
    finally:
        _close_file_handle(confirmation_handle)


def _scandir_names(directory: Path, relative: Path) -> tuple[str, ...]:
    import court_safe_fs

    try:
        with os.scandir(directory) as scanner:
            return tuple(entry.name for entry in scanner)
    except OSError as exc:
        raise court_safe_fs.SafeFilesystemError(
            "directory-scan-failed",
            relative,
            str(exc),
        ) from exc


def list_verified_directory_names(
    directory: Path,
    relative: Path,
) -> tuple[str, ...]:
    import court_safe_fs

    handle, before = _open_verified_path_handle(directory, relative)
    try:
        _validate_handle_information(
            before,
            directory,
            relative,
            expect_directory=True,
        )
        names = _scandir_names(directory, relative)
        after = _windows_handle_information(handle)
        _validate_handle_information(
            after,
            directory,
            relative,
            expect_directory=True,
        )
        if handle_information_snapshot(before) != handle_information_snapshot(after):
            raise court_safe_fs.SafeFilesystemError(
                "identity-drift",
                relative,
                "directory-handle-changed-during-scan",
            )
        _confirm_path_still_names_handle(directory, relative, after)
        return names
    finally:
        _close_file_handle(handle)


def _walk_verified_directory_handle(
    root: Path,
    directory: Path,
    relative_directory: Path,
    seen: dict[str, Path],
    directory_handle: int,
    before_directory: WindowsHandleInformation,
) -> Iterator[tuple[Path, Path]]:
    import court_safe_fs

    _validate_handle_information(
        before_directory,
        directory,
        relative_directory,
        expect_directory=True,
    )
    entries = sorted(
        _scandir_names(directory, relative_directory),
        key=lambda name: (court_safe_fs._component_key(name), name),
    )
    for name in entries:
        raw_relative = relative_directory / name
        normalized = court_safe_fs.validate_relative_path(raw_relative)
        key = court_safe_fs.normalized_relative_key(normalized)
        previous = seen.get(key)
        if previous is not None and os.fspath(previous) != os.fspath(raw_relative):
            raise court_safe_fs.SafeFilesystemError(
                "path-collision",
                normalized,
                previous.as_posix(),
            )
        seen[key] = raw_relative
        path = directory / name
        try:
            child_handle, child_information = _open_verified_path_handle(
                path,
                normalized,
            )
        except court_safe_fs.SafeFilesystemError as exc:
            if exc.code == "missing-entry":
                raise court_safe_fs.SafeFilesystemError(
                    "identity-drift",
                    normalized,
                    "entry-disappeared",
                ) from exc
            raise
        try:
            if child_information.file_attributes & FILE_ATTRIBUTE_DIRECTORY:
                yield from _walk_verified_directory_handle(
                    root,
                    path,
                    normalized,
                    seen,
                    child_handle,
                    child_information,
                )
            else:
                before_file = handle_information_snapshot(child_information)
                yield normalized, root / raw_relative
                after_file = _windows_handle_information(child_handle)
                _validate_handle_information(
                    after_file,
                    path,
                    normalized,
                    expect_directory=False,
                )
                if before_file != handle_information_snapshot(after_file):
                    raise court_safe_fs.SafeFilesystemError(
                        "identity-drift",
                        normalized,
                        "file-handle-changed-during-walk",
                    )
                _confirm_path_still_names_handle(path, normalized, after_file)
        finally:
            _close_file_handle(child_handle)
    after_directory = _windows_handle_information(directory_handle)
    _validate_handle_information(
        after_directory,
        directory,
        relative_directory,
        expect_directory=True,
    )
    if handle_information_snapshot(before_directory) != handle_information_snapshot(
        after_directory
    ):
        raise court_safe_fs.SafeFilesystemError(
            "identity-drift",
            relative_directory,
            "directory-handle-changed-during-walk",
        )
    _confirm_path_still_names_handle(directory, relative_directory, after_directory)


def iter_regular_files_handle(root: Path) -> Iterator[tuple[Path, Path]]:
    import court_safe_fs

    verified_root = court_safe_fs._verified_root(root)
    root_handle, root_information = _open_verified_path_handle(
        verified_root,
        Path(),
    )
    try:
        seen: dict[str, Path] = {}
        yield from _walk_verified_directory_handle(
            verified_root,
            verified_root,
            Path(),
            seen,
            root_handle,
            root_information,
        )
    finally:
        _close_file_handle(root_handle)


def verify_open_descriptor(
    descriptor: int,
    expected_path: Path,
    opened: os.stat_result,
    *,
    relative: Path | None = None,
) -> WindowsHandleInformation:
    if os.name != "nt":
        return WindowsHandleInformation(os.fspath(expected_path), 0, 0, 0, 1)
    import court_safe_fs

    error_relative = Path(relative) if relative is not None else Path(expected_path).name
    handle = platform_handle_from_fd(descriptor)
    try:
        information = _windows_handle_information(handle)
    except OSError as exc:
        raise court_safe_fs.SafeFilesystemError(
            "windows-handle-verification-failed",
            error_relative,
            str(exc),
        ) from exc
    _validate_handle_information(
        information,
        Path(expected_path),
        error_relative,
        expect_directory=False,
    )
    opened_file_id = int(opened.st_ino) & 0xFFFFFFFFFFFFFFFF
    if information.file_id and opened_file_id and information.file_id != opened_file_id:
        raise court_safe_fs.SafeFilesystemError(
            "identity-drift",
            error_relative,
            "opened-handle-file-id-mismatch",
        )
    return information


def open_verified_regular_descriptor(path: Path, relative: Path) -> int:
    if os.name != "nt":
        return os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    _verify_windows_parent_chain(path, relative)
    try:
        handle = _create_file_handle(
            path,
            desired_access=GENERIC_READ,
            share_mode=_SHARE_ALL,
            creation_disposition=OPEN_EXISTING,
            flags_and_attributes=FILE_ATTRIBUTE_NORMAL | _VERIFIED_OPEN_FLAGS,
        )
    except FileNotFoundError as exc:
        import court_safe_fs

        raise court_safe_fs.SafeFilesystemError("missing-entry", relative) from exc
    except OSError as exc:
        import court_safe_fs

        raise court_safe_fs.SafeFilesystemError("open-failed", relative, str(exc)) from exc
    try:
        descriptor = _descriptor_from_handle(
            handle,
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
    except BaseException:
        _close_file_handle(handle)
        raise
    try:
        opened = os.fstat(descriptor)
        verify_open_descriptor(descriptor, path, opened, relative=relative)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def create_shared_candidate_descriptor(path: Path, *, relative: Path | None = None) -> int:
    """Create an exclusive candidate whose open handle permits atomic rename."""

    if os.name != "nt":
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    error_relative = Path(relative) if relative is not None else Path(path).name
    _verify_windows_parent_chain(path, error_relative)
    try:
        handle = _create_file_handle(
            path,
            desired_access=GENERIC_READ | GENERIC_WRITE,
            share_mode=_SHARE_ALL,
            creation_disposition=CREATE_NEW,
            flags_and_attributes=(
                FILE_ATTRIBUTE_TEMPORARY
                | _VERIFIED_OPEN_FLAGS
            ),
        )
    except FileExistsError:
        raise
    except OSError as exc:
        import court_safe_fs

        raise court_safe_fs.SafeFilesystemError(
            "candidate-create-failed",
            error_relative,
            str(exc),
        ) from exc
    try:
        descriptor = _descriptor_from_handle(
            handle,
            os.O_RDWR | getattr(os, "O_BINARY", 0),
        )
    except BaseException:
        _close_file_handle(handle)
        raise
    try:
        opened = os.fstat(descriptor)
        verify_open_descriptor(descriptor, path, opened, relative=error_relative)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_regular_file_handle(root: Path, relative: Path, max_bytes: int) -> bytes:
    import court_safe_fs

    return court_safe_fs._read_regular_file_platform(
        root,
        relative,
        max_bytes,
        verify_windows=os.name == "nt",
    )


def replace_bytes_handle(
    root: Path,
    relative: Path,
    data: bytes,
    expected: ExpectedDestination,
) -> bool:
    import court_safe_fs

    return court_safe_fs._replace_bytes_platform(
        root,
        relative,
        data,
        expected,
        verify_windows=os.name == "nt",
    )


def publish_candidate_handle(
    root: Path,
    relative: Path,
    candidate: SafeCandidateFile,
    expected: ExpectedDestination,
) -> bool:
    import court_safe_fs

    return court_safe_fs._publish_candidate_platform(
        root,
        relative,
        candidate,
        expected,
        verify_windows=os.name == "nt",
    )


__all__ = [
    "FILE_FLAG_BACKUP_SEMANTICS",
    "FILE_FLAG_OPEN_REPARSE_POINT",
    "WindowsHandleInformation",
    "create_shared_candidate_descriptor",
    "handle_information_snapshot",
    "iter_regular_files_handle",
    "list_verified_directory_names",
    "open_verified_regular_descriptor",
    "platform_handle_from_fd",
    "publish_candidate_handle",
    "read_regular_file_handle",
    "replace_bytes_handle",
    "verify_open_descriptor",
]
