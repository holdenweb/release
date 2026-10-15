"""Integration tests for the end-to-end ``release()`` flow.

These call ``release()`` in-process inside the ``uv_project`` fixture, so they
drive the real uv/git sequence: vet, bump, lock, commit, tag.
"""
import subprocess
import sys

import pytest
from packaging.version import Version

from release import release, main
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


# --- --mark-dev: mark the commit after a release as unreleased ------------

def _commit_subjects(n):
    return subprocess.run(
        ("git", "log", f"-{n}", "--pretty=%s"),
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()


def _branch():
    return subprocess.run(
        ("git", "rev-parse", "--abbrev-ref", "HEAD"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_mark_dev_writes_a_local_marker_on_the_released_version(uv_project):
    # CPython's scheme: a local segment on the version just shipped, which
    # claims nothing about what the next release will be.
    release("minor", message="cut 0.2.0", mark_dev=True)
    assert read_version()[1] == "0.2.0+dev"
    assert _commit_subjects(2) == ["Begin development after 0.2.0", "cut 0.2.0"]


def test_the_marker_is_not_tagged_and_makes_no_branch(uv_project):
    before = _branch()
    release("minor", message="cut", mark_dev=True)
    assert git_tags() == ["r0.2.0"]        # only the release carries a tag
    assert _branch() == before             # and no branch was created


def test_the_marker_sorts_between_the_releases(uv_project):
    release("minor", message="cut", mark_dev=True)
    marker = Version(read_version()[1])
    assert Version("0.2.0") < marker < Version("0.2.1")


def test_releasing_from_a_marked_tree_strips_the_marker(uv_project):
    # uv carries a local segment through a bump (0.2.0+dev --bump patch gives
    # 0.2.1+dev), so without stripping, every later release would inherit it
    # and could never be tagged.
    release("minor", message="cut", mark_dev=True)
    assert read_version()[1] == "0.2.0+dev"
    release("patch", message="next one")
    assert read_version()[1] == "0.2.1"    # marker gone
    assert "r0.2.1" in git_tags()          # and therefore taggable


def test_a_local_version_is_never_tagged(uv_project):
    # Verified: Version("0.2.0+dev").dev is None and git accepts the ref name,
    # so testing .dev alone left a hole the marker walks straight into.
    release("0.2.0+dev", message="explicitly local")
    assert read_version()[1] == "0.2.0+dev"
    assert git_tags() == []


def test_dry_run_previews_the_marker_without_writing_it(uv_project, capsys):
    release("minor", dry_run=True, mark_dev=True)
    assert "0.2.0+dev would be committed" in capsys.readouterr().out
    assert read_version()[1] == "0.1.0"
    assert git_tags() == []


# --- the release history, not just the file ------------------------------

def test_release_refuses_a_version_below_the_highest_tag(uv_project):
    # ADR-0005 compares against pyproject.toml, which tracks one line of edits.
    # A tag made by hand, or a branch, can put the release history ahead of the
    # file -- the state this repository was found in.
    release("1.0.0", message="baseline")
    subprocess.run(("git", "checkout", "-q", "-b", "side", "HEAD~1"),
                   check=True, capture_output=True)
    with pytest.raises(VersionOrderError) as exc:
        release("patch")                   # 0.1.1, below the tagged 1.0.0
    assert "already tagged" in str(exc.value)


def test_bare_release_reports_whether_this_commit_is_a_release(uv_project, capsys):
    release("minor", message="cut")
    monkey = capsys.readouterr()           # discard release output
    from release.setver import version_report
    assert "released as r0.2.0" in version_report()
    subprocess.run(("git", "commit", "-q", "--allow-empty", "-m", "after"),
                   check=True, capture_output=True)
    assert "untagged" in version_report()


# --- --mark-dev on its own ------------------------------------------------

def _cli(*argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["release", *argv])
    main()


def test_mark_dev_alone_marks_an_already_released_tree(uv_project, monkeypatch):
    # The marker is derived from the version in the tree, so there is nothing
    # to guess and nothing to bump -- unlike the superseded --next.
    release("minor", message="cut")            # released WITHOUT marking
    assert read_version()[1] == "0.2.0"
    _cli("--mark-dev", monkeypatch=monkeypatch)
    assert read_version()[1] == "0.2.0+dev"
    assert git_tags() == ["r0.2.0"]            # still only the release is tagged
    assert _last_commit_subject() == "Begin development after 0.2.0"


def test_mark_dev_alone_is_idempotent(uv_project, monkeypatch, capsys):
    release("minor", message="cut", mark_dev=True)
    head = subprocess.run(("git", "rev-parse", "HEAD"), capture_output=True,
                          text=True, check=True).stdout
    capsys.readouterr()
    _cli("--mark-dev", monkeypatch=monkeypatch)
    assert "already marked as unreleased" in capsys.readouterr().out
    after = subprocess.run(("git", "rev-parse", "HEAD"), capture_output=True,
                           text=True, check=True).stdout
    assert head == after                        # no second commit


def test_mark_dev_alone_refuses_a_dirty_tree(uv_project, monkeypatch):
    release("minor", message="cut")
    (uv_project / "README.md").write_text("uncommitted\n")
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    # Through the CLI, so the boundary turns DirtyTree into its exit code.
    with pytest.raises(SystemExit) as exc:
        _cli("--mark-dev", monkeypatch=monkeypatch)
    assert exc.value.code == 4
    assert read_version()[1] == "0.2.0"         # unmarked


def test_mark_dev_alone_says_when_the_commit_is_not_a_release(uv_project,
                                                              monkeypatch, capsys):
    release("minor", message="cut")
    subprocess.run(("git", "commit", "-q", "--allow-empty", "-m", "later work"),
                   check=True, capture_output=True)
    capsys.readouterr()
    _cli("--mark-dev", monkeypatch=monkeypatch)
    out = capsys.readouterr().out
    assert "Marked unreleased: 0.2.0+dev" in out
    assert "this commit is not a release" in out


def test_mark_dev_alone_dry_run_changes_nothing(uv_project, monkeypatch, capsys):
    release("minor", message="cut")
    _cli("--mark-dev", "--dry-run", monkeypatch=monkeypatch)
    assert "would mark 0.2.0 -> 0.2.0+dev" in capsys.readouterr().out
    assert read_version()[1] == "0.2.0"


def test_mark_dev_alone_takes_a_message(uv_project, monkeypatch):
    release("minor", message="cut")
    _cli("--mark-dev", "-m", "open the next cycle", monkeypatch=monkeypatch)
    assert _last_commit_subject() == "open the next cycle"


# --- is the release anywhere but this laptop? ----------------------------

def _push_the_release(tag):
    """Send the release commit and its tag the way ADR-0019 specifies.

    The branch refspec is the release commit's SHA, not the branch name, so
    the remote's branch tip is the release itself rather than whatever the
    marker left on top of it.
    """
    sha = subprocess.run(("git", "rev-list", "-1", tag), capture_output=True,
                         text=True, check=True).stdout.strip()
    branch = subprocess.run(("git", "symbolic-ref", "--short", "HEAD"),
                            capture_output=True, text=True,
                            check=True).stdout.strip()
    subprocess.run(
        ("git", "push", "--atomic", "origin", f"{sha}:refs/heads/{branch}",
         f"refs/tags/{tag}:refs/tags/{tag}"),
        check=True, capture_output=True,
    )
    subprocess.run(("git", "fetch", "-q", "origin"), check=True, capture_output=True)


def test_bare_release_says_when_the_release_is_not_on_the_remote(uv_project_with_remote):
    # The gap that let five tags pile up unnoticed: the tool's output was
    # byte-identical whether the release had been pushed or not.
    from release.setver import version_report
    release("minor", message="cut")
    assert "r0.2.0 is not on origin/main" in version_report()


def test_bare_release_is_quiet_once_the_release_is_pushed(uv_project_with_remote):
    from release.setver import version_report
    release("minor", message="cut")
    _push_the_release("r0.2.0")
    assert "is not on" not in version_report()


def test_the_dev_marker_staying_local_is_not_reported_as_unpushed(uv_project_with_remote):
    # The marker is meant to stay on this machine (ADR-0016), so it must not
    # trip the warning: what is checked is the release tag, not HEAD.
    from release.setver import version_report
    release("minor", message="cut", mark_dev=True)
    _push_the_release("r0.2.0")
    assert "is not on" not in version_report()


def test_upstream_ref_names_the_remote_tracking_branch(uv_project_with_remote):
    from release.setver import upstream_ref
    assert upstream_ref() == "origin/main"


def test_the_report_names_whatever_branch_you_are_on(uv_project_with_remote):
    # CI found this the hard way. Every other test here pins the branch to
    # `main` for determinism, which means none of them can catch the tool
    # hardcoding it. This one renames the branch to something nobody would
    # default to, and is the only reason the pin above is safe.
    from release.setver import upstream_ref, version_report
    subprocess.run(("git", "branch", "-m", "trunk"), check=True, capture_output=True)
    subprocess.run(("git", "push", "-q", "-u", "origin", "trunk"),
                   check=True, capture_output=True)
    release("minor", message="cut")
    assert upstream_ref() == "origin/trunk"
    assert "r0.2.0 is not on origin/trunk" in version_report()


def test_a_project_with_no_remote_says_nothing_about_one(uv_project):
    # Plenty of projects are never pushed anywhere. They must not be nagged,
    # and the check must not fail on the missing upstream. Asserting on
    # upstream_ref directly, because a fabricated upstream also ends in
    # silence -- `merge-base` simply errors -- so the report alone cannot
    # tell the difference and the test would not be able to fail.
    from release.setver import version_report, upstream_ref, unpushed_release
    release("minor", message="cut")
    assert upstream_ref() is None        # nothing to compare against...
    assert unpushed_release() is None    # ...so nothing to report
    report = version_report()
    assert "is not on" not in report
    assert "released as r0.2.0" in report


def test_the_tools_own_output_is_not_overtaken_by_the_commands_it_runs(
        uv_project):
    # Python block-buffers stdout when it is a pipe rather than a terminal,
    # while the subprocesses write straight through, so the tool's messages
    # arrived *after* the output of commands they introduce. capsys cannot see
    # this -- it intercepts at the Python level, where the ordering is fine --
    # so the tool has to be run as a real process with a real pipe.
    result = subprocess.run(
        (sys.executable, "-m", "release", "-m", "cut", "minor"),
        capture_output=True, text=True, check=True,
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert "creating release" in lines[0], (
        f"the banner should come first, got: {lines}")
