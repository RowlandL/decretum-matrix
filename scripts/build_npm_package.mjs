import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { constants as fsConstants, createReadStream, readFileSync } from "node:fs";
import {
  chmod,
  copyFile,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
  utimes,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { isDeepStrictEqual } from "node:util";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
export const REPO_ROOT = path.resolve(path.dirname(SCRIPT_PATH), "..");

function gitText(...args) {
  const result = spawnSync("git", args, {
    cwd: REPO_ROOT,
    encoding: "utf8",
    shell: false,
    timeout: 30_000,
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    const detail = result.error?.message || result.stderr?.trim() || `exit ${result.status}`;
    throw new Error(`git ${args.join(" ")} failed: ${detail}`);
  }
  return result.stdout.trim();
}

export function normalizeRepositoryRemote(remote) {
  const value = remote.trim();
  let owner;
  let repository;
  const scpMatch = /^(?:git@)?github\.com:([^/]+)\/([^/?#]+)$/i.exec(value);
  if (scpMatch) {
    [, owner, repository] = scpMatch;
  } else {
    let parsed;
    try {
      parsed = new URL(value);
    } catch {
      throw new Error("origin is not a supported GitHub URL");
    }
    if (
      !["https:", "ssh:"].includes(parsed.protocol) ||
      parsed.hostname.toLowerCase() !== "github.com" ||
      parsed.username ||
      parsed.password ||
      parsed.search ||
      parsed.hash
    ) {
      throw new Error("origin is not a supported GitHub URL");
    }
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length !== 2) {
      throw new Error("origin GitHub path is ambiguous");
    }
    [owner, repository] = parts;
  }
  repository = repository.replace(/\.git$/i, "");
  if (
    !/^[A-Za-z0-9_.-]+$/.test(owner) ||
    !/^[A-Za-z0-9_.-]+$/.test(repository)
  ) {
    throw new Error("origin owner/repository is invalid");
  }
  return Object.freeze({
    owner,
    repository,
    canonicalUrl: `https://github.com/${owner}/${repository}.git`,
  });
}

function loadRepositoryOracle(root, manifest) {
  const result = spawnSync(
    "git",
    ["remote", "get-url", "--all", "origin"],
    {
      cwd: root,
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
      shell: false,
      timeout: 30_000,
      windowsHide: true,
    },
  );
  if (result.error || result.status !== 0) {
    throw new Error(
      `origin repository oracle unavailable: ${result.error?.message || result.stderr.trim()}`,
    );
  }
  const remotes = result.stdout
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (remotes.length !== 1) {
    throw new Error(`origin repository oracle is ambiguous: ${remotes.length} URLs`);
  }
  const repository = normalizeRepositoryRemote(remotes[0]);
  if (
    repository.owner !== "RowlandL" ||
    repository.repository !== "decretum-matrix"
  ) {
    throw new Error(
      `origin repository identity mismatch: ${repository.owner}/${repository.repository}`,
    );
  }
  if (manifest.provenance !== "PROVENANCE.md") {
    throw new Error("release-manifest.json provenance pointer mismatch");
  }
  const provenancePath = path.join(root, manifest.provenance);
  const provenanceBytes = readFileSync(provenancePath);
  const provenanceEntries = (manifest.files || []).filter(
    (entry) => entry.path === manifest.provenance,
  );
  const provenanceSha256 = createHash("sha256")
    .update(provenanceBytes)
    .digest("hex");
  if (
    provenanceEntries.length !== 1 ||
    provenanceEntries[0].size !== provenanceBytes.length ||
    provenanceEntries[0].sha256 !== provenanceSha256
  ) {
    throw new Error("manifest provenance file inventory mismatch");
  }
  const provenanceText = provenanceBytes.toString("utf8");
  if (
    !provenanceText.includes(
      "Canonical repository/skill/package name: `decretum-matrix`",
    ) ||
    !provenanceText.includes("Public maintainer identity: `@RowlandL`")
  ) {
    throw new Error("PROVENANCE.md repository owner/name identity mismatch");
  }
  return Object.freeze({
    ...repository,
    command: "git remote get-url --all origin",
    rc: result.status,
    provenancePath: manifest.provenance,
    provenanceSha256,
  });
}

export function deriveReleaseIdentity(releaseLabel, manifest) {
  const match = /^beta(\d+\.\d+\.\d+)$/.exec(releaseLabel);
  if (!match) {
    throw new Error(`unsupported release label: ${releaseLabel}`);
  }
  const versionCore = match[1];
  if (
    manifest.release_label !== releaseLabel ||
    manifest.version_core !== versionCore ||
    manifest.channel !== "beta"
  ) {
    throw new Error("VERSION and release-manifest.json identity disagree");
  }
  const artifactName = `decretum-matrix-${releaseLabel}.zip`;
  const expectedTagRef = `refs/tags/${releaseLabel}`;
  if (
    manifest.artifact_name !== artifactName ||
    manifest.sidecar_name !== `${artifactName}.sha256` ||
    manifest.attestation_name !==
      `decretum-matrix-${releaseLabel}.release-attestation.json` ||
    manifest.expected_final_tag !== expectedTagRef
  ) {
    throw new Error("release-manifest.json artifact/tag identity disagree");
  }
  const packageVersion = `${versionCore}-beta.0`;
  return Object.freeze({
    artifactName,
    attestationName: manifest.attestation_name,
    packageVersion,
    receiptName: `rowlandl-decretum-matrix-${packageVersion}.receipt.json`,
    releaseLabel,
    releaseNotesName: `decretum-matrix-${releaseLabel}.release-notes.md`,
    sidecarName: manifest.sidecar_name,
    tagRef: expectedTagRef,
    tarballName: `rowlandl-decretum-matrix-${packageVersion}.tgz`,
    versionCore,
  });
}

const LIVE_VERSION = readFileSync(path.join(REPO_ROOT, "VERSION"), "utf8").trim();
const LIVE_MANIFEST_BYTES = readFileSync(
  path.join(REPO_ROOT, "release-manifest.json"),
);
const LIVE_MANIFEST = JSON.parse(LIVE_MANIFEST_BYTES.toString("utf8"));
const LIVE_IDENTITY = deriveReleaseIdentity(LIVE_VERSION, LIVE_MANIFEST);
const LIVE_REPOSITORY = loadRepositoryOracle(REPO_ROOT, LIVE_MANIFEST);

export const PACKAGE_NAME = "@rowlandl/decretum-matrix";
export const PACKAGE_VERSION = LIVE_IDENTITY.packageVersion;
export const DIST_TAG = "beta";
export const REGISTRY = "https://npm.pkg.github.com";
export const LICENSE = "AGPL-3.0-only";
export const SOURCE_COMMIT = gitText("rev-parse", "HEAD");
export const SOURCE_TREE = gitText("rev-parse", "HEAD^{tree}");
export const RELEASE_LABEL = LIVE_IDENTITY.releaseLabel;
export const TAG_REF = LIVE_IDENTITY.tagRef;
export const REPOSITORY_URL = LIVE_REPOSITORY.canonicalUrl;
export const RELEASE_URL = `${REPOSITORY_URL.replace(/\.git$/, "")}/releases/tag/${RELEASE_LABEL}`;
export const WORKSPACE_ROOT = path.resolve(
  process.env.DECRETUM_WORKSPACE_ROOT || path.dirname(REPO_ROOT),
);
export const RELEASE_ASSET_DIR = path.join(
  WORKSPACE_ROOT,
  "release-packages",
  "decretum-matrix",
  RELEASE_LABEL,
);
export const OUTPUT_DIR = path.join(
  WORKSPACE_ROOT,
  "release-staging",
  "decretum-matrix",
  "npm",
  `${PACKAGE_VERSION}-legal-v2`,
);

export const TARBALL_NAME = LIVE_IDENTITY.tarballName;
export const SIDECAR_NAME = `${TARBALL_NAME}.sha256`;
export const RECEIPT_NAME = LIVE_IDENTITY.receiptName;

const FIXED_MTIME = new Date("2000-01-01T00:00:00.000Z");
const MAX_TARBALL_SIZE = 7_000_000;
const OUTPUT_RELATIVE = `release-staging/decretum-matrix/npm/${PACKAGE_VERSION}-legal-v2`;
const RELEASE_MANIFEST_SHA256 = createHash("sha256")
  .update(LIVE_MANIFEST_BYTES)
  .digest("hex");
const AUTHORITY_RECEIPT_ID = `npm-${RELEASE_LABEL}-${SOURCE_COMMIT.slice(0, 8)}-legal-v2`;
const AUTHORITY_CURSOR = `${RELEASE_LABEL.toUpperCase()}_NPM_LOCAL_CANDIDATE`;

export let PACKAGE_README;

const LEGAL_PATHS = Object.freeze([
  "LICENSE",
  "NOTICE",
  "THIRD_PARTY_NOTICES.md",
  "PROVENANCE.md",
  "COMMERCIAL-LICENSE.md",
  "CLA.md",
  "TRADEMARKS.md",
  "CONTRIBUTING.md",
  "AUTHORS.md",
  "SECURITY.md",
  "PRIVACY.md",
]);

export const LEGAL_SOURCE_FILES = Object.freeze(
  LEGAL_PATHS.map((legalPath) => {
    const matches = (LIVE_MANIFEST.files || []).filter(
      (entry) => entry.path === legalPath,
    );
    if (
      matches.length !== 1 ||
      !/^[0-9a-f]{64}$/.test(matches[0].sha256) ||
      !Number.isInteger(matches[0].size) ||
      matches[0].size < 0
    ) {
      throw new Error(`release-manifest.json legal entry invalid: ${legalPath}`);
    }
    return Object.freeze({
      path: legalPath,
      sha256: matches[0].sha256,
      size: matches[0].size,
    });
  }),
);

const PACKAGE_FILE_ALLOWLIST = Object.freeze([
  "README.md",
  ...LEGAL_SOURCE_FILES.map((file) => file.path),
  "release/",
]);

export const RELEASE_ASSETS = Object.freeze([
  Object.freeze({
    name: "SBOM.spdx.json",
    path: "release/SBOM.spdx.json",
  }),
  Object.freeze({
    name: LIVE_IDENTITY.attestationName,
    path: `release/${LIVE_IDENTITY.attestationName}`,
  }),
  Object.freeze({
    name: LIVE_IDENTITY.releaseNotesName,
    path: `release/${LIVE_IDENTITY.releaseNotesName}`,
  }),
  Object.freeze({
    name: LIVE_IDENTITY.artifactName,
    path: `release/${LIVE_IDENTITY.artifactName}`,
  }),
  Object.freeze({
    name: LIVE_IDENTITY.sidecarName,
    path: `release/${LIVE_IDENTITY.sidecarName}`,
  }),
]);

function buildPackageReadmeForContract(contract) {
  return `${[
    `# ${contract.packageName}`,
    "",
    `Immutable legal-v2 npm carrier for Decretum Matrix ${contract.releaseLabel}.`,
    "",
    `- Source commit: \`${contract.sourceCommit}\``,
    `- Release tag: \`${contract.releaseLabel}\``,
    `- Release URL: ${contract.releaseUrl}`,
    `- Registry dist-tag: \`${contract.distTag}\``,
    `- License: \`${contract.license}\``,
    "",
    `This package contains the release ZIP and checksum, release attestation, release notes, SPDX SBOM, and legal/governance documents validated against the ${contract.releaseLabel} release manifest.`,
    "",
    "It has no dependencies, executable entry points, or install lifecycle scripts. Installing it does not modify host configuration or execute package code.",
    "",
    `Verify \`release/${contract.identity.artifactName}\` with \`release/${contract.identity.sidecarName}\` and the release attestation before use.`,
  ].join("\n")}\n`;
}

function createPackageContract(options) {
  const contract = {
    identity: options.identity,
    packageName: options.packageName,
    packageVersion: options.identity.packageVersion,
    releaseLabel: options.identity.releaseLabel,
    tagRef: options.identity.tagRef,
    tarballName: options.identity.tarballName,
    sidecarName: `${options.identity.tarballName}.sha256`,
    receiptName: options.identity.receiptName,
    distTag: options.distTag,
    registry: options.registry,
    license: options.license,
    repositoryUrl: options.repository.canonicalUrl,
    repository: options.repository,
    repoRoot: options.repoRoot,
    releaseAssetDir: options.releaseAssetDir,
    releaseUrl: `${options.repository.canonicalUrl.replace(/\.git$/, "")}/releases/tag/${options.identity.releaseLabel}`,
    sourceCommit: options.sourceCommit,
    sourceTree: options.sourceTree,
    releaseManifestSha256: options.releaseManifestSha256,
    legalFiles: Object.freeze([...options.legalFiles]),
    releaseAssets: Object.freeze([...options.releaseAssets]),
    outputRelative: options.outputRelative,
    authorityReceiptId: options.authorityReceiptId,
    authorityCursor: options.authorityCursor,
  };
  contract.readme = buildPackageReadmeForContract(contract);
  contract.expectedPackFiles = Object.freeze(
    [
      "package.json",
      "README.md",
      ...contract.legalFiles.map((file) => file.path),
      ...contract.releaseAssets.map((asset) => asset.path),
    ].sort(),
  );
  return Object.freeze(contract);
}

const LIVE_PACKAGE_CONTRACT = createPackageContract({
  identity: LIVE_IDENTITY,
  packageName: PACKAGE_NAME,
  distTag: DIST_TAG,
  registry: REGISTRY,
  license: LICENSE,
  repository: LIVE_REPOSITORY,
  repoRoot: REPO_ROOT,
  releaseAssetDir: RELEASE_ASSET_DIR,
  sourceCommit: SOURCE_COMMIT,
  sourceTree: SOURCE_TREE,
  releaseManifestSha256: RELEASE_MANIFEST_SHA256,
  legalFiles: LEGAL_SOURCE_FILES,
  releaseAssets: RELEASE_ASSETS,
  outputRelative: OUTPUT_RELATIVE,
  authorityReceiptId: AUTHORITY_RECEIPT_ID,
  authorityCursor: AUTHORITY_CURSOR,
});
PACKAGE_README = LIVE_PACKAGE_CONTRACT.readme;

const SYNTHETIC_ZIP_SCRIPT = String.raw`
import json, stat, sys, zipfile
from pathlib import Path

source = Path(sys.argv[1])
output = Path(sys.argv[2])
members = json.loads(sys.argv[3])
with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_STORED) as archive:
    for relative in members:
        body = (source / relative).read_bytes()
        info = zipfile.ZipInfo(f"court-capability-router/{relative}", (1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, body, compress_type=zipfile.ZIP_STORED)
`;

const ZIP_PRIVACY_SCRIPT = String.raw`
import hashlib, json, re, stat, sys, zipfile
from pathlib import Path

if len(sys.argv) != 5:
    print(json.dumps({"ok": False, "problems": ["validator-argument-contract"]}))
    raise SystemExit(2)
archive_path = Path(sys.argv[1])
checker_root = Path(sys.argv[2])
expected_label = sys.argv[3]
accepted_manifest_path = Path(sys.argv[4])
sys.path.insert(0, str(checker_root / "scripts"))
import package_skill

problems = []
accepted_manifest_bytes = accepted_manifest_path.read_bytes()
accepted_manifest_sha256 = hashlib.sha256(accepted_manifest_bytes).hexdigest()
accepted_manifest = json.loads(accepted_manifest_bytes.decode("utf-8"))
archive_root = str(accepted_manifest.get("archive_root", "")).rstrip("/")
if archive_root != package_skill.ROOT_NAME:
    problems.append("accepted-manifest:archive-root-mismatch")
if accepted_manifest.get("release_label") != expected_label:
    problems.append("accepted-manifest:release-label-mismatch")

expected = {}
expected_casefolded = {}
for entry in accepted_manifest.get("files", []):
    if not isinstance(entry, dict):
        problems.append("accepted-manifest:non-object-file-entry")
        continue
    relative = entry.get("path")
    mode = entry.get("mode")
    digest = entry.get("sha256")
    size = entry.get("size")
    if (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or "\\" in relative
        or any(part in {"", ".", ".."} or ":" in part for part in relative.split("/"))
    ):
        problems.append(f"accepted-manifest:unsafe-path:{relative}")
        continue
    if relative == "release-manifest.json":
        problems.append("accepted-manifest:self-hash-forbidden")
    if relative in expected:
        problems.append(f"accepted-manifest:duplicate-path:{relative}")
    collision = expected_casefolded.get(relative.casefold())
    if collision is not None and collision != relative:
        problems.append(f"accepted-manifest:case-collision:{relative}:{collision}")
    expected_casefolded[relative.casefold()] = relative
    if mode != "100644":
        problems.append(f"accepted-manifest:unsupported-mode:{relative}:{mode}")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        problems.append(f"accepted-manifest:invalid-sha256:{relative}")
    if not isinstance(size, int) or size < 0:
        problems.append(f"accepted-manifest:invalid-size:{relative}")
    expected[relative] = {"mode": mode, "sha256": digest, "size": size}

def inventory_text(rows):
    return "".join(
        f"{row['mode']} {row['sha256']} {row['size']} {relative}\n"
        for relative, row in sorted(rows.items(), key=lambda item: item[0].encode("utf-8"))
    )

manifest_inventory_text = inventory_text(expected)
manifest_inventory_sha256 = hashlib.sha256(manifest_inventory_text.encode("utf-8")).hexdigest()
integrity = accepted_manifest.get("integrity")
if not isinstance(integrity, dict):
    problems.append("accepted-manifest:missing-integrity")
else:
    if integrity.get("manifest_in_file_inventory") is not False:
        problems.append("accepted-manifest:self-inventory-contract-mismatch")
    if integrity.get("payload_file_count") != len(expected):
        problems.append("accepted-manifest:payload-count-mismatch")
    if integrity.get("payload_index_sha256") != manifest_inventory_sha256:
        problems.append("accepted-manifest:payload-index-sha256-mismatch")

actual = {}
actual_casefolded = {}
manifest_member_count = 0
manifest_member_sha256 = None
total_uncompressed = 0
with zipfile.ZipFile(archive_path) as archive:
    infos = archive.infolist()
    if len(infos) > package_skill.MAX_ARCHIVE_ENTRIES:
        problems.append("too-many-members")
    raw_names = [info.filename for info in infos]
    if len(raw_names) != len(set(raw_names)):
        problems.append("duplicate-member")
    for info in infos:
        normalized, path_problem = package_skill.normalized_zip_member(info.filename)
        if path_problem or normalized is None:
            problems.append(f"{info.filename}:{path_problem or 'unsafe-member-path'}")
            continue
        collision = actual_casefolded.get(normalized.casefold())
        if collision is not None and collision != normalized:
            problems.append(f"{normalized}:case-collision:{collision}")
        actual_casefolded[normalized.casefold()] = normalized
        is_dir = info.is_dir() or info.filename.endswith("/")
        if is_dir:
            problems.append(f"{normalized}:not-regular-file")
            continue
        policy_problem = package_skill.archive_member_policy_problem(normalized, False)
        if policy_problem:
            problems.append(f"{normalized}:{policy_problem}")
        if package_skill.zipinfo_is_link_or_reparse(info):
            problems.append(f"{normalized}:symlink-or-reparse")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_IFMT(unix_mode) != stat.S_IFREG:
            problems.append(f"{normalized}:not-regular-file-mode:{unix_mode:o}")
        zip_mode = f"{unix_mode:06o}"
        if info.flag_bits & 0x1:
            problems.append(f"{normalized}:encrypted-member")
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            problems.append(f"{normalized}:unsupported-compression:{info.compress_type}")
        total_uncompressed += info.file_size
        if info.file_size > package_skill.MAX_MEMBER_UNCOMPRESSED_BYTES:
            problems.append(f"{normalized}:member-too-large")
        if total_uncompressed > package_skill.MAX_TOTAL_UNCOMPRESSED_BYTES:
            problems.append("archive-too-large")
        if (
            info.file_size >= package_skill.MIN_COMPRESSION_RATIO_BYTES
            and info.file_size / max(info.compress_size, 1) > package_skill.MAX_COMPRESSION_RATIO
        ):
            problems.append(f"{normalized}:compression-ratio")
        if package_skill.should_scan_content(normalized):
            if package_skill.has_secret_like_content(archive, info):
                problems.append(f"{normalized}:secret-like-content")
            if package_skill.has_host_absolute_path_content(archive, info):
                problems.append(f"{normalized}:host-absolute-path-content")
        relative = normalized.split("/", 1)[1]
        digest = hashlib.sha256(archive.read(info)).hexdigest()
        if relative == "release-manifest.json":
            manifest_member_count += 1
            manifest_member_sha256 = digest
            if archive.read(info) != accepted_manifest_bytes:
                problems.append("release-manifest.json:accepted-bytes-mismatch")
            continue
        actual[relative] = {
            "mode": zip_mode,
            "sha256": digest,
            "size": info.file_size,
        }

if manifest_member_count != 1:
    problems.append(f"release-manifest.json:member-count:{manifest_member_count}")
missing = sorted(set(expected) - set(actual), key=lambda value: value.encode("utf-8"))
extra = sorted(set(actual) - set(expected), key=lambda value: value.encode("utf-8"))
problems.extend(f"missing:{relative}" for relative in missing)
problems.extend(f"extra:{relative}" for relative in extra)
for relative in sorted(set(expected) & set(actual), key=lambda value: value.encode("utf-8")):
    for field in ("mode", "size", "sha256"):
        if actual[relative][field] != expected[relative][field]:
            problems.append(
                f"{relative}:{field}-mismatch:{actual[relative][field]}:{expected[relative][field]}"
            )

payload_inventory_text = inventory_text(actual)
payload_inventory_sha256 = hashlib.sha256(payload_inventory_text.encode("utf-8")).hexdigest()

if problems:
    print(json.dumps({
        "ok": False,
        "problems": sorted(set(problems)),
        "accepted_manifest_sha256": accepted_manifest_sha256,
        "manifest_inventory_count": len(expected),
        "manifest_inventory_sha256": manifest_inventory_sha256,
        "payload_inventory_count": len(actual),
        "payload_inventory_sha256": payload_inventory_sha256,
    }, ensure_ascii=False))
    raise SystemExit(2)
print(json.dumps({
    "ok": True,
    "member_count": len(actual) + manifest_member_count,
    "payload_member_count": len(actual),
    "accepted_manifest_sha256": accepted_manifest_sha256,
    "manifest_member_sha256": manifest_member_sha256,
    "manifest_inventory_count": len(expected),
    "manifest_inventory_sha256": manifest_inventory_sha256,
    "payload_inventory_count": len(actual),
    "payload_inventory_sha256": payload_inventory_sha256,
}, ensure_ascii=False))
`;

const TAMPER_ZIP_SCRIPT = String.raw`
import sys, zipfile
from pathlib import Path

source = Path(sys.argv[1])
output = Path(sys.argv[2])
target = sys.argv[3]
tampered = False
with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(output, "x") as outgoing:
    for original in incoming.infolist():
        body = bytearray(incoming.read(original))
        if original.filename == target:
            for index, value in enumerate(body):
                if 65 <= value <= 90 or 97 <= value <= 122:
                    body[index] = value ^ 0x20
                    tampered = True
                    break
        info = zipfile.ZipInfo(original.filename, original.date_time)
        info.comment = original.comment
        info.create_system = original.create_system
        info.external_attr = original.external_attr
        info.internal_attr = original.internal_attr
        info.extra = original.extra
        info.compress_type = original.compress_type
        outgoing.writestr(info, bytes(body), compress_type=original.compress_type)
if not tampered:
    raise SystemExit("target member was not tampered")
`;

function payloadInventoryText(entries) {
  return [...entries]
    .sort((left, right) =>
      Buffer.compare(Buffer.from(left.path, "utf8"), Buffer.from(right.path, "utf8")),
    )
    .map(({ mode, sha256, size, path: entryPath }) =>
      `${mode} ${sha256} ${size} ${entryPath}\n`,
    )
    .join("");
}

function runFixtureCommand(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || REPO_ROOT,
    encoding: "utf8",
    env: options.env || process.env,
    maxBuffer: 32 * 1024 * 1024,
    shell: false,
    timeout: options.timeout || 120_000,
    windowsHide: true,
  });
  if (result.error) {
    fail(`${command} fixture invocation failed: ${result.error.message}`);
  }
  return result;
}

let resolvedPythonInvocation;

function pythonCandidates() {
  const override = process.env.DECRETUM_PYTHON_EXECUTABLE?.trim();
  if (override) {
    return [{ command: override, prefixArgs: [], source: "override" }];
  }
  if (process.platform === "win32") {
    return [
      { command: "python", prefixArgs: [], source: "discovery" },
      { command: "py", prefixArgs: ["-3"], source: "discovery" },
      { command: "python3", prefixArgs: [], source: "discovery" },
    ];
  }
  return [
    { command: "python3", prefixArgs: [], source: "discovery" },
    { command: "python", prefixArgs: [], source: "discovery" },
  ];
}

function resolvePythonInvocation() {
  if (resolvedPythonInvocation) {
    return resolvedPythonInvocation;
  }
  const candidates = pythonCandidates();
  for (const candidate of candidates) {
    const probe = spawnSync(
      candidate.command,
      [
        ...candidate.prefixArgs,
        "-B",
        "-c",
        "import json,sys; print(json.dumps({'major':sys.version_info[0],'minor':sys.version_info[1]}))",
      ],
      {
        cwd: REPO_ROOT,
        encoding: "utf8",
        maxBuffer: 1024 * 1024,
        shell: false,
        timeout: 30_000,
        windowsHide: true,
      },
    );
    if (!probe.error && probe.status === 0) {
      let version;
      try {
        version = JSON.parse(probe.stdout.trim());
      } catch {
        continue;
      }
      if (
        Number.isInteger(version.major) &&
        version.major === 3 &&
        Number.isInteger(version.minor)
      ) {
        resolvedPythonInvocation = Object.freeze({
          command: candidate.command,
          prefixArgs: Object.freeze([...candidate.prefixArgs]),
          source: candidate.source,
          version: Object.freeze({ major: version.major, minor: version.minor }),
        });
        return resolvedPythonInvocation;
      }
    }
    if (candidate.source === "override") {
      fail("configured Python interpreter failed the Python 3 probe");
    }
  }
  fail("no compatible Python 3 interpreter was discovered");
}

function runPythonFixtureCommand(args, options = {}) {
  const invocation = resolvePythonInvocation();
  return runFixtureCommand(
    invocation.command,
    [...invocation.prefixArgs, "-B", ...args],
    options,
  );
}

export function pythonInvocationContract() {
  const invocation = resolvePythonInvocation();
  return Object.freeze({
    command: "$PYTHON",
    source: invocation.source,
    python_major: invocation.version.major,
    python_minor: invocation.version.minor,
    bytecode_disabled: true,
    shell: false,
  });
}

const CRITICAL_HEAD_BOUND_PATHS = Object.freeze([
  "package.json",
  "package-lock.json",
  "scripts/build_npm_package.mjs",
  "scripts/check_npm_package.mjs",
  "VERSION",
  "release-manifest.json",
  "scripts/package_skill.py",
  "scripts/check_package_privacy.py",
]);

async function validateTrackedProductionAuthority(root, expectedReleaseLabel) {
  const status = runFixtureCommand(
    "git",
    ["status", "--porcelain=v1", "--untracked-files=no"],
    { cwd: root, timeout: 30_000 },
  );
  assert(status.status === 0, `tracked worktree status failed: ${status.stderr}`);
  assert(
    status.stdout.trim() === "",
    "tracked production authority worktree is dirty",
  );
  const headResult = runFixtureCommand("git", ["rev-parse", "HEAD"], {
    cwd: root,
    timeout: 30_000,
  });
  assert(headResult.status === 0, `cannot resolve production HEAD: ${headResult.stderr}`);
  const files = [];
  const bytesByPath = new Map();
  for (const relativePath of CRITICAL_HEAD_BOUND_PATHS) {
    const worktreePath = path.join(root, ...relativePath.split("/"));
    const worktreeBytes = await readFile(worktreePath);
    const head = spawnSync("git", ["show", `HEAD:${relativePath}`], {
      cwd: root,
      encoding: null,
      maxBuffer: 32 * 1024 * 1024,
      shell: false,
      timeout: 30_000,
      windowsHide: true,
    });
    assert(
      !head.error && head.status === 0,
      `critical production authority path is not tracked at HEAD: ${relativePath}`,
    );
    const headBytes = Buffer.from(head.stdout);
    assert(
      worktreeBytes.equals(headBytes),
      `critical production authority path differs from HEAD: ${relativePath}`,
    );
    const sha256 = createHash("sha256").update(headBytes).digest("hex");
    files.push({ path: relativePath, sha256, size: headBytes.length });
    bytesByPath.set(relativePath, headBytes);
  }
  const headVersion = bytesByPath.get("VERSION").toString("utf8").trim();
  const headManifestBytes = bytesByPath.get("release-manifest.json");
  const headManifest = JSON.parse(headManifestBytes.toString("utf8"));
  const headIdentity = deriveReleaseIdentity(headVersion, headManifest);
  assert(
    headIdentity.releaseLabel === expectedReleaseLabel,
    "HEAD VERSION/release-manifest identity differs from the accepted release",
  );
  return Object.freeze({
    command: "git status --porcelain=v1 --untracked-files=no + git show HEAD:<path>",
    rc: 0,
    head: headResult.stdout.trim(),
    release_label: headIdentity.releaseLabel,
    release_manifest_sha256: createHash("sha256")
      .update(headManifestBytes)
      .digest("hex"),
    files: Object.freeze(files),
  });
}

function validateAnnotatedReleaseTag(root, releaseLabel, expectedHead) {
  const tagRef = `refs/tags/${releaseLabel}`;
  const tagType = runFixtureCommand("git", ["cat-file", "-t", tagRef], {
    cwd: root,
    timeout: 30_000,
  });
  assert(
    tagType.status === 0,
    `annotated release tag is missing: ${tagRef}`,
  );
  assert(tagType.stdout.trim() === "tag", `release tag is lightweight: ${tagRef}`);
  const tagCommit = runFixtureCommand(
    "git",
    ["rev-parse", `${tagRef}^{commit}`],
    { cwd: root, timeout: 30_000 },
  );
  assert(tagCommit.status === 0, `cannot peel release tag to commit: ${tagRef}`);
  assert(
    tagCommit.stdout.trim() === expectedHead,
    `release tag does not point to HEAD: ${tagRef}`,
  );
  return Object.freeze({
    command: `git cat-file -t ${tagRef} + git rev-parse ${tagRef}^{commit}`,
    rc: 0,
    ref: tagRef,
    type: "tag",
    commit: tagCommit.stdout.trim(),
    relation: "HEAD_MATCH",
  });
}

async function writeFixed(filePath, body) {
  await writeFile(filePath, body, { flag: "wx", mode: 0o644 });
  await chmod(filePath, 0o644);
  await utimes(filePath, FIXED_MTIME, FIXED_MTIME);
}

async function copyFixed(sourcePath, destinationPath) {
  await copyFile(sourcePath, destinationPath, fsConstants.COPYFILE_EXCL);
  await chmod(destinationPath, 0o644);
  await utimes(destinationPath, FIXED_MTIME, FIXED_MTIME);
}

async function createOrReuseOutput(outputDirectory, files) {
  if (await pathExists(outputDirectory)) {
    const metadata = await lstat(outputDirectory);
    if (!metadata.isDirectory()) {
      throw new OutputCollisionError(
        "existing output path is not a directory",
        { reason: "NOT_A_DIRECTORY" },
      );
    }
    const names = (await readdir(outputDirectory)).sort();
    const expectedNames = [...files.keys()].sort();
    if (!isDeepStrictEqual(names, expectedNames)) {
      throw new OutputCollisionError(
        "existing output directory allowlist differs from the content key",
        { reason: "FILE_ALLOWLIST_MISMATCH" },
      );
    }
    for (const [name, expectedBody] of files) {
      const existingPath = path.join(outputDirectory, name);
      let actualBody;
      try {
        const existingMetadata = await lstat(existingPath);
        if (!existingMetadata.isFile()) {
          throw new OutputCollisionError(
            `existing output entry is not a regular file: ${name}`,
            { reason: "NON_REGULAR_ENTRY", path: name },
          );
        }
        actualBody = await readFile(existingPath);
      } catch (error) {
        if (error instanceof OutputCollisionError) {
          throw error;
        }
        throw new OutputCollisionError(
          `existing output entry cannot be read: ${name}`,
          { reason: "ENTRY_READ_FAILED", path: name },
        );
      }
      if (!actualBody.equals(expectedBody)) {
        throw new OutputCollisionError(
          `existing output content differs for ${name}`,
          { reason: "CONTENT_MISMATCH", path: name },
        );
      }
    }
    return "REUSED";
  }

  await mkdir(path.dirname(outputDirectory), { recursive: true });
  await mkdir(outputDirectory, { recursive: false });
  try {
    for (const [name, body] of files) {
      await writeFile(path.join(outputDirectory, name), body, {
        flag: "wx",
        mode: 0o644,
      });
    }
  } catch (error) {
    await rm(outputDirectory, { force: true, recursive: true });
    throw error;
  }
  return "CREATED";
}

async function packageOutputFiles(verified, receipt, contract) {
  return new Map([
    [contract.tarballName, await readFile(verified.firstPack.tarballPath)],
    [
      contract.sidecarName,
      Buffer.from(
        `${verified.firstPack.sha256}  ${contract.tarballName}\n`,
        "utf8",
      ),
    ],
    [contract.receiptName, Buffer.from(jsonText(receipt), "utf8")],
  ]);
}

async function materializeVerifiedPackage(
  verified,
  outputDirectory,
  contract = LIVE_PACKAGE_CONTRACT,
) {
  const receipt = buildReceipt(verified, contract);
  const files = await packageOutputFiles(verified, receipt, contract);
  const materialization = await createOrReuseOutput(outputDirectory, files);
  return { files, materialization, receipt };
}

async function snapshotOutputDirectory(outputDirectory) {
  const snapshot = [];
  for (const name of (await readdir(outputDirectory)).sort()) {
    const filePath = path.join(outputDirectory, name);
    const metadata = await lstat(filePath, { bigint: true });
    assert(metadata.isFile(), `output snapshot entry is not regular: ${name}`);
    snapshot.push({
      name,
      sha256: await hashFile(filePath),
      size: metadata.size.toString(),
      mtime_ns: metadata.mtimeNs.toString(),
    });
  }
  return snapshot;
}

async function runSyntheticInstalledSmoke(
  operationRoot,
  tarballPath,
  npmState,
  publishPackage,
  expectedFiles,
  expectedHashes,
  contract,
) {
  const smokeRoot = path.join(operationRoot, "synthetic-installed-smoke");
  await mkdir(smokeRoot, { recursive: false });
  await writeFile(
    path.join(smokeRoot, "package.json"),
    jsonText({ name: "decretum-npm-synthetic-smoke", private: true, version: "1.0.0" }),
    { encoding: "utf8", flag: "wx", mode: 0o644 },
  );
  runNpm(
    [
      "install",
      "--offline",
      "--ignore-scripts",
      "--package-lock=false",
      "--save=false",
      tarballPath,
    ],
    smokeRoot,
    npmState,
  );
  const installedRoot = path.join(
    smokeRoot,
    "node_modules",
    ...contract.packageName.split("/"),
  );
  assertDeepEqual(
    await listRegularFiles(installedRoot),
    expectedFiles,
    "synthetic installed package file allowlist",
  );
  const installedPackage = await readJson(
    path.join(installedRoot, "package.json"),
    "synthetic installed package.json",
  );
  assertDeepEqual(installedPackage, publishPackage, "synthetic installed metadata");
  assert(installedPackage.bin === undefined, "synthetic package unexpectedly exposes a bin");
  assert(installedPackage.main === undefined, "synthetic package unexpectedly exposes a main entry");
  assert(installedPackage.scripts === undefined, "synthetic package contains lifecycle scripts");
  assert(
    installedPackage.exports?.["./package.json"] === "./package.json" &&
      installedPackage.exports?.["./release/*"] === "./release/*",
    "synthetic package exports contract mismatch",
  );
  for (const [relativePath, expectedHash] of expectedHashes) {
    assert(
      (await hashFile(path.join(installedRoot, ...relativePath.split("/")))) ===
        expectedHash,
      `synthetic installed hash drift: ${relativePath}`,
    );
  }
  return "PASS";
}

export async function runSyntheticSelfTest() {
  const root = await mkdtemp(path.join(tmpdir(), "decretum-npm-contract-"));
  try {
    const fixtureVersionCore = "1.2.3";
    const releaseLabel = `beta${fixtureVersionCore}`;
    const manifest = {
      artifact_name: `decretum-matrix-${releaseLabel}.zip`,
      attestation_name: `decretum-matrix-${releaseLabel}.release-attestation.json`,
      channel: "beta",
      expected_final_tag: `refs/tags/${releaseLabel}`,
      release_label: releaseLabel,
      sidecar_name: `decretum-matrix-${releaseLabel}.zip.sha256`,
      version_core: fixtureVersionCore,
    };
    const authorityRoot = path.join(root, "authority");
    const assetRoot = path.join(root, "release-assets");
    await mkdir(authorityRoot, { recursive: false });
    await mkdir(path.join(authorityRoot, "scripts"), { recursive: false });
    await mkdir(assetRoot, { recursive: false });
    await writeFile(path.join(authorityRoot, "VERSION"), `${releaseLabel}\n`, {
      encoding: "utf8",
      flag: "wx",
    });

    const legalEntries = [];
    for (const legalPath of LEGAL_PATHS) {
      const sourcePath = path.join(REPO_ROOT, legalPath);
      const destinationPath = path.join(authorityRoot, legalPath);
      await copyFile(sourcePath, destinationPath, fsConstants.COPYFILE_EXCL);
      legalEntries.push({
        mode: "100644",
        path: legalPath,
        sha256: await hashFile(destinationPath),
        size: (await stat(destinationPath)).size,
      });
    }
    const fixtureLegalFiles = Object.freeze(
      legalEntries.map(({ path: legalPath, sha256, size }) =>
        Object.freeze({ path: legalPath, sha256, size }),
      ),
    );
    for (const relativePath of CRITICAL_HEAD_BOUND_PATHS.filter(
      (item) => !["VERSION", "release-manifest.json"].includes(item),
    )) {
      await copyFile(
        path.join(REPO_ROOT, ...relativePath.split("/")),
        path.join(authorityRoot, ...relativePath.split("/")),
        fsConstants.COPYFILE_EXCL,
      );
    }
    const sbom = {
      spdxVersion: "SPDX-2.3",
      name: `decretum-matrix-${releaseLabel}`,
      documentNamespace: `https://spdx.org/spdxdocs/decretum-matrix-${releaseLabel}-synthetic`,
      packages: [
        {
          name: "decretum-matrix",
          versionInfo: releaseLabel,
          licenseDeclared: LICENSE,
        },
      ],
    };
    await writeFile(
      path.join(authorityRoot, "SBOM.spdx.json"),
      jsonText(sbom),
      { encoding: "utf8", flag: "wx" },
    );
    const versionEntry = {
      mode: "100644",
      path: "VERSION",
      sha256: await hashFile(path.join(authorityRoot, "VERSION")),
      size: (await stat(path.join(authorityRoot, "VERSION"))).size,
    };
    const sbomEntry = {
      mode: "100644",
      path: "SBOM.spdx.json",
      sha256: await hashFile(path.join(authorityRoot, "SBOM.spdx.json")),
      size: (await stat(path.join(authorityRoot, "SBOM.spdx.json"))).size,
    };
    manifest.name = "decretum-matrix";
    manifest.package_name = "decretum-matrix";
    manifest.display_name = "Decretum Matrix（诏令矩阵）";
    manifest.archive_root = "court-capability-router/";
    manifest.license = { declared: LICENSE, file: "LICENSE" };
    manifest.provenance = "PROVENANCE.md";
    manifest.files = [...legalEntries, versionEntry, sbomEntry].sort((left, right) =>
      Buffer.compare(Buffer.from(left.path, "utf8"), Buffer.from(right.path, "utf8")),
    );
    const syntheticInventoryText = payloadInventoryText(manifest.files);
    manifest.integrity = {
      manifest_in_file_inventory: false,
      payload_file_count: manifest.files.length,
      payload_index_sha256: createHash("sha256")
        .update(syntheticInventoryText, "utf8")
        .digest("hex"),
    };
    await writeFile(
      path.join(authorityRoot, "release-manifest.json"),
      `${JSON.stringify(manifest, null, 2)}\n`,
      { encoding: "utf8", flag: "wx" },
    );
    const versionFromDisk = (
      await readFile(path.join(authorityRoot, "VERSION"), "utf8")
    ).trim();
    const manifestFromDisk = JSON.parse(
      await readFile(path.join(authorityRoot, "release-manifest.json"), "utf8"),
    );
    const current = deriveReleaseIdentity(versionFromDisk, manifestFromDisk);
    const futureReleaseLabel = "beta7.8.9";
    const future = deriveReleaseIdentity(futureReleaseLabel, {
      artifact_name: `decretum-matrix-${futureReleaseLabel}.zip`,
      attestation_name: `decretum-matrix-${futureReleaseLabel}.release-attestation.json`,
      channel: "beta",
      expected_final_tag: `refs/tags/${futureReleaseLabel}`,
      release_label: futureReleaseLabel,
      sidecar_name: `decretum-matrix-${futureReleaseLabel}.zip.sha256`,
      version_core: "7.8.9",
    });
    assert(
      current.packageVersion === `${fixtureVersionCore}-beta.0` &&
        current.tarballName ===
          `rowlandl-decretum-matrix-${fixtureVersionCore}-beta.0.tgz`,
      "synthetic fixture identity derivation failed",
    );
    assert(
      future.packageVersion === "7.8.9-beta.0" &&
        future.tagRef === `refs/tags/${futureReleaseLabel}`,
      "future-generic identity derivation failed",
    );

    const gitEnvironment = {
      ...process.env,
      GIT_AUTHOR_DATE: "2000-01-01T00:00:00Z",
      GIT_COMMITTER_DATE: "2000-01-01T00:00:00Z",
    };
    for (const args of [
      ["init", "-q"],
      ["config", "user.name", "Decretum Synthetic"],
      ["config", "user.email", "synthetic@example.invalid"],
      ["config", "core.autocrlf", "false"],
      ["remote", "add", "origin", "git@github.com:RowlandL/decretum-matrix.git"],
      ["add", "."],
      ["commit", "-q", "-m", "synthetic release authority"],
      ["tag", "-a", releaseLabel, "-m", `synthetic ${releaseLabel}`],
    ]) {
      const result = runFixtureCommand("git", args, {
        cwd: authorityRoot,
        env: gitEnvironment,
      });
      assert(result.status === 0, `synthetic git ${args[0]} failed: ${result.stderr}`);
    }
    const syntheticHead = runFixtureCommand("git", ["rev-parse", "HEAD"], {
      cwd: authorityRoot,
    }).stdout.trim();
    const syntheticTree = runFixtureCommand(
      "git",
      ["rev-parse", "HEAD^{tree}"],
      { cwd: authorityRoot },
    ).stdout.trim();
    const syntheticTagCommit = runFixtureCommand(
      "git",
      ["rev-parse", `${releaseLabel}^{}`],
      { cwd: authorityRoot },
    ).stdout.trim();
    assert(
      syntheticTagCommit === syntheticHead,
      "synthetic annotated tag does not point to synthetic HEAD",
    );

    for (const remote of [
      "https://github.com/RowlandL/decretum-matrix.git",
      "ssh://github.com/RowlandL/decretum-matrix.git",
      "git@github.com:RowlandL/decretum-matrix.git",
    ]) {
      const normalized = normalizeRepositoryRemote(remote);
      assert(
        normalized.owner === "RowlandL" &&
          normalized.repository === "decretum-matrix" &&
          normalized.canonicalUrl ===
            "https://github.com/RowlandL/decretum-matrix.git",
        `synthetic repository remote normalization failed: ${remote}`,
      );
    }
    let originUserinfoRejected = true;
    let originUserinfoRedacted = true;
    for (const remote of [
      "https://sensitive-user:sensitive-pass@github.com/RowlandL/decretum-matrix.git",
      "ssh://sensitive-user@github.com/RowlandL/decretum-matrix.git",
    ]) {
      try {
        normalizeRepositoryRemote(remote);
        originUserinfoRejected = false;
      } catch (error) {
        if (String(error?.message || error).includes("sensitive-")) {
          originUserinfoRedacted = false;
        }
      }
    }
    assert(originUserinfoRejected, "origin URL userinfo was not rejected");
    assert(originUserinfoRedacted, "origin URL userinfo leaked through an error");
    let wrongOriginRejected = false;
    const wrongOrigin = runFixtureCommand(
      "git",
      [
        "remote",
        "set-url",
        "origin",
        "https://github.com/Other/decretum-matrix.git",
      ],
      { cwd: authorityRoot },
    );
    assert(wrongOrigin.status === 0, `cannot set wrong synthetic origin: ${wrongOrigin.stderr}`);
    try {
      loadRepositoryOracle(authorityRoot, manifestFromDisk);
    } catch {
      wrongOriginRejected = true;
    }
    const restoredOrigin = runFixtureCommand(
      "git",
      [
        "remote",
        "set-url",
        "origin",
        "git@github.com:RowlandL/decretum-matrix.git",
      ],
      { cwd: authorityRoot },
    );
    assert(
      restoredOrigin.status === 0,
      `cannot restore synthetic origin: ${restoredOrigin.stderr}`,
    );
    assert(wrongOriginRejected, "wrong repository origin was not rejected");
    const fixtureRepository = loadRepositoryOracle(
      authorityRoot,
      manifestFromDisk,
    );
    assert(
      !("input" in fixtureRepository),
      "repository oracle retained the raw origin URL",
    );

    const trackedAuthorityEvidence = await validateTrackedProductionAuthority(
      authorityRoot,
      releaseLabel,
    );
    const fixtureLockPath = path.join(authorityRoot, "package-lock.json");
    const fixtureLockBytes = await readFile(fixtureLockPath);
    await writeFile(
      fixtureLockPath,
      Buffer.concat([fixtureLockBytes, Buffer.from(" ", "utf8")]),
    );
    let dirtyAuthorityRejected = false;
    try {
      await validateTrackedProductionAuthority(authorityRoot, releaseLabel);
    } catch {
      dirtyAuthorityRejected = true;
    } finally {
      await writeFile(fixtureLockPath, fixtureLockBytes);
    }
    assert(dirtyAuthorityRejected, "dirty tracked authority was not rejected");
    const restoredTrackedStatus = runFixtureCommand(
      "git",
      ["status", "--porcelain=v1", "--untracked-files=no"],
      { cwd: authorityRoot },
    );
    assert(
      restoredTrackedStatus.status === 0 &&
        restoredTrackedStatus.stdout.trim() === "",
      "synthetic tracked authority was not restored after dirty negative",
    );
    const annotatedTagEvidence = validateAnnotatedReleaseTag(
      authorityRoot,
      releaseLabel,
      syntheticHead,
    );

    const tagNegativeRoot = path.join(root, "tag-negatives");
    await mkdir(tagNegativeRoot, { recursive: false });
    for (const args of [
      ["init", "-q"],
      ["config", "user.name", "Decretum Synthetic"],
      ["config", "user.email", "synthetic@example.invalid"],
      ["config", "core.autocrlf", "false"],
    ]) {
      const result = runFixtureCommand("git", args, {
        cwd: tagNegativeRoot,
        env: gitEnvironment,
      });
      assert(result.status === 0, `tag-negative git ${args[0]} failed: ${result.stderr}`);
    }
    await writeFile(path.join(tagNegativeRoot, "marker.txt"), "first\n", {
      encoding: "utf8",
      flag: "wx",
    });
    for (const args of [
      ["add", "marker.txt"],
      ["commit", "-q", "-m", "first synthetic tag target"],
    ]) {
      const result = runFixtureCommand("git", args, {
        cwd: tagNegativeRoot,
        env: gitEnvironment,
      });
      assert(result.status === 0, `tag-negative git ${args[0]} failed: ${result.stderr}`);
    }
    const firstTagTarget = runFixtureCommand("git", ["rev-parse", "HEAD"], {
      cwd: tagNegativeRoot,
    }).stdout.trim();
    let annotatedTagMissingRejected = false;
    try {
      validateAnnotatedReleaseTag(tagNegativeRoot, releaseLabel, firstTagTarget);
    } catch {
      annotatedTagMissingRejected = true;
    }
    assert(annotatedTagMissingRejected, "missing annotated release tag was not rejected");
    const lightweightTag = runFixtureCommand(
      "git",
      ["tag", releaseLabel],
      { cwd: tagNegativeRoot, env: gitEnvironment },
    );
    assert(lightweightTag.status === 0, `lightweight tag setup failed: ${lightweightTag.stderr}`);
    let lightweightTagRejected = false;
    try {
      validateAnnotatedReleaseTag(tagNegativeRoot, releaseLabel, firstTagTarget);
    } catch {
      lightweightTagRejected = true;
    }
    assert(lightweightTagRejected, "lightweight release tag was not rejected");
    for (const args of [
      ["tag", "-d", releaseLabel],
      ["tag", "-a", releaseLabel, "-m", `old target ${releaseLabel}`],
    ]) {
      const result = runFixtureCommand("git", args, {
        cwd: tagNegativeRoot,
        env: gitEnvironment,
      });
      assert(result.status === 0, `tag-negative git ${args[0]} failed: ${result.stderr}`);
    }
    await writeFile(path.join(tagNegativeRoot, "marker.txt"), "second\n", {
      encoding: "utf8",
    });
    for (const args of [
      ["add", "marker.txt"],
      ["commit", "-q", "-m", "second synthetic tag target"],
    ]) {
      const result = runFixtureCommand("git", args, {
        cwd: tagNegativeRoot,
        env: gitEnvironment,
      });
      assert(result.status === 0, `tag-negative git ${args[0]} failed: ${result.stderr}`);
    }
    const secondTagTarget = runFixtureCommand("git", ["rev-parse", "HEAD"], {
      cwd: tagNegativeRoot,
    }).stdout.trim();
    assert(firstTagTarget !== secondTagTarget, "wrong-target tag fixture did not advance HEAD");
    let wrongTargetTagRejected = false;
    try {
      validateAnnotatedReleaseTag(tagNegativeRoot, releaseLabel, secondTagTarget);
    } catch {
      wrongTargetTagRejected = true;
    }
    assert(wrongTargetTagRejected, "wrong-target annotated tag was not rejected");

    const fixtureAssetTemplates = Object.freeze(
      [
        "SBOM.spdx.json",
        current.attestationName,
        current.releaseNotesName,
        current.artifactName,
        current.sidecarName,
      ].map((name) => Object.freeze({ name, path: `release/${name}` })),
    );
    const fixtureContract = createPackageContract({
      identity: current,
      packageName: "@rowlandl/decretum-matrix",
      distTag: "beta",
      registry: "https://npm.pkg.github.com",
      license: "AGPL-3.0-only",
      repository: fixtureRepository,
      repoRoot: authorityRoot,
      releaseAssetDir: assetRoot,
      sourceCommit: syntheticHead,
      sourceTree: syntheticTree,
      releaseManifestSha256: await hashFile(
        path.join(authorityRoot, "release-manifest.json"),
      ),
      legalFiles: fixtureLegalFiles,
      releaseAssets: fixtureAssetTemplates,
      outputRelative: `synthetic/npm/${current.packageVersion}-legal-v2`,
      authorityReceiptId: `npm-${releaseLabel}-${syntheticHead.slice(0, 8)}-legal-v2`,
      authorityCursor: `${releaseLabel.toUpperCase()}_NPM_LOCAL_CANDIDATE`,
    });

    const zipMembers = [
      "VERSION",
      "release-manifest.json",
      "SBOM.spdx.json",
      ...fixtureLegalFiles.map((file) => file.path),
    ].sort();
    const zipPath = path.join(assetRoot, current.artifactName);
    const zipCreate = runPythonFixtureCommand(
      [
        "-c",
        SYNTHETIC_ZIP_SCRIPT,
        authorityRoot,
        zipPath,
        JSON.stringify(zipMembers),
      ],
      { cwd: root },
    );
    assert(zipCreate.status === 0, `synthetic ZIP creation failed: ${zipCreate.stderr}`);
    const zipHash = await hashFile(zipPath);
    await writeFile(
      path.join(assetRoot, current.sidecarName),
      `${zipHash}  ${current.artifactName}\n`,
      { encoding: "utf8", flag: "wx" },
    );
    await writeFile(
      path.join(assetRoot, current.releaseNotesName),
      `# Synthetic release notes\n\n## ${releaseLabel}\n`,
      { encoding: "utf8", flag: "wx" },
    );
    await copyFile(
      path.join(authorityRoot, "SBOM.spdx.json"),
      path.join(assetRoot, "SBOM.spdx.json"),
      fsConstants.COPYFILE_EXCL,
    );
    const attestedNames = [
      current.artifactName,
      current.sidecarName,
      current.releaseNotesName,
      "SBOM.spdx.json",
    ];
    const attestedArtifacts = [];
    for (const name of attestedNames) {
      const filePath = path.join(assetRoot, name);
      attestedArtifacts.push({
        name,
        sha256: await hashFile(filePath),
        size: (await stat(filePath)).size,
      });
    }
    const attestation = {
      schema: "court.release_attestation.v1",
      release_label: releaseLabel,
      license: LICENSE,
      source: {
        head_commit: syntheticHead,
        tag_commit: syntheticTagCommit,
        tree: syntheticTree,
        tag_ref: current.tagRef,
      },
      release_manifest: {
        path: "release-manifest.json",
        sha256: await hashFile(path.join(authorityRoot, "release-manifest.json")),
      },
      artifacts: attestedArtifacts,
    };
    await writeFile(
      path.join(assetRoot, current.attestationName),
      jsonText(attestation),
      { encoding: "utf8", flag: "wx" },
    );
    assert(
      attestation.source.head_commit === attestation.source.tag_commit &&
        attestation.source.tree === syntheticTree &&
        attestation.source.tag_ref === current.tagRef,
      "synthetic attestation HEAD/tag/tree relation mismatch",
    );

    const canonicalChecker = path.join(REPO_ROOT, "scripts", "check_package_privacy.py");
    const canonicalPrivacy = runPythonFixtureCommand(
      [canonicalChecker, "-q"],
      {
        cwd: REPO_ROOT,
        env: { ...process.env, COURT_PACKAGE_STAGE_VALIDATION: "1" },
      },
    );
    assert(
      canonicalPrivacy.status === 0,
      `canonical privacy fixture failed: ${canonicalPrivacy.stdout}${canonicalPrivacy.stderr}`,
    );
    const zipPrivacy = runPythonFixtureCommand(
      [
        "-c",
        ZIP_PRIVACY_SCRIPT,
        zipPath,
        REPO_ROOT,
        releaseLabel,
        path.join(authorityRoot, "release-manifest.json"),
      ],
      { cwd: root },
    );
    assert(
      zipPrivacy.status === 0,
      `synthetic ZIP privacy failed: ${zipPrivacy.stdout}${zipPrivacy.stderr}`,
    );
    const zipPrivacyEvidence = JSON.parse(zipPrivacy.stdout.trim());
    assert(zipPrivacyEvidence.ok === true, "synthetic ZIP privacy did not report ok");

    const tamperedRoot = path.join(root, "inventory-tampered-release-assets");
    await mkdir(tamperedRoot, { recursive: false });
    const tamperedZipPath = path.join(tamperedRoot, current.artifactName);
    const tamperResult = runPythonFixtureCommand(
      [
        "-c",
        TAMPER_ZIP_SCRIPT,
        zipPath,
        tamperedZipPath,
        "court-capability-router/NOTICE",
      ],
      { cwd: root },
    );
    assert(tamperResult.status === 0, `synthetic ZIP tamper failed: ${tamperResult.stderr}`);
    const tamperedZipHash = await hashFile(tamperedZipPath);
    assert(tamperedZipHash !== zipHash, "inventory tamper did not change ZIP hash");
    const tamperedSidecar = Buffer.from(
      `${tamperedZipHash}  ${current.artifactName}\n`,
      "utf8",
    );
    await writeFile(
      path.join(tamperedRoot, current.sidecarName),
      tamperedSidecar,
      { flag: "wx", mode: 0o644 },
    );
    const tamperedAttestation = structuredClone(attestation);
    const tamperedZipDescriptor = tamperedAttestation.artifacts.find(
      (artifact) => artifact.name === current.artifactName,
    );
    const tamperedSidecarDescriptor = tamperedAttestation.artifacts.find(
      (artifact) => artifact.name === current.sidecarName,
    );
    assert(
      tamperedZipDescriptor && tamperedSidecarDescriptor,
      "synthetic attestation lacks ZIP/sidecar descriptors",
    );
    tamperedZipDescriptor.sha256 = tamperedZipHash;
    tamperedZipDescriptor.size = (await stat(tamperedZipPath)).size;
    const tamperedSidecarHash = createHash("sha256")
      .update(tamperedSidecar)
      .digest("hex");
    tamperedSidecarDescriptor.sha256 = tamperedSidecarHash;
    tamperedSidecarDescriptor.size = tamperedSidecar.length;
    await writeFile(
      path.join(tamperedRoot, current.attestationName),
      jsonText(tamperedAttestation),
      { encoding: "utf8", flag: "wx", mode: 0o644 },
    );
    assert(
      tamperedSidecar.toString("utf8") ===
        `${tamperedZipHash}  ${current.artifactName}\n` &&
        tamperedZipDescriptor.sha256 === tamperedZipHash &&
        tamperedSidecarDescriptor.sha256 === tamperedSidecarHash &&
        tamperedSidecarDescriptor.size === tamperedSidecar.length,
      "tampered sidecar/attestation were not synchronized",
    );
    const inventoryTamperCheck = runPythonFixtureCommand(
      [
        "-c",
        ZIP_PRIVACY_SCRIPT,
        tamperedZipPath,
        REPO_ROOT,
        releaseLabel,
        path.join(authorityRoot, "release-manifest.json"),
      ],
      { cwd: root },
    );
    assert(
      inventoryTamperCheck.status === 2,
      `inventory-tampered ZIP did not fail closed: ${inventoryTamperCheck.stdout}${inventoryTamperCheck.stderr}`,
    );
    const inventoryTamperEvidence = JSON.parse(
      inventoryTamperCheck.stdout.trim(),
    );
    assert(
      inventoryTamperEvidence.ok === false &&
        inventoryTamperEvidence.problems.some((problem) =>
          problem.includes("NOTICE:sha256-mismatch"),
        ),
      "inventory-tampered ZIP did not report the accepted-manifest hash mismatch",
    );

    const packageRoot = path.join(root, "package");
    await mkdir(packageRoot, { recursive: false });
    const syntheticAssets = [];
    for (const asset of fixtureContract.releaseAssets) {
      const sourcePath = path.join(assetRoot, asset.name);
      const descriptor = {
        name: asset.name,
        path: asset.path,
        sha256: await hashFile(sourcePath),
        size: (await stat(sourcePath)).size,
      };
      syntheticAssets.push(descriptor);
    }
    const { packageText, publishPackage, readmeText } = await stagePackage(
      packageRoot,
      fixtureContract,
      syntheticAssets,
    );
    const expectedHashes = new Map([
      ...fixtureContract.legalFiles.map((file) => [file.path, file.sha256]),
      ...syntheticAssets.map((asset) => [asset.path, asset.sha256]),
    ]);
    const expectedFiles = fixtureContract.expectedPackFiles;
    const expectedUnpackedSize =
      Buffer.byteLength(packageText, "utf8") +
      Buffer.byteLength(readmeText, "utf8") +
      fixtureContract.legalFiles.reduce((total, file) => total + file.size, 0) +
      syntheticAssets.reduce((total, asset) => total + asset.size, 0);
    const npmState = await prepareNpmState(root);
    const dryRun = await npmPackDryRun(
      packageRoot,
      npmState,
      expectedUnpackedSize,
      fixtureContract,
    );
    const firstPack = await npmPackOnce(
      packageRoot,
      path.join(root, "pack-a"),
      npmState,
      expectedUnpackedSize,
      fixtureContract,
    );
    const secondPack = await npmPackOnce(
      packageRoot,
      path.join(root, "pack-b"),
      npmState,
      expectedUnpackedSize,
      fixtureContract,
    );
    assert(
      firstPack.sha256 === secondPack.sha256 && firstPack.size === secondPack.size,
      "synthetic npm pack is not deterministic",
    );
    await runSyntheticInstalledSmoke(
      root,
      firstPack.tarballPath,
      npmState,
      publishPackage,
      expectedFiles,
      expectedHashes,
      fixtureContract,
    );

    const syntheticPrivacyEvidence = {
      canonical: {
        command:
          "COURT_PACKAGE_STAGE_VALIDATION=1 $PYTHON -B scripts/check_package_privacy.py -q",
        rc: canonicalPrivacy.status,
        checker_sha256: await hashFile(canonicalChecker),
      },
      release_zip: {
        command: "$PYTHON -B -c <nested-zip-member-privacy-checker> <zip>",
        rc: zipPrivacy.status,
        checker_sha256: createHash("sha256")
          .update(ZIP_PRIVACY_SCRIPT, "utf8")
          .digest("hex"),
        zip_sha256: zipHash,
        ...zipPrivacyEvidence,
      },
    };
    const syntheticVerified = {
      authorityEvidence: trackedAuthorityEvidence,
      firstPack,
      privacyEvidence: syntheticPrivacyEvidence,
      releaseAssets: syntheticAssets,
      repositoryEvidence: fixtureRepository,
      smokeStatus: "PASS",
      tagEvidence: annotatedTagEvidence,
    };
    const outputRoot = path.join(root, "output");
    const created = await materializeVerifiedPackage(
      syntheticVerified,
      outputRoot,
      fixtureContract,
    );
    const beforeReuse = await snapshotOutputDirectory(outputRoot);
    const reused = await materializeVerifiedPackage(
      syntheticVerified,
      outputRoot,
      fixtureContract,
    );
    const afterReuse = await snapshotOutputDirectory(outputRoot);
    assert(
      created.materialization === "CREATED" &&
        reused.materialization === "REUSED",
      "production output create/reuse contract failed",
    );
    assertDeepEqual(
      afterReuse,
      beforeReuse,
      "production output identical reuse bytes/mtime",
    );
    assert(
      publishPackage.repository === fixtureRepository.canonicalUrl &&
        created.receipt.source.repository === fixtureRepository.canonicalUrl &&
        created.receipt.authority.repository_oracle.canonicalUrl ===
          fixtureRepository.canonicalUrl,
      "synthetic package/receipt repository provenance disagreement",
    );
    const collisionRoot = path.join(root, "collision-output");
    await mkdir(collisionRoot, { recursive: false });
    for (const [name, body] of created.files) {
      const collisionBody =
        name === fixtureContract.receiptName
          ? Buffer.concat([body.subarray(0, Math.max(body.length - 1, 0)), Buffer.from(" ")])
          : body;
      await writeFile(path.join(collisionRoot, name), collisionBody, {
        flag: "wx",
        mode: 0o644,
      });
    }
    const beforeCollision = await snapshotOutputDirectory(collisionRoot);
    let collisionRejected = false;
    try {
      await materializeVerifiedPackage(
        syntheticVerified,
        collisionRoot,
        fixtureContract,
      );
    } catch (error) {
      collisionRejected = error?.code === "COLLISION_BLOCKED";
    }
    const afterCollision = await snapshotOutputDirectory(collisionRoot);
    assert(collisionRejected, "production output collision was not blocked");
    assertDeepEqual(
      afterCollision,
      beforeCollision,
      "production output collision preservation",
    );

    let staleFallbackRejected = false;
    try {
      const staleLabel = "beta1.2.2";
      deriveReleaseIdentity(releaseLabel, {
        ...manifestFromDisk,
        artifact_name: `decretum-matrix-${staleLabel}.zip`,
      });
    } catch {
      staleFallbackRejected = true;
    }
    assert(staleFallbackRejected, "stale release fallback was not rejected");

    return {
      schema: "decretum.npm_self_test.v3",
      status: "PASS",
      synthetic_release: current,
      future_generic: future,
      package: {
        name: fixtureContract.packageName,
        version: fixtureContract.packageVersion,
        filename: fixtureContract.tarballName,
        sha256: firstPack.sha256,
        size: firstPack.size,
      },
      evidence: {
        python_invocation: pythonInvocationContract(),
        repository_oracle: {
          command: fixtureRepository.command,
          rc: fixtureRepository.rc,
          owner: fixtureRepository.owner,
          repository: fixtureRepository.repository,
          canonical_url: fixtureRepository.canonicalUrl,
          provenance_sha256: fixtureRepository.provenanceSha256,
          package_repository: publishPackage.repository,
          receipt_repository: created.receipt.source.repository,
        },
        tracked_authority: trackedAuthorityEvidence,
        annotated_tag: annotatedTagEvidence,
        negatives: {
          wrong_origin_rejected: wrongOriginRejected,
          dirty_authority_rejected: dirtyAuthorityRejected,
          annotated_tag_missing_rejected: annotatedTagMissingRejected,
          lightweight_tag_rejected: lightweightTagRejected,
          wrong_target_tag_rejected: wrongTargetTagRejected,
        },
        canonical_privacy: {
          command:
            "COURT_PACKAGE_STAGE_VALIDATION=1 $PYTHON -B scripts/check_package_privacy.py -q",
          rc: canonicalPrivacy.status,
          checker_sha256: await hashFile(canonicalChecker),
        },
        release_zip: {
          command: "$PYTHON -B -c <nested-zip-member-privacy-checker> <zip>",
          rc: zipPrivacy.status,
          checker_sha256: createHash("sha256")
            .update(ZIP_PRIVACY_SCRIPT, "utf8")
            .digest("hex"),
          zip_sha256: zipHash,
          member_count: zipPrivacyEvidence.member_count,
          payload_member_count: zipPrivacyEvidence.payload_member_count,
          accepted_manifest_sha256:
            zipPrivacyEvidence.accepted_manifest_sha256,
          manifest_member_sha256:
            zipPrivacyEvidence.manifest_member_sha256,
          manifest_inventory_count:
            zipPrivacyEvidence.manifest_inventory_count,
          manifest_inventory_sha256:
            zipPrivacyEvidence.manifest_inventory_sha256,
          payload_inventory_count:
            zipPrivacyEvidence.payload_inventory_count,
          payload_inventory_sha256:
            zipPrivacyEvidence.payload_inventory_sha256,
        },
        inventory_tamper_negative: {
          command:
            "$PYTHON -B -c <nested-zip-member-privacy-checker> <tampered-zip>",
          rc: inventoryTamperCheck.status,
          checker_sha256: createHash("sha256")
            .update(ZIP_PRIVACY_SCRIPT, "utf8")
            .digest("hex"),
          accepted_manifest_sha256:
            inventoryTamperEvidence.accepted_manifest_sha256,
          tampered_zip_sha256: tamperedZipHash,
          sidecar_recomputed: true,
          attestation_recomputed: true,
          problems: inventoryTamperEvidence.problems,
        },
        production_output: {
          helper: "materializeVerifiedPackage/createOrReuseOutput",
          create: created.materialization,
          reuse: reused.materialization,
          reuse_snapshot_before: beforeReuse,
          reuse_snapshot_after: afterReuse,
          collision_status: "COLLISION_BLOCKED",
          collision_snapshot_before: beforeCollision,
          collision_snapshot_after: afterCollision,
        },
        npm_pack: {
          dry_run_entry_count: dryRun.entryCount,
          first_sha256: firstPack.sha256,
          second_sha256: secondPack.sha256,
        },
      },
      validation: {
        canonical_privacy_fixture: "PASS",
        nested_zip_member_privacy: "PASS",
        deterministic_double_pack: "PASS",
        strict_offline_install: "PASS",
        bin_entry: "ABSENT_BY_CONTRACT",
        create_only: "PASS",
        identical_reuse: "PASS",
        collision_rejected: "PASS",
        stale_release_fallback_rejected: "PASS",
        manifest_inventory_exact_match: "PASS",
        inventory_tamper_rejected: "PASS",
        production_output_create: "PASS",
        production_output_reuse_no_mutation: "PASS",
        production_output_collision_preserved: "PASS",
        repository_origin_oracle: "PASS",
        origin_userinfo_rejected: "PASS",
        origin_userinfo_redacted: "PASS",
        receipt_canonical_origin_only: "PASS",
        python_interpreter_contract: "PASS",
        wrong_origin_rejected: "PASS",
        full_fixture_noncurrent_release: "PASS",
        tracked_authority_clean: "PASS",
        dirty_authority_rejected: "PASS",
        annotated_tag_missing_rejected: "PASS",
        lightweight_tag_rejected: "PASS",
        wrong_target_tag_rejected: "PASS",
        network_dependency: "NONE",
      },
      repository_output: "NOT_WRITTEN",
    };
  } finally {
    await rm(root, { force: true, recursive: true });
  }
}

const EXPECTED_PACK_FILES = Object.freeze([
  "package.json",
  "README.md",
  ...LEGAL_SOURCE_FILES.map((file) => file.path),
  ...RELEASE_ASSETS.map((asset) => asset.path),
].sort());

function fail(message) {
  throw new Error(message);
}

export class BlockedReleaseError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "BlockedReleaseError";
    this.code = code;
    this.details = details;
  }

  toJSON() {
    return {
      schema: "decretum.npm_current_check.v3",
      status: this.code,
      message: this.message,
      release_label: RELEASE_LABEL,
      package_version: PACKAGE_VERSION,
      ...this.details,
    };
  }
}

export class OutputCollisionError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "OutputCollisionError";
    this.code = "COLLISION_BLOCKED";
    this.details = details;
  }

  toJSON() {
    return {
      schema: "decretum.npm_output_collision.v1",
      status: this.code,
      message: this.message,
      output_directory: OUTPUT_DIR,
      ...this.details,
    };
  }
}

function assert(condition, message) {
  if (!condition) {
    fail(message);
  }
}

function assertDeepEqual(actual, expected, label) {
  if (!isDeepStrictEqual(actual, expected)) {
    fail(`${label} does not match the immutable npm package contract`);
  }
}

function normalizePackagePath(value) {
  return value.split(path.sep).join("/");
}

function isWithin(parent, child) {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  return (
    relative === "" ||
    (!relative.startsWith(`..${path.sep}`) &&
      relative !== ".." &&
      !path.isAbsolute(relative))
  );
}

async function pathExists(target) {
  try {
    await lstat(target);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

async function hashFile(filePath, algorithm = "sha256", encoding = "hex") {
  return await new Promise((resolve, reject) => {
    const hash = createHash(algorithm);
    const input = createReadStream(filePath);
    input.on("error", reject);
    input.on("data", (chunk) => hash.update(chunk));
    input.on("end", () => resolve(hash.digest(encoding)));
  });
}

function expectedPublishedPackageJson(contract = LIVE_PACKAGE_CONTRACT) {
  return {
    name: contract.packageName,
    version: contract.packageVersion,
    description: `Immutable Decretum Matrix ${contract.releaseLabel} release assets and provenance.`,
    license: contract.license,
    repository: contract.repositoryUrl,
    homepage: contract.releaseUrl,
    bugs: {
      url: `${contract.repositoryUrl.replace(/\.git$/, "")}/issues`,
    },
    keywords: ["codex", "decretum-matrix", "release-assets"],
    files: [
      "README.md",
      ...contract.legalFiles.map((file) => file.path),
      "release/",
    ],
    exports: {
      "./package.json": "./package.json",
      "./release/*": "./release/*",
    },
    publishConfig: {
      registry: contract.registry,
      tag: contract.distTag,
      access: "public",
    },
    gitHead: contract.sourceCommit,
    engines: {
      node: ">=18",
    },
    decretumMatrix: {
      schema: "decretum.npm_release.v2",
      candidate: "legal-v2",
      distTag: contract.distTag,
      releaseLabel: contract.releaseLabel,
      source: {
        commit: contract.sourceCommit,
        tree: contract.sourceTree,
        tag: contract.releaseLabel,
        tagRef: contract.tagRef,
      },
      release: {
        url: contract.releaseUrl,
        attestation: `release/${contract.identity.attestationName}`,
        sbom: "release/SBOM.spdx.json",
      },
      provenance: {
        kind: "immutable-github-release-assets",
        repository: contract.repositoryUrl,
        releaseUrl: contract.releaseUrl,
      },
      legalSurface: {
        revision: "legal-v2",
        sourceCommit: contract.sourceCommit,
        releaseManifestSha256: contract.releaseManifestSha256,
        files: contract.legalFiles.map(({ path: legalPath, sha256, size }) => ({
          path: legalPath,
          sha256,
          size,
        })),
      },
      assets: contract.releaseAssets.map(({ path: assetPath }) => ({
        path: assetPath,
      })),
    },
  };
}

function expectedHarnessPackageJson() {
  return {
    name: "decretum-matrix-npm-release-harness",
    version: "0.0.0-private",
    private: true,
    description:
      "Private version-neutral harness for building and checking Decretum Matrix npm release candidates.",
    license: LICENSE,
    type: "module",
    engines: {
      node: ">=18",
    },
    scripts: {
      build: "node scripts/build_npm_package.mjs",
      check: "node scripts/check_npm_package.mjs",
      test: "node scripts/check_npm_package.mjs --self-test",
    },
  };
}

function expectedHarnessPackageLock() {
  return {
    name: "decretum-matrix-npm-release-harness",
    version: "0.0.0-private",
    lockfileVersion: 3,
    requires: true,
    packages: {
      "": {
        name: "decretum-matrix-npm-release-harness",
        version: "0.0.0-private",
        license: LICENSE,
        engines: {
          node: ">=18",
        },
      },
    },
  };
}

function jsonText(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

async function readJson(filePath, label) {
  let value;
  try {
    value = JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    fail(`${label} is not valid JSON: ${error.message}`);
  }
  return value;
}

function assertSafePaths() {
  assert(
    isWithin(WORKSPACE_ROOT, RELEASE_ASSET_DIR),
    "release asset directory escapes the workspace root",
  );
  assert(
    isWithin(WORKSPACE_ROOT, OUTPUT_DIR),
    "npm output directory escapes the workspace root",
  );
  assert(
    !isWithin(REPO_ROOT, RELEASE_ASSET_DIR),
    "release assets must be read outside the repository",
  );
  assert(
    !isWithin(REPO_ROOT, OUTPUT_DIR),
    "npm outputs must be written outside the repository",
  );
}

export async function validateSourcePackageJson() {
  const packagePath = path.join(REPO_ROOT, "package.json");
  const packageStat = await lstat(packagePath);
  assert(packageStat.isFile(), "package.json must be a regular file");
  const actual = await readJson(packagePath, "package.json");
  const expected = expectedHarnessPackageJson();
  assertDeepEqual(actual, expected, "package.json");
  const lockPath = path.join(REPO_ROOT, "package-lock.json");
  const lockStat = await lstat(lockPath);
  assert(lockStat.isFile(), "package-lock.json must be a regular file");
  const actualLock = await readJson(lockPath, "package-lock.json");
  assertDeepEqual(actualLock, expectedHarnessPackageLock(), "package-lock.json");
  return { packageJson: actual, packageLock: actualLock };
}

function scanTextForSecrets(text, label) {
  const forbidden = [
    [
      /-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----/i,
      "private key",
    ],
    [/\bghp_[A-Za-z0-9]{20,}\b/, "GitHub personal access token"],
    [/\bgithub_pat_[A-Za-z0-9_]{20,}\b/, "GitHub fine-grained token"],
    [/\/\/[A-Za-z0-9._/-]+\/:_authToken\s*=/i, "npm auth token config"],
  ];

  for (const [pattern, description] of forbidden) {
    if (pattern.test(text)) {
      fail(`${label} contains a forbidden ${description}`);
    }
  }
}

function assertSafePackPaths(paths) {
  const forbidden = [
    /(^|\/)\.npmrc$/i,
    /(^|\/)\.env(?:\.[^/]*)?$/i,
    /(^|\/)(?:pending|private)(?:\/|$)/i,
    /(^|\/)[^/]*\.(?:log|trace)$/i,
    /(^|\/)[^/]*(?:credential|token)[^/]*$/i,
  ];

  for (const packagePath of paths) {
    for (const pattern of forbidden) {
      if (pattern.test(packagePath)) {
        fail(`forbidden package path: ${packagePath}`);
      }
    }
  }
}

function validateAttestation(attestation, releaseAssets) {
  assert(
    attestation.schema === "court.release_attestation.v1",
    "release attestation schema mismatch",
  );
  assert(attestation.license === LICENSE, "release attestation license mismatch");
  assert(
    attestation.release_label === RELEASE_LABEL,
    "release attestation label mismatch",
  );
  assert(
    attestation.source?.head_commit === SOURCE_COMMIT &&
      attestation.source?.tag_commit === SOURCE_COMMIT &&
      attestation.source?.tree === SOURCE_TREE &&
      attestation.source?.tag_ref === TAG_REF,
    "release attestation source provenance mismatch",
  );
  assert(
    attestation.release_manifest?.sha256 === RELEASE_MANIFEST_SHA256,
    "release attestation manifest hash mismatch",
  );
  assert(
    attestation.build_contract?.deterministic_zip === true &&
      attestation.build_contract?.exclusive_asset_create === true &&
      attestation.build_contract?.exclusive_final_directory === true &&
      attestation.build_contract?.no_clobber === true,
    "release attestation build contract mismatch",
  );

  const expectedArtifacts = releaseAssets
    .filter((asset) => asset.name !== LIVE_IDENTITY.attestationName)
    .map(({ name, sha256, size }) => ({ name, sha256, size }))
    .sort((left, right) => left.name.localeCompare(right.name));
  const actualArtifacts = [...(attestation.artifacts || [])]
    .map(({ name, sha256, size }) => ({ name, sha256, size }))
    .sort((left, right) => left.name.localeCompare(right.name));
  assertDeepEqual(
    actualArtifacts,
    expectedArtifacts,
    "release attestation artifact list",
  );
}

function validateSbom(sbom) {
  assert(sbom.spdxVersion === "SPDX-2.3", "SBOM SPDX version mismatch");
  assert(
    sbom.name === `decretum-matrix-${RELEASE_LABEL}`,
    "SBOM name mismatch",
  );
  assert(
    Array.isArray(sbom.packages) && sbom.packages.length === 1,
    "SBOM package list mismatch",
  );
  const packageEntry = sbom.packages[0];
  assert(packageEntry.name === "decretum-matrix", "SBOM package name mismatch");
  assert(
    packageEntry.versionInfo === RELEASE_LABEL,
    "SBOM package version mismatch",
  );
  assert(
    packageEntry.licenseDeclared === LICENSE,
    "SBOM declared license mismatch",
  );
}

export async function validateReleaseAssets() {
  assertSafePaths();
  let entries;
  try {
    entries = await readdir(RELEASE_ASSET_DIR, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new BlockedReleaseError(
        "BLOCKED_CURRENT_RELEASE_ASSETS_MISSING",
        "current release asset directory is absent; stale release fallback is forbidden",
        {
          asset_directory: RELEASE_ASSET_DIR,
          missing_assets: RELEASE_ASSETS.map((asset) => asset.name).sort(),
          stale_release_fallback: "FORBIDDEN",
        },
      );
    }
    throw error;
  }
  const actualNames = entries.map((entry) => entry.name).sort();
  const expectedNames = RELEASE_ASSETS.map((asset) => asset.name).sort();
  const missingAssets = expectedNames.filter((name) => !actualNames.includes(name));
  if (missingAssets.length > 0) {
    throw new BlockedReleaseError(
      "BLOCKED_CURRENT_RELEASE_ASSETS_MISSING",
      "current release assets are incomplete; stale release fallback is forbidden",
      {
        asset_directory: RELEASE_ASSET_DIR,
        missing_assets: missingAssets,
        stale_release_fallback: "FORBIDDEN",
      },
    );
  }
  assertDeepEqual(actualNames, expectedNames, "release asset directory allowlist");

  for (const entry of entries) {
    assert(entry.isFile(), `release asset is not a regular file: ${entry.name}`);
  }

  const trackedAuthority = await validateTrackedProductionAuthority(
    REPO_ROOT,
    RELEASE_LABEL,
  );
  let tagEvidence;
  try {
    tagEvidence = validateAnnotatedReleaseTag(
      REPO_ROOT,
      RELEASE_LABEL,
      SOURCE_COMMIT,
    );
  } catch (error) {
    if (error.message.includes("annotated release tag is missing")) {
      throw new BlockedReleaseError(
        "BLOCKED_CURRENT_RELEASE_TAG_MISSING",
        "current release tag is absent; assets cannot be accepted without HEAD/tag binding",
        {
          expected_tag_ref: TAG_REF,
          source_commit: SOURCE_COMMIT,
        },
      );
    }
    throw error;
  }

  const validatedAssets = [];
  for (const asset of RELEASE_ASSETS) {
    const sourcePath = path.join(RELEASE_ASSET_DIR, asset.name);
    const sourceStat = await lstat(sourcePath);
    assert(sourceStat.isFile(), `release asset is not a regular file: ${asset.name}`);
    const digest = await hashFile(sourcePath);
    validatedAssets.push(
      Object.freeze({
        ...asset,
        sha256: digest,
        size: sourceStat.size,
      }),
    );

    if (!asset.name.endsWith(".zip")) {
      scanTextForSecrets(await readFile(sourcePath, "utf8"), asset.name);
    }
  }

  const attestation = await readJson(
    path.join(RELEASE_ASSET_DIR, LIVE_IDENTITY.attestationName),
    "release attestation",
  );
  validateAttestation(attestation, validatedAssets);

  const sbom = await readJson(
    path.join(RELEASE_ASSET_DIR, "SBOM.spdx.json"),
    "release SBOM",
  );
  validateSbom(sbom);

  const sidecar = await readFile(
    path.join(RELEASE_ASSET_DIR, LIVE_IDENTITY.sidecarName),
    "utf8",
  );
  const releaseZip = validatedAssets.find(
    (asset) => asset.name === LIVE_IDENTITY.artifactName,
  );
  assert(releaseZip, "release ZIP descriptor missing");
  assert(
    sidecar === `${releaseZip.sha256}  ${LIVE_IDENTITY.artifactName}\n`,
    "release ZIP sidecar content mismatch",
  );

  const releaseNotes = await readFile(
    path.join(RELEASE_ASSET_DIR, LIVE_IDENTITY.releaseNotesName),
    "utf8",
  );
  assert(
    releaseNotes.includes(`## ${RELEASE_LABEL}`),
    `release notes do not identify ${RELEASE_LABEL}`,
  );

  const canonicalChecker = path.join(
    REPO_ROOT,
    "scripts",
    "check_package_privacy.py",
  );
  const canonicalPrivacy = runPythonFixtureCommand(
    [canonicalChecker, "-q"],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, COURT_PACKAGE_STAGE_VALIDATION: "1" },
    },
  );
  assert(
    canonicalPrivacy.status === 0,
    `canonical privacy fixture failed: ${canonicalPrivacy.stdout}${canonicalPrivacy.stderr}`,
  );
  const zipPrivacy = runPythonFixtureCommand(
    [
      "-c",
      ZIP_PRIVACY_SCRIPT,
      path.join(RELEASE_ASSET_DIR, LIVE_IDENTITY.artifactName),
      REPO_ROOT,
      RELEASE_LABEL,
      path.join(REPO_ROOT, "release-manifest.json"),
    ],
    { cwd: REPO_ROOT },
  );
  assert(
    zipPrivacy.status === 0,
    `release ZIP privacy failed: ${zipPrivacy.stdout}${zipPrivacy.stderr}`,
  );
  const zipPrivacyEvidence = JSON.parse(zipPrivacy.stdout.trim());
  assert(zipPrivacyEvidence.ok === true, "release ZIP privacy did not report ok");

  assertSafePackPaths(EXPECTED_PACK_FILES);
  return Object.freeze({
    assets: Object.freeze(validatedAssets),
    authority: trackedAuthority,
    privacy: Object.freeze({
      canonical: Object.freeze({
        command:
          "COURT_PACKAGE_STAGE_VALIDATION=1 $PYTHON -B scripts/check_package_privacy.py -q",
        rc: canonicalPrivacy.status,
        checker_sha256: await hashFile(canonicalChecker),
      }),
      release_zip: Object.freeze({
        command: "$PYTHON -B -c <nested-zip-member-privacy-checker> <zip>",
        rc: zipPrivacy.status,
        checker_sha256: createHash("sha256")
          .update(ZIP_PRIVACY_SCRIPT, "utf8")
          .digest("hex"),
        zip_sha256: releaseZip.sha256,
        member_count: zipPrivacyEvidence.member_count,
        payload_member_count: zipPrivacyEvidence.payload_member_count,
        accepted_manifest_sha256:
          zipPrivacyEvidence.accepted_manifest_sha256,
        manifest_member_sha256:
          zipPrivacyEvidence.manifest_member_sha256,
        manifest_inventory_count:
          zipPrivacyEvidence.manifest_inventory_count,
        manifest_inventory_sha256:
          zipPrivacyEvidence.manifest_inventory_sha256,
        payload_inventory_count:
          zipPrivacyEvidence.payload_inventory_count,
        payload_inventory_sha256:
          zipPrivacyEvidence.payload_inventory_sha256,
      }),
    }),
    repository: LIVE_REPOSITORY,
    tag: tagEvidence,
  });
}

function loadSourceReleaseManifest() {
  const result = spawnSync(
    "git",
    ["show", `${SOURCE_COMMIT}:release-manifest.json`],
    {
      cwd: REPO_ROOT,
      encoding: null,
      maxBuffer: 16 * 1024 * 1024,
      shell: false,
      timeout: 30_000,
      windowsHide: true,
    },
  );
  if (result.error) {
    fail(`cannot read the HEAD release manifest: ${result.error.message}`);
  }
  if (result.status !== 0) {
    fail(
      `cannot read the HEAD release manifest: ${result.stderr?.toString("utf8").trim() || `git exit ${result.status}`}`,
    );
  }

  const manifestBytes = result.stdout;
  const manifestHash = createHash("sha256").update(manifestBytes).digest("hex");
  assert(
    manifestHash === RELEASE_MANIFEST_SHA256,
    "HEAD release manifest hash mismatch",
  );

  let manifest;
  try {
    manifest = JSON.parse(manifestBytes.toString("utf8"));
  } catch (error) {
    fail(`HEAD release manifest is not valid JSON: ${error.message}`);
  }
  return manifest;
}

export async function validateLegalSourceFiles() {
  const manifest = loadSourceReleaseManifest();
  assert(
    manifest.release_label === RELEASE_LABEL,
    "HEAD release manifest label mismatch",
  );
  const expectedManifestEntries = LEGAL_SOURCE_FILES.map(
    ({ path: legalPath, sha256, size }) => ({
      path: legalPath,
      sha256,
      size,
    }),
  ).sort((left, right) => left.path.localeCompare(right.path));
  const legalPaths = new Set(LEGAL_SOURCE_FILES.map((file) => file.path));
  const actualManifestEntries = (manifest.files || [])
    .filter((entry) => legalPaths.has(entry.path))
    .map(({ path: legalPath, sha256, size }) => ({
      path: legalPath,
      sha256,
      size,
    }))
    .sort((left, right) => left.path.localeCompare(right.path));
  assertDeepEqual(
    actualManifestEntries,
    expectedManifestEntries,
    "HEAD release manifest legal surface",
  );

  for (const legalFile of LEGAL_SOURCE_FILES) {
    const sourcePath = path.join(REPO_ROOT, legalFile.path);
    const sourceStat = await lstat(sourcePath);
    assert(
      sourceStat.isFile(),
      `legal source is not a regular file: ${legalFile.path}`,
    );
    assert(
      sourceStat.size === legalFile.size,
      `legal source size drift from HEAD manifest: ${legalFile.path}`,
    );
    assert(
      (await hashFile(sourcePath)) === legalFile.sha256,
      `legal source hash drift from HEAD manifest: ${legalFile.path}`,
    );
  }

  for (const legalFile of LEGAL_SOURCE_FILES) {
    scanTextForSecrets(
      await readFile(path.join(REPO_ROOT, legalFile.path), "utf8"),
      legalFile.path,
    );
  }
  return LEGAL_SOURCE_FILES;
}

async function stagePackage(packageRoot, contract, releaseAssets) {
  const releaseRoot = path.join(packageRoot, "release");
  await mkdir(releaseRoot, { recursive: false });

  const publishPackage = expectedPublishedPackageJson(contract);
  const packageText = jsonText(publishPackage);
  scanTextForSecrets(packageText, "published package.json");
  const packagePath = path.join(packageRoot, "package.json");
  await writeFile(packagePath, packageText, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o644,
  });
  await utimes(packagePath, FIXED_MTIME, FIXED_MTIME);

  scanTextForSecrets(contract.readme, "published README.md");
  const readmePath = path.join(packageRoot, "README.md");
  await writeFile(readmePath, contract.readme, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o644,
  });
  await utimes(readmePath, FIXED_MTIME, FIXED_MTIME);

  for (const legalFile of contract.legalFiles) {
    const sourcePath = path.join(contract.repoRoot, legalFile.path);
    assert(
      (await hashFile(sourcePath)) === legalFile.sha256,
      `legal source drift before copy: ${legalFile.path}`,
    );
    const destinationPath = path.join(packageRoot, legalFile.path);
    await copyFile(sourcePath, destinationPath, fsConstants.COPYFILE_EXCL);
    await chmod(destinationPath, 0o644);
    await utimes(destinationPath, FIXED_MTIME, FIXED_MTIME);
    const copiedStat = await stat(destinationPath);
    assert(
      copiedStat.size === legalFile.size,
      `staged legal size drift: ${legalFile.path}`,
    );
    assert(
      (await hashFile(destinationPath)) === legalFile.sha256,
      `staged legal hash drift: ${legalFile.path}`,
    );
  }

  for (const asset of releaseAssets) {
    const sourcePath = path.join(contract.releaseAssetDir, asset.name);
    const destinationPath = path.join(releaseRoot, asset.name);
    await copyFile(sourcePath, destinationPath, fsConstants.COPYFILE_EXCL);
    await chmod(destinationPath, 0o644);
    await utimes(destinationPath, FIXED_MTIME, FIXED_MTIME);
    const copiedStat = await stat(destinationPath);
    assert(copiedStat.size === asset.size, `staged size drift: ${asset.name}`);
    assert(
      (await hashFile(destinationPath)) === asset.sha256,
      `staged hash drift: ${asset.name}`,
    );
  }

  return { packageText, publishPackage, readmeText: contract.readme };
}

async function prepareNpmState(operationRoot) {
  const npmStateRoot = path.join(operationRoot, "npm-state");
  const cache = path.join(npmStateRoot, "cache");
  const userConfig = path.join(npmStateRoot, "user-npmrc");
  const globalConfig = path.join(npmStateRoot, "global-npmrc");
  await mkdir(cache, { recursive: true });
  await writeFile(userConfig, "", { flag: "wx" });
  await writeFile(globalConfig, "", { flag: "wx" });
  return { cache, globalConfig, userConfig };
}

function sanitizedNpmEnvironment(npmState) {
  const environment = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (!/(?:token|password|passwd|secret|_auth)/i.test(key)) {
      environment[key] = value;
    }
  }

  return {
    ...environment,
    GH_TOKEN: "",
    GITHUB_TOKEN: "",
    NODE_AUTH_TOKEN: "",
    NPM_TOKEN: "",
    npm_config_audit: "false",
    npm_config_cache: npmState.cache,
    npm_config_fund: "false",
    npm_config_globalconfig: npmState.globalConfig,
    npm_config_ignore_scripts: "true",
    npm_config_offline: "true",
    npm_config_package_lock: "false",
    npm_config_provenance: "false",
    npm_config_registry: "https://registry.invalid/",
    npm_config_update_notifier: "false",
    npm_config_userconfig: npmState.userConfig,
  };
}

function npmInvocation(args) {
  const npmCli = process.env.npm_execpath;
  if (npmCli) {
    return {
      command: process.execPath,
      args: [npmCli, ...args],
    };
  }

  if (process.platform === "win32") {
    return {
      command: process.env.ComSpec || "cmd.exe",
      args: ["/d", "/s", "/c", "npm.cmd", ...args],
    };
  }

  return {
    command: "npm",
    args,
  };
}

function runNpm(args, cwd, npmState) {
  const invocation = npmInvocation(args);
  const result = spawnSync(invocation.command, invocation.args, {
    cwd,
    encoding: "utf8",
    env: sanitizedNpmEnvironment(npmState),
    maxBuffer: 32 * 1024 * 1024,
    shell: false,
    timeout: 120_000,
    windowsHide: true,
  });

  if (result.error) {
    fail(`npm invocation failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const details = [result.stdout, result.stderr]
      .filter(Boolean)
      .join("\n")
      .trim();
    fail(`npm ${args[0]} failed with exit ${result.status}${details ? `: ${details}` : ""}`);
  }
  return result.stdout;
}

function parsePackJson(stdout, label) {
  let payload;
  try {
    payload = JSON.parse(stdout.trim());
  } catch (error) {
    fail(`${label} did not return valid JSON: ${error.message}`);
  }
  assert(
    Array.isArray(payload) && payload.length === 1,
    `${label} returned an unexpected result count`,
  );
  return payload[0];
}

function validatePackReport(report, expectedUnpackedSize, label, contract) {
  assert(report.name === contract.packageName, `${label} package name mismatch`);
  assert(report.version === contract.packageVersion, `${label} package version mismatch`);
  assert(
    path.basename(report.filename) === contract.tarballName,
    `${label} tarball filename mismatch`,
  );
  assert(Array.isArray(report.files), `${label} file list missing`);
  const actualPaths = report.files.map((entry) => entry.path).sort();
  assertDeepEqual(actualPaths, contract.expectedPackFiles, `${label} file allowlist`);
  assertSafePackPaths(actualPaths);
  assert(
    report.entryCount === contract.expectedPackFiles.length,
    `${label} entry count mismatch`,
  );
  assert(
    report.unpackedSize === expectedUnpackedSize,
    `${label} unpacked size mismatch`,
  );
  assert(
    Number.isInteger(report.size) && report.size > 0 && report.size <= MAX_TARBALL_SIZE,
    `${label} tarball size is outside the bounded range`,
  );
  return report;
}

async function npmPackDryRun(
  packageRoot,
  npmState,
  expectedUnpackedSize,
  contract = LIVE_PACKAGE_CONTRACT,
) {
  const stdout = runNpm(["pack", "--dry-run", "--json"], packageRoot, npmState);
  const report = parsePackJson(stdout, "npm pack --dry-run");
  return validatePackReport(
    report,
    expectedUnpackedSize,
    "npm pack --dry-run",
    contract,
  );
}

async function npmPackOnce(
  packageRoot,
  destinationRoot,
  npmState,
  expectedUnpackedSize,
  contract = LIVE_PACKAGE_CONTRACT,
) {
  await mkdir(destinationRoot, { recursive: false });
  const stdout = runNpm(
    ["pack", "--json", "--pack-destination", destinationRoot],
    packageRoot,
    npmState,
  );
  const report = validatePackReport(
    parsePackJson(stdout, "npm pack"),
    expectedUnpackedSize,
    "npm pack",
    contract,
  );
  const entries = await readdir(destinationRoot);
  assertDeepEqual(
    entries.sort(),
    [contract.tarballName],
    "npm pack destination allowlist",
  );

  const tarballPath = path.join(destinationRoot, contract.tarballName);
  const tarballStat = await stat(tarballPath);
  assert(tarballStat.isFile(), "npm pack did not create a regular tarball");
  assert(tarballStat.size === report.size, "npm pack tarball size mismatch");

  const sha256 = await hashFile(tarballPath, "sha256", "hex");
  const sha1 = await hashFile(tarballPath, "sha1", "hex");
  const sha512 = await hashFile(tarballPath, "sha512", "base64");
  assert(report.shasum === sha1, "npm pack SHA1 report mismatch");
  assert(report.integrity === `sha512-${sha512}`, "npm pack integrity mismatch");

  return {
    integrity: report.integrity,
    report,
    sha1,
    sha256,
    size: tarballStat.size,
    tarballPath,
  };
}

async function listRegularFiles(root) {
  const files = [];

  async function visit(current) {
    const entries = await readdir(current, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const absolute = path.join(current, entry.name);
      if (entry.isDirectory()) {
        await visit(absolute);
      } else if (entry.isFile()) {
        files.push(normalizePackagePath(path.relative(root, absolute)));
      } else {
        fail(`installed package contains a non-regular entry: ${entry.name}`);
      }
    }
  }

  await visit(root);
  return files.sort();
}

async function runInstalledSmoke(
  operationRoot,
  tarballPath,
  npmState,
  publishPackage,
  releaseAssets,
  contract,
) {
  const smokeRoot = path.join(operationRoot, "installed-smoke");
  await mkdir(smokeRoot, { recursive: false });
  await writeFile(
    path.join(smokeRoot, "package.json"),
    jsonText({ name: "decretum-npm-smoke", private: true, version: "1.0.0" }),
    { encoding: "utf8", flag: "wx", mode: 0o644 },
  );

  runNpm(
    ["install", "--package-lock=false", "--save=false", tarballPath],
    smokeRoot,
    npmState,
  );

  const installedRoot = path.join(
    smokeRoot,
    "node_modules",
    ...contract.packageName.split("/"),
  );
  const installedFiles = await listRegularFiles(installedRoot);
  assertDeepEqual(
    installedFiles,
    contract.expectedPackFiles,
    "installed package file allowlist",
  );
  assertSafePackPaths(installedFiles);

  const installedPackage = await readJson(
    path.join(installedRoot, "package.json"),
    "installed package.json",
  );
  assertDeepEqual(
    installedPackage,
    publishPackage,
    "installed package metadata",
  );

  assert(
    (await readFile(path.join(installedRoot, "README.md"), "utf8")) ===
      contract.readme,
    "installed package README drift",
  );

  for (const legalFile of contract.legalFiles) {
    const installedPath = path.join(installedRoot, legalFile.path);
    const installedStat = await lstat(installedPath);
    assert(
      installedStat.isFile(),
      `installed legal file is not regular: ${legalFile.path}`,
    );
    assert(
      installedStat.size === legalFile.size,
      `installed legal size drift: ${legalFile.path}`,
    );
    assert(
      (await hashFile(installedPath)) === legalFile.sha256,
      `installed legal hash drift: ${legalFile.path}`,
    );
  }

  for (const asset of releaseAssets) {
    const installedPath = path.join(installedRoot, ...asset.path.split("/"));
    const installedStat = await lstat(installedPath);
    assert(installedStat.isFile(), `installed asset is not regular: ${asset.path}`);
    assert(installedStat.size === asset.size, `installed size drift: ${asset.path}`);
    assert(
      (await hashFile(installedPath)) === asset.sha256,
      `installed hash drift: ${asset.path}`,
    );
  }

  return "PASS";
}

export async function createVerifiedPackage({
  installedSmoke = true,
  contract = LIVE_PACKAGE_CONTRACT,
} = {}) {
  assertSafePaths();
  await validateSourcePackageJson();
  const releaseValidation = await validateReleaseAssets();
  await validateLegalSourceFiles();

  const operationRoot = await mkdtemp(
    path.join(tmpdir(), "decretum-npm-package-"),
  );
  let cleaned = false;
  const cleanup = async () => {
    if (!cleaned) {
      cleaned = true;
      await rm(operationRoot, { force: true, recursive: true });
    }
  };

  try {
    const packageRoot = path.join(operationRoot, "package");
    await mkdir(packageRoot, { recursive: false });
    const { packageText, publishPackage, readmeText } =
      await stagePackage(packageRoot, contract, releaseValidation.assets);
    const npmState = await prepareNpmState(operationRoot);
    const expectedUnpackedSize =
      Buffer.byteLength(packageText, "utf8") +
      Buffer.byteLength(readmeText, "utf8") +
      releaseValidation.assets.reduce((total, asset) => total + asset.size, 0) +
      contract.legalFiles.reduce((total, file) => total + file.size, 0);

    const dryRun = await npmPackDryRun(
      packageRoot,
      npmState,
      expectedUnpackedSize,
      contract,
    );
    const firstPack = await npmPackOnce(
      packageRoot,
      path.join(operationRoot, "pack-a"),
      npmState,
      expectedUnpackedSize,
      contract,
    );
    const secondPack = await npmPackOnce(
      packageRoot,
      path.join(operationRoot, "pack-b"),
      npmState,
      expectedUnpackedSize,
      contract,
    );
    assert(
      firstPack.sha256 === secondPack.sha256 &&
        firstPack.size === secondPack.size,
      "npm pack is not deterministic for the immutable input set",
    );

    const smokeStatus = installedSmoke
      ? await runInstalledSmoke(
          operationRoot,
          firstPack.tarballPath,
          npmState,
          publishPackage,
          releaseValidation.assets,
          contract,
        )
      : "NOT_RUN";

    return {
      cleanup,
      authorityEvidence: releaseValidation.authority,
      dryRun,
      firstPack,
      packageRoot,
      privacyEvidence: releaseValidation.privacy,
      publishPackage,
      releaseAssets: releaseValidation.assets,
      repositoryEvidence: releaseValidation.repository,
      smokeStatus,
      tagEvidence: releaseValidation.tag,
    };
  } catch (error) {
    await cleanup();
    throw error;
  }
}

function buildReceipt(verified, contract = LIVE_PACKAGE_CONTRACT) {
  return {
    schema: "decretum.npm_package_receipt.v2",
    status: "PASS",
    candidate: "legal-v2",
    authority: {
      receipt_id: contract.authorityReceiptId,
      cursor: contract.authorityCursor,
      pending_body_access: "NO",
      tracked_head: verified.authorityEvidence,
      repository_oracle: verified.repositoryEvidence,
    },
    package: {
      name: contract.packageName,
      version: contract.packageVersion,
      dist_tag: contract.distTag,
      registry: contract.registry,
      access: "public",
      filename: contract.tarballName,
      sha256: verified.firstPack.sha256,
      size: verified.firstPack.size,
      shasum: verified.firstPack.sha1,
      integrity: verified.firstPack.integrity,
    },
    source: {
      repository: contract.repositoryUrl,
      commit: contract.sourceCommit,
      tree: contract.sourceTree,
      tag: contract.releaseLabel,
      tag_ref: contract.tagRef,
      release_url: contract.releaseUrl,
      tag_relation: verified.tagEvidence,
    },
    assets: verified.releaseAssets.map(({ path: assetPath, sha256, size }) => ({
      path: assetPath,
      sha256,
      size,
    })),
    legal_surface: {
      revision: "legal-v2",
      release_manifest_sha256: contract.releaseManifestSha256,
      files: contract.legalFiles.map(({ path: legalPath, sha256, size }) => ({
        path: legalPath,
        sha256,
        size,
      })),
    },
    release_inventory: {
      accepted_manifest_sha256:
        verified.privacyEvidence.release_zip.accepted_manifest_sha256,
      manifest_member_sha256:
        verified.privacyEvidence.release_zip.manifest_member_sha256,
      manifest_inventory_count:
        verified.privacyEvidence.release_zip.manifest_inventory_count,
      manifest_inventory_sha256:
        verified.privacyEvidence.release_zip.manifest_inventory_sha256,
      payload_inventory_count:
        verified.privacyEvidence.release_zip.payload_inventory_count,
      payload_inventory_sha256:
        verified.privacyEvidence.release_zip.payload_inventory_sha256,
      checker_command: verified.privacyEvidence.release_zip.command,
      checker_rc: verified.privacyEvidence.release_zip.rc,
      checker_sha256: verified.privacyEvidence.release_zip.checker_sha256,
    },
    validation: {
      asset_hashes: "PASS",
      attestation: "PASS",
      head_release_manifest_legal_surface: "PASS",
      exact_pack_allowlist: "PASS",
      privacy: {
        status: "PASS",
        ...verified.privacyEvidence,
      },
      npm_pack_dry_run: "PASS",
      deterministic_double_pack: "PASS",
      installed_package_smoke: verified.smokeStatus,
      network_dependency: "NONE",
    },
    output: {
      directory: contract.outputRelative,
      tarball: contract.tarballName,
      sha256_sidecar: contract.sidecarName,
      receipt: contract.receiptName,
      materialization_contract: "CONTENT_KEYED_CREATE_OR_REUSE",
      identical_existing: "REUSED_WITHOUT_MUTATION",
      mismatch: "COLLISION_BLOCKED",
    },
  };
}

export async function buildPackageArtifacts() {
  assertSafePaths();
  const verified = await createVerifiedPackage({ installedSmoke: true });
  try {
    const materialized = await materializeVerifiedPackage(verified, OUTPUT_DIR);
    const execution = {
      ...materialized.receipt,
      output: {
        ...materialized.receipt.output,
        materialization: materialized.materialization,
      },
    };
    console.log(jsonText(execution).trimEnd());
    return execution;
  } finally {
    await verified.cleanup();
  }
}

function isMainModule() {
  if (!process.argv[1]) {
    return false;
  }
  return import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
}

if (isMainModule()) {
  const action = process.argv.includes("--self-test")
    ? runSyntheticSelfTest
    : buildPackageArtifacts;
  action().then((report) => {
    if (process.argv.includes("--self-test")) {
      console.log(jsonText(report).trimEnd());
    }
  }).catch((error) => {
    if (error instanceof BlockedReleaseError) {
      console.log(jsonText(error.toJSON()).trimEnd());
      process.exitCode = 2;
      return;
    }
    if (error instanceof OutputCollisionError) {
      console.log(jsonText(error.toJSON()).trimEnd());
      process.exitCode = 3;
      return;
    }
    console.error(`npm package build failed: ${error.message}`);
    process.exitCode = 1;
  });
}
