import argparse
import os
import subprocess
import sys

from packaging.version import InvalidVersion, Version

from .errors import (
    GitError,
    MissingTool,
    NotAProjectError,
    ReleaseError,
    UsageError,
    UvError,
    VersionOrderError,
)
from .version import __version__

# Conventional spellings of "off". Treating every non-empty value as *on*
# silently disabled the safety checks for anyone who wrote RELEASE_NOCHECKS=0
# (or =false) meaning to turn them off.
OFF_VALUES = frozenset({"", "0", "false", "no", "off"})


def flag_is_set(value: str) -> bool:
    """True unless ``value`` is empty or one of the conventional "off" words."""
    return value.strip().lower() not in OFF_VALUES


RELEASE_NOCHECKS = flag_is_set(os.environ.get("RELEASE_NOCHECKS", ""))
TAG_PREFIX = os.environ.get("RELEASE_TAG_PREFIX", "r")

BUMPS = "major, minor, patch, stable, alpha, beta, rc, post, dev".split(", ")

def capture(cmd) -> subprocess.CompletedProcess:
    """Run ``cmd`` capturing its output, explaining a missing executable."""
    try:
        return subprocess.run(tuple(cmd), capture_output=True)
    except FileNotFoundError as exc:
        raise MissingTool(
            f"{cmd[0]!r} is not on your PATH; release needs both uv and git"
        ) from exc

def read_version() -> tuple[str, str]:
    """
    Return a tuple of (project name, version string) from ``uv version``.

    Raises NotAProjectError, relaying uv's own explanation, when the version
    cannot be read -- which covers both "no pyproject.toml here" and "the
    pyproject.toml is unreadable", so the message must not assert either.
    """
    result = capture(("uv", "version"))
    fields = result.stdout.decode("utf-8").split()
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8").strip()
        raise NotAProjectError(
            "could not read the project version"
            + (f"; uv said:\n{detail}" if detail else "")
        )
    if len(fields) != 2:
        raise NotAProjectError(
            f"could not read the project version: expected 'name version' from "
            f"`uv version`, got {result.stdout.decode('utf-8').strip()!r}"
        )
    name, version = fields
    return name, version

def _git(*args: str) -> str:
    """Return the stripped stdout of a git command, or raise GitError."""
    result = capture(("git", *args))
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8").strip()
        raise GitError(
            f"`git {' '.join(args)}` failed"
            + (f":\n{detail}" if detail else f" (exit status {result.returncode})")
        )
    return result.stdout.decode("utf-8").strip()

def git_is_dirty(*paths: str) -> bool:
    """True if tracked files differ from HEAD (staged or not).

    `git diff --quiet` exits 1 for "there are differences" but 128-ish for
    "this is not a repository". The old `!= 0` test reported the second as
    the first, so a directory with no git repo was announced as dirty.
    """
    result = capture(("git", "diff", "--quiet", *paths))
    if result.returncode in (0, 1):
        return result.returncode == 1
    detail = result.stderr.decode("utf-8").strip()
    raise GitError(
        "could not tell whether the working tree is clean"
        + (f":\n{detail}" if detail else f" (git exit status {result.returncode})")
    )

def git_ref_exists(ref: str) -> bool:
    """True if the fully-qualified git ref (refs/tags/x, refs/heads/y) exists.

    Unlike parsing `git tag --list`, this notices git failing: previously a
    broken or absent repository silently answered "no such tag", quietly
    disabling the anti-clobber guard.
    """
    result = capture(("git", "show-ref", "--verify", "--quiet", ref))
    if result.returncode in (0, 1):
        return result.returncode == 0
    detail = result.stderr.decode("utf-8").strip()
    raise GitError(
        f"could not look up {ref}"
        + (f":\n{detail}" if detail else f" (git exit status {result.returncode})")
    )

def snapshot_version() -> str:
    """
    Return the current version labelled with the git checkout id.

    e.g. ``1.4.0+g1a2b3c4`` on a clean tree, or ``1.4.0+g1a2b3c4.dirty`` when
    the working tree differs from HEAD. This is a PEP 440 *local* version: it
    sorts above the plain current version but below the next release, and
    installs everywhere except public indexes (PyPI rejects local versions).

    "Dirty" means tracked files differ from HEAD (staged or not); untracked
    files are not considered.
    """
    _, current = read_version()
    try:
        sha = _git("rev-parse", "--short=8", "HEAD")
    except GitError as exc:
        raise GitError(
            f"--snapshot needs a git repository with at least one commit ({exc})"
        ) from exc
    dirty = git_is_dirty("HEAD")
    return f"{current}+g{sha}.dirty" if dirty else f"{current}+g{sha}"

def _version_command(args: tuple[str, ...], dry_run: bool) -> list[str]:
    """Build the ``uv version`` command for ``args``, or raise UsageError.

    ``args`` is either a single explicit version number, or one or more bump
    names (``patch``, ``rc``, ...). These are exactly the forms ``release``
    accepts, so prediction and application stay in step.
    """
    if not args:
        raise UsageError(
            "no version number or bump name given; give a version number, or "
            f"one or more bump names: {', '.join(BUMPS)}"
        )
    cmd = ["uv", "version"]
    if dry_run:
        cmd.append("--dry-run")
    if len(args) == 1 and args[0] not in BUMPS:
        cmd.append(args[0])  # explicit version; let uv validate/normalise it
    elif all(arg in BUMPS for arg in args):
        for arg in args:
            cmd.extend(["--bump", arg])
    else:
        # A version number and bump names cannot be combined: name the tokens
        # that are not bumps rather than printing a bare usage line.
        strays = [a for a in args if a not in BUMPS]
        raise UsageError(
            f"cannot combine a version number with bump names: "
            f"{', '.join(repr(a) for a in strays)} "
            f"{'is not a bump name' if len(strays) == 1 else 'are not bump names'}. "
            f"bump names are: {', '.join(BUMPS)}"
        )
    return cmd

def _run_version(args: tuple[str, ...], dry_run: bool) -> tuple[str, str]:
    """Run ``uv version`` for ``args``; return (name, new version).

    Raises UsageError if the arguments are not a valid form, UvError if uv
    refuses them or answers in a shape we cannot read, and VersionOrderError
    if the result would move the version backwards.
    """
    cmd = _version_command(args, dry_run)
    result = capture(cmd)
    stdout = result.stdout.decode("utf-8")
    fields = stdout.split()
    applied = len(fields) == 4 and fields[2] == "=>"
    detail = result.stderr.decode("utf-8").strip()

    if result.returncode != 0:
        if applied:
            # uv rewrites pyproject.toml *before* re-locking, so a failure in
            # the follow-on step leaves the new version in the file. Saying
            # "uv would not apply it" here would be flatly untrue.
            raise UvError(
                f"uv set the version to {fields[3]} and then failed, so "
                f"pyproject.toml now says {fields[3]}"
                + (f"; uv said:\n{detail}" if detail else "")
            )
        # uv fails the same way for "that is not a version" and for "there is
        # no project here". Ask which, so an environment problem is reported as
        # itself -- and propagates past v_next -- instead of being blamed on
        # the arguments and flattened into None.
        read_version()
        raise UvError(
            f"uv will not accept {' '.join(args)!r}"
            + (f"; uv said:\n{detail}" if detail else "")
        )

    if not applied:
        raise UvError(
            f"could not read a new version from `{' '.join(cmd)}`; "
            f"it printed {stdout.strip()!r}"
        )
    name, old, _arrow, new_version = fields
    # Bump names always move forward, but an explicit version can go backwards;
    # refuse that (using PEP 440 ordering) unless checks are disabled.
    try:
        backwards = Version(new_version) < Version(old)
    except InvalidVersion as exc:
        raise UvError(f"uv reported a version release cannot parse: {exc}") from exc
    if not RELEASE_NOCHECKS and backwards:
        raise VersionOrderError(
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
    return _run_version(args, dry_run=dry_run)

def v_next(*args: str) -> str | None:
    """
    Predict the version that ``release`` would produce from ``args``.

    ``args`` may be a single explicit version number or a sequence of bump
    names (``minor alpha``, ...) -- exactly what ``release`` accepts -- so the
    prediction always matches what a real release would apply. Always a dry
    run: nothing is changed. Returns None when ``args`` are not a form uv will
    accept.
    """
    # None is this function's documented answer for "not a form uv accepts",
    # so argument-shaped failures are converted back. Policy refusals (a
    # downgrade) and environment failures (no project, no uv) still propagate:
    # a caller asking "what would this give?" should not be told None because
    # uv is missing.
    try:
        return _run_version(args, dry_run=True)[1]
    except (UsageError, UvError):
        return None

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
    try:
        prediction = v_next(*args.bump)
    except ReleaseError as exc:
        # argparse already owns exit 2; tool failures report themselves here.
        print(f"v_next: {exc}", file=sys.stderr)
        sys.exit(exc.exit_code)
    if prediction is None:
        print(f"v_next: {' '.join(args.bump)!r} is not a version number or "
              f"bump name that uv accepts; bump names are: "
              f"{', '.join(BUMPS)}", file=sys.stderr)
        sys.exit(1)
    print(prediction)