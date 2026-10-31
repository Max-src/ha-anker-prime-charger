"""Binary sensors for the Anker Prime Charger integration.

Ports: "device connected" (per physical port) and a fault (USB-A: either
USB-A port). Charger: overheating and a firmware update in progress.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import is_on
from .ports import PORTS, Port

# Updates come from the coordinator: no limit needed
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        PortConnected(coordinator, port, output)
        for port in PORTS
        for output in port.outputs
    ]
    entities += [PortFault(coordinator, port) for port in PORTS]
    entities += [Overheating(coordinator), FirmwareUpdating(coordinator)]
    async_add_entities(entities)


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


class PortFault(PrimeChargerEntity, BinarySensorEntity):
    """A fault the charger reports on a port (USB-A: either USB-A port).

    A bit of the status' fault field (0a00 a3): set after 5 readings with a
    fault, cleared after 10 without.
    """

    _attr_translation_key = "fault"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{port.key}_fault", port)

    @property
    def is_on(self) -> bool | None:
        """Return whether the port has a fault."""
        return is_on(self.mqtt_value)


class Overheating(PrimeChargerEntity, BinarySensorEntity):
    """The charger is too hot (a temperature sensor above 125 °C, until both are below 95 °C)."""

    _attr_translation_key = "over_temperature"
    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "over_temperature")

    @property
    def is_on(self) -> bool | None:
        """Return whether the charger is overheating."""
        return is_on(self.mqtt_value)


class FirmwareUpdating(PrimeChargerEntity, BinarySensorEntity):
    """A firmware update is being installed.

    From the status (0a00 b2: 1 while an update is armed; the live port values
    pause meanwhile), reported with every status. Not from the update message
    (0306), which only comes during an update and could leave it on.
    """

    _attr_translation_key = "firmware_update"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "ota_busy")

    @property
    def is_on(self) -> bool | None:
        """Return whether an update is running."""
        return is_on(self.mqtt_value)
