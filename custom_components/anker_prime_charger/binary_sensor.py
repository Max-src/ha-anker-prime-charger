"""Per-port "device connected" binary sensors for the Anker Prime Charger integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import is_on
from .ports import PORTS, Port


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        PortConnected(coordinator, port, output)
        for port in PORTS
        for output in port.outputs
    )


class PortConnected(PrimeChargerEntity, BinarySensorEntity):
    """Whether a device is connected to a physical port (status 1 = active)."""

    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(
        self, coordinator: PrimeChargerCoordinator, port: Port, output: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{output}_status", port)
        self._attr_translation_key = f"{port.output_prefix(output)}connected"

    @property
    def is_on(self) -> bool | None:
        """Return whether the port is active."""
        return is_on(self.mqtt_value)
