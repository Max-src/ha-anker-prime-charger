"""Switches for the Anker Prime Charger integration.

Charger: clock display, time display, holiday updates, automatic deactivation
of the custom mode, fast updates, and the app's test features.
Ports: the port itself (on/off), timer, schedule start and end.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import custom_mode, schedules, themes
from .const import TEST_FEATURES
from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import is_on
from .mqtt_extensions import TIME_DISPLAY_COMMAND, TIME_DISPLAY_STATE
from .ports import PORTS, Port
from .solixapi.mqttcmdmap import SolixMqttCommands


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        ClockDisplaySwitch(coordinator),
        TimeDisplaySwitch(coordinator),
        HolidaySwitch(coordinator),
        AutoDeactivationSwitch(coordinator),
        FastUpdatesSwitch(coordinator),
    ]
    entities += [TestFeatureSwitch(coordinator, key) for key in TEST_FEATURES]
    for port in PORTS:
        entities += [PortSwitch(coordinator, port), PortTimerSwitch(coordinator, port)]
        entities += [
            PortScheduleSwitch(coordinator, port, part)
            for part in schedules.SCHEDULE_PARTS
        ]
    async_add_entities(entities)


class ReportedSwitch(PrimeChargerEntity, SwitchEntity):
    """Switch showing a 0/1 value the charger reports; subclasses change it."""

    @property
    def is_on(self) -> bool | None:
        """Return whether it is on."""
        return is_on(self.mqtt_value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        raise NotImplementedError


class PortSwitch(ReportedSwitch):
    """The port on or off (USB-A: both USB-A ports; the charger has one switch)."""

    _attr_name = None  # the port device's name

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{port.key}_switch", port)

    async def _async_set(self, on: bool) -> None:
        await self.coordinator.async_send_command(
            f"{self.port.key}_port_switch", "on" if on else "off", "set_port_switch"
        )


class PortTimerSwitch(ReportedSwitch):
    """Turn the port off after the timer duration (see schedules.py)."""

    _attr_translation_key = "timer"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{port.key}_timer_switch", port)

    async def _async_set(self, on: bool) -> None:
        await schedules.async_set_timer(self.coordinator, self.port.key, enabled=on)


class PortScheduleSwitch(ReportedSwitch):
    """Enable the scheduled start or end of a port (see schedules.py)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: PrimeChargerCoordinator, port: Port, part: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, f"{port.key}_{part}_switch", port)
        self._part = part
        self._attr_translation_key = f"schedule_{part}"

    async def _async_set(self, on: bool) -> None:
        await schedules.async_set_schedule(
            self.coordinator, self.port.key, self._part, enabled=on
        )


class ClockDisplaySwitch(ReportedSwitch):
    """Show the clock screen (set together with the theme, see themes.py)."""

    _attr_translation_key = "clock_switch"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "clock_switch")

    async def _async_set(self, on: bool) -> None:
        await themes.async_set_theme(self.coordinator, clock_on=on)


class TimeDisplaySwitch(ReportedSwitch):
    """Show the time on top of a custom clock image (stock themes always show it)."""

    _attr_translation_key = "time_display"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, TIME_DISPLAY_STATE)

    async def _async_set(self, on: bool) -> None:
        await self.coordinator.async_send_command(
            TIME_DISPLAY_COMMAND, "on" if on else "off", "set_time_display"
        )


class HolidaySwitch(ReportedSwitch):
    """Holiday updates: festive clock screens on holidays (the charger picks them)."""

    _attr_translation_key = "holiday_switch"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "holiday_switch")

    async def _async_set(self, on: bool) -> None:
        await self.coordinator.async_send_command(
            SolixMqttCommands.clock_holiday_switch,
            "on" if on else "off",
            "set_holiday_switch",
        )


class AutoDeactivationSwitch(ReportedSwitch):
    """Leave the custom mode when a port set to 0 W is used (see custom_mode.py)."""

    _attr_translation_key = "auto_exit_switch"

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "auto_exit_switch")

    async def _async_set(self, on: bool) -> None:
        await custom_mode.async_apply(self.coordinator, auto_exit=on)


class TestFeatureSwitch(ReportedSwitch):
    """One of the app's test features, stored in the Anker cloud."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator, key)
        self._attr_translation_key = key

    @property
    def mqtt_value(self) -> Any:
        """Return the flag from the cloud settings (not an MQTT value)."""
        return self.coordinator.cloud.device_settings.get(self.key)

    async def _async_set(self, on: bool) -> None:
        await self.coordinator.async_set_test_feature(self.key, on)


class FastUpdatesSwitch(PrimeChargerEntity, SwitchEntity):
    """Port values every second instead of every poll (the app's real-time data).

    Stops by itself after the time set in the options (default 10 minutes).
    """

    _attr_translation_key = "fast_updates"

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "fast_updates")

    @property
    def available(self) -> bool:
        """Available while the charger is reachable."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        """Return whether fast updates are on."""
        return self.coordinator.fast_updates

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """When fast updates stop by themselves."""
        until = self.coordinator.fast_updates_until
        return {"until": until.isoformat() if until else None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start fast updates."""
        await self.coordinator.async_set_fast_updates(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop fast updates."""
        await self.coordinator.async_set_fast_updates(False)
