# Hermes Desktop Gateway Troubleshooting

Use this reference when the court task involves Hermes Desktop or Gateway installation/repair on Windows.

## Guardrails

- Prefer official Hermes documentation as source of truth for Desktop/Gateway behavior.
- Avoid interactive configuration commands unless using PTY or explicit input.
- If Windows installer or site-packages files are locked, stop the process holding the lock or ask for a restart rather than looping retries.
- Do not infer Desktop/Gateway success from file presence alone; verify with the relevant Hermes command or service status.

This reference is intentionally narrow so the main court skill can link it without a missing-file failure. Expand only after a real Desktop/Gateway troubleshooting session produces verified steps.
