"""Integration tests for the end-to-end ``release()`` flow.

These call ``release()`` in-process inside the ``uv_project`` fixture, so they
drive the real uv/git sequence: vet, bump, lock, commit, tag.
"""
import subprocess

import pytest

from release import release
from release.setver import read_version, v_next

from conftest import git_tags

pytestmark = pytest.mark.integration


def test_v_next_predicts_what_release_applies(uv_project):
    # The whole point of v_next: its prediction must equal the version a real
    # release actually writes, for the same (multi-bump) arguments.
    predicted = v_next("minor", "alpha")
    release("minor", "alpha")
    assert read_version()[1] == predicted


def _last_commit_subject():
    return subprocess.run(
        ("git", "log", "-1", "--pretty=%s"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_release_explicit_version_commits_and_tags(uv_project):
    release("0.3.0")
    assert read_version()[1] == "0.3.0"
    assert "r0.3.0" in git_tags()
    assert _last_commit_subject() == "release commit"


def test_release_bump_chain_commits_and_tags(uv_project):
    release("patch", "alpha")
    assert read_version()[1] == "0.1.1a1"
    assert "r0.1.1a1" in git_tags()


def test_release_records_version_in_pyproject_only(uv_project):
    # version.py writing was removed: the version is tracked solely in
    # pyproject.toml (which the release commit captures), and no stray
    # version.py is written into the project.
    release("minor")
    assert read_version()[1] == "0.2.0"
    assert not (uv_project / "src" / "demo_proj" / "version.py").exists()


def test_release_refuses_to_overwrite_existing_tag(uv_project):
    # Regression: the old code used `git tag -f`, silently clobbering an
    # existing tag after already mutating pyproject. Now it must refuse *before*
    # changing anything, leaving the version untouched (no half-release).
    subprocess.run(("git", "tag", "r0.1.1"), check=True, capture_output=True)
    with pytest.raises(SystemExit) as exc:
        release("patch")  # would bump 0.1.0 -> 0.1.1, whose tag already exists
    assert "already exists" in str(exc.value)
    assert read_version()[1] == "0.1.0"  # version not bumped


# --- command-line options -----------------------------------------------

def test_dry_run_previews_and_changes_nothing(uv_project, capsys):
    head_before = subprocess.run(
        ("git", "rev-parse", "HEAD"), capture_output=True, text=True, check=True
    ).stdout
    release("minor", dry_run=True)
    out = capsys.readouterr().out
    assert "0.2.0" in out                 # previews the prospective version
    assert read_version()[1] == "0.1.0"   # version untouched
    assert git_tags() == []               # no tag written
    head_after = subprocess.run(
        ("git", "rev-parse", "HEAD"), capture_output=True, text=True, check=True
    ).stdout
    assert head_before == head_after       # no new commit


def test_message_is_used_as_commit_subject(uv_project):
    release("minor", message="ship the minor")
    assert _last_commit_subject() == "ship the minor"


def test_dirty_tree_is_refused_by_default(uv_project, monkeypatch):
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    (uv_project / "README.md").write_text("uncommitted change\n")
    with pytest.raises(SystemExit):
        release("minor")
    assert read_version()[1] == "0.1.0"    # nothing released


def test_allow_dirty_proceeds_over_a_dirty_tree(uv_project, monkeypatch):
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    (uv_project / "README.md").write_text("uncommitted change\n")
    release("minor", allow_dirty=True)
    assert read_version()[1] == "0.2.0"
