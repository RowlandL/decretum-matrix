export async function verifyCandidateAttempts({
  assert,
  buildCandidate,
  commandExecution,
  outputDirectory,
  path,
  pathExists,
  root,
  runFixtureCommand,
  snapshotOutputDirectory,
}) {
  for (const result of [
    { status: null, signal: "SIGTERM", stdout: "partial", stderr: "err" },
    { status: null, signal: "SIGKILL", stdout: "partial", stderr: "err" },
  ]) {
    const execution = commandExecution({
      entrypoint: "signal-fixture", command: "fixture", argv: [], cwd: root,
      result, runner: "fixture",
    });
    assert(
      execution.status === "FAIL" && execution.exit_code === null &&
        execution.signal === result.signal && execution.failure_reason &&
        execution.stdout === "partial" && execution.stderr === "err",
      "signal termination passed or lost its signal/partial output",
    );
  }
  const timeout = commandExecution({
    entrypoint: "timeout-fixture",
    command: process.execPath,
    argv: ["-e", "timeout"],
    cwd: root,
    result: runFixtureCommand(
      process.execPath,
      ["-e", "process.stdout.write('out');process.stderr.write('err');setTimeout(()=>{},1500)"],
      { cwd: root, timeout: 500, allowProcessError: true },
    ),
    runner: "node",
  });
  assert(
    timeout.status === "FAIL" &&
      timeout.timed_out === true &&
      timeout.failure_reason === "ETIMEDOUT" &&
      timeout.stdout === "out" &&
      timeout.stderr === "err",
    "candidate timeout did not retain its process status and partial streams",
  );

  const blocked = async (directory) => {
    try {
      await buildCandidate({ installedSmoke: false, outputDirectory: directory });
    } catch (error) {
      return error;
    }
    return null;
  };
  const failedOutput = path.join(root, "failed-candidate-output");
  for (const [directory, retry] of [
    [failedOutput, true],
    [outputDirectory, false],
  ]) {
    const before = (await pathExists(directory))
      ? await snapshotOutputDirectory(directory)
      : null;
    const failure = await blocked(directory);
    assert(
      failure?.code === "BLOCKED_LOCAL_INSTALL_CANDIDATE_SMOKE" &&
        (await pathExists(failure.details.attempt.directory)) &&
        (before
          ? JSON.stringify(before) === JSON.stringify(await snapshotOutputDirectory(directory))
          : !(await pathExists(directory))),
      "candidate failure did not preserve an attempt without mutating stable output",
    );
    if (retry) {
      assert(
        (await buildCandidate({ outputDirectory: directory })).output.materialization ===
          "CREATED",
        "successful retry after failed candidate smoke did not create stable output",
      );
    }
  }
}
