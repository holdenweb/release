# release

A small command-line tool that automates the mechanical steps of cutting a
release: bump the version, refresh the lock file, commit, and tag — all in one
command, with the version number as the single source of truth in
`pyproject.toml`.

`release` is a thin, opinionated wrapper around [`uv`](https://docs.astral.sh/uv/)
and `git`. It does no version arithmetic of its own; `uv version` decides what
the next version is, so the result always matches what `uv` would produce.

> Status: early / pre-1.0. The command surface described here works and is
> covered by tests, but expect rough edges.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) on your `PATH`
- `git`
- Python ≥ 3.12
- A project managed by `uv` (i.e. one with a `pyproject.toml`)

The only runtime dependency is [`packaging`](https://pypi.org/project/packaging/)
(used to compare version numbers); everything else is driven through `uv` and
`git`.

## Installation

Install it as a `uv` tool so the `release` and `v_next` commands are available
everywhere:

```bash
# from a clone of this repository
uv tool install .

# or straight from GitHub
uv tool install git+https://github.com/holdenweb/release
```

<!-- TODO: publish to PyPI and document `uv tool install release` / pipx. -->

## Usage

Run `release` **inside the project you want to release** (the one whose
`pyproject.toml` holds the version). With no arguments it just reports the
current version:

```bash
$ release
myproject 1.3.0
```

Give it one or more *bump names* to cut a release:

```bash
$ release minor
```

That will, in order:

1. work out the next version with a dry run (and reject bad arguments early);
2. refuse if the tag for that version already exists;
3. check the working tree is clean (see `--allow-dirty`);
4. run `uv version` to write the new version to `pyproject.toml`;
5. run `uv lock`;
6. `git add pyproject.toml uv.lock`, `git commit`, and `git tag r<version>`.

### Bump names

Any of the bump names understood by `uv version` may be used, and several may
be chained (they are applied in order):

```
major  minor  patch  stable  alpha  beta  rc  post  dev
```

```bash
$ release minor alpha     # 1.3.0 -> 1.4.0a1
$ release patch           # 1.3.0 -> 1.3.1
```

You can also set an explicit version instead of a bump name:

```bash
$ release 2.0.0
```

### Options

```
release [-h] [-n] [-m MESSAGE] [--allow-dirty] [-V] [BUMP ...]

  -n, --dry-run       show the version and tag that would result, changing nothing
  -m, --message MSG   commit message (default: open an editor, as `git commit` does)
  --allow-dirty       release even if the working tree has uncommitted changes
  -V, --version       print the version of the release tool itself
  -h, --help          show help and exit
```

Preview a release without touching anything:

```bash
$ release --dry-run minor
release 0.6.0rc1: myproject 1.3.0 -> 1.4.0  (tag r1.4.0)  [dry run, nothing changed]
```

Commit non-interactively (handy in scripts and CI):

```bash
$ release -m "Release 1.4.0" minor
```

### `v_next` — predict a version

`v_next` answers "what version would `release` produce?" without changing
anything. It accepts exactly the same arguments as `release`:

```bash
$ v_next minor alpha
1.4.0a1
```

## Tags

Releases are tagged `r<version>` (for example `r1.4.0` or `r0.6.0rc1`). Tagging
is non-destructive: if the tag already exists, `release` refuses rather than
overwriting it.

## Environment variables

- `RELEASE_NOCHECKS` — set to any non-empty value to skip the pre-release
  checks (clean working tree and plugin vetting). Use with care.

## Experimental: plugins

Any importable module named `release_<something>` that exposes a
`vet(cached_file)` function can veto a release by returning a message when it
objects to a file's path or contents (for example, to block a debugger stub
from being released). This mechanism is **experimental and incomplete** — treat
it as subject to change.

## Development

```bash
uv run pytest                      # full suite (spins up throwaway uv/git projects)
uv run pytest -m "not integration" # fast unit tests only
```

The tests build real temporary `uv` projects under `git`, so `uv` and `git`
must be available.

## License

<!-- TODO: choose a license and add a LICENSE file. -->

## Author

Steve Holden — <steve@holdenweb.com>
