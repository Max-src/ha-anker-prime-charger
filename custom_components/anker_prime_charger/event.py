"""Hidden ("easter egg") animation event for the Anker Prime Charger integration."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity

EVENT_PLAYED = "played"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up events."""
    async_add_entities([HiddenAnimationEvent(entry.runtime_data)])


class HiddenAnimationEvent(PrimeChargerEntity, EventEntity):
    """Fires when the charger plays a hidden animation.

    The charger starts them on its own (e.g. a port unplugged 10 times within
    60 s) and reports the animation type; they can't be started on demand.
    """

    _attr_translation_key = "hidden_animation"
    _attr_event_types = [EVENT_PLAYED]
    _needs_key = False

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "hidden_animation", screen=True)

    async def async_added_to_hass(self) -> None:
        """Listen for animations."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_easter_egg_listener(self._async_played)
        )

    @callback
    def _async_played(self, animation_type: int) -> None:
        self._trigger_event(EVENT_PLAYED, {"animation_type": animation_type})
        self.async_write_ha_state()
