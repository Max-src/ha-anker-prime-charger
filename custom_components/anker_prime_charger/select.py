"""Selects for the Anker Prime Charger integration.

Charger: charging mode (built-in modes and custom profiles), priority ports,
display timeout, knob direction, clock format, clock theme, clock display days.
Ports: USB-A custom power limit (0, 15 or 24 W), schedule start and end days.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import custom_mode, schedules, themes
from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import to_int, to_weekdays, translated
from .ports import (
    PORTS,
    PRIORITY_NORMAL,
    PRIORITY_ON,
    PRIORITY_OPTIONS,
    USB_A_PORT,
    USB_C_PORTS,
    Port,
)
from .schedules import DAY_PRESETS
from .solixapi.mqttcmdmap import SolixMqttCommands

# usage_mode value of the custom charging mode
CUSTOM_USAGE_MODE: Final = 5
# Preset selects: any value that isn't a preset
CUSTOM: Final = "custom"


@dataclass(frozen=True, kw_only=True)
class OptionSelectDescription(SelectEntityDescription):
    """Select bound to a reported value and a command with fixed options."""

    command: str
    parameter: str
    # option -> (value the charger reports, value sent in the command)
    value_map: dict[str, tuple[int, str]]


USAGE_MODE: Final = OptionSelectDescription(
    key="usage_mode",
    translation_key="usage_mode",
    command=SolixMqttCommands.charger_usage_mode,
    parameter="set_usage_mode",
    # The custom mode (5) is added per profile by UsageModeSelect
    value_map={
        "ai_power": (1, "ai_power"),
        "port_priority": (2, "port_priority"),
        "dual_laptop": (3, "dual_laptop"),
        "low_power": (4, "low_power"),
    },
)
OPTION_SELECTS: Final[tuple[OptionSelectDescription, ...]] = (
    OptionSelectDescription(
        key="display_timeout_mode",
        translation_key="display_timeout_mode",
        entity_category=EntityCategory.CONFIG,
        command=SolixMqttCommands.display_timeout_mode_select,
        parameter="set_display_timeout_mode",
        value_map={
            "never": (0, "0"),
            "30s": (1, "30"),
            "1min": (2, "60"),
            "5min": (3, "300"),
            "30min": (4, "1800"),
        },
    ),
    OptionSelectDescription(
        key="knob_mode",
        translation_key="knob_mode",
        entity_category=EntityCategory.CONFIG,
        command=SolixMqttCommands.knob_mode_select,
        parameter="set_knob_mode",
        value_map={"forward": (0, "forward"), "backward": (1, "backward")},
    ),
    OptionSelectDescription(
        key="clock_mode",
        translation_key="clock_mode",
        entity_category=EntityCategory.CONFIG,
        command=SolixMqttCommands.clock_mode_select,
        parameter="set_clock_mode",
        value_map={"12h": (0, "12h"), "24h": (1, "24h")},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = [
        UsageModeSelect(coordinator, USAGE_MODE),
        PortPrioritySelect(coordinator),
        ClockThemeSelect(coordinator),
        UsbAPowerLimit(coordinator, USB_A_PORT),
        WeekdaysPresetSelect(coordinator, None, None),
    ]
    entities += [
        OptionSelect(coordinator, description) for description in OPTION_SELECTS
    ]
    entities += [
        WeekdaysPresetSelect(coordinator, port, part)
        for port in PORTS
        for part in schedules.SCHEDULE_PARTS
    ]
    entities += [ProtocolsPresetSelect(coordinator, port) for port in USB_C_PORTS]
    async_add_entities(entities)


class OptionSelect(PrimeChargerEntity, SelectEntity):
    """Select with fixed options, each a value the charger reports and a command value."""

    entity_description: OptionSelectDescription

    def __init__(
        self, coordinator: PrimeChargerCoordinator, description: OptionSelectDescription
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_options = list(description.value_map)

    @property
    def current_option(self) -> str | None:
        """Return the option matching the reported value."""
        value = to_int(self.mqtt_value)
        return next(
            (
                option
                for option, (state, _) in self.entity_description.value_map.items()
                if state == value
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        """Send the selected option to the charger."""
        desc = self.entity_description
        await self.coordinator.async_send_command(
            desc.command, desc.value_map[option][1], desc.parameter
        )


class UsageModeSelect(OptionSelect):
    """Charging mode: the built-in modes, plus "Custom: <name>" per custom profile.

    Custom profiles are offered once the "Custom charging mode" test feature is
    on. They are managed in the app or with the profile actions (services.py).
    """

    def _profiles(self) -> dict[str, dict[str, Any]]:
        """Custom profiles by option, if the custom charging mode is enabled."""
        cloud = self.coordinator.cloud
        if not cloud.device_settings.get("charging_mode_status"):
            return {}
        return {
            f"Custom: {profile.get('name') or profile.get('number')}": profile
            for profile in sorted(
                cloud.profiles.values(), key=lambda p: to_int(p.get("number")) or 0
            )
        }

    @property
    def options(self) -> list[str]:
        """Built-in modes and custom profiles."""
        return [*self.entity_description.value_map, *self._profiles()]

    @property
    def current_option(self) -> str | None:
        """Return the active mode, or the active custom profile."""
        if to_int(self.mqtt_value) != CUSTOM_USAGE_MODE:
            return super().current_option
        number = to_int((self.coordinator.data or {}).get("custom_profile_number"))
        return next(
            (
                option
                for option, profile in self._profiles().items()
                if to_int(profile.get("number")) == number
            ),
            None,
        )

    async def async_select_option(self, option: str) -> None:
        """Send a built-in mode, or apply a custom profile's port settings."""
        if not (profile := self._profiles().get(option)):
            await super().async_select_option(option)
            return
        await self.coordinator.async_set_custom_profile(profile.get("number"))


class PortPrioritySelect(PrimeChargerEntity, SelectEntity):
    """USB-C ports that get power first in the Connection priority mode."""

    _attr_translation_key = "port_priority"
    _attr_options = list(PRIORITY_OPTIONS)
    _needs_key = False

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "port_priority")

    def _mask(self) -> int | None:
        data = self.coordinator.data or {}
        flags = [to_int(data.get(f"{port.key}_priority")) for port in USB_C_PORTS]
        if None in flags:
            return None
        return sum(1 << idx for idx, flag in enumerate(flags) if flag == PRIORITY_ON)

    @property
    def available(self) -> bool:
        """Available once all USB-C priority flags were reported."""
        return super().available and self._mask() is not None

    @property
    def current_option(self) -> str | None:
        """Return the option matching the reported per-port flags."""
        mask = self._mask()
        return next(
            (option for option, m in PRIORITY_OPTIONS.items() if m == mask), None
        )

    async def async_select_option(self, option: str) -> None:
        """Send the port bitmask and expect the matching per-port flags."""
        mask = PRIORITY_OPTIONS[option]
        await self.coordinator.async_send_command(
            SolixMqttCommands.port_priority,
            option,
            "set_port_priority",
            expected={
                f"{port.key}_priority": PRIORITY_ON
                if mask & (1 << idx)
                else PRIORITY_NORMAL
                for idx, port in enumerate(USB_C_PORTS)
            },
        )


class ClockThemeSelect(PrimeChargerEntity, SelectEntity):
    """Clock theme: Standard Styles, Anker's stock themes, your custom images.

    The theme list is built once per update (and cloud refresh), not for each
    of the options, the current theme and the picture.
    """

    _attr_translation_key = "clock_theme"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "theme_id")
        self._by_name: dict[str, dict[str, Any]] = {}
        self._update_themes()

    def _update_themes(self) -> None:
        by_name = {
            theme["theme_name"]: theme
            for theme in themes.all_themes(self.coordinator).values()
            if theme.get("theme_name")
        }
        self._by_name = by_name
        # Standard Styles, stock themes (by category), then custom images
        self._attr_options = sorted(
            by_name,
            key=lambda name: (
                themes.CATEGORY_ORDER.get(by_name[name].get("category_name"), 1),
                name.lower(),
            ),
        )
        theme = themes.current_theme(self.coordinator)
        self._attr_current_option = theme.get("theme_name")
        # Preview of a stock theme. Custom image links from the Anker cloud
        # expire after a few minutes, and Standard Styles only have app-internal
        # paths, so neither is used.
        url = theme.get("image_url") or ""
        self._attr_entity_picture = (
            url if theme.get("kind") == "stock" and url.startswith("https://") else None
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_themes()
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Show the theme."""
        if not (theme := self._by_name.get(option)):
            raise translated(HomeAssistantError, "unknown_theme", theme=option)
        await themes.async_set_theme(self.coordinator, theme=theme)


class UsbAPowerLimit(PrimeChargerEntity, SelectEntity):
    """Power of both USB-A ports together in the custom charging mode: 0, 15 or 24 W.

    Changing it switches the charger to the custom charging mode (see
    custom_mode.py).
    """

    _attr_translation_key = "custom_power_limit"
    _attr_options = [str(watts) for watts in custom_mode.USB_A_OPTIONS]

    def __init__(self, coordinator: PrimeChargerCoordinator, port: Port) -> None:
        """Initialize."""
        super().__init__(coordinator, custom_mode.limit_key(port.custom), port)

    @property
    def current_option(self) -> str | None:
        """Return the limit, if it is one of the supported values."""
        value = to_int(self.mqtt_value)
        option = None if value is None else str(value)
        return option if option in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        """Apply the custom settings with the USB-A limit changed."""
        await custom_mode.async_apply(
            self.coordinator, limits={self.port.custom: int(option)}
        )


class PresetSelect(PrimeChargerEntity, SelectEntity, RestoreEntity):
    """Presets for a list value that a text entity edits (days, protocols).

    Shows "custom" for any other value. Picking "custom" keeps the value and
    shows "custom" until it changes (also after a restart), so it can then be
    edited in the text entity.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: PrimeChargerCoordinator, key: str, port: Port | None
    ) -> None:
        """Initialize (key: the value's status key)."""
        super().__init__(coordinator, key, port, unique_key=f"{key}_preset")
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
            coordinator, schedules.weekdays_key(self._port_key, part), port
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
