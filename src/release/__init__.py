import os
import sys
import subprocess
from glob import glob

from release.setver import read_version, update_project_version, VersionValidationError

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
    print(f"Starting release process for {proj_name} {' '.join(args)}")

    # Ensure no debug calls remain!
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
        msg = ("Current git branch is dirty: please commit "
                 "or stash changes before releasing")
        print(msg)
        if not RELEASE_NOCHECKS:
            sys.exit(4)

    # We are clear to update the version - if it passes validation
    try:
        tags, _, version = update_project_version(*args)
    except VersionValidationError as e:
        sys.exit(e)

    # Check in an updated version.py
    pystring = VERSION_TEMPLATE.format(version=version)
    if src_dir:
        file_path = f"src/{mod_name}/version.py"
    else:
        file_path = "version.py"
    with open(file_path, "w") as pyfile:
        pyfile.write(pystring)
    retcode = subprocess.call(["uv", "lock"])
    cmd = ["git", "add", "uv.lock", "pyproject.toml", file_path]  # Note: excludes files previously added
    retcode = subprocess.call(cmd)
    cmd = ["git", "commit", "-m", f"Release r{version}"]
    retcode = subprocess.call(cmd)
    for tag in tags + [version]:
        # Tag the new version
        cmd = ["git", "tag", f"r{version}"]
        retcode = subprocess.call(cmd)

    # Build the project
    retcode = subprocess.call(["uv", "build"])

def main():
    if len(sys.argv) == 1:
        print(read_version())
        sys.exit()
    else:
        release(*sys.argv[1:])

if __name__ == '__main__':
    main()
