"""Machine settings edited on the web Settings page, stored under <data>/config/.

- app.json: which agent proposes changes, and its time limit.
- claude-settings.json: passed verbatim to `claude --settings` (endpoint, token, model...).
"""

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

AgentKind = Literal["claude-cli", "fake"]


class AppConfig(BaseModel):
    agent: AgentKind = "claude-cli"
    agent_timeout_minutes: int = Field(default=60, ge=1, le=600)
    max_source_mb: int = Field(default=50, ge=1, le=2000)
    verify_link_certificates: bool = False  # intranet sites often use private CAs


def _app_path(config_dir: Path) -> Path:
    return config_dir / "app.json"


def claude_settings_path(config_dir: Path) -> Path:
    return config_dir / "claude-settings.json"


def load(config_dir: Path) -> AppConfig:
    path = _app_path(config_dir)
    if not path.exists():
        return AppConfig()
    return AppConfig.model_validate_json(path.read_text())


def save(config_dir: Path, cfg: AppConfig) -> None:
    _write(_app_path(config_dir), cfg.model_dump_json(indent=2))


def load_claude_settings(config_dir: Path) -> str:
    path = claude_settings_path(config_dir)
    return path.read_text() if path.exists() else "{}\n"


def save_claude_settings(config_dir: Path, text: str) -> None:
    """Validate and store the Claude settings file. Raises ValueError if it isn't a JSON object."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise ValueError(f"Not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise ValueError("The settings must be a JSON object, e.g. {\"env\": {...}}")
    _write(claude_settings_path(config_dir), text if text.endswith("\n") else text + "\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
