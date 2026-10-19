"""The dashboard cards: their files, their resource and their websocket command."""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import (
    ClientSessionGenerator,
    WebSocketGenerator,
)

from custom_components.anker_prime_charger.frontend import (
    CACHE_CONTROL,
    CARDS_MODULE,
    WWW,
    CardFilesView,
)
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import KEY_HASS
from homeassistant.setup import async_setup_component

from .conftest import S3_URL, STOCK_THEME_URL, FakeCloud
from .helpers import device_id, entity_id


async def charger(hass: HomeAssistant, ws: WebSocketGenerator, **data: str) -> dict:
    client = await ws(hass)
    await client.send_json_auto_id({"type": "anker_prime_charger/charger", **data})
    return await client.receive_json()


async def test_command_gives_the_ports_entities(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Each physical port with the entities of its readings, by unique id."""
    msg = await charger(hass, hass_ws_client, device_id=device_id(hass))
    assert msg["success"]
    result = msg["result"]
    assert result["device_id"] == device_id(hass)
    assert result["total_power"] == entity_id(hass, "sensor", "total_output_power")
    assert [(p["id"], p["label"], p["usb_c"]) for p in result["ports"]] == [
        ("c1", "C1", True),
        ("c2", "C2", True),
        ("c3", "C3", True),
        ("c4", "C4", True),
        ("a1", "A1", False),
        ("a2", "A2", False),
    ]
    a2 = result["ports"][5]
    assert a2["connected"] == entity_id(hass, "binary_sensor", "usba_2_status")
    for reading in ("power", "voltage", "current"):
        assert a2[reading] == entity_id(hass, "sensor", f"usba_2_{reading}")


async def test_command_gives_the_screen_entities(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """The settings the clock screensaver depends on, for the 3D card."""
    screen = (await charger(hass, hass_ws_client))["result"]["screen"]
    assert screen == {
        "theme": entity_id(hass, "select", "theme_id"),
        "time_display": entity_id(hass, "switch", "time_display"),
        "clock_format": entity_id(hass, "select", "clock_mode"),
    }


async def screensaver(hass: HomeAssistant, ws: WebSocketGenerator) -> dict:
    client = await ws(hass)
    await client.send_json_auto_id({"type": "anker_prime_charger/screensaver"})
    msg = await client.receive_json()
    assert msg["success"], msg
    return msg["result"]


async def test_screensaver_of_each_kind(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A stock theme and its picture, a Standard Style, a custom image's fresh link."""
    assert await screensaver(hass, hass_ws_client) == {
        "kind": "stock",
        "name": "Futuristic - Celestial",
        "image_url": STOCK_THEME_URL,
    }

    cloud.mqtt.deliver({"clock_settings": 0xC2, "theme_id": 47833})  # Standard Style 3
    await hass.async_block_till_done()
    assert await screensaver(hass, hass_ws_client) == {
        "kind": "style_3",
        "name": "Standard Style - Theme 3",
        "image_url": None,
    }

    cloud.mqtt.deliver({"clock_settings": 0xC5, "theme_id": 47833})  # custom image
    await hass.async_block_till_done()
    assert await screensaver(hass, hass_ws_client) == {
        "kind": "custom",
        "name": "Custom - Custom 2",
        "image_url": f"{S3_URL}/custom/x.jpg?fresh",  # asked for now (style/get_url)
    }


async def test_command_without_device_gives_the_first_charger(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A card with no charger chosen shows the first one."""
    msg = await charger(hass, hass_ws_client)
    assert msg["result"]["device_id"] == device_id(hass)


async def test_command_for_another_device_fails(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A device that isn't a charger (a port, say) is not found."""
    msg = await charger(hass, hass_ws_client, device_id=device_id(hass, "usbc_1"))
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_cards_are_served(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """www/ files without login, revalidated on each load; nothing else."""
    client = await hass_client_no_auth()
    resp = await client.get(CARDS_MODULE)
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/javascript")
    assert resp.headers["Cache-Control"] == CACHE_CONTROL
    assert await resp.text() == (WWW / "cards.js").read_text(encoding="utf-8")

    for path in (
        "missing.js",
        "..%2F__init__.py",
        "..%2Fmanifest.json",
        "%2E%2E/%2E%2E/configuration.yaml",
    ):
        resp = await client.get(f"/anker_prime_charger/{path}")
        # 400: Home Assistant's own filter refused it before the view
        assert resp.status in (400, 404), path


async def test_view_refuses_files_outside_www(hass: HomeAssistant) -> None:
    """The view's own guard, behind Home Assistant's filter."""
    app = web.Application()
    app[KEY_HASS] = hass
    view = CardFilesView()
    for path in ("../__init__.py", "../manifest.json", "lib/../../const.py", "x.py"):
        request = make_mocked_request("GET", f"/anker_prime_charger/{path}", app=app)
        with pytest.raises(web.HTTPNotFound):
            await view.get(request, path)


async def test_every_card_file_exists() -> None:
    """The module and each file it loads, so a missing one fails here."""
    for name in (
        "cards.js",
        "card-base.js",
        "card-editor.js",
        "charger.js",
        "charger-3d-card.js",
        "charger-model.js",
        "charger-screensaver.js",
        "charger-outputs-card.js",
        "registration.js",
        "styles.js",
        "lib/lit-all.js",
    ):
        assert (WWW / name).is_file(), name


async def test_cards_are_a_dashboard_resource_until_removed(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Registered once (also after a restart), removed with the last charger."""
    assert await async_setup_component(hass, "lovelace", {})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    resources = hass.data[LOVELACE_DATA].resources
    urls = [item["url"] for item in resources.async_items()]
    assert urls.count(CARDS_MODULE) == 1

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert CARDS_MODULE not in [item["url"] for item in resources.async_items()]
