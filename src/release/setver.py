import tomllib
import os
import subprocess
import sys
from typing import Dict, Any
from packaging.version import Version as PyPIVersion

import toml  # Because tomllib can't write.

option_force = False

# --- Custom Exception Classes ---
class VersionValidationError(ValueError): # Inherit from ValueError for type context
    """Custom exception for semantic version validation errors."""
    pass

class TomlProcessingError(Exception):
    """Custom exception for TOML file processing errors (structure, keys)."""
    pass

# --- Core Functions ---
BUMPS = "major, minor, patch, stable, alpha, beta, rc, post, dev".split(", ")

def read_version() -> str:
    """
    Reads the TOML file and returns the value of 'project.version'.

    Args:
        toml_file_path: The path to the TOML file.

    Returns:
        The version string as returned by `uv`.
    """
    result = subprocess.run(
        ('uv', 'version'),
        capture_output=True
    )
    version = result.stdout.split()[1]
    return version.encode("utf-8")

def write_version(new_version_str: str) -> None:
    """
    Reads the TOML file, updates 'project.version', and writes it back.

    Args:
        toml_file_path: The path to the TOML file.
        new_version_str: The new version string to write.

    Raises:
        FileNotFoundError: If the TOML file does not exist (during read phase).
        TomlProcessingError: If the TOML file is invalid or 'project' is not a table.
        IOError: If there's an error reading or writing the file.
        TypeError: If 'project' exists but isn't a dictionary during read.
        KeyError: If 'project' key doesn't exist during read.
    """
    if new_version_str in BUMPS:
        cmd = ["uv", "version", "--bump", new_version_str]
    else:
        cmd = ["uv", "version", new_version_str]
    result = subprocess.run(cmd)
    result.check_returncode()

def pp_version(version_string):
    return PyPIVersion(version_string)

def pp_version_cli():
    print(pp_version(sys.argv[1]))

def update_project_version(new_version_str: str) -> None:
    """
    Update the 'project.version' in a TOML file if the
    new version is valid and greater than the existing version.

    Args:
        toml_file_path: The path to the TOML file (e.g., 'pyproject.toml').
        new_version_str: The new version string to set (e.g., '1.2.3').

    Raises:
        FileNotFoundError: If the TOML file does not exist.
        TomlProcessingError: If the TOML file is invalid or has structure issues.
        VersionValidationError: If the new or existing version string is not
                                a valid semantic version, or if the new version
                                is not strictly greater than the existing one.
        IOError: If file read/write errors occur.
        TypeError: If TOML structure is incorrect.
        KeyError: If expected TOML keys are missing.
    """
    # Validate the new version string format
    try:
        new_version = pp_version(new_version_str)
        new_version_str = new_version.public
    except ValueError:
        raise VersionValidationError(
            f"New version '{new_version_str}' is not a valid PyPI version (e.g., '1.2.3rc3')."
        )

    existing_version_str = read_version()
    try:
        existing_version = pp_version(existing_version_str)
    except ValueError:
        raise VersionValidationError(
            f"Existing version '{existing_version_str}' in '{toml_file_path}' is not a valid semantic version."
        )

    if new_version <= existing_version and not option_force:
        raise VersionValidationError(
            f"New version '{new_version_str}' ({new_version}) is not strictly greater "
            f"than the existing version '{existing_version_str}' ({existing_version})."
        )

    new_version_str = pp_version(new_version_str).public
    write_version(toml_file_path, new_version_str)

if __name__ == '__main__':
    try:
        if len(sys.argv) == 1:
            print(read_version())
        elif len(sys.argv) == 2:
            update_project_version(sys.argv[1])
        else:
            sys.exit("Aborted: additional arguments detected")
    except Exception as e:
        sys.exit(f"Oops: {e}")