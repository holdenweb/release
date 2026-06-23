import os
import subprocess
import sys

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

def read_version() -> tuple[str, str]:
    """
    Return a tuple of (project name, version string) from ``uv version``.

    Exits with a friendly message (rather than an ``AssertionError``
    traceback) when the current directory is not a uv project, e.g. there
    is no pyproject.toml to read a version from.
    """
    result = subprocess.run(("uv", "version"), capture_output=True)
    fields = result.stdout.decode("utf-8").split()
    if result.returncode != 0 or len(fields) != 2:
        detail = result.stderr.decode("utf-8").strip() or "could not read project version"
        sys.exit(f"release: not a uv project here ({detail})")
    name, version = fields
    return name, version

def update_project_version(*args: str, dry_run: bool = False) -> tuple[str, str]:
    """
    Update 'project.version' and write it back, returning (name, new version).

    Args:
        Either the new version string to write as a single
        arg, or a number of different bump arguments.
        If there's only a single argument then it might be a version
        number, so we have to check by trying to parse it.
    """
    cmd = ["uv", "version"]
    if dry_run:
        cmd.append("--dry-run")
    if len(args) == 1 and args[0] not in BUMPS:
        # A single non-bump argument: treat it as an explicit version and
        # let uv validate/normalise it for us.
        if v_next(args[0]) is None:
            sys.exit("Usage: release [version-number| bump [bump ]...]")
        cmd.append(args[0])
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

def v_next(arg: str) -> str | None:
    """
    Return the version string that releasing ``arg`` would produce.

    ``arg`` may be a bump name (``patch``, ``rc``, ...) or an explicit
    version number. This is always a dry run: it only predicts the next
    version, never changes anything. Returns None when ``arg`` is neither a
    recognised bump nor a version uv will accept.
    """
    if arg in BUMPS:
        cmd = ["uv", "version", "--dry-run", "--bump", arg]
    else:
        cmd = ["uv", "version", "--dry-run", arg]
    result = subprocess.run(cmd, capture_output=True)
    stdout = result.stdout.decode("utf-8")
    if result.returncode != 0 or "=>" not in stdout:
        return None
    return stdout.split("=>", 1)[1].strip()

def v_next_cli():
    if len(sys.argv) != 2:
        sys.exit(f"{sys.argv[0]} requires a bump argument")
    print(v_next(sys.argv[1]))

if __name__ == '__main__':
    try:
        if len(sys.argv) == 1:
            print(read_version())
        else:
            update_project_version(sys.argv[1:])
    except Exception as e:
        sys.exit(f"Oops: {e}")