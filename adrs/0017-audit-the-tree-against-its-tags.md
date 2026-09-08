# ADR-0017: The tool audits the tree against its tags

**Status:** Accepted

**Date:** 2026-09-08

## Context

Every check in this tool is a *pre*-condition, evaluated at release time
([ADR-0011](0011-refuse-before-mutating.md)). Nothing ever looked at the result
afterwards, and `release` with no arguments printed the one fact that cannot
reveal a problem: the version in `pyproject.toml`.

That gap was found by inspection of this very repository, which had been in an
incoherent state since at least 2026-09-01 without anyone noticing:
`pyproject.toml` said `0.8.0`, there was **no `r0.8.0` tag**, and `r0.7.3`
pointed at a commit three later than the "Release 0.8.0" commit whose file also
said `0.8.0`. `git describe --tags` answered `r0.7.3-2-gfb2ff20`. `release`
answered `release 0.8.0`, and every guard in the tool was satisfied, because
each one is asked before a release rather than about the repository.

Larger projects have no equivalent check and do not need one: their artefact is
built by CI *from the tag*, so a disagreement between tree and tag cannot
survive to a release. This tool cuts releases locally and has no such backstop.

There is a second, related blind spot. The ordering guard
([ADR-0005](0005-versions-only-move-forward.md)) compares the prospective
version against the value in `pyproject.toml` — one line of file edits. It says
nothing about the release history. On a branch, or after a tag made by hand, the
highest tag can already be above the file, and a release below it was permitted.

## Decision

`release` with no arguments reports the version *and* whether this commit is a
release, from `git describe`:

```
demo 0.2.1 -- released as r0.2.1
demo 0.2.0+dev -- untagged; nearest tag r0.2.0-1-gbe43eae
```

and warns if the highest existing tag is above the version in the tree. At
release time, the prospective version must also be strictly above the highest
existing release tag, not merely above the file. Equality is left to the
tag-collision check, which reports it better. `RELEASE_NOCHECKS` overrides.

## Consequences

The command already typed most often now answers the question the version alone
cannot. The state described in the Context would have been visible the first
time it was run.

Both facts are *derived from git*, not recorded anywhere, so this adds no
artefact that can drift — the objection that ruled out a changelog. It is the
opposite of a duplicate record: git holds the pieces, and nothing was comparing
them.

Tag scanning costs one `git tag --list` per invocation, and tags that do not
parse as versions after the prefix is stripped are ignored, since a repository
may carry tags this tool did not create.

The check is still not a *gate*. It reports; it does not prevent a release from
being cut on a red or unpushed commit, and there is deliberately no CI in the
loop.

## Alternatives considered

**Gate the release on CI being green.** What most projects get structurally.
Here it would mean a network round trip inside the one command, a second source
of truth, and a dependency on GitHub in an otherwise offline tool. With nothing
published, a tag on a bad commit costs one `git tag -d`.

**A `release --check` subcommand.** A check nobody runs is not a check. Folding
it into the bare invocation costs nothing and is seen every time.

**Compare against the highest tag *instead of* the file.** The file comparison
catches a downgrade within one branch, which the tag comparison would miss when
a release has not been tagged yet. Both are cheap; both are kept.
