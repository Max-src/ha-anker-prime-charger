"""Actions of the Anker Prime Charger integration: manage custom charging profiles.

They target the charger's "Charging mode" select entity. They are registered
when the integration loads (not when the charger is set up), so they always
exist and say clearly when the target isn't usable.
"""

from __future__ import annotations

from typing import Any, Final

import voluptuous as vol

from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, service
from homeassistant.helpers.entity import Entity

from . import custom_mode, profiles
from .const import DOMAIN
from .coordinator import PrimeChargerCoordinator
from .select import UsageModeSelect

SERVICE_SAVE_PROFILE: Final = "save_custom_profile"
SERVICE_CREATE_PROFILE: Final = "create_custom_profile"
SERVICE_DELETE_PROFILE: Final = "delete_custom_profile"

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


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""
    for name, schema, func in (
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
    ):
        service.async_register_platform_entity_service(
            hass,
            DOMAIN,
            name,
            entity_domain=SELECT_DOMAIN,
            schema=schema,
            func=func,
        )


def _coordinator(entity: Entity) -> PrimeChargerCoordinator:
    """The coordinator of the targeted "Charging mode" entity."""
    if not isinstance(entity, UsageModeSelect):
        raise ServiceValidationError(
            'Target the charger\'s "Charging mode" entity with this action'
        )
    return entity.coordinator


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


async def _async_save_profile(entity: Entity, call: ServiceCall) -> None:
    await profiles.async_save_profile(
        _coordinator(entity),
        call.data["profile"],
        new_name=call.data.get("new_name"),
        from_charger=call.data["from_charger"],
        **_settings(call.data),
    )


async def _async_create_profile(entity: Entity, call: ServiceCall) -> None:
    await profiles.async_create_profile(
        _coordinator(entity), call.data["name"], **_settings(call.data)
    )


async def _async_delete_profile(entity: Entity, call: ServiceCall) -> None:
    await profiles.async_delete_profile(_coordinator(entity), call.data["profile"])
