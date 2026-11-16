import argparse
import os
import subprocess
import sys
from typing import NamedTuple

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

def capture(cmd, timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run ``cmd`` capturing its output, explaining a missing executable.

    ``timeout`` is for the commands that talk to a remote: those can block for
    as long as the network lets them, and a bare `release` is a status command
    nobody expects to hang. TimeoutExpired is left to the caller, which knows
    whether "I could not find out" is an answer it can report.
    """
    try:
        return subprocess.run(tuple(cmd), capture_output=True, timeout=timeout)
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

def _release_tags() -> list[tuple[str, Version]]:
    """The repository's release tags, as (tag name, version) pairs.

    Tags that do not parse as a version once the prefix is stripped are
    ignored: a repository may carry tags this tool did not create. The name is
    carried alongside the version because the two do not round-trip -- Version
    normalises, so a hand-made `r01.8.2` would be rebuilt as `r01.8.2` ->
    `1.8.2` -> `r1.8.2`, naming a ref that does not exist.
    """
    try:
        listing = _git("tag", "--list", f"{TAG_PREFIX}*")
    except GitError:
        return []
    tags = []
    for name in listing.split():
        try:
            tags.append((name, Version(name[len(TAG_PREFIX):])))
        except InvalidVersion:
            continue
    return tags

def highest_tag_version() -> Version | None:
    """The greatest version among the repository's release tags, or None."""
    tags = _release_tags()
    return max(version for _name, version in tags) if tags else None

def highest_release_tag() -> str | None:
    """The name of the tag carrying the greatest version, or None."""
    tags = _release_tags()
    return max(tags, key=lambda pair: pair[1])[0] if tags else None

def git_head_sha() -> str:
    """The full commit id of HEAD, or GitError if it cannot be read.

    Recorded explicitly rather than pushing the name ``HEAD``, because the
    marker commit lands on top of the release before anyone re-reads it: a
    recovery command naming HEAD would send the wrong commit a minute later.
    """
    return _git("rev-parse", "HEAD")

def git_current_branch() -> str | None:
    """The branch HEAD is on, or None when HEAD is detached.

    Detached is not an error -- it is a legitimate state that simply has no
    branch to push, which is the caller's problem to report. A genuine git
    failure (exit 128, e.g. no repository here) still raises, so a broken
    environment is not answered with a shrug.
    """
    result = capture(("git", "symbolic-ref", "--quiet", "--short", "HEAD"))
    if result.returncode not in (0, 1):
        detail = result.stderr.decode("utf-8").strip()
        raise GitError(
            "could not tell which branch HEAD is on"
            + (f":\n{detail}" if detail else f" (git exit status {result.returncode})")
        )
    return result.stdout.decode("utf-8").strip() or None

def git_remote_url(remote: str) -> str | None:
    """The configured URL for ``remote``, or None if it is not configured.

    `git config --get` is the probe rather than `git remote`, which exits 0
    with empty output when no remote exists: success and "there is nothing"
    would be the same answer, which is how the tool used to mistake a broken
    repository for an absent tag.
    """
    result = capture(("git", "config", "--get", f"remote.{remote}.url"))
    if result.returncode not in (0, 1):
        detail = result.stderr.decode("utf-8").strip()
        raise GitError(
            f"could not look up the remote {remote!r}"
            + (f":\n{detail}" if detail else f" (git exit status {result.returncode})")
        )
    return result.stdout.decode("utf-8").strip() or None

def upstream_remote() -> str | None:
    """The remote the current branch tracks, e.g. ``origin``.

    `git config --get branch.<name>.remote`, not the first path segment of
    `@{upstream}`: a branch name may itself contain a slash, so splitting
    "origin/feature/x" guesses. Measured: exit 1 when the branch has no
    upstream, which is the same silence as having no remote at all -- a
    project that is deliberately never pushed anywhere must not be nagged.
    """
    branch = git_current_branch()
    if branch is None:
        return None
    result = capture(("git", "config", "--get", f"branch.{branch}.remote"))
    if result.returncode not in (0, 1):
        detail = result.stderr.decode("utf-8").strip()
        raise GitError(
            f"could not look up the remote for branch {branch!r}"
            + (f":\n{detail}" if detail else f" (git exit status {result.returncode})")
        )
    return result.stdout.decode("utf-8").strip() or None

def remote_tag_sha(remote: str, tag: str,
                   timeout: float | None = None) -> str | None:
    """The commit ``tag`` names on ``remote``, or None if the remote lacks it.

    `--exit-code` makes the three answers distinguishable: 0 present, 2 absent,
    128 unreachable. The usual (0, 1) pair would be wrong here -- absent is 2,
    so a first release to a fresh remote would look like a failure, and an
    unreachable remote would look like "the tag is not there", letting the
    preflight pass and the push fail instead.

    The query carries a trailing glob so that an *annotated* tag's peeled
    `^{}` line is returned alongside it, and the peeled line wins. Verified:
    for an annotated tag, plain `ls-remote refs/tags/x` answers with the tag
    object, not the commit, so comparing it against a local `rev-list -1`
    would report every annotated tag as having moved. The glob can over-match
    (`refs/tags/r0.2.0*` also matches `r0.2.0a1`), so the lines are filtered
    back to this exact ref.
    """
    result = capture(
        ("git", "ls-remote", "--exit-code", "--tags", remote, f"refs/tags/{tag}*"),
        timeout=timeout,
    )
    if result.returncode == 2:
        return None
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8").strip()
        raise GitError(
            f"could not reach the remote {remote!r} to check for the tag {tag!r}"
            + (f":\n{detail}" if detail else f" (git exit status {result.returncode})")
        )
    wanted = {f"refs/tags/{tag}": None, f"refs/tags/{tag}^{{}}": None}
    for line in result.stdout.decode("utf-8").splitlines():
        sha, _, ref = line.partition("\t")
        if ref in wanted:
            wanted[ref] = sha.strip()
    # The peeled commit if this is an annotated tag, else the ref itself.
    return wanted[f"refs/tags/{tag}^{{}}"] or wanted[f"refs/tags/{tag}"]

def push_would_be_refused(remote: str, branch: str) -> str | None:
    """git's refusal if pushing HEAD to ``branch`` would be rejected, else None.

    HEAD, not the release commit, because this runs before anything has been
    written and the release commit does not exist yet (ADR-0011). It is a sound
    proxy: the release commit will be HEAD's child, and a child of a
    fast-forwardable commit fast-forwards too.

    Verified to write nothing -- the remote's refs are byte-identical either
    side of the call. Verified incomplete, too: `--dry-run` does not run the
    receiving repository's hooks, so a hook or branch protection that declines
    the ref passes here and fails at the real push. The atomic push and its
    consequence message are the actual guard; this only turns the common
    refusals into a refusal before mutating.
    """
    result = capture(
        ("git", "push", "--dry-run", "--atomic", remote, f"HEAD:refs/heads/{branch}")
    )
    if result.returncode == 0:
        return None
    # git writes the rejection to stderr; stdout carries the ref listing.
    detail = result.stderr.decode("utf-8").strip()
    return detail or f"git push exited {result.returncode}"

# Long enough that a slow link still answers, short enough that a bare
# `release` on a train does not feel broken.
REMOTE_TIMEOUT = 5.0


class TagState(NamedTuple):
    """How the newest release tag stands on the remote that would publish it."""
    tag: str
    remote: str
    state: str                 # "absent" | "moved" | "unreachable"
    remote_sha: str | None


def release_tag_state(timeout: float | None = REMOTE_TIMEOUT) -> TagState | None:
    """What the remote says about the newest release tag, or None if all is well.

    The remote has to be asked. Pushing the *tag* is what triggers publication,
    and git keeps no local record of which tags a remote holds: the default
    fetch refspec is `+refs/heads/*:refs/remotes/origin/*`, branches only, and
    a fetched tag lands in `refs/tags/*` indistinguishable from one made here.
    So there is no offline answer to the only question that matters.

    This replaces a check that resolved the tag to its commit and asked whether
    *that* had reached `origin/<branch>` -- a different question, wrong in both
    directions. Push the branch by hand and it fell silent on a release that
    was never published; push only the tag and it complained about one that
    was.

    None when there is nothing to say: no upstream remote, no release tags, or
    the remote has the tag at the expected commit. An unreachable remote is
    reported rather than swallowed -- "I could not find out" must not read the
    same as "all is well", which is the failure being fixed here.
    """
    try:
        remote = upstream_remote()
        tag = highest_release_tag()
        if remote is None or tag is None:
            return None
        local_sha = _git("rev-list", "-1", tag)
        try:
            remote_sha = remote_tag_sha(remote, tag, timeout=timeout)
        except (GitError, subprocess.TimeoutExpired):
            return TagState(tag, remote, "unreachable", None)
        if remote_sha is None:
            return TagState(tag, remote, "absent", None)
        if remote_sha != local_sha:
            return TagState(tag, remote, "moved", remote_sha)
        return None
    except GitError:
        # Matches describe_head and highest_tag_version: a bare `release`
        # reports what it can, and an audit note is not worth failing over.
        return None

def describe_head() -> tuple[str | None, str | None]:
    """Return (exact tag on HEAD, nearest description), either possibly None.

    This is how the tool answers "is this commit a release?" -- the question
    the version in pyproject.toml cannot answer, because it keeps saying the
    last release long after that commit.
    """
    exact = nearest = None
    try:
        exact = _git("describe", "--tags", "--exact-match", "HEAD")
    except GitError:
        try:
            nearest = _git("describe", "--tags")
        except GitError:
            pass
    return exact, nearest

# Pushing the tag is the publication trigger, so each of these says what the
# remote's answer means for publication, not merely what the refs look like.
TAG_NOTES = {
    "absent": lambda t: (f"{t.tag} has not been pushed to {t.remote}, so "
                         f"nothing has been published from it"),
    "moved": lambda t: (f"{t.tag} on {t.remote} points at "
                        f"{t.remote_sha[:8]}, not the commit tagged here: "
                        f"what was published is not what you released"),
    "unreachable": lambda t: (f"could not reach {t.remote} to check whether "
                              f"{t.tag} was pushed"),
}


def version_report() -> str:
    """One line describing the version *and* whether this commit is a release.

    `release` with no arguments used to print only the version, which is the
    one fact that cannot reveal a disagreement between the tree and its tags.
    """
    name, current = read_version()
    exact, nearest = describe_head()
    if exact is not None:
        state = f"released as {exact}"
    elif nearest is not None:
        state = f"untagged; nearest tag {nearest}"
    else:
        state = "untagged, and no release tag found"
    notes = []
    highest = highest_tag_version()
    if highest is not None and Version(current) < highest:
        notes.append(f"{highest} is already tagged, which is higher than this tree")
    tag_state = release_tag_state()
    if tag_state is not None:
        notes.append(TAG_NOTES[tag_state.state](tag_state))
    return f"{name} {current} -- {state}" + "".join(f"  ! {n}" for n in notes)

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

def _run_version(args: tuple[str, ...], dry_run: bool) -> tuple[str, str, str]:
    """Run ``uv version`` for ``args``; return (name, old version, new version).

    The old version is reported because deciding what a release would land on
    needs both ends: uv carries a local segment through a bump, and only the
    version it started from says whether the segment was already there.

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
    name, old_version, _arrow, new_version = fields
    # Bump names always move forward, but an explicit version can go backwards;
    # refuse that (using PEP 440 ordering) unless checks are disabled.
    try:
        backwards = Version(new_version) < Version(old_version)
    except InvalidVersion as exc:
        raise UvError(f"uv reported a version release cannot parse: {exc}") from exc
    if not RELEASE_NOCHECKS and backwards:
        raise VersionOrderError(
            f"{new_version} is lower than the current version {old_version}: "
            "refusing to "
            "move the version backwards (set RELEASE_NOCHECKS to override)"
        )
    return name, old_version, new_version

def strip_carried_marker(current: str, predicted: str) -> str:
    """``predicted`` with a carried ``+dev`` marker removed, if it carried one.

    uv carries a local segment through a bump -- verified, `0.8.0+dev --bump
    patch` gives `0.8.1+dev`, and only an *explicit* version clears it -- so a
    release cut from a marked commit would inherit the marker and could never
    be tagged (ADR-0009).

    Only the marker this tool applied is stripped, and only when the prediction
    still carries that same segment: a different local version is the caller's
    own and is left exactly as asked for.

    This lives here, and not inside `release`, because `v_next` promises to
    predict what `release` would apply. While the rule was inline in `release`
    the two disagreed on every bump from a marked tree -- `0.2.1+dev` against
    the `0.2.1` actually released -- which, since `--mark-dev` is the normal
    state between releases, was most of the time.
    """
    carried = (Version(current).local is not None
               and Version(predicted).local == Version(current).local)
    return Version(predicted).public if carried else predicted

def update_project_version(*args: str, dry_run: bool = False) -> tuple[str, str]:
    """
    Update 'project.version' and write it back, returning (name, new version).

    ``args`` is either a single new version string, or a sequence of bump
    names applied in order. Exits with a usage message if it is neither.
    """
    name, _old, new_version = _run_version(args, dry_run=dry_run)
    return name, new_version

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
        _name, current, predicted = _run_version(args, dry_run=True)
        return strip_carried_marker(current, predicted)
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