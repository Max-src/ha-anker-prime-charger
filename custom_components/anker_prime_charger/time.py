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
    entities: list[TimeEntity] = [
        ClockDisplayTime(coordinator, part) for part in schedules.SCHEDULE_PARTS
    ]
    entities += [
        PortScheduleTime(coordinator, port, part)
        for port in PORTS
        for part in schedules.SCHEDULE_PARTS
    ]
    async_add_entities(entities)


class ClockDisplayTime(PrimeChargerEntity, TimeEntity):
    """Start or end of the daily period in which the clock screen is shown."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator, part: str) -> None:
        """Initialize."""
        super().__init__(coordinator, f"clock_display_{part}_hour")
        self._part = part
        self._attr_unique_id = f"{coordinator.device_sn}_clock_display_{part}"
        self._attr_translation_key = f"clock_display_{part}"

    @property
    def native_value(self) -> time | None:
        """Return the time."""
        return schedules.reported_time(
            self.coordinator.data or {}, f"clock_display_{self._part}"
        )

    async def async_set_value(self, value: time) -> None:
        """Set the time, keeping the rest of the schedule."""
        await schedules.async_set_clock_schedule(
            self.coordinator, **{self._part: value}
        )


class PortScheduleTime(PrimeChargerEntity, TimeEntity):
    """Time of a port's scheduled start or end (see schedules.py)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: PrimeChargerCoordinator, port: Port, part: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{port.key}_{part}_hour", port)
        self._part = part
        self._attr_unique_id = f"{coordinator.device_sn}_{port.key}_{part}_time"
        self._attr_translation_key = f"schedule_{part}_time"

    @property
    def native_value(self) -> time | None:
        """Return the time."""
        return schedules.reported_time(
            self.coordinator.data or {}, f"{self.port.key}_{self._part}"
        )

    async def async_set_value(self, value: time) -> None:
        """Set the time, keeping the rest of this start or end."""
        await schedules.async_set_schedule(
            self.coordinator, self.port.key, self._part, at=value
        )
