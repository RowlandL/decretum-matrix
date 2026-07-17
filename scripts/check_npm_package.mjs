import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import * as packageBuilder from "./build_npm_package.mjs";
import {
  BlockedReleaseError,
  DIST_TAG,
  LEGAL_SOURCE_FILES,
  LICENSE,
  PACKAGE_NAME,
  PACKAGE_VERSION,
  RECEIPT_NAME,
  REGISTRY,
  RELEASE_ASSET_DIR,
  RELEASE_ASSETS,
  RELEASE_LABEL,
  RELEASE_URL,
  REPOSITORY_URL,
  SOURCE_COMMIT,
  SOURCE_TREE,
  TAG_REF,
  TARBALL_NAME,
  createVerifiedPackage,
} from "./build_npm_package.mjs";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const REPO_ROOT = path.resolve(path.dirname(SCRIPT_PATH), "..");

function fail(message) {
  throw new Error(message);
}

function gitTextAt(root, ...args) {
  const result = spawnSync("git", args, {
    cwd: root,
    encoding: "utf8",
    shell: false,
    timeout: 30_000,
    windowsHide: true,
  });
  if (result.error) {
    fail(`git ${args.join(" ")} failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    fail(
      `git ${args.join(" ")} failed with exit ${result.status}: ${result.stderr.trim()}`,
    );
  }
  return result.stdout.trim();
}

function gitText(...args) {
  return gitTextAt(REPO_ROOT, ...args);
}

function normalizeIndependentGitHubRemote(remote) {
  const value = remote.trim();
  const scpMatch = /^(?:git@)?github\.com:([^/]+)\/([^/?#]+?)(?:\.git)?$/i.exec(
    value,
  );
  let owner;
  let repository;
  if (scpMatch) {
    [, owner, repository] = scpMatch;
  } else {
    let parsed;
    try {
      parsed = new URL(value);
    } catch {
      fail("origin is not an unambiguous GitHub repository URL");
    }
    if (
      !["https:", "ssh:"].includes(parsed.protocol) ||
      parsed.hostname.toLowerCase() !== "github.com" ||
      parsed.username ||
      parsed.password ||
      parsed.search ||
      parsed.hash
    ) {
      fail("origin is not an unambiguous GitHub repository URL");
    }
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length !== 2) {
      fail("origin is not an unambiguous GitHub repository URL");
    }
    [owner, repository] = parts;
    repository = repository.replace(/\.git$/i, "");
  }
  if (
    !/^[A-Za-z0-9_.-]+$/.test(owner) ||
    !/^[A-Za-z0-9_.-]+$/.test(repository)
  ) {
    fail("origin is not an unambiguous GitHub repository URL");
  }
  return {
    owner,
    repository,
    canonicalUrl: `https://github.com/${owner}/${repository}.git`,
  };
}

function runCheckerIndependentOriginSelfTest() {
  const canonical = normalizeIndependentGitHubRemote(
    "https://github.com/RowlandL/decretum-matrix.git",
  );
  let userinfoRejected = true;
  let userinfoRedacted = true;
  for (const remote of [
    "https://sensitive-user:sensitive-pass@github.com/RowlandL/decretum-matrix.git",
    "ssh://sensitive-user@github.com/RowlandL/decretum-matrix.git",
  ]) {
    try {
      normalizeIndependentGitHubRemote(remote);
      userinfoRejected = false;
    } catch (error) {
      if (String(error?.message || error).includes("sensitive-")) {
        userinfoRedacted = false;
      }
    }
  }
  if (!userinfoRejected || !userinfoRedacted) {
    fail("checker-independent origin userinfo contract did not fail closed");
  }
  return {
    evidence: {
      canonical_url: canonical.canonicalUrl,
      userinfo_rejected: userinfoRejected,
      userinfo_redacted: userinfoRedacted,
    },
    validation: {
      checker_independent_origin_userinfo_rejected: "PASS",
      checker_independent_origin_userinfo_redacted: "PASS",
    },
  };
}

const INDEPENDENT_CRITICAL_HEAD_PATHS = Object.freeze([
  "package.json",
  "package-lock.json",
  "scripts/build_npm_package.mjs",
  "scripts/check_npm_package.mjs",
  "VERSION",
  "release-manifest.json",
  "scripts/package_skill.py",
  "scripts/check_package_privacy.py",
]);

async function independentReleaseAssetsComplete() {
  let entries;
  try {
    entries = await readdir(RELEASE_ASSET_DIR, { withFileTypes: true });
  } catch (error) {
    if (error?.code === "ENOENT") {
      return false;
    }
    throw error;
  }
  const names = new Set(entries.map((entry) => entry.name));
  return RELEASE_ASSETS.every((asset) => names.has(asset.name));
}

function validateIndependentAnnotatedTag(root, tagRef, expectedHead) {
  const tagType = gitTextAt(root, "cat-file", "-t", tagRef);
  if (tagType !== "tag") {
    fail(`independent release tag is not annotated: ${tagRef}`);
  }
  const tagCommit = gitTextAt(root, "rev-parse", `${tagRef}^{commit}`);
  if (tagCommit !== expectedHead) {
    fail(`independent release tag does not point to HEAD: ${tagRef}`);
  }
  return {
    ref: tagRef,
    type: tagType,
    commit: tagCommit,
    relation: "HEAD_MATCH",
  };
}

async function validateIndependentHeadAndTag(authority) {
  const status = gitText("status", "--porcelain=v1", "--untracked-files=no");
  if (status !== "") {
    fail("independent tracked production authority worktree is dirty");
  }
  const files = [];
  const bytesByPath = new Map();
  for (const relativePath of INDEPENDENT_CRITICAL_HEAD_PATHS) {
    const worktreeBytes = await readFile(
      path.join(REPO_ROOT, ...relativePath.split("/")),
    );
    const head = spawnSync("git", ["show", `HEAD:${relativePath}`], {
      cwd: REPO_ROOT,
      encoding: null,
      maxBuffer: 32 * 1024 * 1024,
      shell: false,
      timeout: 30_000,
      windowsHide: true,
    });
    if (head.error || head.status !== 0) {
      fail(
        `independent critical HEAD path unavailable: ${relativePath}: ${head.error?.message || head.stderr?.toString("utf8").trim()}`,
      );
    }
    const headBytes = Buffer.from(head.stdout);
    if (!worktreeBytes.equals(headBytes)) {
      fail(`independent critical HEAD path differs from worktree: ${relativePath}`);
    }
    files.push({
      path: relativePath,
      sha256: createHash("sha256").update(headBytes).digest("hex"),
      size: headBytes.length,
    });
    bytesByPath.set(relativePath, headBytes);
  }
  const headVersion = bytesByPath.get("VERSION").toString("utf8").trim();
  const headManifestBytes = bytesByPath.get("release-manifest.json");
  const headManifest = JSON.parse(headManifestBytes.toString("utf8"));
  if (
    headVersion !== authority.releaseLabel ||
    headManifest.release_label !== authority.releaseLabel ||
    headManifest.version_core !== authority.packageVersion.replace(/-beta\.0$/, "")
  ) {
    fail("independent HEAD VERSION/release-manifest identity mismatch");
  }

  const tag = validateIndependentAnnotatedTag(
    REPO_ROOT,
    authority.tagRef,
    authority.headCommit,
  );
  return {
    command:
      "git status --porcelain=v1 --untracked-files=no + git show HEAD:<path> + git cat-file/rev-parse tag",
    rc: 0,
    head: authority.headCommit,
    files,
    tag,
  };
}

async function loadIndependentRepositoryOracle(releaseManifest) {
  const remoteResult = spawnSync(
    "git",
    ["remote", "get-url", "--all", "origin"],
    {
      cwd: REPO_ROOT,
      encoding: "utf8",
      shell: false,
      timeout: 30_000,
      windowsHide: true,
    },
  );
  if (remoteResult.error || remoteResult.status !== 0) {
    fail(
      `origin repository oracle unavailable: ${remoteResult.error?.message || remoteResult.stderr.trim()}`,
    );
  }
  const remotes = remoteResult.stdout
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  if (remotes.length !== 1) {
    fail(`origin repository oracle is ambiguous: ${remotes.length} URLs`);
  }
  const repository = normalizeIndependentGitHubRemote(remotes[0]);
  if (
    repository.owner !== "RowlandL" ||
    repository.repository !== "decretum-matrix"
  ) {
    fail(
      `origin repository identity mismatch: ${repository.owner}/${repository.repository}`,
    );
  }
  if (releaseManifest.provenance !== "PROVENANCE.md") {
    fail("release-manifest.json provenance pointer mismatch");
  }
  const provenancePath = path.join(REPO_ROOT, releaseManifest.provenance);
  const provenanceBytes = await readFile(provenancePath);
  const provenanceEntry = (releaseManifest.files || []).filter(
    (entry) => entry.path === releaseManifest.provenance,
  );
  if (
    provenanceEntry.length !== 1 ||
    provenanceEntry[0].size !== provenanceBytes.length ||
    provenanceEntry[0].sha256 !==
      createHash("sha256").update(provenanceBytes).digest("hex")
  ) {
    fail("manifest provenance file inventory mismatch");
  }
  const provenance = provenanceBytes.toString("utf8");
  if (
    !provenance.includes(
      "Canonical repository/skill/package name: `decretum-matrix`",
    ) ||
    !provenance.includes("Public maintainer identity: `@RowlandL`")
  ) {
    fail("PROVENANCE.md repository owner/name identity mismatch");
  }
  return repository;
}

async function loadIndependentAuthority() {
  const releaseLabel = (await readFile(path.join(REPO_ROOT, "VERSION"), "utf8")).trim();
  const releaseManifest = JSON.parse(
    await readFile(path.join(REPO_ROOT, "release-manifest.json"), "utf8"),
  );
  const repository = await loadIndependentRepositoryOracle(releaseManifest);
  if (releaseManifest.release_label !== releaseLabel) {
    fail("VERSION and release-manifest.json release_label disagree");
  }
  if (!/^beta\d+\.\d+\.\d+$/.test(releaseLabel)) {
    fail(`unsupported VERSION release label: ${releaseLabel}`);
  }
  const versionCore = releaseLabel.slice("beta".length);
  if (releaseManifest.version_core !== versionCore) {
    fail("release-manifest.json version_core does not match VERSION");
  }
  const channel = releaseManifest.channel;
  if (channel !== "beta") {
    fail(`unsupported release channel: ${channel}`);
  }
  const packageVersion = `${versionCore}-${channel}.0`;
  const artifactName = `decretum-matrix-${releaseLabel}.zip`;
  const sidecarName = `${artifactName}.sha256`;
  const attestationName = `decretum-matrix-${releaseLabel}.release-attestation.json`;
  const releaseNotesName = `decretum-matrix-${releaseLabel}.release-notes.md`;
  const tarballName = `rowlandl-decretum-matrix-${packageVersion}.tgz`;
  const receiptName = `rowlandl-decretum-matrix-${packageVersion}.receipt.json`;
  return {
    artifactName,
    attestationName,
    expectedAssetNames: [
      "SBOM.spdx.json",
      artifactName,
      sidecarName,
      attestationName,
      releaseNotesName,
    ].sort(),
    packageVersion,
    receiptName,
    releaseLabel,
    releaseNotesName,
    repository,
    sidecarName,
    tagRef: releaseManifest.expected_final_tag,
    tarballName,
    headCommit: gitText("rev-parse", "HEAD"),
    headTree: gitText("rev-parse", "HEAD^{tree}"),
  };
}

export async function validateIndependentCurrentIdentity() {
  const authority = await loadIndependentAuthority();
  const actualAssetNames = RELEASE_ASSETS.map((asset) => asset.name).sort();
  const packageJson = JSON.parse(
    await readFile(path.join(REPO_ROOT, "package.json"), "utf8"),
  );
  const packageLock = JSON.parse(
    await readFile(path.join(REPO_ROOT, "package-lock.json"), "utf8"),
  );
  const problems = [];
  const expect = (condition, message) => {
    if (!condition) {
      problems.push(message);
    }
  };

  expect(RELEASE_LABEL === authority.releaseLabel, "builder RELEASE_LABEL is not derived from VERSION");
  expect(PACKAGE_VERSION === authority.packageVersion, "builder PACKAGE_VERSION is not derived from VERSION/channel");
  expect(TAG_REF === authority.tagRef, "builder TAG_REF is not derived from release-manifest.json");
  expect(SOURCE_COMMIT === authority.headCommit, "builder SOURCE_COMMIT is not current HEAD");
  expect(SOURCE_TREE === authority.headTree, "builder SOURCE_TREE is not current HEAD tree");
  expect(path.basename(RELEASE_ASSET_DIR) === authority.releaseLabel, "builder release asset directory falls back to a stale release");
  expect(
    JSON.stringify(actualAssetNames) === JSON.stringify(authority.expectedAssetNames),
    "builder release asset allowlist falls back to stale release assets",
  );
  expect(TARBALL_NAME === authority.tarballName, "builder tarball name is stale");
  expect(RECEIPT_NAME === authority.receiptName, "builder receipt name is stale");
  expect(
    packageJson.name === "decretum-matrix-npm-release-harness" &&
      packageJson.version === "0.0.0-private" &&
      packageJson.private === true,
    "package.json is not a private version-neutral harness",
  );
  expect(
    packageLock.name === "decretum-matrix-npm-release-harness" &&
      packageLock.version === "0.0.0-private",
    "package-lock.json is not synchronized to the private harness",
  );
  expect(
    packageLock.packages?.[""]?.version === "0.0.0-private",
    "package-lock.json root package is not version-neutral",
  );
  expect(
    packageJson.gitHead === undefined &&
      packageJson.decretumMatrix === undefined &&
      packageJson.publishConfig === undefined,
    "private harness freezes publish provenance in the repository",
  );
  expect(
    RELEASE_URL.endsWith(`/releases/tag/${authority.releaseLabel}`),
    "builder release URL falls back to a stale release",
  );
  expect(
    REPOSITORY_URL === authority.repository.canonicalUrl,
    "builder repository URL is not derived from the independent origin oracle",
  );
  expect(
    RELEASE_URL ===
      `${authority.repository.canonicalUrl.replace(/\.git$/, "")}/releases/tag/${authority.releaseLabel}`,
    "builder release URL disagrees with the independent origin oracle",
  );

  if (problems.length > 0) {
    fail(`current npm identity/provenance contract rejected:\n- ${problems.join("\n- ")}`);
  }
  const assetsComplete = await independentReleaseAssetsComplete();
  const independentHeadAndTag = assetsComplete
    ? await validateIndependentHeadAndTag(authority)
    : null;
  return { ...authority, assetsComplete, independentHeadAndTag };
}

export async function checkNpmPackage() {
  const independentAuthority = await validateIndependentCurrentIdentity();
  const verified = await createVerifiedPackage({ installedSmoke: true });
  try {
    if (!independentAuthority.independentHeadAndTag) {
      fail("release assets became available without the checker-independent HEAD/tag gate");
    }
    const report = {
      schema: "decretum.npm_package_check.v2",
      status: "PASS",
      candidate: "legal-v2",
      package: {
        name: PACKAGE_NAME,
        version: PACKAGE_VERSION,
        dist_tag: DIST_TAG,
        registry: REGISTRY,
        access: "public",
        license: LICENSE,
        filename: TARBALL_NAME,
        deterministic_sha256: verified.firstPack.sha256,
        size: verified.firstPack.size,
      },
      source: {
        repository: REPOSITORY_URL,
        commit: SOURCE_COMMIT,
        tree: SOURCE_TREE,
        tag: RELEASE_LABEL,
        tag_ref: TAG_REF,
        release_url: RELEASE_URL,
        tag_relation: verified.tagEvidence,
      },
      authority: {
        checker_independent_head_tag: independentAuthority.independentHeadAndTag,
        repository_oracle: independentAuthority.repository,
      },
      assets: verified.releaseAssets.map(({ path: assetPath, sha256, size }) => ({
        path: assetPath,
        sha256,
        size,
      })),
      legal_surface: LEGAL_SOURCE_FILES.map(
        ({ path: legalPath, sha256, size }) => ({
          path: legalPath,
          sha256,
          size,
        }),
      ),
      validation: {
        metadata: "PASS",
        source_provenance: "PASS",
        checker_independent_head_tag: "PASS",
        release_asset_hashes: "PASS",
        head_release_manifest_legal_surface: "PASS",
        exact_pack_allowlist: "PASS",
        privacy: {
          status: "PASS",
          ...verified.privacyEvidence,
        },
        npm_pack_dry_run_json: "PASS",
        deterministic_double_pack: "PASS",
        installed_package_smoke: verified.smokeStatus,
        network_dependency: "NONE",
        repository_output: "NOT_WRITTEN",
      },
    };
    console.log(JSON.stringify(report, null, 2));
    return report;
  } finally {
    await verified.cleanup();
  }
}

async function runCheckerIndependentTagSelfTest() {
  const root = await mkdtemp(path.join(tmpdir(), "decretum-npm-checker-tag-"));
  const tagName = "beta9.8.7";
  const tagRef = `refs/tags/${tagName}`;
  try {
    gitTextAt(root, "init", "-q");
    gitTextAt(root, "config", "user.name", "Decretum Checker");
    gitTextAt(root, "config", "user.email", "checker@example.invalid");
    gitTextAt(root, "config", "core.autocrlf", "false");
    await writeFile(path.join(root, "marker.txt"), "first\n", "utf8");
    gitTextAt(root, "add", "marker.txt");
    gitTextAt(root, "commit", "-q", "-m", "first checker tag target");
    const firstHead = gitTextAt(root, "rev-parse", "HEAD");

    let missingRejected = false;
    try {
      validateIndependentAnnotatedTag(root, tagRef, firstHead);
    } catch {
      missingRejected = true;
    }

    gitTextAt(root, "tag", tagName);
    let lightweightRejected = false;
    try {
      validateIndependentAnnotatedTag(root, tagRef, firstHead);
    } catch {
      lightweightRejected = true;
    }

    gitTextAt(root, "tag", "-d", tagName);
    gitTextAt(root, "tag", "-a", tagName, "-m", "checker annotated target");
    const positive = validateIndependentAnnotatedTag(root, tagRef, firstHead);
    await writeFile(path.join(root, "marker.txt"), "second\n", "utf8");
    gitTextAt(root, "add", "marker.txt");
    gitTextAt(root, "commit", "-q", "-m", "second checker tag target");
    const secondHead = gitTextAt(root, "rev-parse", "HEAD");
    let wrongTargetRejected = false;
    try {
      validateIndependentAnnotatedTag(root, tagRef, secondHead);
    } catch {
      wrongTargetRejected = true;
    }

    if (!missingRejected || !lightweightRejected || !wrongTargetRejected) {
      fail("checker-independent annotated tag negatives did not fail closed");
    }
    return {
      evidence: {
        command: "checker spawnSync git cat-file -t + git rev-parse <tag>^{commit}",
        positive,
        first_head: firstHead,
        second_head: secondHead,
        missing_rejected: missingRejected,
        lightweight_rejected: lightweightRejected,
        wrong_target_rejected: wrongTargetRejected,
      },
      validation: {
        checker_independent_annotated_tag_missing_rejected: "PASS",
        checker_independent_lightweight_tag_rejected: "PASS",
        checker_independent_wrong_target_tag_rejected: "PASS",
      },
    };
  } finally {
    await rm(root, { force: true, recursive: true });
  }
}

export async function selfTestNpmPackage() {
  if (typeof packageBuilder.runSyntheticSelfTest !== "function") {
    fail("build_npm_package.mjs does not expose the version-neutral synthetic self-test");
  }
  if (typeof packageBuilder.pythonInvocationContract !== "function") {
    fail("build_npm_package.mjs does not expose the immutable Python invocation contract");
  }
  const builderReport = await packageBuilder.runSyntheticSelfTest();
  const pythonContract = packageBuilder.pythonInvocationContract();
  if (
    pythonContract.command !== "$PYTHON" ||
    pythonContract.bytecode_disabled !== true ||
    pythonContract.shell !== false ||
    !["override", "discovery"].includes(pythonContract.source)
  ) {
    fail("builder Python invocation contract is incomplete");
  }
  const checkerTagTest = await runCheckerIndependentTagSelfTest();
  const checkerOriginTest = runCheckerIndependentOriginSelfTest();
  const report = {
    ...builderReport,
    evidence: {
      ...builderReport.evidence,
      python_invocation: pythonContract,
      checker_independent_tag_oracle: checkerTagTest.evidence,
      checker_independent_origin_oracle: checkerOriginTest.evidence,
    },
    validation: {
      ...builderReport.validation,
      ...checkerTagTest.validation,
      ...checkerOriginTest.validation,
    },
  };
  const requiredPasses = [
    "canonical_privacy_fixture",
    "nested_zip_member_privacy",
    "deterministic_double_pack",
    "strict_offline_install",
    "create_only",
    "identical_reuse",
    "collision_rejected",
    "stale_release_fallback_rejected",
    "manifest_inventory_exact_match",
    "inventory_tamper_rejected",
    "production_output_create",
    "production_output_reuse_no_mutation",
    "production_output_collision_preserved",
    "repository_origin_oracle",
    "origin_userinfo_rejected",
    "origin_userinfo_redacted",
    "receipt_canonical_origin_only",
    "wrong_origin_rejected",
    "full_fixture_noncurrent_release",
    "tracked_authority_clean",
    "dirty_authority_rejected",
    "annotated_tag_missing_rejected",
    "lightweight_tag_rejected",
    "wrong_target_tag_rejected",
    "checker_independent_annotated_tag_missing_rejected",
    "checker_independent_lightweight_tag_rejected",
    "checker_independent_wrong_target_tag_rejected",
    "checker_independent_origin_userinfo_rejected",
    "checker_independent_origin_userinfo_redacted",
    "python_interpreter_contract",
  ];
  const missing = requiredPasses.filter(
    (name) => report.validation?.[name] !== "PASS",
  );
  if (missing.length > 0) {
    fail(`synthetic self-test is incomplete: ${missing.join(", ")}`);
  }
  if (report.repository_output !== "NOT_WRITTEN") {
    fail("synthetic self-test wrote output inside the repository");
  }
  const liveLabel = (
    await readFile(path.join(REPO_ROOT, "VERSION"), "utf8")
  ).trim();
  if (report.synthetic_release?.releaseLabel === liveLabel) {
    fail("full synthetic harness remains coupled to the live VERSION label");
  }
  if (
    report.evidence?.repository_oracle?.owner !== "RowlandL" ||
    report.evidence?.repository_oracle?.repository !== "decretum-matrix" ||
    report.evidence?.repository_oracle?.canonical_url !==
      "https://github.com/RowlandL/decretum-matrix.git"
  ) {
    fail("synthetic repository oracle evidence is incomplete");
  }
  const zipEvidence = report.evidence?.release_zip;
  if (
    !Number.isInteger(zipEvidence?.manifest_inventory_count) ||
    zipEvidence.manifest_inventory_count <= 0 ||
    !/^[0-9a-f]{64}$/.test(zipEvidence?.accepted_manifest_sha256 || "") ||
    !/^[0-9a-f]{64}$/.test(zipEvidence?.manifest_inventory_sha256 || "") ||
    zipEvidence.manifest_member_sha256 !==
      zipEvidence.accepted_manifest_sha256 ||
    zipEvidence.payload_inventory_count !==
      zipEvidence.manifest_inventory_count ||
    zipEvidence.manifest_inventory_sha256 !==
      zipEvidence.payload_inventory_sha256
  ) {
    fail("synthetic ZIP evidence does not bind the accepted manifest inventory");
  }
  if (
    report.evidence?.inventory_tamper_negative?.rc !== 2 ||
    report.evidence.inventory_tamper_negative.sidecar_recomputed !== true ||
    report.evidence.inventory_tamper_negative.attestation_recomputed !== true
  ) {
    fail("inventory-tampered ZIP negative evidence is incomplete");
  }
  console.log(JSON.stringify(report, null, 2));
  return report;
}

function isMainModule() {
  if (!process.argv[1]) {
    return false;
  }
  return import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
}

if (isMainModule()) {
  const action = process.argv.includes("--self-test")
    ? selfTestNpmPackage
    : checkNpmPackage;
  action().catch((error) => {
    if (error instanceof BlockedReleaseError) {
      console.log(JSON.stringify(error.toJSON(), null, 2));
      process.exitCode = 2;
      return;
    }
    console.error(`npm package check failed: ${error.message}`);
    process.exitCode = 1;
  });
}
