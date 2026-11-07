"""Firmware update entity for the Anker Prime Charger integration.

Shows the installed firmware (from the charger's version message 0830, else
the Anker cloud's device list), the newest one the Anker cloud offers for it
(checked daily, cloud.py) and an update while the charger installs it
(status 0a00 b2). Installing is left to the Anker app: the integration never
starts an update.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import (
    OTA_BUSY_STATE,
    PrimeChargerConfigEntry,
    PrimeChargerCoordinator,
)
from .entity import PrimeChargerEntity
from .helpers import to_int
from .mqtt_extensions import SW_VERSION_STATE

# Updates come from the coordinator: no limit needed
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the firmware update entity."""
    async_add_entities([FirmwareUpdate(entry.runtime_data)])


def _version(value: Any) -> str | None:
    text = str(value or "").strip().lstrip("vV")
    return text or None


class FirmwareUpdate(PrimeChargerEntity, UpdateEntity):
    """The charger's firmware: installed, offered by the Anker cloud, installing."""

    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_supported_features = UpdateEntityFeature.PROGRESS
    _needs_key = False

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, SW_VERSION_STATE, unique_key="firmware")

    @property
    def installed_version(self) -> str | None:
        """The firmware the charger reports, else the one the cloud lists."""
        return _version(self.mqtt_value) or _version(
            self.coordinator.device.get("sw_version")
        )

    @property
    def latest_version(self) -> str | None:
        """The firmware the Anker cloud offers, or the installed one."""
        device = self.coordinator.device
        if device.get("is_ota_update") and (
            offered := _version(device.get("ota_version"))
        ):
            return offered
        return self.installed_version

    @property
    def in_progress(self) -> bool:
        """Whether the charger is installing an update."""
        return bool(to_int((self.coordinator.data or {}).get(OTA_BUSY_STATE)))

    @property
    def update_percentage(self) -> int | None:
        """How far the update is (%), while installing."""
        if not self.in_progress:
            return None
        return to_int((self.coordinator.data or {}).get("ota_progress"))
