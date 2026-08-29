"""Integration tests for the end-to-end ``release()`` flow.

These call ``release()`` in-process inside the ``uv_project`` fixture, so they
drive the real uv/git sequence: vet, bump, lock, commit, tag.
"""
import subprocess
import sys

import pytest
from packaging.version import Version

from release import release, main, next_branch_name
from release.errors import (
    DirtyTree,
    GitError,
    UsageError,
    VersionOrderError,
)
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


def test_release_honours_custom_tag_prefix(uv_project, monkeypatch):
    monkeypatch.setattr("release.TAG_PREFIX", "v")
    release("minor")
    assert "v0.2.0" in git_tags()
    assert "r0.2.0" not in git_tags()


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
    with pytest.raises(GitError) as exc:
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
    with pytest.raises(DirtyTree) as exc:
        release("minor")
    assert exc.value.exit_code == 4        # the documented dirty-tree code
    assert read_version()[1] == "0.1.0"    # nothing released


def test_allow_dirty_proceeds_over_a_dirty_tree(uv_project, monkeypatch):
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    (uv_project / "README.md").write_text("uncommitted change\n")
    release("minor", allow_dirty=True)
    assert read_version()[1] == "0.2.0"


def test_release_refuses_a_downgrade(uv_project):
    release("1.0.0", message="baseline")
    with pytest.raises(VersionOrderError) as exc:
        release("0.9.0")                       # lower than 1.0.0
    assert "backwards" in str(exc.value)
    assert read_version()[1] == "1.0.0"        # unchanged: no half-release


def test_dry_run_also_refuses_a_downgrade(uv_project):
    release("1.0.0", message="baseline")
    with pytest.raises(VersionOrderError):
        release("0.9.0", dry_run=True)
    assert read_version()[1] == "1.0.0"


# --- --next: open the following development version ----------------------

def _commit_subjects(n):
    return subprocess.run(
        ("git", "log", f"-{n}", "--pretty=%s"),
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()


def test_next_opens_a_dev_version_after_the_release(uv_project):
    release("minor", message="cut 0.2.0", next_bump="patch")
    # The release itself happened and is tagged...
    assert git_tags() == ["r0.2.0"]
    # ...and the tree now sits on an untagged .dev version for the next one.
    assert read_version()[1] == "0.2.1.dev1"
    assert _commit_subjects(2) == ["Begin development of 0.2.1.dev1", "cut 0.2.0"]


def test_next_dev_commit_is_not_tagged(uv_project):
    release("minor", message="cut", next_bump="patch")
    # Only the release commit carries a tag; the dev commit must not add one.
    assert len(git_tags()) == 1
    assert "r0.2.1.dev1" not in git_tags()


def test_next_minor_aims_at_the_following_minor(uv_project):
    release("minor", message="cut", next_bump="minor")
    assert read_version()[1] == "0.3.0.dev1"


def test_next_dev_version_sorts_between_the_releases(uv_project):
    release("minor", message="cut", next_bump="patch")
    dev = Version(read_version()[1])
    assert Version("0.2.0") < dev < Version("0.2.1")
    assert dev.is_prerelease          # so pip needs --pre to pick it up


def test_dry_run_does_not_open_the_next_version(uv_project, capsys):
    release("minor", dry_run=True, next_bump="patch")
    assert "patch dev version would be committed" in capsys.readouterr().out
    assert read_version()[1] == "0.1.0"
    assert git_tags() == []


def test_cli_next_requires_a_bump_argument(uv_project, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["release", "--next", "patch"])
    with pytest.raises(SystemExit):
        main()
    assert read_version()[1] == "0.1.0"


def test_cli_next_rejects_a_non_release_bump_name(uv_project, monkeypatch):
    # --next only accepts major/minor/patch; the `dev` chaining is implicit.
    monkeypatch.setattr(sys, "argv", ["release", "--next", "dev", "minor"])
    with pytest.raises(SystemExit):
        main()


def test_cli_next_conflicts_with_snapshot(uv_project, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["release", "--snapshot", "--next", "patch"])
    with pytest.raises(SystemExit):
        main()


# --- --next: the development branch --------------------------------------

def _branch():
    return subprocess.run(
        ("git", "rev-parse", "--abbrev-ref", "HEAD"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _rev(ref):
    return subprocess.run(
        ("git", "rev-parse", ref), capture_output=True, text=True, check=True
    ).stdout.strip()


def test_next_branch_name_drops_the_dev_counter():
    # The branch is named for the version left in pyproject.toml, minus the dev
    # counter, so it survives later `release dev` bumps. No tag prefix, so it
    # can never collide with a release tag.
    assert next_branch_name("0.7.4.dev1") == "0.7.4.dev"
    assert next_branch_name("0.7.4.dev12") == "0.7.4.dev"
    assert next_branch_name("1.0.0.dev1") == "1.0.0.dev"


def test_next_creates_and_switches_to_the_dev_branch(uv_project):
    released_on = _branch()
    release("minor", message="cut 0.2.0", next_bump="patch")
    assert _branch() == "0.2.1.dev"                  # now on the dev branch
    assert read_version()[1] == "0.2.1.dev1"


def test_release_commit_stays_on_the_original_branch(uv_project):
    released_on = _branch()
    release("minor", message="cut 0.2.0", next_bump="patch")
    # The release commit and its tag stay put; only the .dev commit moves on.
    assert _rev(released_on) == _rev("r0.2.0")
    assert _rev("HEAD") != _rev(released_on)
    assert _last_commit_subject() == "Begin development of 0.2.1.dev1"


def test_next_refuses_an_existing_branch_after_releasing(uv_project):
    subprocess.run(("git", "branch", "0.2.1.dev"), check=True, capture_output=True)
    with pytest.raises(GitError) as exc:
        release("minor", message="cut", next_bump="patch")
    assert "already exists" in str(exc.value)
    # The release itself succeeded, and the message must say so rather than
    # claiming the whole thing was aborted.
    assert "release itself succeeded" in str(exc.value)
    assert "r0.2.0" in git_tags()


def test_library_caller_gets_a_clear_error_for_a_bad_next_bump(uv_project):
    # Checked up front, so a bad library call cannot report a usage problem
    # *after* a successful, tagged release.
    with pytest.raises(UsageError) as exc:
        release("minor", next_bump="bogus")
    assert "bogus" in str(exc.value)
    assert read_version()[1] == "0.1.0"      # nothing released
    assert git_tags() == []
