"""Verify the ordinary launcher selects only a committed installation binding."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path

_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
from types import ModuleType
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = ROOT / "bin" / "decretum-matrix.py"
BINDING_RELATIVE = Path(
    ".agents/install-receipts/decretum-matrix/installation-binding-v2.json"
)
BINDING_SCHEMA = "court.installation_binding.v2"


def _load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "decretum_matrix_runtime_identity_probe", LAUNCHER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("launcher_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_binding(
    home: Path,
    canonical: Path,
    *,
    completion: str = "COMMITTED",
    source_commit: str = "commit-a",
    artifact_ref: str = "release/decretum-matrix-beta-test.zip@commit-a",
    build_id: str = "beta-test:commit-a:tree-a",
) -> Path:
    path = home / BINDING_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": BINDING_SCHEMA,
                "source_commit": source_commit,
                "release_label": "beta-test",
                "artifact_ref": artifact_ref,
                "build_id": build_id,
                "installation_id": "installation-a",
                "generation": 1,
                "canonical_root": str(canonical.resolve(strict=False)),
                "selected_roots": [str(canonical.resolve(strict=False))],
                "completion": completion,
                "provenance_receipt_ref": "receipt:candidate-a",
                "transaction_id": "transaction-a",
                "rollback_ref": "rollback:none",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_package_metadata(package_root: Path) -> None:
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "package.json").write_text(
        json.dumps(
            {
                "name": "@rowlandl/decretum-matrix",
                "decretumMatrix": {
                    "releaseLabel": "beta-test",
                    "source": {"commit": "commit-a", "tree": "tree-a"},
                    "artifactRef": "release/decretum-matrix-beta-test.zip@commit-a",
                    "buildId": "beta-test:commit-a:tree-a",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def evaluate() -> dict[str, Any]:
    launcher = _load_launcher()
    failures: list[str] = []
    selected_root: str | None = None
    emitted_binding: dict[str, object] | None = None
    with tempfile.TemporaryDirectory(prefix="decretum-runtime-binding-") as temp_dir:
        temp = Path(temp_dir)
        package_root = temp / "package"
        home = temp / "home"
        canonical = home / ".agents" / "skills" / "decretum-matrix"
        (canonical / "scripts").mkdir(parents=True, exist_ok=True)
        # Deliberately omit VERSION and SKILL.md. Ordinary selection must not
        # read or rehash runtime contents.
        (canonical / "scripts" / "court_cli.py").write_text(
            "print('installed')\n", encoding="utf-8"
        )
        _write_package_metadata(package_root)
        _write_binding(home, canonical)

        try:
            selected = launcher._canonical_runtime_root(package_root, home=home)
        except Exception as exc:
            selected = None
            failures.append(f"committed_binding_selection_error:{type(exc).__name__}:{exc}")
        selected_root = str(selected) if selected is not None else None
        if selected is None or not launcher._same_path(selected, canonical):
            failures.append("committed_installation_binding_not_selected")
        binding_value = json.loads(
            (home / BINDING_RELATIVE).read_text(encoding="utf-8")
        )
        cache_key_a = launcher.cache_generation_key(binding_value)
        changed_artifact = dict(binding_value)
        changed_artifact["artifact_ref"] = "release/decretum-matrix-beta-test.zip@commit-b"
        cache_key_b = launcher.cache_generation_key(changed_artifact)
        if not cache_key_a or cache_key_a == cache_key_b:
            failures.append("cache_generation_key_does_not_separate_artifacts")
        if launcher.cache_generation_key({"artifact_ref": "only-artifact"}) is not None:
            failures.append("cache_generation_key_accepted_incomplete_binding")

        cache_base = temp / "cache"
        try:
            probe = launcher.runtime_identity_probe(
                package_root,
                home=home,
                cache_base=cache_base,
            )
        except Exception as exc:
            probe = None
            failures.append(f"runtime_identity_probe_error:{type(exc).__name__}:{exc}")
        emitted_binding = probe if isinstance(probe, dict) else None
        if (
            not isinstance(probe, dict)
            or probe.get("schema") != BINDING_SCHEMA
            or probe.get("completion") != "COMMITTED"
            or "content_digest" in probe
        ):
            failures.append("runtime_identity_probe_not_binding_v2")
        if cache_base.exists():
            failures.append("ordinary_selector_mutated_cache")

        for label, completion in (
            ("missing", None),
            ("pending", "PENDING_VALIDATION"),
            ("failed", "FAILED"),
        ):
            binding_path = home / BINDING_RELATIVE
            if completion is None:
                binding_path.unlink()
            else:
                _write_binding(home, canonical, completion=completion)
            archive_calls: list[str] = []
            original_release_archive = getattr(launcher, "_release_archive", None)
            if callable(original_release_archive):
                launcher._release_archive = lambda _root: archive_calls.append("archive")
            try:
                try:
                    launcher._select_runtime(package_root, home=home)
                except Exception as exc:
                    if type(exc).__name__ != "LauncherError":
                        failures.append(f"{label}_binding_wrong_exception:{type(exc).__name__}")
                else:
                    failures.append(f"{label}_binding_accepted")
            finally:
                if callable(original_release_archive):
                    launcher._release_archive = original_release_archive
            if archive_calls:
                failures.append(f"{label}_binding_triggered_archive_fallback")
            _write_binding(home, canonical)

        wrong_cases = (
            ("source_commit", "commit-b"),
            ("artifact_ref", "release/other.zip@commit-a"),
            ("build_id", "beta-test:commit-b:tree-b"),
        )
        for field, value in wrong_cases:
            _write_binding(home, canonical, **{field: value})
            try:
                launcher._select_runtime(package_root, home=home)
            except Exception:
                pass
            else:
                failures.append(f"{field}_mismatch_accepted")
            _write_binding(home, canonical)

        package_metadata_path = package_root / "package.json"
        original_package_metadata = package_metadata_path.read_text(encoding="utf-8")
        metadata_negative_cases = (
            ("package_metadata_missing", None),
            ("package_metadata_malformed", "{\n"),
            (
                "package_metadata_source_missing",
                json.dumps(
                    {
                        "name": "@rowlandl/decretum-matrix",
                        "decretumMatrix": {
                            "releaseLabel": "beta-test",
                            "artifactRef": "release/decretum-matrix-beta-test.zip@commit-a",
                            "buildId": "beta-test:commit-a:tree-a",
                        },
                    }
                ),
            ),
            (
                "package_metadata_artifact_missing",
                json.dumps(
                    {
                        "name": "@rowlandl/decretum-matrix",
                        "decretumMatrix": {
                            "releaseLabel": "beta-test",
                            "source": {"commit": "commit-a", "tree": "tree-a"},
                            "buildId": "beta-test:commit-a:tree-a",
                        },
                    }
                ),
            ),
            (
                "package_metadata_build_missing",
                json.dumps(
                    {
                        "name": "@rowlandl/decretum-matrix",
                        "decretumMatrix": {
                            "releaseLabel": "beta-test",
                            "source": {"commit": "commit-a", "tree": "tree-a"},
                            "artifactRef": "release/decretum-matrix-beta-test.zip@commit-a",
                        },
                    }
                ),
            ),
            ("package_metadata_oversized", "{" + "x" * (256 * 1024) + "}"),
        )
        for label, payload in metadata_negative_cases:
            if payload is None:
                package_metadata_path.unlink()
            else:
                package_metadata_path.write_text(payload, encoding="utf-8")
            try:
                selected_negative = launcher._canonical_runtime_root(package_root, home=home)
            except Exception:
                selected_negative = None
            if selected_negative is not None:
                failures.append(f"{label}_accepted")
        package_metadata_path.write_text(original_package_metadata, encoding="utf-8")

        _write_binding(home, canonical)
        old_binding = json.loads((home / BINDING_RELATIVE).read_text(encoding="utf-8"))
        old_binding["schema"] = "court.runtime_identity.v1"
        (home / BINDING_RELATIVE).write_text(
            json.dumps(old_binding), encoding="utf-8"
        )
        if launcher._canonical_runtime_root(package_root, home=home) is not None:
            failures.append("v1_runtime_identity_shim_accepted")
        _write_binding(home, canonical)
        for field in ("content_digest", "source_package_sha256", "court_code"):
            polluted = json.loads(
                (home / BINDING_RELATIVE).read_text(encoding="utf-8")
            )
            polluted[field] = "forbidden"
            (home / BINDING_RELATIVE).write_text(
                json.dumps(polluted), encoding="utf-8"
            )
            if launcher._canonical_runtime_root(package_root, home=home) is not None:
                failures.append(f"{field}_binding_field_accepted")
            _write_binding(home, canonical)

        source = LAUNCHER_PATH.read_text(encoding="utf-8")
        for forbidden in ("hashlib", "_runtime_content_digest", "_embedded_runtime_identity"):
            if forbidden in source:
                failures.append(f"ordinary_launcher_retains_{forbidden}")

        original_release_archive = getattr(launcher, "_release_archive", None)
        if callable(original_release_archive):
            launcher._release_archive = lambda _root: (_ for _ in ()).throw(
                AssertionError("archive_called")
            )
        try:
            try:
                launcher.main(["--npm-postinstall"])
            except Exception as exc:
                if type(exc).__name__ != "LauncherError" or str(exc) != "npm_postinstall_disabled":
                    failures.append(f"npm_postinstall_wrong_rejection:{type(exc).__name__}:{exc}")
            else:
                failures.append("npm_postinstall_accepted")
        finally:
            if callable(original_release_archive):
                launcher._release_archive = original_release_archive

    return {
        "schema": "court.runtime_identity_contract_check.v2",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "INSTALLATION_BINDING_SINGLE_AUTHORITY",
        "evidence": {
            "selected_root": selected_root,
            "binding_schema": BINDING_SCHEMA,
            "binding_relative": BINDING_RELATIVE.as_posix(),
            "runtime_identity": emitted_binding,
            "cache_generation_key": cache_key_a,
            "ordinary_content_digest": "FORBIDDEN",
            "postinstall_mode": "EXPLICIT_DISABLED",
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        result = {
            "schema": "court.runtime_identity_contract_check.v2",
            "ok": False,
            "status": "ERROR",
            "contract": "INSTALLATION_BINDING_SINGLE_AUTHORITY",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"INSTALLATION_BINDING_SINGLE_AUTHORITY={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
