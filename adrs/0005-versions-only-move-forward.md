# ADR-0005: A release may never lower the version

**Status:** Accepted

**Date:** 2026-09-08

## Context

Bump names cannot go backwards — `uv version --bump patch` only ever increases.
An *explicit* version argument has no such protection, and `release 0.5.0` at
`0.6.1rc1` was accepted without comment: it rewrote `pyproject.toml`, committed,
and tagged a release whose number was lower than the one before it.

That is not a recoverable mistake once anything has consumed it. Version numbers
are how everything downstream decides what is newer, and a published release
that sorts below its predecessor is invisible to every resolver.

Comparing versions correctly is not a string operation, and it is not obvious
either. `0.6.1` is *newer* than `0.6.1rc1`, so finalising a release candidate
looks like a downgrade to any naive test and must not be refused.

## Decision

`_run_version` in `src/release/setver.py` compares the version uv is about to
write against the one it is replacing, using `packaging.version.Version`
ordering, and raises `VersionOrderError` if the new one is lower. The check sits
in the shared path, so it applies identically to `release`, `release --dry-run`
and `v_next` — a prediction refuses to predict a downgrade rather than
cheerfully reporting one. `RELEASE_NOCHECKS` overrides it.

## Consequences

The whole `.dev` lifecycle in
[ADR-0008](0008-unreleased-commits-carry-a-dev-version.md) is monotonic by
construction, and was verified to be so before it was built:
`0.7.0 < 0.7.1.dev1 < 0.7.1`. Had it not been, this guard would have blocked the
convention.

Finalising a pre-release is correctly allowed, because PEP 440 says `1.0.0` is
greater than `1.0.0rc1`. That is the case that would have been broken by any
cheaper comparison, and it has a test.

The refusal is deliberately not a special case of "bad argument": it propagates
out of `v_next` rather than being flattened into that function's `None`
([ADR-0006](0006-failures-raise-typed-errors.md)), because "that is not a
version" and "that version would go backwards" are different answers and a
caller needs to tell them apart.

Genuine downgrades — a botched version that needs taking back before anyone saw
it — now require `RELEASE_NOCHECKS`. That is the intended friction.

## Alternatives considered

**Compare version tuples directly.** Splitting on dots and comparing integers is
five lines and no dependency. It gets pre-releases wrong in both directions, and
pre-releases are most of what this project does.

**Warn rather than refuse.** The output of a release is already several lines of
uv and git chatter; a warning in the middle of it would be seen after the tag
was written.
