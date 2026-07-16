# Contributing

Status: `LEGAL_REVIEW_REQUIRED`

Contributions must include clear provenance for code, documentation, fixtures,
artwork and generated material. Do not submit content that you do not have the
right to license or distribute. Preserve every applicable third-party notice.

The community edition is licensed under `AGPL-3.0-only`, except for material
that remains under an identified third-party license. Acceptance of a
contribution requires both of the following:

1. A DCO-compatible `Signed-off-by` trailer in each commit, generated through
   the normal commit-signoff workflow.
2. Acceptance of the final, legally reviewed project CLA in [CLA.md](CLA.md)
   through an auditable process. Maintainer review alone does not satisfy this
   gate, and no active acceptance process is claimed by this draft.

The DCO records the contributor's provenance certification. Only a final,
legally reviewed CLA accepted through an auditable process can supply the
non-exclusive inbound rights needed for 孙华清 to distribute, sublicense,
dual-license and commercially license an accepted contribution. The contributor
retains ownership. Neither mechanism grants rights in third-party material that
the contributor does not own or control.

The repository maintainer is @RowlandL (GitHub ID 42199880). Maintainer activity
does not itself accept a CLA or grant commercial terms.

Before submitting a change:

1. Add focused RED → GREEN tests for behavior changes.
2. Run the relevant source, privacy, legal, manifest and package gates.
3. Update PROVENANCE.md for new third-party, generated or artwork inputs.
4. Do not commit credentials, private Shiguan bodies, host logs, local memory
   decisions, user paths, generated runtime state or nested release archives.
5. Keep historical version tags and release artifacts immutable.

The maintainer may reject or remove changes whose provenance, rights, safety or
release evidence cannot be verified.
