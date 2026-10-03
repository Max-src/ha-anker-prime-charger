"""Preset selects: common values for a list that a text entity edits.

- Days presets (Every day, Weekdays, ...) for the schedule and clock display
  days (text.WeekdaysText).
- Protocols presets (all allowed at the port's power, none) for a USB-C port's
  custom protocols (text.PortProtocols).

Any other value shows as "custom". Set up by the select platform (select.py).
"""

from __future__ import annotations

from typing import Final

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity

from . import custom_mode, schedules
from .coordinator import PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import to_weekdays, translated
from .ports import Port
from .schedules import DAY_PRESETS

# Any value that isn't a preset
CUSTOM: Final = "custom"


class PresetSelect(PrimeChargerEntity, SelectEntity, RestoreEntity):
    """Presets for a list value that a text entity edits (days, protocols).

    Shows "custom" for any other value. Picking "custom" keeps the value and
    shows "custom" until it changes (also after a restart), so it can then be
    edited in the text entity.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: PrimeChargerCoordinator,
        key: str,
        port: Port | None,
        screen: bool = False,
    ) -> None:
        """Initialize (key: the value's status key)."""
        super().__init__(
            coordinator, key, port, unique_key=f"{key}_preset", screen=screen
        )
        # the value when "custom" was picked; shown as custom while unchanged
        self._custom: tuple[str, ...] | None = None

    def _value(self) -> tuple[str, ...] | None:
        """The current value, or None if not reported."""
        raise NotImplementedError

    def _presets(self) -> dict[str, tuple[str, ...] | None]:
        """Value of each preset (None: not known now), in matching order."""
        raise NotImplementedError

    async def _async_set(self, values: list[str]) -> None:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Keep "custom" if it was picked before the restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state == CUSTOM:
            self._custom = self._value()

    @property
    def current_option(self) -> str | None:
        """Return the preset matching the value, else "custom"."""
        if (value := self._value()) is None:
            return None
        if value == self._custom:
            return CUSTOM
        return next(
            (name for name, preset in self._presets().items() if value == preset),
            CUSTOM,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._custom != self._value():
            self._custom = None
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Send the preset's value to the charger ("custom": keep it)."""
        if option == CUSTOM:
            self._custom = self._value()
            self.async_write_ha_state()
            return
        self._custom = None
        if (preset := self._presets()[option]) is None:
            raise translated(HomeAssistantError, "not_reported")
        await self._async_set(list(preset))


class WeekdaysPresetSelect(PresetSelect):
    """Common sets of weekdays for a days text entity (text.WeekdaysText)."""

    _attr_options = [*DAY_PRESETS, CUSTOM]

    def __init__(
        self, coordinator: PrimeChargerCoordinator, port: Port | None, part: str | None
    ) -> None:
        """Initialize."""
        self._port_key = port.key if port else None
        self._part = part
        super().__init__(
            coordinator,
            schedules.weekdays_key(self._port_key, part),
            port,
            screen=port is None,
        )
        self._attr_translation_key = (
            f"schedule_{part}_days_preset" if port else "clock_display_days_preset"
        )

    def _value(self) -> tuple[str, ...] | None:
        days = to_weekdays(self.mqtt_value)
        return None if days is None else tuple(days)

    def _presets(self) -> dict[str, tuple[str, ...] | None]:
        return dict(DAY_PRESETS)

    async def _async_set(self, values: list[str]) -> None:
        await schedules.async_set_days(
            self.coordinator, self._port_key, self._part, values
        )


class ProtocolsPresetSelect(PresetSelect):
    """All or none of the protocols a USB-C port allows at its custom power.

    For a text.PortProtocols entity. Changing it re-applies the custom mode
    (see custom_mode.py).
    """

    _attr_translation_key = "custom_protocols_preset"
    _attr_options = ["all", "none", CUSTOM]

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, custom_mode.protocols_key(port.custom), port)

    def _value(self) -> tuple[str, ...] | None:
        if self.mqtt_value is None:
            return None
        return tuple(
            custom_mode.current_protocols(self.coordinator.data or {}, self.port.custom)
        )

    def _presets(self) -> dict[str, tuple[str, ...] | None]:
        allowed = custom_mode.current_allowed_protocols(
            self.coordinator, self.port.custom
        )
        # "none" first: at a power that allows nothing, both are the same
        return {"none": (), "all": None if allowed is None else tuple(allowed)}

    async def _async_set(self, values: list[str]) -> None:
        await custom_mode.async_apply(
            self.coordinator, protocols={self.port.custom: values}
        )
