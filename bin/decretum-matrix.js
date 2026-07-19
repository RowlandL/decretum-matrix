#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

function configuredCandidate() {
  const command = process.env.DECRETUM_MATRIX_PYTHON?.trim();
  if (!command) {
    return null;
  }
  let prefixArgs = [];
  const encoded = process.env.DECRETUM_MATRIX_PYTHON_PREFIX_JSON?.trim();
  if (encoded) {
    const parsed = JSON.parse(encoded);
    if (!Array.isArray(parsed) || parsed.some((item) => typeof item !== "string")) {
      throw new Error("DECRETUM_MATRIX_PYTHON_PREFIX_JSON must be a JSON string array");
    }
    prefixArgs = parsed;
  }
  return { command, prefixArgs };
}

function pythonCandidates(platform) {
  const configured = configuredCandidate();
  if (configured) {
    return [configured];
  }
  if (platform === "win32") {
    return [
      { command: "python", prefixArgs: [] },
      { command: "py", prefixArgs: ["-3"] },
      { command: "python3", prefixArgs: [] },
    ];
  }
  return [
    { command: "python3", prefixArgs: [] },
    { command: "python", prefixArgs: [] },
  ];
}

function main() {
  const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
  const bootstrap = path.join(scriptRoot, "decretum-matrix.py");
  const platform = process.env.DECRETUM_MATRIX_TEST_PLATFORM || process.platform;
  if (!new Set(["win32", "darwin", "linux"]).has(platform)) {
    throw new Error(`unsupported platform: ${platform}`);
  }
  for (const candidate of pythonCandidates(platform)) {
    const result = spawnSync(
      candidate.command,
      [...candidate.prefixArgs, "-B", bootstrap, ...process.argv.slice(2)],
      {
        cwd: process.cwd(),
        env: process.env,
        shell: false,
        stdio: "inherit",
        windowsHide: true,
      },
    );
    if (result.error?.code === "ENOENT") {
      continue;
    }
    if (result.error) {
      throw result.error;
    }
    if (result.signal) {
      process.kill(process.pid, result.signal);
      return;
    }
    process.exitCode = result.status ?? 1;
    return;
  }
  throw new Error("Python 3 interpreter not found");
}

try {
  main();
} catch (error) {
  console.error(`decretum-matrix launcher failed: ${error.message}`);
  process.exitCode = 1;
}
