# Court Host And Platform Pitfalls

This reference owns host-specific pitfalls that are too detailed for the entrypoint. Load it only when a decree touches Windows terminal setup, Hermes configuration, local GUI/HTTP supervision boundaries, rate-limit recovery, or platform-specific command quirks.

## Installation And Source Provenance

- Windows GUI terminal/emulator installs under `super`/`superCC` are software-install decrees with source/provenance gates. Prefer trusted package managers. For Alacritty, verify `winget show Alacritty.Alacritty` before `winget install --id Alacritty.Alacritty --exact --source winget`; verify both the package-manager record and `alacritty --version`. If the user or host blocks a source query/download, stop and memorialize `BLOCKED`/`NEEDS_CONTEXT` instead of retrying the same outcome through another command or tool. If an async court probe returns after a blocked closeout, append it as supplemental Shiguan evidence rather than silently reopening or changing the decree.

## Windows Terminal And Hermes Config

- For Windows terminal-emulator configuration decrees, separate installer state from launch-shell state. Alacritty v0.17+ reads `%APPDATA%\alacritty\alacritty.toml`; to make new windows start PowerShell 7, preserve or back up any existing file, then set `[terminal.shell]` with `program = "C:/Program Files/PowerShell/7/pwsh.exe"` and lightweight args such as `["-NoLogo"]`. Verify with `pwsh.exe -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'`, TOML readback, and an Alacritty `--config-file ... --command pwsh ...` smoke command rather than assuming MSI install changed the shell.
- For Hermes configuration decrees, do not assume `~/.hermes/config.yaml` is the active home. First resolve the active Hermes home through Hermes' own loader (`hermes_cli.config.get_hermes_home()` / `load_config()` in the active venv) and edit that config path. When the user asks to make compression use the main model, set `auxiliary.compression` explicitly to the active main model endpoint; for named/custom providers, the robust pattern is `provider: custom`, `model: <main model>`, `base_url: <main base_url>`, `api_mode: <main api_mode>`, and empty `api_key` so secrets remain in the normal credential source. Validate by calling `_resolve_task_provider_model('compression')` in the active Hermes venv and checking it resolves to the intended model/base_url without printing secrets.

## Windows Execution Quirks

- Script portability is a first-class package gate. New or changed scripts must
  resolve user data/config/cache roots through `scripts/court_platform.py` and
  Shiguan roots through `scripts/shiguan_paths.py` instead of hard-coding
  `%LOCALAPPDATA%`, `%USERPROFILE%`, `/mnt/c`, `/Users/<name>`, or
  `C:\Users\<name>`. Command examples in governing references should use
  `python -B scripts/...` unless a shell-specific example is explicitly required.
- On Windows, an interactive shell may resolve npm's `codex.cmd`/`codex.ps1`
  while Python or another host using `CreateProcess("codex")` skips those shims
  and reaches a later stale `codex.exe`. Treat matching version text alone as
  insufficient. `scripts/court_codex_host_resolution.py` requires the first
  executable beside the npm shim to share file identity, SHA256, and version
  with the verified npm-native binary, and verifies the bare subprocess path as
  well. Its explicit repair mode first tries a symbolic link, falls back to a
  same-volume hard link, and migrates any conflicting executable into the
  shared Shiguan host-capability backup tree; it never deletes the conflict.
  Re-run the live gate after every npm Codex upgrade because a hard link can
  otherwise remain attached to the previous binary. Fresh office workers still
  execute an exact native path and recheck the host-proof SHA256 at launch.
- Native Windows Python, POSIX-compatible shells on Windows, and Linux/macOS Python disagree about path syntax. Do not teach an office pane to translate workspace paths by hand. For superCC `squad` calls, route through `scripts/supercc_squad.py` or the `.sh`/`.ps1`/`.cmd` wrapper from the role dossier directory; the wrapper resolves the host program and environment. For process inspection, do not assume POSIX `ps` exists on Windows; use the platform's native process tool.
- Claude Code Bash on Windows may be a POSIX shell even when the task workspace is a native Windows directory. The generated Shell Contract must therefore point to the wrapper scripts, not to shell-specific absolute workspace paths. On Linux/macOS the same wrapper should resolve the normal `squad` binary from PATH.
- If Claude Code or another CLI transcript shows a command copied from an older prompt, for example a bare office inbox command, `cd` into a Windows home path, or manual `/mnt/c`/`/c`/`C:\...` conversion, treat that transcript as stale drift evidence. Repair the generated dossier or shell contract instead of adding another host-specific path pattern. The durable command surface is the wrapper path relative to the role dossier plus the task workspace exposed separately through environment/add-dir mechanisms.
- When recovering from SuperCC rate-limits or full-freeze, use bounded request-rate mode. The old fixed 5-agent gate is removed: multiple offices may be open, including 六部, but model-triggering launches/dispatches must stay at `<=20 requests/minute`, and bounded stress tests must also set an explicit total request budget such as `total<=20`. Keep `office_show_delay` independent: it is presentation-only, 0-5 seconds, with no first-office cooldown and no effect on ordinary spawned agents. Provider waits longer than five seconds must surface as `queued_rate_limit`/Retry-After backoff so the launcher never appears silently frozen. Do not let 太子代工 replace a reachable 六部 agente.

## Local GUI And HTTP Exclusion

- Local GUI/HTTP surfaces are explicitly sealed and out-of-scope for `superCC` supervision and monitoring. When modifying or extending `supercc_watchdog.py` or associated incident recovery systems, do not add endpoints, HTTP patrol calls, backend service dependencies, visible monitor panes, or popup windows. Keep incident tracing and safe-recover suggestions restricted to local JSON/JSONL files and silent background script records.
