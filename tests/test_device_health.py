"""The device on each USB-C port, port faults, overheating and firmware updates."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anker_prime_charger.identity import connected_device
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import FakeCloud
from .helpers import attr, device_id, entity_id, state


async def test_connected_device(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """The brand of the device on each USB-C port, on the port's device."""
    assert state(hass, "sensor", "usbc_1_connected_device") == "Apple"
    assert {
        name: attr(hass, "sensor", "usbc_1_connected_device", name)
        for name in ("vendor_id", "product_id", "brand_number", "model_number")
    } == {
        "vendor_id": "05AC",
        "product_id": "12A8",
        "brand_number": 1,
        "model_number": 7,
    }
    # not read yet; an unknown brand; no device
    assert state(hass, "sensor", "usbc_2_connected_device") == STATE_UNKNOWN
    assert state(hass, "sensor", "usbc_3_connected_device") == "VID 1234"
    assert state(hass, "sensor", "usbc_4_connected_device") == STATE_UNKNOWN
    assert attr(hass, "sensor", "usbc_4_connected_device", "vendor_id") is None

    registry = er.async_get(hass)
    sensor = registry.async_get(entity_id(hass, "sensor", "usbc_1_connected_device"))
    assert sensor.device_id == device_id(hass, "usbc_1")
    assert sensor.translation_key == "connected_device"
    # USB-A ports have no identity
    assert not registry.async_get_entity_id(
        "sensor", "anker_prime_charger", "ASHV911G00000001_usba_connected_device"
    )


async def test_connected_device_survives_library_cache(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """The library's cache update drops the identity values; the integration keeps them."""
    cloud.mqtt.deliver(
        {
            "usbc_2_device_vid": 0x04E8,
            "usbc_2_device_pid": 0x6860,
            "usbc_2_device_class": 0,
            "usbc_2_device_code": 0,
        }
    )
    await hass.async_block_till_done()
    # not one the charger recognises: the brand from the vendor id
    assert state(hass, "sensor", "usbc_2_connected_device") == "Samsung"
    assert attr(hass, "sensor", "usbc_2_connected_device", "brand_number") is None

    cloud.mqtt.deliver({"usbc_2_device_vid": 0xFFFA, "usbc_2_device_pid": 0xFFFB})
    await hass.async_block_till_done()
    assert state(hass, "sensor", "usbc_2_connected_device") == STATE_UNKNOWN


async def test_connected_device_unavailable_without_support(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """When the charger's ports can't read devices (2), the sensors are unavailable."""
    cloud.mqtt.deliver({"usbc_identity_support": 2})
    await hass.async_block_till_done()
    assert state(hass, "sensor", "usbc_1_connected_device") == STATE_UNAVAILABLE


def test_connected_device_needs_a_device() -> None:
    """Ids left from an unplugged device are not shown."""
    data = {
        "usbc_1_status": 0,
        "usbc_1_device_vid": 0x05AC,
        "usbc_1_device_pid": 0x12A8,
    }
    assert connected_device(data, "usbc_1") is None
    assert connected_device(data | {"usbc_1_status": 1}, "usbc_1") == {
        "name": "Apple",
        "vendor_id": "05AC",
        "product_id": "12A8",
        "brand_number": None,
        "model_number": None,
    }
    # the charger's brand number wins over the vendor id
    assert (
        connected_device(
            data | {"usbc_1_status": 1, "usbc_1_device_class": 10}, "usbc_1"
        )["name"]
        == "Anker"
    )
    assert connected_device({}, "usbc_1") is None


async def test_faults(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Port faults on the port devices, overheating on the charger's."""
    registry = er.async_get(hass)
    for port in ("usbc_1", "usbc_2", "usbc_3", "usbc_4", "usba"):
        eid = entity_id(hass, "binary_sensor", f"{port}_fault")
        assert hass.states.get(eid).state == STATE_OFF
        assert hass.states.get(eid).attributes["device_class"] == "problem"
        assert registry.async_get(eid).device_id == device_id(hass, port)
    eid = entity_id(hass, "binary_sensor", "over_temperature")
    assert hass.states.get(eid).state == STATE_OFF
    assert hass.states.get(eid).attributes["device_class"] == "heat"
    assert registry.async_get(eid).device_id == device_id(hass)

    cloud.mqtt.deliver({"usbc_3_fault": 1, "over_temperature": 1})
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor", "usbc_3_fault") == STATE_ON
    assert state(hass, "binary_sensor", "usbc_1_fault") == STATE_OFF
    assert state(hass, "binary_sensor", "over_temperature") == STATE_ON


async def test_firmware_update(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """A firmware update in progress, and how far it is."""
    assert state(hass, "binary_sensor", "ota_busy") == STATE_OFF
    assert state(hass, "sensor", "ota_progress") == "0"

    cloud.mqtt.deliver({"ota_busy": 1, "ota_progress": 42})
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor", "ota_busy") == STATE_ON
    assert state(hass, "sensor", "ota_progress") == "42"
    assert attr(hass, "sensor", "ota_progress", "unit_of_measurement") == "%"

    cloud.mqtt.deliver({"ota_busy": 0, "ota_progress": 100})
    await hass.async_block_till_done()
    assert state(hass, "binary_sensor", "ota_busy") == STATE_OFF
