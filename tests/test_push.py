"""Sending a release to a remote.

Every test here builds a local ``git init --bare`` repository as the remote, so
the real push plumbing runs -- refspecs, atomicity, rejection -- without
anything leaving the machine.
"""
import subprocess

import pytest

from release.errors import GitError

pytestmark = pytest.mark.integration


def _git_out(*args):
    return subprocess.run(
        ("git", *args), capture_output=True, text=True, check=True
    ).stdout.strip()


# --- the local probes: what can be known without touching the network -----

def test_current_branch_names_the_branch(uv_project):
    from release.setver import git_current_branch
    # Checked against a different git spelling rather than the same one, so
    # the test is evidence and not a tautology.
    assert git_current_branch() == _git_out("branch", "--show-current") != ""


def test_current_branch_is_none_when_head_is_detached(uv_project):
    # Not an error: a detached HEAD is a legitimate state. It simply has no
    # branch to push, which is the caller's problem to report.
    from release.setver import git_current_branch
    subprocess.run(("git", "checkout", "-q", "--detach"),
                   check=True, capture_output=True)
    assert git_current_branch() is None


def test_current_branch_raises_outside_a_repository(non_project_dir):
    # git exits 128 here, not 1. Folding that into "no branch" would answer a
    # broken environment with a shrug, which is the bug git_ref_exists was
    # written to avoid.
    from release.setver import git_current_branch
    with pytest.raises(GitError):
        git_current_branch()


def test_remote_url_finds_the_configured_remote(uv_project_with_remote):
    from release.setver import git_remote_url
    _proj, bare = uv_project_with_remote
    assert git_remote_url("origin") == str(bare)


def test_remote_url_is_none_for_a_remote_that_is_not_configured(
        uv_project_with_remote):
    from release.setver import git_remote_url
    assert git_remote_url("upstream") is None


def test_remote_url_is_none_when_there_are_no_remotes_at_all(uv_project):
    # `git remote` would exit 0 with empty output here, so it cannot be the
    # probe: success and "there is nothing" would be the same answer.
    from release.setver import git_remote_url
    assert git_remote_url("origin") is None


# --- the network probes: what only the remote can answer ------------------

def _advance_the_remote(bare, tmp_path):
    """Let someone else push to ``bare``, so our branch is no longer a ff."""
    other = tmp_path / "other"
    subprocess.run(("git", "clone", "-q", str(bare), str(other)),
                   check=True, capture_output=True)
    for cmd in (("config", "user.email", "other@example.com"),
                ("config", "user.name", "Someone Else"),
                ("commit", "-q", "--allow-empty", "-m", "their work"),
                ("push", "-q", "origin", "HEAD")):
        subprocess.run(("git", *cmd), cwd=other, check=True, capture_output=True)


def test_remote_tag_sha_finds_a_tag_on_the_remote(uv_project_with_remote):
    from release.setver import remote_tag_sha
    subprocess.run(("git", "tag", "r9.9.9"), check=True, capture_output=True)
    subprocess.run(("git", "push", "-q", "origin", "r9.9.9"),
                   check=True, capture_output=True)
    assert remote_tag_sha("origin", "r9.9.9") == _git_out("rev-parse", "r9.9.9")


def test_remote_tag_sha_is_none_when_the_remote_has_no_such_tag(
        uv_project_with_remote):
    # git exits 2 here, not 1: the usual (0, 1) pair would read "absent" as a
    # failure and refuse every first release.
    from release.setver import remote_tag_sha
    assert remote_tag_sha("origin", "r9.9.9") is None


def test_remote_tag_sha_raises_when_the_remote_is_unreachable(uv_project):
    # Exit 128. Reading this as "the tag is not there" would let the preflight
    # pass on an unreachable remote and fail at the push instead -- exactly the
    # half-done release ADR-0011 exists to prevent.
    from release.setver import remote_tag_sha
    with pytest.raises(GitError) as exc:
        remote_tag_sha("/nonexistent/nope.git", "r1.0.0")
    assert "could not reach" in str(exc.value)


def test_push_is_not_refused_when_the_branch_fast_forwards(
        uv_project_with_remote):
    from release.setver import push_would_be_refused
    assert push_would_be_refused("origin", "main") is None


def test_push_is_refused_when_the_remote_has_moved_on(
        uv_project_with_remote, tmp_path):
    from release.setver import push_would_be_refused
    _proj, bare = uv_project_with_remote
    before = _git_out("--git-dir", str(bare), "show-ref")
    _advance_the_remote(bare, tmp_path)
    subprocess.run(("git", "commit", "-q", "--allow-empty", "-m", "our work"),
                   check=True, capture_output=True)
    refusal = push_would_be_refused("origin", "main")
    assert refusal is not None and "rejected" in refusal
    # The probe must be a probe: it advanced nothing of its own.
    after = _git_out("--git-dir", str(bare), "show-ref")
    assert after != before                       # only the other clone moved it
    assert _git_out("rev-parse", "HEAD") not in after


def test_the_probe_checks_head_because_the_release_commit_does_not_exist_yet(
        uv_project_with_remote):
    # The preflight runs before anything is written, so there is no release
    # commit to dry-run. HEAD is a sound proxy: the release commit will be its
    # child, and a child of a fast-forwardable commit fast-forwards too.
    from release.setver import push_would_be_refused
    subprocess.run(("git", "commit", "-q", "--allow-empty", "-m", "ahead"),
                   check=True, capture_output=True)
    assert push_would_be_refused("origin", "main") is None
