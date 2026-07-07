"""Example ``release`` plugins: keep Wing IDE debugger stubs out of a release.

A plugin is a *vet* callable. Given a file -- an object with ``.path`` and
``.read_text()`` -- it returns a message to veto the release, or ``None`` to
allow it. These functions are registered under the ``release.plugins``
entry-point group in this package's pyproject.toml.

They are specific to `Wing IDE <https://wingware.com/>`_; copy this directory
and adapt them for your own environment.
"""

def no_debug_file(cached_file):
    """Veto a bare ``wingdbstub.py`` debugger stub anywhere in the tree."""
    if cached_file.path == "wingdbstub.py" or cached_file.path.endswith("/wingdbstub.py"):
        return "is a Wing debugger stub"


_GUILTY = "import" + " wingdbstub"


def no_debug_import(cached_file):
    """Veto any .py/.pyw file that still imports the Wing debugger."""
    if cached_file.path.endswith((".py", ".pyw")) and _GUILTY in cached_file.read_text():
        return "still imports the Wing debugger (wingdbstub)"
