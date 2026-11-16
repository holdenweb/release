# Example release plugins

A **plugin** for [`release`](../../README.md) is a callable that vets a single
file and either returns a message (to veto the release) or `None` (to allow it):

```python
def no_debug_file(cached_file):
    if cached_file.path.endswith("/wingdbstub.py"):
        return "is a Wing debugger stub"
```

`cached_file` exposes `.path` and `.read_text()`. Before cutting a release,
`release` runs every plugin against every file in the tree; if any returns a
message, the release is refused (exit code 3). The message is reported as
`{path}: {message} (plugin {name})`, so it is phrased to read after the path.

Plugins are discovered through the `release.plugins`
[entry-point group](https://packaging.python.org/en/latest/specifications/entry-points/),
so a plugin must be **installed into the same environment as `release`** — nothing
loads automatically ([ADR-0007](../../adrs/0007-plugins-are-entry-points-and-ship-disabled.md)).

## What's here

Each example is a separate installable distribution, so each has its own
directory and its own `pyproject.toml`; install either, both, or neither.

### `wing/` — distribution `release-wing-plugins`

Blocks [Wing IDE](https://wingware.com/) debugger stubs — `wingdbstub.py`
files, and `.py`/`.pyw` files that still `import wingdbstub` — from being
released. Entry points `no-wingdbstub-file` and `no-wingdbstub-import`. It is
**specific to Wing**; treat it as a template.

### `no-source/` — distribution `release-no-source`

Blocks a `pyproject.toml` that resolves a dependency through `uv.sources` — a
local path, a git ref or a URL. That is the right way to develop against an
unreleased sibling, and fatal in a release: the published artefact names a
dependency that nobody else can resolve. Entry point `no-uv-sources`, which
names the table it refuses rather than the distribution, because that is what
the reader of a veto has to go and delete:

```
pyproject.toml: pins tool.uv.sources.demo-lib to a dependency source that
nothing outside this checkout can resolve (plugin no-uv-sources)
```

Every offending entry is named by its full dotted key, and the search is
recursive: `[tool.uv.sources]` is where uv reads, but a `uv.sources` table
nested anywhere in the document pins just as effectively.

## Enabling them

Install the example alongside the tool, from a clone of this repository (there
is no `pip install release` — see
[ADR-0015](../../adrs/0015-installed-from-git-not-pypi.md)):

```bash
uv tool install . --with ./examples/plugins/no-source
```

```bash
uv tool install . --with ./examples/plugins/wing
```

Either one replaces an existing `release` installation, so to run both, name
both:

```bash
uv tool install . --with ./examples/plugins/wing --with ./examples/plugins/no-source
```

`release` then prints the plugins it found on every run, and refuses a tree
that any of them objects to:

```
Plugins: no-uv-sources, no-wingdbstub-file, no-wingdbstub-import
```

To install the tool from the remote rather than a clone, use the
`git+https://…` form from the [main README](../../README.md), but note that the
`--with` paths above are directories of *this checkout*: a plugin can only be
installed from somewhere pip can reach it.

## Writing your own

Copy one of these directories, rewrite the vet functions, and update the
`[project.entry-points."release.plugins"]` table in its `pyproject.toml` to
point at them. Then install it the same way. Two things worth knowing before
you do:

- the vet loop shows you **every** file in the tree, hidden files included, so
  test the path before reading it — `CachedFile.read_text()` raises on a file
  that is not text, and a plugin that raises aborts the release with a
  `PluginError`;
- a plugin that raises is a broken release, not a veto, so decide deliberately
  what a malformed file means and say so in a comment. `no-source` allows a
  `pyproject.toml` it cannot parse, and explains why.
