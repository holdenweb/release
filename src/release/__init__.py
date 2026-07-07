import argparse
import os
import sys
import subprocess
from glob import glob
from importlib.metadata import entry_points
from .version import __version__
from .setver import (
    read_version,
    update_project_version,
    snapshot_version,
    v_next_cli,
    BUMPS,
    RELEASE_NOCHECKS,
    TAG_PREFIX,
)

PLUGIN_GROUP = "release.plugins"


def run_or_die(cmd, what):
    if subprocess.call(cmd) != 0:
        sys.exit(f"release: {what} failed; release aborted")


class CachedFile:
    def __init__(self, path):
        self.path = path
        self.content = None
    def read(self, mode):
        if self.content is None:
            with open(self.path, mode) as f:
                self.content = f.read()
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
    plugins = [(ep.name, ep.load()) for ep in entry_points(group=PLUGIN_GROUP)]
    if plugins:
        print("Plugins:", ", ".join(name for name, _ in plugins))
    return [vet for _, vet in plugins]


def release(*args, dry_run=False, message=None, allow_dirty=False):

    plugins = load_plugins()
    proj_name, current_version = read_version()

    # Work out the prospective version with a dry run first: this validates the
    # arguments and lets us preview and check the tag *before* mutating
    # anything and leaving a half-released tree behind.
    _, prospective = update_project_version(*args, dry_run=True)
    tag = f"{TAG_PREFIX}{prospective}"
    tag_exists = tag in subprocess.run(
        ["git", "tag", "--list", tag], capture_output=True
    ).stdout.decode("utf-8").split()
    dirty = subprocess.call("git diff --quiet".split()) != 0

    if dry_run:
        print(f"release {__version__}: {proj_name} {current_version} -> "
              f"{prospective}  (tag {tag})  [dry run, nothing changed]")
        if tag_exists:
            print(f"  ! tag {tag!r} already exists")
        if dirty:
            print("  ! working tree has uncommitted changes")
        return

    print(f"release {__version__} creating release {proj_name} {' '.join(args)}")

    # Ensure no plugin blackballs the content of any file. Each file is read at
    # most once (CachedFile), shared across plugins; directories are skipped.
    oopsies = False
    for source in glob("**/*", recursive=True):
        if not os.path.isfile(source):
            continue
        cached = CachedFile(source)
        for vet in plugins:
            if m := vet(cached):
                oopsies = True
                print(cached.path, m)
    if oopsies and not RELEASE_NOCHECKS:
        sys.exit(3)

    # Ensure a clean environment, unless the caller opted out.
    if dirty and not (allow_dirty or RELEASE_NOCHECKS):
        print("Current git branch is dirty: please stage, commit or stash "
              "changes before releasing, or pass --allow-dirty")
        sys.exit(4)

    if tag_exists:
        sys.exit(f"release: tag {tag!r} already exists; refusing to overwrite")

    # We are clear to update the version for real.
    _, version = update_project_version(*args)

    run_or_die(["uv", "lock"], "uv lock")
    # Plus any files the user already staged.
    run_or_die(["git", "add", "uv.lock", "pyproject.toml"], "git add")
    commit_cmd = ["git", "commit"]
    if message is not None:
        commit_cmd += ["-m", message]
    run_or_die(commit_cmd, "git commit")
    # Tag the new version (no -f: refuse rather than clobber an existing tag).
    run_or_die(["git", "tag", tag], "git tag")

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
    run_or_die(["uv", "version", version], "uv version")
    try:
        run_or_die(["uv", "build"], "uv build")
    finally:
        # Always put pyproject.toml back, even if the build failed.
        run_or_die(["uv", "version", original], "restore version")

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
        "-V", "--version",
        action="version",
        version=f"release {__version__}",
    )
    args = parser.parse_args()

    if args.snapshot:
        if args.bump:
            parser.error("--snapshot builds a snapshot of the current version "
                         "and takes no bump argument")
        if args.message or args.allow_dirty:
            parser.error("--snapshot cannot be combined with --message or --allow-dirty")
        snapshot(dry_run=args.dry_run)
        return

    if not args.bump:
        # No bump given: report the current project version and exit cleanly.
        project, version = read_version()
        print(f"{project} {version}")
        return

    release(
        *args.bump,
        dry_run=args.dry_run,
        message=args.message,
        allow_dirty=args.allow_dirty,
    )
