"""Example ``release`` plugin: no ``uv.sources`` pins in a release.

A plugin is a *vet* callable. Given a file -- an object with ``.path`` and
``.read_text()`` -- it returns a message to veto the release, or ``None`` to
allow it. This one is registered under the ``release.plugins`` entry-point
group in this package's pyproject.toml.

A ``uv.sources`` entry resolves a dependency from a local path, a git ref or a
URL instead of an index. That is exactly right while developing against an
unreleased sibling, and fatal in a release: the published artefact's metadata
names a dependency nobody else can resolve, so the first person to install it
discovers the pin for us.
"""
import os
import tomllib


def _uv_sources(table, trail=()):
    """Yield ``(dotted table name, dependency)`` for every uv.sources entry.

    Recursive, rather than a lookup of ``tool.uv.sources``. That is the only
    place uv itself reads, but it is not the only place the table can be
    written -- a workspace root, a generated fragment, or a tool that wraps uv
    config under its own key -- and a check that trusted the canonical
    location would hand a clean bill of health to a file that still pins a
    path. Recursion costs one pass over a document already in memory.

    ``trail`` accumulates the enclosing keys so the message can name the
    offending entry by its full dotted key, which is what makes it findable in
    the file rather than merely alarming.
    """
    for key, value in table.items():
        if not isinstance(value, dict):          # scalars and arrays: nothing nests
            continue
        if key == "uv" and isinstance(value.get("sources"), dict):
            where = ".".join((*trail, key, "sources"))
            # Iterating the table yields the dependency names; the values are
            # each a source table, or an array of them when uv selects between
            # sources by marker. Which kind it is does not change the verdict.
            for dependency in value["sources"]:
                yield where, dependency
        yield from _uv_sources(value, (*trail, key))


def no_uv_sources(cached_file):
    """Veto a pyproject.toml that resolves a dependency through uv.sources."""
    # The basename, not equality with "pyproject.toml": the vet loop is shown
    # every file in the tree, so a vendored or nested project's manifest pins
    # dependencies just as effectively and must be read -- while a
    # pyproject.toml.bak must not be. Checked before reading, because the loop
    # also offers binaries, and CachedFile raises on a file that is not text.
    if os.path.basename(cached_file.path) != "pyproject.toml":
        return
    try:
        document = tomllib.loads(cached_file.read_text())
    except tomllib.TOMLDecodeError:
        # Allowed, deliberately, and not raised: a plugin that raises becomes a
        # PluginError and aborts the release, which is far too harsh a response
        # to a file this plugin has nothing to say about. The project's own
        # manifest cannot reach here broken -- `uv version` parses it before the
        # vet loop runs, and fails with a better message -- so what arrives
        # malformed is some other file of that name, most often a fixture that
        # is deliberately invalid TOML. Whatever it is, it is not a resolvable
        # pin, which is the only thing being asserted here.
        return
    pinned = list(_uv_sources(document))
    if pinned:
        entries = ", ".join(f"{where}.{dep}" for where, dep in pinned)
        return (f"pins {entries} to a dependency source that nothing outside "
                f"this checkout can resolve")
