"""Port timers and schedules, custom-mode protocols, fast updates, hidden animations."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .conftest import TIMER_REPORTED, FakeCloud
from .helpers import attr, call, entity_id, last_command_field, state

WEEKDAYS_MON_FRI = ["mon", "tue", "wed", "thu", "fri"]


async def test_port_timer(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """A timer is sent with its on/off and duration (default 1 h)."""
    eid = entity_id(hass, "switch", "usbc_2_timer_switch")
    assert hass.states.get(eid).state == STATE_OFF
    await call(hass, "switch", "turn_on", eid)
    assert commands[-1] == (
        "usbc_2_port_timer",
        {"set_port_timer_switch": "on", "set_port_timer_seconds": 3600},
    )
    assert cloud.mqtt.published_types[-1] == "0209"
    assert last_command_field(cloud, "a2") == "0101"  # port select: USB-C 2
    assert hass.states.get(eid).state == STATE_ON


async def test_port_timer_duration(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """The duration is in minutes, 5 minute steps, and keeps the timer running."""
    eid = entity_id(hass, "number", "usbc_1_timer_seconds")
    assert float(hass.states.get(eid).state) == 60
    await call(hass, "number", "set_value", eid, value=90)
    assert commands[-1] == (
        "usbc_1_port_timer",
        {"set_port_timer_switch": "on", "set_port_timer_seconds": 5400},
    )
    with pytest.raises(ServiceValidationError, match="5 minute steps"):
        await call(hass, "number", "set_value", eid, value=7)


async def test_port_timer_end(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """The end time is when the remaining seconds were reported, plus them."""
    end = dt_util.utc_from_timestamp(TIMER_REPORTED + 1800)
    assert state(hass, "sensor", "usbc_1_timer_end") == end.isoformat()
    assert state(hass, "sensor", "usbc_2_timer_end") == STATE_UNKNOWN  # timer off


async def test_port_schedule(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Each start or end is sent whole: on/off, time and weekdays."""
    assert state(hass, "switch", "usba_start_switch") == STATE_ON
    assert state(hass, "time", "usba_start_time") == "07:30:00"
    days = entity_id(hass, "text", "usba_start_weekdays")
    assert hass.states.get(days).state == "mon,tue,wed,thu,fri"

    await call(
        hass,
        "time",
        "set_value",
        entity_id(hass, "time", "usba_start_time"),
        time="08:15:00",
    )
    assert commands[-1] == (
        "usba_start_time",
        {
            "set_port_time_switch": "on",
            "set_port_time_hour": 8,
            "set_port_time_minute": 15,
            "set_port_time_weekdays": WEEKDAYS_MON_FRI,
        },
    )
    assert cloud.mqtt.published_types[-1] == "0208"
    assert state(hass, "time", "usba_start_time") == "08:15:00"

    await call(hass, "text", "set_value", days, value="sat,sun")
    assert commands[-1][1]["set_port_time_weekdays"] == ["sat", "sun"]
    assert commands[-1][1]["set_port_time_hour"] == 8
    assert hass.states.get(days).state == "sat,sun"

    await call(
        hass, "switch", "turn_on", entity_id(hass, "switch", "usbc_3_end_switch")
    )
    assert commands[-1] == (
        "usbc_3_end_time",
        {
            "set_port_time_switch": "on",
            "set_port_time_hour": 0,
            "set_port_time_minute": 0,
            "set_port_time_weekdays": [],
        },
    )


async def test_custom_protocols(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """A USB-C port's protocols are set all at once, like the app's list."""
    eid = entity_id(hass, "text", "custom_usb_c1_protocols")
    st = hass.states.get(eid)
    assert st.state == "ufcs"
    # USB-C 1 is at 100 W: everything but Huawei (the cloud's table)
    assert st.attributes["allowed"] == [
        "scp",
        "ufcs",
        "pd12v",
        "pps11v",
        "pps16v",
        "pps20v",
        "xiaomi",
    ]
    assert state(hass, "text", "custom_usb_c2_protocols") == "none"

    await call(hass, "text", "set_value", eid, value="pps20v, SCP,ufcs")
    cmd, parm_map = commands[-1]
    assert cmd == "charger_custom_usage_mode"
    assert parm_map["set_usb_c1_protocols"] == ["scp", "ufcs", "pps20v"]
    assert parm_map["set_usb_c4_protocols"] == ["ufcs"]  # others unchanged
    assert cloud.mqtt.published_types[-1] == "0206"
    assert hass.states.get(eid).state == "scp,ufcs,pps20v"

    sent = len(commands)
    await call(hass, "text", "set_value", eid, value="ufcs,scp,pps20v")  # unchanged
    assert len(commands) == sent
    with pytest.raises(ServiceValidationError, match="possible: scp"):
        await call(hass, "text", "set_value", eid, value="usb4")
    await call(hass, "text", "set_value", eid, value="none")
    assert commands[-1][1]["set_usb_c1_protocols"] == []


async def test_custom_protocols_follow_power(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Protocols a port's power doesn't allow are refused, or dropped when lowering it."""
    c4 = entity_id(hass, "text", "custom_usb_c4_protocols")  # 15 W
    assert attr(hass, "text", "custom_usb_c4_protocols", "allowed") == ["ufcs"]
    with pytest.raises(
        ServiceValidationError, match="15 W doesn't allow scp; allowed: ufcs"
    ):
        await call(hass, "text", "set_value", c4, value="scp,ufcs")

    c1 = entity_id(hass, "text", "custom_usb_c1_protocols")
    await call(hass, "text", "set_value", c1, value="scp,ufcs,pps16v")
    # Lowering USB-C 1 to 30 W drops 5-16V PPS (needs 45 W), keeps SCP and UFCS
    await call(
        hass,
        "number",
        "set_value",
        entity_id(hass, "number", "custom_usb_c1_power_limit"),
        value=30,
    )
    assert commands[-1][1]["set_usb_c1_power_limit"] == 30
    assert commands[-1][1]["set_usb_c1_protocols"] == ["scp", "ufcs"]


async def test_fast_updates(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Fast updates resend the real-time trigger every 8 s until turned off."""
    eid = entity_id(hass, "switch", "fast_updates")
    assert hass.states.get(eid).state == STATE_OFF

    def triggers() -> int:
        return cloud.mqtt.published_types.count("020b")

    await call(hass, "switch", "turn_on", eid)
    assert hass.states.get(eid).state == STATE_ON
    assert triggers() == 1
    freezer.tick(timedelta(seconds=8))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert triggers() == 2

    await call(hass, "switch", "turn_off", eid)
    assert hass.states.get(eid).state == STATE_OFF
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert triggers() == 2


async def test_hidden_animation(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """The charger's report of a played animation fires an event; unlocked ones are listed."""
    assert state(hass, "sensor", "unlocked_animations") == "1"
    assert attr(hass, "sensor", "unlocked_animations", "animations") == [
        {"type": 5, "unlocked": dt_util.utc_from_timestamp(1790737674).isoformat()}
    ]

    eid = entity_id(hass, "event", "hidden_animation")
    assert hass.states.get(eid).state == STATE_UNKNOWN
    cloud.mqtt.deliver({"easter_egg_type": 5})
    await hass.async_block_till_done()
    st = hass.states.get(eid)
    assert st.state != STATE_UNKNOWN  # time of the event
    assert st.attributes["event_type"] == "played"
    assert st.attributes["animation_type"] == 5


def test_hidden_animation_message_decoded() -> None:
    """Message 0305 field a2 (as captured: 05) is decoded as the animation type."""
    from functools import reduce
    from operator import xor

    from custom_components.anker_prime_charger import mqtt_extensions  # noqa: F401
    from custom_components.anker_prime_charger.solixapi.mqtttypes import DeviceHexData

    body = bytes.fromhex("a10164a2020105")
    length = 9 + len(body) + 1
    data = (
        b"\xff\x09" + length.to_bytes(2, "little") + bytes.fromhex("03010f0305") + body
    )
    data += bytes([reduce(xor, data, 0)])
    assert (
        DeviceHexData(model="A2345", hexbytes=data).values().get("easter_egg_type") == 5
    )
