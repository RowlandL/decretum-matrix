"""Focused checks for Windows Codex host command resolution."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True

import court_codex_host_resolution as host_resolution
from court_codex_host_resolution import (
    build_resolution_report,
    ensure_front_link,
    parse_codex_version,
)


def main() -> int:
    assert parse_codex_version("codex-cli 0.144.1\n") == "0.144.1"
    try:
        parse_codex_version("Codex unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid Codex version output was accepted")

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        native = root / "native-codex.exe"
        front = root / "front" / "codex.exe"
        native.write_bytes(b"verified-native")
        front.parent.mkdir()
        os.link(native, front)

        with patch.object(Path, "read_bytes", side_effect=AssertionError("host file rehash")):
            report = build_resolution_report(
            native_path=native,
            front_path=front,
            native_version_output="codex-cli 0.144.1",
            front_version_output="codex-cli 0.144.1",
            bare_version_output="codex-cli 0.144.1",
            which_path=front,
        )
        assert report["healthy"] is True
        assert report["ok"] is True
        assert report["same_file_identity"] is True
        assert report["native_sha256"] is None
        assert report["binary_identity_status"] == "UNAVAILABLE_NOT_REHASHED"

        copied = root / "copied-codex.exe"
        copied.write_bytes(native.read_bytes())
        stale = build_resolution_report(
            native_path=native,
            front_path=copied,
            native_version_output="codex-cli 0.144.1",
            front_version_output="codex-cli 0.144.1",
            bare_version_output="codex-cli 0.144.1",
            which_path=copied,
        )
        assert stale["hash_equal"] is None
        assert stale["same_file_identity"] is False
        assert stale["healthy"] is False
        assert stale["ok"] is False

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        native = root / "native-codex.exe"
        front = root / "front" / "codex.exe"
        backup = root / "backups"
        native.write_bytes(b"new-native")
        front.parent.mkdir()
        front.write_bytes(b"old-conflict")
        result = ensure_front_link(
            native_path=native,
            front_path=front,
            backup_root=backup,
            prefer_symlink=False,
        )
        assert result["changed"] is True
        assert result["link_kind"] == "hardlink"
        assert Path(str(result["migrated_path"])).read_bytes() == b"old-conflict"
        assert os.path.samefile(native, front)

    print("COURT_CODEX_HOST_RESOLUTION_OK")
    # Applicability contract: a host without both npm premises must be told so
    # explicitly, and that verdict must never be reported as a healthy npm
    # resolution. Explicit path probes stay strict.
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        absent_native = root / "vendor" / "codex.exe"
        # The absent-premise verdict must not depend on this host's real PATH: pin it
        # to a directory that provably holds no npm shim.
        shimless_path = root / "shimless-path"
        shimless_path.mkdir()
        with patch.dict(os.environ, {"PATH": str(shimless_path)}, clear=False):
            bare_report = host_resolution.applicability_report(absent_native)
        assert bare_report["schema"] == host_resolution.APPLICABILITY_SCHEMA
        assert bare_report["applicable"] is False
        assert bare_report["status"] == host_resolution.APPLICABILITY_STATUS
        assert bare_report["premises"] == {"npm_shim_on_path": False, "npm_native_vendor_binary": False}
        shim_dir = root / "npm-prefix"
        shim_dir.mkdir()
        (shim_dir / "codex.cmd").write_text("@echo off\n", encoding="utf-8")
        native_copy = root / "native" / "codex.exe"
        native_copy.parent.mkdir()
        native_copy.write_bytes(b"verified-native")
        with patch.dict(os.environ, {"PATH": str(shim_dir)}, clear=False):
            shim_report = host_resolution.applicability_report(native_copy)
        assert shim_report["applicable"] is True
        assert shim_report["status"] == "APPLICABLE_NPM_SHIM_HOST"
        assert shim_report["npm_shim_directories"] == [str(shim_dir)]
        with patch.dict(os.environ, {"PATH": str(shim_dir)}, clear=False):
            half_report = host_resolution.applicability_report(absent_native)
        assert half_report["applicable"] is False
        assert half_report["premises"]["npm_shim_on_path"] is True

    # Boundary: an explicit --native-path that equals the default value is still an
    # explicit probe and must never be downgraded to the NOT_APPLICABLE verdict.
    import io
    from contextlib import redirect_stdout

    default_equal = host_resolution.default_native_path()
    with redirect_stdout(io.StringIO()):
        try:
            explicit_code = host_resolution.main(["--native-path", str(default_equal)])
        except (RuntimeError, FileNotFoundError, OSError):
            explicit_code = None
    assert explicit_code != host_resolution.APPLICABILITY_EXIT_CODE

    host_applicable = host_resolution.applicability_report(default_equal)["applicable"]
    if host_applicable is not True:
        with redirect_stdout(io.StringIO()):
            bare_code = host_resolution.main([])
        assert bare_code == host_resolution.APPLICABILITY_EXIT_CODE

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
