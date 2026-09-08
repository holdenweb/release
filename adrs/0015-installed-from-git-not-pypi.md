# ADR-0015: Installed as a uv tool from git, not published on PyPI

**Status:** Deferred

**Date:** 2026-09-08

## Context

`release` is installed with `uv tool install`, either from a clone or straight
from the GitHub URL. That works, and it has two sharp edges that only showed up
in use.

A bare git URL installs the **default branch's HEAD**, not the last release. Once
[ADR-0008](0008-unreleased-commits-carry-a-dev-version.md) put a `.dev` version
on every post-release commit, that became visible rather than silent: installing
from GitHub reported `release 0.7.3.dev1`, and *said so*. Before the convention
the same mistake would have reported a release number. Pinning the ref —
`uv tool install git+https://github.com/holdenweb/release@r0.7.2` — installs the
release, and requires that the tag has been pushed.

The natural next step is PyPI, and it is blocked on the name. No project called
`release` exists there, but the name is not obtainable: it is judged too
generic. Publishing would mean renaming the distribution, which is a different
and larger decision than adding a workflow.

## Decision

Not published. `release` is installed as a uv tool from a git ref, and
`just install` builds the last *tagged* release rather than the working tree —
`git archive <tag> | tar -x` into a temporary directory, then `uv build` — for
the same reason the `.dev` convention exists: between releases the tree runs
ahead, and `dist/release-<current version>.whl` names an artefact that was never
built.

The trigger to revisit is wanting other people to install it, which would first
require choosing a different distribution name.

## Consequences

Installation needs a git URL and, for a release rather than a tip, a tag that
has been pushed. There is no `pip install release`, and there will not be under
that name.

`release` therefore has no publish workflow, which means its local tags trigger
nothing and can sit unpushed indefinitely. That is a comfortable state and it is
the reason the hazards below are recorded rather than felt: elsewhere in these
projects, pushing a tag *is* the publish trigger.

Two things must be true before any such workflow is added here, both recorded in
`BACKLOG.md`. `git push --tags` pushes *every* unpushed tag at once, so with a
tag-triggered publish it would fire one run per tag; tags should be pushed
individually. And `git push --follow-tags` pushes annotated tags only, so it
silently pushes none of ours ([ADR-0004](0004-releases-are-tagged.md)).

The third protection is in the tool rather than the workflow: because a `.dev`
version is never tagged ([ADR-0009](0009-only-releases-are-tagged.md)), a glob
as loose as `r*` cannot match a development version. That was learned by
creating exactly such a tag by accident.

## Alternatives considered

**Publish under a different name** — `holdenweb-release`, or similar. The
obvious route if distribution is ever wanted. Not chosen now because nobody
outside this machine needs it, and a name is hard to change afterwards.

**Publish to a private index.** Solves distribution without the name problem and
adds infrastructure to maintain for one user.

**Install from a built wheel by hand.** What `just install` does, and it is
enough for one user; it just is not distribution.
