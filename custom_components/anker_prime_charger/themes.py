"""Clock themes of the Anker Prime Charger integration.

Three kinds of themes (decoded by watching the Anker app's MQTT messages):
- the built-in "Standard Style" themes 1-3: the charger draws the clock in its
  own style on a plain background. They are not in the Anker cloud's theme
  list; the app sends theme id 4, hash 0 and app-internal image paths.
- Anker's stock themes (from the Anker cloud, e.g. "Futuristic - Celestial").
- custom images added in the Anker app (from the Anker cloud).

The kind is the low 3 bits of the clock flag byte "clock_settings": 0, 1, 2
the Standard Styles 1-3, 3 a stock theme, 5 a custom image. With a Standard
Style active the charger still reports the previous theme's id, so the kind
decides which theme is current.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from homeassistant.exceptions import HomeAssistantError

from .helpers import is_on, on_off, to_int, translated
from .solixapi.mqttcmdmap import SolixMqttCommands

if TYPE_CHECKING:
    from .coordinator import PrimeChargerCoordinator

CUSTOM_CATEGORY: Final = "Custom"  # images added in the Anker app
# What the app calls a custom image without a name
UNNAMED_IMAGE: Final = "Custom"
STANDARD_CATEGORY: Final = "Standard Style"
# Order of the theme list, as in the app: Standard Styles, stock themes, custom
CATEGORY_ORDER: Final = {STANDARD_CATEGORY: 0, CUSTOM_CATEGORY: 2}
CLOCK_ON: Final = 0x80  # clock flag byte: clock screen shown
HOLIDAY_ON: Final = 0x40  # clock flag byte: holiday updates
THEME_KIND_MASK: Final = 0x07  # clock flag byte: the theme kind
# Our theme kinds: (value in the clock flag byte, the library's option name)
THEME_KINDS: Final[dict[str, tuple[int, str]]] = {
    "style_1": (0, "theme_1"),
    "style_2": (1, "theme_2"),
    "style_3": (2, "theme_3"),
    "stock": (3, "stock"),
    "custom": (5, "custom"),
}

STANDARD_STYLES: Final[tuple[dict[str, Any], ...]] = tuple(
    {
        "kind": f"style_{number}",
        "category_name": STANDARD_CATEGORY,
        "title": f"Theme {number}",
        "theme_name": f"{STANDARD_CATEGORY} - Theme {number}",
        "id": 4,
        "file_hash": "0x0",
        "image_url": path,
    }
    for number, path in (
        (1, "assets/img/shared/icl_a2345_theme1.png"),
        (2, "assets/img/a2345/icl_a2345_theme2.png"),
        (3, "assets/img/a2345/icl_a2345_theme3.png"),
    )
)


def parse_stock_catalogue(resp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Stock themes by id, from the cloud's catalogue (categories of themes)."""
    themes: dict[str, dict[str, Any]] = {}
    for category in resp.get("category") or []:
        if not (category_name := category.get("category_name")):
            continue
        for theme in category.get("list") or []:
            if theme_id := theme.get("id"):
                themes[str(theme_id)] = {
                    "category_name": category_name,
                    "title": theme.get("title"),
                    "file_hash": theme.get("file_crc32"),
                    "image_url": theme.get("image_url"),
                    "id": theme_id,
                    "theme_name": f"{category_name} - {theme.get('title')}",
                }
    return themes


def name_unnamed_custom_themes(
    custom_themes: dict[str, dict[str, Any]], seqs: dict[str, int | None]
) -> None:
    """Name the custom images that have no name, as the Anker app shows them.

    The app shows "Custom <seq>" (with the image's "seq" from the cloud
    list), or "Custom" when seq is 0. Without a seq (not
    read yet), "Image <id>".
    """
    for theme_id, theme in custom_themes.items():
        if theme.get("title"):
            continue
        if (seq := seqs.get(theme_id)) is None:
            theme["title"] = f"Image {theme_id}"
        else:
            theme["title"] = f"{UNNAMED_IMAGE} {seq}" if seq else UNNAMED_IMAGE
        theme["theme_name"] = f"{theme.get('category_name')} - {theme['title']}"


def all_themes(coordinator: PrimeChargerCoordinator) -> dict[str, dict[str, Any]]:
    """All clock themes by id, each with a "theme_name" and a "kind"."""
    themes = {theme["kind"]: theme for theme in STANDARD_STYLES}
    cloud_themes = coordinator.api.get_charger_themes(deviceSn=coordinator.device_sn)
    for theme_id, theme in cloud_themes.items():
        kind = "custom" if theme.get("category_name") == CUSTOM_CATEGORY else "stock"
        themes[theme_id] = theme | {"kind": kind}
    return themes


def current_theme(coordinator: PrimeChargerCoordinator) -> dict[str, Any]:
    """The clock theme the charger reports, if it is in the theme list."""
    data = coordinator.data or {}
    settings = to_int(data.get("clock_settings"))
    kind = None if settings is None else settings & THEME_KIND_MASK
    for style in STANDARD_STYLES:
        if THEME_KINDS[style["kind"]][0] == kind:
            return style
    theme_id = data.get("theme_id")
    if theme_id is None:
        return {}
    return all_themes(coordinator).get(str(theme_id), {})


async def async_set_theme(
    coordinator: PrimeChargerCoordinator,
    theme: dict[str, Any] | None = None,
    clock_on: bool | None = None,
) -> None:
    """Show a theme and/or switch the clock screen on or off.

    The charger takes both in one command. Every flag is sent explicitly
    (unchanged ones as reported), so nothing falls back to a library default.
    """
    data = coordinator.data or {}
    if theme is None and not (theme := current_theme(coordinator)):
        raise translated(HomeAssistantError, "not_reported")
    if clock_on is None:
        clock_on = bool(is_on(data.get("clock_switch")))
    holiday_on = bool(is_on(data.get("holiday_switch")))
    kind = theme.get("kind", "stock")
    kind_value, kind_option = THEME_KINDS[kind]
    url = theme.get("image_url") or ""
    if kind == "custom":
        # The charger downloads the image: the link read with the custom image
        # list has expired after 5 minutes (it then shows the previous theme)
        path = coordinator.cloud.custom_paths.get(str(theme.get("id")), "")
        url = await coordinator.cloud.async_fresh_link(path) or url
    parm_map = {
        "set_clock_switch": on_off(clock_on),
        "set_holiday_switch": on_off(holiday_on),
        "set_theme_type": kind_option,
        "set_theme_id": int(theme.get("id") or 0),
        "set_theme_hash": int(str(theme.get("file_hash") or "0"), 16),
        "set_theme_url": url,
    }
    # The library can't predict the new flag byte: compute it
    settings = to_int(data.get("clock_settings")) or 0
    expected = {
        "clock_settings": (settings & ~(CLOCK_ON | HOLIDAY_ON | THEME_KIND_MASK))
        | (CLOCK_ON if clock_on else 0)
        | (HOLIDAY_ON if holiday_on else 0)
        | kind_value
    }
    command = (
        SolixMqttCommands.display_theme_custom
        if kind == "custom"
        else SolixMqttCommands.display_theme
    )
    await coordinator.async_send_command(command, parm_map=parm_map, expected=expected)
