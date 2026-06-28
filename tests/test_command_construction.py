"""Unit tests for the argument -> `uv version` command mapping.

``subprocess.run`` is faked so these run fast and assert exactly which command
``update_project_version`` builds for each shape of input, without depending on
a real uv install or its output format.
"""
import pytest

from release import setver


class _FakeResult:
    def __init__(self, stdout):
        self.returncode = 0
        self.stdout = stdout.encode("utf-8")
        self.stderr = b""

    def check_returncode(self):
        pass


@pytest.fixture
def record_run(monkeypatch):
    """Patch setver.subprocess.run to record commands and return fixed output."""
    calls = []

    def fake_run(cmd, capture_output=False, **kwargs):
        calls.append(list(cmd))
        return _FakeResult("demo 0.1.0 => 0.2.0")

    monkeypatch.setattr(setver.subprocess, "run", fake_run)
    return calls


def test_single_bump_uses_bump_flag(record_run):
    setver.update_project_version("patch")
    assert record_run[-1] == ["uv", "version", "--bump", "patch"]


def test_bump_chain_repeats_the_flag(record_run):
    setver.update_project_version("patch", "alpha")
    assert record_run[-1] == ["uv", "version", "--bump", "patch", "--bump", "alpha"]


def test_explicit_version_is_passed_positionally(record_run):
    # Regression: explicit versions used to be rejected outright. The arg is
    # handed straight to `uv version <ver>`, which validates/normalises it.
    setver.update_project_version("1.2.3")
    assert record_run == [["uv", "version", "1.2.3"]]


def test_dry_run_adds_the_flag(record_run):
    setver.update_project_version("patch", dry_run=True)
    assert record_run[-1] == ["uv", "version", "--dry-run", "--bump", "patch"]


def test_unknown_argument_exits(monkeypatch):
    # A single non-bump arg that uv won't accept as a version: bail with a
    # usage error rather than mutating the project.
    def fake_run(cmd, capture_output=False, **kwargs):
        result = _FakeResult("")
        result.returncode = 2
        return result

    monkeypatch.setattr(setver.subprocess, "run", fake_run)
    with pytest.raises(SystemExit):
        setver.update_project_version("not-a-version")
