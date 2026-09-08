# ADR-0006: Failures raise typed errors, reported at one boundary

**Status:** Accepted

**Date:** 2026-09-08

## Context

Failure used to be signalled two ways, both lossy. Helper functions returned
`None`, and callers turned that into `sys.exit(USAGE)` — a single line reading
`Usage: release [version-number | bump [bump ...]]`, printed for causes that had
nothing to do with usage. An audit of the code found roughly forty paths that
could fail without telling the user anything useful. Four of them printed that
same usage line:

- `release stable` from a version with no pre-release. uv's own explanation —
  *"0.1.0 => 0.1.0 didn't increase the version; provide the exact version to
  force an update"* — was captured and discarded, and the user was told their
  perfectly well-formed command line was a usage error.
- running outside a uv project at all, which is not a usage problem either.
- a version and a bump name given together, without naming which token offended.
- and, worst, a failure in the `--next` step *after* a successful, tagged
  release: the entire user-facing output of a release that had completely
  succeeded was a usage line.

Elsewhere the messages were confidently wrong rather than merely unhelpful.
`run_or_die` appended "release aborted" to every failure, including those after
`pyproject.toml` had been rewritten, when the release had emphatically not been
aborted. `git diff --quiet` returns non-zero both for "there are changes" and
for "this is not a repository", and the second was reported as the first — a
directory with no git repo was announced as having uncommitted changes. A
missing `uv` or `git` produced a raw `FileNotFoundError` traceback.

## Decision

Library code raises exceptions from `src/release/errors.py`, all deriving from
`ReleaseError`, which carries an `exit_code`. `UsageError`, `UvError`,
`VersionOrderError`, `NotAProjectError`, `MissingTool`, `GitError`,
`StepFailed`, `PluginError`, `PluginVeto` (3) and `DirtyTree` (4) say what kind
of thing went wrong. The only two places that turn one into a message and an
exit code are `main()` and `v_next_cli()`; everything else raises. `argparse`
keeps its own `SystemExit(2)`, raised from `_dispatch` and the parser, and is
not routed through this.

`StepFailed` carries a *consequence* as well as a step, so a failure states what
the tree was left holding rather than asserting it was untouched. Where uv or
git explains itself, that explanation is relayed instead of replaced.

## Consequences

The messages are the point, and they are much better:

```
release: uv will not accept 'stable'; uv said:
error: 0.1.0 => 0.1.0 didn't increase the version; provide the exact version to force an update
```

`release` is now usable as a library: failures are `Exception` subclasses that a
caller can catch, where before they were `SystemExit` — a `BaseException` that
`except Exception` does not catch and that kills the calling process. That is a
real change to the public interface, noted in `README.md`.

It cost a good deal of test churn: nine tests asserted `SystemExit` and now
assert a specific type, which is the improvement — they say which failure they
expect rather than merely that something exited.

One subtlety had to be preserved. `v_next` documents `None` as its answer for
"that is not a form uv accepts", and tests pin it. So `v_next` catches
`UsageError` and `UvError` and returns `None`, while policy refusals
([ADR-0005](0005-versions-only-move-forward.md)) and environment failures
propagate. Getting this wrong is easy and was got wrong once during the work:
because uv fails identically for "bad argument" and "no project here", an
environment failure was briefly reported as a bad argument and swallowed. The
fix is that `_run_version` asks `read_version()` which case it is looking at
before blaming the arguments.

Exit codes 3 and 4 survive because they were an unwritten contract; they are now
written down, in `README.md`.

## Alternatives considered

**Catch `Exception` at the boundary as well.** Tempting, and wrong: an
unanticipated exception is a bug in `release` and deserves its traceback.
`ReleaseError` *is* the definition of "we thought about this".

**Put the boundary in `__main__.py`.** It looks like the entry point, but
`pyproject.toml` declares `release = "release.__main__:main"` and `__main__.py`
merely re-exports `release.main`, so a `try` under its `if __name__` guard would
protect `python -m release` and never the installed command.

**Keep `sys.exit` and just write better strings.** It fixes the messages and
leaves the library unusable from other code, and leaves tests asserting on
message text rather than on kinds of failure.
