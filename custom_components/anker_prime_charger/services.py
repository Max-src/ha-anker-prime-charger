"""Actions of the Anker Prime Charger integration.

They target devices: the charger, or one of its ports (child devices).

- Charger: manage custom charging profiles; set custom settings (several of
  the custom-mode settings in one command, so the ports are cut and
  renegotiated once, see custom_mode.py).
- Set days: the weekdays of a port schedule's start or end (target the port,
  pick the schedule), or of the clock display (target the charger).
- Set protocols: the fast-charging protocols of a USB-C port in the custom
  mode (target the port).

An entity of the integration may be targeted instead of a device: it stands
for its device. The actions are registered when the integration loads (not
when a charger is set up), so they always exist and say clearly when the
target isn't usable.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)

from . import custom_mode, profiles, schedules
from .const import DOMAIN
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


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""
    actions: tuple[
        tuple[str, dict[Any, Any], Callable[[ServiceCall, Target], Awaitable[None]]],
        ...,
    ] = (
        (
            SERVICE_SAVE_PROFILE,
            {
                vol.Required("profile"): cv.string,
                vol.Optional("new_name"): cv.string,
                vol.Optional("from_charger", default=False): cv.boolean,
                **SETTINGS_FIELDS,
            },
            _async_save_profile,
        ),
        (
            SERVICE_CREATE_PROFILE,
            {vol.Required("name"): cv.string, **SETTINGS_FIELDS},
            _async_create_profile,
        ),
        (
            SERVICE_DELETE_PROFILE,
            {vol.Required("profile"): cv.string},
            _async_delete_profile,
        ),
        (SERVICE_SET_CUSTOM_SETTINGS, SETTINGS_FIELDS, _async_set_custom_settings),
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
        ),
    )
    for name, fields, func in actions:
        hass.services.async_register(
            DOMAIN,
            name,
            _for_each_target(hass, func),
            schema=cv.make_entity_service_schema(fields),
        )


def _for_each_target(
    hass: HomeAssistant, func: Callable[[ServiceCall, Target], Awaitable[None]]
) -> Callable[[ServiceCall], Awaitable[None]]:
    async def handle(call: ServiceCall) -> None:
        if not (targets := _targets(hass, call)):
            raise translated(ServiceValidationError, "no_target")
        for target in targets:
            await func(call, target)

    return handle


def _targets(hass: HomeAssistant, call: ServiceCall) -> list[Target]:
    """The integration's devices the call targets (entities count as their device)."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    device_ids = set(cv.ensure_list(call.data.get(ATTR_DEVICE_ID)))
    for entity_id in cv.ensure_list(call.data.get(ATTR_ENTITY_ID)):
        entry = entity_registry.async_get(entity_id)
        if entry and entry.platform == DOMAIN and entry.device_id:
            device_ids.add(entry.device_id)
    # Device identifiers of the loaded chargers and their ports (the port
    # devices are child devices: matched by identifier, not config entry)
    known: dict[str, Target] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            coordinator = entry.runtime_data
            sn = coordinator.device_sn
            known[sn] = Target(coordinator, None)
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
    if target.port is not None:
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
