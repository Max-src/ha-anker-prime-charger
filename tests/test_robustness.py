"""Polling, cloud refresh and fast updates under normal and failing conditions."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from .conftest import FakeCloud
from .helpers import attr, call, entity_id, state


async def poll(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int = 30
) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_theme_message_every_10_polls(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The theme message is asked for on the first poll, then every 10th."""
    for _ in range(10):
        cloud.mqtt.pending_reply = {"usbc_1_power": 1.0}  # keep the charger answering
        await poll(hass, freezer)
    types = cloud.mqtt.published_types
    assert types.count("0200") == 11
    assert types.count("0202") == 2  # polls 1 and 11


async def test_cloud_refresh_survives_an_unexpected_answer(
    hass: HomeAssistant,
    cloud: FakeCloud,
    entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A broken cloud answer is logged; the other settings are still read."""
    cloud.rest["charger_get_triggers"] = {"egg_trigger_list": 5}  # not a list
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        "Unexpected answer from the Anker cloud for the unlocked animations"
        in caplog.text
    )
    assert state(hass, "text", "port_label_c1") == "MacBook"  # read after it
    assert attr(hass, "text", "custom_usb_c1_protocols", "allowed")  # read after it


async def test_fast_updates_stop_by_themselves(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Fast updates stop after the duration in the options (default 10 min)."""
    eid = entity_id(hass, "switch", "fast_updates")
    await call(hass, "switch", "turn_on", eid)
    assert hass.states.get(eid).state == STATE_ON
    assert hass.states.get(eid).attributes["until"]

    for _ in range(19):  # 9.5 minutes, the charger answering every poll
        cloud.mqtt.pending_reply = {"usbc_1_power": 1.0}
        await poll(hass, freezer)
    assert hass.states.get(eid).state == STATE_ON
    cloud.mqtt.pending_reply = {"usbc_1_power": 1.0}
    await poll(hass, freezer)
    assert hass.states.get(eid).state == STATE_OFF
    triggers = cloud.mqtt.published_types.count("020b")
    cloud.mqtt.pending_reply = {"usbc_1_power": 1.0}
    await poll(hass, freezer)
    assert cloud.mqtt.published_types.count("020b") == triggers  # stopped


async def test_fast_updates_log_errors_once(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """While the trigger can't be sent, the problem is logged once, not every 8 s."""
    await call(hass, "switch", "turn_on", entity_id(hass, "switch", "fast_updates"))
    mdev = setup_entry.runtime_data.mqtt_device

    async def refuse(*args, **kwargs):
        return None

    mdev.realtime_trigger = refuse
    for _ in range(4):
        await poll(hass, freezer, 8)
    assert (
        caplog.text.count("Fast updates: the real-time trigger could not be sent") == 1
    )
