"""Fixtures for the Anker Prime Charger 250W tests.

The real vendored Anker library is used (device model, command validation and
encoding). Only the network edges are faked: cloud login, the device list and
the MQTT connection. FakeMqttSession plays the charger: when a message is
published it can answer with a status update, like the real device does.
"""

from __future__ import annotations

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anker_prime_charger.const import (
    CONF_COUNTRY,
    CONF_DEVICE_SN,
    CONF_SERVER,
    DOMAIN,
    TEST_FEATURES,
)
from custom_components.anker_prime_charger.library import create_api as real_create_api
from custom_components.anker_prime_charger.solixapi.api import AnkerSolixApi
from custom_components.anker_prime_charger.solixapi.apitypes import API_ENDPOINTS
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

SN = "ASHV911G00000001"
EMAIL = "user@example.com"
PASSWORD = "secret-password"

DEVICE = {
    "device_sn": SN,
    "device_pn": "A2345",
    "type": "charger",
    "alias": "250W Prime Charger",
    "name": "Prime Charger 250W",
    "sw_version": "2.1.1.6",
    "is_admin": True,
    "mqtt_supported": True,
}

# Decoded status as the library stores it. Some values are strings on purpose:
# the library does not always convert to numbers.
STATUS = {
    "usbc_1_power": "6.3",
    "usbc_1_voltage": 9.0,
    "usbc_1_current": 0.7,
    "usbc_1_status": 1,
    "usbc_2_power": 1.5,
    "usbc_2_status": 1,
    "usbc_3_power": 0.5,
    "usbc_3_status": 1,
    "usbc_4_power": 0.0,
    "usbc_4_status": 0,
    "usba_1_power": 0.0,
    "usba_1_status": 0,
    "usba_2_power": 2.5,
    "usba_2_status": "1",
    "usbc_1_switch": 1,
    "usbc_2_switch": 1,
    "usbc_3_switch": 1,
    "usbc_4_switch": 1,
    "usba_switch": 1,
    "usbc_1_priority": 2,
    "usbc_2_priority": 1,
    "usbc_3_priority": 1,
    "usbc_4_priority": 1,
    "usage_mode": 2,
    "display_brightness": 100,
    "display_timeout_mode": 1,
    "knob_mode": 0,
    "clock_mode": 1,
    # clock screen: shown (0x80), holiday updates on (0x40), theme kind 3 =
    # stock image theme, here "Futuristic - Celestial" (as captured)
    "clock_settings": 0xC3,
    "clock_switch": 1,
    "holiday_switch": 1,
    "stock_theme_active": 1,
    "custom_theme_active": 0,
    "theme_id": 948897111,
    # shown 07:00-22:30, Monday to Friday (bitmask, bit 0 = Monday)
    "clock_display_start_hour": 7,
    "clock_display_start_minute": 0,
    "clock_display_end_hour": 22,
    "clock_display_end_minute": 30,
    "clock_display_weekdays": 0x1F,
    "custom_profile_number": 1,
    # the charger's current custom-mode settings (library keeps limits as str)
    "auto_exit_switch": 0,
    "custom_usb_c1_power_limit": "100",
    "custom_usb_c2_power_limit": "30",
    "custom_usb_c3_power_limit": "0",
    "custom_usb_c4_power_limit": "15",
    "custom_usb_a_power_limit": "15",
    "custom_usb_c1_protocols": ["ufcs"],
    "custom_usb_c2_protocols": [],
    "custom_usb_c3_protocols": [],
    "custom_usb_c4_protocols": ["ufcs"],
    # from the theme message 0a02 (named by mqtt_extensions.py)
    "time_display": 1,
}

# Port timers and schedules: all off, except a running 1 h timer on USB-C 1
# (30 min left when reported) and a weekday 07:30 start on USB-A.
TIMER_REPORTED = 1790740000  # when the remaining seconds were received
for _port in ("usbc_1", "usbc_2", "usbc_3", "usbc_4", "usba"):
    STATUS |= {
        f"{_port}_timer_switch": 0,
        f"{_port}_timer_seconds": 0,
        f"{_port}_timer_remaining_seconds": 0,
        f"{_port}_start_switch": 0,
        f"{_port}_start_hour": 0,
        f"{_port}_start_minute": 0,
        f"{_port}_start_weekdays": 0,
        f"{_port}_end_switch": 0,
        f"{_port}_end_hour": 0,
        f"{_port}_end_minute": 0,
        f"{_port}_end_weekdays": 0,
    }
STATUS |= {
    "usbc_1_timer_switch": 1,
    "usbc_1_timer_seconds": 3600,
    "usbc_1_timer_remaining_seconds": 1800,
    "usbc_1_timer_remaining_timestamp": TIMER_REPORTED,
    "usba_start_switch": 1,
    "usba_start_hour": 7,
    "usba_start_minute": 30,
    "usba_start_weekdays": 0x1F,  # Monday to Friday
}

STOCK_THEME_URL = "https://example.com/stock/celestial.jpg"


def _port_setting(name: str, power: int, max_power: int, **protocols: int) -> dict:
    """A port of a custom profile, as the cloud lists it."""
    return {
        "name": name,
        "power": power,
        "max_power": max_power,
        "input_power": 0,
        "input_max_power": 0,
    } | {
        p: protocols.get(p, 0)
        for p in (
            "scp",
            "ufcs",
            "pps11v",
            "pps16v",
            "pps20v",
            "pd12v",
            "huawei",
            "xiaomi",
        )
    }


# Anker cloud REST answers (only the "data" part), by endpoint key (or path)
CLOUD = {
    "charger_get_device_setting": {
        "device_setting": {
            "charging_mode_status": 0,
            "compatibility_status": 1,
            "antiloss_mode_status": 0,
            "temperature_mode_status": 0,
            "charging_device_identity_status": 0,
        }
    },
    # structure as the real cloud returns it (tools/probe_profiles.py)
    "charger_get_charging_modes": {
        "charging_mode_list": [
            {
                "id": 24581,
                "number": 1,
                "name": "Desk",
                "total_power": 160,
                "max_total_power": 250,
                "auto_exit": 0,
                "has_charge_protocol": 1,
                "power_settings": [
                    _port_setting("C1", 100, 140, ufcs=1),
                    _port_setting("C2", 30, 100),
                    _port_setting("C3", 0, 100),
                    _port_setting("C4", 15, 100),
                    _port_setting("A", 15, 24),
                ],
            },
        ]
    },
    # protocols per USB-C port and power, as the real cloud returns it
    "mini_power/v1/app/setting/get_power_range_support_protocols": {
        "port_list": [
            {
                "port": port,
                "power_range_protocols_mapping": [
                    {"min_power": 15, "max_power": 20, "protocols": ["UFCS"]},
                    {
                        "min_power": 21,
                        "max_power": 22,
                        "protocols": ["UFCS", "5-11V PPS", "PD 12V"],
                    },
                    {
                        "min_power": 23,
                        "max_power": 44,
                        "protocols": ["UFCS", "SCP", "5-11V PPS", "PD 12V"],
                    },
                    {
                        "min_power": 45,
                        "max_power": 140 if port == "C1" else 120,
                        "protocols": [
                            "UFCS",
                            "SCP",
                            "5-11V PPS",
                            "5-16V PPS",
                            "4.5-21V PPS",
                            "PD 12V",
                            "Support Xiaomi HyperCharge",
                        ],
                    },
                ],
            }
            for port in ("C1", "C2", "C3", "C4")
        ]
    },
    "charger_get_port_remarks": {
        "port_remarks": [
            {"port_name": "C1", "remark": "MacBook"},
            {"port_name": "C2", "remark": ""},
        ]
    },
    "charger_get_manual_screensavers": {
        "list": [
            {
                "id": 38820,
                "img_url": "https://example.com/custom/fw.jpg?X-Amz-Credential=SECRET",
                "short_url": "/custom/fw.jpg",
                "hash_code": "0x14edd612",
                "name": "Fireworks",
                "seq": 1,
            },
            # the app allows images without a name
            {
                "id": 47833,
                "img_url": "https://example.com/custom/x.jpg?X-Amz-Credential=SECRET",
                "short_url": "/custom/x.jpg",
                "hash_code": "0x2dad756f",
                "name": "",
                "seq": 2,
            },
        ],
        "total": 2,
    },
    # unlocked hidden animations, as on the real charger
    "charger_get_triggers": {
        "egg_trigger_list": [{"egg_type": 5, "trigger_time": 1790737674, "status": 1}]
    },
    "charger_get_screensavers": {
        "category": [
            {
                "id": "Futuristic",
                "category_name": "Futuristic",
                "list": [
                    {
                        "id": "948897111",
                        "title": "Celestial",
                        "image_url": STOCK_THEME_URL,
                        "file_crc32": "0x40914327",
                    },
                ],
            },
            {
                "id": "Cosmic",
                "category_name": "Cosmic",
                "list": [
                    {
                        "id": "938963984",
                        "title": "Lunar",
                        "image_url": "https://example.com/stock/lunar.jpg",
                        "file_crc32": "0xbd2ddca7",
                    },
                ],
            },
        ]
    },
}

ENTRY_DATA = {
    CONF_EMAIL: EMAIL,
    CONF_PASSWORD: PASSWORD,
    CONF_COUNTRY: "SG",
    CONF_DEVICE_SN: SN,
    CONF_SERVER: "com",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom_components in all tests."""


class FakeMqttSession:
    """Stands in for the library's AnkerSolixMqttSession and the charger."""

    def __init__(self, api: AnkerSolixApi) -> None:
        self.api = api
        self.host = "mqtt.example.com"
        self.port = 8883
        self.connected = True
        self.subscriptions: set[str] = set()
        self.published: list[str] = []
        # What the charger answers to the next published message (None = silent)
        self.pending_reply: dict[str, Any] | None = dict(STATUS)
        # Set like the real session, used by the library's cache update
        self.message_callback: Any = None
        self.mqtt_data: dict[str, dict[str, Any]] = {}
        self.mqtt_stats = MagicMock()
        self.mqtt_stats.asdict.side_effect = lambda: {"start_time": None}

    def deliver(self, values: dict[str, Any]) -> None:
        """Deliver decoded message values the way the real session does.

        Unlike pending_reply, this goes through the registered message callback
        and the library's own cache update (which drops keys it doesn't know).
        """
        self.mqtt_data[SN] = (
            (self.mqtt_data.get(SN) or {})
            | values
            | {"last_message": "2099-01-01 00:00:00"}
        )
        self.message_callback(self, "dt/x", {}, b"", "A2345", SN, values)

    @property
    def published_types(self) -> list[str]:
        """Message types ("0200" status request, ...) of the published commands."""
        return [
            (bytes(h) if isinstance(h, bytes | bytearray) else bytes.fromhex(h))[
                7:9
            ].hex()
            for h in self.published
        ]

    def is_connected(self) -> bool:
        return self.connected

    def get_topic_prefix(self, deviceDict: dict, publish: bool = False) -> str:
        return f"dt/anker_power/A2345/{deviceDict['device_sn']}/"

    def subscribe(self, topic: str) -> None:
        self.subscriptions.add(topic)

    def publish(self, deviceDict: dict, hexbytes: str, encoding_type: Any = None):
        self.published.append(hexbytes)
        if self.pending_reply is not None:
            reply, self.pending_reply = self.pending_reply, None
            self.api.devices[SN]["mqtt_data"].update(reply)
            self.api.mqtt_update_callback()(SN)
        info = MagicMock()
        info.is_published.return_value = True
        return {}, info

    def cleanup(self) -> None:
        self.connected = False


class FakeCloud:
    """Controls what the fake Anker cloud returns, per server."""

    def __init__(self) -> None:
        self.charger_servers: set[str] = {"eu", "com"}
        self.devices: list[dict[str, Any]] = [dict(DEVICE)]
        self.auth_error: Exception | None = None
        self.bind_error: Exception | None = None
        self.charger_silent = False
        self.account_country = "SG"
        self.apis: list[AnkerSolixApi] = []
        # REST answers by endpoint key; an exception value is raised instead
        self.rest: dict[str, Any] = copy.deepcopy(CLOUD)
        self.rest_requests: list[tuple[str, dict[str, Any]]] = []
        # Answer "success" to port label changes without storing them
        self.ignore_port_labels = False

    def rest_request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Answer a cloud REST request like the Anker server."""
        if endpoint in TEST_FEATURES.values():
            self.rest_requests.append((endpoint, payload))
            if isinstance(error := self.rest.get(endpoint), Exception):
                raise error
            settings = self.rest["charger_get_device_setting"]["device_setting"]
            settings.update({k: v for k, v in payload.items() if k in settings})
            return {"code": 0, "msg": "success!", "data": {}}
        key = next((k for k, v in API_ENDPOINTS.items() if v == endpoint), endpoint)
        self.rest_requests.append((key, payload))
        if key.endswith("_charging_mode"):
            profiles = self.rest["charger_get_charging_modes"]["charging_mode_list"]
        if key.endswith("/update_charging_mode"):
            stored = {k: v for k, v in payload.items() if k != "device_sn"}
            profiles[:] = [stored if p["id"] == payload["id"] else p for p in profiles]
            return {"code": 0, "msg": "success!", "data": {}}
        if key.endswith("/add_charging_mode"):
            stored = {k: v for k, v in payload.items() if k != "device_sn"}
            stored["id"] = max((p["id"] for p in profiles), default=30000) + 1
            profiles.append(stored)
            return {"code": 0, "msg": "success!", "data": copy.deepcopy(stored)}
        if key.endswith("/delete_charging_mode"):
            profiles[:] = [p for p in profiles if p["id"] != payload["id"]]
            return {"code": 0, "msg": "success!", "data": {}}
        if key == "charger_set_port_remark" and self.ignore_port_labels:
            return {"code": 0, "msg": "success!"}
        if key == "charger_set_port_remark":
            remarks = self.rest["charger_get_port_remarks"]["port_remarks"]
            remarks[:] = [r for r in remarks if r["port_name"] != payload["port_name"]]
            remarks.append(
                {"port_name": payload["port_name"], "remark": payload["remark"]}
            )
            return {"code": 0, "msg": "success!"}
        answer = self.rest[key]
        if isinstance(answer, Exception):
            raise answer
        return {"code": 0, "msg": "success!", "data": copy.deepcopy(answer)}

    @property
    def api(self) -> AnkerSolixApi:
        """The most recently created API client."""
        return self.apis[-1]

    @property
    def mqtt(self) -> FakeMqttSession:
        """The MQTT session of the most recent API client."""
        return self.api.mqttsession

    def create_api(
        self, hass: HomeAssistant, data: dict[str, Any], server: str | None = None
    ) -> AnkerSolixApi:
        # Real factory (country -> server mapping and override), fake network.
        api = real_create_api(hass, data, server)
        region = api.apisession.region

        async def authenticate(restart: bool = False) -> bool:
            if self.auth_error:
                raise self.auth_error
            api.apisession._login_response = {"country_code": self.account_country}
            return True

        async def get_bind_devices(fromFile: bool = False) -> dict:
            if self.bind_error:
                raise self.bind_error
            if region in self.charger_servers:
                for dev in self.devices:
                    api.devices[dev["device_sn"]] = dict(dev)
            return {}

        async def start_mqtt(*args: Any, **kwargs: Any) -> FakeMqttSession:
            api.mqttsession = FakeMqttSession(api)
            api.mqttsession.message_callback = (
                kwargs.get("message_callback") or api.mqtt_received
            )
            if self.charger_silent:
                api.mqttsession.pending_reply = None
            for dev in api.devices.values():
                dev.setdefault("mqtt_data", {})
            return api.mqttsession

        async def request(method: str, endpoint: str, **kwargs: Any) -> dict:
            return self.rest_request(endpoint, kwargs.get("json") or {})

        api.async_authenticate = authenticate
        api.apisession.request = request
        api.get_bind_devices = get_bind_devices
        api.startMqttSession = AsyncMock(side_effect=start_mqtt)
        self.apis.append(api)
        return api


@pytest.fixture
def cloud() -> Generator[FakeCloud]:
    """Patch the API factory used by setup and the config flow."""
    fake = FakeCloud()
    with (
        patch("custom_components.anker_prime_charger.create_api", fake.create_api),
        patch(
            "custom_components.anker_prime_charger.config_flow.create_api",
            fake.create_api,
        ),
        patch(
            "custom_components.anker_prime_charger.coordinator.FIRST_DATA_TIMEOUT", 0.1
        ),
    ):
        yield fake


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry for the charger."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="250W Prime Charger", unique_id=SN, data=dict(ENTRY_DATA)
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration with a charger that answers status requests."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def commands(setup_entry: MockConfigEntry) -> list[tuple]:
    """Record every command, still running the real one.

    Single-value commands as (command, value, parameter), multi-parameter
    commands as (command, parameter map).
    """
    mdev = setup_entry.runtime_data.mqtt_device
    sent: list[tuple] = []
    original = mdev.run_command

    async def spy(cmd, value=None, parm=None, parm_map=None, toFile=False):
        sent.append((cmd, value, parm) if not parm_map else (cmd, parm_map))
        return await original(
            cmd=cmd, value=value, parm=parm, parm_map=parm_map, toFile=toFile
        )

    mdev.run_command = spy
    return sent
