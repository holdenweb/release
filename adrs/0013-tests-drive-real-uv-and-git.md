# ADR-0013: Tests drive a real uv project under real git

**Status:** Accepted

**Date:** 2026-09-08

## Context

For most of its life the project had no automated tests. What it had was a
shell script, `tests`, and a `just test` recipe that created a temporary
project, ran a few releases and compared version strings by hand. Neither ran
unless someone remembered, and the shell script had a `trap` referring to
variables set two lines later.

The tool is almost pure integration: it is a sequence of `uv` and `git`
invocations and the parsing of their output. Mocking `subprocess` proves that we
build the command line we think we build, and nothing about whether uv agrees.
Most of the real bugs found in this project — that `uv version --bump dev`
errors from a release; that `patch` from a `.dev` silently skips a version; that
`uv version` can rewrite `pyproject.toml` *and* exit non-zero — are facts about
uv that no mock would have told us.

## Decision

The suite is pytest. The `uv_project` fixture builds a genuine throwaway project
for each test: `uv init --lib`, `git init`, an identity, an initial commit, and
the working directory switched into it. Tests then call `release()` in-process
and inspect the resulting `pyproject.toml`, commits and tags. Tests needing a
real interpreter boundary — anything depending on an environment variable read
at import time — run the CLI in a subprocess instead.

Tests that need `uv` and `git` are marked `integration`, so
`pytest -m "not integration"` gives a fast unit subset. Of 90 tests, 62 are
integration and 28 are not.

## Consequences

The suite exercises the real thing, and has repeatedly caught behaviour that
reading the code would not have revealed. Each new guard was checked by running
the new tests against the *old* code first and confirming they went red: the
dotfile fix produced three failures against the previous walk, the
`RELEASE_NOCHECKS` change nine, the exception refactor ten. A test that cannot
fail is not evidence, and these were made to fail before they were trusted.

It is slow — about thirteen seconds — because every integration test resolves a
real project, and the snapshot test runs a real `uv build`. It also cannot run
where `uv` and `git` are absent, which is a real constraint on where CI can run
and an accepted one.

The fixture has to defeat [ADR-0012](0012-capture-to-interrogate-inherit-to-mutate.md)
deliberately: because `git commit` inherits the terminal, the fixture sets
`GIT_EDITOR` to a command that writes a message, or every test would block
waiting for an editor.

The old shell-based `just test` recipe is now entirely superseded and should be
retired; it remains only because nobody has deleted it.

## Alternatives considered

**Mock `subprocess` throughout.** Fast, hermetic, and it would have passed
happily while `release 1.2.3` was completely broken — the failure was in what uv
does with an argument, and a mock does what the test says. A few such tests are
kept, precisely scoped to "which command line does this argument shape produce",
where the assertion is about our logic and not uv's.

**Test only through the CLI, in subprocesses.** The most faithful, and too slow
and too coarse to assert on much. Used only where the import-time reading of an
environment variable makes it the only honest option.
