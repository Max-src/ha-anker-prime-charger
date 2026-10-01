"""Saving custom charging profiles in the Anker cloud."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anker_prime_charger.const import DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .conftest import FakeCloud
from .helpers import entity_id

UPDATE = "mini_power/v1/app/charging/update_charging_mode"


async def save(hass: HomeAssistant, **data: Any) -> None:
    await hass.services.async_call(
        DOMAIN,
        "save_custom_profile",
        {ATTR_ENTITY_ID: entity_id(hass, "select", "usage_mode"), **data},
        blocking=True,
    )


def updates(cloud: FakeCloud) -> list[dict[str, Any]]:
    return [payload for key, payload in cloud.rest_requests if key == UPDATE]


def port(profile: dict[str, Any], name: str) -> dict[str, Any]:
    return next(p for p in profile["power_settings"] if p["name"] == name)


async def test_save_profile(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """The profile is sent back as listed, with the changes and the serial."""
    await save(
        hass,
        profile="desk",
        new_name="Office",
        c2_power=45,
        c2_protocols=["ufcs", "scp"],
    )
    [body] = updates(cloud)
    assert body["device_sn"] == setup_entry.runtime_data.device_sn
    assert (body["id"], body["number"], body["name"]) == (24581, 1, "Office")
    assert body["total_power"] == 100 + 45 + 0 + 15 + 15
    assert body["max_total_power"] == 250  # untouched fields kept
    c2 = port(body, "C2")
    assert (c2["power"], c2["max_power"]) == (45, 100)
    assert {
        k
        for k in ("scp", "ufcs", "pps11v", "pps16v", "pps20v", "pd12v", "xiaomi")
        if c2[k]
    } == {
        "scp",
        "ufcs",
    }
    assert port(body, "C1")["ufcs"] == 1  # other ports unchanged
    # The profile list is re-read from the cloud
    names = [
        p["name"] for p in setup_entry.runtime_data.device["custom_modes"].values()
    ]
    assert names == ["Office"]


async def test_save_profile_from_charger(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """from_charger starts from the charger's current custom settings."""
    setup_entry.runtime_data.data["custom_usb_c3_power_limit"] = "25"
    await save(hass, profile="Desk", from_charger=True, auto_deactivation=True)
    [body] = updates(cloud)
    assert port(body, "C3")["power"] == 25
    assert body["auto_exit"] == 1
    assert body["name"] == "Desk"


async def test_save_profile_checks(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Unknown profiles and values the charger doesn't allow are refused."""
    with pytest.raises(ServiceValidationError, match="profiles: Desk"):
        await save(hass, profile="Gaming")
    with pytest.raises(ServiceValidationError, match="0 W or 15-100 W"):
        await save(hass, profile="Desk", c2_power=10)
    with pytest.raises(ServiceValidationError, match="20 W doesn't allow scp"):
        await save(hass, profile="Desk", c2_power=20, c2_protocols=["scp"])
    with pytest.raises(ServiceValidationError, match="0, 15 or 24 W"):
        await save(hass, profile="Desk", a_power=20)
    assert updates(cloud) == []


async def call_profile_action(hass: HomeAssistant, action: str, **data: Any) -> None:
    await hass.services.async_call(
        DOMAIN,
        action,
        {ATTR_ENTITY_ID: entity_id(hass, "select", "usage_mode"), **data},
        blocking=True,
    )


def requests(cloud: FakeCloud, name: str) -> list[dict[str, Any]]:
    return [
        p
        for key, p in cloud.rest_requests
        if key == f"mini_power/v1/app/charging/{name}"
    ]


async def test_create_profile(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """A new profile gets the next free number and the charger's settings plus changes."""
    await call_profile_action(
        hass,
        "create_custom_profile",
        name="Travel",
        c1_power=65,
        c1_protocols=["ufcs", "pps20v"],
    )
    [body] = requests(cloud, "add_charging_mode")
    assert "id" not in body
    assert (body["number"], body["name"], body["device_sn"]) == (
        2,
        "Travel",
        setup_entry.runtime_data.device_sn,
    )
    assert (body["max_total_power"], body["has_charge_protocol"]) == (250, 1)
    assert [
        (p["name"], p["power"], p["max_power"]) for p in body["power_settings"]
    ] == [
        ("C1", 65, 140),
        ("C2", 30, 100),
        ("C3", 0, 100),
        ("C4", 15, 100),
        ("A", 15, 24),
    ]
    c1 = port(body, "C1")
    assert (c1["ufcs"], c1["pps20v"], c1["scp"]) == (1, 1, 0)
    assert body["total_power"] == 65 + 30 + 0 + 15 + 15
    names = sorted(
        p["name"] for p in setup_entry.runtime_data.device["custom_modes"].values()
    )
    assert names == ["Desk", "Travel"]


async def test_create_profile_limits(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Names must be new, and the charger holds at most 4 profiles."""
    with pytest.raises(ServiceValidationError, match="already exists"):
        await call_profile_action(hass, "create_custom_profile", name="desk")
    for name in ("Two", "Three", "Four"):
        await call_profile_action(hass, "create_custom_profile", name=name)
    with pytest.raises(ServiceValidationError, match="at most 4"):
        await call_profile_action(hass, "create_custom_profile", name="Five")
    assert [b["number"] for b in requests(cloud, "add_charging_mode")] == [2, 3, 4]


async def test_delete_profile(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Deleting sends the profile id; the last one also disappears from the cache."""
    await call_profile_action(hass, "delete_custom_profile", profile="Desk")
    assert requests(cloud, "delete_charging_mode") == [{"id": 24581}]
    assert setup_entry.runtime_data.device["custom_modes"] == {}
    with pytest.raises(ServiceValidationError, match="No custom profile named 'Desk'"):
        await call_profile_action(hass, "delete_custom_profile", profile="Desk")


async def test_actions_exist_without_a_charger(hass: HomeAssistant) -> None:
    """The actions are registered when the integration loads, before any charger."""
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, DOMAIN, {})
    for action in (
        "save_custom_profile",
        "create_custom_profile",
        "delete_custom_profile",
    ):
        assert hass.services.has_service(DOMAIN, action)


async def test_actions_need_the_charging_mode_entity(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Targeting another of the charger's selects is refused with a clear message."""
    with pytest.raises(ServiceValidationError, match="Charging mode"):
        await hass.services.async_call(
            DOMAIN,
            "delete_custom_profile",
            {ATTR_ENTITY_ID: entity_id(hass, "select", "knob_mode"), "profile": "Desk"},
            blocking=True,
        )
