"""Read and write OKF Article frontmatter, keeping unknown fields and their order."""

import yaml

_FENCE = "---"


def split(text: str) -> tuple[dict, str]:
    if not text.startswith(_FENCE + "\n"):
        return {}, text
    end = text.find("\n" + _FENCE + "\n", len(_FENCE))
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[len(_FENCE) + 1 : end]) or {}
    body = text[end + len(_FENCE) + 2 :]
    return (meta if isinstance(meta, dict) else {}), body


def join(meta: dict, body: str) -> str:
    dumped = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000)
    return f"{_FENCE}\n{dumped}{_FENCE}\n{body}"


def update(text: str, **fields) -> str:
    meta, body = split(text)
    meta.update(fields)
    return join(meta, body)


SYSTEM_FIELDS = ("status", "sources", "generated", "review")


def finalize(content: str, base_content: str | None, generated: dict) -> str:
    """Make an agent-written Article safe to propose.

    System fields are removed and rewritten (`status: proposed`, `generated`); frontmatter fields
    present in the base version but dropped by the agent are restored, so unknown fields survive.
    """
    meta, body = split(content)
    base_meta, _ = split(base_content) if base_content else ({}, "")
    for key, value in base_meta.items():
        if key not in meta and key not in SYSTEM_FIELDS:
            meta[key] = value
    for key in SYSTEM_FIELDS:
        meta.pop(key, None)
    if "sources" in base_meta:
        meta["sources"] = base_meta["sources"]
    meta["status"] = "proposed"
    meta["generated"] = generated
    return join(meta, body if body.startswith("\n") else "\n" + body)
