import os
import subprocess
import sys
from packaging.version import Version as PyPIVersion

RELEASE_NOCHECKS = os.environ.get("RELEASE_NOCHECKS", "") != ""

# --- Custom Exception Classes ---
class VersionValidationError(ValueError): # Inherit from ValueError for type context
    """Custom exception for semantic version validation errors."""
    pass

class TomlProcessingError(Exception):
    """Custom exception for TOML file processing errors (structure, keys)."""
    pass

# --- Core Functions ---
BUMPS = "major, minor, patch, stable, alpha, beta, rc, post, dev".split(", ")

def read_version() -> tuple[str]:
    """
    Return a tuple containing the project name and version string.
    """
    result = subprocess.run(
        ('uv', 'version'),
        capture_output=True
    )
    version = result.stdout.decode("utf-8").split()
    assert len(version) == 2
    return tuple(version)

def update_project_version(*args: list[str]) -> None:
    """
    Updates 'project.version', and writes it back.

    Args:
        Either the new version string to write as a single
        arg, or a number of different bump arguments.
        If there's only a single argument then it might be a version
        number, so we have to check by trying to parse it.
    """
    if len(args) == 1 and (normalised_version := pp_version(args[0])) != "":
        cmd = ["uv", "version", normalised_version.public]
    elif all(arg in BUMPS for arg in args):
        cmd = ["uv", "version"]
        for arg in args:
            cmd.extend(["--bump", arg])
    else:
        sys.exit("Usage: release [version-number| bump [bump ]...]")

    result = subprocess.run(cmd, capture_output=True)
    result.check_returncode()
    stdout = result.stdout.decode("utf-8")
    proj_name, old, _, new_version_str = stdout.split()
    if _ != "=>":
        sys.exit(f"Unable to parse {' '.join(args)!r}")
    return proj_name, new_version_str

def pp_version(version_string):
    try:
        return PyPIVersion(version_string)
    except Exception:
        return ""

def pp_version_cli():
    print(pp_version(sys.argv[1]))

if __name__ == '__main__':
    try:
        if len(sys.argv) == 1:
            print(read_version())
        else:
            update_project_version(sys.argv[1:])
    except Exception as e:
        sys.exit(f"Oops: {e}")