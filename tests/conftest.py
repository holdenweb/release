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
    _git("init", "-q", cwd=proj)
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
