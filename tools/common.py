"""Shared code of the investigation scripts in tools/.

Each script asks for the Anker login in the terminal (kept in memory only),
deletes the library's login cache when done, and writes its results with the
serial, the account's user id hash and signed links masked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from getpass import getpass
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.anker_prime_charger.solixapi.api import (
    AnkerSolixApi,
)
from custom_components.anker_prime_charger.solixapi.apitypes import (
    API_COUNTRIES,
    API_SERVERS,
)
from custom_components.anker_prime_charger.solixapi.errors import (
    AnkerSolixError,
    AuthorizationError,
    InvalidCredentialsError,
)

MODEL = "A2345"
SETTING = "mini_power/v1/app/setting/"
CHARGING = "mini_power/v1/app/charging/"
MISSING_FIELD = re.compile(r'field \\?"(\w+)\\?" is not set')


def ask(question: str) -> bool:
    """Yes/no question in the terminal (no by default)."""
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def ok(resp: dict[str, Any]) -> str:
    """Short result of a call() for printing."""
    return "OK" if resp.get("ok") else str(resp.get("msg"))[:160]


async def call(
    api: AnkerSolixApi, endpoint: str, body: dict[str, Any]
) -> dict[str, Any]:
    """POST to the cloud, return {"ok", "code", "msg", "data"} instead of raising."""
    try:
        resp = await api.apisession.request("post", endpoint, json=body)
    except (AnkerSolixError, aiohttp.ClientError) as err:
        return {"ok": False, "msg": str(err)}
    return {
        "ok": resp.get("code") == 0,
        "code": resp.get("code"),
        "msg": resp.get("msg"),
        "data": resp.get("data"),
    }


async def read_settings(api: AnkerSolixApi, sn: str) -> dict[str, Any]:
    """The charger's cloud settings flags (test features, ...)."""
    resp = await api.get_charger_device_setting(deviceSn=sn)
    return resp.get("device_setting") or {}


async def discover_fields(
    api: AnkerSolixApi, endpoint: str, start: dict[str, Any], fill: dict[str, Any]
) -> dict[str, Any]:
    """Learn a request's fields from the server's "field X is not set" answers.

    Adds the named field (value from `fill`, or fill["*"]) and retries; stops
    at success or any other answer.
    """
    body = dict(start)
    steps = []
    for _ in range(12):
        resp = await call(api, endpoint, body)
        steps.append({"body": dict(body), "response": resp})
        missing = MISSING_FIELD.search(str(resp.get("msg", "")))
        print(f"  {endpoint.rsplit('/', 1)[-1]} {list(body)} -> {ok(resp)}")
        if resp["ok"] or not missing or missing.group(1) in body:
            break
        body[missing.group(1)] = fill.get(missing.group(1), fill.get("*", ""))
    return {"final_body_fields": list(body), "steps": steps}


async def login(
    session: aiohttp.ClientSession, email: str, password: str
) -> tuple[AnkerSolixApi, str]:
    """Log in on the server that has the charger; return (api, serial)."""
    quiet = logging.getLogger("tools")
    quiet.setLevel(logging.ERROR)
    first = AnkerSolixApi(email, password, "US", session, quiet)
    await first.async_authenticate(restart=True)
    country = (first.apisession.get_login_info("country_code") or "US").upper()
    default = next((r for r, cs in API_COUNTRIES.items() if country in cs), "eu")
    for server in [default, *(s for s in API_SERVERS if s != default)]:
        api = AnkerSolixApi(email, password, country, session, quiet)
        api.apisession._api_base = API_SERVERS[server]
        api.apisession._region = server
        await api.async_authenticate(restart=True)
        await api.get_bind_devices()
        for sn, dev in api.devices.items():
            if dev.get("device_pn") == MODEL:
                print(f"Found the charger on the '{server}' server ({country}).")
                return api, sn
    raise SystemExit("No Prime Charger 250W (A2345) found on this account.")


def mask(api: AnkerSolixApi, sn: str, obj: Any) -> Any:
    """Copy of `obj` without the serial, the user id hash or signed link parts."""
    text = json.dumps(obj, ensure_ascii=False)
    text = text.replace(sn, "<SN>").replace(sn.encode().hex(), "<SN-HEX>")
    if gtoken := api.apisession._gtoken:
        text = text.replace(gtoken, "<USER>").replace(
            gtoken.encode().hex(), "<USER-HEX>"
        )
    text = re.sub(r"(https?://[^\"?\s]+)\?[^\"\s]*", r"\1?<signed>", text)
    return json.loads(text)


@asynccontextmanager
async def anker_login(
    results_path: Path, results: dict[str, Any]
) -> AsyncIterator[tuple[AnkerSolixApi, str]]:
    """Ask for the login, log in, and on exit save `results` (masked) and log out.

    The library's login cache is deleted so no token is left on disk.
    """
    email = input("Anker account email: ").strip()
    password = getpass("Anker password (not shown): ")
    async with aiohttp.ClientSession() as session:
        try:
            api, sn = await login(session, email, password)
        except (AuthorizationError, InvalidCredentialsError) as err:
            # Stop at once: repeated failed logins can lock the account
            raise SystemExit(f"Login failed, nothing was changed: {err}") from None
        try:
            yield api, sn
        finally:
            results_path.write_text(
                json.dumps(mask(api, sn, results), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\nResults written to {results_path}")
            api.stopMqttSession()
            Path(api.apisession._authFile).unlink(missing_ok=True)
