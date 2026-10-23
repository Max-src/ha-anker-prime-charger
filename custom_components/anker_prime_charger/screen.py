"""What the charger's screen shows: an estimate (the charger doesn't report it).

As tried at the charger: the screen wakes on the power page when a device is
plugged in or out, and with every command from Home Assistant except the
theme command (a theme change, or Clock screensaver turned on or off, only
changes what the screensaver shows). Status requests and fast updates don't
wake it. It stays on for the Timeout after the last of these, then shows the
clock screensaver if it is on and within its hours and days, else goes dark.

Turning the knob wakes it too, which Home Assistant can't see: then the
estimate says clock or off while the power page shows, until the Timeout.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Final

from homeassistant.util import dt as dt_util

from .helpers import WEEKDAYS, is_on, reported_time, to_int, to_weekdays
from .ports import PORTS
from .solixapi.mqttcmdmap import SolixMqttCommands

POWER: Final = "power"
CLOCK: Final = "clock"
OFF: Final = "off"
PAGES: Final = (POWER, CLOCK, OFF)

# display_timeout_mode -> how long the screen stays on (None: always on)
TIMEOUTS: Final[dict[int, timedelta | None]] = {
    0: None,
    1: timedelta(seconds=30),
    2: timedelta(minutes=1),
    3: timedelta(minutes=5),
    4: timedelta(minutes=30),
}
# Commands that don't wake the screen
QUIET_COMMANDS: Final = (
    SolixMqttCommands.charger_theme,
    SolixMqttCommands.charger_theme_custom,
)
# A device plugged in or out of a port
PORT_STATUS_KEYS: Final = tuple(
    f"{output}_status" for port in PORTS for output in port.outputs
)


def plugged_changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Whether a device was plugged into or out of a port between two statuses."""
    for key in PORT_STATUS_KEYS:
        before, after = is_on(old.get(key)), is_on(new.get(key))
        if before is not None and after is not None and before != after:
            return True
    return False


def page(data: dict[str, Any], last_wake: datetime | None, now: datetime) -> str | None:
    """The page shown at `now` (None until the Timeout is reported)."""
    mode = to_int(data.get("display_timeout_mode"))
    if mode not in TIMEOUTS:
        return None
    timeout = TIMEOUTS[mode]
    if timeout is None or (last_wake is not None and now < last_wake + timeout):
        return POWER
    return CLOCK if _clock_shown(data, dt_util.as_local(now)) else OFF


def next_change(
    data: dict[str, Any], last_wake: datetime | None, now: datetime
) -> datetime:
    """When the page may change by itself: the Timeout's end or the next minute.

    (The clock's hours are set in minutes.)
    """
    following = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    timeout = TIMEOUTS.get(to_int(data.get("display_timeout_mode")) or 0)
    if last_wake is not None and timeout is not None and now < last_wake + timeout:
        return min(last_wake + timeout, following)
    return following


def _clock_shown(data: dict[str, Any], local: datetime) -> bool:
    """Whether the clock screensaver shows at `local` (the charger's time)."""
    if not is_on(data.get("clock_switch")):
        return False
    days = to_weekdays(data.get("clock_display_weekdays"))
    if days is not None and WEEKDAYS[local.weekday()] not in days:
        return False
    start = reported_time(data, "clock_display_start")
    end = reported_time(data, "clock_display_end")
    if start is None or end is None or start == end:
        return True
    at = time(local.hour, local.minute)
    # hours past midnight (22:00-07:00): from the start, or until the end
    return start <= at < end if start < end else at >= start or at < end
