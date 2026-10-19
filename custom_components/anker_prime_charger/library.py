"""The only module that touches the vendored Anker library's internals.

Everything else uses the library's public methods, or the helpers here. When
the library is updated, check this module (and mqtt_extensions.py); the
library contract tests (tests/test_library_contract.py) fail if something we
rely on changed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_COUNTRY, LOGGER, TEST_FEATURES
from .solixapi.api import AnkerSolixApi
from .solixapi.apitypes import API_ENDPOINTS, API_SERVERS

# Anker cloud endpoints used without a library helper
ENDPOINTS: Final = {
    # {"device_sn"} -> {"egg_trigger_list": [{"egg_type", "trigger_time", "status"}]}
    "easter_eggs": API_ENDPOINTS["charger_get_triggers"],
    # {"device_model"} -> protocols per USB-C port and power range
    "power_range_protocols": "mini_power/v1/app/setting/get_power_range_support_protocols",
    # custom profiles (found by probing the cloud)
    "update_charging_mode": "mini_power/v1/app/charging/update_charging_mode",
    "add_charging_mode": "mini_power/v1/app/charging/add_charging_mode",
    "delete_charging_mode": "mini_power/v1/app/charging/delete_charging_mode",
    # custom clock images (from the decompiled app, verified with
    # probing the cloud; see clock_images.py)
    "upload_token": "app/cloudstor/get_app_up_token_general",
    "add_custom_theme": "mini_power/v1/app/style/add_manual_clock_screensavers",
    "rename_custom_theme": "mini_power/v1/app/style/set_manual_clock_screensaver_name",
    "delete_custom_theme": "mini_power/v1/app/style/delete_manual_clock_screensavers",
    "theme_url": "mini_power/v1/app/style/get_url",
} | TEST_FEATURES


def create_api(
    hass: HomeAssistant, data: Mapping[str, Any], server: str | None = None
) -> AnkerSolixApi:
    """Create the API client, optionally forcing the server ("eu" or "com").

    The library picks the server from the country code, but only knows a
    subset of countries and falls back to the EU server for the rest (e.g. SG).
    An account only sees its devices on its home server, so allow overriding.
    """
    api = AnkerSolixApi(
        data[CONF_EMAIL],
        data[CONF_PASSWORD],
        data[CONF_COUNTRY],
        async_get_clientsession(hass),
        LOGGER,
    )
    if server in API_SERVERS:
        api.apisession._api_base = API_SERVERS[server]  # noqa: SLF001
        api.apisession._region = server  # noqa: SLF001
    return api


async def async_request(
    api: AnkerSolixApi, endpoint: str, body: dict[str, Any]
) -> dict[str, Any]:
    """POST to an Anker cloud endpoint (a key of ENDPOINTS); return the "data".

    Raises the library's errors (AnkerSolixError, aiohttp's ClientError) on
    failure.
    """
    resp = await api.apisession.request("post", ENDPOINTS[endpoint], json=body)
    return resp.get("data") or {}


async def async_read_custom_themes(api: AnkerSolixApi, sn: str) -> list[dict[str, Any]]:
    """Read the charger's custom clock images into the library's cache.

    Returns the cloud's list as is: the library keeps only some fields (not
    "seq"). It also ignores an empty list, so the images deleted last would
    stay listed: clear them then.
    """
    data = await api.get_charger_manual_screensavers(deviceSn=sn)
    items = list((data or {}).get("list") or [])
    if not items and sn in api.devices:
        api.devices[sn]["screensaver"] = {}
    return items


def store_stock_themes(api: AnkerSolixApi, model: str, themes: dict[str, Any]) -> None:
    """Put the stock theme catalogue where the library's theme lookup reads it."""
    screensavers = dict(api.account.get("screensaver") or {})
    screensavers[model] = {"themes": themes}
    api._update_account({"screensaver": screensavers})  # noqa: SLF001
