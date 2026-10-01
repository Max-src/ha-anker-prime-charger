"""Clock screen, themes, custom profiles, port labels and test feature flags."""

from __future__ import annotations

from functools import reduce
from operator import xor

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anker_prime_charger.solixapi import errors
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .conftest import STOCK_THEME_URL, FakeCloud
from .helpers import attr, call, entity_id, last_command_field, state

WEEKDAYS_MON_FRI = ["mon", "tue", "wed", "thu", "fri"]


async def test_holiday_switch(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Holiday updates use their own command."""
    eid = entity_id(hass, "switch", "holiday_switch")
    assert hass.states.get(eid).state == STATE_ON
    await call(hass, "switch", "turn_off", eid)
    assert commands == [("clock_holiday_switch", "off", "set_holiday_switch")]
    assert hass.states.get(eid).state == STATE_OFF


async def test_clock_display_switch_keeps_theme_and_holiday(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Hiding the clock resends the current theme with holiday updates still on."""
    eid = entity_id(hass, "switch", "clock_switch")
    assert hass.states.get(eid).state == STATE_ON
    await call(hass, "switch", "turn_off", eid)
    assert commands == [
        (
            "charger_theme",
            {
                "set_clock_switch": "off",
                "set_holiday_switch": "on",
                "set_theme_id": 948897111,
                "set_theme_hash": 0x40914327,
                "set_theme_url": STOCK_THEME_URL,
                "set_theme_type": "stock",
            },
        )
    ]
    # flags byte: clock off (0x80 clear), holiday on (0x40), stock theme (kind 3)
    assert last_command_field(cloud, "a2") == "0143"
    assert hass.states.get(eid).state == STATE_OFF
    assert state(hass, "switch", "holiday_switch") == STATE_ON


async def test_time_display_switch(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Time display uses command 0222 (decoded from the app), a2: 0 off / 1 on."""
    eid = entity_id(hass, "switch", "time_display")
    assert hass.states.get(eid).state == STATE_ON

    await call(hass, "switch", "turn_off", eid)
    assert commands == [("time_display_switch", "off", "set_time_display")]
    assert cloud.mqtt.published_types[-1] == "0222"
    assert last_command_field(cloud, "a2") == "0100"
    assert hass.states.get(eid).state == STATE_OFF

    await call(hass, "switch", "turn_on", eid)
    assert last_command_field(cloud, "a2") == "0101"
    assert hass.states.get(eid).state == STATE_ON


async def test_time_display_survives_library_cache(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """The library's cache update drops time_display; the integration keeps it.

    Regression: the switch stayed unavailable on a real charger.
    """
    eid = entity_id(hass, "switch", "time_display")
    setup_entry.runtime_data.device["mqtt_data"].pop("time_display")
    cloud.mqtt.deliver({"theme_id": 47833, "time_display": 0})
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == STATE_OFF

    cloud.mqtt.deliver({"theme_id": 47833, "time_display": 1})
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == STATE_ON


def test_theme_message_time_display_decoded() -> None:
    """The charger's theme message 0a02 field a6 is decoded as time_display."""
    from custom_components.anker_prime_charger import mqtt_extensions  # noqa: F401
    from custom_components.anker_prime_charger.solixapi.mqtttypes import DeviceHexData

    # As captured: a2 flags c5, a3 theme id 47833, a4 04, a6 time display off
    body = bytes.fromhex("a10164a20201c5a30503d9ba0000a4020104a6020100")
    length = 9 + len(body) + 1  # header + fields + checksum
    data = (
        b"\xff\x09" + length.to_bytes(2, "little") + bytes.fromhex("03010f0a02") + body
    )
    data += bytes([reduce(xor, data, 0)])  # XOR checksum
    values = DeviceHexData(model="A2345", hexbytes=data).values()
    assert values.get("time_display") == 0
    assert values.get("theme_id") == 47833


async def test_clock_theme_select(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Built-in, stock and custom themes are offered; the stock preview is the picture."""
    eid = entity_id(hass, "select", "theme_id")
    st = hass.states.get(eid)
    assert st.state == "Futuristic - Celestial"
    assert st.attributes["options"] == [
        "Standard Style - Theme 1",
        "Standard Style - Theme 2",
        "Standard Style - Theme 3",
        "Cosmic - Lunar",
        "Futuristic - Celestial",
        "Custom - Fireworks",
        "Custom - Image 47833",  # unnamed in the app
    ]
    assert st.attributes["entity_picture"] == STOCK_THEME_URL

    await call(hass, "select", "select_option", eid, option="Custom - Fireworks")
    cmd, parm_map = commands[-1]
    assert cmd == "charger_theme_custom"
    assert parm_map["set_theme_id"] == 38820
    assert parm_map["set_theme_hash"] == 0x14EDD612
    assert parm_map["set_clock_switch"] == "on"
    assert parm_map["set_holiday_switch"] == "on"
    assert parm_map["set_theme_type"] == "custom"
    # flags byte: clock on, holiday on, custom image (kind 5), like the app
    assert last_command_field(cloud, "a2") == "01c5"
    st = hass.states.get(eid)
    assert st.state == "Custom - Fireworks"
    # signed custom image links expire, so no picture
    assert "entity_picture" not in st.attributes

    await call(hass, "select", "select_option", eid, option="Cosmic - Lunar")
    assert commands[-1][0] == "charger_theme"
    assert last_command_field(cloud, "a2") == "01c3"  # stock image (kind 3)
    assert state(hass, "select", "theme_id") == "Cosmic - Lunar"


async def test_standard_style_themes(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """The built-in Standard Styles are sent like the app does (kind 0-2, id 4, hash 0)."""
    eid = entity_id(hass, "select", "theme_id")
    await call(hass, "select", "select_option", eid, option="Standard Style - Theme 2")
    cmd, parm_map = commands[-1]
    assert cmd == "charger_theme"
    assert parm_map == {
        "set_clock_switch": "on",
        "set_holiday_switch": "on",
        "set_theme_type": "style_2",
        "set_theme_id": 4,
        "set_theme_hash": 0,
        "set_theme_url": "assets/img/a2345/icl_a2345_theme2.png",
    }
    assert last_command_field(cloud, "a2") == "01c1"  # kind 1 = Standard Style 2
    st = hass.states.get(eid)
    assert st.state == "Standard Style - Theme 2"
    assert "entity_picture" not in st.attributes  # app-internal image path

    # Detected from the charger's report, although it keeps the previous theme id
    cloud.mqtt.deliver({"clock_settings": 0xC0, "theme_id": 47833})
    await hass.async_block_till_done()
    assert state(hass, "select", "theme_id") == "Standard Style - Theme 1"
    cloud.mqtt.deliver({"clock_settings": 0xC5, "theme_id": 47833})
    await hass.async_block_till_done()
    assert state(hass, "select", "theme_id") == "Custom - Image 47833"


async def test_clock_theme_unavailable_without_cloud(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """Cloud REST errors are not fatal; only cloud-backed entities are unavailable."""
    for key in cloud.rest:
        cloud.rest[key] = errors.AnkerSolixError("cloud down")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Only the built-in Standard Styles are known; the stock theme in use isn't
    assert attr(hass, "select", "theme_id", "options") == [
        "Standard Style - Theme 1",
        "Standard Style - Theme 2",
        "Standard Style - Theme 3",
    ]
    assert state(hass, "select", "theme_id") == STATE_UNKNOWN
    assert state(hass, "text", "port_label_c1") == STATE_UNAVAILABLE
    assert state(hass, "switch", "compatibility_status") == STATE_UNAVAILABLE
    assert state(hass, "switch", "holiday_switch") == STATE_ON  # MQTT still works


async def test_custom_profiles_hidden_while_feature_off(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Without the custom charging mode feature, only the built-in modes are offered."""
    assert attr(hass, "select", "usage_mode", "options") == [
        "ai_power",
        "port_priority",
        "dual_laptop",
        "low_power",
    ]


async def test_custom_profile_select(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """With the feature on, each custom profile is an option and applies its ports."""
    cloud.rest["charger_get_device_setting"]["device_setting"][
        "charging_mode_status"
    ] = 1
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    eid = entity_id(hass, "select", "usage_mode")
    assert hass.states.get(eid).attributes["options"][-1] == "Custom: Desk"
    published = len(cloud.mqtt.published)

    await call(hass, "select", "select_option", eid, option="Custom: Desk")
    assert len(cloud.mqtt.published) == published + 1
    # profile number, auto exit, then C1..C4 and A power limits
    # 1, auto exit off, C1 100 W, C2 30 W, C3 0 W, C4 15 W, A 12 W
    assert last_command_field(cloud, "a3").endswith("0100641e000f0f")
    data = entry.runtime_data.data
    assert data["usage_mode"] == 5
    assert hass.states.get(eid).state == "Custom: Desk"

    await call(hass, "select", "select_option", eid, option="low_power")
    assert hass.states.get(eid).state == "low_power"


async def test_clock_display_schedule(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Start/end times and days are sent together, keeping the other values."""
    start = entity_id(hass, "time", "clock_display_start")
    assert hass.states.get(start).state == "07:00:00"
    assert state(hass, "time", "clock_display_end") == "22:30:00"
    days = entity_id(hass, "text", "clock_display_weekdays")
    assert hass.states.get(days).state == "mon,tue,wed,thu,fri"

    await call(hass, "time", "set_value", start, time="08:15:00")
    assert commands == [
        (
            "clock_display_schedule",
            {
                "set_clock_display_start_hour": 8,
                "set_clock_display_start_minute": 15,
                "set_clock_display_end_hour": 22,
                "set_clock_display_end_minute": 30,
                "set_clock_display_weekdays": WEEKDAYS_MON_FRI,
            },
        )
    ]
    assert hass.states.get(start).state == "08:15:00"

    await call(hass, "text", "set_value", days, value="sat, sun")
    assert commands[-1][1]["set_clock_display_weekdays"] == ["sat", "sun"]
    assert commands[-1][1]["set_clock_display_start_hour"] == 8
    assert hass.states.get(days).state == "sat,sun"

    await call(hass, "text", "set_value", days, value="all")
    assert hass.states.get(days).state == "mon,tue,wed,thu,fri,sat,sun"

    with pytest.raises((ServiceValidationError, ValueError)):
        await call(hass, "text", "set_value", days, value="funday")


async def test_port_labels(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Port labels come from and are saved to the Anker cloud."""
    assert state(hass, "text", "port_label_c1") == "MacBook"
    assert state(hass, "text", "port_label_c3") == ""
    eid = entity_id(hass, "text", "port_label_c3")
    await call(hass, "text", "set_value", eid, value="iPhone")
    assert (
        "charger_set_port_remark",
        {
            "device_sn": setup_entry.runtime_data.device_sn,
            "port_name": "C3",
            "remark": "iPhone",
        },
    ) in cloud.rest_requests
    assert hass.states.get(eid).state == "iPhone"


async def test_port_label_not_stored(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """A label the cloud accepts but does not store is reported, not shown as set."""
    cloud.ignore_port_labels = True
    eid = entity_id(hass, "text", "port_label_c1")
    with pytest.raises(HomeAssistantError, match="still reports MacBook"):
        await call(hass, "text", "set_value", eid, value="Work laptop")
    assert hass.states.get(eid).state == "MacBook"


async def test_test_feature_switches(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Test features are set in the Anker cloud and read back."""
    sn = setup_entry.runtime_data.device_sn
    assert state(hass, "switch", "compatibility_status") == STATE_ON
    assert state(hass, "switch", "charging_mode_status") == STATE_OFF
    eid = entity_id(hass, "switch", "charging_device_identity_status")
    assert hass.states.get(eid).state == STATE_OFF

    await call(hass, "switch", "turn_on", eid)
    assert (
        "mini_power/v1/app/setting/set_charging_device_identity_status",
        {"device_sn": sn, "charging_device_identity_status": 1},
    ) in cloud.rest_requests
    assert cloud.rest_requests[-1][0] == "charger_get_device_setting"  # read back
    assert hass.states.get(eid).state == STATE_ON

    await call(
        hass, "switch", "turn_off", entity_id(hass, "switch", "compatibility_status")
    )
    assert state(hass, "switch", "compatibility_status") == STATE_OFF


async def test_custom_mode_switch_unlocks_profiles(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Turning on Custom charging mode adds the custom profiles to Charging mode."""
    options = attr(hass, "select", "usage_mode", "options")
    assert "Custom: Desk" not in options
    await call(
        hass, "switch", "turn_on", entity_id(hass, "switch", "charging_mode_status")
    )
    assert attr(hass, "select", "usage_mode", "options")[-1] == "Custom: Desk"


async def test_test_feature_cloud_error(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """A cloud error shows in the UI and leaves the state unchanged."""
    cloud.rest["mini_power/v1/app/setting/set_compatibility_status"] = (
        errors.AnkerSolixError("cloud down")
    )
    eid = entity_id(hass, "switch", "compatibility_status")
    with pytest.raises(HomeAssistantError):
        await call(hass, "switch", "turn_off", eid)
    assert hass.states.get(eid).state == STATE_ON


async def test_port_power_limit_unchanged_sends_nothing(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Setting a port to its current limit sends nothing (it would disconnect devices)."""
    published = len(cloud.mqtt.published)
    eid = entity_id(hass, "number", "custom_usb_c2_power_limit")
    await call(hass, "number", "set_value", eid, value=30)
    assert commands == []
    assert len(cloud.mqtt.published) == published


async def test_port_power_limit(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """A port limit resends the charger's custom settings with that port changed."""
    eid = entity_id(hass, "number", "custom_usb_c2_power_limit")
    assert float(hass.states.get(eid).state) == 30
    assert attr(hass, "number", "custom_usb_c1_power_limit", "max") == 140

    await call(hass, "number", "set_value", eid, value=60)
    cmd, parm_map = commands[-1]
    assert cmd == "charger_custom_usage_mode"
    assert parm_map == {
        "set_custom_profile_number": 1,
        "set_auto_exit_switch": "off",
        "set_usb_c1_power_limit": 100,
        "set_usb_c2_power_limit": 60,
        "set_usb_c3_power_limit": 0,
        "set_usb_c4_power_limit": 15,
        "set_usb_a_power_limit": 15,
        "set_usb_c1_protocols": ["ufcs"],
        "set_usb_c2_protocols": [],
        "set_usb_c3_protocols": [],
        "set_usb_c4_protocols": ["ufcs"],
    }
    assert cloud.mqtt.published_types[-1] == "0206"
    # profile 1, auto exit off, then C1..C4 and A limits in W
    assert last_command_field(cloud, "a3").endswith("0100643c000f0f")
    assert float(hass.states.get(eid).state) == 60
    data = setup_entry.runtime_data.data
    assert data["usage_mode"] == 5  # switched to the custom charging mode


async def test_port_power_limit_total(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """The limits can't add up to more than the charger's 250 W."""
    eid = entity_id(hass, "number", "custom_usb_c3_power_limit")
    with pytest.raises(ServiceValidationError, match="250 W"):
        await call(hass, "number", "set_value", eid, value=100)  # 260 W in total
    assert commands == []


async def test_refresh_button_rereads_cloud(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Refresh also re-reads custom profiles, labels, themes and test features."""
    cloud.rest_requests.clear()
    await call(hass, "button", "press", entity_id(hass, "button", "refresh"))
    assert {key for key, _ in cloud.rest_requests} >= {
        "charger_get_charging_modes",
        "charger_get_device_setting",
        "charger_get_port_remarks",
        "charger_get_manual_screensavers",
    }


async def test_usb_c_limit_below_15w_refused(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """USB-C ports take 0 W or 15 W and more, like in the app."""
    eid = entity_id(hass, "number", "custom_usb_c2_power_limit")
    with pytest.raises(ServiceValidationError, match="0 W or 15-100 W"):
        await call(hass, "number", "set_value", eid, value=10)
    await call(hass, "number", "set_value", eid, value=0)
    assert commands[-1][1]["set_usb_c2_power_limit"] == 0


async def test_usb_a_power_limit_select(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Both USB-A ports together: 0, 15 or 24 W only."""
    eid = entity_id(hass, "select", "custom_usb_a_power_limit")
    st = hass.states.get(eid)
    assert st.state == "15"
    assert st.attributes["options"] == ["0", "15", "24"]
    await call(hass, "select", "select_option", eid, option="24")
    cmd, parm_map = commands[-1]
    assert cmd == "charger_custom_usage_mode"
    assert parm_map["set_usb_a_power_limit"] == 24
    assert parm_map["set_usb_c1_power_limit"] == 100  # others unchanged
    assert hass.states.get(eid).state == "24"


async def test_auto_deactivation_switch(
    hass: HomeAssistant, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Automatic deactivation is sent with the unchanged custom limits."""
    eid = entity_id(hass, "switch", "auto_exit_switch")
    assert hass.states.get(eid).state == STATE_OFF
    await call(hass, "switch", "turn_on", eid)
    cmd, parm_map = commands[-1]
    assert cmd == "charger_custom_usage_mode"
    assert parm_map["set_auto_exit_switch"] == "on"
    assert parm_map["set_usb_c2_power_limit"] == 30
    assert hass.states.get(eid).state == STATE_ON
    # Already on: nothing is sent (it would disconnect the devices)
    sent = len(commands)
    await call(hass, "switch", "turn_on", eid)
    assert len(commands) == sent
