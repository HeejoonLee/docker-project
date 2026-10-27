"""Read-only Bundle references to source code mounted on the worker."""

import hashlib
import subprocess
from pathlib import Path
from urllib.parse import quote

from stonepedia.models import BundleSpec


def resolve(root: Path, subdir: str) -> Path | None:
    if not subdir:
        return None
    if Path(subdir).is_absolute() or ".." in Path(subdir).parts:
        raise ValueError("Reference directory must be a path below /references.")
    parent = root.resolve()
    selected = (parent / subdir).resolve()
    if not selected.is_relative_to(parent) or not selected.is_dir():
        raise ValueError(f"Reference directory '{subdir}' is unavailable under {parent}.")
    return selected


def git_commit(directory: Path) -> str:
    result = subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(directory), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def citation(directory: Path, spec: BundleSpec, relative: str, commit: str = "") -> dict:
    relative = relative.strip()
    path = (directory / relative).resolve()
    if (not relative or Path(relative).is_absolute() or ".." in Path(relative).parts
            or not path.is_relative_to(directory) or not path.is_file()):
        raise ValueError(f"Code citation '{relative}' is not a file in the Reference directory.")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    item = {
        "id": f"code:{relative}",
        "kind": "code",
        "resource": f"code://{spec.slug}/{quote(relative)}",
        "path": relative,
        "reference_dir": spec.reference_dir,
        "sha256": digest,
    }
    if commit:
        item["git_commit"] = commit
    return item


def citations_from_content(content: str) -> list[dict]:
    from stonepedia import frontmatter

    meta, _ = frontmatter.split(content)
    sources = meta.get("sources")
    if not isinstance(sources, list):
        return []
    return [item for item in sources if isinstance(item, dict) and item.get("kind") == "code"]


def changed(root: Path, spec: BundleSpec, items: list[dict]) -> list[str]:
    if not items:
        return []
    try:
        directory = resolve(root, spec.reference_dir)
    except ValueError:
        return sorted({str(item.get("path", "")) for item in items})
    if directory is None:
        return sorted({str(item.get("path", "")) for item in items})
    stale = set()
    for item in items:
        rel = str(item.get("path", ""))
        if item.get("reference_dir") != spec.reference_dir:
            stale.add(rel)
            continue
        try:
            current = citation(directory, spec, rel)
        except ValueError:
            stale.add(rel)
            continue
        if current["sha256"] != item.get("sha256"):
            stale.add(rel)
    return sorted(stale)
