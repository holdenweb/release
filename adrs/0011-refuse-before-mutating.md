# ADR-0011: Refuse before mutating, and say what was left behind

**Status:** Accepted

**Date:** 2026-09-08

## Context

A release is half a dozen irreversible-ish steps in a row: write the version,
re-lock, stage, commit, tag. Anything that fails after the first of those leaves
the tree in a state the user did not ask for and did not see happen.

The tool used to fail in the middle routinely and then describe it wrongly. The
tag was applied last, and the tag-collision check happened *after* the version
had been bumped and committed — so re-releasing an existing version got as far
as a commit before stopping. Every failed step appended the same words, "release
aborted", including the ones after `pyproject.toml` had already been rewritten.
Reproduced at the time: quitting the commit editor without saving produced
`release: git commit failed; release aborted`, with `pyproject.toml` sitting at
the new version and both files staged. The release had not been aborted; it had
been left halfway.

## Decision

Every check that can refuse a release runs before anything is written. The
prospective version is obtained with a dry run, and the tag's existence, the
working tree's cleanliness and the plugin verdict are all established from that
— so a refusal costs nothing and changes nothing. The order inside `release()`
is: validate arguments, load plugins, read the current version, predict, probe
the tag and the tree, *(a dry run returns here)*, run the vet loop, enforce the
dirty check, enforce the tag check, and only then mutate.

Past that point, every step reports the state it actually left. `StepFailed`
carries a `consequence` as well as a step name, and each mutating call supplies
one: nothing changed yet; `pyproject.toml` has already been set to X and is not
committed; X is committed but NOT tagged; the release succeeded but the next
development version was not opened.

## Consequences

A refusal is genuinely free. `release patch` against an existing tag stops with
the tag named and the version untouched, where it used to stop with a commit
already made.

A message can no longer lie about the state of the tree, which is the property
that makes the tool safe to run when unsure. Where recovery is a single command,
the message says which: *"put it back with `git checkout pyproject.toml
uv.lock`"*.

The ordering has a consequence nobody chose deliberately and which is worth
knowing: a plugin veto outranks a dirty tree, because the vet loop runs first.
A tree that is both dirty and vetoed reports the veto.

The dry run is a second `uv version` invocation on every release. That is a few
milliseconds, and it buys the ability to check the tag before touching anything.

Failures are still possible mid-sequence — a `git commit` can fail after
`uv lock` has run — and nothing rolls back. The decision is to *describe*
accurately, not to make the sequence atomic, which git cannot offer anyway.

## Alternatives considered

**Roll back on failure.** Undo the version write when a later step fails.
Tempting and unsound: by the time `git commit` fails the tree may contain the
user's own staged work, and a tool that runs `git checkout` on their behalf to
tidy up can destroy it. Telling them precisely what to undo is safer than
undoing it.

**Check the tag last, where the tagging happens.** Simpler code, and it means
discovering the collision after the commit — which is what used to happen.

**One generic failure message.** What "release aborted" was. It is one string
instead of five, and four fifths of the time it is false.
