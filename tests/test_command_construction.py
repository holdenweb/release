"""Unit tests for the argument -> `uv version` command mapping.

``subprocess.run`` is faked so these run fast and assert exactly which command
``update_project_version`` builds for each shape of input, without depending on
a real uv install or its output format.
"""
import pytest

from release import setver
from release.errors import UsageError, UvError


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


def test_unknown_argument_raises_with_uvs_reason(monkeypatch):
    # A single non-bump arg that uv won't accept as a version. The old code
    # replaced uv's explanation with a bare usage line; now uv's own words are
    # relayed, because they say what is actually wrong.
    def fake_run(cmd, capture_output=False, **kwargs):
        # A plain `uv version` is read_version()'s probe, asking "is there a
        # project here at all?" -- it must succeed, so the failure below is
        # attributed to the argument and not to the environment.
        if list(cmd) == ["uv", "version"]:
            return _FakeResult("demo 0.1.0")
        result = _FakeResult("")
        result.returncode = 2
        result.stderr = b"error: expected version to start with a number"
        return result

    monkeypatch.setattr(setver.subprocess, "run", fake_run)
    with pytest.raises(UvError) as exc:
        setver.update_project_version("not-a-version")
    assert "not-a-version" in str(exc.value)
    assert "expected version to start with a number" in str(exc.value)


def test_mixed_form_names_the_offending_token():
    # A version number combined with a bump name: the message must name the
    # stray token rather than printing a generic usage line.
    with pytest.raises(UsageError) as exc:
        setver._version_command(("2.5.0", "alpha"), dry_run=False)
    assert "'2.5.0'" in str(exc.value)


def test_no_arguments_raises():
    with pytest.raises(UsageError):
        setver._version_command((), dry_run=False)
