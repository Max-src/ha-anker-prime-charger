"""Find how the Anker cloud expects the undocumented charger settings calls.

Run it yourself (it asks for your Anker login; nothing is stored):
    powershell -ExecutionPolicy Bypass -File tools\\probe_cloud.ps1

For each test feature it asks before touching anything, then:
  1. sends the "set" call with a candidate request format and the opposite value,
  2. reads the setting back to see whether it really changed,
  3. puts the original value back and checks it.
Optionally it does the same for renaming the charger (renames it to
"<name> (test)" and back).

Results (no email, password or token; serial masked) are printed and written
to tools/probe_results.json.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from common import MODEL, SETTING, anker_login, ask, call, read_settings

from custom_components.anker_prime_charger.solixapi.api import AnkerSolixApi

RESULTS = Path(__file__).with_name("probe_results.json")

# device_setting key -> (label, candidate endpoints)
FEATURES: dict[str, tuple[str, list[str]]] = {
    "compatibility_status": (
        "Maximum compatibility",
        [SETTING + "set_compatibility_status"],
    ),
    "charging_mode_status": (
        "Custom charging mode",
        [SETTING + "set_charging_mode_status"],
    ),
    "charging_device_identity_status": (
        "Charging device identification",
        [
            SETTING + "set_charging_device_identity_status",
            SETTING + "set_charging_device_identity_new_status",
        ],
    ),
}
RENAME_ENDPOINTS = ["app/devicerelation/up_alias_name"]


def payloads(sn: str, key: str, value: int) -> list[dict[str, Any]]:
    """Candidate request bodies, most likely first."""
    return [
        {"device_sn": sn, key: value},
        {"device_sn": sn, "status": value},
        {"device_sn": sn, "status": bool(value)},
        {"device_sn": sn, key: bool(value)},
        {"device_sn": sn, "switch": value},
        {"device_sn": sn, "enable": bool(value)},
    ]


def hide_sn(sn: str, obj: Any) -> str:
    """Printable copy without the serial."""
    return str(obj).replace(sn, "<SN>")


async def probe_feature(api: AnkerSolixApi, sn: str, key: str) -> dict[str, Any]:
    label, endpoints = FEATURES[key]
    settings = await read_settings(api, sn)
    if key not in settings:
        return {
            "feature": key,
            "result": "not reported by the cloud",
            "settings": settings,
        }
    original = int(bool(settings[key]))
    target = 1 - original
    print(f"\n{label}: currently {'ON' if original else 'OFF'}.")
    if not ask(f"Switch it {'ON' if target else 'OFF'} briefly, then back?"):
        return {"feature": key, "result": "skipped"}

    attempts = []
    for endpoint in endpoints:
        for body in payloads(sn, key, target):
            resp = await call(api, endpoint, body)
            after = (await read_settings(api, sn)).get(key)
            changed = after is not None and int(bool(after)) == target
            attempts.append(
                {
                    "endpoint": endpoint,
                    "body": body,
                    "response": resp,
                    "changed": changed,
                }
            )
            print(
                f"  {endpoint.rsplit('/', 1)[-1]} {hide_sn(sn, body)} -> "
                f"{'OK' if resp['ok'] else resp.get('msg')}, changed: {changed}"
            )
            if not changed:
                continue
            # Found it: restore with the same request format
            restore_body = {
                k: (type(v)(original) if k != "device_sn" else v)
                for k, v in body.items()
            }
            restore = await call(api, endpoint, restore_body)
            restored = int(bool((await read_settings(api, sn)).get(key))) == original
            print(f"  restored to {'ON' if original else 'OFF'}: {restored}")
            if not restored:
                print(f"  !! Could not restore {label}. Set it back in the Anker app.")
            return {
                "feature": key,
                "result": "found",
                "endpoint": endpoint,
                "body": body,
                "restore": {
                    "body": restore_body,
                    "response": restore,
                    "restored": restored,
                },
                "attempts": attempts,
            }
    return {"feature": key, "result": "no format worked", "attempts": attempts}


async def probe_rename(api: AnkerSolixApi, sn: str) -> dict[str, Any]:
    dev = api.devices[sn]
    name = dev.get("alias") or dev.get("name") or ""
    print(f"\nCharger name in the Anker app: '{name}'.")
    test_name = f"{name} (test)"
    if not ask(f"Rename it to '{test_name}' briefly, then back?"):
        return {"feature": "rename", "result": "skipped"}
    # The server requires device_sn and alias_name (its 400 errors say so) but
    # answered "(10003) Failed to request" with only those: try extra fields.
    # "<USER_ID>" is filled in at send time and never stored.
    extras: list[dict[str, Any]] = [
        {},
        {"device_pn": MODEL},
        {"product_code": MODEL},
        {"device_pn": MODEL, "product_code": MODEL},
        {"device_name": test_name},
        {"device_pn": MODEL, "device_name": test_name},
        {"user_id": "<USER_ID>"},
    ]
    user_id = api.apisession.get_login_info("user_id") or ""
    attempts = []
    for endpoint in RENAME_ENDPOINTS:
        for extra in extras:
            body = {"device_sn": sn, "alias_name": test_name, **extra}
            sent = {k: user_id if v == "<USER_ID>" else v for k, v in body.items()}
            resp = await call(api, endpoint, sent)
            await api.get_bind_devices()
            changed = api.devices[sn].get("alias") == test_name
            attempts.append(
                {
                    "endpoint": endpoint,
                    "body": body,
                    "response": resp,
                    "changed": changed,
                }
            )
            print(
                f"  {hide_sn(sn, body)} -> {'OK' if resp['ok'] else resp.get('msg')}, "
                f"changed: {changed}"
            )
            if not changed:
                continue
            restore = await call(api, endpoint, {**sent, "alias_name": name})
            await api.get_bind_devices()
            restored = api.devices[sn].get("alias") == name
            print(f"  restored to '{name}': {restored}")
            if not restored:
                print(
                    "  !! Could not restore the name. Rename it back in the Anker app."
                )
            return {
                "feature": "rename",
                "result": "found",
                "endpoint": endpoint,
                "body": body,
                "restore": {"response": restore, "restored": restored},
                "attempts": attempts,
            }
    return {"feature": "rename", "result": "no format worked", "attempts": attempts}


async def main() -> None:
    summary: dict[str, Any] = {}
    async with anker_login(RESULTS, summary) as (api, sn):
        summary["settings_before"] = await read_settings(api, sn)
        print(f"Test feature flags now: {summary['settings_before']}")
        summary["results"] = [await probe_feature(api, sn, key) for key in FEATURES]
        summary["results"].append(await probe_rename(api, sn))
        summary["settings_after"] = await read_settings(api, sn)
        print(f"\nSettings after: {summary['settings_after']}")


if __name__ == "__main__":
    asyncio.run(main())
