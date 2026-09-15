"""Refuse a tag that does not name exactly what the tree it points at holds.

Run by the `verify-tag` job before anything is built or published. The tool
itself already refuses to mint a bad tag, but a tag can be made by hand, and
by the time CI sees one there is nothing left to consult but the tag and the
tree it points at.
"""
import os
import sys
import tomllib

from packaging.version import InvalidVersion, Version


def verify_tag(tag: str, declared: str, prefix: str = "r") -> Version:
    """Return the version ``tag`` names, or raise ValueError saying why not."""
    if not tag.startswith(prefix):
        raise ValueError(f"tag {tag!r} does not start with {prefix!r}")
    named = tag[len(prefix):]
    # String equality, not PEP 440 equivalence. Version("01.8.2") compares
    # equal to Version("1.8.2"), so an equivalence test would happily accept a
    # Release titled r01.8.2 whose wheels all read 1.8.2.
    if named != declared:
        raise ValueError(
            f"tag {tag} names {named!r}, but pyproject.toml at that commit "
            f"declares {declared!r}"
        )
    try:
        version = Version(declared)
    except InvalidVersion as exc:
        raise ValueError(f"{declared!r} is not a PEP 440 version: {exc}") from exc
    # Defence in depth behind ADR-0009, which is what should stop this upstream:
    # git accepts refs/tags/r1.8.2+dev perfectly happily, and one was created by
    # accident in this repository before the guard existed.
    if version.is_devrelease or version.local is not None:
        raise ValueError(
            f"{declared} is a development version, not a release: it marks its "
            f"commit as unreleased and must never have been tagged"
        )
    return version


def main() -> None:
    with open("pyproject.toml", "rb") as f:
        declared = tomllib.load(f)["project"]["version"]
    try:
        version = verify_tag(
            os.environ["TAG"], declared, os.environ.get("TAG_PREFIX", "r")
        )
    except ValueError as exc:
        sys.exit(f"verify-tag: {exc}")

    print(f"{os.environ['TAG']} correctly names {version}"
          + (" (a pre-release)" if version.is_prerelease else ""))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"version={version}\n")
            # Pre-releases are genuine releases and are tagged (ADR-0009), so
            # they get a Release -- marked as one, so nothing treats an rc as
            # the current version. Publication to an index is a separate
            # question, and the answer there is no (ADR-0020).
            f.write(f"prerelease={str(version.is_prerelease).lower()}\n")


if __name__ == "__main__":
    main()
