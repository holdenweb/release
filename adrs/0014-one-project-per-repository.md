# ADR-0014: One project per repository

**Status:** Deferred

**Date:** 2026-09-08

## Context

`release` assumes three things are the same directory: the project root holding
`pyproject.toml`, the git root, and the location of `uv.lock`. That is true of a
plain single-project repository, which is every repository it has been used on.

Two other shapes are broken, both reproduced:

**A project in a subdirectory of its repository.** git commands run in the
current directory with bare relative paths, so `git add uv.lock pyproject.toml`
fails from anywhere but the project root — after the version has been bumped:

```
fatal: pathspec 'uv.lock' did not match any files
```

**A uv workspace member.** `uv version` correctly reports and updates the
member, but `uv.lock` lives at the *workspace* root, so the same `git add` fails
even standing in the member's own directory, with no subdirectory involved at
all.

The obvious fix is wrong, which is the main reason this record exists. Anchoring
on the **git root** makes matters worse: in a repository whose project sits in a
subdirectory, `uv version` at the git root fails outright with *"No
`pyproject.toml` found in current directory or any parent directory"*. The right
anchor is the project root, and uv will not tell us where that is —
`uv version --output-format json` returns the package name and version and no
path.

## Decision

Not fixed. "One project per repository" is a documented limitation, stated in
`README.md` under Requirements, with the detail and the shape of a fix recorded
in `BACKLOG.md`.

The trigger to revisit is distribution: if `release` is ever installed by
someone other than its author, they will point it at layouts nobody here has
tried, and the failure mode — version bumped, commit impossible — is unpleasant
enough to fix before that rather than after.

## Consequences

The tool stays smaller, and every git operation can go on using relative paths
and the current directory.

Anyone who hits it gets a confusing failure: the message names the pathspec, not
the cause, and the version has already moved. That is the cost of deferring, and
it is why the limitation is in `README.md` where an installer will see it rather
than only in the backlog.

The fix, when wanted, needs two paths resolved rather than one — the project
root for `pyproject.toml`, the vet walk and `uv build`'s output, and the lock
file at the nearest ancestor whose `pyproject.toml` carries a
`[tool.uv.workspace]` table. Both `tomllib` and `contextlib.chdir` are stdlib on
the supported Python, so it is cheap; it is simply not needed yet.

## Alternatives considered

**Fix it now.** The work is contained and understood. It was declined because
the supported layout covers every current use, and speculative generality in a
release tool is how you get a release tool that fails in a new way.

**Anchor on the git root.** Rejected on evidence: it breaks the subdirectory
case it was meant to fix.

**Refuse to run in an unsupported layout.** Detecting the layout is most of the
work of supporting it, and a refusal helps nobody who has already hit it.
