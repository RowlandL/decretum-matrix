# Security policy

## Reporting a vulnerability

When the authoritative GitHub repository enables private vulnerability
reporting, use the repository's **Security → Advisories → Report a
vulnerability** workflow. Until an authoritative private channel is published,
do not disclose exploit details or credentials in a public issue.

Never paste API keys, bearer tokens, cookies, `.shiguan-key` contents, private
Shiguan records, host logs, or personal filesystem paths into a public issue.
Revoke or rotate any credential that may already have been exposed.

## Scope

Security reports may cover package construction, source/package path
traversal, local service exposure, peer synchronization, credential handling,
redaction, release manifests, or provenance. The package is provided without
warranty under Apache-2.0; this policy does not create a service-level
agreement.

## Supported release

The next reviewed release is `beta0.5.9`. Historical artifacts remain
immutable and are not silently replaced.
