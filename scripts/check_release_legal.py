"""Validate release licensing, attribution, policy documents, and SPDX metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile


sys.dont_write_bytecode = True


REQUIRED_FILES = (
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "PROVENANCE.md",
    "COMMERCIAL-LICENSE.md",
    "CLA.md",
    "TRADEMARKS.md",
    "AUTHORS.md",
    "SECURITY.md",
    "PRIVACY.md",
    "CONTRIBUTING.md",
    "README.md",
    "SBOM.spdx.json",
)
EXPECTED_UPSTREAM_COMMIT = "14a207557719c046af0f993a7bff1cc5a5015b33"
EXPECTED_UPSTREAM_LICENSE_BLOB_SHA1 = "69499c3250cbecc6079c69dc0e5a0f7a4be716da"
EXPECTED_UPSTREAM_LICENSE_SHA256 = "5f67c084a1b5bd87409f05221d5985cde0b99472aa34670613761e614330d93c"
EXPECTED_UPSTREAM_COPYRIGHT = "Copyright (c) 2026 openclaw-sansheng-liubu contributors"
EXPECTED_UPSTREAM_REPOSITORY = "https://github.com/cft0808/edict"
EXPECTED_RELEASE = "beta1.0.3"
EXPECTED_PACKAGE_NAME = "decretum-matrix"
EXPECTED_LICENSE = "AGPL-3.0-only"
EXPECTED_AGPL_SHA256 = "0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0"
EXPECTED_SBOM_NAME = "decretum-matrix-beta1.0.3"
EXPECTED_SBOM_CREATED = "2026-07-21T00:00:00Z"
EXPECTED_SBOM_NAMESPACE = "https://spdx.org/spdxdocs/decretum-matrix-beta1.0.3-20260721"
EXPECTED_COPYRIGHT = "Copyright 2026 孙华清"
EXPECTED_OWNER = "孙华清"
EXPECTED_MAINTAINER = "@RowlandL"
EXPECTED_GITHUB_ID = "42199880"
EXPECTED_TRADEMARK_POLICY_OWNER = f"Trademark policy owner: {EXPECTED_OWNER}"
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MIT_FENCE_PATTERN = re.compile(r"```text\n(?P<body>MIT License\n.*?\n)```", re.DOTALL)
COMMERCIAL_GRANT_PATTERN = re.compile(
    r"\bthis\s+(?:document|notice|file)\s+(?:hereby\s+)?grants?\b.*?\bcommercial\s+(?:license|rights?)\b",
    re.IGNORECASE | re.DOTALL,
)
PINYIN_PATTERN = re.compile(r"\bSun\s+Hua[ -]?qing\b", re.IGNORECASE)
COMPANY_PATTERN = re.compile(
    r"\b(?:company|corporation|corp\.?|inc\.?|llc|ltd\.?)\b|公司|有限公司",
    re.IGNORECASE,
)
ADDRESS_FIELD_PATTERN = re.compile(r"(?im)^\s*(?:postal\s+)?address\s*[:：]|^\s*地址\s*[:：]")
OWNER_AS_MAINTAINER_PATTERN = re.compile(
    rf"(?im)^\s*(?:[-*]\s*)?maintainer(?:[^:\n]*)\s*:[^\n]*{re.escape(EXPECTED_OWNER)}"
)
TRADEMARK_OWNER_DISCLAIMER_PATTERN = re.compile(
    r"does not claim that any mark is owned|does not establish ownership of any trademark",
    re.IGNORECASE,
)
UNSUPPORTED_BETA058_APACHE_PATTERNS = (
    re.compile(
        r"(?i)(?:`?beta0\.5\.8`?.{0,80}`?beta0\.5\.9`?|"
        r"`?beta0\.5\.9`?.{0,80}`?beta0\.5\.8`?).{0,80}"
        r"`?Apache-2\.0`?.{0,40}(?:授权|licenses?|releases?|版本)"
    ),
    re.compile(
        r"(?i)`?beta0\.5\.8`?\s*(?:=|is|was|为|是)\s*"
        r"`?Apache-2\.0`?\s*(?:授权|licenses?|releases?|版本)"
    ),
)


def has_beta058_apache_claim_without_evidence(text: str) -> bool:
    for line in text.splitlines():
        normalized = line.casefold()
        if "beta0.5.8" not in normalized or "apache-2.0" not in normalized:
            continue
        if (
            "license_not_established_from_tag" not in normalized
            or "artifact-specific evidence" not in normalized
        ):
            return True
    return False


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def evaluate(root: Path) -> dict[str, object]:
    root = root.resolve()
    problems: list[str] = []
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    problems.extend(f"missing:{name}" for name in missing)

    license_path = root / "LICENSE"
    license_bytes = license_path.read_bytes() if license_path.is_file() else b""
    license_sha256 = hashlib.sha256(license_bytes).hexdigest() if license_bytes else None
    license_text = license_bytes.decode("utf-8") if license_bytes else ""
    for marker in (
        "GNU AFFERO GENERAL PUBLIC LICENSE",
        "Version 3, 19 November 2007",
        "13. Remote Network Interaction; Use with the GNU General Public License.",
        "END OF TERMS AND CONDITIONS",
    ):
        if marker not in license_text:
            problems.append(f"license:missing:{marker}")
    if license_sha256 != EXPECTED_AGPL_SHA256:
        problems.append(f"license:sha256:expected:{EXPECTED_AGPL_SHA256}")

    notice_text = read_text(root / "NOTICE") if (root / "NOTICE").is_file() else ""
    for marker in (
        "Decretum Matrix（诏令矩阵）",
        f"Copyright 2026 {EXPECTED_OWNER}",
        f"Community edition: {EXPECTED_LICENSE}",
        f"GitHub: {EXPECTED_MAINTAINER}",
        f"GitHub ID {EXPECTED_GITHUB_ID}",
        "not affiliated with",
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
        "upstream-inspired",
    ):
        if marker not in third_party:
            problems.append(f"third_party:missing:{marker}")
    mit_match = MIT_FENCE_PATTERN.search(third_party)
    mit_sha256 = (
        hashlib.sha256(mit_match.group("body").encode("utf-8")).hexdigest()
        if mit_match is not None
        else None
    )
    if mit_sha256 != EXPECTED_UPSTREAM_LICENSE_SHA256:
        problems.append(f"third_party:mit-sha256:expected:{EXPECTED_UPSTREAM_LICENSE_SHA256}")

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
        "runtime_dependency: false",
        "governing_source: false",
    ):
        if marker not in benchmark:
            problems.append(f"benchmark:missing:{marker}")

    sbom_path = root / "SBOM.spdx.json"
    try:
        sbom = json.loads(sbom_path.read_text(encoding="utf-8")) if sbom_path.is_file() else {}
    except json.JSONDecodeError:
        sbom = {}
        problems.append("sbom:invalid-json")
    if not isinstance(sbom, dict):
        problems.append("sbom:not-object")
        sbom = {}
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
        "name": EXPECTED_SBOM_NAME,
        "documentNamespace": EXPECTED_SBOM_NAMESPACE,
    }
    for key, expected in expected_sbom.items():
        if sbom.get(key) != expected:
            problems.append(f"sbom:{key}:expected:{expected}")
    creation_info = sbom.get("creationInfo") if isinstance(sbom, dict) else None
    if not isinstance(creation_info, dict) or creation_info.get("created") != EXPECTED_SBOM_CREATED:
        problems.append(f"sbom:creationInfo.created:expected:{EXPECTED_SBOM_CREATED}")
    if package.get("name") != EXPECTED_PACKAGE_NAME:
        problems.append("sbom:package-name")
    if package.get("versionInfo") != EXPECTED_RELEASE:
        problems.append("sbom:version")
    if package.get("licenseDeclared") != EXPECTED_LICENSE:
        problems.append("sbom:license")
    if package.get("copyrightText") != EXPECTED_COPYRIGHT:
        problems.append("sbom:copyright")
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
    for marker in ("provenance", EXPECTED_LICENSE, "Signed-off-by", "CLA", "private Shiguan"):
        if marker not in contributing:
            problems.append(f"contributing:missing:{marker}")

    provenance = read_text(root / "PROVENANCE.md") if (root / "PROVENANCE.md").is_file() else ""
    for marker in (
        EXPECTED_UPSTREAM_REPOSITORY,
        EXPECTED_UPSTREAM_COMMIT,
        EXPECTED_UPSTREAM_LICENSE_SHA256,
        EXPECTED_UPSTREAM_COPYRIGHT,
        "Whole-file matches: `0`",
        "does not exclude",
        "unknown-needs-review",
        "docs/legal/2026-07-16-cft0808-edict-bounded-similarity-and-rights-review.md",
        "P1_UPSTREAM_MIT_PROVENANCE_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED",
        "P3_CLA_AND_RIGHTS_CHAIN_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED",
        "source_thread=019f6691-258f-71a1-b63d-f7ad0b881d70",
    ):
        if marker not in provenance:
            problems.append(f"provenance:missing:{marker}")

    commercial = read_text(root / "COMMERCIAL-LICENSE.md") if (root / "COMMERCIAL-LICENSE.md").is_file() else ""
    for marker in (
        "LEGAL_REVIEW_REQUIRED",
        "does not itself grant a commercial license",
        f"separate written agreement signed by {EXPECTED_OWNER}",
    ):
        if marker not in commercial:
            problems.append(f"commercial:missing:{marker}")
    if COMMERCIAL_GRANT_PATTERN.search(commercial):
        problems.append("commercial:notice-must-not-grant")

    cla = read_text(root / "CLA.md") if (root / "CLA.md").is_file() else ""
    for marker in (
        "LEGAL_REVIEW_REQUIRED",
        EXPECTED_OWNER,
        "dual-license",
        "commercially license",
        "irrevocable",
    ):
        if marker not in cla:
            problems.append(f"cla:missing:{marker}")

    trademarks = read_text(root / "TRADEMARKS.md") if (root / "TRADEMARKS.md").is_file() else ""
    for marker in (
        EXPECTED_TRADEMARK_POLICY_OWNER,
        "Decretum Matrix（诏令矩阵）",
        "decretum-matrix",
        "nominative",
        "no affiliation",
        "does not claim that any mark is registered",
    ):
        if marker not in trademarks:
            problems.append(f"trademarks:missing:{marker}")
    if TRADEMARK_OWNER_DISCLAIMER_PATTERN.search(trademarks):
        problems.append("trademarks:policy-owner-disclaimed")

    readme = read_text(root / "README.md") if (root / "README.md").is_file() else ""
    for marker in (
        "`beta0.5.9` 是 Git 已确证的历史 `Apache-2.0` 版本",
        "`beta0.5.8` 的 tag 证据为 `LICENSE_NOT_ESTABLISHED_FROM_TAG`",
        "artifact-specific evidence",
    ):
        if marker not in readme:
            problems.append(f"readme:missing:{marker}")
    if (
        any(pattern.search(readme) for pattern in UNSUPPORTED_BETA058_APACHE_PATTERNS)
        or has_beta058_apache_claim_without_evidence(readme)
    ):
        problems.append("readme:unsupported-beta0.5.8-apache-claim")

    authors = read_text(root / "AUTHORS.md") if (root / "AUTHORS.md").is_file() else ""
    for marker in (EXPECTED_OWNER, EXPECTED_MAINTAINER, EXPECTED_GITHUB_ID):
        if marker not in authors:
            problems.append(f"authors:missing:{marker}")

    identity_docs = {
        "NOTICE": notice_text,
        "AUTHORS.md": authors,
        "CLA.md": cla,
        "COMMERCIAL-LICENSE.md": commercial,
        "TRADEMARKS.md": trademarks,
    }
    for name, text in identity_docs.items():
        if EMAIL_PATTERN.search(text):
            problems.append(f"identity:email-forbidden:{name}")
        if PINYIN_PATTERN.search(text):
            problems.append(f"identity:pinyin-forbidden:{name}")
        if COMPANY_PATTERN.search(text):
            problems.append(f"identity:company-forbidden:{name}")
        if ADDRESS_FIELD_PATTERN.search(text):
            problems.append(f"identity:address-forbidden:{name}")
        if OWNER_AS_MAINTAINER_PATTERN.search(text):
            problems.append(f"identity:owner-is-not-maintainer:{name}")

    legal_review_docs = {
        "THIRD_PARTY_NOTICES.md": third_party,
        "PROVENANCE.md": provenance,
        "COMMERCIAL-LICENSE.md": commercial,
        "CLA.md": cla,
        "TRADEMARKS.md": trademarks,
        "CONTRIBUTING.md": contributing,
    }
    for name, text in legal_review_docs.items():
        if "LEGAL_REVIEW_REQUIRED" not in text:
            problems.append(f"legal-review-marker:missing:{name}")

    return {
        "schema": "decretum.release_legal.result.v2",
        "ok": not problems,
        "root": str(root),
        "license_declared": EXPECTED_LICENSE if license_sha256 == EXPECTED_AGPL_SHA256 else None,
        "license_sha256": license_sha256,
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
    with tempfile.TemporaryDirectory(prefix="decretum-release-legal-") as tmp_text:
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

        license_text = (fixture / "LICENSE").read_text(encoding="utf-8")
        (fixture / "LICENSE").write_text(license_text + "\nTAMPERED\n", encoding="utf-8")
        assertions["altered_agpl_text_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "LICENSE", fixture / "LICENSE")

        (fixture / "THIRD_PARTY_NOTICES.md").write_text("missing attribution\n", encoding="utf-8")
        assertions["missing_mit_notice_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "THIRD_PARTY_NOTICES.md", fixture / "THIRD_PARTY_NOTICES.md")

        third_party = (fixture / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        (fixture / "THIRD_PARTY_NOTICES.md").write_text(
            third_party.replace("MIT License\n", "MIT License\nTAMPERED\n", 1),
            encoding="utf-8",
        )
        assertions["altered_mit_text_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "THIRD_PARTY_NOTICES.md", fixture / "THIRD_PARTY_NOTICES.md")

        provenance = (fixture / "PROVENANCE.md").read_text(encoding="utf-8")
        (fixture / "PROVENANCE.md").write_text(
            provenance.replace(
                "P1_UPSTREAM_MIT_PROVENANCE_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED",
                "P1_UPSTREAM_MIT_PROVENANCE_GATE=REVIEW_PENDING",
            ),
            encoding="utf-8",
        )
        assertions["missing_p1_provenance_receipt_gate_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "PROVENANCE.md", fixture / "PROVENANCE.md")

        provenance = (fixture / "PROVENANCE.md").read_text(encoding="utf-8")
        (fixture / "PROVENANCE.md").write_text(
            provenance.replace(
                "P3_CLA_AND_RIGHTS_CHAIN_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED",
                "P3_CLA_AND_RIGHTS_CHAIN_GATE=REVIEW_PENDING",
            ),
            encoding="utf-8",
        )
        assertions["missing_p3_rights_matrix_gate_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "PROVENANCE.md", fixture / "PROVENANCE.md")

        commercial = (fixture / "COMMERCIAL-LICENSE.md").read_text(encoding="utf-8")
        (fixture / "COMMERCIAL-LICENSE.md").write_text(
            commercial + "\nThis notice grants a commercial license.\n", encoding="utf-8"
        )
        assertions["commercial_notice_must_not_grant_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "COMMERCIAL-LICENSE.md", fixture / "COMMERCIAL-LICENSE.md")

        authors = (fixture / "AUTHORS.md").read_text(encoding="utf-8")
        (fixture / "AUTHORS.md").write_text(authors + "\nowner@example.com\n", encoding="utf-8")
        assertions["identity_email_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "AUTHORS.md", fixture / "AUTHORS.md")

        authors = (fixture / "AUTHORS.md").read_text(encoding="utf-8")
        (fixture / "AUTHORS.md").write_text(authors + "\nSun Huaqing\n", encoding="utf-8")
        assertions["identity_pinyin_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "AUTHORS.md", fixture / "AUTHORS.md")

        authors = (fixture / "AUTHORS.md").read_text(encoding="utf-8")
        (fixture / "AUTHORS.md").write_text(authors + "\nCompany: Example LLC\n", encoding="utf-8")
        assertions["identity_company_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "AUTHORS.md", fixture / "AUTHORS.md")

        authors = (fixture / "AUTHORS.md").read_text(encoding="utf-8")
        (fixture / "AUTHORS.md").write_text(authors + "\nAddress: Example Street\n", encoding="utf-8")
        assertions["identity_address_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "AUTHORS.md", fixture / "AUTHORS.md")

        authors = (fixture / "AUTHORS.md").read_text(encoding="utf-8")
        (fixture / "AUTHORS.md").write_text(authors + f"\nMaintainer: {EXPECTED_OWNER}\n", encoding="utf-8")
        assertions["owner_must_not_be_maintainer_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "AUTHORS.md", fixture / "AUTHORS.md")

        trademarks = (fixture / "TRADEMARKS.md").read_text(encoding="utf-8")
        (fixture / "TRADEMARKS.md").write_text(
            trademarks.replace("LEGAL_REVIEW_REQUIRED", "REVIEWED", 1), encoding="utf-8"
        )
        assertions["missing_legal_review_marker_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "TRADEMARKS.md", fixture / "TRADEMARKS.md")

        trademarks = (fixture / "TRADEMARKS.md").read_text(encoding="utf-8")
        (fixture / "TRADEMARKS.md").write_text(
            trademarks.replace(
                EXPECTED_TRADEMARK_POLICY_OWNER,
                f"Trademark policy owner: {EXPECTED_MAINTAINER}",
                1,
            ),
            encoding="utf-8",
        )
        assertions["wrong_trademark_policy_owner_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "TRADEMARKS.md", fixture / "TRADEMARKS.md")

        trademarks = (fixture / "TRADEMARKS.md").read_text(encoding="utf-8")
        (fixture / "TRADEMARKS.md").write_text(
            trademarks + "\nThis identity statement does not establish ownership of any trademark.\n",
            encoding="utf-8",
        )
        assertions["trademark_owner_disclaimer_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "TRADEMARKS.md", fixture / "TRADEMARKS.md")

        readme = (fixture / "README.md").read_text(encoding="utf-8")
        (fixture / "README.md").write_text(
            readme + "\nOld beta0.5.8 and beta0.5.9 are Apache-2.0 releases.\n",
            encoding="utf-8",
        )
        assertions["unsupported_beta058_apache_claim_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "README.md", fixture / "README.md")

        (fixture / "SBOM.spdx.json").write_text("[]\n", encoding="utf-8")
        assertions["non_object_sbom_fails_without_exception"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "SBOM.spdx.json", fixture / "SBOM.spdx.json")

        sbom = json.loads((fixture / "SBOM.spdx.json").read_text(encoding="utf-8"))
        sbom["spdxVersion"] = "SPDX-2.2"
        (fixture / "SBOM.spdx.json").write_text(json.dumps(sbom), encoding="utf-8")
        assertions["wrong_sbom_version_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "SBOM.spdx.json", fixture / "SBOM.spdx.json")

        sbom = json.loads((fixture / "SBOM.spdx.json").read_text(encoding="utf-8"))
        sbom["documentNamespace"] = "https://example.invalid/wrong"
        (fixture / "SBOM.spdx.json").write_text(json.dumps(sbom), encoding="utf-8")
        assertions["wrong_sbom_namespace_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "SBOM.spdx.json", fixture / "SBOM.spdx.json")

        sbom = json.loads((fixture / "SBOM.spdx.json").read_text(encoding="utf-8"))
        sbom["creationInfo"]["created"] = "2026-07-16T00:00:00Z"
        (fixture / "SBOM.spdx.json").write_text(json.dumps(sbom), encoding="utf-8")
        assertions["wrong_sbom_created_fails"] = evaluate(fixture)["ok"] is False
        shutil.copy2(root / "SBOM.spdx.json", fixture / "SBOM.spdx.json")

        sbom = json.loads((fixture / "SBOM.spdx.json").read_text(encoding="utf-8"))
        sbom["packages"][0]["copyrightText"] = "NOASSERTION"
        (fixture / "SBOM.spdx.json").write_text(json.dumps(sbom), encoding="utf-8")
        assertions["wrong_sbom_copyright_fails"] = evaluate(fixture)["ok"] is False

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
