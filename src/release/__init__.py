import argparse
import importlib
import os
import sys
import subprocess
from glob import glob
from .version import __version__
from .setver import (
    read_version,
    update_project_version,
    v_next_cli,
    BUMPS,
    RELEASE_NOCHECKS,
)

import pkgutil


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
    plugins = {
        name: importlib.import_module(name)
        for finder, name, ispkg in pkgutil.iter_modules()
        if name.startswith("release_")
    }
    if plugins:
        print("Plugins:", ", ".join(name for name in plugins))
    return list(plugins.values())


def release(*args, dry_run=False, message=None, allow_dirty=False):

    plugins = load_plugins()
    proj_name, current_version = read_version()

    # Work out the prospective version with a dry run first: this validates the
    # arguments and lets us preview and check the tag *before* mutating
    # anything and leaving a half-released tree behind.
    _, prospective = update_project_version(*args, dry_run=True)
    tag = f"r{prospective}"
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

    # Ensure no plugin blackballs the content of any file.
    oopsies = False
    for source in glob("**/*", recursive=True):
        for plugin in plugins:
            m = plugin.vet(f := CachedFile(source))
            if m:
                oopsies = True
                print(f.path, m)
    if oopsies and not RELEASE_NOCHECKS:
        sys.exit(3)

    # Ensure a clean environment, unless the caller opted out.
    if dirty and not (allow_dirty or RELEASE_NOCHECKS):
        print("Current git branch is dirty: please stage, commit or stash "
              "changes before releasing, or pass --allow-dirty")
        sys.exit(4)

    if tag_exists:
        sys.exit(f"release: tag {tag!r} already exists; refusing to overwrite")

    def run_or_die(cmd, what):
        if subprocess.call(cmd) != 0:
            sys.exit(f"release: {what} failed; release aborted")

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
        "-V", "--version",
        action="version",
        version=f"release {__version__}",
    )
    args = parser.parse_args()

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
