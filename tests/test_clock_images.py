"""Custom clock images: add (upload), rename, delete and list."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
import zlib

from PIL import Image
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.anker_prime_charger import clock_images
from custom_components.anker_prime_charger.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component

from .conftest import S3_URL, FakeCloud
from .helpers import attr, device_id, entity_id, state


@pytest.fixture
def photo(hass: HomeAssistant, tmp_path: Path) -> Path:
    """A 1200x900 photo in a folder Home Assistant may read."""
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (1200, 900), (200, 40, 40)).save(path, "JPEG")
    return path


@pytest.fixture
def storage(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Anker's image storage, accepting uploads."""
    aioclient_mock.put(
        f"{S3_URL}/anker_power/edge/screen_saver/test/1.cropped_image.jpg", status=200
    )
    aioclient_mock.put(
        f"{S3_URL}/anker_power/edge/screen_saver/test/2.cropped_image.jpg", status=200
    )
    return aioclient_mock


async def act(
    hass: HomeAssistant, service: str, response: bool = False, **data: Any
) -> Any:
    return await hass.services.async_call(
        DOMAIN,
        service,
        {"device_id": device_id(hass, "screen"), **data},
        blocking=True,
        return_response=response,
    )


def custom_options(hass: HomeAssistant) -> list[str]:
    options = attr(hass, "select", "theme_id", "options")
    return [o for o in options if o.startswith("Custom")]


async def test_add_clock_image(
    hass: HomeAssistant,
    storage: AiohttpClientMocker,  # before setup: the integration's web session
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    photo: Path,
    commands: list,
) -> None:
    """The photo is cut to 480x200, uploaded, registered, named and shown."""
    answer = await act(
        hass, "add_clock_image", response=True, path=str(photo), name="Beach", show=True
    )
    assert answer == {"id": 47834, "name": "Beach", "on_screen": False}

    # the token asks for a clock image (file type 106) of the uploaded size
    token = next(p for k, p in cloud.rest_requests if k.endswith("up_token_general"))
    assert token["type"] == 106
    assert token["file_name"] == "cropped_image.jpg"
    # the uploaded file: a 480x200 baseline JPEG, registered with its CRC32
    uploaded = storage.mock_calls[0][2]
    assert token["file_size"] == len(uploaded)
    with Image.open(io.BytesIO(uploaded)) as img:
        assert (img.format, img.size, img.info.get("progressive")) == (
            "JPEG",
            (480, 200),
            None,
        )
    added = next(
        p for k, p in cloud.rest_requests if k.endswith("add_manual_clock_screensavers")
    )
    assert added["img_url"] == "/anker_power/edge/screen_saver/test/1.cropped_image.jpg"
    assert added["hash_code"] == f"0x{zlib.crc32(uploaded):x}"

    # listed right away, and shown on the charger (theme kind custom)
    assert "Custom - Beach" in custom_options(hass)
    assert commands[-1][0] == "charger_theme_custom"
    assert commands[-1][1]["set_theme_id"] == 47834


async def test_add_clock_image_without_name(
    hass: HomeAssistant,
    storage: AiohttpClientMocker,
    setup_entry: MockConfigEntry,
    photo: Path,
) -> None:
    """Without a name it is shown like in the app: Custom <seq>."""
    answer = await act(
        hass, "add_clock_image", response=True, path=str(photo), fit="fit"
    )
    assert answer["name"] == "Custom 3"
    assert "Custom - Custom 3" in custom_options(hass)


async def test_add_clock_image_from_my_media(
    hass: HomeAssistant,
    storage: AiohttpClientMocker,
    setup_entry: MockConfigEntry,
    photo: Path,
) -> None:
    """An image picked in Media > My media."""
    hass.config.media_dirs = {"local": str(photo.parent)}
    assert await async_setup_component(hass, "media_source", {})
    answer = await act(
        hass,
        "add_clock_image",
        response=True,
        image={
            "media_content_id": "media-source://media_source/local/photo.jpg",
            "media_content_type": "image/jpeg",
        },
        name="From media",
    )
    assert answer["name"] == "From media"


async def test_add_clock_image_refused(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    photo: Path,
    tmp_path: Path,
) -> None:
    """Bad names and sources are refused before anything is uploaded."""
    with pytest.raises(ServiceValidationError, match="longer than 13"):
        await act(hass, "add_clock_image", path=str(photo), name="A name too long")
    with pytest.raises(ServiceValidationError, match="already named"):
        await act(hass, "add_clock_image", path=str(photo), name="fireworks")
    with pytest.raises(ServiceValidationError, match="may not read"):
        await act(hass, "add_clock_image", path="/etc/passwd")
    with pytest.raises(ServiceValidationError, match="Choose an image"):
        await act(hass, "add_clock_image")
    not_image = tmp_path / "notes.txt"
    not_image.write_text("hello")
    with pytest.raises(ServiceValidationError, match="isn't an image"):
        await act(hass, "add_clock_image", path=str(not_image))
    with pytest.raises(ServiceValidationError, match="Screen device"):
        await hass.services.async_call(
            DOMAIN,
            "add_clock_image",
            {"device_id": device_id(hass, "usbc_1"), "path": str(photo)},
            blocking=True,
        )
    assert not any(k.endswith("up_token_general") for k, _ in cloud.rest_requests)


async def test_rename_clock_image(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Renamed by name, Clock theme option or id; names stay unique and short."""
    await act(hass, "rename_clock_image", image="Custom - Custom 2", new_name="Beach")
    assert "Custom - Beach" in custom_options(hass)
    await act(hass, "rename_clock_image", image="38820", new_name="Party")
    assert "Custom - Party" in custom_options(hass)
    # keeping its own name is fine; another image's name is not
    await act(hass, "rename_clock_image", image="beach", new_name="Beach")
    with pytest.raises(ServiceValidationError, match="already named"):
        await act(hass, "rename_clock_image", image="Beach", new_name="Party")
    with pytest.raises(ServiceValidationError, match="No custom clock image"):
        await act(hass, "rename_clock_image", image="Nope", new_name="X")


async def test_delete_clock_image(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry, commands: list
) -> None:
    """Deleting the image on screen switches to Standard Style 1 first."""
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": entity_id(hass, "select", "theme_id"),
            "option": "Custom - Fireworks",
        },
        blocking=True,
    )
    assert state(hass, "select", "theme_id") == "Custom - Fireworks"
    sent = len(commands)
    await act(hass, "delete_clock_image", image="Fireworks")
    assert commands[sent][0] == "charger_theme"
    assert commands[sent][1]["set_theme_type"] == "style_1"
    assert "Custom - Fireworks" not in custom_options(hass)
    assert state(hass, "select", "theme_id") == "Standard Style - Theme 1"

    # an image that isn't on screen: just deleted
    sent = len(commands)
    await act(hass, "delete_clock_image", image="Custom 2")
    assert len(commands) == sent
    assert custom_options(hass) == []


async def test_list_clock_images(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Each image with its name, option, whether it is on screen and a fresh link."""
    current = state(hass, "select", "theme_id")
    answer = await act(hass, "list_clock_images", response=True)
    assert [i["on_screen"] for i in answer["images"]] == [
        current == "Custom - Fireworks",
        current == "Custom - Custom 2",
    ]
    for image in answer["images"]:
        image.pop("on_screen")
    assert answer["images"] == [
        {
            "id": 38820,
            "name": "Fireworks",
            "option": "Custom - Fireworks",
            "preview_url": f"{S3_URL}/custom/fw.jpg?fresh",
        },
        {
            "id": 47833,
            "name": "Custom 2",
            "option": "Custom - Custom 2",
            "preview_url": f"{S3_URL}/custom/x.jpg?fresh",
        },
    ]


def test_frames() -> None:
    """No frame keeps the image as is; the app's frame darkens it, most at the edges."""
    white = io.BytesIO()
    Image.new("RGB", (960, 400), (255, 255, 255)).save(white, "JPEG")

    def brightness(frame: str) -> dict[str, int]:
        prepared = clock_images.prepare(white.getvalue(), "fill", frame)
        with Image.open(io.BytesIO(prepared)) as img:
            grey = img.convert("L")
            return {
                "middle": grey.getpixel((240, 100)),
                "edge": grey.getpixel((0, 100)),
                "corner": grey.getpixel((0, 0)),
            }

    plain = brightness("none")
    assert min(plain.values()) >= 250
    shaded = brightness("shade")
    # like the app's mask: ~25 % darker in the middle, ~85 % at an edge, darkest in a corner
    assert 185 <= shaded["middle"] <= 197
    assert 30 <= shaded["edge"] <= 45
    assert shaded["corner"] < shaded["edge"]
    assert set(clock_images.FRAMES) == {"none", "shade"}


async def test_add_clock_image_with_frame(
    hass: HomeAssistant,
    storage: AiohttpClientMocker,
    setup_entry: MockConfigEntry,
    photo: Path,
) -> None:
    """The frame is drawn on the uploaded image."""
    await act(hass, "add_clock_image", path=str(photo), frame="shade")
    uploaded = storage.mock_calls[0][2]
    with Image.open(io.BytesIO(uploaded)) as img:
        corner, middle = (
            img.convert("L").getpixel((0, 0)),
            img.convert("L").getpixel((240, 100)),
        )
    assert corner < middle / 3
