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
6. `git add pyproject.toml uv.lock`, `git commit`, and `git tag r<version>`;
7. with `--next`, create a branch for the next version and make one further
   untagged commit there opening its `.dev` version
   (see [Marking unreleased commits](#marking-unreleased-commits)).

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
release [-h] [-n] [-m MESSAGE] [--allow-dirty] [--snapshot]
        [--next {major,minor,patch}] [-V] [BUMP ...]

  -n, --dry-run       show the version and tag that would result, changing nothing
  -m, --message MSG   commit message (default: open an editor, as `git commit` does)
  --allow-dirty       release even if the working tree has uncommitted changes
  --snapshot          build a labelled snapshot of the current version (see below)
  --next KIND         after releasing, open the next major/minor/patch dev
                      version on its own branch (see below)
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

### Marking unreleased commits

Once a release is tagged, its version number stays in `pyproject.toml` for every
later commit — so an edited-but-unreleased commit looks identical, by version, to
the release itself. `--next` closes that gap by opening the following development
version on its own branch:

```bash
$ release -m "Release 0.2.0" --next patch minor
Next development version: 0.2.1.dev1 on branch 0.2.1.dev
```

The release commit (`0.2.0`, tagged `r0.2.0`) stays on the branch you released
from, which is left sitting on the release. A new branch is created for the next
version and checked out, and the `.dev` commit lands there. Every commit from
then on carries a `.dev` version, so an unreleased tree is obvious at a glance,
and only release commits are ever tagged.

The branch is named for the version left in `pyproject.toml` with the dev
counter dropped — `0.2.1.dev1` gives branch `0.2.1.dev` — so the name stays
valid as you `release dev` through `.dev2`, `.dev3` and so on. Branch names carry
no tag prefix, so a branch can never collide with a release tag.

When it is time to ship, `stable` drops the suffix and releases the version the
`.dev` was aiming at:

```bash
$ release -m "Release 0.2.1" stable      # 0.2.1.dev1 -> 0.2.1, tagged r0.2.1
```

You are not locked in to the target you named: from `0.2.1.dev1`, `release minor
dev` re-aims at `0.3.0.dev1`, and `release dev` just advances the counter. The
whole sequence stays monotonic (`0.2.0 < 0.2.1.dev1 < 0.2.1`), so the tool's
"no going backwards" check is satisfied throughout.

> Beware `release patch` from a `.dev` version: it yields `0.2.2`, **skipping**
> `0.2.1` altogether. Use `stable` to finalise.

### Snapshot builds

`release --snapshot` builds a wheel of the **current** version, labelled with
the git checkout id, without cutting a real release — nothing is committed or
tagged, and `pyproject.toml` is left untouched:

```bash
$ release --snapshot
release 0.6.0rc1: snapshot 1.4.0+g1a2b3c4.dirty
# ... builds dist/myproject-1.4.0+g1a2b3c4.dirty-py3-none-any.whl

$ release --snapshot --dry-run    # just print the version, don't build
```

The version it produces is a [PEP 440 *local
version*](https://peps.python.org/pep-0440/#local-version-identifiers):
`<current>+g<sha>`, with `.dirty` appended when tracked files differ from HEAD
(untracked files are not considered). It sorts *above* the plain current
version but *below* the next release, so it can never be mistaken for a clean
release. Because it builds the current version as-is, `--snapshot` takes no
bump argument.

> Local versions install and resolve fine from a file, URL, or private index,
> but public indexes such as PyPI **reject** them on upload:
> a snapshot is a throwaway build, not something to publish.

### `v_next` — predict a version

`v_next` answers "what version would `release` produce?" without changing
anything. It accepts exactly the same arguments as `release`:

```bash
$ v_next minor alpha
1.4.0a1
```

## Tags

Releases are tagged `r<version>` (for example `r1.4.0` or `r0.6.0rc1`). The `r`
prefix can be changed with the `RELEASE_TAG_PREFIX` environment variable — set
it to `v` for `v1.4.0`, or to an empty string for a bare `1.4.0`. Tagging is
non-destructive: if the tag already exists, `release` refuses rather than
overwriting it.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success (including `--dry-run` and a bare `release`) |
| 1 | the operation failed; the message says what, and what state the tree is in |
| 2 | bad command line (from `argparse`) |
| 3 | a plugin refused the release |
| 4 | the working tree is dirty and `--allow-dirty` was not given |

Failures are reported on stderr as `release: <what went wrong>`, relaying uv's or
git's own words where they explain more than we could. When a step fails after
the version has already been written, the message says so, rather than claiming
the release was abandoned.

If you use `release` as a library rather than a command, those failures are
raised as exceptions from `release.errors` (all deriving from `ReleaseError`)
instead of terminating the process, so you can catch them.

## Environment variables

- `RELEASE_NOCHECKS` — skips the pre-release checks (clean working tree and
  plugin vetting) and lets a version move backwards. Use with care. Set it to
  `1`, `yes`, `on` or any other value to enable it; it stays **off** when
  unset, empty, or set to `0`, `false`, `no` or `off`, so writing
  `RELEASE_NOCHECKS=0` means what it looks like.
- `RELEASE_TAG_PREFIX` — the prefix for release tags (default `r`, giving
  `r1.4.0`).

## Plugins

`release` can veto a release based on your files. A plugin is a
`vet(cached_file)` callable that returns a message to block the release (or
`None` to allow it), registered under the `release.plugins`
[entry-point group](https://packaging.python.org/en/latest/specifications/entry-points/).
Discovery reads the environment `release` is installed in, so a plugin must be
installed alongside the tool — **none are enabled by default**.

Plugins are shown every file in the project, **including hidden ones** such as
`.env` and `.github/workflows/*` — which are the files most likely to hold the
things a plugin is looking for. Version-control metadata, virtual environments
and caches (`.git`, `.venv`, `__pycache__`, `node_modules` and friends) are not
walked at all.

See [`examples/plugins/`](examples/plugins/) for a working example (blocking
Wing IDE debugger stubs) and instructions for enabling or adapting it.

## Development

```bash
uv run pytest                      # full suite (spins up throwaway uv/git projects)
uv run pytest -m "not integration" # fast unit tests only
```

The tests build real temporary `uv` projects under `git`, so `uv` and `git`
must be available.

## License

MIT — see [LICENSE](LICENSE).

## Author

Steve Holden — <steve@holdenweb.com>
