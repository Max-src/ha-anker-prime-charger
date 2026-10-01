"""Find out how custom clock images get into the Anker cloud and onto the charger.

Run it yourself (it asks for your Anker login; nothing is stored):
    powershell -ExecutionPolicy Bypass -File tools\\probe_themes.ps1

Stages (the ones that could change something ask first):
  1. Read-only: list your custom clock images, download one custom and one
     stock image, report format / size / dimensions, and check whether the
     charger's theme hash is the CRC32 of the file.
  2. Learn the request fields of the "add / rename / delete custom image"
     endpoints from the server's "field X is not set" answers. Placeholder
     values reuse one of your existing images, so the worst case is a duplicate
     entry, which the probe then tries to delete.
  3. Try likely names for an "upload link" endpoint (missing ones answer 404).

Results (no email, password or token; serial masked; signed links cut at "?")
are printed and written to tools/probe_themes_results.json.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import struct
from typing import Any
import zlib

import aiohttp
from common import MODEL, anker_login, ask, call, discover_fields

RESULTS = Path(__file__).with_name("probe_themes_results.json")
STYLE = "mini_power/v1/app/style/"

# Guesses for an endpoint that hands out an upload link (stage 3)
UPLOAD_GUESSES = [
    STYLE + "get_upload_url",
    STYLE + "get_upload_sign",
    STYLE + "upload_manual_clock_screensaver",
    STYLE + "get_presigned_url",
    "mini_power/v1/app/common/get_upload_url",
    "mini_power/v1/app/upload/get_url",
    "power_service/v1/app/get_upload_url",
    "power_service/v1/app/upload/get_url",
    "app/upload/get_upload_url",
    "app/upload/presigned_url",
    "app/common/upload_file",
]


def image_info(data: bytes) -> dict[str, Any]:
    """Format, size, pixel dimensions and CRC32 of an image file."""
    info: dict[str, Any] = {"bytes": len(data), "crc32": f"0x{zlib.crc32(data):x}"}
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", data[16:24])
        info |= {"format": "png", "width": width, "height": height}
    elif data[:2] == b"\xff\xd8":
        info["format"] = "jpeg"
        pos = 2
        while pos + 9 < len(data):
            if data[pos] != 0xFF:
                break
            marker, length = (
                data[pos + 1],
                struct.unpack(">H", data[pos + 2 : pos + 4])[0],
            )
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack(">HH", data[pos + 5 : pos + 9])
                info |= {
                    "width": width,
                    "height": height,
                    "progressive": marker == 0xC2,
                }
                break
            pos += 2 + length
    else:
        info["format"] = f"unknown ({data[:4].hex()})"
    return info


async def download(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
    try:
        async with session.get(url) as resp:
            data = await resp.read()
            if resp.status != 200:
                return {"http_status": resp.status}
            return image_info(data) | {"content_type": resp.headers.get("Content-Type")}
    except aiohttp.ClientError as err:
        return {"error": str(err)}


async def stage_read(api, session, sn: str) -> dict[str, Any]:
    print("\n== Stage 1: your custom images and the image format (read-only)")
    custom = await call(api, STYLE + "get_manual_clock_screensavers", {"sn": sn})
    items = ((custom.get("data") or {}).get("list")) or []
    print(f"  {len(items)} custom image(s): {[i.get('name') for i in items]}")
    out: dict[str, Any] = {"custom_list": custom}
    if items:
        item = items[0]
        info = await download(session, item.get("img_url", ""))
        info["hash_code"] = item.get("hash_code")
        info["hash_is_crc32"] = (
            info.get("crc32") == str(item.get("hash_code", "")).lower()
        )
        print(f"  custom '{item.get('name')}': {info}")
        out["custom_image"] = info
        out["get_url"] = await call(
            api, STYLE + "get_url", {"sn": sn, "short_url": item.get("short_url")}
        )
        out["get_screensaver_img_url"] = await call(
            api,
            STYLE + "get_screensaver_img_url",
            {"sn": sn, "id": item.get("id"), "type": "manual"},
        )
    stock = await call(api, STYLE + "get_clock_screensavers", {"product_code": MODEL})
    categories = ((stock.get("data") or {}).get("category")) or []
    first = next((t for c in categories for t in c.get("list") or []), None)
    if first:
        info = await download(session, first.get("image_url", ""))
        info["file_crc32"] = first.get("file_crc32")
        info["hash_is_crc32"] = (
            info.get("crc32") == str(first.get("file_crc32", "")).lower()
        )
        info["bin_url"] = first.get("bin_url")
        print(f"  stock '{first.get('title')}': {info}")
        out["stock_image"] = info
        out["stock_sample"] = first
    return out


async def stage_fields(api, sn: str, sample: dict[str, Any] | None) -> dict[str, Any]:
    print("\n== Stage 2: request fields of the custom image endpoints")
    if not sample:
        print("  Skipped: needs one custom image in the app to reuse as placeholder.")
        return {"skipped": "no custom image"}
    if not ask(
        "Learn the 'add custom image' fields (may create a duplicate of "
        f"'{sample.get('name')}', which is then deleted)?"
    ):
        return {"skipped": "declined"}
    fill = {
        "sn": sn,
        "device_sn": sn,
        "product_code": MODEL,
        "device_pn": MODEL,
        "name": "HA probe test",
        "short_url": sample.get("short_url"),
        "img_url": sample.get("short_url"),
        "url": sample.get("short_url"),
        "image_url": sample.get("short_url"),
        "hash_code": sample.get("hash_code"),
        "file_hash": sample.get("hash_code"),
        "seq": 99,
    }
    out: dict[str, Any] = {}
    before = {i.get("id") for i in await custom_items(api, sn)}
    out["add"] = await discover_fields(
        api, STYLE + "add_manual_clock_screensavers", {}, fill
    )
    created = [i for i in await custom_items(api, sn) if i.get("id") not in before]
    out["created"] = created
    if created:
        print(f"  created {len(created)} entry(ies); learning the delete request")
        fill_delete = fill | {
            "id": created[0]["id"],
            "screensaver_id": created[0]["id"],
            "ids": [created[0]["id"]],
            "screensaver_ids": [created[0]["id"]],
        }
        out["delete"] = await discover_fields(
            api, STYLE + "delete_manual_clock_screensavers", {}, fill_delete
        )
        left = [i for i in await custom_items(api, sn) if i.get("id") not in before]
        out["left_over"] = left
        if left:
            print(
                "  !! Could not delete the test entry 'HA probe test'. "
                "Delete it in the Anker app."
            )
    else:
        print("  Nothing was created.")
        # Learn the delete fields without a valid id (nothing can be deleted)
        out["delete"] = await discover_fields(
            api, STYLE + "delete_manual_clock_screensavers", {}, fill | {"*": 0}
        )
    return out


async def custom_items(api, sn: str) -> list[dict[str, Any]]:
    resp = await call(api, STYLE + "get_manual_clock_screensavers", {"sn": sn})
    return ((resp.get("data") or {}).get("list")) or []


async def stage_upload(api, sn: str) -> dict[str, Any]:
    print("\n== Stage 3: look for an upload-link endpoint")
    out = {}
    for endpoint in UPLOAD_GUESSES:
        resp = await call(api, endpoint, {"sn": sn, "product_code": MODEL})
        out[endpoint] = resp
        print(f"  {endpoint} -> {'OK' if resp['ok'] else str(resp.get('msg'))[:120]}")
    return out


async def main() -> None:
    results: dict[str, Any] = {}
    async with (
        anker_login(RESULTS, results) as (api, sn),
        aiohttp.ClientSession() as downloads,
    ):
        results["read"] = await stage_read(api, downloads, sn)
        items = ((results["read"]["custom_list"].get("data") or {}).get("list")) or []
        results["fields"] = await stage_fields(api, sn, items[0] if items else None)
        results["upload"] = await stage_upload(api, sn)


if __name__ == "__main__":
    asyncio.run(main())
