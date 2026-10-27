"""Runtime settings, read from environment variables (set by docker compose or `make dev`)."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TASK_QUEUE = "stonepedia"


@dataclass(frozen=True)
class Settings:
    temporal_address: str
    namespace: str
    data_dir: Path
    temporal_ui_upstream: str = "http://localhost:8233"  # where the web app proxies /temporal/ to
    agent: Literal["claude-cli", "fake"] = "claude-cli"  # "fake" is for tests only
    timezone: str = "Asia/Seoul"  # for maintenance schedules
    reference_root: Path = Path("/references")  # read-only host mount, worker only

    @property
    def bundles_dir(self) -> Path:
        return self.data_dir / "bundles"

    @property
    def scratch_dir(self) -> Path:
        return self.data_dir / "scratch"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def sources_dir(self) -> Path:
        """Prepared Sources, staged here until committed into a Bundle."""
        return self.data_dir / "sources"

    @property
    def config_dir(self) -> Path:
        return self.data_dir / "config"


def load() -> Settings:
    return Settings(
        temporal_address=os.environ.get("STONEPEDIA_TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("STONEPEDIA_NAMESPACE", "default"),
        data_dir=Path(os.environ.get("STONEPEDIA_DATA_DIR", ".data")).resolve(),
        temporal_ui_upstream=os.environ.get("STONEPEDIA_TEMPORAL_UI_UPSTREAM", "http://localhost:8233"),
        timezone=os.environ.get("STONEPEDIA_TIMEZONE", "Asia/Seoul"),
        reference_root=Path(os.environ.get("STONEPEDIA_REFERENCE_ROOT", "/references")).resolve(),
        agent="fake" if os.environ.get("STONEPEDIA_AGENT") == "fake" else "claude-cli",
    )
