#!/usr/bin/env python3
"""Quick local validator for a portable court skill directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
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
    scripts_dir = skill_path / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from check_response_fewshot_format import evaluate  # type: ignore
        from check_response_draft_fixtures import evaluate as evaluate_drafts  # type: ignore
        from check_context_compression_survival import evaluate as evaluate_compression  # type: ignore
    except Exception as exc:
        return False, f"Court shard validator unavailable: {exc}"

    result = evaluate(skill_path)
    draft_result = evaluate_drafts(skill_path)
    compression_result = evaluate_compression(skill_path)
    errors: list[object] = []
    if result.get("response_fewshot_gate") != "PASSED":
        result_errors = result.get("errors", [])
        if isinstance(result_errors, list):
            errors.extend(result_errors)
        else:
            errors.append(result_errors)
    if draft_result.get("response_draft_fixture_gate") != "PASSED":
        draft_errors = draft_result.get("errors", [])
        if isinstance(draft_errors, list):
            errors.extend(draft_errors)
        else:
            errors.append(draft_errors)
    if compression_result.get("compression_survival_gate") != "PASSED":
        compression_errors = compression_result.get("errors", [])
        if isinstance(compression_errors, list):
            errors.extend(compression_errors)
        else:
            errors.append(compression_errors)
    usage_check = subprocess.run(
        [sys.executable, str(scripts_dir / "check_court_usage_ledger.py")],
        cwd=str(skill_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if usage_check.returncode != 0:
        errors.append(f"usage_ledger:{(usage_check.stderr or usage_check.stdout).strip()}")
    if not errors:
        return True, "Response few-shot format, draft fixtures, context compression survival, and usage ledger are valid!"
    if isinstance(errors, list):
        detail = ", ".join(str(item) for item in errors)
    else:
        detail = str(errors)
    return False, f"Court shard format invalid: {detail}"


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
