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

def update_project_version(*args: list[str], dry_run: bool = False) -> None:
    """
    Updates 'project.version', and writes it back.

    Args:
        Either the new version string to write as a single
        arg, or a number of different bump arguments.
        If there's only a single argument then it might be a version
        number, so we have to check by trying to parse it.
    """
    cmd = ["uv", "version"]
    if dry_run:
        cmd.append("--dry-run")
    if len(args) == 1 and (normalised_version := v_next(args[0])) is not None:
        cmd.append(normalised_version.public)
    elif all(arg in BUMPS for arg in args):
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

def v_next(version_string, dry_run=False):
    try:
        result = subprocess.run(["uv", "version", "--dry-run", version_string])
    except Exception as e:
        return None

def v_next_cli():
    if len(sys.argv) != 2:
        sys.exit(f"{sys.argv[0]} requires a bump argument")
    print(v_next(sys.argv[1], dry_run=True))

if __name__ == '__main__':
    try:
        if len(sys.argv) == 1:
            print(read_version())
        else:
            update_project_version(sys.argv[1:])
    except Exception as e:
        sys.exit(f"Oops: {e}")