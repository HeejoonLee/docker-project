"""The proposing agent: `claude -p` in production, a deterministic fake in tests."""

# Where the agent finds its task inputs inside the workspace. Never committed.
TASK_DIR = ".stonepedia/task"


class AgentError(RuntimeError):
    """The agent ran but failed (worth retrying)."""


class AgentConfigError(RuntimeError):
    """The agent cannot run as configured (retrying won't help)."""
