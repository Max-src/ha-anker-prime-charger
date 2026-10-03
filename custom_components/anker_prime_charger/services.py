"""Actions of the Anker Prime Charger integration.

They target devices: the charger, or one of its ports (child devices).

- Charger: manage custom charging profiles; set custom settings (several of
  the custom-mode settings in one command, so the ports are cut and
  renegotiated once, see custom_mode.py).
- Set days: the weekdays of a port schedule's start or end (target the port,
  pick the schedule), or of the clock screensaver (target the Screen device;
  the charger's device is accepted too).
- Set protocols: the fast-charging protocols of a USB-C port in the custom
  mode (target the port).

An entity of the integration may be targeted instead of a device: it stands
for its device. Devices and entities named directly must suit the action (a
clear error otherwise). Areas, floors and labels are resolved to the
integration's devices in them, keeping those the action applies to (e.g. the
charger for a profile action, its USB-C ports for Set protocols). The actions are registered when the integration loads (not
when a charger is set up), so they always exist and say clearly when the
target isn't usable.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_AREA_ID,
    ATTR_DEVICE_ID,
    ATTR_ENTITY_ID,
    ATTR_FLOOR_ID,
    ATTR_LABEL_ID,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.target import (
    TargetSelection,
    async_extract_referenced_entity_ids,
)

from . import custom_mode, profiles, schedules
from .const import DOMAIN, SCREEN
from .coordinator import PrimeChargerCoordinator
from .helpers import WEEKDAYS, translated
from .ports import PORTS, Port

SERVICE_SAVE_PROFILE: Final = "save_custom_profile"
SERVICE_CREATE_PROFILE: Final = "create_custom_profile"
SERVICE_DELETE_PROFILE: Final = "delete_custom_profile"
SERVICE_SET_CUSTOM_SETTINGS: Final = "set_custom_settings"
SERVICE_SET_DAYS: Final = "set_days"
SERVICE_SET_PROTOCOLS: Final = "set_protocols"

# Optional settings fields: "auto_deactivation", "c1_power" ... "a_power",
# "c1_protocols" ... "c4_protocols"
SETTINGS_FIELDS: Final = {
    vol.Optional("auto_deactivation"): cv.boolean,
    **{vol.Optional(f"{port}_power"): vol.Coerce(int) for port in custom_mode.PORTS},
    **{
        vol.Optional(f"{port}_protocols"): vol.All(
            cv.ensure_list, [vol.In(custom_mode.PROTOCOLS)]
        )
        for port in custom_mode.USB_C_MAX
    },
}


@dataclass(frozen=True)
class Target:
    """A targeted device: the charger (port None) or one of its ports."""

    coordinator: PrimeChargerCoordinator
    port: Port | None
    # the charger's Screen device (port None)
    screen: bool = False


type Handler = Callable[[ServiceCall, Target], Awaitable[None]]
# Whether an action applies to a device found through an area, floor or label
type Applies = Callable[[ServiceCall, Target], bool]


def _is_charger(call: ServiceCall, target: Target) -> bool:
    return target.port is None and not target.screen


def _has_schedule_days(call: ServiceCall, target: Target) -> bool:
    """A port's start or end days with "schedule", else the clock screensaver's."""
    if "schedule" in call.data:
        return target.port is not None
    return target.screen


def _is_usb_c_port(call: ServiceCall, target: Target) -> bool:
    return target.port is not None and target.port.is_usb_c


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""
    actions: tuple[tuple[str, dict[Any, Any], Handler, Applies], ...] = (
        (
            SERVICE_SAVE_PROFILE,
            {
                vol.Required("profile"): cv.string,
                vol.Optional("new_name"): cv.string,
                vol.Optional("from_charger", default=False): cv.boolean,
                **SETTINGS_FIELDS,
            },
            _async_save_profile,
            _is_charger,
        ),
        (
            SERVICE_CREATE_PROFILE,
            {vol.Required("name"): cv.string, **SETTINGS_FIELDS},
            _async_create_profile,
            _is_charger,
        ),
        (
            SERVICE_DELETE_PROFILE,
            {vol.Required("profile"): cv.string},
            _async_delete_profile,
            _is_charger,
        ),
        (
            SERVICE_SET_CUSTOM_SETTINGS,
            SETTINGS_FIELDS,
            _async_set_custom_settings,
            _is_charger,
        ),
        (
            SERVICE_SET_DAYS,
            {
                # no days selected: none
                vol.Optional("days", default=[]): vol.All(
                    cv.ensure_list, [vol.In(WEEKDAYS)]
                ),
                vol.Optional("schedule"): vol.In(schedules.SCHEDULE_PARTS),
            },
            _async_set_days,
            _has_schedule_days,
        ),
        (
            SERVICE_SET_PROTOCOLS,
            {
                # none selected: none
                vol.Optional("protocols", default=[]): vol.All(
                    cv.ensure_list, [vol.In(custom_mode.PROTOCOLS)]
                )
            },
            _async_set_protocols,
            _is_usb_c_port,
        ),
    )
    for name, fields, func, applies in actions:
        hass.services.async_register(
            DOMAIN,
            name,
            _for_each_target(hass, func, applies),
            schema=cv.make_entity_service_schema(fields),
        )


def _for_each_target(
    hass: HomeAssistant, func: Handler, applies: Applies
) -> Callable[[ServiceCall], Awaitable[None]]:
    async def handle(call: ServiceCall) -> None:
        named = _resolve(hass, _named_devices(hass, call))
        found = [
            target
            for target in _resolve(hass, _devices_in_groups(hass, call))
            if target not in named and applies(call, target)
        ]
        if not (targets := named + found):
            raise translated(ServiceValidationError, "no_target")
        for target in targets:
            await func(call, target)

    return handle


def _device_of(hass: HomeAssistant, entity_id: str) -> str | None:
    """The device of one of the integration's entities."""
    entry = er.async_get(hass).async_get(entity_id)
    return entry.device_id if entry and entry.platform == DOMAIN else None


def _named_devices(hass: HomeAssistant, call: ServiceCall) -> set[str]:
    """Devices targeted by id, or through one of their entities."""
    devices = set(cv.ensure_list(call.data.get(ATTR_DEVICE_ID)))
    for entity_id in cv.ensure_list(call.data.get(ATTR_ENTITY_ID)):
        if device_id := _device_of(hass, entity_id):
            devices.add(device_id)
    return devices


def _devices_in_groups(hass: HomeAssistant, call: ServiceCall) -> set[str]:
    """Devices in the targeted areas, floors and labels (or with entities in them)."""
    groups = {
        key: call.data[key]
        for key in (ATTR_AREA_ID, ATTR_FLOOR_ID, ATTR_LABEL_ID)
        if key in call.data
    }
    if not groups:
        return set()
    selected = async_extract_referenced_entity_ids(
        hass, TargetSelection(groups), expand_group=False
    )
    devices = set(selected.referenced_devices)
    for entity_id in selected.referenced | selected.indirectly_referenced:
        if device_id := _device_of(hass, entity_id):
            devices.add(device_id)
    return devices


def _resolve(hass: HomeAssistant, device_ids: set[str]) -> list[Target]:
    """The integration's chargers and ports among these devices."""
    device_registry = dr.async_get(hass)
    # Device identifiers of the loaded chargers and their ports (the port
    # devices are child devices: matched by identifier, not config entry)
    known: dict[str, Target] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            coordinator = entry.runtime_data
            sn = coordinator.device_sn
            known[sn] = Target(coordinator, None)
            known[f"{sn}_{SCREEN}"] = Target(coordinator, None, screen=True)
            known |= {f"{sn}_{port.key}": Target(coordinator, port) for port in PORTS}
    targets: dict[str, Target] = {}
    for device_id in device_ids:
        if (device := device_registry.async_get(device_id)) is None:
            continue
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier in known:
                targets[device_id] = known[identifier]
    return sorted(
        targets.values(),
        key=lambda t: (t.coordinator.device_sn, t.port.key if t.port else ""),
    )


def _charger(target: Target) -> PrimeChargerCoordinator:
    """The coordinator of a targeted charger (not a port)."""
    if target.port is not None or target.screen:
        raise translated(ServiceValidationError, "target_charger")
    return target.coordinator


def _settings(data: dict[str, Any]) -> dict[str, Any]:
    """The optional settings fields as async_*_profile arguments."""
    return {
        "auto_exit": data.get("auto_deactivation"),
        "limits": {
            port: data[f"{port}_power"]
            for port in custom_mode.PORTS
            if f"{port}_power" in data
        },
        "protocols": {
            port: data[f"{port}_protocols"]
            for port in custom_mode.USB_C_MAX
            if f"{port}_protocols" in data
        },
    }


async def _async_save_profile(call: ServiceCall, target: Target) -> None:
    await profiles.async_save_profile(
        _charger(target),
        call.data["profile"],
        new_name=call.data.get("new_name"),
        from_charger=call.data["from_charger"],
        **_settings(call.data),
    )


async def _async_create_profile(call: ServiceCall, target: Target) -> None:
    await profiles.async_create_profile(
        _charger(target), call.data["name"], **_settings(call.data)
    )


async def _async_set_custom_settings(call: ServiceCall, target: Target) -> None:
    await custom_mode.async_apply(_charger(target), **_settings(call.data))


async def _async_delete_profile(call: ServiceCall, target: Target) -> None:
    await profiles.async_delete_profile(_charger(target), call.data["profile"])


async def _async_set_days(call: ServiceCall, target: Target) -> None:
    """A port's schedule start or end days, or (charger) the clock display days."""
    part = call.data.get("schedule")
    if target.port is not None and part is None:
        raise translated(ServiceValidationError, "schedule_required")
    await schedules.async_set_days(
        target.coordinator,
        target.port.key if target.port else None,
        part,
        call.data["days"],
    )


async def _async_set_protocols(call: ServiceCall, target: Target) -> None:
    if target.port is None or not target.port.is_usb_c:
        raise translated(ServiceValidationError, "target_usb_c_port")
    await custom_mode.async_apply(
        target.coordinator, protocols={target.port.custom: call.data["protocols"]}
    )
