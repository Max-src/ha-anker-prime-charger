"""Times for the Anker Prime Charger integration.

Charger: clock display start and end.
Ports: schedule start and end times.
"""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import schedules
from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .ports import PORTS, Port


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up times."""
    coordinator = entry.runtime_data
    async_add_entities(
        ScheduleTime(coordinator, port, part)
        for port in (None, *PORTS)
        for part in schedules.SCHEDULE_PARTS
    )


class ScheduleTime(PrimeChargerEntity, TimeEntity):
    """Time of a schedule's start or end (see schedules.py).

    A port's scheduled start or end, or (no port) the start or end of the daily
    period in which the clock screen is shown.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: PrimeChargerCoordinator, port: Port | None, part: str
    ) -> None:
        """Initialize."""
        self._prefix = schedules.time_prefix(port.key if port else None, part)
        super().__init__(
            coordinator,
            f"{self._prefix}_hour",
            port,
            unique_key=f"{self._prefix}_time" if port else self._prefix,
            screen=port is None,
        )
        self._part = part
        self._attr_translation_key = (
            f"schedule_{part}_time" if port else f"clock_display_{part}"
        )

    @property
    def native_value(self) -> time | None:
        """Return the time."""
        return schedules.reported_time(self.coordinator.data or {}, self._prefix)

    async def async_set_value(self, value: time) -> None:
        """Set the time, keeping the rest of the schedule."""
        await schedules.async_set_time(
            self.coordinator, self.port.key if self.port else None, self._part, value
        )
