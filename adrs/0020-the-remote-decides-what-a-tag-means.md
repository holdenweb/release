# ADR-0020: The remote decides what a pushed tag means

**Status:** Accepted

**Date:** 2026-09-15

## Context

[ADR-0019](0019-releasing-includes-pushing.md) makes a pushed tag a thing that
actually happens, on purpose, at a known moment. That turns it into a signal
worth acting on — and until now nothing acted on it. CI triggered only on
`push: branches: [main]` and `pull_request`, so it had never once run against a
release commit: the tagged commit either was already on main and tested as part
of an ordinary push, or was not on the remote at all.

The question is what the remote should do with a tag, and in particular which
end of the wire decides whether a release gets published. Putting that decision
in the tool means every repository using `release` inherits one policy, chosen
on a laptop, with credentials that would have to live there. Putting it on the
remote means each repository answers for itself, in a file under review, with
credentials that never leave it.

[ADR-0015](0015-installed-from-git-not-pypi.md) says this project is installed
from git and not published on PyPI — the name is too generic to claim. So the
PyPI half of the question is not live here, but the shape of the answer is, and
the rule it needs is worth writing down while the reasoning is fresh rather
than reconstructed under pressure later.

## Decision

Two jobs, both gated on `github.ref_type == 'tag'`, so a branch push behaves
exactly as before.

**verify-tag** checks the tag against the tree it points at. The tool refuses
to mint a bad tag, but tags get made by hand, and by the time CI sees one there
is nothing left to consult but the tag and that tree. It refuses three things:

- A name that does not match the declared version **as a string**. Not as an
  equivalent PEP 440 version: `Version("01.8.2")` compares equal to
  `Version("1.8.2")`, so an equivalence test would accept a Release titled
  `r01.8.2` containing nothing but `1.8.2` wheels.
- A `.dev` or local version, defence in depth behind
  [ADR-0009](0009-only-releases-are-tagged.md). `git check-ref-format` accepts
  `refs/tags/r1.8.2+dev`, and an `r0.8.0.dev1` was created here by accident
  before that guard covered local segments. Verified against that exact shape.
- A tag without the configured prefix.

**github-release** `needs: [test, verify-tag]`, so nothing is built or attached
unless the tagged commit's own tests pass — which is also what finally puts CI
on the release commit. It builds from the tagged tree with caching disabled,
attests build provenance, and creates a GitHub Release with the sdist and wheel
attached.

**Pre-releases are released, never published.** `rc`, `alpha` and `beta` are
genuine releases and are tagged (ADR-0009), so they get a Release — flagged
`--prerelease`, so nothing reads an rc as the current version. They are not
uploaded to a package index, and that rule stands ahead of the decision to
publish at all: when ADR-0015's PyPI question is reopened, final releases are
the only candidates.

The guard is a module with its own unit tests, not a heredoc inside the YAML. A
shell-quoted script in a workflow can only ever be tested by pushing a tag,
which is the one thing nobody wants to do speculatively.

## Consequences

The decision to publish now lives where the credentials do. Nothing about
publication is configurable from the command line, and `release` needs no
token, no index URL and no knowledge of what happens next: it pushes a tag and
stops.

Every release from here on gets its tests run against the exact commit being
released, which has never previously happened in this repository, and a
downloadable artefact with signed provenance, which it has never had.

The trigger glob `r[0-9]*` hardcodes the prefix, because `on:` accepts no
expressions. If `RELEASE_TAG_PREFIX` is ever changed, this workflow must change
with it, and the failure mode is silent — the tag is pushed and nothing runs.
`verify-tag` reads the prefix from the environment, so the two can disagree.

The workflow is not portable as written. It is this repository's answer, not a
template shipped with the tool, which is the point: another project using
`release` writes its own, and one of them will publish to PyPI.

Deliberately not checked: that the tag is an ancestor of the default branch.
`release --push` sends to the current branch, so a release cut on a side branch
is legitimate and that check would refuse it. It would also refuse `r0.4.1`,
orphaned here by an old `--amend` and whose tree is byte-identical to the
commit that is on `main`.

## Alternatives considered

**Decide in the tool: `release --publish`.** Every repository inherits one
policy and the credentials have to reach the machine cutting the release. It
also makes the most irreversible step in the chain — an upload no index will
let you take back — a flag on a command run casually and often.

**Trigger publication on the tag glob alone, with no verification.** Simplest,
and what most projects do. Rejected because this repository has already
produced an `r0.8.0.dev1` by accident: the glob would have matched it.

**Verify only; attach nothing.** Cheaper, and enough to get CI onto the release
commit. Rejected as a false economy — the build is the thing that proves the
tagged tree is releasable at all, and a wheel that was never built is a claim
nobody checked.

**Require the tag to be reachable from `main`.** Would have caught `r0.4.1`.
Rejected because it also refuses a legitimate release cut on a branch, and
`release --push` explicitly supports that by pushing to the current branch.
