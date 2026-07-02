"""The tool reports its own version from installed distribution metadata."""
from importlib.metadata import version

from release import __version__


def test_dunder_version_comes_from_metadata():
    # Guards against reintroducing a hand-maintained literal that drifts from
    # pyproject.toml: __version__ must equal the installed distribution version.
    assert __version__ == version("release")
