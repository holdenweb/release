# Architectural decision records

Why `release` is the way it is. The interface is described in
[`README.md`](../README.md); what is deliberately not done yet is in
[`BACKLOG.md`](../BACKLOG.md); this directory holds the reasoning, and is not
rewritten when a decision changes — a new record supersedes the old one.

Start with [ADR-0000](0000-template.md) for the format and the conventions.

**Where the version comes from**

- [ADR-0001](0001-delegate-version-arithmetic-to-uv.md) — delegate all version arithmetic to uv
- [ADR-0002](0002-pyproject-toml-is-the-source-of-truth.md) — pyproject.toml is the source of truth for the version
- [ADR-0003](0003-pep-440-not-semver.md) — version numbers are PEP 440, not semver

**What a release is**

- [ADR-0004](0004-releases-are-tagged.md) — releases are tagged `r<version>`, and tags are never moved
- [ADR-0005](0005-versions-only-move-forward.md) — a release may never lower the version
- [ADR-0009](0009-only-releases-are-tagged.md) — only releases are tagged

**Between releases**

- [ADR-0016](0016-mark-unreleased-with-a-local-segment.md) — mark unreleased commits with `+dev`, not a guess at the next version
- [ADR-0008](0008-unreleased-commits-carry-a-dev-version.md) — ~~unreleased commits carry a `.dev` version, on their own branch~~ *(superseded by 0016)*
- [ADR-0010](0010-snapshots-are-local-versions.md) — snapshots are local versions, built and discarded

**How it behaves**

- [ADR-0006](0006-failures-raise-typed-errors.md) — failures raise typed errors, reported at one boundary
- [ADR-0011](0011-refuse-before-mutating.md) — refuse before mutating, and say what was left behind
- [ADR-0017](0017-audit-the-tree-against-its-tags.md) — the tool audits the tree against its tags
- [ADR-0012](0012-capture-to-interrogate-inherit-to-mutate.md) — capture output to interrogate, inherit it to mutate
- [ADR-0007](0007-plugins-are-entry-points-and-ship-disabled.md) — plugins are entry points, and none ship enabled

**How it is built and shipped**

- [ADR-0013](0013-tests-drive-real-uv-and-git.md) — tests drive a real uv project under real git
- [ADR-0014](0014-one-project-per-repository.md) — one project per repository *(Deferred)*
- [ADR-0015](0015-installed-from-git-not-pypi.md) — installed as a uv tool from git, not published on PyPI *(Deferred)*
