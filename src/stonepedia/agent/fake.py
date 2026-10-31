"""Deterministic stand-in for the proposing agent, used in tests and offline UI work.

- propose: turns the Sources' and the Request's text.md into one new Guidance Article under `notes/`,
  citing all of them (a Request aimed at Articles appends to those instead; "RETIRE..." deletes them).
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
        items = job.sources + ([job.request] if job.request else [])
        texts = [(workspace / "sources" / i.id / "text.md") for i in items]
        text = "\n\n".join(t.read_text().strip() for t in texts if t.exists() and t.read_text().strip())
        refs = [i.id for i in items if i.kind != "audit"]
        if job.request_targets and job.request:
            text = (workspace / "sources" / job.request.id / "text.md").read_text().strip()
            for rel in job.request_targets:
                target = workspace / rel
                if text.startswith("RETIRE"):
                    target.unlink(missing_ok=True)
                elif target.exists():
                    meta, body = frontmatter.split(target.read_text())
                    meta["source_refs"] = refs
                    target.write_text(frontmatter.join(meta, body.rstrip("\n") + f"\n\nRequested: {text}\n"))
            return f"Applied the Request to {', '.join(job.request_targets)}."
        path = workspace / "notes" / f"{_slug(job.title, job.proposal_id)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        first = text.splitlines()[0][:200] if text else job.title
        meta = {"type": "Guidance", "title": job.title, "description": first, "tags": ["fake-agent"]}
        if refs:
            meta["source_refs"] = refs
        if job.use_reference and job.reference_dir:
            from pathlib import Path
            reference = Path(job.reference_dir)
            example = next((p for p in reference.rglob("*") if p.is_file() and ".git" not in p.parts), None)
            if example:
                meta["code_refs"] = [example.relative_to(reference).as_posix()]
        path.write_text(frontmatter.join(meta, f"\n# {job.title}\n\n{text}\n"))
        return f"Created {path.relative_to(workspace)}."
    targets = job.targets if job.mode == "revise" else [c.path for c in job.carried if c.path not in job.locked]
    for rel in targets:
        path = workspace / rel
        if job.mode == "feedback" and job.feedback.strip() == "DELETE":
            path.unlink(missing_ok=True)
            continue
        previous = path.read_text()
        if job.use_reference:
            meta, body = frontmatter.split(previous)
            meta["code_refs"] = [s["path"] for s in meta.get("sources", [])
                                 if isinstance(s, dict) and s.get("kind") == "code"]
            path.write_text(frontmatter.join(meta, body.rstrip("\n") + f"\n\nRevision: {job.feedback.strip()}\n"))
        else:
            path.write_text(previous.rstrip("\n") + f"\n\nRevision: {job.feedback.strip()}\n")
    return f"{job.mode}: {', '.join(targets)}"
