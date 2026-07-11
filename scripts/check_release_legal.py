"""Validate release licensing, attribution, policy documents, and SPDX metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile


sys.dont_write_bytecode = True


REQUIRED_FILES = (
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "SECURITY.md",
    "PRIVACY.md",
    "CONTRIBUTING.md",
    "SBOM.spdx.json",
)
EXPECTED_UPSTREAM_COMMIT = "14a207557719c046af0f993a7bff1cc5a5015b33"
EXPECTED_UPSTREAM_LICENSE_BLOB_SHA1 = "69499c3250cbecc6079c69dc0e5a0f7a4be716da"
EXPECTED_UPSTREAM_LICENSE_SHA256 = "5f67c084a1b5bd87409f05221d5985cde0b99472aa34670613761e614330d93c"
EXPECTED_UPSTREAM_COPYRIGHT = "Copyright (c) 2026 openclaw-sansheng-liubu contributors"
EXPECTED_UPSTREAM_REPOSITORY = "https://github.com/cft0808/edict"
EXPECTED_RELEASE = "beta0.5.9"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def evaluate(root: Path) -> dict[str, object]:
    root = root.resolve()
    problems: list[str] = []
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    problems.extend(f"missing:{name}" for name in missing)

    license_text = read_text(root / "LICENSE") if not missing or (root / "LICENSE").is_file() else ""
    for marker in (
        "Apache License",
        "Version 2.0, January 2004",
        "http://www.apache.org/licenses/",
        "3. Grant of Patent License.",
        "END OF TERMS AND CONDITIONS",
    ):
        if marker not in license_text:
            problems.append(f"license:missing:{marker}")

    notice_text = read_text(root / "NOTICE") if (root / "NOTICE").is_file() else ""
    for marker in (
        "court-capability-router",
        "Copyright 2026 court-capability-router contributors",
        "Apache License 2.0",
        "not affiliated with cft0808/edict or OpenClaw",
    ):
        if marker not in notice_text:
            problems.append(f"notice:missing:{marker}")

    third_party = read_text(root / "THIRD_PARTY_NOTICES.md") if (root / "THIRD_PARTY_NOTICES.md").is_file() else ""
    for marker in (
        EXPECTED_UPSTREAM_REPOSITORY,
        EXPECTED_UPSTREAM_COMMIT,
        EXPECTED_UPSTREAM_LICENSE_BLOB_SHA1,
        EXPECTED_UPSTREAM_LICENSE_SHA256,
        EXPECTED_UPSTREAM_COPYRIGHT,
        "Permission is hereby granted, free of charge",
        "The above copyright notice and this permission notice shall be included",
        "THE SOFTWARE IS PROVIDED \"AS IS\"",
        "no upstream runtime dependency",
        "no governing authority",
    ):
        if marker not in third_party:
            problems.append(f"third_party:missing:{marker}")

    benchmark_path = root / "references" / "benchmarks" / "cft0808-edict.yaml"
    benchmark = read_text(benchmark_path) if benchmark_path.is_file() else ""
    if not benchmark:
        problems.append("benchmark:missing")
    for marker in (
        'checked_at: "2026-07-12"',
        f'commit: "{EXPECTED_UPSTREAM_COMMIT}"',
        "spdx: MIT",
        f'git_blob_sha1: "{EXPECTED_UPSTREAM_LICENSE_BLOB_SHA1}"',
        f'sha256: "{EXPECTED_UPSTREAM_LICENSE_SHA256}"',
        f'copyright: "{EXPECTED_UPSTREAM_COPYRIGHT}"',
    ):
        if marker not in benchmark:
            problems.append(f"benchmark:missing:{marker}")

    sbom_path = root / "SBOM.spdx.json"
    try:
        sbom = json.loads(sbom_path.read_text(encoding="utf-8")) if sbom_path.is_file() else {}
    except json.JSONDecodeError:
        sbom = {}
        problems.append("sbom:invalid-json")
    packages = sbom.get("packages") if isinstance(sbom, dict) else None
    package = packages[0] if isinstance(packages, list) and packages and isinstance(packages[0], dict) else {}
    relationships = sbom.get("relationships") if isinstance(sbom, dict) else None
    describes = any(
        isinstance(item, dict)
        and item.get("spdxElementId") == "SPDXRef-DOCUMENT"
        and item.get("relationshipType") == "DESCRIBES"
        and item.get("relatedSpdxElement") == "SPDXRef-Package"
        for item in relationships or []
    )
    expected_sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
    }
    for key, expected in expected_sbom.items():
        if sbom.get(key) != expected:
            problems.append(f"sbom:{key}:expected:{expected}")
    if package.get("name") != "court-capability-router":
        problems.append("sbom:package-name")
    if package.get("versionInfo") != EXPECTED_RELEASE:
        problems.append("sbom:version")
    if package.get("licenseDeclared") != "Apache-2.0":
        problems.append("sbom:license")
    if package.get("filesAnalyzed") is not False:
        problems.append("sbom:files-analyzed")
    if not describes:
        problems.append("sbom:describes")

    security = read_text(root / "SECURITY.md") if (root / "SECURITY.md").is_file() else ""
    security_normalized = " ".join(security.lower().split())
    if "private vulnerability reporting" not in security_normalized:
        problems.append("security:private-reporting")
    if "credentials" not in security_normalized or "public issue" not in security_normalized:
        problems.append("security:no-public-credentials")

    privacy = read_text(root / "PRIVACY.md") if (root / "PRIVACY.md").is_file() else ""
    for marker in ("127.0.0.1", "explicit LAN opt-in", "obfuscation, not encryption", "bearer secret"):
        if marker not in privacy:
            problems.append(f"privacy:missing:{marker}")

    contributing = read_text(root / "CONTRIBUTING.md") if (root / "CONTRIBUTING.md").is_file() else ""
    for marker in ("provenance", "Apache-2.0", "Signed-off-by", "private Shiguan"):
        if marker not in contributing:
            problems.append(f"contributing:missing:{marker}")

    return {
        "schema": "court.release_legal.result.v1",
        "ok": not problems,
        "root": str(root),
        "license_declared": "Apache-2.0" if "Apache License" in license_text else None,
        "upstream": {
            "repository": EXPECTED_UPSTREAM_REPOSITORY,
            "commit": EXPECTED_UPSTREAM_COMMIT,
            "license": "MIT",
            "license_sha256": EXPECTED_UPSTREAM_LICENSE_SHA256,
        },
        "required_files": list(REQUIRED_FILES),
        "problems": sorted(set(problems)),
    }


def run_self_test(root: Path) -> dict[str, object]:
    current = evaluate(root)
    assertions: dict[str, bool] = {"current_tree_passes": current["ok"] is True}
    with tempfile.TemporaryDirectory(prefix="court-release-legal-") as tmp_text:
        fixture = Path(tmp_text) / "fixture"
        (fixture / "references" / "benchmarks").mkdir(parents=True)
        for name in REQUIRED_FILES:
            shutil.copy2(root / name, fixture / name)
        shutil.copy2(
            root / "references" / "benchmarks" / "cft0808-edict.yaml",
            fixture / "references" / "benchmarks" / "cft0808-edict.yaml",
        )

        (fixture / "NOTICE").unlink()
        assertions["missing_notice_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "NOTICE", fixture / "NOTICE")

        (fixture / "THIRD_PARTY_NOTICES.md").write_text("missing attribution\n", encoding="utf-8")
        assertions["missing_mit_notice_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "THIRD_PARTY_NOTICES.md", fixture / "THIRD_PARTY_NOTICES.md")

        sbom = json.loads((fixture / "SBOM.spdx.json").read_text(encoding="utf-8"))
        sbom["spdxVersion"] = "SPDX-2.2"
        (fixture / "SBOM.spdx.json").write_text(json.dumps(sbom), encoding="utf-8")
        assertions["wrong_sbom_version_fails"] = evaluate(fixture)["ok"] is False

    ok = all(assertions.values())
    return {"ok": ok, "assertions": assertions, "current": current}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.root) if args.self_test else evaluate(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"RELEASE_LEGAL {'PASSED' if result['ok'] else 'FAILED'}")
        for problem in result.get("problems", result.get("current", {}).get("problems", [])):
            print(problem)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
