"""Shared Temporal client setup."""

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from stonepedia.config import Settings


async def connect(settings: Settings) -> Client:
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.namespace,
        data_converter=pydantic_data_converter,
    )
