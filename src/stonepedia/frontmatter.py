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
