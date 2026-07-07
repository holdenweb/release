# Example release plugins

A **plugin** for [`release`](../../README.md) is a callable that vets a single
file and either returns a message (to veto the release) or `None` (to allow it):

```python
def no_debug_file(cached_file):
    if cached_file.path.endswith("/wingdbstub.py"):
        return "is a Wing debugger stub"
```

`cached_file` exposes `.path` and `.read_text()`. Before cutting a release,
`release` runs every plugin against every file in the tree; if any returns a
message, the release is refused (exit code 3).

Plugins are discovered through the `release.plugins`
[entry-point group](https://packaging.python.org/en/latest/specifications/entry-points/),
so a plugin must be **installed into the same environment as `release`** — nothing
loads automatically.

## What's here

`release_wing_plugins` blocks [Wing IDE](https://wingware.com/) debugger stubs —
`wingdbstub.py` files, and `.py`/`.pyw` files that still `import wingdbstub` —
from being released. It is **specific to Wing**; treat it as a template.

## Enabling it

Install the plugin package alongside the `release` tool so its entry points are
visible to it:

```bash
uv tool install release --with /path/to/release/examples/plugins
```

`release` will then print `Plugins: no-wingdbstub-file, no-wingdbstub-import` on
each run and refuse to release a tree that still contains Wing debugger stubs.

## Writing your own

Copy this directory, rewrite the `vet` functions, and update the
`[project.entry-points."release.plugins"]` table in `pyproject.toml` to point at
them. Then install it the same way.
