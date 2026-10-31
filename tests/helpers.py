"""Helpers shared by the tests."""

from __future__ import annotations

from typing import Any

from custom_components.anker_prime_charger.const import DOMAIN
from custom_components.anker_prime_charger.solixapi.mqtttypes import DeviceHexData
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import SN, FakeCloud


def entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    """Look up an entity id from its unique id ("<serial>_<key>")."""
    eid = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{SN}_{key}")
    assert eid, f"no {platform} entity for {key}"
    return eid


def device_id(hass: HomeAssistant, port: str | None = None) -> str:
    """Device id of the charger, or of one of its ports ("usbc_1" ... "usba")."""
    ident = SN if port is None else f"{SN}_{port}"
    entry_id = hass.config_entries.async_entries(DOMAIN)[0].entry_id
    devices = dr.async_get(hass)
    device = (
        devices.async_get_device_by_identifier((DOMAIN, ident), entry_id)
        if port is None
        else devices.async_get_child_device_by_identifier((DOMAIN, ident), entry_id)
    )
    assert device, f"no device {ident}"
    return device.id


async def act(hass: HomeAssistant, service: str, device: str, **data: Any) -> None:
    """Call one of the integration's actions on a device and wait for it."""
    await hass.services.async_call(
        DOMAIN, service, {ATTR_DEVICE_ID: device, **data}, blocking=True
    )


def state(hass: HomeAssistant, platform: str, key: str) -> str:
    """State of an entity, by unique id key."""
    return hass.states.get(entity_id(hass, platform, key)).state


def attr(hass: HomeAssistant, platform: str, key: str, name: str) -> Any:
    """State attribute of an entity, by unique id key."""
    return hass.states.get(entity_id(hass, platform, key)).attributes.get(name)


async def call(
    hass: HomeAssistant, domain: str, service: str, eid: str, **data: Any
) -> None:
    """Call an entity action and wait for it."""
    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: eid, **data}, blocking=True
    )


def last_command_field(cloud: FakeCloud, field: str) -> str:
    """Hex value (type byte + value) of a field ("a2", ...) of the last published command.

    Read with the library's own parser, which also reads 2 byte field lengths.
    """
    msg = DeviceHexData(hexbytes=cloud.mqtt.published[-1])
    assert field in msg.msg_fields, f"field {field} not in {msg.hexbytes.hex(':')}"
    data = msg.msg_fields[field]
    return (data.f_type + data.f_value).hex()
