"""Integration tests for version reading/prediction against a real uv project.

Each test runs inside the ``uv_project`` fixture (CWD is a fresh temp project
whose starting version is 0.1.0), so they exercise the genuine uv interface.
"""
import sys

import pytest

from release import setver
from release.setver import (
    read_version,
    update_project_version,
    v_next,
    v_next_cli,
)

pytestmark = pytest.mark.integration


# --- read_version -------------------------------------------------------

def test_read_version_returns_name_and_version(uv_project):
    name, version = read_version()
    assert name == "demo-proj"
    assert version == "0.1.0"


def test_read_version_outside_project_exits_cleanly(non_project_dir):
    # Regression: this used to raise a bare AssertionError traceback (see the
    # ISSUES file). It must now be a friendly SystemExit, not AssertionError.
    with pytest.raises(SystemExit) as exc:
        read_version()
    assert not isinstance(exc.value, AssertionError)
    assert "release:" in str(exc.value)


# --- v_next (prediction, never mutates) ---------------------------------

def test_v_next_predicts_a_bump(uv_project):
    assert v_next("patch") == "0.1.1"
    assert v_next("minor") == "0.2.0"
    assert v_next("major") == "1.0.0"


def test_v_next_normalises_an_explicit_version(uv_project):
    assert v_next("2.5.0") == "2.5.0"


def test_v_next_predicts_a_bump_chain(uv_project):
    # v_next must accept the same multi-bump form as `release` and predict the
    # version that chain would produce (minor zeroes the patch, then alpha).
    assert v_next("minor", "alpha") == "0.2.0a1"


def test_v_next_rejects_a_version_plus_bump_mix(uv_project):
    # The same invalid form `release` rejects -- a version and a bump together.
    assert v_next("2.5.0", "alpha") is None


def test_v_next_returns_none_for_garbage(uv_project):
    assert v_next("definitely-not-a-version") is None


def test_v_next_does_not_change_the_project_version(uv_project):
    v_next("major")
    # Prediction is a dry run: the real version must be untouched.
    assert read_version()[1] == "0.1.0"


def test_v_next_cli_prints_the_prediction(uv_project, monkeypatch, capsys):
    # Regression: the CLI used to print "None" for every input.
    monkeypatch.setattr(sys, "argv", ["v_next", "patch"])
    v_next_cli()
    assert capsys.readouterr().out.strip() == "0.1.1"


def test_v_next_cli_accepts_multiple_bumps(uv_project, monkeypatch, capsys):
    # Regression: the CLI used to reject anything but exactly one argument.
    monkeypatch.setattr(sys, "argv", ["v_next", "minor", "alpha"])
    v_next_cli()
    assert capsys.readouterr().out.strip() == "0.2.0a1"


# --- update_project_version (actually writes) ---------------------------

def test_update_with_explicit_version_sets_it(uv_project):
    # Regression: `release 1.2.3` used to fail with "Usage:".
    name, new = update_project_version("0.4.2")
    assert (name, new) == ("demo-proj", "0.4.2")
    assert read_version()[1] == "0.4.2"


def test_update_with_bump_chain(uv_project):
    _, new = update_project_version("patch", "alpha")
    assert new == "0.1.1a1"
    assert read_version()[1] == "0.1.1a1"


def test_update_with_bad_argument_exits(uv_project):
    with pytest.raises(SystemExit):
        update_project_version("not-a-version")
    assert read_version()[1] == "0.1.0"  # nothing written


def test_update_dry_run_leaves_version_unchanged(uv_project):
    _, predicted = update_project_version("minor", dry_run=True)
    assert predicted == "0.2.0"
    assert read_version()[1] == "0.1.0"
