"""Unit tests for ``CachedFile`` — pure, no subprocess involved.

These pin the caching contract that the plugin-vetting loop relies on: a file
read more than once (by different plugins) must keep returning its content.
"""
from release import CachedFile


def test_read_text_returns_file_contents(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("hello world")
    assert CachedFile(str(p)).read_text() == "hello world"


def test_repeated_reads_return_content_not_none(tmp_path):
    # Regression: the cache-hit branch used to return None on the 2nd read,
    # so a file vetted by two plugins came back empty for the second one.
    p = tmp_path / "f.txt"
    p.write_text("first")
    cf = CachedFile(str(p))
    assert cf.read_text() == "first"
    assert cf.read_text() == "first"  # 2nd read must still be the content
    assert cf.read_text() == "first"  # ...and the 3rd


def test_content_is_cached_from_first_read(tmp_path):
    # Once read, later edits on disk must not change what the cache returns.
    p = tmp_path / "f.txt"
    p.write_text("original")
    cf = CachedFile(str(p))
    assert cf.read_text() == "original"
    p.write_text("changed on disk")
    assert cf.read_text() == "original"
