"""The integration's dashboard cards (www/): served, loaded, and fed.

- Serves www/ at URL_BASE. Every file is revalidated on each load (no-cache),
  so a new version of a card applies on the next page load, also for the
  modules a card imports (they have no version in their URL); stale-if-error
  keeps the cached copy when Home Assistant is briefly unreachable.
- Loads the cards on every dashboard: registered as a Lovelace resource (as
  HACS does), or injected in the page when resources are managed in YAML.
- Answers the cards' websocket commands: which entities show a charger's
  ports and screen (found by unique id, so renamed entities and devices keep
  working), and which clock screensaver it has (the selected theme).
- Serves the clock screensaver's picture (login needed), kept in memory per
  charger: Anker's links to it change every time, so the browser could never
  keep it; the card keeps it by its key (theme and file), which doesn't.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from aiohttp import ClientError, ClientTimeout, web
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import websocket_command
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView

from . import clock_images, themes
from .const import DOMAIN, LOGGER, MODEL
from .coordinator import PrimeChargerCoordinator
from .ports import PORTS

URL_BASE: Final = f"/{DOMAIN}"
WWW: Final = Path(__file__).parent / "www"
# The one module dashboards load; it imports the cards
CARDS_MODULE: Final = f"{URL_BASE}/cards.js"
CACHE_CONTROL: Final = "no-cache, stale-if-error=86400"
# Explicit types: a module served with another type is refused by the browser
CONTENT_TYPES: Final = {".js": "text/javascript"}

WS_CHARGER: Final = f"{DOMAIN}/charger"
WS_SCREENSAVER: Final = f"{DOMAIN}/screensaver"
SCREENSAVER_IMAGE_URL: Final = f"/api/{DOMAIN}/screensaver_image"
IMAGE_TIMEOUT: Final = 30  # seconds to download a picture from Anker


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the cards, load them on the dashboards, answer their command.

    Called from async_setup: once per Home Assistant start, before any charger
    is set up, so a dashboard opened meanwhile already loads the cards.
    """
    hass.http.register_view(CardFilesView())
    hass.http.register_view(ScreensaverImageView())
    websocket_api.async_register_command(hass, ws_charger)
    websocket_api.async_register_command(hass, ws_screensaver)
    if await _async_add_resource(hass) or "frontend" not in hass.config.components:
        return
    # resources in YAML: load the cards with every page instead (not stored)
    from homeassistant.components.frontend import add_extra_js_url

    add_extra_js_url(hass, CARDS_MODULE)


async def async_remove_frontend(hass: HomeAssistant) -> None:
    """Stop loading the cards (the last charger was removed)."""
    if (resources := await _async_resources(hass)) is None:
        return
    for item in resources.async_items():
        if item["url"] == CARDS_MODULE:
            await resources.async_delete_item(item["id"])


class CardFilesView(HomeAssistantView):
    """The files of www/, without login: the browser loads them as scripts."""

    url = f"{URL_BASE}/{{path:.+}}"
    name = f"{DOMAIN}:cards"
    requires_auth = False

    async def get(self, request: web.Request, path: str) -> web.FileResponse:
        """Return the file, if it is one of www/."""
        root = WWW.resolve()
        file = (root / path).resolve()
        content_type = CONTENT_TYPES.get(file.suffix)
        # only files inside www/ ("../" is refused), of the types above
        if not file.is_relative_to(root) or content_type is None:
            raise web.HTTPNotFound
        if not await request.app[KEY_HASS].async_add_executor_job(file.is_file):
            raise web.HTTPNotFound
        return web.FileResponse(
            file,
            headers={"Cache-Control": CACHE_CONTROL, "Content-Type": content_type},
        )


async def _async_resources(hass: HomeAssistant) -> Any:
    """The dashboards' resources when they can be changed (storage mode), else None."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None or lovelace.resource_mode != "storage":
        return None
    resources = lovelace.resources
    # loaded on first use: read before looking for ours
    await resources.async_get_info()
    return resources


async def _async_add_resource(hass: HomeAssistant) -> bool:
    """Make the dashboards load the cards (once); False if resources are in YAML."""
    try:
        resources = await _async_resources(hass)
    except Exception:  # noqa: BLE001  # Lovelace internals changed: inject instead
        LOGGER.debug("Dashboard resources not available", exc_info=True)
        return False
    if resources is None:
        return False
    if not any(item["url"] == CARDS_MODULE for item in resources.async_items()):
        await resources.async_create_item({"res_type": "module", "url": CARDS_MODULE})
    return True


def _find(hass: HomeAssistant, wanted: str | None) -> PrimeChargerCoordinator | None:
    """The charger of device `wanted`, or the first one set up."""
    coordinators: list[PrimeChargerCoordinator] = [
        entry.runtime_data for entry in hass.config_entries.async_loaded_entries(DOMAIN)
    ]
    return next(
        (c for c in coordinators if not wanted or c.charger_device_id == wanted), None
    )


def _coordinator(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> PrimeChargerCoordinator | None:
    """The charger of the message's `device_id`, or the first one set up.

    None (and an error sent) when there is none.
    """
    wanted = msg.get("device_id")
    coordinator = _find(hass, wanted)
    if coordinator is None:
        connection.send_error(
            msg["id"],
            ERR_NOT_FOUND,
            "Charger not found" if wanted else "No charger set up",
        )
    return coordinator


@websocket_command({vol.Required("type"): WS_CHARGER, vol.Optional("device_id"): str})
@callback
def ws_charger(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """The charger's ports and screen, and their entities, for the cards.

    The charger of `device_id` (its device), or the first one set up. Each
    physical port (C1-C4, A1, A2) with the entity ids of its readings, and
    the screen's: the page it shows (estimated) and the settings the clock
    screensaver depends on; None for one that doesn't exist (disabled).
    """
    if (coordinator := _coordinator(hass, connection, msg)) is None:
        return

    registry = er.async_get(hass)
    sn = coordinator.device_sn

    def entity(platform: str, key: str) -> str | None:
        return registry.async_get_entity_id(platform, DOMAIN, f"{sn}_{key}")

    connection.send_result(
        msg["id"],
        {
            "device_id": coordinator.charger_device_id,
            "name": coordinator.charger_name,
            "model": MODEL,
            "total_power": entity("sensor", "total_output_power"),
            "ports": [
                {
                    "id": remark.lower(),
                    "label": remark,
                    "usb_c": port.is_usb_c,
                    "connected": entity("binary_sensor", f"{output}_status"),
                    "power": entity("sensor", f"{output}_power"),
                    "voltage": entity("sensor", f"{output}_voltage"),
                    "current": entity("sensor", f"{output}_current"),
                }
                for port in PORTS
                for output, remark in zip(port.outputs, port.remarks, strict=True)
            ],
            "screen": {
                "page": entity("sensor", "screen_page"),
                "theme": entity("select", "theme_id"),
                "time_display": entity("switch", "time_display"),
                "clock_format": entity("select", "clock_mode"),
            },
        },
    )


@websocket_command(
    {vol.Required("type"): WS_SCREENSAVER, vol.Optional("device_id"): str}
)
@callback
def ws_screensaver(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """The charger's clock screensaver: the selected theme, for the 3D card.

    Its kind ("style_1" ... "style_3": a Standard Style the charger draws;
    "stock"; "custom"), its name, and for a picture (stock themes, custom
    images) its key: the same as long as the picture is (ScreensaverImageView
    serves it). Kind None when the charger hasn't reported its theme yet.
    """
    if (coordinator := _coordinator(hass, connection, msg)) is None:
        return
    theme = themes.current_theme(coordinator)
    connection.send_result(
        msg["id"],
        {
            "kind": theme.get("kind"),
            "name": theme.get("theme_name"),
            "image_key": _image_key(coordinator, theme),
        },
    )


def _custom_image(
    coordinator: PrimeChargerCoordinator, theme: dict[str, Any]
) -> clock_images.ClockImage | None:
    return next(
        (
            i
            for i in clock_images.images(coordinator)
            if str(i.id) == str(theme.get("id"))
        ),
        None,
    )


def _image_key(
    coordinator: PrimeChargerCoordinator, theme: dict[str, Any]
) -> str | None:
    """The key of a theme's picture: its theme and file (None: no picture)."""
    kind = theme.get("kind")
    if kind == "stock" and isinstance(theme.get("image_url"), str):
        file = theme["image_url"]
    elif kind == "custom" and (item := _custom_image(coordinator, theme)):
        file = item.short_url
    else:
        return None
    return f"{kind}:{theme.get('id')}:{file}"


async def _async_image_url(
    coordinator: PrimeChargerCoordinator, theme: dict[str, Any]
) -> str | None:
    """A link to the theme's picture (a custom image's: fresh, from Anker)."""
    if theme.get("kind") == "custom":
        item = _custom_image(coordinator, theme)
        return await clock_images.async_preview_url(coordinator, item) if item else None
    url = theme.get("image_url")
    return url if isinstance(url, str) and url.startswith("https://") else None


class ScreensaverImageView(HomeAssistantView):
    """The picture of a charger's clock screensaver: <url>/<its device id>.

    Kept in memory (the charger's current one): asked from Anker only when
    the picture changes. Its key is in the X-Image-Key header.
    """

    url = f"{SCREENSAVER_IMAGE_URL}/{{device_id}}"
    name = f"api:{DOMAIN}:screensaver_image"

    async def get(self, request: web.Request, device_id: str) -> web.Response:
        """Return the picture of the selected theme."""
        hass = request.app[KEY_HASS]
        if (coordinator := _find(hass, device_id)) is None:
            raise web.HTTPNotFound
        theme = themes.current_theme(coordinator)
        if (key := _image_key(coordinator, theme)) is None:
            raise web.HTTPNotFound
        cached = coordinator.screensaver_image
        if cached is None or cached[0] != key:
            if (url := await _async_image_url(coordinator, theme)) is None:
                raise web.HTTPNotFound
            try:
                async with async_get_clientsession(hass).get(
                    url, timeout=ClientTimeout(total=IMAGE_TIMEOUT)
                ) as resp:
                    if resp.status != 200:
                        raise web.HTTPBadGateway
                    body = await resp.read()
                    content_type = resp.content_type or "image/jpeg"
            except (ClientError, TimeoutError) as err:
                raise web.HTTPBadGateway from err
            cached = coordinator.screensaver_image = (key, body, content_type)
        return web.Response(
            body=cached[1],
            content_type=cached[2],
            headers={"X-Image-Key": cached[0], "Cache-Control": "no-store"},
        )
