"""Base entity for the Anker Prime Charger integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import ChildDeviceInfo, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL, MODEL_NAME, SCREEN, SCREEN_LABEL
from .coordinator import PrimeChargerCoordinator
from .ports import Port, port_device_info


class PrimeChargerEntity(CoordinatorEntity[PrimeChargerCoordinator]):
    """Entity bound to one value the charger reports (its "key").

    Entities of a port go on that port's device, those of the screen (display,
    clock screensaver, knob, hidden animations) on the Screen device, the others
    on the charger's. The unique id is "<serial>_<unique_key>" (default: the
    key); moving an entity to another device keeps it.

    Available while the charger is reachable and has reported the key; entities
    that don't show a reported value set _needs_key = False (and may add their
    own conditions to `available`).
    """

    _attr_has_entity_name = True
    _needs_key = True

    def __init__(
        self,
        coordinator: PrimeChargerCoordinator,
        key: str,
        port: Port | None = None,
        *,
        unique_key: str | None = None,
        screen: bool = False,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.key = key
        self.port = port
        sn = coordinator.device_sn
        self._attr_unique_id = f"{sn}_{unique_key or key}"
        if screen:
            self._attr_device_info = screen_device_info(coordinator)
        elif port is None:
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
        """Available while the charger is reachable (and has reported the key)."""
        return super().available and (
            not self._needs_key or self.mqtt_value is not None
        )


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


def screen_device_info(coordinator: PrimeChargerCoordinator) -> ChildDeviceInfo:
    """The charger's screen: a child device of the charger's device, like the ports."""
    return ChildDeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.device_sn}_{SCREEN}")},
        name=f"{coordinator.charger_name} {SCREEN_LABEL}",
        parent_device_id=coordinator.charger_device_id,
    )
