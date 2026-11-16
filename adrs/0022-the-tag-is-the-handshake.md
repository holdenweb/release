# ADR-0022: `release` cuts, the remote publishes, and the tag is the handshake

**Status:** Accepted

**Date:** 2026-11-16

## Context

[ADR-0020](0020-the-remote-decides-what-a-tag-means.md) put the publication
decision on the remote, and gave this repository a workflow to act on a pushed
tag. It settled what *this* project does. It did not say what the division of
labour is in general, and the estate this tool was written for has an answer of
its own that nobody compared with it.

The podpack applications publish to PyPI through two mechanisms neither of which
involves this tool. `tools/publish.py` — present in seven sibling repositories
— builds into a clean `dist/` and refuses an upload unless exactly one version
is present, it matches `pyproject.toml`, the tree is clean, the release tag
exists, and the version is not already on PyPI. Alongside it,
`.github/workflows/publish.yml` triggers on `tags: ["r*"]`, checks the tag
against the declared version, runs the tests, builds, and uploads with PyPI's
trusted publishing. Its own header describes releasing as "bump the version,
commit, tag `r<version>`, push the tag".

That sentence is this tool's entire job, and nothing in those repositories calls
it: no podpack repository references `release` at all, so the bump, the commit
and the tag are all made by hand. The two halves already meet at the tag, and
the seam has simply never been written down.

The cost of leaving it unwritten has now been paid twice. podpack-mail's first
release, 0.1.0, was one hand-made commit reverting the version from `0.1.0+dev`
(recorded in [BACKLOG.md](../BACKLOG.md), with the defect that forced it). And
podpack-mail's `publish.yml`, copied byte-for-byte from a sibling, cites
`tools/publish.py` in a repository that has no `tools/` directory at all.

There is also a real gap where the two overlap. Measured against both scripts:

| tag / declared version | `publish.yml`'s shell check | this tool's `verify_tag.py` |
|---|---|---|
| `r0.1.0.dev1` / `0.1.0.dev1` | **passes** | refuses |
| `r0.1.0+dev` / `0.1.0+dev` | **passes** | refuses |
| `r01.8.2` / `1.8.2` | refuses | refuses |

The local-version row fails late, since PyPI rejects local versions on upload.
The `.dev1` row does not: that is a valid upload, and it would permanently
occupy that version on an index that never forgets. The guard that catches it
exists here because an `r0.8.0.dev1` tag was once created in this repository by
accident.

## Decision

`release` owns everything up to and including the pushed tag: the version
arithmetic ([ADR-0001](0001-delegate-version-arithmetic-to-uv.md)), the source
of truth ([ADR-0002](0002-pyproject-toml-is-the-source-of-truth.md)), the
ordering guard ([ADR-0005](0005-versions-only-move-forward.md)), the tag
([ADR-0004](0004-releases-are-tagged.md),
[ADR-0009](0009-only-releases-are-tagged.md)), the push
([ADR-0019](0019-releasing-includes-pushing.md)) and the audit
([ADR-0021](0021-the-audit-asks-the-remote-about-the-tag.md)).

The remote owns everything after it: verification, build, and publication to
whatever index that project uses.

**The tag is the only interface between them.** `release` writes no workflow,
holds no credential, and knows the name of no index. A tag-triggered workflow
does no version arithmetic and creates no tag. Neither reads the other's
configuration; a pushed tag is the whole of the message.

Two rules follow, and they bind anything on the far side of that interface:

- A workflow acting on a release tag must apply at least the checks
  `verify_tag.py` makes: the tag names the declared version *as a string* (PEP
  440 equivalence is not enough — `Version("01.8.2") == Version("1.8.2")`), and
  development versions are refused outright. A shell equality test is not
  sufficient, as the table above shows.
- The tag prefix is fixed in a workflow's `on:` glob, because `on:` accepts no
  expressions. If `RELEASE_TAG_PREFIX` changes for a project, that project's
  workflow changes with it, and the failure mode is silent — the tag is pushed
  and nothing runs.

A repository adopting this tool therefore keeps its own publish workflow. It
does not inherit one, and this tool does not scaffold one.

## Consequences

"Which thing releases this project?" has one answer: `release` cuts, the remote
publishes. The hand-made commit that prompted this record was not a shortcut
past a working procedure, but it was a shortcut past an *unstated* one.

Publication policy stays per-repository, where the credentials are, which is
the point of ADR-0020 generalised. One estate can publish to PyPI while this
project — whose name is unobtainable there
([ADR-0015](0015-installed-from-git-not-pypi.md)) — attaches artefacts to a
GitHub Release, and neither needs the other to change.

This tool stays ignorant of PyPI, so it can offer nothing when an upload fails.
The remote's logs are the only place to look, and the tool will not say so
because it does not know an upload was attempted.

Nothing is shared as code by this decision. The `verify_tag.py` guard is worth
sharing and the second rule above requires its substance, but lifting it into
the podpack workflow is a separate change in a separate repository. Writing the
seam down also does nothing about eight byte-identical workflow files, which
will keep drifting until one of them is called rather than copied.

`release` is not yet adopted anywhere in the podpack estate, and cannot be for a
*first* release until the marker defect in BACKLOG.md is fixed: a tree already
carrying `0.1.0+dev` can never ship `0.1.0`.

## Alternatives considered

**Put publication in the tool — `release --publish`.** Rejected in ADR-0020 and
restated here, because the estate's `tools/publish.py` is precisely that shape
and the obvious way to "reconcile" would be to converge on it. It would make
every repository inherit one policy, bring credentials to the machine cutting
the release, and put the least reversible step in the chain behind a flag on a
command run casually and often.

**Put the cut in the workflow** — bump and tag in CI on a dispatch, so one
mechanism does everything. It moves version arithmetic away from the working
tree that ADR-0002 makes the source of truth, and makes `v_next` and
`--dry-run` unanswerable on a laptop, which is where the question is asked.

**Have the tool own the workflow file**, scaffolding `publish.yml` into each
repository it is used on. Tempting: it would have prevented podpack-mail's
reference to a script that is not there. Rejected because it makes this tool
responsible for each project's publication policy, which is the thing this
record declines. A reusable `workflow_call` workflow, called by each app
instead of copied into it, solves the drift without involving the tool at all.

**Leave it unwritten.** It was unwritten, and the result was a release cut by
hand in a repository whose workflow refers to a script it does not contain.
