# Backlog

Known limitations and deferred work. Nothing here is a bug in the layouts
`release` is currently used on; these are things to attend to if and when its
audience widens.

## One project per repository (deferred, 2026-08-30)

`release` assumes the project root, the git root and the location of `uv.lock`
are all the same directory. That holds for a plain single-project repo — which
is how it is used today, and is the supported layout — but two other shapes are
broken. Both were reproduced; neither can occur in this repo.

**A project in a subdirectory of the repo.** Every git command is run in the
current directory, so `git add uv.lock pyproject.toml` fails from anywhere but
the project root, leaving the version bumped and uncommitted:

    fatal: pathspec 'uv.lock' did not match any files

Note the obvious fix is wrong: chdir-ing to the *git* root breaks it further,
because `uv version` then finds no `pyproject.toml` at all. The right anchor is
the project root — the nearest ancestor holding the `pyproject.toml` that
`uv version` is actually updating. (`uv version --output-format json` reports
only the package name and version, so the path has to be found by walking up.)

**A uv workspace member.** `uv version` correctly reports and updates the
member, but `uv.lock` lives at the *workspace* root, so the same `git add`
fails even when standing in the member's own directory — no subdirectory
involved.

Shape of the fix, if it is ever wanted:

- resolve two paths up front, before anything mutates: the project root (for
  `pyproject.toml`, the plugin vet walk, and `uv build`'s `dist/`), and the
  lock file — at the nearest ancestor whose `pyproject.toml` carries a
  `[tool.uv.workspace]` table, else beside the project root. `tomllib` is
  stdlib on 3.12, so reading that table costs nothing;
- run the body inside `contextlib.chdir(project_root)` (also stdlib on 3.12;
  restores the directory even if something raises, which `os.chdir` would not);
- stage by resolved absolute path rather than assuming the current directory;
- if the project root turns out to be outside the git repository, say so
  plainly rather than committing into a surprising repo.

Until then, "one project per repository" is a documented limitation rather than
a defect. Worth revisiting before publishing to PyPI, when people will start
pointing the tool at monorepos and workspaces nobody here has tried.

## Smaller known gaps

- **The vet loop walks `dist/` and `build/`.** Plugins are shown build
  artifacts that are not part of the source, so a stale wheel left in `dist/`
  can veto an otherwise good release. (The converse — hidden files being
  skipped — is fixed; see `PRUNE_DIRS` in `src/release/__init__.py`.)
- **Publishing to PyPI.** The name `release` was unregistered as of
  2026-08-30. The natural shape is a workflow triggered on tag push using
  trusted publishing, which suits the convention here: only real releases are
  tagged, so a `.dev` commit can never publish by accident.
