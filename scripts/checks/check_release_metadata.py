"""Validate the active release projection and concise GitHub release metadata."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
META = "references/manifests/github-release-metadata.v1.json"
ICON = "assets/brand/decretum-matrix-icon.svg"
TARGET = "beta1.1.2"
PRIVATE = "0.0.0-private"
def read(root: Path, path: str) -> str:
    return (root / path).read_text(encoding="utf-8")
def one(value: str, pattern: str, field: str, first: bool = False) -> str:
    matches = re.findall(pattern, value)
    if not matches or (not first and len(matches) != 1):
        raise AssertionError(f"{field}_count:{len(matches)}")
    result = matches[0]
    if not isinstance(result, str) or not result.strip():
        raise AssertionError(f"{field}_required")
    return result.strip()
def render(entry: dict[str, Any]) -> str:
    title = one(str(entry.get("title") or ""), r"(.+)", "title")
    summary = one(str(entry.get("summary") or ""), r"(.+)", "summary")
    highlights = entry.get("highlights")
    if not isinstance(highlights, list) or not 2 <= len(highlights) <= 6:
        raise AssertionError("highlights_count_invalid")
    lines = [f"# {title}", "", summary, "", "## 主要变化", ""]
    lines.extend(f"- {one(str(item or ''), r'(.+)', 'highlight')}" for item in highlights)
    install = str(entry.get("install") or "").strip()
    if install:
        lines.extend(["", f"安装：\x60{install}\x60"])
    lines.extend(["", one(str(entry.get("asset_note") or ""), r"(.+)", "asset_note")])
    return "\n".join(lines).rstrip() + "\n"
def evaluate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    checks: list[str] = []
    values: dict[str, object] = {}
    def check(name: str, loader: Any, expected: object = TARGET) -> None:
        try:
            value = loader()
            values[name] = value
            if value != expected:
                errors.append(f"active_version:{name}:expected:{expected}:got:{value}")
        except (AssertionError, FileNotFoundError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            errors.append(f"active_version:{name}:{exc}")
    check("VERSION", lambda: read(root, "VERSION").strip())
    check("SKILL.md metadata.version", lambda: one(read(root, "SKILL.md"), r"(?m)^  version:\s*(\S+)\s*$", "skill_version"))
    check("README.md current marker", lambda: one(read(root, "README.md"), r"(?m)^当前源码活动版本为\s+\x60([^\x60]+)\x60", "readme_version"))
    check("CHANGELOG.md latest heading", lambda: one(read(root, "CHANGELOG.md"), r"(?m)^##\s+(beta[^\s]+)", "changelog_latest", True))
    check("RELEASE-LOG.md latest heading", lambda: one(read(root, "RELEASE-LOG.md"), r"(?m)^##\s+(beta[^\s]+)", "release_log_latest", True))
    check(".codex-plugin/plugin.json version", lambda: json.loads(read(root, ".codex-plugin/plugin.json"))["version"])
    sbom = lambda: json.loads(read(root, "SBOM.spdx.json"))
    check("SBOM.spdx.json package.versionInfo", lambda: sbom()["packages"][0]["versionInfo"])
    check("SBOM.spdx.json name", lambda: sbom()["name"], f"decretum-matrix-{TARGET}")
    check("github release metadata latest_tag", lambda: json.loads(read(root, META))["latest_tag"])
    check("github release metadata first release tag", lambda: json.loads(read(root, META))["releases"][0]["tag"])
    check("github release metadata first release title", lambda: json.loads(read(root, META))["releases"][0]["title"], f"Decretum Matrix {TARGET}")
    check("release_payload_manifest.py RELEASE_LABEL", lambda: one(read(root, "scripts/commands/release_payload_manifest.py"), r'(?m)^RELEASE_LABEL\s*=\s*"([^"]+)"', "generator_label"))
    check("check_release_legal.py EXPECTED_RELEASE", lambda: one(read(root, "scripts/checks/check_release_legal.py"), r'(?m)^EXPECTED_RELEASE\s*=\s*"([^"]+)"', "legal_release"))
    try:
        namespace = sbom()["documentNamespace"]
        values["SBOM.spdx.json documentNamespace"] = namespace
        prefix = f"https://spdx.org/spdxdocs/decretum-matrix-{TARGET}-"
        if not isinstance(namespace, str) or not namespace.startswith(prefix):
            errors.append(f"active_version:SBOM.spdx.json documentNamespace:expected_prefix:{prefix}:got:{namespace}")
        core = one(read(root, "scripts/commands/release_payload_manifest.py"), r'(?m)^VERSION_CORE\s*=\s*"([^"]+)"', "generator_core")
        values["release_payload_manifest.py VERSION_CORE"] = core
        if core != TARGET.removeprefix("beta"):
            errors.append(f"active_version:release_payload_manifest.py VERSION_CORE:expected:{TARGET.removeprefix('beta')}:got:{core}")
    except (AssertionError, FileNotFoundError, json.JSONDecodeError, TypeError, ValueError, KeyError, AttributeError) as exc:
        errors.append(f"active_version:derived:{exc}")
    try:
        harness = json.loads(read(root, "package.json"))
        values.update({"package.json version": harness.get("version"), "package.json private": harness.get("private")})
        if harness.get("version") != PRIVATE:
            errors.append(f"harness:version:expected:{PRIVATE}:got:{harness.get('version')}")
        if harness.get("private") is not True:
            errors.append(f"harness:private:expected:true:got:{harness.get('private')}")
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"harness:{exc}")
    for path, stale in (("references/install.md", "First install may install or reuse"), ("docs/wiki/Installation.md", "首次安装会安装或复用")):
        try:
            guidance = read(root, path)
            assert TARGET in guidance and ("unreleased" in guidance.lower() or "未发行" in guidance) and ("external installation transaction" in guidance.lower() or "外置安装事务" in guidance) and stale not in guidance and all(token not in guidance for token in ("sync_active_copies.py", "quick_validate.py", "check_active_copy_hashes.py", "Runtime identity SHA-256 use remains valid", "CLI/projection manifest hashes"))
            checks.append(f"install_guidance:{path}")
        except (AssertionError, FileNotFoundError, TypeError, ValueError) as exc:
            errors.append(f"install_guidance:{path}:{exc}")
    try:
        metadata = json.loads(read(root, META))
        assert metadata.get("schema") == "decretum.github_release_metadata.v1"
        policy = metadata.get("brief_policy")
        assert isinstance(policy, dict) and 300 <= int(policy.get("max_body_chars") or 0) <= 1600
        entries = metadata.get("releases")
        assert isinstance(entries, list) and entries and entries[0].get("tag") == TARGET
        tags: list[str] = []
        for entry in entries:
            assert isinstance(entry, dict)
            tag = one(str(entry.get("tag") or ""), r"(.+)", "tag")
            assert tag not in tags, f"duplicate_tag:{tag}"
            assert len(render(entry)) <= int(policy["max_body_chars"])
            tags.append(tag)
        assert TARGET in tags and entries[0].get("title") == f"Decretum Matrix {TARGET}"
        checks.extend(["github_release_briefs_registered", "github_release_briefs_bounded", "github_latest_policy_registered", "current_release_metadata_is_first"])
    except (AssertionError, FileNotFoundError, json.JSONDecodeError, TypeError, ValueError, KeyError, AttributeError) as exc:
        errors.append(f"release_metadata:{exc}")
    frozen: dict[str, object] | None = None
    try:
        readme = read(root, "README.md")
        assert f'<img src="{ICON}"' in readme and (root / ICON).is_file()
        manifest = json.loads(read(root, "release-manifest.json"))
        assert ICON in {item.get("path") for item in manifest.get("files", []) if isinstance(item, dict)}
        checks.append("readme_brand_icon_rendered")
        frozen = {"path": "release-manifest.json", "status": "FROZEN_BY_SCOPE", "observed_release_label": manifest.get("release_label")}
    except (AssertionError, FileNotFoundError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"readme_brand:{exc}")
    return {"schema": "decretum.release_metadata_gate.v1", "gate": "PASSED" if not errors else "FAILED", "active_version": TARGET, "active_version_map": values, "scope_exceptions": frozen, "checks": checks, "errors": sorted(set(errors))}
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"RELEASE_METADATA_{result['gate']} checks={len(result['checks'])} errors={len(result['errors'])}")
        for error in result["errors"]:
            print(error)
    return 0 if result["gate"] == "PASSED" else 2
if __name__ == "__main__":
    raise SystemExit(main())
