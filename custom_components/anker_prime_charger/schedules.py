"""Timers and schedules of the Anker Prime Charger integration.

Port timers and schedules (ports.Port.key: "usbc_1" ... "usbc_4", and "usba"
for both USB-A ports):
- Timer: turn the port off after a duration (5 minute steps, up to 23:55).
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
"""

from __future__ import annotations

from datetime import time
from typing import Any, Final

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .coordinator import PrimeChargerCoordinator
from .helpers import is_on, to_int, to_weekdays
from .solixapi.mqttcmdmap import SolixMqttCommands

TIMER_STEP: Final = 300  # seconds
TIMER_MAX: Final = 86100  # 23:55
TIMER_DEFAULT: Final = 3600  # when turned on without a duration
SCHEDULE_PARTS: Final = ("start", "end")
NOT_REPORTED: Final = "The charger has not reported this yet, try again in a minute"


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
        raise ServiceValidationError(
            "The timer takes 5 minute steps, up to 23 hours 55 minutes"
        )
    await coordinator.async_send_command(
        f"{port}_port_timer",
        parm_map={
            "set_port_timer_switch": "on" if enabled else "off",
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
        raise HomeAssistantError(NOT_REPORTED)
    await coordinator.async_send_command(
        f"{port}_{part}_time",
        parm_map={
            "set_port_time_switch": "on" if enabled else "off",
            "set_port_time_hour": at.hour,
            "set_port_time_minute": at.minute,
            "set_port_time_weekdays": weekdays,
        },
    )


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
        raise HomeAssistantError(NOT_REPORTED)
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
