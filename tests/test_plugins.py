"""Tests for entry-point plugin discovery and the vetting loop."""
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
