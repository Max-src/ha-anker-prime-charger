"""The bytes of every command the integration sends, as the charger accepts them.

tests/command_bytes.json holds each distinct command the test suite sends,
with the message the library built for it before its October 2026 update
(checked on a real charger; timestamps left out). When the library is
updated, a command it now builds differently fails here: check it on a
charger before changing the file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from custom_components.anker_prime_charger import mqtt_extensions
from custom_components.anker_prime_charger.solixapi.api import AnkerSolixApi
from custom_components.anker_prime_charger.solixapi.mqtt_charger import (
    SolixMqttDeviceCharger,
)
from custom_components.anker_prime_charger.solixapi.mqtttypes import DeviceHexData

from .conftest import DEVICE, SN

GOLDEN = json.loads((Path(__file__).parent / "command_bytes.json").read_text())
TIMESTAMPS = ("fd", "fe")


class _Publish:
    def wait_for_publish(self, timeout: float | None = None) -> None:
        return None

    def is_published(self) -> bool:
        return True


class _Session:
    """Records what the library publishes."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def is_connected(self) -> bool:
        return True

    def publish(
        self, deviceDict: dict, hexbytes: str, encoding_type: Any = None
    ) -> tuple[str, _Publish]:
        self.sent.append(hexbytes)
        return "", _Publish()


def _message(hexbytes: str) -> dict[str, Any]:
    msg = DeviceHexData(hexbytes=hexbytes)
    return {
        "type": msg.msg_header.msgtype.hex(),
        "fields": {
            name: (field.f_type + field.f_value).hex()
            for name, field in msg.msg_fields.items()
            if name not in TIMESTAMPS
        },
    }


@pytest.mark.parametrize(
    "case",
    GOLDEN["commands"],
    ids=[f"{i:02d}-{case['command']}" for i, case in enumerate(GOLDEN["commands"])],
)
async def test_command_bytes(case: dict[str, Any]) -> None:
    """The library builds the same message as before, for the same state."""
    status = GOLDEN["status"] | case.get("status", {})
    api = AnkerSolixApi("a@b.c", "x", "DE", None, logging.getLogger("test"))
    api.devices[SN] = dict(DEVICE) | {"mqtt_data": dict(status)}
    session = _Session()
    api.mqttsession = session  # type: ignore[assignment]
    device = SolixMqttDeviceCharger(api, SN)
    device.mqttdata = dict(status)

    await device.run_command(
        cmd=case["command"],
        value=case.get("value"),
        parm=case.get("parameter"),
        parm_map=case.get("parameters"),
    )
    assert [_message(sent) for sent in session.sent] == case["messages"]


def test_every_command_is_covered() -> None:
    """Each command the integration can send has bytes on file (port commands: one port)."""
    covered = {case["command"] for case in GOLDEN["commands"]}
    for family in ("_port_switch", "_port_timer", "_start_time", "_end_time"):
        assert any(command.endswith(family) for command in covered), family
    sent_by_the_integration = {
        "charger_custom_usage_mode",
        "charger_usage_mode",
        "clock_display_schedule",
        "clock_holiday_switch",
        "clock_mode_select",
        mqtt_extensions.TIME_DISPLAY_COMMAND,
        mqtt_extensions.COMPATIBILITY_COMMAND,
        mqtt_extensions.CUSTOM_MODE_COMMAND,
        mqtt_extensions.IDENTIFICATION_COMMAND,
        "display_brightness",
        "display_theme",
        "display_theme_custom",
        "display_timeout_mode_select",
        "knob_mode_select",
        "port_priority",
        "realtime_trigger",
        mqtt_extensions.TIMED_TRIGGER_COMMAND,
        "theme_request",
        mqtt_extensions.VERSION_REQUEST_COMMAND,
    }
    assert sent_by_the_integration <= covered
