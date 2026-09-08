import argparse
import os
import sys
import subprocess
from importlib.metadata import entry_points
from packaging.version import Version
from .version import __version__
from .errors import (
    DirtyTree,
    VersionOrderError,
    GitError,
    PluginError,
    PluginVeto,
    ReleaseError,
    StepFailed,
    UsageError,
)
from .setver import (
    capture,
    describe_head,
    highest_tag_version,
    version_report,
    git_is_dirty,
    git_ref_exists,
    read_version,
    update_project_version,
    snapshot_version,
    v_next_cli,
    BUMPS,
    RELEASE_NOCHECKS,
    TAG_PREFIX,
)

PLUGIN_GROUP = "release.plugins"

# Directories never worth vetting: version-control metadata, virtual
# environments and caches. They are pruned rather than filtered afterwards so
# the walk never descends into them -- .git and .venv alone hold tens of
# thousands of files, many of them binary.
PRUNE_DIRS = frozenset({
    ".git", ".hg", ".svn",
    ".venv", "venv", ".tox", ".eggs", ".nox",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules",
})


def project_files(root="."):
    """Yield the project's files, relative to ``root``, hidden ones included.

    ``glob("**/*")`` silently skips every dotfile and dot-directory, so a
    plugin whose whole job is "no secrets, no debugger stubs in the release"
    never saw .env, .github/ or .gitignore and gave a false all-clear.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE_DIRS)
        for name in sorted(filenames):
            yield os.path.relpath(os.path.join(dirpath, name), root)


MARK_FAILED = ("the release itself succeeded and is tagged, but the commit "
               "after it was not marked as unreleased")
NOTHING_DONE = "nothing has been changed"


def run_or_die(cmd, what, consequence=NOTHING_DONE):
    """Run ``cmd``, raising StepFailed (naming the consequence) if it fails.

    ``consequence`` must describe the state the tree is actually left in: once
    the version has been written, "nothing has been changed" is a lie.
    """
    if subprocess.call(cmd) != 0:
        raise StepFailed(what, consequence)


class CachedFile:
    def __init__(self, path):
        self.path = path
        self.content = None
    def read(self, mode):
        if self.content is None:
            try:
                with open(self.path, mode) as f:
                    self.content = f.read()
            except UnicodeDecodeError as exc:
                raise PluginError(
                    f"a plugin asked to read {self.path} as text, but it is not "
                    f"text: {exc}"
                ) from exc
            except OSError as exc:
                raise PluginError(f"could not read {self.path}: {exc}") from exc
        return self.content
    def read_text(self):
        return self.read("r")


def load_plugins():
    """Return the vet callables registered under the ``release.plugins`` group.

    Each entry point loads to a ``vet(cached_file)`` callable that returns a
    message to veto the release (or None to allow it). Discovery reads the
    environment ``release`` is installed in, so a plugin must be installed
    alongside the tool -- none ship enabled. See examples/plugins/.
    """
    plugins = []
    for ep in entry_points(group=PLUGIN_GROUP):
        try:
            plugins.append((ep.name, ep.load()))
        except Exception as exc:
            raise PluginError(
                f"the plugin {ep.name!r} ({ep.value}) could not be loaded: {exc}. "
                f"Uninstall it, or fix it, to release without it"
            ) from exc
    if plugins:
        print("Plugins:", ", ".join(name for name, _ in plugins))
    return plugins


def release(*args, dry_run=False, message=None, allow_dirty=False,
            mark_dev=False):

    plugins = load_plugins()
    proj_name, current_version = read_version()

    # Work out the prospective version with a dry run first: this validates the
    # arguments and lets us preview and check the tag *before* mutating
    # anything and leaving a half-released tree behind.
    _, predicted = update_project_version(*args, dry_run=True)
    # uv carries a local segment through a bump -- 0.8.0+dev --bump patch gives
    # 0.8.1+dev -- so a release cut from a marked commit would inherit the
    # marker. Strip the marker we put there, and only that one: an explicit
    # local version the user asked for is left alone.
    carried = (Version(current_version).local is not None
               and Version(predicted).local == Version(current_version).local)
    prospective = Version(predicted).public if carried else predicted
    highest = highest_tag_version()
    # Strictly below: equality means the tag itself already exists, which the
    # collision check below reports with a more useful message.
    if (highest is not None and Version(prospective) < highest
            and not RELEASE_NOCHECKS):
        # ADR-0005 compares against pyproject.toml, which only tracks one line
        # of edits. On a branch, or after a tag was made by hand, the highest
        # tag can already be above the file -- and nothing noticed.
        raise VersionOrderError(
            f"{prospective} is not above {highest}, which is already tagged "
            f"{TAG_PREFIX}{highest}: refusing to release a version that does "
            f"not advance the release history (set RELEASE_NOCHECKS to override)"
        )
    tag = f"{TAG_PREFIX}{prospective}"
    # Only releases are tagged. A .dev version marks its commit as *unreleased*,
    # so it is committed but deliberately left untagged -- which also keeps it
    # out of reach of a publishing workflow triggered on a `r*` tag glob. This
    # is what lets `release dev` advance the counter and `release minor dev`
    # re-aim, without either minting a release tag. rc/alpha/beta are genuine
    # releases and are tagged as normal.
    # `.local` as well as `.dev`: verified, Version("0.8.0+dev").dev is None,
    # and git accepts refs/tags/r0.8.0+dev, so testing .dev alone left a hole
    # that the +dev marker walks straight into.
    tagging = Version(prospective).dev is None and Version(prospective).local is None
    tag_exists = tagging and git_ref_exists(f"refs/tags/{tag}")
    dirty = git_is_dirty()

    if dry_run:
        labelled = f"tag {tag}" if tagging else "no tag: development version"
        print(f"release {__version__}: {proj_name} {current_version} -> "
              f"{prospective}  ({labelled})  [dry run, nothing changed]")
        if tag_exists:
            print(f"  ! tag {tag!r} already exists")
        if dirty:
            print("  ! working tree has uncommitted changes")
        if mark_dev:
            print(f"  then {prospective}+dev would be committed (untagged) "
                  "to mark the commit after it as unreleased")
        return

    print(f"release {__version__} creating release {proj_name} {' '.join(args)}")

    # Ensure no plugin blackballs the content of any file. Each file is read at
    # most once (CachedFile), shared across plugins; directories are skipped.
    vetoes = []
    for source in project_files():
        if not os.path.isfile(source):
            continue                      # a broken symlink, or raced away
        cached = CachedFile(source)
        for name, vet in plugins:
            try:
                m = vet(cached)
            except ReleaseError:
                raise
            except Exception as exc:
                raise PluginError(
                    f"the plugin {name!r} raised while checking {cached.path}: "
                    f"{exc}"
                ) from exc
            if m:
                vetoes.append(f"{cached.path}: {m} (plugin {name})")
    if vetoes and not RELEASE_NOCHECKS:
        listing = "\n  ".join(vetoes)
        raise PluginVeto(
            f"{len(vetoes)} file(s) were refused by plugins, so nothing has "
            f"been changed:\n  {listing}\n"
            f"Fix them, uninstall the plugin, or set RELEASE_NOCHECKS to override"
        )

    # Ensure a clean environment, unless the caller opted out.
    if dirty and not (allow_dirty or RELEASE_NOCHECKS):
        raise DirtyTree(
            "the working tree has uncommitted changes, so nothing has been "
            "changed: stage, commit or stash them, or pass --allow-dirty"
        )

    if tag_exists:
        raise GitError(
            f"tag {tag!r} already exists; refusing to overwrite it, so nothing "
            f"has been changed"
        )

    # We are clear to update the version for real. When the marker was carried
    # through a bump, set the cleaned version explicitly instead of bumping
    # again -- only an explicit version clears a local segment in uv.
    if carried:
        _, version = update_project_version(prospective)
    else:
        _, version = update_project_version(*args)

    stranded = (f"pyproject.toml has already been set to {version} and is not "
                f"committed; put it back with `git checkout pyproject.toml "
                f"uv.lock` or finish by hand")
    run_or_die(["uv", "lock"], "uv lock", stranded)
    # Plus any files the user already staged.
    run_or_die(["git", "add", "uv.lock", "pyproject.toml"], "git add", stranded)
    commit_cmd = ["git", "commit"]
    if message is not None:
        commit_cmd += ["-m", message]
    run_or_die(commit_cmd, "git commit", stranded)
    if tagging:
        # No -f: refuse rather than clobber an existing tag.
        run_or_die(["git", "tag", tag], "git tag",
                   f"{version} is committed but NOT tagged; tag it with "
                   f"`git tag {tag}`")
    else:
        print(f"{version} is a development version: committed, not tagged")

    if mark_dev:
        mark_development(allow_dirty=allow_dirty)

def mark_development(allow_dirty=False, message=None, dry_run=False,
                     consequence=MARK_FAILED):
    """Mark the current commit as unreleased by adding a ``+dev`` segment.

    Writes ``<current>+dev``: a PEP 440 *local* segment on the version in the
    tree. It sorts above that version and below the next one, and unlike a
    ``.dev`` version on a guessed next number it asserts nothing about what the
    next release will be. Committed on the current branch, and never tagged --
    the tagging guard refuses local versions.

    Runs both as the tail of a release and on its own, to mark a tree that was
    released without it.
    """
    _, current = read_version()
    if Version(current).local is not None:
        # Idempotent: asking uv to set the version it already holds would make
        # it print no change, which surfaces as an unhelpful parse failure.
        print(f"{current} is already marked as unreleased; nothing to do")
        return

    marked = f"{current}+dev"
    exact, nearest = describe_head()
    if dry_run:
        print(f"release {__version__}: would mark {current} -> {marked} "
              "(untagged)  [dry run, nothing changed]")
        return
    if git_is_dirty() and not (allow_dirty or RELEASE_NOCHECKS):
        raise DirtyTree(
            "the working tree has uncommitted changes, so nothing has been "
            "changed: stage, commit or stash them, or pass --allow-dirty"
        )

    _, marker = update_project_version(marked)
    run_or_die(["uv", "lock"], "uv lock", consequence)
    run_or_die(["git", "add", "uv.lock", "pyproject.toml"], "git add", consequence)
    run_or_die(["git", "commit", "-m", message or f"Begin development after {current}"],
               "git commit", consequence)
    print(f"Marked unreleased: {marker}")
    if exact is None:
        # Marking a commit that is not itself a release is legitimate, but say
        # so: the version alone cannot distinguish the two.
        print(f"  note: this commit is not a release "
              f"({'nearest tag ' + nearest if nearest else 'no release tags found'})")

def snapshot(dry_run=False):
    """
    Build a wheel of the *current* version labelled with the git checkout id.

    This is a transient build: it stamps a PEP 440 local version
    (``<current>+g<sha>[.dirty]``) into pyproject.toml only long enough to run
    ``uv build``, then restores it. Nothing is committed or tagged. With
    dry_run, just print the version that would be built.
    """
    _, original = read_version()
    version = snapshot_version()
    print(f"release {__version__}: snapshot {version}")
    if dry_run:
        return
    stamped = (f"pyproject.toml may have been left at {version}; put it back "
               f"with `uv version {original}`")
    try:
        # Inside the try: uv can rewrite pyproject.toml and *then* fail, so the
        # restore below must run even when the stamping step itself fails.
        run_or_die(["uv", "version", version], "uv version", stamped)
        run_or_die(["uv", "build"], "uv build", stamped)
    finally:
        run_or_die(["uv", "version", original], "restoring the version", stamped)

def main():
    parser = argparse.ArgumentParser(
        prog="release",
        description="Bump the project version, commit, and tag the release.",
    )
    parser.add_argument(
        "bump",
        nargs="*",
        metavar="BUMP",
        help="a version number, or one or more bump names "
             "(major, minor, patch, stable, alpha, beta, rc, post, dev). "
             "With no argument, print the current project version.",
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="show the version and tag that would result, changing nothing",
    )
    parser.add_argument(
        "-m", "--message",
        help="commit message (default: open an editor, as `git commit` does)",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="release even if the working tree has uncommitted changes",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="build a wheel of the current version labelled with the git "
             "checkout id (e.g. 1.4.0+g1a2b3c4.dirty); takes no bump argument",
    )
    parser.add_argument(
        "--mark-dev",
        action="store_true",
        help="commit <version>+dev (untagged) so later commits are visibly "
             "unreleased; follows a release, or runs on its own with no bump",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"release {__version__}",
    )
    args = parser.parse_args()
    try:
        _dispatch(parser, args)
    except ReleaseError as exc:
        print(f"release: {exc}", file=sys.stderr)
        sys.exit(exc.exit_code)

def _dispatch(parser, args):
    if args.snapshot:
        if args.bump:
            parser.error("--snapshot builds a snapshot of the current version "
                         "and takes no bump argument")
        if args.message or args.allow_dirty or args.mark_dev:
            parser.error("--snapshot cannot be combined with --message, "
                         "--allow-dirty or --mark-dev")
        snapshot(dry_run=args.dry_run)
        return

    if not args.bump:
        if args.mark_dev:
            # Standalone: nothing to guess, because the marker is derived from
            # the version already in the tree. (Under the superseded --next it
            # needed a bump to know what to guess; that restriction went with
            # it -- see ADR-0016.)
            mark_development(allow_dirty=args.allow_dirty,
                             message=args.message, dry_run=args.dry_run,
                             consequence=NOTHING_DONE)
            return
        # No bump given: report the version *and* whether this commit is a
        # release. Printing the version alone is the one answer that cannot
        # reveal a disagreement between the tree and its tags.
        print(version_report())
        return

    release(
        *args.bump,
        dry_run=args.dry_run,
        message=args.message,
        allow_dirty=args.allow_dirty,
        mark_dev=args.mark_dev,
    )
