"""What the integration relies on in the vendored Anker library.

When the library is updated, these tests fail if something we depend on
changed. Each test says where it is used. Fix the integration (library.py,
mqtt_extensions.py, ...) before updating the expectations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from paho.mqtt.client import MQTT_ERR_NO_CONN, MQTT_ERR_SUCCESS

from custom_components.anker_prime_charger import library, mqtt_extensions, themes
from custom_components.anker_prime_charger.solixapi import mqttcmdmap
from custom_components.anker_prime_charger.solixapi.api import AnkerSolixApi
from custom_components.anker_prime_charger.solixapi.apitypes import (
    API_ENDPOINTS,
    API_SERVERS,
)
from custom_components.anker_prime_charger.solixapi.mqtt import AnkerSolixMqttSession
from custom_components.anker_prime_charger.solixapi.mqtt_charger import FEATURES
from custom_components.anker_prime_charger.solixapi.mqttmap import SOLIXMQTTMAP
from custom_components.anker_prime_charger.solixapi.mqtttypes import DeviceHexData

from .conftest import DEVICE, SN


def _commands() -> dict[str, dict]:
    """The A2345's command descriptions by command name."""
    commands: dict[str, dict] = {}
    for desc in SOLIXMQTTMAP["A2345"].values():
        if name := desc.get(mqttcmdmap.COMMAND_NAME):
            commands[name] = desc
        for name in desc.get(mqttcmdmap.COMMAND_LIST, []):
            commands[name] = desc.get(name, desc)
    return commands


def _cache_update(keys: tuple[str, ...]) -> dict:
    """Run the library's cache update with these values; return what it kept."""
    api = AnkerSolixApi("a@b.c", "x", "DE", None, logging.getLogger("test"))
    sn = "SN1"
    api.devices[sn] = {"device_sn": sn, "device_pn": "A2345", "mqtt_data": {}}
    values = dict.fromkeys(keys, 1)
    api.mqttsession = SimpleNamespace(
        mqtt_data={sn: values | {"last_message": "2026-01-01 00:00:00"}},
        mqtt_stats=SimpleNamespace(asdict=lambda: {"start_time": None}),
        is_connected=lambda: True,
        host="h",
        port=1,
    )
    api.update_device_mqtt(deviceSn=sn, values=values)
    return api.devices[sn]["mqtt_data"]


def test_private_session_attributes() -> None:
    """library.create_api overrides the server through these attributes."""
    api = AnkerSolixApi("a@b.c", "x", "DE", None, logging.getLogger("test"))
    assert hasattr(api.apisession, "_api_base")
    assert hasattr(api.apisession, "_region")
    # library.create_api: the login cache's file; account_id: the user id
    assert api.apisession._authFile.endswith("a@b.c.json")
    api.apisession._login_response = {"user_id": "u1"}
    assert api.apisession.get_login_info("user_id") == "u1"
    assert set(API_SERVERS) == {"eu", "com"}
    assert callable(api._update_account)  # library.store_stock_themes


def test_subscribe_result() -> None:
    """coordinator.async_ensure_mqtt: once connected, paho's error code (0 on success)."""
    session = AnkerSolixMqttSession.__new__(AnkerSolixMqttSession)
    session.subscriptions, session.mids = set(), {}
    session.apisession = SimpleNamespace(nickname="test")
    session._logger = logging.getLogger("test")
    for code in (MQTT_ERR_SUCCESS, MQTT_ERR_NO_CONN):
        session.client = SimpleNamespace(
            is_connected=lambda: True, subscribe=lambda topic, code=code: (code, 7)
        )
        assert session.subscribe(f"topic{code}/#") == code
    # not connected yet: kept for when it connects
    session.client = None
    assert session.subscribe("later/#") is None
    assert "later/#" in session.subscriptions


def test_mqtt_session_attributes() -> None:
    """library.async_start_mqtt / async_stop_mqtt: certificate folder, paho client."""
    api = AnkerSolixApi("a@b.c", "x", "DE", None, logging.getLogger("test"))
    session = AnkerSolixMqttSession(apisession=api.apisession)
    assert isinstance(session._auth_cache_dir, Path)
    assert session.client is None
    assert callable(session.cleanup)


def test_versions_message_decoded() -> None:
    """mqtt_extensions' 0830: the versions (as the charger sends them, 2026-10)."""
    hexbytes = (
        "ff09280003000f0830a1090076302e322e392e37a2090076322e312e312e36"
        "a30600413233343505"
    )
    values = DeviceHexData(model="A2345", hexbytes=bytes.fromhex(hexbytes)).values()
    assert values == {"hw_version": "v0.2.9.7", "sw_version": "v2.1.1.6"}
    assert library.message_type(bytes.fromhex(hexbytes)) == "0830"
    # kept by the cache update, without the "v"
    kept = _cache_update(("sw_version",))
    assert "sw_version" in kept


async def test_ota_batch_stored() -> None:
    """update.py reads what get_ota_batch stores: is_ota_update, ota_version."""
    api = AnkerSolixApi("a@b.c", "x", "DE", None, logging.getLogger("test"))
    api._update_dev(dict(DEVICE))
    answer = {
        "update_infos": [
            {
                "device_sn": SN,
                "need_update": True,
                "lastPackage": {"version": "v2.2.0.1"},
                "current_version": "v2.1.1.6",
            }
        ]
    }

    async def request(method: str, endpoint: str, **kwargs: object) -> dict:
        assert endpoint == API_ENDPOINTS["get_ota_batch"]
        return {"code": 0, "data": answer}

    api.apisession.request = request  # type: ignore[method-assign]
    await api.get_ota_batch(deviceSns=[SN])
    assert api.devices[SN]["is_ota_update"] is True
    assert api.devices[SN]["ota_version"] == "2.2.0.1"


def test_wifi_charger_takes_commands() -> None:
    """The library sends no commands to a device without "wifi" in relate_type."""
    api = AnkerSolixApi("a@b.c", "x", "DE", None, logging.getLogger("test"))
    api._update_dev(dict(DEVICE))
    assert not api.devices[SN].get("is_passive")
    api._update_dev(DEVICE | {"relate_type": ["ble"]})
    assert api.devices[SN].get("is_passive")


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
    names = set(_commands())
    for command in (
        "status_request",
        "theme_request",
        "realtime_trigger",
        "display_theme",
        "display_theme_custom",
        "charger_usage_mode",
        "charger_custom_usage_mode",
        "display_brightness",
        "clock_display_schedule",
        "clock_holiday_switch",
        "usbc_1_port_switch",
        "usba_port_timer",
        "usba_start_time",
        mqtt_extensions.TIME_DISPLAY_COMMAND,
        mqtt_extensions.COMPATIBILITY_COMMAND,
        mqtt_extensions.IDENTIFICATION_COMMAND,
        mqtt_extensions.CUSTOM_MODE_COMMAND,  # added by mqtt_extensions
        mqtt_extensions.TIMED_TRIGGER_COMMAND,  # added by mqtt_extensions
        mqtt_extensions.VERSION_REQUEST_COMMAND,  # added by mqtt_extensions
    ):
        assert command in names or command == "realtime_trigger", command
        assert command in FEATURES, command


def test_switch_command_parameters() -> None:
    """The on/off commands of switch.py: their parameter, options and state."""
    commands = _commands()
    for command, parameter, options, reported in (
        (
            mqtt_extensions.TIME_DISPLAY_COMMAND,
            mqtt_extensions.TIME_DISPLAY_PARAMETER,
            {"off": 0, "on": 1},
            mqtt_extensions.TIME_DISPLAY_STATE,
        ),
        *(
            (
                command,
                parm,
                {"on": 0, "off": 1} if means_off else {"off": 0, "on": 1},
                st,
            )
            for command, parm, st, means_off in (
                mqtt_extensions.TEST_FEATURE_COMMANDS.values()
            )
        ),
    ):
        field = commands[command]["a2"]
        assert field[mqttcmdmap.NAME] == parameter, command
        assert field[mqttcmdmap.VALUE_OPTIONS] == options, command
        assert field[mqttcmdmap.STATE_NAME] == reported, command


def test_theme_kinds() -> None:
    """themes.py sends the library's theme kind options with these values (mask 0x07)."""
    theme_type = next(
        item
        for item in mqttcmdmap.CMD_DISPLAY_THEME["a2"][mqttcmdmap.BYTES]["00"]
        if item.get(mqttcmdmap.NAME) == "set_theme_type"
    )
    assert theme_type[mqttcmdmap.MASK] == themes.THEME_KIND_MASK
    assert theme_type[mqttcmdmap.VALUE_OPTIONS] == {
        option: value for value, option in themes.THEME_KINDS.values()
    }


def test_timer_step_still_needs_our_change() -> None:
    """mqtt_extensions allows whole minutes; drop that once the library does."""
    seconds = mqttcmdmap.CMD_PORT_TIMER["usbc_1"]["a3"][mqttcmdmap.BYTES]["01"]
    assert seconds[mqttcmdmap.VALUE_STEP] == 300, (
        "upstream changed the timer step: review mqtt_extensions.TIMER_STEP"
    )
    ours = _commands()["usbc_1_port_timer"]["a3"][mqttcmdmap.BYTES]["01"]
    assert ours[mqttcmdmap.VALUE_STEP] == mqtt_extensions.TIMER_STEP


def test_reported_values_kept() -> None:
    """Values the entities read from the library's cache are kept by its update."""
    keys = (
        mqtt_extensions.TIME_DISPLAY_STATE,
        mqtt_extensions.COMPATIBILITY_OFF_STATE,
        mqtt_extensions.IDENTIFICATION_STATE,
        "clock_settings",
        "over_temperature",
        "usbc_1_fault",
        "usba_fault",
        "ota_busy",
        "ota_progress",
        "ota_status",
    )
    assert set(keys) <= set(_cache_update(keys))


def test_unknown_values_still_dropped() -> None:
    """The coordinator keeps values the library's cache update drops (EXTRA_STATE_KEYS).

    If this fails, the library now keeps them and the workaround can go.
    """
    keys = mqtt_extensions.EXTRA_STATE_KEYS
    assert not set(keys) & set(_cache_update(keys))


def _message(msg_type: str, fields: dict[str, bytes]) -> str:
    """A charger message: these fields (each its type byte and value)."""
    body = bytes.fromhex("a10122")
    for field, data in fields.items():
        body += bytes.fromhex(field) + bytes([len(data)]) + data
    raw = (
        bytes.fromhex("ff09")
        + (len(body) + 10).to_bytes(2, "little")
        + bytes.fromhex("03010f" + msg_type)
        + body
    )
    checksum = 0
    for byte in raw:
        checksum ^= byte
    return (raw + bytes([checksum])).hex()


def test_theme_id_read_as_bin_or_var() -> None:
    """The charger sends the theme id as a bin field; mqtt_extensions describes it."""
    theme_id = (47843).to_bytes(4, "little")
    for msg_type, field in (("0a02", "a3"), ("0311", "a2")):
        for field_type in ("03", "04"):  # var, bin
            msg = _message(msg_type, {field: bytes.fromhex(field_type) + theme_id})
            values = DeviceHexData(model="A2345", hexbytes=msg).values()
            assert values["theme_id"] == 47843, (msg_type, field_type)
