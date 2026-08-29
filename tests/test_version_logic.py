"""Integration tests for version reading/prediction against a real uv project.

Each test runs inside the ``uv_project`` fixture (CWD is a fresh temp project
whose starting version is 0.1.0), so they exercise the genuine uv interface.
"""
import sys

import pytest

from release import setver
from release.errors import (
    NotAProjectError,
    UsageError,
    UvError,
    VersionOrderError,
)
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


def test_read_version_outside_project_raises(non_project_dir):
    # Regression: this once raised a bare AssertionError traceback (see the
    # ISSUES file). It is now a typed error a library caller can catch, and it
    # relays uv's own explanation rather than asserting a cause.
    with pytest.raises(NotAProjectError) as exc:
        read_version()
    assert "could not read the project version" in str(exc.value)


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


def test_v_next_refuses_a_downgrade(uv_project):
    update_project_version("1.0.0")            # move the current version forward
    # A downgrade is a policy refusal, not "not a valid form", so it must
    # propagate rather than being flattened into v_next's None.
    with pytest.raises(VersionOrderError) as exc:
        v_next("0.9.0")                         # ...then try to go backwards
    assert "backwards" in str(exc.value)


def test_v_next_allows_finalising_a_prerelease(uv_project):
    update_project_version("1.0.0rc1")
    # 1.0.0 is *newer* than 1.0.0rc1 (final > pre-release), so not a downgrade.
    assert v_next("1.0.0") == "1.0.0"


def test_downgrade_is_allowed_under_release_nochecks(uv_project, monkeypatch):
    monkeypatch.setattr("release.setver.RELEASE_NOCHECKS", True)
    update_project_version("1.0.0")
    assert v_next("0.9.0") == "0.9.0"


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


def test_update_with_bad_argument_raises(uv_project):
    with pytest.raises(UvError):
        update_project_version("not-a-version")
    assert read_version()[1] == "0.1.0"  # nothing written


def test_update_dry_run_leaves_version_unchanged(uv_project):
    _, predicted = update_project_version("minor", dry_run=True)
    assert predicted == "0.2.0"
    assert read_version()[1] == "0.1.0"


def test_v_next_outside_a_project_raises_rather_than_returning_none(non_project_dir):
    # Regression: uv fails identically for "not a version" and "no project
    # here", so an environment failure was reported as a bad argument and then
    # flattened into v_next's None -- the caller was told "that isn't a valid
    # bump" when the real problem was that there was no project at all.
    with pytest.raises(NotAProjectError):
        v_next("patch")
