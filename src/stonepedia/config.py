"""Runtime settings, read from environment variables (set by docker compose or `make dev`)."""

import os
from dataclasses import dataclass
from pathlib import Path

TASK_QUEUE = "stonepedia"


@dataclass(frozen=True)
class Settings:
    temporal_address: str
    namespace: str
    data_dir: Path
    temporal_ui_url: str

    @property
    def bundles_dir(self) -> Path:
        return self.data_dir / "bundles"

    @property
    def scratch_dir(self) -> Path:
        return self.data_dir / "scratch"

    @property
    def config_dir(self) -> Path:
        return self.data_dir / "config"


def load() -> Settings:
    return Settings(
        temporal_address=os.environ.get("STONEPEDIA_TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("STONEPEDIA_NAMESPACE", "default"),
        data_dir=Path(os.environ.get("STONEPEDIA_DATA_DIR", ".data")).resolve(),
        temporal_ui_url=os.environ.get("STONEPEDIA_TEMPORAL_UI_URL", "http://localhost:8233"),
    )
