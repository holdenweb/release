# ADR-0021: The audit asks the remote about the tag, not the branch

**Status:** Accepted

**Date:** 2026-11-13

Supersedes the audit clause of
[ADR-0019](0019-releasing-includes-pushing.md); the rest of that record stands.

## Context

ADR-0019 gave a bare `release` a third clause: a warning when the newest
release tag "is not on origin/main". It was built on remote-tracking refs so
that it cost no network call, and that constraint chose the question rather
than the other way round. It resolved the tag to its commit and then asked
whether *that commit* had reached `origin/<branch>`.

That is not the question. Pushing the **tag** is what triggers publication —
[ADR-0020](0020-the-remote-decides-what-a-tag-means.md) puts the workflow on
`push: tags`, and it is the tag that a PyPI upload would hang off. The branch
is incidental. Measured, in a throwaway project with a local bare remote, the
old check was wrong in both directions:

- `git push` by hand, which sends no tags at all: the commit reaches
  `origin/main`, so the check fell **silent** on a release that had published
  nothing. A false all-clear, and precisely the habitual move that produced
  the five unpushed tags ADR-0019 was written about.
- `git push origin r0.2.0`, tag only: the trigger fired and the release
  published, while `origin/main` had not moved, so the check **complained**.

`release --push` moves both refs atomically, so for tool-made releases the two
questions agree and the fault is invisible. It bites exactly the hand-pushed
case the audit exists to catch.

There is no offline answer. Verified: git's default fetch refspec is
`+refs/heads/*:refs/remotes/origin/*` — branches only — and a tag fetched from
a remote lands in `refs/tags/*` indistinguishable from one made locally. There
is no `refs/remotes/origin/tags/*` to read, and `FETCH_HEAD` records only the
last fetch. The question can only be put to the remote.

## Decision

`release_tag_state()` asks the remote, with `git ls-remote` and a five-second
timeout, and distinguishes four answers: the tag is there at the expected
commit (say nothing); the tag is absent (say that nothing has been published);
the tag is there but names a different commit (say that what was published is
not what was released); the remote could not be reached.

The unreachable case is reported, not swallowed. Silence is what this record
exists to remove, and "I could not find out" must not render identically to
"all is well".

No upstream remote means silence and no network call at all, which keeps
ADR-0019's promise that a project deliberately never pushed anywhere is not
nagged.

The remote is read from `branch.<name>.remote` rather than by splitting
`@{upstream}` on its first slash, because a branch name may itself contain
one.

`remote_tag_sha` now resolves to the **commit**. Verified: for an annotated
tag, `ls-remote refs/tags/x` answers with the tag object, not the commit, so
comparing it against a local `rev-list -1` would report every annotated tag as
having moved. The query carries a trailing glob so the peeled `^{}` line comes
back too, and the returned lines are filtered to this exact ref — the glob
over-matches, and `refs/tags/r0.2.0*` also matches `r0.2.0a1`.

## Consequences

A bare `release` is now a network operation, reversing the property ADR-0019
recorded. That was a cheapness constraint, and it bought the wrong answer; the
command is interactive and deliberate, and one `ls-remote` is a round trip, not
a fetch.

Offline, `release` pauses for up to five seconds and then says it could not
reach the remote. That is the cost of not lying.

Only the *newest* release tag is examined, so this says nothing about older
tags left behind — `r0.7.0` through `r1.8.2` in this repository remain
invisible to it. Checking every tag would mean one `ls-remote` per tag, or
listing them all and diffing, which is a different and larger change.

The four outcomes are rendered from a table keyed on the state, so adding an
answer does not mean editing the report's string arithmetic.

## Alternatives considered

**Keep the offline check and reword it**, so it claims only what it measures —
"the release commit is not on origin/main". Honest, and useless: it leaves the
false all-clear in place, which is the dangerous direction.

**Make the remote check opt-in**, behind a flag or an environment variable, and
keep the offline check as the default. Rejected on ADR-0019's own argument
against an opt-in push: a step you have to remember is a step that gets
skipped, and the five unpushed tags are the evidence. An audit nobody runs is
not an audit.

**Configure a tag-tracking refspec** (`+refs/tags/*:refs/remotes/origin/tags/*`)
so the answer becomes local. It would work, but it means writing to the user's
git config, it changes what every other git command in the repository sees, and
the answer would still only be as fresh as the last fetch — so a release pushed
from another machine would read as unpushed.
