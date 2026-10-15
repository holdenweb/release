"""Shared fixtures for the release test-suite.

The tool is a thin orchestrator over ``uv`` and ``git``, so the integration
tests run against a real, throwaway uv project under git. The ``uv_project``
fixture builds that project and switches the working directory into it, so the
code under test operates on the temp project rather than this repository.
"""
import subprocess

import pytest


def _git(*args, cwd):
    """Run a git command in ``cwd``, failing loudly if it errors."""
    subprocess.run(("git", *args), cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def uv_project(tmp_path, monkeypatch):
    """A fresh ``uv init --lib`` project under git, with CWD switched into it.

    Git is configured with an identity and a non-interactive editor so that the
    tool's bare ``git commit`` (no ``-m``) completes without blocking. The
    starting version is uv's default of ``0.1.0``. Yields the project path.
    """
    proj = tmp_path / "demo-proj"
    subprocess.run(
        ("uv", "init", "--lib", "demo-proj"),
        cwd=tmp_path, check=True, capture_output=True,
    )
    # `uv init` has already made the repository, so this init is a no-op
    # re-init -- and `-b main` would be ignored outright ("warning: re-init:
    # ignored --initial-branch=main"). The branch has to be renamed instead,
    # which symbolic-ref can do because there are no commits yet.
    #
    # It is pinned because GitHub's runners set init.defaultBranch to master:
    # tests that named `main` passed here and failed there, while the tool
    # itself was correct and reported origin/master. That the *tool* reads the
    # branch name rather than assuming it is asserted separately, in
    # test_the_report_names_whatever_branch_you_are_on.
    _git("init", "-q", cwd=proj)
    _git("symbolic-ref", "HEAD", "refs/heads/main", cwd=proj)
    _git("config", "user.email", "test@example.com", cwd=proj)
    _git("config", "user.name", "Test Runner", cwd=proj)
    _git("add", "-A", cwd=proj)
    _git("commit", "-qm", "initial", cwd=proj)

    monkeypatch.chdir(proj)
    # Make the tool's interactive `git commit` non-interactive: git invokes
    # `sh -c "<GIT_EDITOR> <file>"`, so this writes a message into the file.
    monkeypatch.setenv("GIT_EDITOR", "printf 'release commit\\n' >")
    return proj


@pytest.fixture
def non_project_dir(tmp_path, monkeypatch):
    """A directory with no pyproject.toml anywhere above it, set as CWD."""
    here = tmp_path / "empty"
    here.mkdir()
    monkeypatch.chdir(here)
    return here


def git_tags(cwd="."):
    out = subprocess.run(
        ("git", "tag"), cwd=cwd, capture_output=True, text=True, check=True
    )
    return out.stdout.split()


def _git_out(*args, cwd):
    """Run a git command in ``cwd`` and return its stripped stdout."""
    return subprocess.run(
        ("git", *args), cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def uv_project_with_remote(uv_project):
    """``uv_project`` with a local bare repository as ``origin``, branch pushed.

    The remote is a ``git init --bare`` directory beside the project, so the
    tests exercise real push/fetch plumbing without anything leaving the
    machine. The branch is pushed with ``-u`` so it has an upstream, which is
    what the remote-tracking checks read. Yields (project path, bare path).
    """
    bare = uv_project.parent / "remote.git"
    # -b main here too, and for a second reason: a bare repository's own HEAD
    # is what `git clone` resolves to pick a branch. Left at the host's
    # default it names a ref the repository does not have, so a clone checks
    # out nothing and a push from it advances no branch -- which quietly
    # turned the "remote has moved on" tests into no-ops.
    _git("init", "-q", "--bare", "-b", "main", str(bare), cwd=uv_project.parent)
    _git("remote", "add", "origin", str(bare), cwd=uv_project)
    branch = _git_out("symbolic-ref", "--short", "HEAD", cwd=uv_project)
    _git("push", "-q", "-u", "origin", branch, cwd=uv_project)
    return uv_project, bare
