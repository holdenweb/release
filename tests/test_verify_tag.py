"""The CI guard that checks a tag against the tree it points at.

Loaded by path because the module lives where GitHub Actions expects it rather
than on the import path.
"""
import importlib.util
import pathlib

import pytest

_path = pathlib.Path(__file__).parent.parent / ".github" / "scripts" / "verify_tag.py"
_spec = importlib.util.spec_from_file_location("verify_tag", _path)
verify_tag_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_tag_mod)
verify_tag = verify_tag_mod.verify_tag


def test_a_tag_naming_its_own_version_passes():
    assert str(verify_tag("r1.8.2", "1.8.2")) == "1.8.2"


def test_a_pre_release_passes_and_is_reported_as_one():
    # ADR-0009 treats rc/alpha/beta as genuine releases, so they are tagged.
    assert verify_tag("r1.9.0rc1", "1.9.0rc1").is_prerelease


def test_a_final_release_is_not_reported_as_a_pre_release():
    assert not verify_tag("r1.8.2", "1.8.2").is_prerelease


def test_a_tag_that_disagrees_with_the_tree_is_refused():
    # The shape a stale or hand-made tag takes: the tag says one thing and the
    # committed pyproject.toml says another.
    with pytest.raises(ValueError, match="declares"):
        verify_tag("r1.8.2", "1.8.2+dev")


def test_equivalent_is_not_good_enough_it_must_be_identical():
    # Version("01.8.2") == Version("1.8.2"), so a PEP 440 equivalence test
    # passes this and leaves a Release titled r01.8.2 full of 1.8.2 wheels.
    with pytest.raises(ValueError, match="names"):
        verify_tag("r01.8.2", "1.8.2")


def test_a_development_version_is_refused_even_if_the_tag_matches():
    # Defence in depth: git accepts refs/tags/r1.8.2+dev, and one was made by
    # accident here before ADR-0009's guard covered local segments.
    with pytest.raises(ValueError, match="development version"):
        verify_tag("r1.8.2+dev", "1.8.2+dev")


def test_a_dev_release_is_refused_too():
    with pytest.raises(ValueError, match="development version"):
        verify_tag("r1.8.2.dev1", "1.8.2.dev1")


def test_a_tag_without_the_prefix_is_refused():
    with pytest.raises(ValueError, match="does not start with"):
        verify_tag("v1.8.2", "1.8.2")


def test_the_prefix_is_configurable():
    assert str(verify_tag("v1.8.2", "1.8.2", prefix="v")) == "1.8.2"


def test_something_that_is_not_a_version_is_refused():
    with pytest.raises(ValueError, match="not a PEP 440 version"):
        verify_tag("rwhat", "what")
