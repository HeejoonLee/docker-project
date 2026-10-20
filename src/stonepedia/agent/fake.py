"""Deterministic stand-in for the proposing agent, used in tests and offline UI work.

It turns the task text into one new Guidance Article under `notes/`.
"""

import re
from pathlib import Path

from stonepedia import frontmatter
from stonepedia.models import AgentTask


def _slug(title: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or fallback


def run(workspace: Path, task: AgentTask) -> None:
    path = workspace / "notes" / f"{_slug(task.title, task.proposal_id)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "type": "Guidance",
        "title": task.title,
        "description": task.text.strip().splitlines()[0][:200] if task.text.strip() else task.title,
        "tags": ["fake-agent"],
    }
    path.write_text(frontmatter.join(meta, f"\n# {task.title}\n\n{task.text.strip()}\n"))
