# ADR-0018: The development marker can be applied on its own

**Status:** Accepted

**Date:** 2026-09-08

Extends [ADR-0016](0016-mark-unreleased-with-a-local-segment.md).

## Context

`--mark-dev` was reachable only as the tail of a release: given without a
version or bump argument it was a usage error, `--mark-dev marks the commit
after a release, so it needs a version number or bump argument as well`.

That restriction was inherited, not designed. Under the superseded
[ADR-0008](0008-unreleased-commits-carry-a-dev-version.md) the flag was
`--next {major,minor,patch}` and it *had* to accompany a release, because the
marker was the next version's development release and the tool needed to know
which bump to guess. [ADR-0016](0016-mark-unreleased-with-a-local-segment.md)
removed the guess — the marker is now derived entirely from the version already
in the tree — but the argument requirement stayed behind.

The cost is not hypothetical. A release cut without `--mark-dev` could not be
marked afterwards except by hand, and this repository contains several such
releases.

## Decision

`release --mark-dev` with no version or bump argument marks the current tree:
it sets `<current>+dev` through `uv version`, refreshes the lock file, and
commits, leaving nothing tagged. It is the same code path as the post-release
tail, so the two cannot diverge.

Three behaviours belong to it specifically. It is **idempotent** — a tree that
already carries a local segment reports `already marked as unreleased` and makes
no commit, because asking uv to set the version it already holds produces no
`=>` line and would surface as an unhelpful parse failure. It **refuses a dirty
tree** unless `--allow-dirty` is given, as a release does, because it makes a
commit. And it **says when the commit is not itself a release**, using the
`git describe` machinery from
[ADR-0017](0017-audit-the-tree-against-its-tags.md), since marking an arbitrary
commit is legitimate but the version alone cannot tell the two apart.

`--dry-run` previews it and `-m` sets the commit message, so neither flag is
silently ignored.

## Consequences

Cutting a release and marking the tree are now separable, which suits a tool
whose author drives it by hand: the marker can be applied after the fact, and a
tree released long ago can be brought into the convention without editing
`pyproject.toml` by hand.

`release --mark-dev` on a commit that is not a release is allowed. It is
truthful — that commit is not a release — but it will mark a tree at a version
that was never shipped, and only a printed note distinguishes the cases.

There are now two ways to reach the same state, which is a small surface cost.
They share an implementation, so the risk is documentation drift rather than
behavioural drift.

## Alternatives considered

**Keep the restriction and require a bump.** It forces a release on someone who
wanted only to mark a tree, which is how the current repository ended up with
releases that were never marked.

**A separate command, `mark-dev`.** Cleaner in isolation and it would need its
own argument parsing, its own dirty check and its own tests, to express a
variation the existing flag already covers.
