"""Tests for `release --snapshot` — transient, locally-versioned builds."""
import re
import subprocess
import sys

import pytest

from release import snapshot, main
from release.setver import snapshot_version, read_version

pytestmark = pytest.mark.integration


def test_snapshot_version_is_local_and_clean(uv_project):
    assert re.fullmatch(r"0\.1\.0\+g[0-9a-f]{8}", snapshot_version())


def test_snapshot_version_marks_a_dirty_tree(uv_project):
    (uv_project / "README.md").write_text("work in progress\n")
    assert re.fullmatch(r"0\.1\.0\+g[0-9a-f]{8}\.dirty", snapshot_version())


def test_snapshot_dry_run_emits_version_and_changes_nothing(uv_project, capsys):
    snapshot(dry_run=True)
    assert "0.1.0+g" in capsys.readouterr().out
    assert read_version()[1] == "0.1.0"          # pyproject untouched


def test_snapshot_builds_a_wheel_and_restores_pyproject(uv_project):
    (uv_project / "README.md").write_text("work in progress\n")
    sha = subprocess.run(
        ("git", "rev-parse", "--short=8", "HEAD"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    snapshot()

    wheels = list((uv_project / "dist").glob("*.whl"))
    assert wheels, "expected a wheel in dist/"
    assert any(f"g{sha}" in w.name for w in wheels)   # built with the local version
    assert read_version()[1] == "0.1.0"               # pyproject restored


def test_cli_snapshot_rejects_a_bump_argument(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["release", "--snapshot", "minor"])
    with pytest.raises(SystemExit):
        main()
