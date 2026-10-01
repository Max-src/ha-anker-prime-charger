"""Numbers for the Anker Prime Charger integration.

Charger: display brightness.
Ports: custom power limit (USB-C; USB-A is a select), timer duration.
"""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import custom_mode, schedules
from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import to_int
from .ports import PORTS, USB_C_PORTS, Port
from .solixapi.mqttcmdmap import SolixMqttCommands


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up numbers."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [DisplayBrightness(coordinator)]
    entities += [UsbCPowerLimit(coordinator, port) for port in USB_C_PORTS]
    entities += [PortTimerDuration(coordinator, port) for port in PORTS]
    async_add_entities(entities)


class DisplayBrightness(PrimeChargerEntity, NumberEntity):
    """Display brightness, 20-100 % in 5 % steps (lower values have no effect)."""

    _attr_translation_key = "display_brightness"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 20
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "display_brightness")

    @property
    def native_value(self) -> int | None:
        """Return the brightness."""
        return to_int(self.mqtt_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the brightness."""
        await self.coordinator.async_send_command(
            SolixMqttCommands.display_brightness, int(value), "set_display_brightness"
        )


class UsbCPowerLimit(PrimeChargerEntity, NumberEntity):
    """Maximum power of a USB-C port in the custom charging mode: 0 W or 15 W-max.

    Changing it switches the charger to the custom charging mode, which briefly
    disconnects the charging devices (see custom_mode.py).
    """

    _attr_translation_key = "custom_power_limit"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, custom_mode.limit_key(port.custom), port)
        self._attr_native_max_value = custom_mode.USB_C_MAX[port.custom]

    @property
    def native_value(self) -> int | None:
        """Return the limit."""
        return to_int(self.mqtt_value)

    async def async_set_native_value(self, value: float) -> None:
        """Apply the custom settings with this port changed."""
        await custom_mode.async_apply(
            self.coordinator, limits={self.port.custom: value}
        )


class PortTimerDuration(PrimeChargerEntity, NumberEntity):
    """How long the port stays on once its timer is started (whole minutes)."""

    _attr_translation_key = "timer_duration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = schedules.TIMER_STEP // 60
    _attr_native_max_value = schedules.TIMER_MAX // 60
    _attr_native_step = schedules.TIMER_STEP // 60
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{port.key}_timer_seconds", port)

    @property
    def native_value(self) -> int | None:
        """Return the duration in minutes."""
        seconds = to_int(self.mqtt_value)
        return None if seconds is None else seconds // 60

    async def async_set_native_value(self, value: float) -> None:
        """Set the duration (applies to a running timer as well)."""
        await schedules.async_set_timer(
            self.coordinator, self.port.key, seconds=round(value) * 60
        )
