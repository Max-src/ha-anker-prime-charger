"""The Anker Prime Charger integration."""

from __future__ import annotations

from typing import Final

from aiohttp import ClientError

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType

from .const import CONF_DEVICE_SN, CONF_SERVER, DOMAIN
from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import charger_device_info
from .helpers import translated
from .library import create_api
from .services import async_setup_services
from .solixapi import errors

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
]

# Entities that earlier versions created and that no longer exist:
# (platform, unique id suffix). Removed from the entity registry at setup.
RETIRED_ENTITIES: Final = (
    # flags of the cloud settings that turned out to do nothing
    (Platform.SWITCH, "_antiloss_mode_status"),
    (Platform.SWITCH, "_temperature_mode_status"),
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: PrimeChargerConfigEntry
) -> bool:
    """Set up the charger from a config entry."""
    api = create_api(hass, entry.data, entry.data.get(CONF_SERVER))
    try:
        # A login reused from the library's cache returns False even though the
        # token is valid, so don't check the result. Bad or expired credentials
        # surface as errors on the request below (the library re-logs in on 401).
        await api.async_authenticate()
        # Lists every device the account owns, including standalone chargers
        await api.get_bind_devices()
    except (errors.AuthorizationError, errors.InvalidCredentialsError) as err:
        raise translated(ConfigEntryAuthFailed, "auth_failed", error=err) from err
    except (ClientError, errors.AnkerSolixError) as err:
        raise translated(ConfigEntryNotReady, "cloud_unreachable", error=err) from err

    device_sn = entry.data[CONF_DEVICE_SN]
    if device_sn not in api.devices:
        raise translated(ConfigEntryNotReady, "charger_not_found", serial=device_sn)

    _remove_retired_entities(hass, entry)
    coordinator = PrimeChargerCoordinator(hass, entry, api, device_sn)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    # The port devices are child devices of the charger's: register it first
    charger_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **charger_device_info(coordinator)
    )
    coordinator.charger_device_id = charger_device.id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PrimeChargerConfigEntry
) -> bool:
    """Unload a config entry and close the MQTT connection."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop()
    return unloaded


def _remove_retired_entities(
    hass: HomeAssistant, entry: PrimeChargerConfigEntry
) -> None:
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if any(
            reg_entry.domain == platform and reg_entry.unique_id.endswith(suffix)
            for platform, suffix in RETIRED_ENTITIES
        ):
            registry.async_remove(reg_entry.entity_id)
