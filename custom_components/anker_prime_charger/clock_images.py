"""Custom clock images: add, rename, delete and list them (the app's custom themes).

Found in the Anker app (3.24.3, decompiled) and verified with
probing the cloud (see docs/PROTOCOL.md):

1. The image is cropped to the screen's 480x200 and saved as a baseline JPEG
   ("cropped_image.jpg", like the app).
   A frame can be drawn on it first (FRAMES: the app's dark edges).
2. The cloud hands out an upload link (cloudstor token, file type 106) and the
   object's path ("key_prefix").
3. The file is PUT to the link, then registered as a custom image with
   img_url = the object's path and hash_code = its CRC32.

Names: at most 13 characters and not one already used, like in the app. An
image without a name shows as "Custom <seq>" (see themes.py).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import io
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
import zlib

from aiohttp import ClientError

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import library, themes
from .cloud import CLOUD_ERRORS
from .helpers import translated

if TYPE_CHECKING:
    from .coordinator import PrimeChargerCoordinator

SIZE: Final = (480, 200)  # the screen's clock image
FILE_NAME: Final = "cropped_image.jpg"
FILE_TYPE: Final = 106  # the cloud's file type for clock images
CONTENT_TYPE: Final = "binary/octet-stream"
MAX_NAME: Final = 13
FITS: Final = ("fill", "fit")  # centre-crop, or the whole image with bars
JPEG_QUALITY: Final = 90

# The Anker app's frame: dark edges, from its mask icl_a2345_custom_theme_cover
# (black, 25 % opaque in the middle, ~85 % at the edges, ~96 % in the corners),
# stretched over the crop and multiplied in. Generated here rather than copied:
# its profile measured, scaled to 480x200.
SHADE_BASE: Final = 64 / 255  # darkening everywhere
SHADE_EDGE: Final = 0.806  # extra darkening right at an edge
SHADE_WIDTH: Final = 62  # pixels over which an edge fades
SHADE_CURVE: Final = 1.8  # how quickly it fades


def _shade_edges(img: Any) -> Any:
    """Darken the image like the app's frame (a PIL image, 480x200)."""
    from PIL import Image, ImageChops

    width, height = img.size

    def keep(size: int) -> list[int]:
        # share of light kept along one axis: 1 - edge darkening
        out = []
        for i in range(size):
            distance = min(i, size - 1 - i)
            fade = max(0.0, 1 - distance / SHADE_WIDTH) ** SHADE_CURVE
            out.append(round(255 * (1 - SHADE_EDGE * fade)))
        return out

    across = Image.new("L", (width, 1))
    across.putdata(keep(width))
    down = Image.new("L", (1, height))
    down.putdata(keep(height))
    light = ImageChops.multiply(
        across.resize((width, height), Image.Resampling.NEAREST),
        down.resize((width, height), Image.Resampling.NEAREST),
    )
    light = light.point(lambda v: round(v * (1 - SHADE_BASE)))
    return ImageChops.multiply(img, Image.merge("RGB", (light, light, light)))


# Frames drawn on the image before it is uploaded: name -> how to draw it on a
# 480x200 RGB image (None: the image as is). Add new frames here, with their
# name in services.yaml and translations (selector "clock_image_frame").
FRAMES: Final[dict[str, Callable[[Any], Any] | None]] = {
    "none": None,
    "shade": _shade_edges,
}


@dataclass(frozen=True)
class ClockImage:
    """A custom clock image of the charger."""

    id: int
    name: str  # as shown, e.g. "Custom 1" for an image without a name
    short_url: str  # the object's path in Anker's storage
    on_screen: bool


def prepare(data: bytes, fit: str, frame: str = "none") -> bytes:
    """The image as the charger takes it: 480x200 baseline JPEG (blocking)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as source:
            img = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError) as err:
        raise translated(ServiceValidationError, "image_unreadable") from err
    if fit == "fit":
        img = ImageOps.pad(img, SIZE, Image.Resampling.LANCZOS, color=(0, 0, 0))
    else:
        img = ImageOps.fit(img, SIZE, Image.Resampling.LANCZOS)
    if (draw := FRAMES[frame]) is not None:
        img = draw(img)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=JPEG_QUALITY, progressive=False, optimize=False)
    return out.getvalue()


async def async_read_source(
    hass: HomeAssistant, media_content_id: str | None, path: str | None
) -> bytes:
    """The file picked in the media browser (My media) or at an allowed path."""
    if path:
        if not hass.config.is_allowed_path(path):
            raise translated(ServiceValidationError, "path_not_allowed", path=path)
        file = Path(path)
    elif media_content_id:
        file = _local_media_file(hass, media_content_id)
    else:
        raise translated(ServiceValidationError, "image_missing")
    try:
        return await hass.async_add_executor_job(file.read_bytes)
    except OSError as err:
        raise translated(
            ServiceValidationError, "image_unreadable_path", path=str(file)
        ) from err


def _local_media_file(hass: HomeAssistant, media_content_id: str) -> Path:
    """The file of a "My media" item (other media sources aren't supported)."""
    from homeassistant.components import media_source
    from homeassistant.components.media_source.const import DATA_LOCAL_SOURCE
    from homeassistant.components.media_source.local_source import LocalSource

    local = hass.data.get(DATA_LOCAL_SOURCE)
    try:
        item = media_source.MediaSourceItem.from_uri(hass, media_content_id, None)
        if not isinstance(local, LocalSource) or item.domain != local.domain:
            raise translated(ServiceValidationError, "image_source_unsupported")
        source_dir_id, location = local.async_parse_identifier(item)
        return local.async_full_path(source_dir_id, location)
    except (media_source.Unresolvable, ValueError) as err:
        raise translated(ServiceValidationError, "image_source_unsupported") from err


def images(coordinator: PrimeChargerCoordinator) -> list[ClockImage]:
    """The custom images, as last read from the cloud."""
    current = themes.current_theme(coordinator)
    return [
        ClockImage(
            id=int(theme["id"]),
            name=str(theme.get("title") or ""),
            short_url=coordinator.cloud.custom_paths.get(str(theme["id"]), ""),
            on_screen=current.get("kind") == "custom"
            and str(current.get("id")) == str(theme["id"]),
        )
        for theme in themes.all_themes(coordinator).values()
        if theme.get("kind") == "custom"
    ]


def find(coordinator: PrimeChargerCoordinator, image: str | int) -> ClockImage:
    """A custom image by id, name or Clock theme option ("Custom - <name>")."""
    wanted = str(image).strip()
    if wanted.lower().startswith(f"{themes.CUSTOM_CATEGORY.lower()} - "):
        wanted = wanted[len(themes.CUSTOM_CATEGORY) + 3 :]
    for item in images(coordinator):
        if wanted == str(item.id) or wanted.casefold() == item.name.casefold():
            return item
    names = ", ".join(i.name for i in images(coordinator)) or "none"
    raise translated(
        ServiceValidationError, "clock_image_not_found", image=image, images=names
    )


def check_name(
    coordinator: PrimeChargerCoordinator, name: str, keep: int | None = None
) -> str:
    """A valid new name: at most 13 characters, not used by another image."""
    name = name.strip()
    if not name:
        raise translated(ServiceValidationError, "clock_image_name_empty")
    if len(name) > MAX_NAME:
        raise translated(
            ServiceValidationError, "clock_image_name_too_long", name=name, max=MAX_NAME
        )
    if any(
        i.name.casefold() == name.casefold() and i.id != keep
        for i in images(coordinator)
    ):
        raise translated(ServiceValidationError, "clock_image_name_used", name=name)
    return name


async def async_add(
    coordinator: PrimeChargerCoordinator,
    data: bytes,
    name: str | None = None,
    fit: str = "fill",
    show: bool = False,
    frame: str = "none",
) -> ClockImage:
    """Upload an image as a new custom clock image, optionally show it."""
    hass = coordinator.hass
    api, sn = coordinator.api, coordinator.device_sn
    if name:
        name = check_name(coordinator, name)
    jpeg = await hass.async_add_executor_job(prepare, data, fit, frame)
    try:
        token = await library.async_request(
            api,
            "upload_token",
            {
                "file_name": FILE_NAME,
                "content_type": CONTENT_TYPE,
                "file_size": len(jpeg),
                "disable_ssl": False,
                "type": FILE_TYPE,
            },
        )
        uptoken, path = token.get("uptoken"), token.get("key_prefix")
        if not uptoken or not path:
            raise translated(
                HomeAssistantError, "clock_image_upload_failed", reason="no upload link"
            )
        async with async_get_clientsession(hass).put(
            uptoken, data=jpeg, headers={"Content-Type": CONTENT_TYPE}
        ) as resp:
            if resp.status >= 300:
                raise translated(
                    HomeAssistantError,
                    "clock_image_upload_failed",
                    reason=f"HTTP {resp.status}",
                )
        await library.async_request(
            api,
            "add_custom_theme",
            {"sn": sn, "img_url": path, "hash_code": f"0x{zlib.crc32(jpeg):x}"},
        )
        await coordinator.cloud.async_refresh_custom_images()
        image_id = coordinator.cloud.custom_id_of(path)
        if image_id is None:
            raise translated(
                HomeAssistantError, "clock_image_upload_failed", reason="not listed"
            )
        if name:
            await library.async_request(
                api,
                "rename_custom_theme",
                {"sn": sn, "screensaver_id": image_id, "name": name},
            )
            await coordinator.cloud.async_refresh_custom_images()
    except CLOUD_ERRORS as err:
        raise translated(HomeAssistantError, "cloud_error", error=err) from err
    finally:
        coordinator.async_update_listeners()
    image = find(coordinator, image_id)
    if show:
        await async_show(coordinator, image)
    return image


async def async_show(coordinator: PrimeChargerCoordinator, image: ClockImage) -> None:
    """Show a custom image on the charger's screen."""
    theme = themes.all_themes(coordinator)[str(image.id)]
    await themes.async_set_theme(coordinator, theme=theme)


async def async_rename(
    coordinator: PrimeChargerCoordinator, image: str | int, new_name: str
) -> ClockImage:
    """Rename a custom image."""
    item = find(coordinator, image)
    name = check_name(coordinator, new_name, keep=item.id)
    try:
        await library.async_request(
            coordinator.api,
            "rename_custom_theme",
            {"sn": coordinator.device_sn, "screensaver_id": item.id, "name": name},
        )
        await coordinator.cloud.async_refresh_custom_images()
    except CLOUD_ERRORS as err:
        raise translated(HomeAssistantError, "cloud_error", error=err) from err
    finally:
        coordinator.async_update_listeners()
    return find(coordinator, item.id)


async def async_delete(coordinator: PrimeChargerCoordinator, image: str | int) -> None:
    """Delete a custom image; if it is on screen, show Standard Style 1 first."""
    item = find(coordinator, image)
    if item.on_screen:
        await themes.async_set_theme(coordinator, theme=themes.STANDARD_STYLES[0])
    try:
        await library.async_request(
            coordinator.api, "delete_custom_theme", {"id": item.id}
        )
        await coordinator.cloud.async_refresh_custom_images()
    except CLOUD_ERRORS as err:
        raise translated(HomeAssistantError, "cloud_error", error=err) from err
    finally:
        coordinator.async_update_listeners()


async def async_preview_url(
    coordinator: PrimeChargerCoordinator, item: ClockImage
) -> str | None:
    """A fresh link to a custom image (valid a few minutes), or None."""
    if not item.short_url:
        return None
    try:
        answer = await library.async_request(
            coordinator.api, "theme_url", {"short_url": item.short_url}
        )
    except (*CLOUD_ERRORS, ClientError):
        return None
    url = answer.get("url")
    return url if isinstance(url, str) else None


async def async_list(coordinator: PrimeChargerCoordinator) -> list[dict[str, Any]]:
    """The custom images, each with a fresh preview link (valid a few minutes)."""
    out = []
    for item in images(coordinator):
        preview = await async_preview_url(coordinator, item)
        out.append(
            {
                "id": item.id,
                "name": item.name,
                "option": f"{themes.CUSTOM_CATEGORY} - {item.name}",
                "on_screen": item.on_screen,
                "preview_url": preview,
            }
        )
    return out
