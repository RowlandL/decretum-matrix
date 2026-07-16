# Decretum Matrix license and release preimage inventory

Receipt: `DM-LPR-P0-20260716`

Status: `PASS / CUTOVER_CANDIDATE_ELIGIBLE / LEGAL_REVIEW_REQUIRED`

Captured from `D:\project\decretum-matrix-beta0.5.10` at 2026-07-16 14:28 +08:00.

## Git and publication boundary

- branch: `release/beta0.5.10`
- HEAD: `040f707e5acc7c12cfcf50afcfc111a7e49a2f00`
- reachable commits from HEAD: `17`; reachable commits across local refs: `28`
- child index: `0`
- child remotes: `0`
- `beta0.5.10` local tags: `0`
- local artifact-name hits for `beta0.5.10` under release-packages, release-staging, release-backups, release-failed, `.staging`, and release-temp: `0`
- GitHub target: `https://github.com/RowlandL/decretum-matrix`; PUBLIC and empty, as explicitly verified by the user
- pending body access: `NO`

Cutover decision: the enumerated local/GitHub evidence contains no `beta0.5.10` distribution. `beta0.5.10` remains the first candidate new-name/AGPL cutover. If any later evidence shows prior delivery or distribution, the cutover automatically moves to the next unused release. This inventory does not purport to revoke any prior license that was validly granted; the existence, scope and rights basis of any historical grant remain `LEGAL_REVIEW_REQUIRED`.

## Legal and release surface hashes

| Path | Bytes | SHA-256 |
|---|---:|---|
| `LICENSE` | 10775 | `b87a529a13d5294f97bb847936a82f39e4f8adae2425a3a5fb5f1a7b75d43e6a` |
| `NOTICE` | 290 | `d3cd2b016b630b5ea2361096d8b0b0015eff582a3bae0dc60352bde78d7a69b6` |
| `THIRD_PARTY_NOTICES.md` | 1922 | `68dc950cc288617e6ea6fa9f8f4680bf733118a999eae94a5cfdc9e7b1634dc6` |
| `README.md` | 49873 | `9458018b22a17957350c70dadfb89ec00f633e34fe4992c76dffcbbd54c567a5` |
| `CONTRIBUTING.md` | 1042 | `bba82a6a57713d4507853f190601232863c79fc4b9e2b5c1df29203715f6bbd2` |
| `CHANGELOG.md` | 3781 | `b059077dd4a9790c522c2f80c9d813884609b89a26e5ac59cc120bf6265ab0e5` |
| `RELEASE-LOG.md` | 8767 | `235e7dd837687f2ceb4bc72ad50e74affacfb4eb928d56cdaaec5d5565ad656b` |
| `SBOM.spdx.json` | 913 | `32bf147eba3c6e8d13710f0f465a26f2a415beaa342a9fb5a1ce5a565d542151` |
| `release-manifest.json` | 43072 | `adf52a140285d49271f1550447df7011ecba36df398568a7b21f0e38be5ead05` |
| `INSTALL-PROMPT.md` | 2267 | `b22feb07af0267eb092cbf2c247fd75c458d8ed86d149639d10c81a30f983b7c` |
| `references/benchmarks/cft0808-edict.yaml` | 1437 | `a9a7632cc242d4b1f822039852ae60b63a28ee5f21fcc6936392384d49ecfb2a` |
| `scripts/check_release_legal.py` | 8615 | `e64cfaf65c0258d044c7044a8b1bce3751a53029ddad26984ef2b8c6ea77349a` |
| `scripts/package_skill.py` | 51351 | `bb22688f5d84852971542d5b204edeccda3b74370a764a3f70bc0252e6daab4b` |
| `scripts/check_package_privacy.py` | 60238 | `a5f5441f528191c78d8b46fc6c62433774cf5ec55219790ad4bf05869aeef348` |
| `scripts/release_payload_manifest.py` | 21399 | `a167bf51a6d50f091221699051aa2a401f33ddcf7bf5607dfb2bfdf33704ba54` |
| `scripts/check_release_manifest.py` | 5770 | `6501d3ad0486c0660881390f28af2227f59b075045159ceffa740475ce3e5be7` |
| `scripts/build_release_artifacts.py` | 16667 | `1c79c8a38a4311dcd512dce04045cb872dab82c0f5bf156160d59e51a541163e` |
| `VERSION` | 10 | `6e20ff2803855acff6e91fd8fe5bd1c4341f51d976bb01c0351ef4350f9ffb74` |

These files are compliance/release declarations, not proof that copyright or relicensing rights are concentrated in one person.

## License text and history audit

The hash table above is the frozen 14:28 preimage snapshot. It is not a claim
that the concurrently edited worktree still has those hashes.

- The current worktree `LICENSE` is 34,523 bytes with SHA-256
  `0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`.
  It is byte-for-byte identical to the GNU AGPLv3 text retrieved from
  `https://www.gnu.org/licenses/agpl-3.0.txt` on 2026-07-16. The project's
  `AGPL-3.0-only` selection is a project notice/metadata decision; the
  canonical license text remains unmodified and contains no project owner or
  maintainer identity.
- Commit `fcb0b3944c91010661156c2a0eaf56c4c0fb63e1` introduced the Apache
  license. `release/beta0.5.10` HEAD
  `040f707e5acc7c12cfcf50afcfc111a7e49a2f00` and tag `beta0.5.9` contain
  blob `b20752a137cd5e8d89b63bcdadbc2ff5fcbf246a` (10,775 bytes; SHA-256
  `b87a529a13d5294f97bb847936a82f39e4f8adae2425a3a5fb5f1a7b75d43e6a`).
  Its non-whitespace token sequence matches the official Apache-2.0 text, but
  its layout is not byte-for-byte canonical.
- Local commit `fcfca0c550deaea5036ed26f652d8862bb8ebd1b` contains the canonical
  Apache-2.0 bytes as blob `d645695673349e3947e8e5ae42332d0ac3164cd7`
  (11,358 bytes; SHA-256
  `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`).
  That commit is on `work/oss-governance-bilingual`, not the current release
  branch.
- Tag `beta0.5.9` has a `LICENSE`; its SBOM and release manifest explicitly
  declare `Apache-2.0`.
- Tag `beta0.5.8` resolves to commit
  `a584aab32eb706c406367b4504b8b3c206f12436`, which has no `LICENSE`,
  `NOTICE`, or SBOM, and its release manifest has no license declaration.
  Within this bounded Git evidence it is therefore
  `LICENSE_NOT_ESTABLISHED_FROM_TAG`, not an established Apache-2.0 release.
  Any different characterization requires separate artifact evidence and
  legal review.
- For project-owned material, the sole recorded legal owner/licensor is
  孙华清. The sole recorded maintainer identity is `@RowlandL` (GitHub ID
  `42199880`); neither identity is expanded beyond those values here.
- The cft0808/edict provenance record and MIT notice remain a separate
  third-party boundary. The AGPL cutover does not convert that upstream
  material to exclusive project property or replace its MIT terms.

This is a provenance and governance audit, not final legal advice. Rights to
relicense project material, the validity and scope of historical grants, and
any external distribution conclusion remain subject to qualified legal review.

## Existing release state

- At the frozen 14:28 preimage, the generated SBOM, manifest, install and release surfaces described `beta0.5.9` and Apache-2.0. Post-preimage AGPL/new-name surfaces must be regenerated or updated through their authoritative producers and then revalidated; this historical inventory does not assert that every concurrently edited working-tree file still has the preimage value.
- `beta0.5.9` is the Git-established historical Apache-2.0 release. `beta0.5.8` predates the repository's license addition and remains `LICENSE_NOT_ESTABLISHED_FROM_TAG` pending separate evidence.
- Commit author metadata is not title evidence and is not used here to expand the recorded owner or maintainer identities.
- The repository currently has no configured remote. The new GitHub remote must not be added until a clean accepted commit and the legal/provenance/package gates pass.

## P0 result

- `LEGAL_PREIMAGE_INVENTORY_GATE=PASS`
- `LICENSE_HISTORY_AUDIT=PASS_WITH_LEGAL_REVIEW_CAVEATS`
- `beta0.5.10_external_distribution_count=0` within the enumerated evidence boundary
- `next_cursor=P1_UPSTREAM_MIT_PROVENANCE_AND_RIGHTS_MATRIX`
