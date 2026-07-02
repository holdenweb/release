import argparse
import os
import subprocess
import sys

from packaging.version import Version

from .version import __version__

RELEASE_NOCHECKS = os.environ.get("RELEASE_NOCHECKS", "") != ""

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

USAGE = "Usage: release [version-number | bump [bump ...]]"


def _version_command(args: tuple[str, ...], dry_run: bool) -> list[str] | None:
    """Build the ``uv version`` command for ``args``, or None if invalid.

    ``args`` is either a single explicit version number, or one or more bump
    names (``patch``, ``rc``, ...). These are exactly the forms ``release``
    accepts, so prediction and application stay in step.
    """
    if not args:
        return None
    cmd = ["uv", "version"]
    if dry_run:
        cmd.append("--dry-run")
    if len(args) == 1 and args[0] not in BUMPS:
        cmd.append(args[0])  # explicit version; let uv validate/normalise it
    elif all(arg in BUMPS for arg in args):
        for arg in args:
            cmd.extend(["--bump", arg])
    else:
        return None
    return cmd

def _run_version(args: tuple[str, ...], dry_run: bool) -> tuple[str, str] | None:
    """Run ``uv version`` for ``args``; return (name, new version) or None.

    None means the args were not a valid form, or uv rejected them (e.g. an
    unparseable explicit version).
    """
    cmd = _version_command(args, dry_run)
    if cmd is None:
        return None
    result = subprocess.run(cmd, capture_output=True)
    stdout = result.stdout.decode("utf-8")
    if result.returncode != 0 or "=>" not in stdout:
        return None
    name, old, _arrow, new_version = stdout.split()
    # Bump names always move forward, but an explicit version can go backwards;
    # refuse that (using PEP 440 ordering) unless checks are disabled.
    if not RELEASE_NOCHECKS and Version(new_version) < Version(old):
        sys.exit(
            f"{new_version} is lower than the current version {old}: refusing to "
            "move the version backwards (set RELEASE_NOCHECKS to override)"
        )
    return name, new_version

def update_project_version(*args: str, dry_run: bool = False) -> tuple[str, str]:
    """
    Update 'project.version' and write it back, returning (name, new version).

    ``args`` is either a single new version string, or a sequence of bump
    names applied in order. Exits with a usage message if it is neither.
    """
    result = _run_version(args, dry_run=dry_run)
    if result is None:
        sys.exit(USAGE)
    return result

def v_next(*args: str) -> str | None:
    """
    Predict the version that ``release`` would produce from ``args``.

    ``args`` may be a single explicit version number or a sequence of bump
    names (``minor alpha``, ...) -- exactly what ``release`` accepts -- so the
    prediction always matches what a real release would apply. Always a dry
    run: nothing is changed. Returns None when ``args`` are not a form uv will
    accept.
    """
    result = _run_version(args, dry_run=True)
    return result[1] if result is not None else None

def v_next_cli():
    parser = argparse.ArgumentParser(
        prog="v_next",
        description="Predict the version that `release` would produce.",
    )
    parser.add_argument(
        "bump",
        nargs="+",
        metavar="BUMP",
        help="a version number, or one or more bump names "
             "(major, minor, patch, stable, alpha, beta, rc, post, dev)",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"v_next (release {__version__})",
    )
    args = parser.parse_args()
    prediction = v_next(*args.bump)
    if prediction is None:
        sys.exit(USAGE)
    print(prediction)