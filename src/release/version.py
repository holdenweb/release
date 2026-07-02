"""The installed version of the ``release`` distribution.

Read from package metadata so it always reflects the built/installed version
rather than a hand-maintained literal that can drift from pyproject.toml.
"""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("release")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0+unknown"
