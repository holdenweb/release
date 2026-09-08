# ADR-0004: Releases are tagged `r<version>`, and tags are never moved

**Status:** Accepted

**Date:** 2026-09-08

## Context

Every release from `r0.1.1` onwards has carried a tag, and the tag is the only
durable record that a particular commit *is* a release: `pyproject.toml` says
what the version is now, not which commit first claimed it.

The tag was applied with `git tag -f`. The force flag makes re-running a release
quietly succeed by moving an existing tag onto a new commit, which destroys the
only evidence of where the earlier release was. Nothing warned, and nothing in
the output distinguished the two cases.

The prefix was hardcoded. `r` is an unusual choice — most projects use `v` or
nothing — and a tool meant to be pointed at other people's repositories should
not impose it.

## Decision

A release is tagged `f"{TAG_PREFIX}{version}"`, where `TAG_PREFIX` defaults to
`"r"` and is read from `RELEASE_TAG_PREFIX`; an empty setting gives a bare
`1.4.0`. The tag is created with a plain `git tag`, never `-f`, and the tag's
existence is checked *before* anything is mutated, so a collision refuses the
release rather than half-completing it. Only releases are tagged
([ADR-0009](0009-only-releases-are-tagged.md)).

## Consequences

A release that has already been cut cannot be cut again by accident. Re-running
`release patch` when the tag exists stops with the tag named, having changed
nothing.

The tags are *lightweight* — `git tag <name>` creates a ref, not a tag object —
which has a consequence nobody expects until it bites: `git push --follow-tags`
pushes annotated tags only, and therefore silently pushes none of ours. Tags
reach a remote only via `git push --tags` or an explicit
`git push origin r1.2.3`. This is recorded in `BACKLOG.md` because it matters a
great deal to anyone who later wires a tag-triggered publish
([ADR-0015](0015-installed-from-git-not-pypi.md)): `--tags` pushes *every* unpushed
tag at once.

Making the prefix configurable means the branch names in
[ADR-0008](0008-unreleased-commits-carry-a-dev-version.md) deliberately do *not*
use it, so the two namespaces cannot collide however the variable is set.

## Alternatives considered

**Annotated tags.** They carry a message, an author and a date, and they work
with `--follow-tags`. They would be better. The tool has always made lightweight
ones and changing it now would make the existing tags inconsistent with the new
ones for no benefit anybody has asked for; it is a reasonable future change.

**Keep `-f` but warn.** A warning printed during a release that then succeeds is
a warning nobody reads. Refusing is the only version of this that changes what
happens.
