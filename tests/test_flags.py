"""How environment-variable flags are interpreted."""
import os
import subprocess
import sys

import pytest

from release.setver import flag_is_set


@pytest.mark.parametrize("value", ["", "0", "false", "False", "FALSE", "no", "off", "  ", " 0 "])
def test_off_values_leave_the_checks_on(value):
    # Regression: every non-empty value used to mean "skip the checks", so
    # RELEASE_NOCHECKS=0 -- which almost everyone means as *off* -- silently
    # disabled the dirty-tree guard and the plugin veto.
    assert flag_is_set(value) is False


@pytest.mark.parametrize("value", ["1", "yes", "on", "true", "please"])
def test_anything_else_turns_the_checks_off(value):
    assert flag_is_set(value) is True


def _release_cli(env_extra):
    """Run the real `python -m release patch` in a subprocess.

    A subprocess, not an in-process call, because RELEASE_NOCHECKS is read at
    import time -- only a fresh interpreter exercises the real path from
    environment variable to behaviour.
    """
    return subprocess.run(
        [sys.executable, "-m", "release", "-m", "release commit", "patch"],
        capture_output=True, text=True, env=dict(os.environ, **env_extra),
    )


@pytest.mark.integration
def test_nochecks_off_still_refuses_a_dirty_tree(uv_project):
    (uv_project / "README.md").write_text("uncommitted\n")
    result = _release_cli({"RELEASE_NOCHECKS": "0"})
    assert result.returncode == 4              # the dirty-tree refusal stands
    assert "uncommitted changes" in result.stderr


@pytest.mark.integration
def test_nochecks_on_overrides_the_dirty_tree(uv_project):
    (uv_project / "README.md").write_text("uncommitted\n")
    result = _release_cli({"RELEASE_NOCHECKS": "1"})
    assert result.returncode == 0, result.stderr
