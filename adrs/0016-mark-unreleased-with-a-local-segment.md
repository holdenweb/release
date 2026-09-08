# ADR-0016: Mark unreleased commits with `+dev`, not a guess at the next version

**Status:** Accepted

**Date:** 2026-09-08

Supersedes [ADR-0008](0008-unreleased-commits-carry-a-dev-version.md).

## Context

[ADR-0008](0008-unreleased-commits-carry-a-dev-version.md) marked the commit
after a release with the *next* version's development release — `0.8.1.dev1` —
on a branch named for it. Both halves have since been shown to cost more than
they earn.

The number is a guess, and this repository falsified it in its own log:
`8f1a4ae` is "Begin development of 0.7.3.dev1", and two commits later `5df3003`
is "Release 0.8.0". 0.7.3 was never released as such. This is the known weakness
of setuptools-scm's `guess-next-dev`, which ships a `no-guess-dev` scheme
precisely to avoid it. The sharp edge ADR-0008 itself recorded — that `release
patch` from `0.8.1.dev1` yields `0.8.2`, skipping a version — is the same guess
biting from the other side, and the ADR conceded it "must be carried in the
head", which is the kind of rule this tool exists to abolish.

CPython does not guess. After each release it writes a PEP 440 *local* segment
on the version just shipped — `3.14.7+dev` — which says "past this release, not
yet the next" and names no successor.

The branch was the second cost. It made `main` stop advancing, left HEAD
somewhere other than where the release was cut, and after a re-aim its name
described a version it no longer held. This repository still carries `0.8.0dev`,
a branch whose name does not even match the scheme the code implemented.

## Decision

`release --mark-dev` commits `<released>+dev` on the current branch after the
release commit and its tag. No branch is created, nothing is tagged, and no
claim is made about the next version. The flag is opt-in, as `--next` was.

Because uv carries a local segment through a bump — verified, `0.8.0+dev --bump
patch` gives `0.8.1+dev`, and only an *explicit* version clears it — `release`
strips the marker it put there when cutting the next release, using
`Version(predicted).public`, and applies the cleaned version explicitly. A local
version the caller asked for is left alone.

The tagging guard from [ADR-0009](0009-only-releases-are-tagged.md) is widened
from `.dev` to `.dev or .local`. It had a hole: verified,
`Version("0.8.0+dev").dev` is `None` and `git check-ref-format
refs/tags/r0.8.0+dev` **accepts**, so the marker would otherwise have been
taggable.

## Consequences

The marker asserts only what is true. Ordering still works —
`0.8.0 < 0.8.0+dev < 0.8.1` — so [ADR-0005](0005-versions-only-move-forward.md)
is satisfied, and an artefact built from a marked tree still says plainly that
it is not a release.

`main` advances again, HEAD stays where the release was cut, and there is no
branch whose name can go stale.

The cost is the strip. It is a rule inside the tool rather than one in the
user's head, but it is a rule: a release cut from a marked tree is applied as an
explicit version rather than as the bump the user asked for. Anyone reading
`release patch` in a shell history will not see that.

`+dev` is also not a *unique* marker — every commit between two releases carries
the same string, where `0.8.1.dev1`, `.dev2` at least counted. Distinguishing
commits was never the job; `git describe` does that, and
[ADR-0017](0017-audit-the-tree-against-its-tags.md) now surfaces it.

## Alternatives considered

**Keep `.dev` and drop only the branch.** Halves the cost and keeps the guess. A
`.dev` marker cannot be applied to the version just released — `0.8.0.dev1`
sorts *below* `0.8.0` and the ordering guard would refuse it — so `.dev`
*forces* a guess. That asymmetry is the whole argument.

**Bare `+` as CPython once used.** `Version("0.8.0+")` is not valid PEP 440;
`+dev` is the spelling that parses.

**Keep `--next` as the flag name.** Rejected because the semantics changed
entirely: `--next patch` would have silently become a `patch` bump plus a
boolean. Renaming makes an old invocation fail loudly instead.
