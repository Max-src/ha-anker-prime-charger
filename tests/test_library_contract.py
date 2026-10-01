"""What the integration relies on in the vendored Anker library.

When the library is updated, these tests fail if something we depend on
changed. Each test says where it is used. Fix the integration (library.py,
mqtt_extensions.py, ...) before updating the expectations.
"""

from __future__ import annotations

import logging

from custom_components.anker_prime_charger import mqtt_extensions
from custom_components.anker_prime_charger.solixapi import mqttcmdmap
from custom_components.anker_prime_charger.solixapi.api import AnkerSolixApi
from custom_components.anker_prime_charger.solixapi.apitypes import (
    API_ENDPOINTS,
    API_SERVERS,
)
from custom_components.anker_prime_charger.solixapi.mqtt_charger import FEATURES
from custom_components.anker_prime_charger.solixapi.mqttmap import SOLIXMQTTMAP


def test_private_session_attributes() -> None:
    """library.create_api overrides the server through these attributes."""
    api = AnkerSolixApi("a@b.c", "x", "DE", None, logging.getLogger("test"))
    assert hasattr(api.apisession, "_api_base")
    assert hasattr(api.apisession, "_region")
    assert set(API_SERVERS) == {"eu", "com"}
    assert callable(api._update_account)  # library.store_stock_themes


def test_endpoints() -> None:
    """Library endpoint keys used by library.ENDPOINTS and the library helpers."""
    for key in (
        "charger_get_triggers",
        "charger_get_device_setting",
        "charger_get_charging_modes",
        "charger_get_port_remarks",
        "charger_set_port_remark",
        "charger_get_screensavers",
        "charger_get_manual_screensavers",
    ):
        assert key in API_ENDPOINTS


def test_a2345_commands() -> None:
    """Commands the entities send (by name) are known for the A2345."""
    model_map = SOLIXMQTTMAP["A2345"]
    names = {
        name
        for desc in model_map.values()
        for name in (
            desc.get(mqttcmdmap.COMMAND_NAME),
            *desc.get(mqttcmdmap.COMMAND_LIST, []),
        )
        if name
    }
    for command in (
        "status_request",
        "theme_request",
        "realtime_trigger",
        "charger_theme",
        "charger_theme_custom",
        "charger_usage_mode",
        "charger_custom_usage_mode",
        "display_brightness",
        "clock_display_schedule",
        "clock_holiday_switch",
        "usbc_1_port_switch",
        "usba_port_timer",
        "usba_start_time",
        mqtt_extensions.TIME_DISPLAY_COMMAND,  # added by mqtt_extensions
    ):
        assert command in names or command == "realtime_trigger", command
        assert command in FEATURES, command


def test_theme_kind_still_needs_our_correction() -> None:
    """mqtt_extensions corrects the theme kind; drop the correction once upstream fixes it.

    Upstream describes the kind as two flags (mask 0x06); we use the 3 bit
    number the app sends (mask 0x07).
    """
    theme_type = next(
        item
        for item in mqttcmdmap.CMD_CHARGER_THEME["a2"][mqttcmdmap.BYTES]["00"]
        if item.get(mqttcmdmap.NAME) == "set_theme_type"
    )
    assert theme_type[mqttcmdmap.MASK] == 0x06, (
        "upstream changed the theme kind: review mqtt_extensions"
    )


def test_unknown_values_still_dropped() -> None:
    """The coordinator keeps values the library's cache update drops (EXTRA_STATE_KEYS).

    If this fails, the library now keeps them and the workaround can go.
    """
    from types import SimpleNamespace

    api = AnkerSolixApi("a@b.c", "x", "DE", None, logging.getLogger("test"))
    sn = "SN1"
    api.devices[sn] = {"device_sn": sn, "device_pn": "A2345", "mqtt_data": {}}
    values = dict.fromkeys(mqtt_extensions.EXTRA_STATE_KEYS, 1)
    api.mqttsession = SimpleNamespace(
        mqtt_data={sn: values | {"last_message": "2026-01-01 00:00:00"}},
        mqtt_stats=SimpleNamespace(asdict=lambda: {"start_time": None}),
        is_connected=lambda: True,
        host="h",
        port=1,
    )
    api.update_device_mqtt(deviceSn=sn, values=values)
    assert not set(values) & set(api.devices[sn]["mqtt_data"])
