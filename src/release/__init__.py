import os
import sys
import subprocess
import toml
from glob import glob
from pathlib import Path

from release.setver import read_version, update_project_version, VersionValidationError

VERSION_TEMPLATE = """\
__version__ = "{version}"
"""

def release(version):
    # Need to be able to handle {non-,}packaged app, & lib
    with open("pyproject.toml", "rb") as  toml_file:
        toml = toml.load(toml_file)
    src_dir = os.path.exists("src")
    proj_name = toml['project']['name']
    mod_name = proj_name.replace("-", "_")
    print(f"Starting release process for {proj_name} r{version}")
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
        sys.exit(f"Some files still use wingdbstub : {oopsies!r}")

    # Ensure a clean environment
    if subprocess.call("git diff --quiet".split()) != 0:
        sys.exit("Current git branch is dirty: please commit "
                 "or stash changes before releasing")

    # We are clear to update the version - if it passes validation
    try:
        update_project_version('pyproject.toml', version)
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

    # Tag the new version
    cmd = ["git", "tag", f"r{version}"]
    retcode = subprocess.call(cmd)

    # Build the project
    retcode = subprocess.call(["uv", "build"])

def main():
    if len(sys.argv) == 1:
        print(read_version("pyproject.toml"))
        sys.exit()

    elif len(sys.argv) != 2:
        sys.exit(usage())

    else:
        release(sys.argv[1])

if __name__ == '__main__':
    main()
