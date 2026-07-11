"""Metadata-only source-state and complexity budget gate.

The tree walk uses paths and stat metadata only. File bodies are never opened
except for this manifest and the explicitly configured Python source files whose
line counts are budgeted. In particular, pending import bodies are never read.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "references" / "manifests" / "source-state-budget.v1.json"
MANIFEST_SCHEMA = "court.source_state_budget.v1"
RESULT_SCHEMA = "court.source_state_budget.result.v1"
CATEGORIES = ("portable_source", "generated_runtime", "historical")


class SourceStateBudgetError(ValueError):
    """Raised when the budget manifest itself is invalid."""


def fail(message: str) -> None:
    raise SourceStateBudgetError(message)


def relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        fail(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    if (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or ".." in normalized.split("/")
    ):
        fail(f"{label} must stay inside the skill root")
    return normalized


def string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        fail(f"{label} must be a list of non-empty strings")
    return list(value)


def nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        fail(f"{label} must be a non-negative integer")
    return value


def positive_int(value: object, label: str) -> int:
    result = nonnegative_int(value, label)
    if result < 1:
        fail(f"{label} must be greater than zero")
    return result


def validate_manifest(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        fail(f"manifest schema must be {MANIFEST_SCHEMA}")
    classification = value.get("classification")
    hard_limits = value.get("hard_limits")
    warning_targets = value.get("warning_targets")
    if not isinstance(classification, dict) or not isinstance(hard_limits, dict) or not isinstance(warning_targets, dict):
        fail("classification, hard_limits, and warning_targets must be objects")

    normalized_classification: dict[str, object] = {}
    for key in (
        "historical_top_level_prefixes",
        "historical_path_prefixes",
        "generated_dir_names",
        "generated_exact_files",
        "generated_path_components",
        "generated_filename_prefixes",
        "generated_filename_contains",
        "generated_suffixes",
        "runtime_candidate_directory_fragments",
        "runtime_candidate_suffixes",
    ):
        normalized_classification[key] = string_list(classification.get(key), f"classification.{key}")
    rules = classification.get("generated_path_rules")
    if not isinstance(rules, list):
        fail("classification.generated_path_rules must be a list")
    normalized_rules: list[dict[str, object]] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            fail(f"generated_path_rules[{index}] must be an object")
        normalized_rules.append(
            {
                "prefix": relative_path(rule.get("prefix"), f"generated_path_rules[{index}].prefix"),
                "portable_basenames": string_list(
                    rule.get("portable_basenames"),
                    f"generated_path_rules[{index}].portable_basenames",
                ),
            }
        )
    normalized_classification["generated_path_rules"] = normalized_rules

    portable = hard_limits.get("portable_source")
    source_lines = hard_limits.get("source_lines")
    if not isinstance(portable, dict) or not isinstance(source_lines, dict) or not source_lines:
        fail("hard_limits.portable_source and hard_limits.source_lines must be non-empty objects")
    normalized_lines: dict[str, int] = {}
    for raw_path, raw_limit in source_lines.items():
        path = relative_path(raw_path, "source line budget path")
        if not path.startswith("scripts/") or not path.endswith(".py"):
            fail(f"source line budget must target scripts/*.py: {path}")
        normalized_lines[path] = positive_int(raw_limit, f"source line budget {path}")

    normalized_warnings: dict[str, dict[str, object]] = {}
    for category in ("historical", "generated_runtime"):
        target = warning_targets.get(category)
        if not isinstance(target, dict) or not isinstance(target.get("code"), str):
            fail(f"warning_targets.{category} must contain max_files, max_bytes, and code")
        normalized_warnings[category] = {
            "max_files": nonnegative_int(target.get("max_files"), f"warning_targets.{category}.max_files"),
            "max_bytes": nonnegative_int(target.get("max_bytes"), f"warning_targets.{category}.max_bytes"),
            "code": target["code"],
        }
    return {
        "schema": MANIFEST_SCHEMA,
        "classification": normalized_classification,
        "hard_limits": {
            "portable_source": {
                "max_files": positive_int(portable.get("max_files"), "portable max_files"),
                "max_bytes": positive_int(portable.get("max_bytes"), "portable max_bytes"),
            },
            "source_lines": normalized_lines,
        },
        "warning_targets": normalized_warnings,
    }


def load_manifest(path: Path) -> dict[str, object]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SourceStateBudgetError(f"cannot read budget manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SourceStateBudgetError(f"invalid budget manifest JSON {path}: {exc}") from exc
    return validate_manifest(raw)


def path_starts(relative: str, prefix: str) -> bool:
    clean = prefix.rstrip("/")
    return relative == clean or relative.startswith(clean + "/")


def classify(relative: Path, config: dict[str, object]) -> str:
    text = relative.as_posix()
    parts = relative.parts
    first = parts[0] if parts else ""
    if any(first.startswith(prefix) for prefix in config["historical_top_level_prefixes"]):  # type: ignore[union-attr]
        return "historical"
    if any(path_starts(text, prefix) for prefix in config["historical_path_prefixes"]):  # type: ignore[union-attr]
        return "historical"

    directory_parts = set(parts[:-1])
    if directory_parts & set(config["generated_dir_names"]):  # type: ignore[arg-type]
        return "generated_runtime"
    if text in set(config["generated_exact_files"]):  # type: ignore[arg-type]
        return "generated_runtime"
    if directory_parts & set(config["generated_path_components"]):  # type: ignore[arg-type]
        return "generated_runtime"
    for rule in config["generated_path_rules"]:  # type: ignore[union-attr]
        if path_starts(text, str(rule["prefix"])) and relative.name not in rule["portable_basenames"]:
            return "generated_runtime"
    lower_name = relative.name.lower()
    if any(lower_name.startswith(item.lower()) for item in config["generated_filename_prefixes"]):  # type: ignore[union-attr]
        return "generated_runtime"
    if any(item.lower() in lower_name for item in config["generated_filename_contains"]):  # type: ignore[union-attr]
        return "generated_runtime"
    if any(lower_name.endswith(item.lower()) for item in config["generated_suffixes"]):  # type: ignore[union-attr]
        return "generated_runtime"
    return "portable_source"


def runtime_candidate_reason(relative: Path, config: dict[str, object]) -> str:
    directory_parts = [part.lower() for part in relative.parts[:-1]]
    for fragment in config["runtime_candidate_directory_fragments"]:  # type: ignore[union-attr]
        lowered = fragment.lower()
        if any(lowered in part for part in directory_parts):
            return f"directory_fragment:{fragment}"
    lower_name = relative.name.lower()
    for suffix in config["runtime_candidate_suffixes"]:  # type: ignore[union-attr]
        if lower_name.endswith(suffix.lower()):
            return f"runtime_suffix:{suffix}"
    return ""


def count_source_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _line in handle)


def evaluate(root: Path, manifest: dict[str, object]) -> dict[str, object]:
    root = root.resolve()
    config = manifest["classification"]  # type: ignore[assignment]
    categories = {name: {"files": 0, "bytes": 0} for name in CATEGORIES}
    hard_fail: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    unclassified: list[dict[str, object]] = []
    bytecode_artifacts: list[str] = []

    if not root.is_dir():
        return {
            "schema": RESULT_SCHEMA,
            "ok": False,
            "hard_fail": [{"code": "skill_root_missing", "path": str(root)}],
            "warnings": [],
            "categories": categories,
            "complexity": {},
            "unclassified_runtime_candidates": [],
        }

    for path in root.rglob("*"):
        if path.is_symlink():
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, ValueError):
                hard_fail.append({"code": "external_or_broken_symlink", "path": path.relative_to(root).as_posix()})
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or relative.suffix.lower() == ".pyc":
            bytecode_artifacts.append(relative.as_posix())
        try:
            size = path.stat().st_size
        except OSError as exc:
            hard_fail.append({"code": "stat_failed", "path": relative.as_posix(), "error": str(exc)})
            continue
        category = classify(relative, config)
        categories[category]["files"] += 1
        categories[category]["bytes"] += size
        if category == "portable_source":
            reason = runtime_candidate_reason(relative, config)
            if reason:
                unclassified.append({"path": relative.as_posix(), "reason": reason, "bytes": size})

    if unclassified:
        hard_fail.append(
            {
                "code": "unclassified_runtime_detected",
                "count": len(unclassified),
                "samples": unclassified[:20],
            }
        )

    if bytecode_artifacts:
        hard_fail.append(
            {
                "code": "bytecode_artifacts_present",
                "count": len(bytecode_artifacts),
                "samples": bytecode_artifacts[:20],
            }
        )

    portable_limits = manifest["hard_limits"]["portable_source"]  # type: ignore[index]
    portable = categories["portable_source"]
    if portable["files"] > portable_limits["max_files"]:
        hard_fail.append(
            {
                "code": "portable_file_budget_exceeded",
                "actual": portable["files"],
                "limit": portable_limits["max_files"],
            }
        )
    if portable["bytes"] > portable_limits["max_bytes"]:
        hard_fail.append(
            {
                "code": "portable_byte_budget_exceeded",
                "actual": portable["bytes"],
                "limit": portable_limits["max_bytes"],
            }
        )

    complexity: dict[str, dict[str, object]] = {}
    for relative_text, limit in manifest["hard_limits"]["source_lines"].items():  # type: ignore[index,union-attr]
        path = root / Path(relative_text)
        if not path.is_file():
            hard_fail.append({"code": "budgeted_source_missing", "path": relative_text})
            complexity[relative_text] = {"lines": None, "limit": limit, "status": "missing"}
            continue
        try:
            lines = count_source_lines(path)
        except (OSError, UnicodeError) as exc:
            hard_fail.append({"code": "source_line_count_failed", "path": relative_text, "error": str(exc)})
            complexity[relative_text] = {"lines": None, "limit": limit, "status": "error"}
            continue
        status = "PASSED" if lines <= limit else "FAILED"
        complexity[relative_text] = {"lines": lines, "limit": limit, "status": status}
        if status == "FAILED":
            hard_fail.append(
                {
                    "code": "source_line_budget_exceeded",
                    "path": relative_text,
                    "actual": lines,
                    "limit": limit,
                }
            )

    for category, target in manifest["warning_targets"].items():  # type: ignore[union-attr]
        actual = categories[category]
        if actual["files"] > target["max_files"] or actual["bytes"] > target["max_bytes"]:
            diagnostic = {
                "code": target["code"],
                "category": category,
                "actual": dict(actual),
                "target": {"max_files": target["max_files"], "max_bytes": target["max_bytes"]},
            }
            warnings.append(diagnostic)
            hard_fail.append({**diagnostic, "release_gate": "hard_fail"})
    return {
        "schema": RESULT_SCHEMA,
        "ok": not hard_fail,
        "hard_fail": hard_fail,
        "warnings": warnings,
        "categories": categories,
        "complexity": complexity,
        "unclassified_runtime_candidates": unclassified,
        "inspection_contract": {
            "tree_scan": "path_and_stat_only",
            "body_reads": ["budget_manifest", *manifest["hard_limits"]["source_lines"].keys()],  # type: ignore[index,union-attr]
            "pending_body_reads": 0,
        },
    }


def has_failure(result: dict[str, object], code: str) -> bool:
    return any(item.get("code") == code for item in result.get("hard_fail", []))  # type: ignore[union-attr]


def run_fixture_tests(manifest: dict[str, object]) -> dict[str, bool]:
    root = Path(tempfile.mkdtemp(prefix="court-source-budget-preserved-"))
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "ensure_supercc_court.py").write_text("print('fixture')\n", encoding="utf-8")
    (root / "scripts" / "serve_shiguan_tree.py").write_text("print('fixture')\n", encoding="utf-8")
    (root / "SKILL.md").write_text("# fixture\n", encoding="utf-8")

    fixture_manifest = deepcopy(manifest)
    fixture_manifest["hard_limits"]["portable_source"] = {"max_files": 10, "max_bytes": 100000}  # type: ignore[index]
    fixture_manifest["hard_limits"]["source_lines"] = {  # type: ignore[index]
        "scripts/ensure_supercc_court.py": 10,
        "scripts/serve_shiguan_tree.py": 10,
    }
    baseline = evaluate(root, fixture_manifest)

    pending = root / "references" / "shiguan-imports" / "pending"
    pending.mkdir(parents=True)
    pending_body = pending / "opaque-body.json"
    pending_body.write_bytes(b"not-json-and-never-opened")
    generated_runtime = evaluate(root, fixture_manifest)
    pending_body.unlink()

    historical_root = root / "references.imported-fixture"
    historical_root.mkdir(parents=True)
    historical_body = historical_root / "legacy.md"
    historical_body.write_text("legacy fixture\n", encoding="utf-8")
    historical = evaluate(root, fixture_manifest)
    historical_body.unlink()

    over_budget_manifest = deepcopy(fixture_manifest)
    over_budget_manifest["hard_limits"]["portable_source"]["max_files"] = 1  # type: ignore[index]
    over_budget = evaluate(root, over_budget_manifest)

    unexpected = root / "references" / "unclassified-runtime"
    unexpected.mkdir(parents=True)
    (unexpected / "state.json").write_text("{}\n", encoding="utf-8")
    unclassified = evaluate(root, fixture_manifest)

    bytecode = root / "scripts" / "__pycache__"
    bytecode.mkdir(parents=True)
    (bytecode / "fixture.pyc").write_bytes(b"preserved-bytecode-fixture")
    bytecode_result = evaluate(root, fixture_manifest)
    return {
        "baseline_passes": bool(baseline["ok"]),
        "pending_body_is_stat_only": generated_runtime["inspection_contract"]["pending_body_reads"] == 0,  # type: ignore[index]
        "generated_runtime_zero_budget_is_hard_fail": has_failure(
            generated_runtime,
            "generated_runtime_present",
        ),
        "historical_zero_budget_is_hard_fail": has_failure(historical, "legacy_over_target"),
        "unclassified_runtime_fails": has_failure(unclassified, "unclassified_runtime_detected"),
        "portable_budget_fails": has_failure(over_budget, "portable_file_budget_exceeded"),
        "bytecode_artifacts_fail": has_failure(bytecode_result, "bytecode_artifacts_present"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        result = evaluate(args.root, manifest)
        if args.self_test:
            fixture_tests = run_fixture_tests(manifest)
            result["fixture_tests"] = fixture_tests
            if not all(fixture_tests.values()):
                result["hard_fail"].append(  # type: ignore[union-attr]
                    {"code": "fixture_contract_failed", "fixture_tests": fixture_tests}
                )
                result["ok"] = False
    except SourceStateBudgetError as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "ok": False,
            "hard_fail": [{"code": "manifest_invalid", "error": str(exc)}],
            "warnings": [],
        }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "SOURCE_STATE_BUDGET_{} hard_fail={} warnings={} portable_files={} portable_bytes={}".format(
                "PASSED" if result["ok"] else "FAILED",
                len(result.get("hard_fail", [])),
                len(result.get("warnings", [])),
                result.get("categories", {}).get("portable_source", {}).get("files", "unknown"),
                result.get("categories", {}).get("portable_source", {}).get("bytes", "unknown"),
            )
        )
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
