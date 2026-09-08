# ADR-0009: Only releases are tagged

**Status:** Accepted

**Date:** 2026-09-08

## Context

`--next` deliberately leaves its development commit untagged
([ADR-0008](0008-unreleased-commits-carry-a-dev-version.md)). But `--next` is
not the only way to reach a `.dev` version: `release minor dev` re-aims the
development target, and `release dev` advances the counter, and both of those
went through the ordinary release path — which tags whatever version it
produces. The repository accordingly acquired a tag `r0.8.0.dev1`, on a commit
whose message was "Checking dev release pattern."

A release tag on a development version is a contradiction in terms: the `.dev`
marker exists to say *this commit is not a release*.

It is also dangerous in a way that is invisible locally. A trusted-publishing
workflow of the kind used elsewhere in these projects triggers on a tag glob:

```yaml
on:
  push:
    tags: ["r*"]
```

`r0.8.0.dev1` matches `r*`. Pushing that tag would have published a development
version to PyPI, which accepts `.dev` releases and never lets a version number
be reused. The tag had not been pushed — this repository has no publish
workflow, and its tags were all still local — so nothing escaped. That was luck,
not design.

## Decision

A version whose PEP 440 `dev` component is set is committed but **not tagged**.
`release` prints `<version> is a development version: committed, not tagged`,
and `--dry-run` says `no tag: development version` instead of naming one. The
tag-collision check is skipped, there being no tag.

Release candidates, alphas and betas are *not* affected. They are genuine
releases, they have always been tagged, and they still are.

## Consequences

`release dev` and `release minor dev` keep working, which is the point. The
version still moves; only the tag is withheld. Refusing the whole operation was
tried first and was wrong: it broke the two documented moves the convention in
[ADR-0008](0008-unreleased-commits-carry-a-dev-version.md) depends on.

The distinction is narrower than "pre-release". PEP 440 counts `rc`, `a` and `b`
as pre-releases too, and the suite already asserted that `release patch alpha`
produces the tag `r0.1.1a1`, so a rule phrased as "refuse to tag pre-releases"
would have gone red immediately. The suite decided the question.

There is no override. Every other check here has one — `RELEASE_NOCHECKS` turns
off the dirty-tree guard, the plugin veto and the version-order check — and this
one does not, because there is no circumstance in which a development version
should carry a release tag. If one is ever wanted, `git tag` is right there.

A tag glob is still the wrong place to enforce this. The protection lives in the
tool, so a project that does have a publish workflow is protected by what
`release` will not do, not by how carefully the glob was written.

## Alternatives considered

**Refuse the release outright.** The first implementation. It stops the bad tag
and also stops `release dev`, which is a documented, wanted operation. The
instruction was to refuse the *tag*.

**Narrow the workflow glob instead**, to something that cannot match a `.dev`.
It fixes one repository's workflow and leaves the tool free to keep minting
contradictory tags for every other consumer.

**Refuse every PEP 440 pre-release.** Ruled out by the existing behaviour and
its test: alphas and release candidates are things this project ships.
