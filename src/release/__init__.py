import os
import sys
import subprocess
from glob import glob
from .version import __version__
from .setver import read_version, update_project_version, pp_version_cli, VersionValidationError

VERSION_TEMPLATE = """\
__version__ = "{version}"
"""
RELEASE_NOCHECKS = os.getenv("RELEASE_NOCHECKS", "") != ""
BUMPS = "major, minor, patch, stable, alpha, beta, rc, post, dev".split(", ")

def release(*args):

    # Need to be able to handle {non-,}packaged app, & lib
    proj_name, current_version_str = read_version()
    src_dir = os.path.exists("src")
    mod_name = proj_name.replace("-", "_")
    print(f"release{__version__} creating release {proj_name} {' '.join(args)}")

    # Ensure no debug calls remain!
    # This code should be factored out to a plugin.
    oopsies = []
    stubs = list(glob("**/wingdbstub.py", recursive=True))
    for source in glob("**/*.py", recursive=True):
        if source in stubs:
            continue
        # TODO: fix release process to omit wingdbstub file(s)
        with open(source) as f:
            if ("import" + " wingdbstub") in f.read():
                oopsies.append(source)
    if oopsies:
        msg = f"Some files still use wingdbstub : {oopsies!r}"
        print(msg)
        if not RELEASE_NOCHECKS:
            sys.exit(2)

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
