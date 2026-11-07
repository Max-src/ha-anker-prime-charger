"""Buttons for the Anker Prime Charger integration.

Charger: Refresh (charger status and cloud settings). Screen: Wake screen.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import to_int, translated
from .select import DISPLAY_TIMEOUT

# Send the charger one command at a time
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator = entry.runtime_data
    async_add_entities([RefreshButton(coordinator), WakeScreenButton(coordinator)])


class RefreshButton(PrimeChargerEntity, ButtonEntity):
    """Request a status update from the charger now."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _needs_key = False

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        """Send a status request and re-read the cloud settings (profiles, themes, ...)."""
        await self.coordinator.async_refresh_cloud()
        await self.coordinator.async_request_refresh()


class WakeScreenButton(PrimeChargerEntity, ButtonEntity):
    """Wake the screen on its power page, as a press of the knob does.

    The charger has no command for it, but every command but the theme's
    wakes the screen (screen.py): this one sends the screen's Timeout as it
    is, which changes nothing else. The page estimate follows (the
    coordinator notes the wake). Needs the Timeout reported.
    """

    _attr_translation_key = "wake_screen"

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(
            coordinator, DISPLAY_TIMEOUT.key, unique_key="wake_screen", screen=True
        )

    async def async_press(self) -> None:
        """Send the Timeout the charger reports."""
        reported = to_int(self.mqtt_value)
        value = next(
            (
                sent
                for state, sent in DISPLAY_TIMEOUT.value_map.values()
                if state == reported
            ),
            None,
        )
        if value is None:
            raise translated(HomeAssistantError, "screen_timeout_unknown")
        await self.coordinator.async_send_command(
            DISPLAY_TIMEOUT.command, value, DISPLAY_TIMEOUT.parameter
        )
