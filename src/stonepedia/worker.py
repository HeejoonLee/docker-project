"""Temporal worker entry point: `python -m stonepedia.worker`."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from stonepedia import config
from stonepedia.activities import Activities
from stonepedia.temporal import connect
from stonepedia.workflows import AgentCheckWorkflow, BundleWorkflow, ProposalWorkflow


def build_worker(client: Client, settings: config.Settings, executor: ThreadPoolExecutor) -> Worker:
    settings.bundles_dir.mkdir(parents=True, exist_ok=True)
    settings.scratch_dir.mkdir(parents=True, exist_ok=True)
    return Worker(
        client,
        task_queue=config.TASK_QUEUE,
        workflows=[AgentCheckWorkflow, BundleWorkflow, ProposalWorkflow],
        activities=Activities(settings, client).all(),
        activity_executor=executor,
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = config.load()
    client = await connect(settings)
    with ThreadPoolExecutor(max_workers=8) as executor:
        await build_worker(client, settings, executor).run()


if __name__ == "__main__":
    asyncio.run(main())
