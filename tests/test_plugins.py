"""Tests for entry-point plugin discovery and the vetting loop."""
import os
import subprocess

import pytest

import release
from release.setver import read_version
from release.errors import PluginError, PluginVeto


class _FakeEntryPoint:
    def __init__(self, name, fn):
        self.name = name
        self._fn = fn

    def load(self):
        return self._fn


def test_load_plugins_returns_entry_point_callables(monkeypatch):
    def veto(cached):
        return "nope"

    monkeypatch.setattr(
        "release.entry_points",
        lambda group: [_FakeEntryPoint("demo", veto)] if group == "release.plugins" else [],
    )
    plugins = release.load_plugins()
    assert len(plugins) == 1
    name, vet = plugins[0]          # (entry-point name, vet callable) pairs
    assert name == "demo"
    assert vet(object()) == "nope"


def test_load_plugins_is_empty_by_default(monkeypatch):
    monkeypatch.setattr("release.entry_points", lambda group: [])
    assert release.load_plugins() == []


@pytest.mark.integration
def test_release_is_blocked_by_a_vetoing_plugin(uv_project, monkeypatch):
    def veto_readme(cached):
        return "blocked" if cached.path.endswith("README.md") else None

    monkeypatch.setattr("release.entry_points", lambda group: [_FakeEntryPoint("no-readme", veto_readme)])
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    with pytest.raises(PluginVeto) as exc:
        release.release("minor")
    assert exc.value.exit_code == 3              # the documented veto code
    assert "README.md" in str(exc.value)         # says WHICH file was refused
    assert "no-readme" in str(exc.value)         # ...and which plugin refused it
    assert read_version()[1] == "0.1.0"          # not released


@pytest.mark.integration
def test_vet_loop_skips_directories(uv_project, monkeypatch):
    # A plugin that reads *every* path must not choke on directories (src/ etc.);
    # the loop only feeds it real files.
    def read_everything(cached):
        cached.read_text()
        return None

    monkeypatch.setattr("release.entry_points", lambda group: [_FakeEntryPoint("reader", read_everything)])
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    release.release("minor")
    assert read_version()[1] == "0.2.0"          # completed and released


# --- which files the vet loop actually sees ------------------------------

def _seen_paths(uv_project, monkeypatch):
    """Run a release with a plugin that records every path it is shown."""
    seen = []

    def recorder(cached):
        seen.append(cached.path)
        return None

    monkeypatch.setattr(
        "release.entry_points",
        lambda group: [_FakeEntryPoint("recorder", recorder)],
    )
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    release.release("minor")
    return seen


@pytest.mark.integration
def test_hidden_files_are_vetted(uv_project, monkeypatch):
    # Regression: glob("**/*") skipped every dotfile, so a plugin looking for
    # stray secrets or debugger stubs gave a false all-clear on exactly the
    # files most likely to hold them.
    (uv_project / ".env").write_text("SECRET=test-value\n")
    (uv_project / ".github" / "workflows").mkdir(parents=True)
    (uv_project / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    subprocess.run(("git", "add", "-A"), check=True, capture_output=True)
    subprocess.run(("git", "commit", "-qm", "add hidden files"),
                   check=True, capture_output=True)

    seen = _seen_paths(uv_project, monkeypatch)
    assert ".env" in seen
    assert os.path.join(".github", "workflows", "ci.yml") in seen


@pytest.mark.integration
def test_vcs_and_cache_directories_are_not_walked(uv_project, monkeypatch):
    # Including hidden files must not mean crawling .git (or a virtualenv, or
    # __pycache__): they hold thousands of files, many of them binary.
    (uv_project / "__pycache__").mkdir()
    (uv_project / "__pycache__" / "x.pyc").write_bytes(b"\x00\x01binary")
    (uv_project / ".venv").mkdir()
    (uv_project / ".venv" / "pyvenv.cfg").write_text("home = /usr\n")

    seen = _seen_paths(uv_project, monkeypatch)
    assert not [p for p in seen if p.startswith(".git" + os.sep)]
    assert not [p for p in seen if p.startswith("__pycache__")]
    assert not [p for p in seen if p.startswith(".venv")]
    assert "pyproject.toml" in seen          # ...but real files are still seen


@pytest.mark.integration
def test_a_hidden_file_can_veto_the_release(uv_project, monkeypatch):
    (uv_project / ".env").write_text("SECRET=test-value\n")

    def no_env(cached):
        return "looks like a secrets file" if cached.path == ".env" else None

    monkeypatch.setattr(
        "release.entry_points",
        lambda group: [_FakeEntryPoint("no-env", no_env)],
    )
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    with pytest.raises(PluginVeto) as exc:
        release.release("minor")
    assert ".env" in str(exc.value)
    assert read_version()[1] == "0.1.0"      # not released
