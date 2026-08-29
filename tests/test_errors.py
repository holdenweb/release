"""The error boundary: how failures reach the user."""
import subprocess
import sys

import pytest

import release as rel
from release.errors import DirtyTree, GitError, PluginVeto, ReleaseError
from release.setver import git_is_dirty


def test_every_error_carries_an_exit_code():
    # The boundary maps exception -> exit status, so each must have one.
    for cls in (ReleaseError, GitError, DirtyTree, PluginVeto):
        assert isinstance(cls.exit_code, int)
    assert PluginVeto.exit_code == 3      # documented codes must not drift
    assert DirtyTree.exit_code == 4


@pytest.mark.integration
def test_git_failure_is_not_reported_as_a_dirty_tree(non_project_dir):
    # Regression: `git diff --quiet` exits non-zero both for "dirty" and for
    # "not a repository", and the old `!= 0` test announced the second as the
    # first -- telling the user to commit changes in a directory with no repo.
    with pytest.raises(GitError) as exc:
        git_is_dirty()
    assert "could not tell whether the working tree is clean" in str(exc.value)


@pytest.mark.integration
def test_cli_reports_the_error_on_stderr_with_its_exit_code(
    uv_project, monkeypatch, capsys
):
    (uv_project / "README.md").write_text("uncommitted\n")
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    monkeypatch.setattr(sys, "argv", ["release", "minor"])
    with pytest.raises(SystemExit) as exc:
        rel.main()
    assert exc.value.code == 4                     # the dirty-tree code survives
    captured = capsys.readouterr()
    assert "release: " in captured.err             # explained, and on stderr
    assert "uncommitted changes" in captured.err
    assert "release: " not in captured.out


@pytest.mark.integration
def test_v_next_cli_reports_errors_under_its_own_name(uv_project, monkeypatch, capsys):
    # Regression: v_next used to print a usage line naming *release*.
    monkeypatch.setattr(sys, "argv", ["v_next", "not-a-version"])
    with pytest.raises(SystemExit):
        rel.v_next_cli()
    assert "v_next:" in capsys.readouterr().err
