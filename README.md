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
- **One project per repository.** `release` assumes the project root, the git
  root and `uv.lock` are all the same directory. A project in a subdirectory of
  its repository, or a uv workspace member (whose `uv.lock` lives at the
  workspace root), is not yet supported — see [BACKLOG.md](BACKLOG.md).

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
`pyproject.toml` holds the version). With no arguments it reports the current
version and whether this commit is a release:

```bash
$ release
myproject 1.3.0 -- released as r1.3.0
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
7. with `--mark-dev`, make one further untagged commit setting
   `<version>+dev` (see [Marking unreleased commits](#marking-unreleased-commits)).

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
        [--mark-dev] [--push] [--remote NAME] [-V] [BUMP ...]

  -n, --dry-run       show the version and tag that would result, changing nothing
  -m, --message MSG   commit message (default: open an editor, as `git commit` does)
  --allow-dirty       release even if the working tree has uncommitted changes
  --snapshot          build a labelled snapshot of the current version (see below)
  --mark-dev          commit <version>+dev (untagged) so later commits are
                      visibly unreleased; follows a release, or runs on its
                      own with no bump (see below)
  --push              send the release to the remote: the release commit and
                      its tag, atomically, leaving any +dev marker local
  --remote NAME       the remote --push sends to (default: origin)
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

Once a release is tagged, its version stays in `pyproject.toml` for every commit
that follows, so an edited-but-unreleased tree is indistinguishable *by version*
from the release itself. `--mark-dev` closes that gap the way CPython does —
with a PEP 440 *local* segment on the version just shipped:

```bash
$ release -m "Release 0.2.0" --mark-dev minor
Marked unreleased: 0.2.0+dev
```

That leaves two commits: the release (`0.2.0`, tagged `r0.2.0`) and a follow-up
setting `0.2.0+dev`, untagged, on the same branch. `0.2.0+dev` sorts *above*
`0.2.0` and *below* `0.2.1`, so any build made from a later commit says plainly
that it is not a release — and, unlike a `.dev` version on a guessed next
number, it claims nothing about which release comes next.

Cutting the next release strips the marker automatically: `release patch` from
`0.2.0+dev` gives `0.2.1`, not `0.2.1+dev`.

`--mark-dev` also works on its own, to mark a tree that was released without it:

```bash
$ release --mark-dev
Marked unreleased: 0.2.0+dev
```

It is idempotent (a tree already marked reports so and makes no commit), refuses
a dirty tree unless `--allow-dirty` is given, and says so when the commit it
marks is not itself a release. `--dry-run` previews it; `-m` sets the message.

To see whether the commit you are on is a release, run `release` with no
arguments:

```bash
$ release
myproject 0.2.1 -- released as r0.2.1
myproject 0.2.0+dev -- untagged; nearest tag r0.2.0-1-gbe43eae
```

If the newest release tag has not reached the remote, the report says so — the
gap that let five tags pile up here unnoticed:

```bash
$ release
myproject 0.2.0+dev -- untagged; nearest tag r0.2.0-1-gceaddf7  ! r0.2.0 is not on origin/main (as of your last fetch)
```

That check reads remote-tracking refs only, so it makes no network call and is
exactly as fresh as your last `git fetch`. It compares the release **tag**, not
`HEAD`, so a `+dev` marker deliberately left on your machine is not reported as
unpushed. A project with no remote, a branch with no upstream, or an upstream
never fetched are all simply silent: plenty of projects are never pushed
anywhere, and they are not nagged about it.

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

**Only releases are tagged.** A `.dev` version, or one carrying a local segment
such as `+dev`, is committed but deliberately left *untagged*, since it marks
its commit as unreleased — and a publishing workflow triggered on a tag glob
such as `r*` would otherwise match it and push a development version to an index
that never forgets. So `release dev` and `--mark-dev` still move the version
along, they just mint no tag. Release candidates, alphas and betas are genuine
releases and are tagged as normal.

A release must also be **strictly above the highest existing release tag**, not
merely above the version in `pyproject.toml` — the file tracks one line of edits
and can fall behind the release history on a branch, or after a tag is made by
hand.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success (including `--dry-run` and a bare `release`) |
| 1 | the operation failed; the message says what, and what state the tree is in |
| 2 | bad command line (from `argparse`) |
| 3 | a plugin refused the release |
| 4 | the working tree is dirty and `--allow-dirty` was not given |
| 5 | `--push` was refused before anything was written; fix the remote and re-run |
| 6 | the release is committed and tagged here, but no ref reached the remote |

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
