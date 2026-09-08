# ADR-0010: Snapshots are local versions, built and discarded

**Status:** Accepted

**Date:** 2026-09-08

## Context

`--allow-dirty` lets a release proceed with uncommitted changes, but the commit
it makes stages only `pyproject.toml` and `uv.lock`. The dirty changes are not
in it. The result is a tagged release whose tag points at a commit that does not
contain the code that was built — a number that claims to be a pristine release
and is not.

What was actually wanted was a way to build and share an in-progress tree
without pretending it was a release.

PEP 440 has exactly this: a *local version identifier*, `1.4.0+g1a2b3c4`. The
ordering was checked before anything was built. For any public version `X`,
`X < X+local`, so a local build of the *next* release would sort **above** the
real release when it arrived — a consumer offered both would prefer the
throwaway. Basing the snapshot on the *current* version avoids that entirely:
`1.4.0+g1a2b3c4.dirty` sits above `1.4.0` and below `1.4.1`.

## Decision

`release --snapshot` builds a wheel of the **current** version labelled with the
git checkout id — `<current>+g<sha>`, with `.dirty` appended when tracked files
differ from HEAD. It takes no bump argument, because it releases nothing. It
stamps the local version into `pyproject.toml` only long enough to run
`uv build`, then restores it in a `finally`; nothing is committed and nothing is
tagged.

## Consequences

An in-progress build can be handed to somebody, and its version says exactly
what it is and which tree it came from.

Public indexes reject local versions on upload. That is the safety rail, not a
limitation: a snapshot is installable from a file, a URL or a private index, and
cannot be published by accident.

Stamping and restoring `pyproject.toml` is inelegant, and it is the reason
build-time versioning (`hatch-vcs`) exists. It was verified not to leave a mark:
a clean tree is still clean afterwards, because `uv version` preserves
formatting. A hard kill mid-build would strand the local version in the file,
which is the residual risk of doing it this way.

Restoring the version afterwards is, in PEP 440 terms, a *downgrade*:
`1.4.0` is lower than `1.4.0+g1a2b3c4`. The restore therefore calls `uv version`
directly rather than going through `update_project_version`, deliberately
bypassing [ADR-0005](0005-versions-only-move-forward.md)'s guard. It is the one
place in the tool where a safety check is routed around on purpose, and it is
commented as such.

"Dirty" means tracked files differ from HEAD. Untracked files are not
considered, so a snapshot can be labelled clean while an untracked file sits
beside it.

`--snapshot` does not remove the underlying problem with `--allow-dirty`; it
gives that use a better answer.

## Alternatives considered

**Dynamic versioning with `hatch-vcs`.** The proper fix: `pyproject.toml` is
never touched and the version is derived from git at build time. Rejected for
the same reason as in [ADR-0002](0002-pyproject-toml-is-the-source-of-truth.md) —
it changes how every build resolves its version, not just snapshots.

**Base the snapshot on the next release rather than the current one.** Reads
more naturally — "this is heading for 1.5.0" — and sorts *above* the real
`1.5.0` when it ships, which is exactly backwards. Expressing "heading for" needs
a `.dev` base, which is [ADR-0008](0008-unreleased-commits-carry-a-dev-version.md)'s
job.

**Use `git stash create` for a true content hash of the dirty tree.** It gives a
different id for different uncommitted states, where `+g<sha>.dirty` does not.
Rejected as more precision than the use warrants, and it still misses untracked
files.
