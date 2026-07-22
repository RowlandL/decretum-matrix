#!/usr/bin/env python3
"""Quick local validator for a portable court skill directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on minimal hosts.
    yaml = None


MAX_SKILL_NAME_LENGTH = 64
ALLOWED_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
}


def parse_frontmatter(text: str) -> tuple[dict[str, object] | None, str | None]:
    if not text.startswith("---"):
        return None, "No YAML frontmatter found"

    match = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    if not match:
        return None, "Invalid frontmatter format"

    frontmatter_text = match.group(1)
    if yaml is not None:
        try:
            frontmatter = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError as exc:
            return None, f"Invalid YAML in frontmatter: {exc}"
        if not isinstance(frontmatter, dict):
            return None, "Frontmatter must be a YAML dictionary"
        return frontmatter, None

    frontmatter: dict[str, object] = {}
    for line in frontmatter_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            return None, "Invalid frontmatter line without ':'"
        frontmatter[key.strip()] = value.strip().strip("'\"")
    return frontmatter, None


def validate_skill(skill_path: Path) -> tuple[bool, str]:
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    frontmatter, error = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    if error:
        return False, error
    assert frontmatter is not None

    unexpected_keys = set(frontmatter) - ALLOWED_FRONTMATTER_KEYS
    if unexpected_keys:
        allowed = ", ".join(sorted(ALLOWED_FRONTMATTER_KEYS))
        unexpected = ", ".join(sorted(unexpected_keys))
        return (
            False,
            f"Unexpected key(s) in SKILL.md frontmatter: {unexpected}. "
            f"Allowed properties are: {allowed}",
        )

    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if not re.match(r"^[a-z0-9-]+$", name):
        return (
            False,
            f"Name '{name}' should be hyphen-case "
            "(lowercase letters, digits, and hyphens only)",
        )
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
    if len(name) > MAX_SKILL_NAME_LENGTH:
        return (
            False,
            f"Name is too long ({len(name)} characters). "
            f"Maximum is {MAX_SKILL_NAME_LENGTH} characters.",
        )

    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if "<" in description or ">" in description:
        return False, "Description cannot contain angle brackets (< or >)"
    if len(description) > 1024:
        return (
            False,
            f"Description is too long ({len(description)} characters). Maximum is 1024 characters.",
        )

    return True, "Skill is valid!"


def validate_court_shards(skill_path: Path) -> tuple[bool, str]:
    required = [
        "SKILL.md",
        "references/court-core-contract.md",
        "references/court-startup-authority.md",
        "references/court-offices-dispatch.md",
        "references/court-state-runtime-agents.md",
        "references/benchmarks/cft0808-edict.yaml",
        "references/sections/court-office-name-profile-skill-binding.md",
        "references/manifests/install-projection.v1.json",
        "scripts/sync_active_copies.py",
    ]
    missing = [item for item in required if not (skill_path / item).exists()]
    if missing:
        return False, "Missing required installed file(s): " + ", ".join(missing)

    forbidden = [
        "office_ok" + "_probe",
        "check_active_copy_" + ("ha" + "sh") + "es",
        "ha" + "sh",
        "s" + "ha" + "256",
        "SHA" + "256",
        "SHA" + "-256",
        "哈" + "希",
    ]
    manifest_path = skill_path / "references/manifests/install-projection.v1.json"
    projected = list(required)
    frozen_references: set[str] = set()
    violations: list[str] = []
    try:
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        projected = list(manifest.get("projections", {}).get("shared_agents", projected))
        declared_frozen = manifest.get("frozen_install_references", [])
        if not isinstance(declared_frozen, list) or not all(isinstance(item, str) for item in declared_frozen):
            violations.append("install projection has invalid frozen_install_references")
        for item in declared_frozen if isinstance(declared_frozen, list) else []:
            relative = Path(item)
            normalized = relative.as_posix()
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not normalized.startswith("references/benchmarks/")
                or normalized not in projected
            ):
                violations.append(f"invalid frozen reference: {item}")
                continue
            reference_path = skill_path / relative
            if not reference_path.is_file():
                violations.append(f"missing frozen reference: {normalized}")
                continue
            reference_text = reference_path.read_text(encoding="utf-8", errors="replace")
            for marker in ("state: frozen_reference", "runtime_loading: false"):
                if marker not in reference_text:
                    violations.append(f"frozen reference missing {marker}: {normalized}")
            frozen_references.add(normalized)
    except (OSError, ValueError, TypeError):
        pass

    for relative in projected:
        path = skill_path / str(relative)
        if path.is_dir():
            files = [item for item in path.rglob("*") if item.is_file()]
        elif path.is_file():
            files = [path]
        else:
            continue
        for file_path in files:
            relative_path = file_path.relative_to(skill_path).as_posix()
            if relative_path in frozen_references:
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            except OSError as exc:
                violations.append(f"{file_path}: unreadable:{exc}")
                continue
            for term in forbidden:
                if term in text:
                    violations.append(f"{relative_path}: forbidden runtime term")
                    break
    if violations:
        return False, "Forbidden runtime term(s): " + ", ".join(violations[:20])
    return True, "Court installed projection is lightweight and runtime-clean!"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "skill_directory",
        nargs="?",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Skill directory to validate. Defaults to this script's parent skill.",
    )
    args = parser.parse_args(argv)

    skill_path = args.skill_directory.resolve()
    valid, message = validate_skill(skill_path)
    if valid:
        valid, shard_message = validate_court_shards(skill_path)
        if valid:
            message = f"{message} {shard_message}"
        else:
            message = shard_message
    print(message)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
