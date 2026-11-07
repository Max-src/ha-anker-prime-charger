"""The only module that touches the vendored Anker library's internals.

Everything else uses the library's public methods, or the helpers here. When
the library is updated, check this module (and mqtt_extensions.py); the
library contract tests (tests/test_library_contract.py) fail if something we
rely on changed.
"""

from __future__ import annotations

from collections.abc import Mapping
import contextlib
import hashlib
from pathlib import Path
from typing import Any, Final

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_COUNTRY, DOMAIN, LOGGER, TEST_FEATURES
from .solixapi.api import AnkerSolixApi
from .solixapi.apitypes import API_ENDPOINTS, API_SERVERS
from .solixapi.mqtt import AnkerSolixMqttSession, MessageCallback
from .solixapi.mqtttypes import DeviceHexDataHeader

# The library's own login cache folder (inside the integration): only cleaned up
LIBRARY_CACHE_DIR: Final = Path(__file__).parent / "solixapi" / "authcache"
# MQTT certificate files the library writes per account
MQTT_CERT_FILES: Final = ("aws_root_ca1_pem", "certificate_pem", "private_key")

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
    # custom clock images (verified by probing the cloud; see clock_images.py)
    "upload_token": "app/cloudstor/get_app_up_token_general",
    "add_custom_theme": "mini_power/v1/app/style/add_manual_clock_screensavers",
    "rename_custom_theme": "mini_power/v1/app/style/set_manual_clock_screensaver_name",
    "delete_custom_theme": "mini_power/v1/app/style/delete_manual_clock_screensavers",
    "theme_url": "mini_power/v1/app/style/get_url",
} | TEST_FEATURES


def storage_dir(hass: HomeAssistant) -> Path:
    """Where the login cache and the MQTT certificates go (.storage/<domain>).

    Not the library's folder inside the integration: that one is replaced on
    every update of the integration (a new login each time), and holds a
    token and a private key next to the code.
    """
    return Path(hass.config.path(".storage", DOMAIN))


def _account_key(email: str) -> str:
    """A file name part for the account, without the email address in it."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def create_api(
    hass: HomeAssistant, data: Mapping[str, Any], server: str | None = None
) -> AnkerSolixApi:
    """Create the API client, optionally forcing the server ("eu" or "com").

    The library picks the server from the country code, but only knows a
    subset of countries and falls back to the EU server for the rest (e.g. SG).
    An account only sees its devices on its home server, so allow overriding.

    Does file system work (the library creates its cache folder): call it in
    the executor, or use async_create_api.
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
    folder = storage_dir(hass)
    folder.mkdir(parents=True, exist_ok=True)
    api.apisession._authFile = str(  # noqa: SLF001
        folder / f"auth_{_account_key(data[CONF_EMAIL])}.json"
    )
    _remove_library_cache(data[CONF_EMAIL])
    return api


async def async_create_api(
    hass: HomeAssistant, data: Mapping[str, Any], server: str | None = None
) -> AnkerSolixApi:
    """create_api, run in the executor."""
    return await hass.async_add_executor_job(create_api, hass, data, server)


def remove_login_cache(hass: HomeAssistant, email: str) -> None:
    """Delete the account's login cache (when its last entry is removed)."""
    path = storage_dir(hass) / f"auth_{_account_key(email)}.json"
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def _remove_library_cache(email: str) -> None:
    """Delete what earlier versions left in the library's folder (a token, keys)."""
    names = [f"{email}.json", *(f"{email}_mqtt_{c}.crt" for c in MQTT_CERT_FILES)]
    for name in names:
        with contextlib.suppress(OSError):
            (LIBRARY_CACHE_DIR / name).unlink(missing_ok=True)


async def async_start_mqtt(
    hass: HomeAssistant, api: AnkerSolixApi, message_callback: MessageCallback
) -> AnkerSolixMqttSession | None:
    """Start the MQTT session (connect, register the callback).

    The session is created here first so its certificate files go to
    storage_dir (the library writes them for the session's lifetime).
    """
    if api.mqttsession is None:
        api.mqttsession = await hass.async_add_executor_job(
            _new_mqtt_session, hass, api
        )
    return await api.startMqttSession(message_callback=message_callback)


def _new_mqtt_session(hass: HomeAssistant, api: AnkerSolixApi) -> AnkerSolixMqttSession:
    # (the constructor creates the library's folder: file system work)
    session = AnkerSolixMqttSession(apisession=api.apisession)
    session._auth_cache_dir = storage_dir(hass)  # noqa: SLF001
    return session


async def async_stop_mqtt(hass: HomeAssistant, api: AnkerSolixApi) -> None:
    """Stop the MQTT session for good, keeping the devices' values.

    paho's network thread is stopped in the executor (it is joined). The
    library's own cleanup leaves it running when the connection is down (it
    only stops a connected client), and drops every device's values.
    """
    if (session := api.mqttsession) is None:
        return
    kept = {
        sn: dev["mqtt_data"] for sn, dev in api.devices.items() if "mqtt_data" in dev
    }
    await hass.async_add_executor_job(_stop_mqtt, api, session)
    for sn, values in kept.items():
        if sn in api.devices:
            api.devices[sn]["mqtt_data"] = values


def _stop_mqtt(api: AnkerSolixApi, session: AnkerSolixMqttSession) -> None:
    if (client := session.client) is not None:
        client.disconnect()
        client.loop_stop()
    api.stopMqttSession()


def message_type(data: Any) -> str:
    """The type of a received message ("0303", "0a00", ...); "" if unknown."""
    if isinstance(data, bytes | bytearray) and len(data) >= 9:
        return DeviceHexDataHeader(hexbytes=data).msgtype.hex()
    return ""


def account_id(api: AnkerSolixApi) -> str | None:
    """The account's user id (sent to the charger as the app does)."""
    user_id = api.apisession.get_login_info("user_id")
    return user_id if isinstance(user_id, str) and user_id else None


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
