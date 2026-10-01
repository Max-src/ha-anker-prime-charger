"""Refresh button for the Anker Prime Charger integration (charger status and cloud settings)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    async_add_entities([RefreshButton(entry.runtime_data)])


class RefreshButton(PrimeChargerEntity, ButtonEntity):
    """Request a status update from the charger now."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "refresh")

    @property
    def available(self) -> bool:
        """Always pressable while the coordinator works."""
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        """Send a status request and re-read the cloud settings (profiles, themes, ...)."""
        await self.coordinator.async_refresh_cloud()
        await self.coordinator.async_request_refresh()
