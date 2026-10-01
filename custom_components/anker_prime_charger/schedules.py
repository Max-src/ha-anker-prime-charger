"""Timers and schedules of the Anker Prime Charger integration.

Port timers and schedules (ports.Port.key: "usbc_1" ... "usbc_4", and "usba"
for both USB-A ports):
- Timer: turn the port off after a duration (1 minute steps, up to 23:55).
  Command "<port>_port_timer": on/off and the duration in seconds; the status
  reports <port>_timer_switch, _timer_seconds and _timer_remaining_seconds.
- Schedule: a start and an end, each with its own on/off, time and weekdays.
  Commands "<port>_start_time" / "<port>_end_time"; the status reports
  <port>_start_switch, _start_hour, _start_minute, _start_weekdays (bit 0 =
  Monday), and the same for _end_.

Clock display schedule: the daily period and the weekdays in which the clock
screen is shown; command "clock_display_schedule", status
clock_display_start_hour/_minute, clock_display_end_hour/_minute,
clock_display_weekdays.

Each command carries a whole timer or schedule (part), so the current values
are always sent along with the one that changes.

Schedules are addressed as (port, part): a port's key and "start" or "end",
or port None for the clock display schedule (its days are shared by both
parts, so `part` doesn't matter there).
"""

from __future__ import annotations

from datetime import time
from typing import Any, Final

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .coordinator import PrimeChargerCoordinator
from .helpers import WEEKDAYS, is_on, on_off, to_int, to_weekdays, translated
from .mqtt_extensions import TIMER_STEP
from .solixapi.mqttcmdmap import SolixMqttCommands

TIMER_MAX: Final = 86100  # 23:55
TIMER_DEFAULT: Final = 3600  # when turned on without a duration
SCHEDULE_PARTS: Final = ("start", "end")

# Common sets of weekdays (the days preset selects); any other set is "custom"
DAY_PRESETS: Final[dict[str, tuple[str, ...]]] = {
    "every_day": WEEKDAYS,
    "weekdays": WEEKDAYS[:5],
    "weekends": WEEKDAYS[5:],
    "none": (),
}


def time_prefix(port: str | None, part: str) -> str:
    """Status key prefix of a schedule time (<prefix>_hour, <prefix>_minute)."""
    return f"{port}_{part}" if port else f"clock_display_{part}"


def weekdays_key(port: str | None, part: str | None) -> str:
    """Status key of a schedule's weekdays."""
    return f"{port}_{part}_weekdays" if port else "clock_display_weekdays"


def reported_time(data: dict[str, Any], prefix: str) -> time | None:
    """A time the charger reports as <prefix>_hour and <prefix>_minute."""
    hour = to_int(data.get(f"{prefix}_hour"))
    minute = to_int(data.get(f"{prefix}_minute"))
    if hour is None or minute is None:
        return None
    try:
        return time(hour, minute)
    except ValueError:
        return None


async def async_set_timer(
    coordinator: PrimeChargerCoordinator,
    port: str,
    enabled: bool | None = None,
    seconds: int | None = None,
) -> None:
    """Send the port's timer with the given changes."""
    data = coordinator.data or {}
    if enabled is None:
        enabled = bool(is_on(data.get(f"{port}_timer_switch")))
    if seconds is None:
        seconds = to_int(data.get(f"{port}_timer_seconds")) or 0
    if enabled and not seconds:
        seconds = TIMER_DEFAULT
    if seconds % TIMER_STEP or not 0 <= seconds <= TIMER_MAX:
        raise translated(ServiceValidationError, "timer_duration")
    await coordinator.async_send_command(
        f"{port}_port_timer",
        parm_map={
            "set_port_timer_switch": on_off(enabled),
            "set_port_timer_seconds": seconds,
        },
    )


async def async_set_schedule(
    coordinator: PrimeChargerCoordinator,
    port: str,
    part: str,
    enabled: bool | None = None,
    at: time | None = None,
    weekdays: list[str] | None = None,
) -> None:
    """Send the start or end of a port's schedule with the given changes."""
    data = coordinator.data or {}
    if enabled is None:
        enabled = bool(is_on(data.get(f"{port}_{part}_switch")))
    at = at or reported_time(data, f"{port}_{part}")
    if weekdays is None:
        weekdays = to_weekdays(data.get(f"{port}_{part}_weekdays"))
    if at is None or weekdays is None:
        raise translated(HomeAssistantError, "not_reported")
    await coordinator.async_send_command(
        f"{port}_{part}_time",
        parm_map={
            "set_port_time_switch": on_off(enabled),
            "set_port_time_hour": at.hour,
            "set_port_time_minute": at.minute,
            "set_port_time_weekdays": weekdays,
        },
    )


async def async_set_time(
    coordinator: PrimeChargerCoordinator, port: str | None, part: str, at: time
) -> None:
    """Set the time of a schedule's start or end."""
    if port is None:
        await async_set_clock_schedule(coordinator, **{part: at})
    else:
        await async_set_schedule(coordinator, port, part, at=at)


async def async_set_days(
    coordinator: PrimeChargerCoordinator,
    port: str | None,
    part: str | None,
    weekdays: list[str],
) -> None:
    """Set the weekdays (in any order) of a schedule."""
    weekdays = [day for day in WEEKDAYS if day in weekdays]
    if port is None:
        await async_set_clock_schedule(coordinator, weekdays=weekdays)
    else:
        await async_set_schedule(coordinator, port, part, weekdays=weekdays)


async def async_set_clock_schedule(
    coordinator: PrimeChargerCoordinator,
    start: time | None = None,
    end: time | None = None,
    weekdays: list[str] | None = None,
) -> None:
    """Send the clock display schedule with the given changes."""
    data = coordinator.data or {}
    start = start or reported_time(data, "clock_display_start")
    end = end or reported_time(data, "clock_display_end")
    if weekdays is None:
        weekdays = to_weekdays(data.get("clock_display_weekdays"))
    if start is None or end is None or weekdays is None:
        raise translated(HomeAssistantError, "not_reported")
    await coordinator.async_send_command(
        SolixMqttCommands.clock_display_schedule,
        parm_map={
            "set_clock_display_start_hour": start.hour,
            "set_clock_display_start_minute": start.minute,
            "set_clock_display_end_hour": end.hour,
            "set_clock_display_end_minute": end.minute,
            "set_clock_display_weekdays": weekdays,
        },
    )
