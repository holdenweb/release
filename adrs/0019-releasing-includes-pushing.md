# ADR-0019: A release is not finished until it is on the remote

**Status:** Accepted

**Date:** 2026-09-15

## Context

`release` said it had released something after writing a version, making a
commit and moving a local ref — three operations entirely inside one laptop.
The word was doing work the tool did not do, and this repository is the
evidence. When this was written `main` was eight commits ahead of
`origin/main`, and of eleven local tags running to `r1.8.2`, `git ls-remote`
showed the remote holding none past `r0.6.0`.

That is not cosmetic. [ADR-0015](0015-installed-from-git-not-pypi.md) makes a
pushed tag the *only* supported way to install a release, and its own worked
example is `uv tool install git+https://github.com/holdenweb/release@r0.7.2` —
a tag the remote does not have. The documented install has been failing for
every release since `r0.6.0` and nothing ever said so.

The symptom that prompted this was different, and on its face wrong: that
`--mark-dev` makes it impossible to push the release commit without checking it
out and hiding the marker. It does not. Verified from a marked tip, `git push
origin r0.2.0` exits 0, sends the release commit and its tag, leaves
`origin/main` alone, and touches neither HEAD nor the working tree.

What is true is that nothing in the tool had ever mentioned a remote — bare
`release` printed byte-identical text whether the tag was pushed, unpushed, or
the remote deleted — and that the three obvious spellings of "push the release"
each fail differently and quietly. Measured: `git push` sends the branch and
zero tags; `git push --follow-tags` sends the branch, zero tags, and exits 0
with no warning, because our tags are lightweight
([ADR-0004](0004-releases-are-tagged.md)); `git push --tags` sends every
unpushed tag and does not move the branch. Nobody keeps running a command whose
last three spellings gave no usable signal.

## Decision

`release --push` sends the release it has just cut. It is one opt-in flag, off
by default, and it issues exactly one command, after `git tag` and before
`mark_development`:

    git push --atomic <remote> <sha>:refs/heads/<branch> \
        refs/tags/<tag>:refs/tags/<tag>

`--atomic` is load-bearing and the measurement is the argument. Against a
receiving hook that declines branches but not tags, a plain multi-ref push
applies the refs independently: the branch is rejected and **the tag lands**,
leaving the remote holding a release tag on a commit its branch does not
contain — precisely what a tag-triggered publish would then build from
([ADR-0020](0020-the-remote-decides-what-a-tag-means.md)). With `--atomic`, the
same push leaves no refs at all.

The branch refspec names the release commit's id. This is **not** what keeps
the `+dev` marker off the remote — the ordering does that, and mutation testing
proved it: the push runs before the marker is made, so `<branch>:refs/heads/…`
sends the same object and every test still passes. What the id buys is a
recovery command that stays correct. The consequence message on a failed push
prints the command to finish by hand, and it may be run hours later, by which
time the branch has moved on to the marker or the next day's work.

Everything refusable is asked at [ADR-0011](0011-refuse-before-mutating.md)'s
existing gate, beside the dirty-tree and tag-collision checks: a remote is
configured, HEAD is on a branch, the tag is not already on the remote, and the
branch would fast-forward. The third is a genuinely new guard — `git_ref_exists`
reads only local refs, so a tag existing solely on the remote passed it, and the
release would be cut, committed, tagged and *then* refused. `--remote NAME`
chooses where; `RELEASE_NOCHECKS` overrides none of it.

Because the flag is opt-in it can be forgotten, which is how five tags
accumulated. The mitigation is not a default but visibility:
[ADR-0017](0017-audit-the-tree-against-its-tags.md)'s audit gains a third
clause, `! r1.8.2 is not on origin/main (as of your last fetch)`, read from
remote-tracking refs with no network call. Unlike any default, that also
catches the releases already cut.

## Consequences

The remote's branch tip becomes the release commit rather than the marker, so a
bare `git+https://…` install stops reporting a `+dev` version — the sharp edge
ADR-0015 records. The marker stays exactly one commit local, which `git status
-sb` shows as `ahead 1`.

The push carries every ancestor commit on the branch, at a moment chosen by a
version bump rather than deliberately. Pushing a commit while withholding its
parents is not something git can do, so this is a cost to be known, not fixed.

`--dry-run --push` becomes a network operation, twice — `ls-remote` and a dry
push. Rehearsing the destination is most of the flag's value, so that is bought
knowingly. Bare `release` stays offline.

The preflight is incomplete and must not be read otherwise: `git push
--dry-run` does not run the receiving repository's hooks. Measured against a
bare remote whose `update` hook declines `refs/heads/main`, the dry run exits 0
and the real push exits 1. Branch protection is undetectable in advance; the
atomic push and its consequence message are the actual guard.

Two exit codes join the promised set: 5, refused before anything was written; 6,
the release is committed and tagged here but no ref on the remote moved. Without
them a caller cannot tell "nothing happened" from "cut locally, never sent",
which is the one partial state worth scripting against. The message says "no ref
was updated" rather than "the remote rejected it" (git exits 1 for client-side
refspec errors too) or "nothing reached the remote" (false — a hook-declined
atomic push has already transferred the objects; it simply moves no refs).

Releases cut before this existed are not retrospectively pushed, and the
decision has been taken not to push them: `r0.7.0` through `r1.8.2` stay local,
so ADR-0015's worked example remains broken for those versions.

## Alternatives considered

**Push by default, with `--no-push`.** The most literal reading of "the release
operation includes push", and the one originally proposed. Rejected: every flag
this tool has is affirmative and opt-in, and this would be the first negative
one; `just test` cuts releases in a project with no remote, where even a
tag-only push exits 128; and the options are asymmetric — promoting an opt-in
flag to a default later is two lines and a superseding record, while demoting a
default costs a year of unrecallable pushes to discover it was wrong.

**A separate `release --push <tag>` verb, sending a release cut earlier.**
Cleanly separates the reversible act from the irreversible one, and would drain
the existing backlog. Rejected because separation is precisely the status quo —
`release`, then `git push` — that produced the backlog. Renaming the second
command does not supply the discipline it needs.

**Push the tag alone.** Enough for the pinned install and nothing else. It
leaves the remote's branch arbitrarily stale, and a plain `git fetch` in an
existing clone retrieves neither the tag nor its commit until someone thinks to
run `git fetch --tags`.

**Make tags annotated and use `--follow-tags`.** ADR-0004's rejected
alternative, and a remote that acts on tags is the benefit it lacked. Still
rejected: naming both refspecs explicitly makes the flag unnecessary, and
`--follow-tags` deliberately omits tags unreachable from the branch — this
repository has one, `r0.4.1`, orphaned by an old amend — which is a silent
omission either way.
