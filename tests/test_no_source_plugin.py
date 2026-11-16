"""The example plugin that keeps `uv.sources` pins out of a release.

Loaded by path because `examples/plugins/` holds installable distributions
rather than importable packages -- nothing there is on `sys.path` when the
suite runs, which is the whole point of ADR-0007. Same trick as
test_verify_tag.py.
"""
import importlib.util
import pathlib
import subprocess

import pytest

import release
from release import CachedFile
from release.errors import PluginVeto
from release.setver import read_version

_path = (pathlib.Path(__file__).parent.parent / "examples" / "plugins"
         / "no-source" / "release_no_source" / "__init__.py")
_spec = importlib.util.spec_from_file_location("release_no_source", _path)
release_no_source = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_no_source)
no_uv_sources = release_no_source.no_uv_sources


def vet(tmp_path, content, name="pyproject.toml"):
    """Vet ``content`` written to ``name``, through a real CachedFile.

    The real object rather than a stub: the plugin's whole contract is the one
    `release` hands it, and a stub cannot show that `.path` carries a path
    whose *basename* is what matters.
    """
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return no_uv_sources(CachedFile(str(target)))


# --- what counts as an offence ------------------------------------------

def test_a_pyproject_with_no_sources_is_allowed(tmp_path):
    assert vet(tmp_path, '[project]\nname = "demo"\nversion = "0.1.0"\n') is None


def test_the_canonical_table_is_vetoed(tmp_path):
    message = vet(tmp_path, """
        [project]
        name = "demo"
        dependencies = ["demo-lib"]

        [tool.uv.sources]
        demo-lib = { path = "../demo-lib" }
    """)
    assert message is not None
    assert "tool.uv.sources.demo-lib" in message


def test_the_message_names_every_offending_entry(tmp_path):
    # "found something" is not a diagnosis: the user has to be able to go
    # straight to the lines to delete.
    message = vet(tmp_path, """
        [tool.uv.sources]
        demo-lib = { path = "../demo-lib" }
        other-lib = { git = "https://example.invalid/other-lib" }
        third-lib = { url = "https://example.invalid/third.whl" }
    """)
    assert "tool.uv.sources.demo-lib" in message
    assert "tool.uv.sources.other-lib" in message
    assert "tool.uv.sources.third-lib" in message


def test_a_sources_table_nested_anywhere_is_found(tmp_path):
    # "At any level": uv reads it at tool.uv.sources, but nothing stops a
    # document carrying it deeper, and a check that only looked at the
    # canonical place would give a clean bill of health to a file that still
    # pins a path.
    message = vet(tmp_path, """
        [tool.wrapper.environments.dev.uv.sources]
        demo-lib = { path = "../demo-lib" }
    """)
    assert message is not None
    assert "tool.wrapper.environments.dev.uv.sources.demo-lib" in message


def test_every_level_is_reported_not_just_the_first(tmp_path):
    message = vet(tmp_path, """
        [tool.uv.sources]
        demo-lib = { path = "../demo-lib" }

        [tool.wrapper.uv.sources]
        other-lib = { path = "../other-lib" }
    """)
    assert "tool.uv.sources.demo-lib" in message
    assert "tool.wrapper.uv.sources.other-lib" in message


def test_a_marker_dependent_list_of_sources_is_vetoed(tmp_path):
    # uv allows a list of sources per dependency, selected by marker. The
    # value is then an array of tables, not a table.
    message = vet(tmp_path, """
        [tool.uv.sources]
        demo-lib = [
            { path = "../demo-lib", marker = "sys_platform == 'darwin'" },
            { git = "https://example.invalid/demo-lib" },
        ]
    """)
    assert message is not None
    assert "tool.uv.sources.demo-lib" in message


# --- what must not be mistaken for one ----------------------------------

def test_a_uv_table_without_sources_is_allowed(tmp_path):
    assert vet(tmp_path, """
        [tool.uv]
        package = true
        default-groups = ["dev"]
    """) is None


def test_an_empty_sources_table_pins_nothing(tmp_path):
    assert vet(tmp_path, "[tool.uv.sources]\n") is None


def test_a_sources_key_that_is_not_a_table_is_allowed(tmp_path):
    # Whatever this means, it is not a pin -- and it must not raise, because a
    # plugin that raises aborts the release as a PluginError.
    assert vet(tmp_path, '[tool.uv]\nsources = "elsewhere"\n') is None


def test_a_sources_table_not_under_uv_is_allowed(tmp_path):
    assert vet(tmp_path, """
        [tool.somethingelse.sources]
        demo-lib = { path = "../demo-lib" }
    """) is None


# --- which files are looked at ------------------------------------------

def test_a_pyproject_toml_in_a_subdirectory_is_examined(tmp_path):
    # A vendored or nested project pins dependencies just as effectively, so
    # the test is on the basename, not on equality with "pyproject.toml".
    message = vet(tmp_path, '[tool.uv.sources]\ndemo-lib = { path = "." }\n',
                  name="vendor/demo/pyproject.toml")
    assert message is not None


def test_a_file_merely_named_like_one_is_ignored(tmp_path):
    assert vet(tmp_path, '[tool.uv.sources]\ndemo-lib = { path = "." }\n',
               name="pyproject.toml.bak") is None


def test_other_files_are_not_even_read(tmp_path):
    # The vet loop shows every file in the tree, binaries included. Reading
    # them would be waste at best and a PluginError at worst (CachedFile
    # raises on a file that is not text).
    class Explode:
        path = "assets/logo.png"
        def read_text(self):
            raise AssertionError("read a file that is not a pyproject.toml")

    assert no_uv_sources(Explode()) is None


def test_unparseable_toml_is_allowed_rather_than_raising(tmp_path):
    # Deliberate, and justified in the plugin: a file that is not TOML pins
    # nothing, the project's own manifest has already been parsed by
    # `uv version` before the vet loop runs, and the plausible nested
    # offender is a deliberately-malformed test fixture.
    assert vet(tmp_path, "[tool.uv.sources\ndemo-lib = oops\n") is None


# --- the real thing ------------------------------------------------------

class _FakeEntryPoint:
    def __init__(self, name, fn):
        self.name = name
        self._fn = fn

    def load(self):
        return self._fn


def _install(monkeypatch):
    """Register the real plugin as the only entry point in the group."""
    monkeypatch.setattr(
        "release.entry_points",
        lambda group: [_FakeEntryPoint("no-uv-sources", no_uv_sources)],
    )
    monkeypatch.setattr("release.RELEASE_NOCHECKS", False)


@pytest.mark.integration
def test_release_is_blocked_by_a_uv_sources_entry(uv_project, monkeypatch):
    pyproject = uv_project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text()
                         + '\n[tool.uv.sources]\ndemo-lib = { path = "../demo-lib" }\n')
    subprocess.run(("git", "commit", "-qam", "pin demo-lib"),
                   check=True, capture_output=True)
    _install(monkeypatch)

    with pytest.raises(PluginVeto) as exc:
        release.release("minor")
    assert exc.value.exit_code == 3                        # the veto code
    assert "pyproject.toml" in str(exc.value)
    assert "tool.uv.sources.demo-lib" in str(exc.value)    # which entry
    assert "no-uv-sources" in str(exc.value)               # which plugin
    assert read_version()[1] == "0.1.0"                    # not released


@pytest.mark.integration
def test_release_proceeds_without_one(uv_project, monkeypatch):
    # The other half of the evidence: the plugin installed and silent, so the
    # veto above is the entry and not the plugin's mere presence.
    _install(monkeypatch)
    release.release("minor")
    assert read_version()[1] == "0.2.0"
