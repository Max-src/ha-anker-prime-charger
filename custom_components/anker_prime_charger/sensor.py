"""Sensors for the Anker Prime Charger integration.

Charger: total output power and energy, unlocked hidden animations.
Ports: power, voltage and current (per physical port), energy, timer end.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Final

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import is_on, summed_power, to_number
from .ports import PORTS, Port

# Every physical port (MQTT reading names)
ALL_OUTPUTS: Final = tuple(output for port in PORTS for output in port.outputs)

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
        EnergySensor(coordinator, "total_output_energy", ALL_OUTPUTS),
        UnlockedAnimations(coordinator),
    ]
    for port in PORTS:
        entities += [
            PortReading(coordinator, port, output, description)
            for output in port.outputs
            for description in READINGS
        ]
        entities += [
            EnergySensor(coordinator, f"{output}_energy", (output,), port)
            for output in port.outputs
        ]
        entities.append(PortTimerEnd(coordinator, port))
    async_add_entities(entities)


class PortReading(PrimeChargerEntity, SensorEntity):
    """Power, voltage or current of a physical port.

    Power has the port's maximum as attribute "max_power" (W): USB-C 1 140,
    USB-C 2-4 100, each USB-A 22.5 (Anker's user guide).
    """

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
        if description.key == "power":
            self._attr_extra_state_attributes = {"max_power": port.output_max_power}

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        return to_number(self.mqtt_value)


class TotalPowerSensor(PrimeChargerEntity, SensorEntity):
    """Sum of the output power of all ports."""

    _needs_key = False
    _attr_translation_key = "total_output_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "total_output_power")

    def _power(self) -> float | None:
        return summed_power(self.coordinator.data or {}, ALL_OUTPUTS)

    @property
    def available(self) -> bool:
        """Available once any port power was reported."""
        return super().available and self._power() is not None

    @property
    def native_value(self) -> float | None:
        """Return the summed port power."""
        power = self._power()
        return None if power is None else round(power, 2)


class EnergySensor(PrimeChargerEntity, RestoreSensor):
    """Energy delivered by some ports, for the Energy dashboard.

    The charger only reports power, so this adds up power x time at each
    update (left Riemann sum: the power last reported lasts until the next
    update). Time while the charger is unavailable or Home Assistant is
    stopped isn't counted. The total is kept across restarts.
    """

    _needs_key = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: PrimeChargerCoordinator,
        key: str,
        outputs: Iterable[str],
        port: Port | None = None,
    ) -> None:
        """Initialize: `outputs` are the physical ports whose power is added up.

        On a port device: one physical port (USB-A: "A1 energy", "A2 energy").
        """
        super().__init__(coordinator, key, port)
        self._outputs = tuple(outputs)
        self._attr_translation_key = (
            f"{port.output_prefix(self._outputs[0])}energy" if port else key
        )
        self._energy = 0.0
        self._last: tuple[datetime, float] | None = None  # last time and power

    async def async_added_to_hass(self) -> None:
        """Restore the total, then start counting."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._energy = to_number(last.native_value) or 0.0
        self._sample()

    def _power(self) -> float | None:
        """Summed power of the outputs (W), or nothing if none was reported."""
        return summed_power(self.coordinator.data or {}, self._outputs)

    def _sample(self) -> None:
        """Add the energy since the last update, and remember the current power."""
        now = dt_util.utcnow()
        power = self._power() if self.coordinator.last_update_success else None
        if self._last is not None and power is not None:
            since, last_power = self._last
            # a clock set back must not lower the total (seen as a meter reset)
            hours = max((now - since).total_seconds(), 0) / 3600
            self._energy += max(last_power, 0.0) * hours / 1000
        self._last = None if power is None else (now, power)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sample()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Available once any of the outputs' power was reported."""
        return super().available and self._power() is not None

    @property
    def native_value(self) -> float:
        """Return the total (kWh)."""
        return round(self._energy, 6)


class PortTimerEnd(PrimeChargerEntity, SensorEntity):
    """When a running port timer turns the port off (see schedules.py).

    The charger reports the remaining seconds; the library adds when it
    received them.
    """

    _attr_translation_key = "timer_end"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            f"{port.key}_timer_remaining_seconds",
            port,
            unique_key=f"{port.key}_timer_end",
        )

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

    _needs_key = False
    _attr_translation_key = "unlocked_animations"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "unlocked_animations", screen=True)

    @property
    def available(self) -> bool:
        """Available once the list was read from the Anker cloud."""
        return super().available and self.coordinator.cloud.easter_eggs is not None

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
