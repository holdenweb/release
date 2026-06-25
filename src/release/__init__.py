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
    VersionValidationError,
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


def release(*args):

    plugins = load_plugins()

    # Need to be able to handle {non-,}packaged app, & lib
    proj_name, current_version_str = read_version()
    print(f"release{__version__} creating release {proj_name} {' '.join(args)}")

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

    # Ensure a clean environment
    if subprocess.call("git diff --quiet".split()) != 0:
        msg = ("Current git branch is dirty: please stage, commit "
                 "or stash changes before releasing")
        print(msg)
        if not RELEASE_NOCHECKS:
            sys.exit(4)

    def run_or_die(cmd, what):
        if subprocess.call(cmd) != 0:
            sys.exit(f"release: {what} failed; release aborted")

    # Work out the prospective version with a dry run first, so we can
    # refuse a duplicate tag (and reject bad arguments) *before* mutating
    # anything and leaving a half-released tree behind.
    try:
        _, prospective = update_project_version(*args, dry_run=True)
    except VersionValidationError as e:
        sys.exit(e)
    tag = f"r{prospective}"
    existing = subprocess.run(
        ["git", "tag", "--list", tag], capture_output=True
    ).stdout.decode("utf-8").split()
    if tag in existing:
        sys.exit(f"release: tag {tag!r} already exists; refusing to overwrite")

    # We are clear to update the version for real.
    try:
        _, version = update_project_version(*args)
    except VersionValidationError as e:
        sys.exit(e)

    run_or_die(["uv", "lock"], "uv lock")
    # Plus any files the user already staged.
    #run_or_die(["git", "add", "uv.lock", "pyproject.toml", file_path], "git add")
    run_or_die(["git", "add", "uv.lock", "pyproject.toml"], "git add")

    # User will be required to add a message in the usual way.
    #  TODO: Implement an option to pass the message on the command line.
    run_or_die(["git", "commit"], "git commit")

    # Tag the new version (no -f: refuse rather than clobber an existing tag).
    run_or_die(["git", "tag", tag], "git tag")

def main():
    if len(sys.argv) == 1:
        project, version = read_version()
        sys.exit(f"{project} {version}")
    else:
        release(*sys.argv[1:])
