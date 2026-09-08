# ADR-0001: Delegate all version arithmetic to uv

**Status:** Accepted

**Date:** 2026-09-08

## Context

`release` began by reading and writing `pyproject.toml` itself. Doing that well
turned out to be harder than the job it was in aid of. On 2025-08-08 the project
cycled through three TOML libraries in a single day: `tomllib` because it is
stdlib (`c0c3c7c`), then away from it because it cannot write (`7222306`), to
`tomlkit` (`6569c8e`), then back to `toml` to get the file written at all
(`80d0cb9`), then a fix because `toml` will not take a binary handle
(`115dfe4`).

The version number itself was a `semver` object, and the writer serialised it
faithfully. What landed in the project's own `pyproject.toml` was:

```toml
version = [ 0, 1, 19, "None", "None",]
```

That is one of *three* distinct ways the writer corrupted the file, and
`pyproject.toml` was repaired by hand four times in a single day:

- **truncated to nothing.** `write_version` opened the file `'wb'` and called
  `toml.dump`, which emits `str`: `open` truncates, then the write raises. The
  empty file was committed — `115dfe4`'s diff shows `index 4b35681..e69de29`,
  git's empty blob — and rebuilt by hand in `785abcd`, "Replace pyproject.tom
  wiped out by earlier bug".
- **the array above** (`54eecd4`), repaired in `70d35be`.
- **a repr.** After `c1300b5` the version reached the writer as a `packaging`
  object, and `c6413d7` wrote `version = "<Version('0.2.0a1')>"`. Repaired in
  `e1ec485`, then written again by the next release, `9ef0b31`.

A release tool had eaten the file that defines the release, three ways.

Meanwhile `uv` was already a hard requirement, and `uv version` already knew how
to do every one of these operations correctly.

## Decision

`release` performs no version *arithmetic*. Every increment shells out to
`uv version`, or `uv version --dry-run` when only a prediction is wanted, and
the answer is read from uv's output. The one version string the tool composes
itself is the snapshot local segment
([ADR-0010](0010-snapshots-are-local-versions.md)), and even that is applied by
handing it to `uv version` to validate and normalise. `_version_command` in
`src/release/setver.py` turns the user's arguments into a uv command line and
nothing else; `_run_version` runs it and parses `name old => new`. The tool owns
the *process* of releasing — the checks, the commit, the tag — and none of the
arithmetic. `3ffb607` is where this arrived: 82 lines deleted, 24 added.

## Consequences

Being wrong about PEP 440 is no longer possible, because we never compute
anything. `release minor alpha` produces whatever `uv version --bump minor
--bump alpha` produces, by construction, which is also why
[ADR-0005](0005-versions-only-move-forward.md)'s guard can trust its inputs.

The cost is that brittleness moved rather than vanished. It now sits in parsing
uv's standard output, which we split on whitespace and expect to be four fields
around a `=>`. A change in that format breaks us, and we would find out at
release time. The mitigation is only that uv's own words are relayed rather than
replaced ([ADR-0006](0006-failures-raise-typed-errors.md)), so a surprise is at
least legible.

`release` also cannot work on a project uv does not understand. That is not a
limitation anyone has minded, because the tool exists to release uv projects.

The three dead TOML libraries left a longer shadow than expected: the exception
classes invented for that era, `TomlProcessingError` and
`VersionValidationError`, outlived the code that raised them by more than a
year, and were still being imported when this record was written.

## Alternatives considered

**Keep the round-trip with a comment-preserving writer.** `tomlkit` exists for
exactly this and would have stopped the file being reformatted. It was tried and
abandoned within hours. It also addresses the easy half of the problem: writing
the file back safely says nothing about what "bump a release candidate from a
development version" should produce, and that semantic half is where the value
is.

**Hand-roll PEP 440 arithmetic on top of `packaging`.** `packaging` parses and
compares versions, which is why it survives as our one runtime dependency, but
it does not bump them. We would be writing the interesting part ourselves, and
`uv` would still be installed and still know the answer.
