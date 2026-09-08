# ADR-0007: Plugins are entry points, and none ship enabled

**Status:** Accepted

**Date:** 2026-09-08

## Context

`release` can refuse to release a tree — the original motivation was keeping a
Wing IDE debugger stub, `wingdbstub.py`, out of a published package. The check
was made extensible early (`d634cf3`, "Move file processing to plugins for
configurability") and then did not work. The commit messages record the
struggle plainly: "Testing whether wingdp files are found. Looks like a no :(",
"Still a no on the plugins!", "Work to get plugin logic properly functional".

The mechanism was `pkgutil.iter_modules()`, scanning `sys.path` for any importable
module named `release_*`. The two plugins lived at `src/release_check_debug.py`
and `src/release_debug_file.py` — beside the package, not inside it — so they
were not part of the installed distribution. Once `release` was installed as a
uv tool, nothing found them. The feature worked only when running from a source
checkout with `src` on the path, which is why it appeared to work while being
developed and never afterwards.

The two plugins were also specific to one person's editor. Anyone installing
`release` would be running Wing IDE checks whether or not they had ever used it.

Separately, the loop that fed files to plugins used `glob("**/*")`, which skips
every dotfile and dot-directory. A plugin whose entire purpose is "no secrets in
the release" never saw `.env`, `.github/` or `.gitignore` — it returned a
confident all-clear on precisely the files most likely to hold what it was
looking for.

## Decision

Plugins are discovered through the `release.plugins`
[entry-point group](https://packaging.python.org/en/latest/specifications/entry-points/),
read with `importlib.metadata`. A plugin is any installed distribution exposing
a `vet(cached_file)` callable that returns a message to refuse the release or
`None` to allow it. Discovery reads the environment `release` itself is
installed in, so a plugin must be installed alongside the tool.

`release` registers none. The Wing checks moved to `examples/plugins/` as a
separate installable distribution, `release-wing-plugins`, which a user opts
into with `uv tool install release --with .../examples/plugins`.

The vet loop walks the tree with `os.walk`, so hidden files are included, and
prunes `PRUNE_DIRS` — `.git`, `.venv`, caches, `node_modules` — so that
including them does not mean crawling a hundred thousand objects.

## Consequences

Plugins work when installed, which they did not for about a year. This was
verified end to end rather than reasoned about: with `release` and the example
package installed into one environment, a tree containing `wingdbstub.py` is
refused with exit 3 and both checks firing, and the same tree without it
releases.

Nobody gets somebody else's editor checks by default, and the example is a
working template rather than a snippet — it demonstrates the real mechanism,
because entry points cannot be demonstrated any other way.

Enabling a plugin now requires installing a distribution into the tool's
environment. That is a heavier action than dropping a file next to the project,
and it is the price of the feature working at all: entry points are metadata,
and metadata comes from installation.

Pruning is a fixed list, so a large directory not on it is still walked. `dist/`
and `build/` are deliberately *not* pruned and probably should be — a stale
wheel can veto a good release — which is recorded in `BACKLOG.md`.

## Alternatives considered

**Move the `release_*` modules inside the package and keep the `pkgutil` scan.**
It would have made the existing plugins load. It also makes them load for
everyone, which is the thing that was wrong with them, and leaves discovery
keyed on a module-name convention that any unrelated package could satisfy.

**A configuration file listing plugin module paths.** No installation needed and
plugins could live in the project being released. It invents a second mechanism
for something packaging already solves, and reintroduces "importable from
where?", which is the question that broke the original design.

**Delete the plugin system.** Genuinely considered: it was a broken feature with
one user. Keeping it cost one function and gained a checked example; deleting it
would have thrown away the only reason the tool refuses a release for reasons
other than version arithmetic.
