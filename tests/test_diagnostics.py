"""Diagnostics tests."""

from __future__ import annotations

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anker_prime_charger.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant

from .conftest import DEVICE, EMAIL, PASSWORD, SN, FakeCloud


async def test_diagnostics(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Diagnostics include decoded data but no personal information."""
    diag = await async_get_config_entry_diagnostics(hass, setup_entry)

    assert diag["mqtt"] == {
        "connected": True,
        "subscribed": True,
        "host": "mqtt.example.com",
    }
    assert diag["coordinator"]["last_update_success"] is True
    assert diag["coordinator"]["last_message"] is not None
    assert diag["mqtt_data"]["usbc_1_power"] == "6.3"
    assert diag["device"]["device_pn"] == "A2345"
    assert diag["coordinator"]["fast_updates_until"] is None
    assert diag["cloud"]["last_refresh"] is not None
    assert diag["cloud"]["protocol_ranges"]["c1"][0] == (15, 20, ["ufcs"])
    assert diag["cloud"]["unlocked_animations"][0]["egg_type"] == 5

    dumped = json.dumps(diag, default=str)
    for secret in (EMAIL, PASSWORD, SN, "250W Prime Charger"):
        assert secret not in dumped


async def test_diagnostics_other_account_devices(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """The account's other devices show their model and connection, nothing else."""
    cloud.devices = [
        dict(DEVICE),
        {
            "device_sn": "OTHER_SERIAL_123",
            "device_pn": "A2687",
            "type": "charger",
            "alias": "Desk charger",
            "name": "Prime Charger 160W",
            "wireless_type": "2",
            "mqtt_supported": False,
            "bt_ble_mac": "AABBCCDDEEFF",
        },
    ]
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["other_account_devices"] == [
        {
            "device_pn": "A2687",
            "type": "charger",
            "sw_version": None,
            "mqtt_supported": False,
            "wireless_type": "2",
            "wifi_online": None,
            "is_admin": None,
        }
    ]
    dumped = json.dumps(diag, default=str)
    for private in ("OTHER_SERIAL_123", "Desk charger", "AABBCCDDEEFF"):
        assert private not in dumped
