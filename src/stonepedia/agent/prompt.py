"""Builds the instructions given to the proposing agent."""

from stonepedia.agent import TASK_DIR
from stonepedia.models import AgentJob

LANGUAGES = {"ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese"}
SYSTEM_FIELDS = ("status", "sources", "generated", "review")


def build(job: AgentJob, bundle: dict, template: dict, stale_targets: list[str]) -> str:
    language = LANGUAGES.get(bundle.get("language", ""), bundle.get("language") or "English")
    return "\n\n".join(
        [
            _intro(bundle),
            _contract(template, language),
            _rules(),
            _task(job, stale_targets),
            _finish(language),
        ]
    )


def _intro(bundle: dict) -> str:
    return (
        f'You maintain "{bundle.get("name", "this Bundle")}", a knowledge base of OKF v0.2 Markdown '
        "Articles that AI agents read. Your working directory is a copy of it. Your edits become a "
        "Proposal that a human reviews before anything is committed."
    )


def _contract(template: dict, language: str) -> str:
    lines = ["## Article contract (this Bundle's Template)", "", "Types (each Article has exactly one):"]
    for t in template.get("types", []):
        sections = ", ".join(t.get("sections", []))
        lines.append(f"- `{t['name']}`: {t.get('rule', '')}" + (f" Typical sections: {sections}." if sections else ""))
    lines.append("")
    lines.append("Frontmatter fields you write:")
    for f in template.get("fields", []):
        if f.get("written_by", "ai") == "ai":
            req = "required" if f.get("required") else "optional"
            lines.append(f"- `{f['name']}` ({req}): {f.get('description', '')}")
    system = [f["name"] for f in template.get("fields", []) if f.get("written_by") == "system"]
    system = sorted(set(system) | set(SYSTEM_FIELDS))
    lines.append("")
    lines.append(f"Fields the system writes; never add or change them: {', '.join(f'`{s}`' for s in system)}.")
    if template.get("guidance"):
        lines += ["", "Writing guidance:", template["guidance"].strip()]
    lines += ["", f"Write Article prose in {language}. Keep original technical terms."]
    return "\n".join(lines)


def _rules() -> str:
    return "\n".join(
        [
            "## Rules",
            "- Only create or edit Markdown Articles. Never touch `.stonepedia/`, `sources/`, `index.md` or `README.md`."
            " Existing Sources under `sources/` may be read as evidence.",
            "- First survey the existing Articles (Glob `**/*.md`, then read the ones that look related). "
            "Prefer updating an existing Article over creating a near-duplicate; keep one home per fact.",
            "- Put a new Article in an existing topic folder when one fits, otherwise a new short folder. "
            "Use lowercase ASCII kebab-case file and folder names ending in `.md`.",
            "- Every Article starts with YAML frontmatter between `---` lines, followed by the body.",
            "- When updating an Article, keep frontmatter fields you do not recognize exactly as they are.",
            "- Base every claim on the material provided or on the existing Articles. "
            "Mark assumptions and unknowns explicitly; never invent values.",
        ]
    )


def _material(job: AgentJob) -> str:
    src = job.source
    folder = f"sources/{src.id}"
    if src.kind == "text":
        lines = [f'The material is in `{folder}/text.md` ("{job.title}", submitted by {job.submitted_by}).']
    elif src.kind == "request":
        lines = [
            f"This is a Request by {src.submitted_by} (`{folder}/request.md`): a direct statement from a person,",
            "not a document. Record it as that person's statement, not as verified fact.",
        ]
        if job.request_targets:
            lines.append("It is aimed at: " + ", ".join(f"`{p}`" for p in job.request_targets) + ".")
    elif src.kind == "link":
        lines = [
            f"The material was fetched from {src.url}. `{folder}/text.md` is its text; "
            f"`{folder}/{src.original}` is the original.",
        ]
    elif src.media == "image":
        lines = [
            f"The material is an image (for example a photo of a handwritten note): `{folder}/{src.original}`"
            f' ("{src.filename}"). Read the image directly. In your summary, mention anything you could not read.',
        ]
    else:
        unit = "pages" if src.media == "pdf" else "slides" if src.media == "pptx" else ""
        count = f", {src.pages} {unit}" if src.pages and unit else ""
        lines = [
            f'The material is the {src.media} file "{src.filename}"{count}. `{folder}/text.md` holds its extracted '
            f"text with section markers; `{folder}/{src.original}` is the original. Use Grep on text.md to find "
            "relevant parts of large documents. If the text is missing or garbled (e.g. a scan), read the original.",
        ]
    for warning in src.warnings:
        lines.append(f"Note: {warning}")
    lines.append(
        "The system adds this Source to the `sources` field of every Article you create or change; "
        "refer to it in the body where useful (e.g. by page)."
    )
    return "\n".join(lines)


def _task(job: AgentJob, stale_targets: list[str]) -> str:
    if job.mode == "propose":
        return (
            "## Task\n"
            f'Turn this material ("{job.title}") into Article changes: create new Articles and/or update existing ones.\n\n'
            + _material(job)
        )
    if job.mode == "revise":
        lines = [
            "## Task",
            f"A reviewer asked for changes to: {', '.join(f'`{p}`' for p in job.targets)}.",
            "The current proposed version is already in the working copy. Change only these files.",
            "",
            "Reviewer feedback:",
            job.feedback.strip() or "(none given: produce an improved version)",
            "",
            _material(job),
        ]
        for path in stale_targets:
            lines.append(
                f"\n`{path}` was changed in the knowledge base after it was proposed. The working copy holds the "
                f"current version; the earlier proposal is in `{TASK_DIR}/previous/{path}`. "
                "Re-apply the earlier proposal's intent on top of the current file."
            )
        return "\n".join(lines)
    pending = [c.path for c in job.carried if c.path not in job.locked]
    lines = [
        "## Task",
        "A reviewer gave feedback on the whole Proposal. Its current changes are already applied in the working copy.",
        "",
        "Reviewer feedback:",
        job.feedback.strip(),
        "",
        "Pending Articles you may change, merge, split or replace: " + (", ".join(f"`{p}`" for p in pending) or "(none)"),
        "You may also create or update other Articles. To withdraw a new Article you proposed, delete its file.",
    ]
    if job.locked:
        lines.append("Accepted Articles you must not modify: " + ", ".join(f"`{p}`" for p in job.locked))
    lines += ["", _material(job)]
    return "\n".join(lines)


def _finish(language: str) -> str:
    return (
        "## When done\n"
        f"Reply in {language} with a short summary: one line per file you created or changed, saying what "
        "changed and why. Mention anything you could not resolve from the material."
    )
