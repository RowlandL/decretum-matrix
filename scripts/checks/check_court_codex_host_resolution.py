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

sys.dont_write_bytecode = True

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

        report = build_resolution_report(
            native_path=native,
            front_path=front,
            native_version_output="codex-cli 0.144.1",
            front_version_output="codex-cli 0.144.1",
            bare_version_output="codex-cli 0.144.1",
            which_path=front,
        )
        assert report["healthy"] is True
        assert report["same_file_identity"] is True

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
        assert stale["hash_equal"] is True
        assert stale["same_file_identity"] is False
        assert stale["healthy"] is False

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



