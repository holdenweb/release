# ADR-0008: Unreleased commits carry a `.dev` version, on their own branch

**Status:** Accepted

**Date:** 2026-09-08

## Context

Once a release is tagged, its version stays in `pyproject.toml` for every commit
that follows. An edited-but-unreleased tree is therefore indistinguishable, *by
version*, from the release itself — the observation that started this: "at
r0.6.1rc1 I don't remember building 0.6.1". A build made from such a tree claims
to be the release and is not.

`git describe --exact-match --tags HEAD` already answers "is this commit a
release?", and answering it that way costs nothing. The first design here was an
*automatic* post-release bump, and it was rejected for exactly that reason: it
adds a commit to every release and a rule to remember, to record something git
already knows. The objection was put as "aren't we in danger of creating a
mindless operations team?"

What survived the objection was the opt-in form. The information is not missing
from git; it is missing from `pyproject.toml`, which is the one place that
cannot help being stale, and which is what a *built artefact* carries.

uv's behaviour then constrained the shape. Measured, not assumed:

| from | bump | to |
| --- | --- | --- |
| `0.7.0` (a release) | `dev` | **error** — uv demands it be chained |
| `0.7.0` | `patch dev` | `0.7.1.dev1` |
| `0.7.1.dev1` | `stable` | `0.7.1` |
| `0.7.1.dev1` | `patch` | `0.7.2` — **skips 0.7.1** |
| `0.7.1.dev1` | `minor dev` | `0.8.0.dev1` (re-aim) |

## Decision

`release --next {major,minor,patch}` is optional and off by default. After the
release has been committed and tagged, it creates a branch, checks it out, and
commits the next development version there — leaving the release commit and its
tag on the branch released from. The bump is always chained (`patch` then
`dev`), because uv rejects a bare `dev` from a release.

The branch is named for the version left in `pyproject.toml` with the dev
counter dropped: `0.8.1.dev1` gives branch `0.8.1.dev`. It carries no tag
prefix, so branch and tag namespaces cannot collide however
`RELEASE_TAG_PREFIX` is set ([ADR-0004](0004-releases-are-tagged.md)).

## Consequences

Every commit after a release carries a `.dev` version, so an unreleased tree is
obvious at a glance and a wheel built from one is honestly labelled. This showed
its worth immediately: installing from a bare git URL picked up `0.7.3.dev1`
rather than the release, and *said so* — before this convention the same
mistake would have reported a release number.

The sequence is monotonic throughout — `0.7.0 < 0.7.1.dev1 < 0.7.1` — so
[ADR-0005](0005-versions-only-move-forward.md) never fires against it. That was
checked before the feature was written, not after.

Dropping the counter from the branch name means the branch survives `release
dev` advancing to `.dev2`, `.dev3`. It also means the name records where
development *started*, so after a re-aim the branch may be called `0.8.1.dev`
while holding `0.9.0.dev1`. That is mildly untidy and was accepted.

The sharp edge is the fourth row of the table: from a `.dev` version, `release
patch` yields `0.7.2` and silently skips `0.7.1`. `stable` is the finaliser.
This is documented in `README.md` with a warning, and is the one thing about the
convention that must be carried in the head.

`main` no longer advances on its own — development happens on the dev branch and
`main` sits on the last release until fast-forwarded. HEAD is left on the *dev*
branch, not returned to the one released from. That is a real workflow change
and the reason `--next` is opt-in rather than default.

The branch is created after the release has been committed and tagged, so a
collision with an existing branch cannot undo the release. It is reported as
`the release itself succeeded and is tagged, but the next development version
was not opened` — an instance of the rule in
[ADR-0011](0011-refuse-before-mutating.md) that a message must describe the
state actually left behind.

## Alternatives considered

**Do it automatically after every release.** Rejected as above: ceremony
installed by a tool whose job is to remove it.

**Base the dev version on the *next* release number rather than the current
one** — snapshot `1.5.0.dev1` while heading for `1.5.0`. Sound, and it is what
`--next` does. The related trap is worth recording: a *local* version of the
next release (`1.5.0+g1a2b3c4`) would sort *above* the eventual `1.5.0`, which
is why [ADR-0010](0010-snapshots-are-local-versions.md) bases snapshots on the
current version instead.

**Tag the dev commit as well.** Considered and firmly rejected; see
[ADR-0009](0009-only-releases-are-tagged.md), which was written after doing it
by accident.
