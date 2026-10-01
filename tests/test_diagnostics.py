"""Diagnostics tests."""

from __future__ import annotations

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anker_prime_charger.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant

from .conftest import EMAIL, PASSWORD, SN


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
