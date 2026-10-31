"""A2345 messages and commands the vendored library does not know (or limits).

Decoded by watching the Anker app's MQTT messages. They are added
to the library's model map at runtime, so the vendored files stay unchanged.

- Port timer duration (command 0209, field a3 bytes 01, in seconds): the
  library rounds it to the app's 5 minute steps, but the charger also takes
  whole minutes (TIMER_STEP; a 1 minute timer works).
- Hidden ("easter egg") animations: the charger reports each one it plays in
  message 0305, field a2 = animation type (e.g. 5 after unplugging a port 10
  times within 60 s). There is no command to play one.
- Custom image theme (command 0205, field a7, the image's link): sent
  without a length byte, as the app does and as the library describes the
  stock theme's link (a6). The library's custom theme command doesn't say so,
  and its encoder then adds one, which fails on the long signed links.
- Theme id (theme message 0a02 a3, message 0311 a2): the charger sends it
  as a bin field (type 04), and the library decodes a bin field's bytes only
  where they are described. Described as byte 00 of the field, it is read
  either way (the theme otherwise showed as unknown until the next status).
- Custom charging mode (one of the app's test features, captured 2026-10-22,
  docs/PROTOCOL.md) is turned on in the cloud only; turning it off also sends
  0211, a2 0.

The library knows the rest the integration uses for the A2345, since its
late October 2026 update: the time display (command 0222, reported in 0a02
a6), the theme kind as a 3 bit number (see themes.py) and the two test
features the charger holds, maximum compatibility (0214, reported in 0a00 bb:
0 on, 1 off) and charging device identification (0223, reported in 0a00 bf).
Their names are below.

Tried and dropped: display brightness below the app's 20 % (the charger
accepts the command but the screen doesn't get darker).
"""

from __future__ import annotations

from typing import Final

from .const import MODEL
from .ports import USB_C_PORTS
from .solixapi.apitypes import DeviceHexDataTypes
from .solixapi.mqtt_charger import FEATURES, MODELS
from .solixapi.mqttcmdmap import (
    BYTES,
    CMD_COMMON,
    COMMAND_NAME,
    LENGTH,
    NAME,
    TYPE,
    VALUE_OPTIONS,
    VALUE_STEP,
    SolixMqttCommands,
)
from .solixapi.mqttmap import SOLIXMQTTMAP

# The library's names (command, its parameter, the reported state)
TIME_DISPLAY_COMMAND: Final = SolixMqttCommands.clock_time_switch
TIME_DISPLAY_PARAMETER: Final = "set_clock_time_switch"
TIME_DISPLAY_STATE: Final = "clock_time_switch"

# Test features held by the charger (library names)
COMPATIBILITY_COMMAND: Final = SolixMqttCommands.compatibility_switch
COMPATIBILITY_OFF_STATE: Final = "compatibility_switch"  # 0 on, 1 off
IDENTIFICATION_COMMAND: Final = SolixMqttCommands.device_id_switch
IDENTIFICATION_STATE: Final = "device_id_switch"
CUSTOM_MODE_COMMAND: Final = "custom_charging_mode_switch"
CUSTOM_MODE_PARAMETER: Final = "set_custom_charging_mode"
# cloud flag -> (command, its parameter, reported state, whether the state's 1 means off)
TEST_FEATURE_COMMANDS: Final = {
    "compatibility_status": (
        COMPATIBILITY_COMMAND,
        "set_compatibility_switch",
        COMPATIBILITY_OFF_STATE,
        True,
    ),
    "charging_device_identity_status": (
        IDENTIFICATION_COMMAND,
        "set_device_id_switch",
        IDENTIFICATION_STATE,
        False,
    ),
}

EASTER_EGG_STATE: Final = "easter_egg_type"

# Decoded values the library's cache update drops (its key filter doesn't
# know them); the coordinator stores these itself (see _async_mqtt_message):
# the device on each USB-C port (USB-PD vendor and product id, brand and
# model numbers; status 0a00 bd/be, live values 0303 a8/a9) and whether the
# charger can read them.
IDENTITY_SUPPORT_STATE: Final = "usbc_identity_support"
DEVICE_ID_PARTS: Final = ("vid", "pid", "class", "code")
EXTRA_STATE_KEYS: Final = (
    IDENTITY_SUPPORT_STATE,
    *(f"{port.key}_device_{part}" for port in USB_C_PORTS for part in DEVICE_ID_PARTS),
)

# Port timer duration step (seconds), instead of the library's 300
TIMER_STEP: Final = 60


def _extend_model_map() -> None:
    model_map = SOLIXMQTTMAP[MODEL]
    # Turning the custom charging mode test feature off
    model_map.setdefault(
        "0211",
        CMD_COMMON
        | {
            COMMAND_NAME: CUSTOM_MODE_COMMAND,
            "a2": {
                NAME: CUSTOM_MODE_PARAMETER,
                TYPE: DeviceHexDataTypes.ui.value,
                VALUE_OPTIONS: {"off": 0, "on": 1},
            },
        },
    )
    # Commands must also be listed as a charger feature to be accepted
    FEATURES.setdefault(CUSTOM_MODE_COMMAND, MODELS)
    model_map.setdefault("0305", {"a2": {NAME: EASTER_EGG_STATE}})

    # The custom image's link: no length byte (LENGTH 0, like the stock link)
    theme_cmds = model_map["0205"]
    custom = theme_cmds[SolixMqttCommands.display_theme_custom]
    link = custom["a7"][BYTES]["00"]
    if LENGTH not in link:
        theme_cmds[SolixMqttCommands.display_theme_custom] = custom | {
            "a7": custom["a7"] | {BYTES: {"00": link | {LENGTH: 0}}}
        }

    # The theme id as byte 00 of a bin field (also read when sent as var)
    for message, field in (("0a02", "a3"), ("0311", "a2")):
        theme_id = model_map[message][field]
        if BYTES not in theme_id:
            model_map[message] = model_map[message] | {field: {BYTES: {"00": theme_id}}}

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
