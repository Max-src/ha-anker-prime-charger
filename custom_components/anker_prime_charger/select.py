"""Selects for the Anker Prime Charger integration.

Charger: charging mode (built-in modes and custom profiles), priority ports,
display timeout, knob direction, clock format, clock theme.
Ports: USB-A custom power limit (0, 15 or 24 W).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import custom_mode, themes
from .coordinator import PrimeChargerConfigEntry, PrimeChargerCoordinator
from .entity import PrimeChargerEntity
from .helpers import to_int
from .ports import PORTS, Port
from .solixapi.mqttcmdmap import SolixMqttCommands

# usage_mode value of the custom charging mode
CUSTOM_USAGE_MODE: Final = 5


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

# Priority ports: the command takes a bitmask of USB-C ports (bit 0 = C1 ...),
# at most two ports. The status reports a flag per port: 1 normal, 2 priority.
PRIORITY_PORTS: Final = ("usbc_1", "usbc_2", "usbc_3", "usbc_4")
PRIORITY_OPTIONS: Final[dict[str, int]] = {
    "off": 0,
    "c1": 1,
    "c2": 2,
    "c3": 4,
    "c4": 8,
    "c1_c2": 3,
    "c1_c3": 5,
    "c1_c4": 9,
    "c2_c3": 6,
    "c2_c4": 10,
    "c3_c4": 12,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrimeChargerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    coordinator = entry.runtime_data
    usb_a = next(port for port in PORTS if not port.is_usb_c)
    entities: list[SelectEntity] = [
        UsageModeSelect(coordinator, USAGE_MODE),
        PortPrioritySelect(coordinator),
        ClockThemeSelect(coordinator),
        UsbAPowerLimit(coordinator, usb_a),
    ]
    entities += [
        OptionSelect(coordinator, description) for description in OPTION_SELECTS
    ]
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
        mdev = await self.coordinator.async_mqtt_device()
        resp = await mdev.set_custom_usage_profile(number=profile.get("number"))
        if not isinstance(resp, dict):
            raise HomeAssistantError(
                f"The charger's library refused custom profile {option}"
            )
        self.coordinator.async_apply_state(resp)


class PortPrioritySelect(PrimeChargerEntity, SelectEntity):
    """USB-C ports that get power first in the Connection priority mode."""

    _attr_translation_key = "port_priority"
    _attr_options = list(PRIORITY_OPTIONS)

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "port_priority")

    def _mask(self) -> int | None:
        data = self.coordinator.data or {}
        flags = [to_int(data.get(f"{port}_priority")) for port in PRIORITY_PORTS]
        if None in flags:
            return None
        return sum(1 << idx for idx, flag in enumerate(flags) if flag == 2)

    @property
    def available(self) -> bool:
        """Available once all USB-C priority flags were reported."""
        return self.coordinator.last_update_success and self._mask() is not None

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
                f"{port}_priority": 2 if mask & (1 << idx) else 1
                for idx, port in enumerate(PRIORITY_PORTS)
            },
        )


class ClockThemeSelect(PrimeChargerEntity, SelectEntity):
    """Clock theme: Standard Styles, Anker's stock themes, your custom images."""

    _attr_translation_key = "clock_theme"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "theme_id")

    def _by_name(self) -> dict[str, dict[str, Any]]:
        return {
            theme["theme_name"]: theme
            for theme in themes.all_themes(self.coordinator).values()
            if theme.get("theme_name")
        }

    @property
    def options(self) -> list[str]:
        """Standard Styles, stock themes (by category), then custom images."""
        by_name = self._by_name()
        return sorted(
            by_name,
            key=lambda name: (
                themes.CATEGORY_ORDER.get(by_name[name].get("category_name"), 1),
                name.lower(),
            ),
        )

    @property
    def current_option(self) -> str | None:
        """Return the active theme."""
        return themes.current_theme(self.coordinator).get("theme_name")

    @property
    def entity_picture(self) -> str | None:
        """Preview of a stock theme.

        Custom image links from the Anker cloud expire after a few minutes, and
        Standard Styles only have app-internal paths, so neither is used.
        """
        theme = themes.current_theme(self.coordinator)
        url = theme.get("image_url") or ""
        if theme.get("kind") != "stock" or not url.startswith("https://"):
            return None
        return url

    async def async_select_option(self, option: str) -> None:
        """Show the theme."""
        if not (theme := self._by_name().get(option)):
            raise HomeAssistantError(f"Unknown clock theme {option}")
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
