"""A2345 messages and commands the vendored library does not know (or gets wrong).

Decoded by watching the Anker app's MQTT messages. They are added
to the library's model map at runtime, so the vendored files stay unchanged.

- Time display (show the time on top of a custom clock image; stock themes
  always show it): command 0222, field a2: 0 off, 1 on. The app sends it
  when "time display" is toggled on a custom image. The charger reports it in
  the theme message 0a02, field a6, which the library calls "unknown_0a02_a6".
- Theme kind: the low 3 bits of the clock flag byte (theme command 0205 field
  a2, status 0a00 af byte 0 "clock_settings", theme message 0a02 a2) are a
  number, not two flags as the library assumes (stock 0x02, custom 0x04):
  0, 1, 2 = the built-in "Standard Style" themes 1-3, 3 = a stock image
  theme, 5 = a custom image. The app sends exactly these values.
- Port timer duration (command 0209, field a3 bytes 01, in seconds): the
  library rounds it to the app's 5 minute steps, but the charger also takes
  whole minutes (TIMER_STEP; a 1 minute timer works).
- Hidden ("easter egg") animations: the charger reports each one it plays in
  message 0305, field a2 = animation type (e.g. 5 after unplugging a port 10
  times within 60 s). There is no command to play one.
- The app's test features (captured 2026-10-22, docs/PROTOCOL.md): the
  charger holds two of them, which a change of the cloud flag alone doesn't
  reach. Maximum compatibility: command 0214, field a2: 0 on, 1 off; reported
  in 0a00 field bb (0 on, 1 off). Charging device identification: command
  0223, field a2: 1 on, 0 off; reported in 0a00 field bf. Custom charging
  mode is turned on in the cloud only; turning it off also sends 0211, a2 0.

Tried and dropped: display brightness below the app's 20 % (the charger
accepts the command but the screen doesn't get darker).
"""

from __future__ import annotations

from typing import Any, Final

from .const import MODEL
from .solixapi.apitypes import DeviceHexDataTypes
from .solixapi.mqtt_charger import FEATURES, MODELS
from .solixapi.mqttcmdmap import (
    BYTES,
    CMD_COMMON,
    COMMAND_NAME,
    MASK,
    NAME,
    STATE_NAME,
    TYPE,
    VALUE_DEFAULT,
    VALUE_OPTIONS,
    VALUE_STEP,
    SolixMqttCommands,
)
from .solixapi.mqttmap import SOLIXMQTTMAP

TIME_DISPLAY_COMMAND: Final = "time_display_switch"
TIME_DISPLAY_STATE: Final = "time_display"

# Test features held by the charger (cloud flag key -> command and state)
COMPATIBILITY_COMMAND: Final = "compatibility_switch"
COMPATIBILITY_OFF_STATE: Final = "compatibility_off"  # 0 on, 1 off
IDENTIFICATION_COMMAND: Final = "device_identification_switch"
IDENTIFICATION_STATE: Final = "device_identification"
CUSTOM_MODE_COMMAND: Final = "custom_charging_mode_switch"
CUSTOM_MODE_PARAMETER: Final = "set_custom_charging_mode"
# cloud flag -> (command, its parameter, reported state, whether the state's 1 means off)
TEST_FEATURE_COMMANDS: Final = {
    "compatibility_status": (
        COMPATIBILITY_COMMAND,
        "set_compatibility",
        COMPATIBILITY_OFF_STATE,
        True,
    ),
    "charging_device_identity_status": (
        IDENTIFICATION_COMMAND,
        "set_device_identification",
        IDENTIFICATION_STATE,
        False,
    ),
}

# Decoded values the library's cache update drops because it doesn't know
# them; the coordinator stores these itself (see _async_mqtt_message).
EXTRA_STATE_KEYS: Final = (
    TIME_DISPLAY_STATE,
    COMPATIBILITY_OFF_STATE,
    IDENTIFICATION_STATE,
)

EASTER_EGG_STATE: Final = "easter_egg_type"

# Theme kind: value of the low 3 bits of the clock flag byte
THEME_KIND_MASK: Final = 0x07
THEME_KINDS: Final = {"style_1": 0, "style_2": 1, "style_3": 2, "stock": 3, "custom": 5}

# Port timer duration step (seconds), instead of the library's 300
TIMER_STEP: Final = 60


def _theme_kind_field(field: dict[str, Any], default: int) -> dict[str, Any]:
    """Copy of a theme command's a2 field with the theme kind as a 3 bit number."""
    bits = [
        item
        | {MASK: THEME_KIND_MASK, VALUE_OPTIONS: THEME_KINDS, VALUE_DEFAULT: default}
        if item.get(NAME) == "set_theme_type"
        else item
        for item in field[BYTES]["00"]
    ]
    return field | {BYTES: field[BYTES] | {"00": bits}}


def _switch_command(
    command: str, parameter: str, options: dict[str, int], state: str | None
) -> dict[str, Any]:
    """An on/off command with one field (a2), and the state it changes."""
    field: dict[str, Any] = {
        NAME: parameter,
        TYPE: DeviceHexDataTypes.ui.value,
        VALUE_OPTIONS: options,
    }
    if state:
        field[STATE_NAME] = state
    return CMD_COMMON | {COMMAND_NAME: command, "a2": field}


def _extend_model_map() -> None:
    model_map = SOLIXMQTTMAP[MODEL]
    # The test features (the state fields are named in 0a00 below); the
    # compatibility state is 1 when off, as the command's value
    for code, command, parameter, options, state in (
        ("0211", CUSTOM_MODE_COMMAND, CUSTOM_MODE_PARAMETER, {"off": 0, "on": 1}, None),
        (
            "0214",
            COMPATIBILITY_COMMAND,
            "set_compatibility",
            {"on": 0, "off": 1},
            COMPATIBILITY_OFF_STATE,
        ),
        (
            "0223",
            IDENTIFICATION_COMMAND,
            "set_device_identification",
            {"off": 0, "on": 1},
            IDENTIFICATION_STATE,
        ),
    ):
        model_map.setdefault(code, _switch_command(command, parameter, options, state))
        FEATURES.setdefault(command, MODELS)
    status = model_map.get("0a00", {})
    status.setdefault("bb", {NAME: COMPATIBILITY_OFF_STATE})
    status.setdefault("bf", {NAME: IDENTIFICATION_STATE})
    model_map.setdefault(
        "0222",
        CMD_COMMON
        | {
            COMMAND_NAME: TIME_DISPLAY_COMMAND,
            "a2": {
                NAME: "set_time_display",
                TYPE: DeviceHexDataTypes.ui.value,
                VALUE_OPTIONS: {"off": 0, "on": 1},
                STATE_NAME: TIME_DISPLAY_STATE,
            },
        },
    )
    theme_message = model_map.get("0a02", {})
    if theme_message.get("a6", {}).get(NAME, "").startswith("unknown"):
        theme_message["a6"] = {NAME: TIME_DISPLAY_STATE}
    model_map.setdefault("0305", {"a2": {NAME: EASTER_EGG_STATE}})
    # Commands must also be listed as a charger feature to be accepted
    FEATURES.setdefault(TIME_DISPLAY_COMMAND, MODELS)

    # Theme kind as the app sends it; the shared descriptions are copied
    theme_cmds = model_map["0205"]
    for cmd, default in (
        (SolixMqttCommands.charger_theme, THEME_KINDS["stock"]),
        (SolixMqttCommands.charger_theme_custom, THEME_KINDS["custom"]),
    ):
        theme_cmds[cmd] = theme_cmds[cmd] | {
            "a2": _theme_kind_field(theme_cmds[cmd]["a2"], default)
        }

    # Timer duration step; the shared descriptions are copied
    timer_cmds = model_map["0209"]
    for cmd in (
        SolixMqttCommands.usbc_1_port_timer,
        SolixMqttCommands.usbc_2_port_timer,
        SolixMqttCommands.usbc_3_port_timer,
        SolixMqttCommands.usbc_4_port_timer,
        SolixMqttCommands.usba_port_timer,
    ):
        field = timer_cmds[cmd]["a3"]
        seconds = field[BYTES]["01"] | {VALUE_STEP: TIMER_STEP}
        timer_cmds[cmd] = timer_cmds[cmd] | {
            "a3": field | {BYTES: field[BYTES] | {"01": seconds}}
        }


_extend_model_map()
