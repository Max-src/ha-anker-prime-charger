"""Base entity for the Anker Prime Charger integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL, MODEL_NAME
from .coordinator import PrimeChargerCoordinator
from .ports import Port, port_device_info


class PrimeChargerEntity(CoordinatorEntity[PrimeChargerCoordinator]):
    """Entity bound to one value the charger reports (its "key").

    Entities of a port go on that port's device, the others on the charger's.
    The unique id is "<serial>_<key>", unless a subclass sets its own.
    """

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PrimeChargerCoordinator, key: str, port: Port | None = None
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.key = key
        self.port = port
        sn = coordinator.device_sn
        self._attr_unique_id = f"{sn}_{key}"
        if port is None:
            self._attr_device_info = charger_device_info(coordinator)
        else:
            self._attr_device_info = port_device_info(
                sn, coordinator.charger_name, coordinator.charger_device_id, port
            )

    @property
    def mqtt_value(self) -> Any:
        """Return the value the charger reports for this entity's key."""
        return (self.coordinator.data or {}).get(self.key)

    @property
    def available(self) -> bool:
        """Available once the charger has reported this key."""
        return super().available and self.mqtt_value is not None


def charger_device_info(coordinator: PrimeChargerCoordinator) -> DeviceInfo:
    """The charger's device."""
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.device_sn)},
        manufacturer=MANUFACTURER,
        model=MODEL_NAME,
        model_id=MODEL,
        name=coordinator.charger_name,
        serial_number=coordinator.device_sn,
        sw_version=coordinator.device.get("sw_version") or None,
    )
