import importlib
import os
import sys
import subprocess
from glob import glob
from .version import __version__
from .setver import read_version, update_project_version, pp_version_cli, VersionValidationError

import pkgutil

VERSION_TEMPLATE = """\
__version__ = "{version}"
"""
RELEASE_NOCHECKS = os.getenv("RELEASE_NOCHECKS", "") != ""
BUMPS = "major minor patch stable alpha beta rc post dev".split(" ")


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
    src_dir = os.path.exists("src")
    mod_name = proj_name.replace("-", "_")
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

    # We are clear to update the versiona
    try:
        _, version = update_project_version(*args)
    except VersionValidationError as e:
        sys.exit(e)

    # Check in an updated version.py
    pystring = VERSION_TEMPLATE.format(version=version)
    if src_dir:
        file_path = f"src/{mod_name}/version.py"
    else:
        file_path = "version.py"
    #print(f"Opening {file_path!r} for writing")
    with open(file_path, "w") as pyfile:
        pyfile.write(pystring)
    #print("Calling `uv lock`")
    retcode = subprocess.call(["uv", "lock"])
    #print("Adding files)")
    cmd = ["git", "add", "uv.lock", "pyproject.toml", file_path]  # Plus already-added added files
    retcode = subprocess.call(cmd)
    #print("Committing this release")
    cmd = ["git", "commit"]  # User will  be required to add a message in the usual way
    retcode = subprocess.call(cmd)
    # Tag the new version
    cmd = ["git", "tag", "-f", f"r{version}"]
    retcode = subprocess.call(cmd)

def main():
    if len(sys.argv) == 1:
        project, version = read_version()
        sys.exit(f"{project} {version}")
    else:
        release(*sys.argv[1:])
