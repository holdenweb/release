# ADR-0003: Version numbers are PEP 440, not semver

**Status:** Accepted

**Date:** 2026-09-08

## Context

The first implementation used `semver`. It is a good library for the scheme it
implements, and that scheme is not the one Python packaging uses. Nothing on
PyPI is a semver version: `1.0.0-rc.1` is spelled `1.0.0rc1`, and PEP 440 has
concepts — epochs, post-releases, development releases, local versions — that
semver has no room for.

The mismatch was not academic. The `semver` version object is a five-field
structure, and when the tool serialised it into `pyproject.toml` what it wrote
was a TOML array (see [ADR-0001](0001-delegate-version-arithmetic-to-uv.md)):

```toml
version = [ 0, 1, 19, "None", "None",]
```

Two of the five fields were the *string* `"None"`. That is the shape of a
version that has been through a translation layer between two models that do not
agree.

## Decision

Versions are PEP 440 throughout, and are never translated. `uv` produces them
([ADR-0001](0001-delegate-version-arithmetic-to-uv.md)) and
`packaging.version.Version` is the only thing that parses or orders them.
`c1300b5` made the switch and `75dcab0` removed "the last vestiges of semver's
involvement". `packaging` is the project's sole runtime dependency, and it is
there to *compare*, never to compute.

## Consequences

The parts of PEP 440 that semver lacks turned out to be the parts this project
is built on. Development releases carry the whole unreleased-commit convention
([ADR-0008](0008-unreleased-commits-carry-a-dev-version.md)); local versions
carry snapshots ([ADR-0010](0010-snapshots-are-local-versions.md)); pre-release
ordering is what makes the monotonic guard safe
([ADR-0005](0005-versions-only-move-forward.md)). None of that would have been
expressible.

What is lost is semver's simplicity. PEP 440 ordering is genuinely surprising in
places — `0.7.1.dev1` sorts *below* `0.7.1`, while `0.7.1+g1a2b3c4` sorts
*above* it — and those two facts, which look alike, are load-bearing in opposite
directions. They are worked out in the records that depend on them rather than
assumed.

## Alternatives considered

**Keep semver internally and translate at the boundary.** The version would stay
a semver object and become a PEP 440 string only when written. This is precisely
what produced `[ 0, 1, 19, "None", "None",]`: the translation layer is where the
bug lived, and keeping two models means keeping it.
