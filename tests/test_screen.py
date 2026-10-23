"""The page the screen shows, as estimated (screen.py and its sensor)."""

from __future__ import annotations

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.anker_prime_charger import screen
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .conftest import STATUS, FakeCloud
from .helpers import attr, call, entity_id, state

# Clock screensaver on, 07:00-22:30 Monday to Friday; Timeout 30 s (STATUS)
MONDAY = datetime(2026, 10, 19)


def local(day: datetime, hour: int, minute: int = 0) -> datetime:
    """A time of `day` in Home Assistant's time zone (the charger's)."""
    return day.replace(hour=hour, minute=minute, tzinfo=dt_util.get_default_time_zone())


@pytest.mark.parametrize(
    ("changes", "at", "expected"),  # at: (days after Monday, hour, minute)
    [
        ({}, (0, 8, 31), "clock"),
        ({}, (0, 22, 30), "off"),  # the end isn't shown
        ({}, (0, 6, 59), "off"),
        ({}, (5, 12, 0), "off"),  # Saturday
        ({"clock_switch": 0}, (0, 12, 0), "off"),
        ({"display_timeout_mode": 0}, (0, 23, 0), "power"),  # always on
        ({"display_timeout_mode": None}, (0, 12, 0), None),
        # past midnight: from 22:00, or until 07:00
        (
            {"clock_display_start_hour": 22, "clock_display_end_hour": 7},
            (0, 23, 0),
            "clock",
        ),
        (
            {"clock_display_start_hour": 22, "clock_display_end_hour": 7},
            (0, 12, 0),
            "off",
        ),
    ],
)
async def test_page_after_the_timeout(
    hass: HomeAssistant, changes: dict, at: tuple[int, int, int], expected: str
) -> None:
    """Asleep: the clock within its hours and days, else off."""
    days, hour, minute = at
    now = local(MONDAY + timedelta(days=days), hour, minute)
    assert screen.page(STATUS | changes, None, now) == expected


async def test_page_within_the_timeout(hass: HomeAssistant) -> None:
    """The power page for the Timeout after a wake, whatever the clock."""
    woke = local(MONDAY, 23)
    assert screen.page(STATUS, woke, woke + timedelta(seconds=29)) == "power"
    assert screen.page(STATUS, woke, woke + timedelta(seconds=30)) == "off"
    five_minutes = STATUS | {"display_timeout_mode": 3}
    assert screen.page(five_minutes, woke, woke + timedelta(minutes=4)) == "power"
    # the next change: the Timeout's end, else the next minute
    assert screen.next_change(STATUS, woke, woke + timedelta(seconds=10)) == (
        woke + timedelta(seconds=30)
    )
    assert screen.next_change(STATUS, None, woke + timedelta(seconds=10)) == (
        woke + timedelta(minutes=1)
    )


async def test_sensor_follows_the_wakes(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
) -> None:
    """Commands and devices plugged in or out wake it; the theme command doesn't."""

    async def later(delta: timedelta = timedelta()) -> None:
        freezer.tick(delta)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    freezer.move_to(local(MONDAY, 8, 31))
    cloud.mqtt.deliver({"usbc_1_power": 1.6})  # the charger heard at the new time
    await later()
    assert state(hass, "sensor", "screen_page") == "clock"
    assert attr(hass, "sensor", "screen_page", "options") == ["power", "clock", "off"]
    assert (
        attr(hass, "sensor", "screen_page", "friendly_name")
        == "250W Prime Charger Screen Page"
    )

    # a command: the power page for the Timeout (30 s)
    await call(hass, "switch", "turn_off", entity_id(hass, "switch", "usbc_4_switch"))
    assert state(hass, "sensor", "screen_page") == "power"
    await later(timedelta(seconds=29))
    assert state(hass, "sensor", "screen_page") == "power"
    await later(timedelta(seconds=2))
    assert state(hass, "sensor", "screen_page") == "clock"

    # the theme command (Clock screensaver off) doesn't wake it
    await call(hass, "switch", "turn_off", entity_id(hass, "switch", "clock_switch"))
    assert state(hass, "sensor", "screen_page") == "off"

    # a device plugged in wakes it; other readings don't
    cloud.mqtt.deliver({"usbc_4_status": 1})
    await hass.async_block_till_done()
    assert state(hass, "sensor", "screen_page") == "power"
    await later(timedelta(seconds=31))
    cloud.mqtt.deliver({"usbc_4_power": 5.0})
    await hass.async_block_till_done()
    assert state(hass, "sensor", "screen_page") == "off"


async def test_sensor_follows_the_clock_hours(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
) -> None:
    """At the end of the clock's hours the screen goes dark."""
    freezer.move_to(local(MONDAY, 22, 29))
    cloud.mqtt.deliver({"usbc_1_power": 1.6})  # the charger heard at the new time
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert state(hass, "sensor", "screen_page") == "clock"
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert state(hass, "sensor", "screen_page") == "off"
