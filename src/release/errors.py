"""Exceptions raised by the release tool.

Library code raises these rather than calling ``sys.exit``, so that callers can
handle a failure, tests can assert on it, and every message reaches the user
with an explanation attached. The CLI entry points are the only place that
converts them into a message on stderr and a process exit code.

``exit_code`` preserves the codes the tool already promised: 3 for a plugin
veto and 4 for a dirty working tree.
"""


class ReleaseError(Exception):
    """Base for every failure the tool reports to the user."""
    exit_code = 1


class UsageError(ReleaseError):
    """The arguments given are not a form that can be turned into a command."""


class UvError(ReleaseError):
    """uv refused the command, or answered in a shape we cannot read."""


class VersionOrderError(ReleaseError):
    """The requested version would move the project backwards."""


class NotAProjectError(ReleaseError):
    """The working directory is not a uv project we can read a version from."""


class MissingTool(ReleaseError):
    """A required external command (uv or git) is not on PATH."""


class GitError(ReleaseError):
    """A git command failed, or its result could not be trusted."""


class StepFailed(ReleaseError):
    """A step of a multi-step operation failed, possibly part-way through.

    ``consequence`` says what state the tree was left in, so the message can
    never claim a release was "aborted" when it had in fact already landed.
    """

    def __init__(self, what, consequence):
        super().__init__(f"{what} failed; {consequence}")
        self.what = what
        self.consequence = consequence


class PluginError(ReleaseError):
    """A plugin could not be loaded, or raised while vetting a file."""


class PluginVeto(ReleaseError):
    """One or more plugins refused the release."""
    exit_code = 3


class DirtyTree(ReleaseError):
    """The working tree has uncommitted changes and no override was given."""
    exit_code = 4
