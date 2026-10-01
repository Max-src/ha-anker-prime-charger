"""Entity states and controls."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anker_prime_charger.const import DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import SN, FakeCloud
from .helpers import attr, entity_id, state


async def test_device_info(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """The device is registered with model and firmware."""
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, SN), setup_entry.entry_id
    )
    assert device.name == "250W Prime Charger"
    assert device.manufacturer == "Anker"
    assert device.model_id == "A2345"
    assert device.sw_version == "2.1.1.6"
    assert device.serial_number == SN


async def test_sensors(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Port power values (string or number) and their sum."""
    assert state(hass, "sensor", "usbc_1_power") == "6.3"
    assert state(hass, "sensor", "usba_2_power") == "2.5"
    assert state(hass, "sensor", "total_output_power") == "10.8"


async def test_all_entities_enabled_by_default(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """No entity is created disabled."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, setup_entry.entry_id)
    assert entries
    assert [e.entity_id for e in entries if e.disabled_by] == []


async def test_retired_entities_are_removed(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """Entities of earlier versions that no longer exist are removed at setup."""
    registry = er.async_get(hass)
    retired = registry.async_get_or_create(
        "switch", DOMAIN, f"{SN}_antiloss_mode_status", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(retired.entity_id) is None
    assert registry.async_get_entity_id("switch", DOMAIN, f"{SN}_compatibility_status")


async def test_port_devices(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Each port is a child device of the charger; port entities are on it."""
    devices = dr.async_get(hass)
    registry = er.async_get(hass)
    entry_id = setup_entry.entry_id
    charger = devices.async_get_device_by_identifier((DOMAIN, SN), entry_id)
    ports = {
        key: devices.async_get_child_device_by_identifier(
            (DOMAIN, f"{SN}_{key}"), entry_id
        )
        for key in ("usbc_1", "usbc_2", "usbc_3", "usbc_4", "usba")
    }
    assert [d.name for d in ports.values()] == [
        "250W Prime Charger USB-C 1",
        "250W Prime Charger USB-C 2",
        "250W Prime Charger USB-C 3",
        "250W Prime Charger USB-C 4",
        "250W Prime Charger USB-A",
    ]
    assert {d.parent_device_id for d in ports.values()} == {charger.id}

    def device_of(platform: str, key: str) -> str:
        return registry.async_get(entity_id(hass, platform, key)).device_id

    usb_a = ports["usba"].id
    assert device_of("sensor", "usba_1_power") == usb_a
    assert device_of("sensor", "usba_2_power") == usb_a
    assert device_of("switch", "usba_switch") == usb_a
    assert device_of("text", "port_label_a2") == usb_a
    assert device_of("number", "custom_usb_c3_power_limit") == ports["usbc_3"].id
    assert device_of("sensor", "total_output_power") == charger.id
    # The port's switch is named after its device; the rest after what they are
    assert (
        attr(hass, "switch", "usbc_1_switch", "friendly_name")
        == "250W Prime Charger USB-C 1"
    )
    assert (
        attr(hass, "sensor", "usba_2_power", "friendly_name")
        == "250W Prime Charger USB-A A2 power"
    )


async def test_port_devices_of_0_13_become_child_devices(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """Port devices that 0.13 created as separate devices become child devices, same id."""
    devices = dr.async_get(hass)
    charger = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, SN)}
    )
    old_port = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{SN}_usbc_1")},
        via_device_id=charger.id,
    )
    # As after a restart: these devices come from storage, not from this run
    devices.async_config_entry_unloaded(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    child = devices.async_get_child_device_by_identifier(
        (DOMAIN, f"{SN}_usbc_1"), entry.entry_id
    )
    assert child.id == old_port.id
    assert child.parent_device_id == charger.id
    registry = er.async_get(hass)
    assert (
        registry.async_get(entity_id(hass, "switch", "usbc_1_switch")).device_id
        == child.id
    )


async def test_port_connected(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Port status 1 means a device is connected."""
    assert state(hass, "binary_sensor", "usbc_1_status") == STATE_ON
    assert state(hass, "binary_sensor", "usba_2_status") == STATE_ON  # "1" string
    assert state(hass, "binary_sensor", "usbc_4_status") == STATE_OFF


async def test_switch(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Turning a port off sends the command and updates the state immediately."""
    eid = entity_id(hass, "switch", "usbc_1_switch")
    assert hass.states.get(eid).state == STATE_ON
    published = len(cloud.mqtt.published)

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: eid}, blocking=True
    )
    assert commands == [("usbc_1_port_switch", "off", "set_port_switch")]
    assert len(cloud.mqtt.published) == published + 1
    assert hass.states.get(eid).state == STATE_OFF

    eid = entity_id(hass, "switch", "usba_switch")
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: eid}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: eid}, blocking=True
    )
    assert commands[1:] == [
        ("usba_port_switch", "off", "set_port_switch"),
        ("usba_port_switch", "on", "set_port_switch"),
    ]
    assert hass.states.get(eid).state == STATE_ON


async def test_rejected_command_raises(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """A command the library refuses surfaces as an error in the UI."""
    mdev = setup_entry.runtime_data.mqtt_device

    async def refuse(**kwargs):
        return None

    mdev.run_command = refuse
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch",
            "turn_off",
            {ATTR_ENTITY_ID: entity_id(hass, "switch", "usbc_2_switch")},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("key", "initial", "option", "expected_cmd"),
    [
        (
            "usage_mode",
            "port_priority",
            "low_power",
            ("charger_usage_mode", "low_power", "set_usage_mode"),
        ),
        (
            "display_timeout_mode",
            "30s",
            "5min",
            ("display_timeout_mode_select", "300", "set_display_timeout_mode"),
        ),
    ],
)
async def test_selects(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    commands: list,
    key: str,
    initial: str,
    option: str,
    expected_cmd: tuple,
) -> None:
    """Selects show the device state and send the chosen option."""
    eid = entity_id(hass, "select", key)
    assert hass.states.get(eid).state == initial
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: eid, "option": option},
        blocking=True,
    )
    assert commands == [expected_cmd]
    assert hass.states.get(eid).state == option


async def test_usage_mode_custom_is_unknown(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Custom mode (5) shows as unknown while the custom mode feature is off."""
    cloud.mqtt.pending_reply = {"usage_mode": 5}
    await setup_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, "select", "usage_mode") == STATE_UNKNOWN


async def test_knob_and_clock_format(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Knob direction and clock format show the state and send commands."""
    assert state(hass, "select", "knob_mode") == "forward"
    assert state(hass, "select", "clock_mode") == "24h"

    for key, option in (("knob_mode", "backward"), ("clock_mode", "12h")):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: entity_id(hass, "select", key), "option": option},
            blocking=True,
        )
        assert state(hass, "select", key) == option
    assert commands == [
        ("knob_mode_select", "backward", "set_knob_mode"),
        ("clock_mode_select", "12h", "set_clock_mode"),
    ]


async def test_port_priority(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Priority is derived from per-port flags and set with a port bitmask."""
    eid = entity_id(hass, "select", "port_priority")
    assert hass.states.get(eid).state == "c1"  # only usbc_1_priority == 2

    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: eid, "option": "c3_c4"},
        blocking=True,
    )
    assert commands == [("port_priority", "c3_c4", "set_port_priority")]
    assert hass.states.get(eid).state == "c3_c4"
    data = setup_entry.runtime_data.data
    assert [data[f"usbc_{i}_priority"] for i in (1, 2, 3, 4)] == [1, 1, 2, 2]

    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: eid, "option": "off"}, blocking=True
    )
    assert hass.states.get(eid).state == "off"


async def test_display_brightness(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Brightness shows the device value and sends an integer percentage."""
    eid = entity_id(hass, "number", "display_brightness")
    assert hass.states.get(eid).state == "100"
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: eid, "value": 45}, blocking=True
    )
    assert commands == [("display_brightness", 45, "set_display_brightness")]
    assert float(hass.states.get(eid).state) == 45


async def test_refresh_button(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """The refresh button sends the status and theme requests and applies the answer."""
    cloud.mqtt.pending_reply = {"usbc_2_power": 20.0}
    published = len(cloud.mqtt.published)
    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: entity_id(hass, "button", "refresh")},
        blocking=True,
    )
    await hass.async_block_till_done()
    # (the theme message is only asked for every 10 polls)
    assert cloud.mqtt.published_types[published:] == ["0200"]
    assert state(hass, "sensor", "usbc_2_power") == "20.0"


async def test_every_entity_has_a_name(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Every translation key resolves to a name (only port switches use the device's)."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, setup_entry.entry_id)
    unnamed = [
        e.entity_id
        for e in entries
        if e.original_name is None
        and not e.unique_id.endswith(
            (
                "usbc_1_switch",
                "usbc_2_switch",
                "usbc_3_switch",
                "usbc_4_switch",
                "usba_switch",
            )
        )
    ]
    assert unnamed == []
