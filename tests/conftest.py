import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import pytest_asyncio
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from stonepedia import search
from stonepedia.config import Settings
from stonepedia.worker import build_worker


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def env():
    async with await WorkflowEnvironment.start_local(
        data_converter=pydantic_data_converter,
        search_attributes=search.ALL,
        dev_server_existing_path=shutil.which("temporal"),
    ) as env:
        yield env


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        temporal_address="unused",
        namespace="default",
        data_dir=tmp_path,
        temporal_ui_url="http://localhost:8233",
    )


@pytest_asyncio.fixture(loop_scope="session")
async def worker(env, settings):
    with ThreadPoolExecutor(max_workers=4) as executor:
        w = build_worker(env.client, settings, executor)
        async with w:
            yield w


@pytest.fixture
def uid() -> str:
    return uuid.uuid4().hex[:8]
