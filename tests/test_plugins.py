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


# --- the dry run previews a veto -----------------------------------------
#
# A plugin veto is the one refusal the user can act on by editing a file, and
# for a long time it was the one refusal `--dry-run` could not show: the dry
# run returned before the vet loop was reached, so `release -n` reported a
# clean preview of a release that would then be refused.


def _vetoing(monkeypatch, *paths):
    """Install a plugin that refuses exactly ``paths``."""
    def veto(cached):
        return "refused for the test" if cached.path in paths else None

    monkeypatch.setattr(
        "release.entry_points",
        lambda group: [_FakeEntryPoint("no-those", veto)],
    )
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)


@pytest.mark.integration
def test_dry_run_reports_a_plugin_veto(uv_project, monkeypatch, capsys):
    _vetoing(monkeypatch, "README.md")
    release.release("minor", dry_run=True)
    out = capsys.readouterr().out
    assert "README.md" in out                 # which file
    assert "no-those" in out                  # which plugin refused it
    assert "0.2.0" in out                     # ...alongside the usual preview
    assert read_version()[1] == "0.1.0"       # and still a dry run


@pytest.mark.integration
def test_dry_run_reports_every_vetoed_file(uv_project, monkeypatch, capsys):
    # Not just the first: the point of previewing is to fix them in one pass.
    _vetoing(monkeypatch, "README.md", "pyproject.toml")
    release.release("minor", dry_run=True)
    out = capsys.readouterr().out
    assert "README.md" in out
    assert "pyproject.toml:" in out           # colon: the veto line, not the lock step


@pytest.mark.integration
def test_dry_run_of_a_clean_tree_reports_no_veto(uv_project, monkeypatch, capsys):
    # The complement: a plugin that allows everything must not make the dry run
    # print a warning, or the preview cries wolf on every release.
    _vetoing(monkeypatch)                     # refuses nothing
    release.release("minor", dry_run=True)
    assert "refused" not in capsys.readouterr().out


@pytest.mark.integration
def test_dry_run_surfaces_a_plugin_that_raises(uv_project, monkeypatch):
    # A plugin that raises is a broken release rather than a veto, and the dry
    # run is where that should surface -- before anything is committed.
    def explode(cached):
        raise RuntimeError("plugin is broken")

    monkeypatch.setattr(
        "release.entry_points",
        lambda group: [_FakeEntryPoint("broken", explode)],
    )
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)
    with pytest.raises(PluginError) as exc:
        release.release("minor", dry_run=True)
    assert "broken" in str(exc.value)
    assert read_version()[1] == "0.1.0"


@pytest.mark.integration
def test_no_plugins_means_no_walk(uv_project, monkeypatch, capsys):
    # The dry run vets, so with no plugins installed -- the default, since none
    # ship enabled -- it would otherwise walk the whole tree to show every file
    # to nobody.
    monkeypatch.setattr("release.entry_points", lambda group: [])
    monkeypatch.setattr(
        "release.project_files",
        lambda root=".": pytest.fail("walked the tree with no plugins loaded"),
    )
    release.release("minor", dry_run=True)
    assert "0.2.0" in capsys.readouterr().out
