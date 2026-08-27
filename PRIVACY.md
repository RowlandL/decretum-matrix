# Privacy and local-data policy

- The Shiguan Web service defaults to `127.0.0.1`. LAN exposure requires an
  explicit LAN opt-in such as `--host 0.0.0.0` and should be protected by host
  firewall rules and an appropriate bearer key.
- Shared Shiguan data is stored outside the installed skill under the
  platform user-data root, normally
  `court-shiguan/decretum-matrix/references`. It may contain local
  records, plan archives, ledgers, peer state, and user-authored notes.
- Portable packages exclude private Shiguan bodies, plan archives, runtime
  ledgers, imports, peer state, logs, credentials, host-specific paths, caches,
  and generated local capability catalogs. Only empty portable seed material
  is generated during staging.
- A `.shiguan-key` value is a bearer secret. Its compatibility encoding is
  obfuscation, not encryption; anyone who can read it can use the credential
  until expiry or revocation.
- Peer endpoints must not embed credentials, query strings, or fragments.
  Non-loopback peers require HTTPS, redirects are rejected, and bearer tokens
  must never be forwarded to another origin.
- Diagnostic logs redact common API-key, authorization, bearer, cookie, token,
  secret, and password fields. Redaction reduces accidental disclosure but is
  not a substitute for avoiding sensitive input.
