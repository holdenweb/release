# ADR-0012: Capture output to interrogate, inherit it to mutate

**Status:** Accepted

**Date:** 2026-09-08

## Context

`release` is almost entirely subprocess calls to `uv` and `git`, and those calls
want two different things from their standard streams.

When the tool is *asking a question* — what is the version, does this tag exist,
is the tree dirty, what would this bump produce — it needs the answer as data,
and it needs the error text to put in its own message
([ADR-0006](0006-failures-raise-typed-errors.md)).

When the tool is *doing something* — `git commit` with no `-m` — the user needs
their editor. An editor cannot run with its input and output captured.

## Decision

Interrogation goes through `capture()` in `src/release/setver.py`, which sets
`capture_output=True` and turns a missing executable into `MissingTool` rather
than a `FileNotFoundError` traceback. Mutation goes through `run_or_die`, which
uses `subprocess.call` and lets the child inherit the terminal.

## Consequences

`git commit` opens the editor, which is the behaviour anyone expects of a
release tool, and `-m` is there when it is not wanted
([ADR-0013](0013-tests-drive-real-uv-and-git.md) explains why the tests need
it).

The cost is that uv's and git's own output during the mutating half goes
straight to the terminal, unlabelled and interleaved with ours. Worse, our
`print` is block-buffered when stdout is a pipe while the child writes directly
to the file descriptor, so in a CI log the tool's line can appear *after* the
output it was meant to introduce. Not fixed; a flush would do it.

A failed mutating step therefore has its diagnosis on the terminal and its
consequence in our exception, in two places rather than one.

## Alternatives considered

**Capture everything and re-emit.** Uniform, and it makes the output orderly. It
also makes `git commit` impossible without `-m`, turning an interactive tool
into a scripted one.

**Inherit everything.** Uniform the other way, and it throws away the error text
that makes the messages in [ADR-0006](0006-failures-raise-typed-errors.md) worth
having.
