"""Find how the Anker cloud expects custom charging profiles to be created and edited.

Run it yourself (it asks for your Anker login; nothing is stored):
    powershell -ExecutionPolicy Bypass -File tools\\probe_profiles.ps1

Stages (the ones that change something ask first and undo their change):
  1. Read-only: your custom profiles with all their fields, and the related
     read-only settings (protocol status, power ranges).
  2. Edit: send your first profile back unchanged to learn the accepted
     request, then rename it to "<name> HA", check, and rename it back.
  3. Create and delete (only with fewer than 4 profiles): create "HA probe"
     as a copy of your first profile, learning the required fields from the
     server's "field X is not set" answers; then delete it the same way.

Results (no email, password or token; serial masked) are printed and written
to tools/probe_profiles_results.json.
"""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

from common import CHARGING, MODEL, SETTING, anker_login, ask, call, discover_fields

RESULTS = Path(__file__).with_name("probe_profiles_results.json")
MAX_PROFILES = 4  # per Anker's user guide


async def list_profiles(api, sn: str) -> list[dict[str, Any]]:
    resp = await call(api, CHARGING + "get_charging_mode_list", {"device_sn": sn})
    return ((resp.get("data") or {}).get("charging_mode_list")) or []


def fill_from(profile: dict[str, Any], sn: str) -> dict[str, Any]:
    """Values for fields the server may ask for, taken from an existing profile."""
    return copy.deepcopy(profile) | {
        "device_sn": sn,
        "sn": sn,
        "mode_id": profile.get("id"),
        "charging_mode_id": profile.get("id"),
        "product_code": MODEL,
        "device_model": MODEL,
    }


async def stage_read(api, sn: str) -> dict[str, Any]:
    print("\n== Stage 1: your custom profiles (read-only)")
    out: dict[str, Any] = {"profiles": await list_profiles(api, sn)}
    for profile in out["profiles"]:
        ports = {
            p.get("name"): p.get("power") for p in profile.get("power_settings") or []
        }
        print(
            f"  #{profile.get('number')} '{profile.get('name')}' (id {profile.get('id')}): {ports}"
        )
    out["protocol_status"] = await call(
        api, SETTING + "get_protocol_status", {"device_sn": sn}
    )
    out["power_range_protocols"] = await call(
        api, SETTING + "get_power_range_support_protocols", {"device_model": MODEL}
    )
    out["port_protocol_status"] = await call(
        api, SETTING + "get_port_protocol_status", {"device_sn": sn}
    )
    return out


async def stage_edit(api, sn: str, profile: dict[str, Any]) -> dict[str, Any]:
    print("\n== Stage 2: edit a profile")
    name = profile.get("name") or ""
    if not ask(f"Rename '{name}' to '{name} HA' briefly, then back?"):
        return {"skipped": "declined"}
    endpoint = CHARGING + "update_charging_mode"
    out: dict[str, Any] = {}
    # a) the profile exactly as the cloud returns it, plus the serial
    body = copy.deepcopy(profile) | {"device_sn": sn}
    out["as_listed"] = await call(api, endpoint, body)
    print(
        f"  unchanged, as listed -> {'OK' if out['as_listed']['ok'] else out['as_listed'].get('msg')}"
    )
    if not out["as_listed"]["ok"]:
        # b) learn the required fields
        out["discover"] = await discover_fields(
            api, endpoint, {}, fill_from(profile, sn)
        )
        if not out["discover"]["steps"][-1]["response"]["ok"]:
            return out
        body = out["discover"]["steps"][-1]["body"]
    out["format"] = sorted(body)
    # rename, check, rename back
    out["rename"] = await call(api, endpoint, body | {"name": f"{name} HA"})
    renamed = any(p.get("name") == f"{name} HA" for p in await list_profiles(api, sn))
    out["renamed"] = renamed
    print(
        f"  rename -> {'OK' if out['rename']['ok'] else out['rename'].get('msg')}, stored: {renamed}"
    )
    out["restore"] = await call(api, endpoint, body | {"name": name})
    restored = any(
        p.get("id") == profile.get("id") and p.get("name") == name
        for p in await list_profiles(api, sn)
    )
    out["restored"] = restored
    print(f"  renamed back: {restored}")
    if not restored:
        print(f"  !! Could not rename it back. Rename it to '{name}' in the Anker app.")
    return out


async def stage_create(api, sn: str, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    print("\n== Stage 3: create and delete a profile")
    if len(profiles) >= MAX_PROFILES:
        print(f"  Skipped: you already have {MAX_PROFILES} profiles (the maximum).")
        return {"skipped": "maximum reached"}
    if not ask("Create a copy of your first profile named 'HA probe', then delete it?"):
        return {"skipped": "declined"}
    template = profiles[0]
    fill = fill_from(template, sn) | {"name": "HA probe"}
    for key in ("id", "mode_id", "charging_mode_id", "number"):
        fill.pop(key, None)
    out: dict[str, Any] = {}
    before = {p.get("id") for p in profiles}
    # a) the listed profile without its id/number, plus the serial
    out["as_listed"] = await call(api, CHARGING + "add_charging_mode", dict(fill))
    print(
        f"  copy as listed -> {'OK' if out['as_listed']['ok'] else out['as_listed'].get('msg')}"
    )
    if not out["as_listed"]["ok"]:
        out["discover"] = await discover_fields(
            api, CHARGING + "add_charging_mode", {}, fill
        )
    created = [p for p in await list_profiles(api, sn) if p.get("id") not in before]
    out["created"] = created
    if not created:
        print("  Nothing was created.")
        return out
    new = created[0]
    print(
        f"  created '{new.get('name')}' (id {new.get('id')}, #{new.get('number')}); deleting it"
    )
    out["delete"] = await discover_fields(
        api,
        CHARGING + "delete_charging_mode",
        {},
        fill_from(new, sn) | {"ids": [new.get("id")], "mode_ids": [new.get("id")]},
    )
    left = [p for p in await list_profiles(api, sn) if p.get("id") not in before]
    out["left_over"] = left
    if left:
        print("  !! Could not delete 'HA probe'. Delete it in the Anker app.")
    else:
        print("  deleted.")
    return out


async def main() -> None:
    results: dict[str, Any] = {}
    async with anker_login(RESULTS, results) as (api, sn):
        results["read"] = await stage_read(api, sn)
        if not (profiles := results["read"]["profiles"]):
            print(
                "\nNo custom profile yet: create one in the app, then run this again."
            )
            return
        results["edit"] = await stage_edit(api, sn, profiles[0])
        results["create"] = await stage_create(api, sn, await list_profiles(api, sn))


if __name__ == "__main__":
    asyncio.run(main())
