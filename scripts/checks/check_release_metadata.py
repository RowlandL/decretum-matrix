"""Validate concise GitHub release metadata and README brand rendering."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
METADATA_PATH = ROOT / "references" / "manifests" / "github-release-metadata.v1.json"
ICON_PATH = "assets/brand/decretum-matrix-icon.svg"


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(f"{field}_required")
    return value.strip()


def render_release(entry: dict[str, Any]) -> str:
    title = _nonblank(entry.get("title"), "title")
    summary = _nonblank(entry.get("summary"), "summary")
    highlights = entry.get("highlights")
    if not isinstance(highlights, list) or not 2 <= len(highlights) <= 6:
        raise AssertionError("highlights_count_invalid")
    lines = [f"# {title}", "", summary, "", "## 主要变化", ""]
    for item in highlights:
        lines.append(f"- {_nonblank(item, 'highlight')}")
    install = str(entry.get("install") or "").strip()
    if install:
        lines.extend(["", f"安装：`{install}`"])
    asset_note = _nonblank(entry.get("asset_note"), "asset_note")
    lines.extend(["", asset_note])
    return "\n".join(lines).rstrip() + "\n"


def evaluate() -> dict[str, Any]:
    errors: list[str] = []
    checks: list[str] = []
    try:
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        assert metadata.get("schema") == "decretum.github_release_metadata.v1"
        current = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        assert metadata.get("latest_tag") == current, "latest_tag_not_current_version"
        policy = metadata.get("brief_policy")
        assert isinstance(policy, dict), "brief_policy_required"
        max_chars = int(policy.get("max_body_chars") or 0)
        assert 300 <= max_chars <= 1600, "max_body_chars_invalid"
        entries = metadata.get("releases")
        assert isinstance(entries, list) and entries, "release_entries_required"
        tags: list[str] = []
        for entry in entries:
            assert isinstance(entry, dict), "release_entry_invalid"
            tag = _nonblank(entry.get("tag"), "tag")
            assert tag not in tags, f"duplicate_tag:{tag}"
            body = render_release(entry)
            assert len(body) <= max_chars, f"release_body_too_long:{tag}:{len(body)}"
            tags.append(tag)
        assert current in tags, "current_release_metadata_missing"
        checks.extend(
            [
                "github_release_briefs_registered",
                "github_release_briefs_bounded",
                "github_latest_policy_registered",
            ]
        )
    except (AssertionError, FileNotFoundError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"release_metadata:{exc}")

    try:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert f'<img src="{ICON_PATH}"' in readme, "readme_brand_icon_missing"
        assert (ROOT / ICON_PATH).is_file(), "brand_icon_asset_missing"
        release_manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
        paths = {item.get("path") for item in release_manifest.get("files", []) if isinstance(item, dict)}
        assert ICON_PATH in paths, "brand_icon_not_packaged"
        checks.append("readme_brand_icon_rendered")
    except (AssertionError, FileNotFoundError, json.JSONDecodeError) as exc:
        errors.append(f"readme_brand:{exc}")

    return {
        "schema": "decretum.release_metadata_gate.v1",
        "gate": "PASSED" if not errors else "FAILED",
        "checks": checks,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"RELEASE_METADATA_{result['gate']} checks={len(result['checks'])} errors={len(result['errors'])}")
        for error in result["errors"]:
            print(error)
    return 0 if result["gate"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())



