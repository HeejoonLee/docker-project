"""Rules for the contents of one Bundle folder (the Bundle root inside its git repo).

<root>/.stonepedia/bundle.yaml    BundleSettings (versioned with the knowledge)
<root>/.stonepedia/template.yaml  Template
<root>/sources/<id>/              Sources
<root>/index.md, manifest.json    generated on every commit (if enabled)
everything else *.md              Articles
"""

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from stonepedia import frontmatter
from stonepedia.template import DEFAULT_TEMPLATE

NOT_ARTICLES = ("index.md", "README.md", "AGENTS.md", "CLAUDE.md", "CONTEXT.md")
SYSTEM_DIRS = (".stonepedia/", "sources/", ".git/")
INDEX_START = "<!-- stonepedia:articles:start -->"
INDEX_END = "<!-- stonepedia:articles:end -->"


class TypeDef(BaseModel):
    name: str = Field(min_length=1)
    rule: str = ""
    sections: list[str] = []


class FieldDef(BaseModel):
    name: str = Field(min_length=1)
    written_by: Literal["ai", "system"] = "ai"
    required: bool = False
    description: str = ""


class Template(BaseModel):
    types: list[TypeDef] = Field(min_length=1)
    fields: list[FieldDef] = []
    guidance: str = ""


class BundleSettings(BaseModel):
    name: str
    language: str = "ko"
    id_prefix: str = ""  # e.g. "BK-"; empty = no ids assigned
    id_field: str = "id"  # frontmatter key; dots for nesting, e.g. "cornerstone.knowledge_id"
    id_digits: int = Field(default=2, ge=1, le=6)
    generate_index: bool = True
    generate_manifest: bool = True


def meta_dir(root: Path) -> Path:
    return root / ".stonepedia"


def is_article(rel: str) -> bool:
    return rel.endswith(".md") and rel not in NOT_ARTICLES and not rel.startswith(SYSTEM_DIRS)


def load_settings(root: Path) -> BundleSettings:
    data = yaml.safe_load((meta_dir(root) / "bundle.yaml").read_text()) or {}
    return BundleSettings.model_validate(data)


def save_settings(root: Path, settings: BundleSettings) -> None:
    meta_dir(root).mkdir(parents=True, exist_ok=True)
    (meta_dir(root) / "bundle.yaml").write_text(
        yaml.safe_dump(settings.model_dump(), sort_keys=False, allow_unicode=True)
    )


def load_template(root: Path) -> Template:
    path = meta_dir(root) / "template.yaml"
    data = yaml.safe_load(path.read_text()) if path.exists() else DEFAULT_TEMPLATE
    return Template.model_validate(data)


def save_template(root: Path, template: Template) -> None:
    meta_dir(root).mkdir(parents=True, exist_ok=True)
    (meta_dir(root) / "template.yaml").write_text(
        yaml.safe_dump(template.model_dump(), sort_keys=False, allow_unicode=True, width=1000)
    )


def articles(root: Path) -> list[tuple[str, dict]]:
    """(path relative to root, frontmatter) for every Article, sorted by path."""
    out = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if not is_article(rel) or any(part.startswith(".") for part in Path(rel).parts):
            continue
        meta, _ = frontmatter.split(path.read_text(errors="replace"))
        out.append((rel, meta))
    return out


# ---------- ids ----------


def get_field(meta: dict, dotted: str):
    node = meta
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def set_field(meta: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    node = meta
    for key in keys[:-1]:
        if not isinstance(node.get(key), dict):
            node[key] = {}
        node = node[key]
    node[keys[-1]] = value


def assign_ids(root: Path, settings: BundleSettings, paths: list[str]) -> dict[str, str]:
    """Give each of `paths` (Articles relative to root) the next id if it has none. Returns path -> id."""
    if not settings.id_prefix:
        return {}
    pattern = re.compile(re.escape(settings.id_prefix) + r"(\d+)$")
    used = [
        int(m.group(1))
        for _, meta in articles(root)
        if (m := pattern.match(str(get_field(meta, settings.id_field) or "")))
    ]
    next_number = max(used, default=0) + 1
    assigned = {}
    for rel in paths:
        path = root / rel
        meta, body = frontmatter.split(path.read_text())
        if get_field(meta, settings.id_field):
            continue
        new_id = f"{settings.id_prefix}{next_number:0{settings.id_digits}d}"
        next_number += 1
        set_field(meta, settings.id_field, new_id)
        path.write_text(frontmatter.join(meta, body))
        assigned[rel] = new_id
    return assigned


# ---------- index.md / manifest.json ----------


def regenerate(root: Path, settings: BundleSettings) -> None:
    items = articles(root)
    if settings.generate_index:
        _write_index(root, settings, items)
    if settings.generate_manifest:
        _write_manifest(root, settings, items)


def _write_index(root: Path, settings: BundleSettings, items: list[tuple[str, dict]]) -> None:
    rows = ["| ID | Title | Type | Status |", "| --- | --- | --- | --- |"]
    for rel, meta in items:
        title = str(meta.get("title") or rel).replace("|", "\\|")
        rows.append(
            f"| {get_field(meta, settings.id_field) or ''} | [{title}]({rel}) | "
            f"{meta.get('type', '')} | {meta.get('status', '')} |"
        )
    block = f"{INDEX_START}\n<!-- Generated by Stonepedia on every commit; edits inside this block are replaced. -->\n\n" + "\n".join(rows) + f"\n\n{INDEX_END}"
    index = root / "index.md"
    if index.exists():
        text = index.read_text()
        if INDEX_START in text and INDEX_END in text:
            start, end = text.index(INDEX_START), text.index(INDEX_END) + len(INDEX_END)
            text = text[:start] + block + text[end:]
        else:
            text = text.rstrip("\n") + "\n\n## Articles\n\n" + block + "\n"
    else:
        text = f'---\nokf_version: "0.2"\n---\n\n# {settings.name}\n\n## Articles\n\n{block}\n'
    index.write_text(text)


def _write_manifest(root: Path, settings: BundleSettings, items: list[tuple[str, dict]]) -> None:
    documents = []
    for rel, meta in items:
        doc = {"id": get_field(meta, settings.id_field), "path": rel, "type": meta.get("type"),
               "title": meta.get("title"), "status": meta.get("status")}
        documents.append({k: v for k, v in doc.items() if v is not None})
    manifest = {
        "bundle": settings.name,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "document_count": len(documents),
        "documents": documents,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


# ---------- Template inference ----------


def infer_template(root: Path) -> Template:
    """A Template matching the Articles already in the Bundle (for imported repos)."""
    items = articles(root)
    defaults = {t["name"]: t for t in DEFAULT_TEMPLATE["types"]}
    type_counts = Counter(str(meta["type"]) for _, meta in items if meta.get("type"))
    types = [
        TypeDef(name=name, rule=defaults.get(name, {}).get("rule", ""), sections=defaults.get(name, {}).get("sections", []))
        for name, _ in type_counts.most_common()
    ] or [TypeDef(**t) for t in DEFAULT_TEMPLATE["types"]]

    system = {f["name"] for f in DEFAULT_TEMPLATE["fields"] if f["written_by"] == "system"}
    known = {f["name"]: f for f in DEFAULT_TEMPLATE["fields"]}
    key_counts = Counter(key for _, meta in items for key in meta)
    fields = []
    for key, count in key_counts.most_common():
        if key in system or count < max(1, len(items) * 0.3):
            continue
        base = known.get(key, {})
        fields.append(FieldDef(
            name=key,
            written_by="ai",
            required=count == len(items),
            description=base.get("description", "") or f"Used by {count} of {len(items)} Articles.",
        ))
    fields += [FieldDef(name=name, written_by="system") for name in sorted(system)]
    return Template(types=types, fields=fields, guidance=DEFAULT_TEMPLATE["guidance"])
