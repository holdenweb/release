import argparse
import os
import sys
import subprocess
from glob import glob
from importlib.metadata import entry_points
from packaging.version import Version
from .version import __version__
from .errors import (
    DirtyTree,
    GitError,
    PluginError,
    PluginVeto,
    ReleaseError,
    StepFailed,
    UsageError,
)
from .setver import (
    capture,
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


NEXT_FAILED = ("the release itself succeeded and is tagged, but the next "
               "development version was not opened")
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
            next_bump=None):

    if next_bump is not None and next_bump not in ("major", "minor", "patch"):
        # Checked before anything is touched: argparse guards the CLI, but
        # release() is a documented library entry point with no such guard,
        # and this used to surface as a usage line *after* a tagged release.
        raise UsageError(
            f"next_bump must be 'major', 'minor' or 'patch', not {next_bump!r}"
        )
    plugins = load_plugins()
    proj_name, current_version = read_version()

    # Work out the prospective version with a dry run first: this validates the
    # arguments and lets us preview and check the tag *before* mutating
    # anything and leaving a half-released tree behind.
    _, prospective = update_project_version(*args, dry_run=True)
    tag = f"{TAG_PREFIX}{prospective}"
    tag_exists = git_ref_exists(f"refs/tags/{tag}")
    dirty = git_is_dirty()

    if dry_run:
        print(f"release {__version__}: {proj_name} {current_version} -> "
              f"{prospective}  (tag {tag})  [dry run, nothing changed]")
        if tag_exists:
            print(f"  ! tag {tag!r} already exists")
        if dirty:
            print("  ! working tree has uncommitted changes")
        if next_bump is not None:
            print(f"  then a {next_bump} dev version would be committed "
                  "(untagged) on a new branch to open the next release")
        return

    print(f"release {__version__} creating release {proj_name} {' '.join(args)}")

    # Ensure no plugin blackballs the content of any file. Each file is read at
    # most once (CachedFile), shared across plugins; directories are skipped.
    vetoes = []
    for source in glob("**/*", recursive=True):
        if not os.path.isfile(source):
            continue
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

    # We are clear to update the version for real.
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
    # Tag the new version (no -f: refuse rather than clobber an existing tag).
    run_or_die(["git", "tag", tag], "git tag",
               f"{version} is committed but NOT tagged; tag it with "
               f"`git tag {tag}`")

    if next_bump is not None:
        open_next_release(next_bump)

def next_branch_name(dev_version: str) -> str:
    """The branch name for a development version: 0.7.4.dev1 -> 0.7.4.dev.

    The dev counter is dropped so the name survives later `release dev` bumps,
    and no tag prefix is applied, so a branch can never collide with a release
    tag in git's ref namespace.
    """
    return f"{Version(dev_version).base_version}.dev"

def open_next_release(next_bump):
    """Start the next release on its own branch, at a .dev version.

    Called after the release has been committed and tagged: the release commit
    stays on the current branch, and the .dev commit -- deliberately untagged,
    since only releases are tagged -- goes on a new branch named for the
    version it leaves in pyproject.toml.
    """
    # Predict first, because the branch is named for the version and must exist
    # before the commit that carries it. uv rejects a bare `dev` bump from a
    # release, so the bump is always chained.
    _, prospective = update_project_version(next_bump, "dev", dry_run=True)
    branch = next_branch_name(prospective)
    if git_ref_exists(f"refs/heads/{branch}"):
        raise GitError(f"branch {branch!r} already exists; {NEXT_FAILED}")
    run_or_die(["git", "switch", "-c", branch], f"git switch -c {branch}",
               NEXT_FAILED)
    on_branch = (f"you are now on branch {branch!r}, but the development "
                 f"version was not set on it")
    _, next_version = update_project_version(next_bump, "dev")
    run_or_die(["uv", "lock"], "uv lock", on_branch)
    run_or_die(["git", "add", "uv.lock", "pyproject.toml"], "git add", on_branch)
    run_or_die(["git", "commit", "-m", f"Begin development of {next_version}"],
               "git commit", on_branch)
    print(f"Next development version: {next_version} on branch {branch}")

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
        "--next",
        choices=("major", "minor", "patch"),
        help="after the release commit, bump to the next major/minor/patch "
             "dev version and commit it (untagged) as the first commit of the "
             "next release",
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
        if args.message or args.allow_dirty or args.next:
            parser.error("--snapshot cannot be combined with --message, "
                         "--allow-dirty or --next")
        snapshot(dry_run=args.dry_run)
        return

    if not args.bump:
        if args.next:
            parser.error("--next opens the next release after cutting one, so it "
                         "needs a version number or bump argument as well")
        # No bump given: report the current project version and exit cleanly.
        project, version = read_version()
        print(f"{project} {version}")
        return

    release(
        *args.bump,
        dry_run=args.dry_run,
        message=args.message,
        allow_dirty=args.allow_dirty,
        next_bump=args.next,
    )
