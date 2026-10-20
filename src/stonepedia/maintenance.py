"""Integrity checks over one Bundle. Read-only: findings become a report, never a change."""

import re
from collections import defaultdict
from pathlib import Path

from stonepedia import bundle, frontmatter
from stonepedia.models import Finding

_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|#|//)", re.I)


def check(root: Path, repo: Path) -> list[Finding]:
    settings = bundle.load_settings(root)
    template = bundle.load_template(root)
    type_names = {t.name for t in template.types}
    required = [f.name for f in template.fields if f.written_by == "ai" and f.required]
    findings: list[Finding] = []
    cited: set[str] = set()
    ids: dict[str, list[str]] = defaultdict(list)

    for rel, meta in bundle.articles(root):
        path = root / rel
        _, body = frontmatter.split(path.read_text(errors="replace"))
        if meta.get("status") == "retired":
            continue
        if not meta:
            findings.append(Finding(severity="error", kind="no_frontmatter", path=rel, message="No YAML frontmatter."))
            continue
        for name in required:
            if meta.get(name) in (None, "", []):
                findings.append(Finding(severity="warning", kind="missing_field", path=rel,
                                        message=f"Required field '{name}' is missing."))
        if meta.get("type") and meta["type"] not in type_names:
            findings.append(Finding(severity="warning", kind="unknown_type", path=rel,
                                    message=f"Type '{meta['type']}' is not in the Template ({', '.join(sorted(type_names))})."))
        if article_id := bundle.get_field(meta, settings.id_field):
            ids[str(article_id)].append(rel)

        for target in _LINK.findall(body):
            if _EXTERNAL.match(target):
                continue
            if not _exists(path.parent, target, repo):
                findings.append(Finding(severity="error", kind="broken_link", path=rel,
                                        message=f"Link target not found: {target}"))

        for src in meta.get("sources") or []:
            if not isinstance(src, dict):
                continue
            if src.get("id"):
                cited.add(str(src["id"]))
            for key in ("resource", "archived"):
                ref = src.get(key)
                if isinstance(ref, str) and ref and not _EXTERNAL.match(ref) and not _exists(path.parent, ref, repo):
                    findings.append(Finding(severity="error", kind="missing_source", path=rel,
                                            message=f"Source '{src.get('id', '?')}' points to a missing file: {ref}"))

    for article_id, paths in ids.items():
        if len(paths) > 1:
            findings.append(Finding(severity="error", kind="duplicate_id", path=paths[0],
                                    message=f"Id {article_id} is used by {', '.join(paths)}."))

    sources_dir = root / "sources"
    if sources_dir.is_dir():
        for folder in sorted(p for p in sources_dir.iterdir() if p.is_dir()):
            if folder.name not in cited:
                findings.append(Finding(severity="warning", kind="uncited_source", path=f"sources/{folder.name}",
                                        message="No Article cites this Source."))
    return findings


def _exists(base: Path, target: str, repo: Path) -> bool:
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return True
    from urllib.parse import unquote

    resolved = (base / unquote(target)).resolve()
    return resolved.is_relative_to(repo.resolve()) and resolved.exists()
