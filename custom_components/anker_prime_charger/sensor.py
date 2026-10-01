"""Sensors for the Anker Prime Charger integration.

Charger: total output power, unlocked hidden animations.
Ports: power, voltage and current (per physical port), timer end.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import is_on, to_number
from .ports import PORTS, Port

# Readings of each physical port: "<output>_<key>" in the charger's status
READINGS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        TotalPowerSensor(coordinator),
        UnlockedAnimations(coordinator),
    ]
    for port in PORTS:
        entities += [
            PortReading(coordinator, port, output, description)
            for output in port.outputs
            for description in READINGS
        ]
        entities.append(PortTimerEnd(coordinator, port))
    async_add_entities(entities)


class PortReading(PrimeChargerEntity, SensorEntity):
    """Power, voltage or current of a physical port."""

    def __init__(
        self,
        coordinator: PrimeChargerCoordinator,
        port: Port,
        output: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{output}_{description.key}", port)
        self.entity_description = description
        self._attr_translation_key = f"{port.output_prefix(output)}{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        return to_number(self.mqtt_value)


class TotalPowerSensor(PrimeChargerEntity, SensorEntity):
    """Sum of the output power of all ports."""

    _attr_translation_key = "total_output_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "total_output_power")

    def _port_powers(self) -> list[float]:
        data = self.coordinator.data or {}
        return [
            power
            for port in PORTS
            for output in port.outputs
            if (power := to_number(data.get(f"{output}_power"))) is not None
        ]

    @property
    def available(self) -> bool:
        """Available once any port power was reported."""
        return self.coordinator.last_update_success and bool(self._port_powers())

    @property
    def native_value(self) -> float | None:
        """Return the summed port power."""
        return round(sum(self._port_powers()), 2)


class PortTimerEnd(PrimeChargerEntity, SensorEntity):
    """When a running port timer turns the port off (see schedules.py).

    The charger reports the remaining seconds; the library adds when it
    received them.
    """

    _attr_translation_key = "timer_end"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{port.key}_timer_remaining_seconds", port)
        self._attr_unique_id = f"{coordinator.device_sn}_{port.key}_timer_end"

    @property
    def native_value(self) -> datetime | None:
        """Return the end time, or nothing while the timer is off."""
        data = self.coordinator.data or {}
        remaining = to_number(self.mqtt_value)
        received = to_number(data.get(f"{self.port.key}_timer_remaining_timestamp"))
        if (
            not is_on(data.get(f"{self.port.key}_timer_switch"))
            or not remaining
            or not received
        ):
            return None
        return dt_util.utc_from_timestamp(received + remaining)


class UnlockedAnimations(PrimeChargerEntity, SensorEntity):
    """Hidden animations unlocked on this charger (from the Anker cloud)."""

    _attr_translation_key = "unlocked_animations"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "unlocked_animations")

    @property
    def available(self) -> bool:
        """Available once the list was read from the Anker cloud."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.cloud.easter_eggs is not None
        )

    def _unlocked(self) -> list[dict[str, Any]]:
        return [
            egg
            for egg in self.coordinator.cloud.easter_eggs or []
            if egg.get("status") == 1
        ]

    @property
    def native_value(self) -> int:
        """Return how many are unlocked."""
        return len(self._unlocked())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Animation types and when each was first triggered."""
        return {
            "animations": [
                {
                    "type": egg.get("egg_type"),
                    "unlocked": dt_util.utc_from_timestamp(
                        egg["trigger_time"]
                    ).isoformat()
                    if egg.get("trigger_time")
                    else None,
                }
                for egg in self._unlocked()
            ]
        }
