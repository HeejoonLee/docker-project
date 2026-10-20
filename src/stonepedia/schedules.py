"""Maintenance schedules, stored as Temporal Schedules (one per Bundle and check)."""

from typing import Literal

from pydantic import BaseModel, Field
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleCalendarSpec,
    ScheduleRange,
    ScheduleSpec,
    ScheduleUpdate,
)
from temporalio.common import SearchAttributePair, TypedSearchAttributes
from temporalio.service import RPCError

from stonepedia import config, search
from stonepedia.models import MaintenanceCheck, MaintenanceInput

Cadence = Literal["off", "daily", "weekly"]


class ScheduleConfig(BaseModel):
    cadence: Cadence = "off"
    time: str = Field(default="03:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekday: int = Field(default=0, ge=0, le=6)  # 0 = Sunday (weekly only)
    next_run: str | None = None


def schedule_id(bundle: str, check: MaintenanceCheck) -> str:
    return f"maintenance-{bundle}-{check}"


async def get(client: Client, bundle: str, check: MaintenanceCheck) -> ScheduleConfig:
    try:
        desc = await client.get_schedule_handle(schedule_id(bundle, check)).describe()
    except RPCError:
        return ScheduleConfig()
    cal = desc.schedule.spec.calendars[0]
    weekly = len(cal.day_of_week) == 1 and cal.day_of_week[0].end in (0, cal.day_of_week[0].start)
    next_times = desc.info.next_action_times
    return ScheduleConfig(
        cadence="weekly" if weekly else "daily",
        time=f"{cal.hour[0].start:02d}:{cal.minute[0].start:02d}",
        weekday=cal.day_of_week[0].start if weekly else 0,
        next_run=next_times[0].isoformat() if next_times else None,
    )


async def put(client: Client, settings: config.Settings, bundle: str, check: MaintenanceCheck, cfg: ScheduleConfig) -> ScheduleConfig:
    handle = client.get_schedule_handle(schedule_id(bundle, check))
    if cfg.cadence == "off":
        try:
            await handle.delete()
        except RPCError:
            pass
        return ScheduleConfig()
    hour, minute = (int(x) for x in cfg.time.split(":"))
    calendar = ScheduleCalendarSpec(
        hour=[ScheduleRange(hour)],
        minute=[ScheduleRange(minute)],
        **({"day_of_week": [ScheduleRange(cfg.weekday)]} if cfg.cadence == "weekly" else {}),
        comment=f"{cfg.cadence} {cfg.time}",
    )
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            "MaintenanceWorkflow",
            MaintenanceInput(bundle=bundle, check=check, requested_by="schedule"),
            id=schedule_id(bundle, check),
            task_queue=config.TASK_QUEUE,
            typed_search_attributes=TypedSearchAttributes([SearchAttributePair(search.BUNDLE, bundle)]),
        ),
        spec=ScheduleSpec(calendars=[calendar], time_zone_name=settings.timezone),
    )
    try:
        await client.create_schedule(schedule_id(bundle, check), schedule)
    except ScheduleAlreadyRunningError:
        await handle.update(lambda _: ScheduleUpdate(schedule=schedule))
    return await get(client, bundle, check)
