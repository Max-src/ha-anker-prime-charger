"""Firmware: versions from the charger (0830), the cloud's offer, an update running."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.anker_prime_charger.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .conftest import SN, USER_ID, FakeCloud
from .helpers import attr, entity_id, last_command_field, state


def _firmware(hass: HomeAssistant) -> str | None:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, SN), entry.entry_id
    )
    assert device
    return device.sw_version


async def test_versions_are_asked_for(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """The first poll asks for the versions, with the account's user id."""
    assert "0030" in cloud.mqtt.published_types
    index = cloud.mqtt.published_types.index("0030")
    cloud.mqtt.published.append(cloud.mqtt.published.pop(index))
    assert last_command_field(cloud, "a2") == "00" + USER_ID.encode().hex()


async def test_charger_firmware_follows_the_charger(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """The device's firmware and the update entity follow the charger's 0830."""
    assert _firmware(hass) == "2.1.1.6"  # from the cloud's device list
    assert state(hass, "update", "firmware") == STATE_OFF
    assert attr(hass, "update", "firmware", "installed_version") == "2.1.1.6"

    cloud.mqtt.deliver({"hw_version": "v0.2.9.7", "sw_version": "v2.1.2.0"}, "0830")
    await hass.async_block_till_done()
    assert _firmware(hass) == "2.1.2.0"
    assert attr(hass, "update", "firmware", "installed_version") == "2.1.2.0"
    assert attr(hass, "update", "firmware", "latest_version") == "2.1.2.0"


async def test_update_offered_and_installing(
    hass: HomeAssistant,
    cloud: FakeCloud,
    entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A newer firmware offered by the cloud; then installed by the charger."""
    info = cloud.rest["get_ota_batch"]["update_infos"][0]
    info["need_update"] = True
    info["lastPackage"]["version"] = "v2.2.0.1"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert state(hass, "update", "firmware") == STATE_ON
    assert attr(hass, "update", "firmware", "latest_version") == "2.2.0.1"
    assert attr(hass, "update", "firmware", "in_progress") is False

    cloud.mqtt.deliver({"ota_busy": 1, "ota_progress": 40})
    await hass.async_block_till_done()
    assert attr(hass, "update", "firmware", "in_progress") is True
    assert attr(hass, "update", "firmware", "update_percentage") == 40

    # done: the versions are asked for again at the next poll
    requests = cloud.mqtt.published_types.count("0030")
    cloud.mqtt.deliver({"ota_busy": 0, "ota_progress": 100})
    await hass.async_block_till_done()
    assert attr(hass, "update", "firmware", "in_progress") is False
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert cloud.mqtt.published_types.count("0030") == requests + 1


async def test_versions_asked_for_daily(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Not at every poll: once a day."""
    assert entity_id(hass, "update", "firmware")
    requests = cloud.mqtt.published_types.count("0030")
    for _ in range(3):
        freezer.tick(timedelta(seconds=30))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert cloud.mqtt.published_types.count("0030") == requests
