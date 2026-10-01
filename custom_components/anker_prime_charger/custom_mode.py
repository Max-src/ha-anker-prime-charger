"""The charger's custom charging mode settings.

The charger keeps one set of custom-mode settings, reported in its status: a
profile number, "automatic deactivation" (auto exit), a power limit per port
and the allowed fast-charging protocols per USB-C port. Applying a custom
profile in the app loads its values into that set.

The only known command sends the whole set and switches the charger to the
custom mode (command 0206). The charger then re-applies power on every port,
which briefly disconnects the charging devices, so it is only sent when
something actually changes.

Limits, from Anker's user guide and the app: USB-C ports 0 W or 15 W up to
their maximum in 1 W steps; the two USB-A ports together 0, 15 or 24 W;
at most 250 W in total. Which protocols a USB-C port allows depends on its
power; the Anker cloud has the table (cloud.CloudSettings.protocol_ranges):
15-20 W UFCS; 21-22 W + 5-11V PPS, PD 12V; 23-44 W + SCP; 45 W and more
+ 5-16V PPS, 4.5-21V PPS, Xiaomi. No Huawei on this charger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .coordinator import PrimeChargerCoordinator
from .helpers import is_on, on_off, to_int, translated
from .ports import PORTS as PORT_DEVICES, USB_A_PORT, USB_C_PORTS
from .solixapi.mqttcmdmap import SolixMqttCommands

# Ports by their custom-mode name ("c1" ... "a"), from ports.PORTS
USB_C_MAX: Final = {port.custom: port.max_power for port in USB_C_PORTS}
USB_C_MIN: Final = 15  # or 0
USB_A_OPTIONS: Final = (0, 15, USB_A_PORT.max_power)
TOTAL_MAX: Final = 250
PORTS: Final = tuple(port.custom for port in PORT_DEVICES)
LABELS: Final = {port.custom: port.label for port in PORT_DEVICES}
# Fast-charging protocols a USB-C port can allow (the library's names and order;
# the app shows e.g. "SCP/UFCS/5-11V/5-16V"): 5-11V, 5-16V and 4.5-21V are PPS.
PROTOCOLS: Final = (
    "scp",
    "ufcs",
    "pd12v",
    "pps11v",
    "pps16v",
    "pps20v",
    "huawei",
    "xiaomi",
)


@dataclass
class CustomSettings:
    """A complete set of custom-mode settings."""

    limits: dict[str, int]  # port -> W
    protocols: dict[str, list[str]]  # USB-C port -> protocol names
    auto_exit: bool


def limit_key(port: str) -> str:
    """Status key of a port's custom power limit."""
    return f"custom_usb_{port}_power_limit"


def protocols_key(port: str) -> str:
    """Status key of a USB-C port's allowed protocols in the custom mode."""
    return f"custom_usb_{port}_protocols"


def check_limit(port: str, watts: float) -> None:
    """Refuse values the charger doesn't support."""
    if port == "a":
        if watts not in USB_A_OPTIONS:
            raise translated(
                ServiceValidationError,
                "usb_a_limit",
                options=f"{', '.join(map(str, USB_A_OPTIONS[:-1]))} or {USB_A_OPTIONS[-1]}",
            )
    elif not (watts == 0 or USB_C_MIN <= watts <= USB_C_MAX[port]):
        raise translated(
            ServiceValidationError,
            "usb_c_limit",
            port=LABELS[port],
            min=USB_C_MIN,
            max=USB_C_MAX[port],
        )


def ordered(names: list[str] | set[str]) -> list[str]:
    """Protocol names in the library's order, without duplicates or unknowns."""
    wanted = set(names)
    return [name for name in PROTOCOLS if name in wanted]


def current_protocols(data: dict[str, Any], port: str) -> list[str]:
    """A USB-C port's allowed protocols, in the library's order."""
    return ordered(data.get(protocols_key(port)) or [])


def allowed_protocols(
    coordinator: PrimeChargerCoordinator, port: str, watts: float
) -> list[str] | None:
    """Protocols a USB-C port can allow at this power (None: table not loaded)."""
    ranges = coordinator.cloud.protocol_ranges.get(port)
    if not ranges:
        return None
    for low, high, names in ranges:
        if low <= watts <= high:
            return ordered(names)
    return []


def current_allowed_protocols(
    coordinator: PrimeChargerCoordinator, port: str
) -> list[str] | None:
    """Protocols a USB-C port can allow at its current custom power (None: unknown)."""
    watts = to_int((coordinator.data or {}).get(limit_key(port)))
    if watts is None:
        return None
    return allowed_protocols(coordinator, port, watts)


def current_settings(coordinator: PrimeChargerCoordinator) -> CustomSettings:
    """The custom settings the charger reports."""
    data = coordinator.data or {}
    limits = {port: to_int(data.get(limit_key(port))) for port in PORTS}
    if None in limits.values():
        raise translated(HomeAssistantError, "not_reported")
    return CustomSettings(
        limits=limits,
        protocols={port: current_protocols(data, port) for port in USB_C_MAX},
        auto_exit=bool(is_on(data.get("auto_exit_switch"))),
    )


def resolve(
    coordinator: PrimeChargerCoordinator,
    base: CustomSettings,
    limits: dict[str, float] | None = None,
    auto_exit: bool | None = None,
    protocols: dict[str, list[str]] | None = None,
) -> CustomSettings:
    """Apply changes to `base` and check them like the app does.

    Protocols set explicitly must be allowed at the port's power. When only a
    port's power changes, protocols it no longer allows are dropped.
    """
    for port, watts in (limits or {}).items():
        check_limit(port, watts)
    new = CustomSettings(
        limits=base.limits
        | {port: int(watts) for port, watts in (limits or {}).items()},
        protocols=dict(base.protocols),
        auto_exit=base.auto_exit if auto_exit is None else auto_exit,
    )
    if (total := sum(new.limits.values())) > TOTAL_MAX:
        raise translated(
            ServiceValidationError, "total_too_high", total=total, max=TOTAL_MAX
        )
    for port in USB_C_MAX:
        allowed = allowed_protocols(coordinator, port, new.limits[port])
        if protocols and port in protocols:
            wanted = ordered(protocols[port])
            if unknown := set(protocols[port]) - set(PROTOCOLS):
                raise translated(
                    ServiceValidationError,
                    "unknown_protocol",
                    protocols=", ".join(sorted(unknown)),
                    possible=", ".join(PROTOCOLS),
                )
            if allowed is not None and (
                refused := [n for n in wanted if n not in allowed]
            ):
                raise translated(
                    ServiceValidationError,
                    "protocol_not_allowed",
                    port=LABELS[port],
                    watts=new.limits[port],
                    refused=", ".join(refused),
                    allowed=", ".join(allowed) or "none",
                )
            new.protocols[port] = wanted
        elif allowed is not None and new.limits[port] != base.limits[port]:
            new.protocols[port] = [n for n in new.protocols[port] if n in allowed]
    return new


async def async_apply(
    coordinator: PrimeChargerCoordinator,
    limits: dict[str, float] | None = None,
    auto_exit: bool | None = None,
    protocols: dict[str, list[str]] | None = None,
) -> None:
    """Send the charger's custom settings with the given changes.

    Does nothing if nothing changes.
    """
    base = current_settings(coordinator)
    new = resolve(coordinator, base, limits, auto_exit, protocols)
    if new == base:
        return
    data = coordinator.data or {}
    parm_map: dict[str, Any] = {
        "set_custom_profile_number": to_int(data.get("custom_profile_number")) or 0,
        "set_auto_exit_switch": on_off(new.auto_exit),
    }
    parm_map |= {
        f"set_usb_{port}_power_limit": watts for port, watts in new.limits.items()
    }
    parm_map |= {
        f"set_usb_{port}_protocols": names for port, names in new.protocols.items()
    }
    await coordinator.async_send_command(
        SolixMqttCommands.charger_custom_usage_mode, parm_map=parm_map
    )
