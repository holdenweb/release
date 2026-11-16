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

## The marker forbids the version it marks (deferred, 2026-11-16)

Reported from another session: podpack-mail's first release, 0.1.0, was cut by
hand rather than with `release` — one commit, `3c18b8b "Revert to 0.1.0 §"`,
changing only the version, tagged `r0.1.0` and pushed. Verified in
`~/sites/podpack-mail`, which is to be left as it is.

The interesting part is the commit's own title. It moved the version *down*,
from `0.1.0+dev` to `0.1.0`, because the tree carried the marker before it had
ever been released. `release` cannot do that, and reproducing it in a fresh
project at `0.1.0+dev` with no tags shows why:

    $ release --dry-run 0.1.0
    release: 0.1.0 is lower than the current version 0.1.0+dev: refusing to
    move the version backwards (set RELEASE_NOCHECKS to override)

    $ release --dry-run patch
    pm 0.1.0+dev -> 0.1.1  (tag r0.1.1)

So 0.1.0 was unreachable: refused as a downgrade, and skipped by the only bump
the tool would accept. The hand-made commit was the available route, not a
shortcut past a working one.

The cause is an assumption in [ADR-0016](adrs/0016-mark-unreleased-with-a-local-segment.md)
that nothing enforces. `<version>+dev` means "past this release, not yet the
next", which presumes the release happened; `--mark-dev` is documented as
following a release, and [ADR-0018](adrs/0018-the-marker-can-be-applied-on-its-own.md)
widened it to any tree without revisiting that. Applied to a version never
shipped, the marker asserts something false, and because `0.1.0+dev` sorts
*above* `0.1.0`, [ADR-0005](adrs/0005-versions-only-move-forward.md) then
forbids ever shipping it. The marker eats its own version.

Shapes of a fix, none obviously right:

- **Refuse to mark an unreleased version.** `--mark-dev` already knows whether
  HEAD is a release — it prints "this commit is not a release" as a note. The
  note could become a refusal when *no* release tag exists at all, which is the
  only case where the marker is unambiguously premature. Narrow and cheap.
- **Let a release clear a marker on its own base version.** The strip logic
  already recognises a carried marker; the gap is that `0.1.0+dev -> 0.1.0` is
  the same base version rather than a bump, so it reads as a downgrade.
  Permitting exactly `X+dev -> X` when `X` is untagged would make the
  hand-made commit a supported move.
- **Nothing, and document it.** First releases happen once per project.

Also worth recording: podpack-mail's `main` is still at the tagged commit with
a bare `0.1.0`, where its siblings carry a marker between releases
(podpack-notebooks `0.1.2+dev`, podpack-qrcode `0.2.2+dev`) — so by version
alone its next commit will be indistinguishable from the release, which is what
ADR-0016 exists to prevent. Not to be fixed there: 0.1.0 is out and being
adopted elsewhere.

Its `.github/workflows/publish.yml` is byte-identical to podpack-notebooks',
triggers on `tags: ["r*"]`, and says in a comment that its checks are the ones
`tools/publish.py` makes from a laptop. That is a second, parallel release path
in the estate that does not go through this tool, and the two should be
reconciled — or their division of labour written down — before either is
changed again.

## Smaller known gaps

- **`v_next` disagrees with `release` on a marked tree.** Found while
  reproducing the above. From `0.1.0+dev`, `v_next patch` answers `0.1.1+dev`
  while `release --dry-run patch` answers `0.1.1`; likewise `minor` gives
  `0.2.0+dev` against `0.2.0`. `release()` strips a carried local segment with
  `Version(predicted).public` before deciding the version and the tag;
  `v_next` returns uv's raw prediction and never learned that rule. Since
  `--mark-dev` is now the normal state between releases, the predictor is
  wrong most of the time — and "`v_next` predicts what `release` would do" was
  an explicit requirement when it was last fixed. The fix is to move the strip
  out of `release()` and into one place both call.

- **The vet loop walks `dist/` and `build/`.** Plugins are shown build
  artifacts that are not part of the source, so a stale wheel left in `dist/`
  can veto an otherwise good release. (The converse — hidden files being
  skipped — is fixed; see `PRUNE_DIRS` in `src/release/__init__.py`.)
- **Publishing to PyPI — blocked on the name.** No project called `release`
  exists on PyPI, but the name is not obtainable: it is judged too generic.
  Publishing would mean renaming the distribution, so this is not simply a
  matter of adding a workflow. Not currently wanted — the tool has one user.

  If it is ever revisited, the shape is a workflow triggered on tag push using
  trusted publishing, which suits the convention here: only releases are
  tagged, so a `.dev` commit cannot publish by accident. Note that
  `git push --tags` pushes *every* unpushed tag at once, so with such a
  workflow tags should be pushed one at a time (`git push origin r1.2.3`).
  Lightweight tags — which this tool creates — are also skipped by
  `git push --follow-tags`, so that is not a shortcut.
