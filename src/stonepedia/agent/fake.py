"""Deterministic stand-in for the proposing agent, used in tests and offline UI work.

- propose: turns the source text into one new Guidance Article under `notes/`.
- revise: appends the feedback to each target Article.
- feedback: appends the feedback to every pending Article; "DELETE" withdraws them instead.
"""

import re
from pathlib import Path

from stonepedia import frontmatter
from stonepedia.models import AgentJob


def _slug(title: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or fallback


def run(workspace: Path, job: AgentJob) -> str:
    if job.mode == "propose":
        path = workspace / "notes" / f"{_slug(job.title, job.proposal_id)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        first = job.text.strip().splitlines()[0][:200] if job.text.strip() else job.title
        meta = {"type": "Guidance", "title": job.title, "description": first, "tags": ["fake-agent"]}
        path.write_text(frontmatter.join(meta, f"\n# {job.title}\n\n{job.text.strip()}\n"))
        return f"Created {path.relative_to(workspace)}."
    targets = job.targets if job.mode == "revise" else [c.path for c in job.carried if c.path not in job.locked]
    for rel in targets:
        path = workspace / rel
        if job.mode == "feedback" and job.feedback.strip() == "DELETE":
            path.unlink(missing_ok=True)
            continue
        path.write_text(path.read_text().rstrip("\n") + f"\n\nRevision: {job.feedback.strip()}\n")
    return f"{job.mode}: {', '.join(targets)}"
