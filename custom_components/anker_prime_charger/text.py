"""Text entities for the Anker Prime Charger integration.

Charger: clock display days.
Ports: labels (per physical port), custom-mode protocols (USB-C), schedule
start and end days.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import custom_mode, schedules
from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import WEEKDAYS, to_int, to_weekdays
from .ports import PORTS, USB_C_PORTS, Port

DAYS_PATTERN = r"^\s*(all|none|(mon|tue|wed|thu|fri|sat|sun)(\s*,\s*(mon|tue|wed|thu|fri|sat|sun))*)\s*$"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up text entities."""
    coordinator = entry.runtime_data
    entities: list[TextEntity] = [ClockDisplayDays(coordinator)]
    for port in PORTS:
        entities += [
            PortLabel(coordinator, port, output, remark)
            for output, remark in zip(port.outputs, port.remarks, strict=True)
        ]
        entities += [
            PortScheduleDays(coordinator, port, part)
            for part in schedules.SCHEDULE_PARTS
        ]
    entities += [PortProtocols(coordinator, port) for port in USB_C_PORTS]
    async_add_entities(entities)


def parse_list(
    value: str, allowed: tuple[str, ...] | list[str], example: str
) -> list[str]:
    """Comma separated names from `allowed` ("all": all, "none": none), in order."""
    text = value.strip().lower()
    if text == "none":
        return []
    names = (
        set(allowed)
        if text == "all"
        else {n.strip() for n in text.split(",") if n.strip()}
    )
    if not names or names - set(allowed):
        raise ServiceValidationError(
            f"Invalid value '{value}': use {example}, all or none "
            f"(possible: {', '.join(allowed) or 'none'})"
        )
    return [name for name in allowed if name in names]


class WeekdaysText(PrimeChargerEntity, TextEntity):
    """Weekdays, e.g. "mon,tue,wed,thu,fri"; 3-letter English names, "all" or "none"."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_pattern = DAYS_PATTERN

    @property
    def native_value(self) -> str | None:
        """Return the days, comma separated ("none" if none)."""
        days = to_weekdays(self.mqtt_value)
        return None if days is None else ",".join(days) or "none"

    async def async_set_value(self, value: str) -> None:
        """Set the days."""
        await self._async_set_days(parse_list(value, WEEKDAYS, "e.g. mon,tue,wed"))

    async def _async_set_days(self, days: list[str]) -> None:
        raise NotImplementedError


class ClockDisplayDays(WeekdaysText):
    """Days on which the clock screen is shown."""

    _attr_translation_key = "clock_display_days"

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "clock_display_weekdays")

    async def _async_set_days(self, days: list[str]) -> None:
        await schedules.async_set_clock_schedule(self.coordinator, weekdays=days)


class PortScheduleDays(WeekdaysText):
    """Days of a port's scheduled start or end (see schedules.py)."""

    def __init__(
        self, coordinator: PrimeChargerCoordinator, port: Port, part: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{port.key}_{part}_weekdays", port)
        self._part = part
        self._attr_translation_key = f"schedule_{part}_days"

    async def _async_set_days(self, days: list[str]) -> None:
        await schedules.async_set_schedule(
            self.coordinator, self.port.key, self._part, weekdays=days
        )


class PortProtocols(PrimeChargerEntity, TextEntity):
    """Fast-charging protocols a USB-C port allows in the custom charging mode.

    E.g. "scp,ufcs,pps11v,pps16v" (the app's "SCP/UFCS/5-11V/5-16V"); "all"
    (every protocol allowed at the port's power) or "none". Changing it
    re-applies the custom mode (see custom_mode.py).
    """

    _attr_translation_key = "custom_protocols"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, custom_mode.protocols_key(port.custom), port)

    def _allowed(self) -> list[str] | None:
        """Protocols allowed at the port's current custom power (None: unknown)."""
        watts = to_int(
            (self.coordinator.data or {}).get(custom_mode.limit_key(self.port.custom))
        )
        if watts is None:
            return None
        return custom_mode.allowed_protocols(self.coordinator, self.port.custom, watts)

    @property
    def native_value(self) -> str | None:
        """Return the protocols, comma separated ("none" if none)."""
        names = custom_mode.current_protocols(
            self.coordinator.data or {}, self.port.custom
        )
        return ",".join(names) or "none"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Protocols the port can allow at its current custom power limit."""
        allowed = self._allowed()
        return {} if allowed is None else {"allowed": allowed}

    async def async_set_value(self, value: str) -> None:
        """Allow exactly these protocols."""
        allowed = self._allowed()
        names = parse_list(
            value,
            custom_mode.PROTOCOLS
            if value.strip().lower() != "all" or allowed is None
            else allowed,
            "e.g. scp,ufcs,pps11v",
        )
        await custom_mode.async_apply(
            self.coordinator, protocols={self.port.custom: names}
        )


class PortLabel(PrimeChargerEntity, TextEntity):
    """Label of a physical port, as shown in the Anker app (stored in the Anker cloud)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_max = 20

    def __init__(
        self, coordinator: PrimeChargerCoordinator, port: Port, output: str, remark: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, f"port_label_{remark.lower()}", port)
        self._remark = remark
        self._attr_translation_key = f"{port.output_prefix(output)}label"

    @property
    def available(self) -> bool:
        """Available once the labels were read from the Anker cloud."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.cloud.port_labels is not None
        )

    @property
    def native_value(self) -> str | None:
        """Return the label (empty when not set)."""
        return next(
            (
                item.get("remark") or ""
                for item in self.coordinator.cloud.port_labels or []
                if item.get("port_name") == self._remark
            ),
            "",
        )

    async def async_set_value(self, value: str) -> None:
        """Store the label in the Anker cloud (checked by reading it back)."""
        try:
            await self.coordinator.cloud.async_set_port_label(self._remark, value)
        finally:
            self.coordinator.async_update_listeners()
