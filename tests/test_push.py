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


# --- --push: the preflight, which must refuse before mutating -------------

def _cli(*argv, monkeypatch):
    import sys
    from release import main
    monkeypatch.setattr(sys, "argv", ["release", *argv])
    main()


def _nothing_happened(proj):
    """Assert the tree is exactly as it was: ADR-0011's actual promise."""
    from release.setver import read_version
    assert read_version()[1] == "0.1.0"
    assert _git_out("tag", "-l") == ""
    assert _git_out("status", "--porcelain") == ""


def test_push_is_refused_when_no_remote_is_configured(uv_project, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _cli("--push", "minor", "-m", "cut", monkeypatch=monkeypatch)
    assert exc.value.code == 5
    _nothing_happened(uv_project)


def test_push_is_refused_on_a_detached_head(uv_project_with_remote, monkeypatch):
    proj, _bare = uv_project_with_remote
    subprocess.run(("git", "checkout", "-q", "--detach"),
                   check=True, capture_output=True)
    with pytest.raises(SystemExit) as exc:
        _cli("--push", "minor", "-m", "cut", monkeypatch=monkeypatch)
    assert exc.value.code == 5
    _nothing_happened(proj)


def test_push_is_refused_when_the_tag_is_already_on_the_remote(
        uv_project_with_remote, monkeypatch):
    # The genuinely new guard. The local anti-clobber check cannot see this:
    # the tag exists only on the remote, so `git_ref_exists` says no and the
    # release would be cut, tagged, and then refused at the push.
    proj, _bare = uv_project_with_remote
    subprocess.run(("git", "tag", "r0.2.0"), check=True, capture_output=True)
    subprocess.run(("git", "push", "-q", "origin", "r0.2.0"),
                   check=True, capture_output=True)
    subprocess.run(("git", "tag", "-d", "r0.2.0"), check=True, capture_output=True)
    with pytest.raises(SystemExit) as exc:
        _cli("--push", "minor", "-m", "cut", monkeypatch=monkeypatch)
    assert exc.value.code == 5
    _nothing_happened(proj)


def test_push_is_refused_when_the_branch_would_not_fast_forward(
        uv_project_with_remote, monkeypatch, tmp_path):
    proj, bare = uv_project_with_remote
    _advance_the_remote(bare, tmp_path)
    with pytest.raises(SystemExit) as exc:
        _cli("--push", "minor", "-m", "cut", monkeypatch=monkeypatch)
    assert exc.value.code == 5
    _nothing_happened(proj)


def test_dry_run_previews_the_destination_without_touching_it(
        uv_project_with_remote, monkeypatch, capsys):
    proj, bare = uv_project_with_remote
    before = _git_out("--git-dir", str(bare), "show-ref")
    _cli("-n", "--push", "minor", monkeypatch=monkeypatch)
    out = capsys.readouterr().out
    assert "origin" in out and "main" in out
    _nothing_happened(proj)
    assert _git_out("--git-dir", str(bare), "show-ref") == before


def test_dry_run_reports_a_refusal_rather_than_raising(
        uv_project_with_remote, monkeypatch, capsys, tmp_path):
    # The dry run's job is to show you everything that is wrong at once, the
    # way it already does for a dirty tree and a colliding tag.
    proj, bare = uv_project_with_remote
    _advance_the_remote(bare, tmp_path)
    _cli("-n", "--push", "minor", monkeypatch=monkeypatch)
    assert "!" in capsys.readouterr().out
    _nothing_happened(proj)


def test_a_development_version_has_no_release_to_push(
        uv_project_with_remote, monkeypatch):
    # ADR-0009: a dev version is committed and deliberately not tagged, so
    # there is no release for --push to send. `dev` is chained because uv
    # refuses a bare dev bump from a release -- "0.1.0 => 0.1.0.dev1 didn't
    # increase the version".
    proj, _bare = uv_project_with_remote
    with pytest.raises(SystemExit) as exc:
        _cli("--push", "minor", "dev", "-m", "cut", monkeypatch=monkeypatch)
    assert exc.value.code == 5
    _nothing_happened(proj)


def test_push_cannot_be_combined_with_snapshot(uv_project_with_remote,
                                               monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _cli("--snapshot", "--push", monkeypatch=monkeypatch)
    assert exc.value.code == 2


def test_push_needs_something_to_release(uv_project_with_remote, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _cli("--push", monkeypatch=monkeypatch)
    assert exc.value.code == 2


def test_push_is_refused_alongside_a_standalone_marker(uv_project_with_remote,
                                                       monkeypatch):
    # Marking is not a release (ADR-0018), so there is nothing to push.
    with pytest.raises(SystemExit) as exc:
        _cli("--mark-dev", "--push", monkeypatch=monkeypatch)
    assert exc.value.code == 2


def test_remote_without_push_is_a_usage_error(uv_project_with_remote,
                                              monkeypatch):
    # Otherwise it silently does nothing, which reads as "pushed to upstream".
    with pytest.raises(SystemExit) as exc:
        _cli("--remote", "upstream", "minor", "-m", "cut",
             monkeypatch=monkeypatch)
    assert exc.value.code == 2
