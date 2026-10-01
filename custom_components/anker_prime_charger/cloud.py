"""Settings of the charger that live in the Anker cloud, not on the charger.

The theme catalogue, custom images, custom charging profiles, test features,
port labels, unlocked hidden animations and the protocols allowed per power.
They change rarely (usually from the app), so they are read every
REFRESH_INTERVAL, in the background: a slow or failing cloud never delays or
fails the charger's status polls.

The library keeps most of them in its device dict (api.devices[sn]):
"device_setting", "custom_modes", "port_remarks" and "screensaver" (custom
images). The rest is kept here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, Final

from aiohttp import ClientError

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import library, themes
from .const import LOGGER, MODEL
from .solixapi.api import AnkerSolixApi
from .solixapi.errors import AnkerSolixError

REFRESH_INTERVAL: Final = timedelta(minutes=10)
STOCK_THEMES_INTERVAL: Final = timedelta(days=1)
CLOUD_ERRORS: Final = (ClientError, TimeoutError, AnkerSolixError)

# Protocol labels of the cloud (as seen for this charger; no Huawei) -> the
# library's protocol names
PROTOCOL_LABELS: Final = {
    "SCP": "scp",
    "UFCS": "ufcs",
    "PD 12V": "pd12v",
    "5-11V PPS": "pps11v",
    "5-16V PPS": "pps16v",
    "4.5-21V PPS": "pps20v",
    "Support Xiaomi HyperCharge": "xiaomi",
}

type ProtocolRanges = dict[str, list[tuple[int, int, list[str]]]]


class CloudSettings:
    """Reads and changes the charger's settings in the Anker cloud."""

    def __init__(self, api: AnkerSolixApi, device_sn: str) -> None:
        """Initialize."""
        self.api = api
        self.device_sn = device_sn
        self.refreshed: datetime | None = None
        self._stock_themes_refreshed: datetime | None = None
        # Unlocked hidden animations: [{"egg_type", "trigger_time", "status"}]
        self.easter_eggs: list[dict[str, Any]] | None = None
        # USB-C port ("c1") -> [(min W, max W, [protocol names])]
        self.protocol_ranges: ProtocolRanges = {}

    @property
    def _device(self) -> dict[str, Any]:
        return self.api.devices.get(self.device_sn) or {}

    @property
    def device_settings(self) -> dict[str, Any]:
        """The test feature flags ({"compatibility_status": 0, ...})."""
        return self._device.get("device_setting") or {}

    @property
    def profiles(self) -> dict[str, dict[str, Any]]:
        """Saved custom charging profiles by id."""
        return self._device.get("custom_modes") or {}

    @property
    def port_labels(self) -> list[dict[str, Any]] | None:
        """[{"port_name": "C1", "remark": "MacBook"}, ...]; None until read."""
        if "port_remarks" not in self._device:
            return None
        return self._device.get("port_remarks") or []

    def refresh_due(self) -> bool:
        """Whether the settings are older than REFRESH_INTERVAL."""
        return (
            self.refreshed is None
            or dt_util.utcnow() - self.refreshed >= REFRESH_INTERVAL
        )

    async def async_refresh(self) -> None:
        """Read everything. Each failing read is logged and the others go on."""
        now = dt_util.utcnow()
        self.refreshed = now
        api, sn = self.api, self.device_sn
        reads: list[tuple[str, Callable[[], Awaitable[Any]]]] = [
            ("test features", lambda: api.get_charger_device_setting(deviceSn=sn)),
            ("custom profiles", lambda: api.get_charger_custom_mode_list(deviceSn=sn)),
            ("port labels", lambda: api.get_charger_port_remarks(deviceSn=sn)),
            ("custom images", lambda: api.get_charger_manual_screensavers(deviceSn=sn)),
            ("unlocked animations", self._async_read_easter_eggs),
            ("protocols per power", self._async_read_protocol_ranges),
        ]
        if (
            self._stock_themes_refreshed is None
            or now - self._stock_themes_refreshed >= STOCK_THEMES_INTERVAL
        ):
            reads.append(("stock themes", self._async_read_stock_themes))
        for what, read in reads:
            try:
                await read()
            except CLOUD_ERRORS as err:
                LOGGER.warning(
                    "Could not read the %s from the Anker cloud: %s", what, err
                )
            except Exception:  # noqa: BLE001  (an unexpected answer must not stop the rest)
                LOGGER.exception(
                    "Unexpected answer from the Anker cloud for the %s", what
                )
        themes.name_unnamed_custom_themes(self._device.get("screensaver") or {})

    async def _async_read_easter_eggs(self) -> None:
        data = await library.async_request(
            self.api, "easter_eggs", {"device_sn": self.device_sn}
        )
        self.easter_eggs = list(data.get("egg_trigger_list") or [])

    async def _async_read_protocol_ranges(self) -> None:
        data = await library.async_request(
            self.api, "power_range_protocols", {"device_model": MODEL}
        )
        ranges: ProtocolRanges = {}
        for port in data.get("port_list") or []:
            ranges[str(port.get("port", "")).lower()] = [
                (
                    int(item.get("min_power") or 0),
                    int(item.get("max_power") or 0),
                    [
                        PROTOCOL_LABELS[label]
                        for label in item.get("protocols") or []
                        if label in PROTOCOL_LABELS
                    ],
                )
                for item in port.get("power_range_protocols_mapping") or []
            ]
        if ranges:
            self.protocol_ranges = ranges

    async def _async_read_stock_themes(self) -> None:
        catalogue = await self.api.get_charger_screensavers(devicePn=MODEL)
        if stock := themes.parse_stock_catalogue(catalogue):
            library.store_stock_themes(self.api, MODEL, stock)
            self._stock_themes_refreshed = dt_util.utcnow()

    async def async_set_test_feature(self, key: str, enabled: bool) -> None:
        """Turn a test feature on or off, then read the flags back."""
        try:
            await library.async_request(
                self.api, key, {"device_sn": self.device_sn, key: int(enabled)}
            )
            await self.api.get_charger_device_setting(deviceSn=self.device_sn)
        except CLOUD_ERRORS as err:
            raise HomeAssistantError(f"Anker cloud error: {err}") from err

    async def async_set_port_label(self, port_name: str, label: str) -> None:
        """Store a port label ("C1" ... "A2"), then check it was stored."""
        try:
            resp = await self.api.set_charger_port_remark(
                deviceSn=self.device_sn, portName=port_name, remark=label
            )
        except CLOUD_ERRORS as err:
            raise HomeAssistantError(f"Anker cloud error: {err}") from err
        if resp is False:
            raise HomeAssistantError(f"The Anker cloud rejected the {port_name} label")
        stored = next(
            (
                item.get("remark") or ""
                for item in self.port_labels or []
                if item.get("port_name") == port_name
            ),
            "",
        )
        if stored != label:
            raise HomeAssistantError(
                f"The Anker cloud accepted the {port_name} label but still reports {stored!r}"
            )

    async def async_profile_request(self, endpoint: str, body: dict[str, Any]) -> None:
        """Create, update or delete a custom profile, then read the profiles back."""
        try:
            await library.async_request(self.api, endpoint, body)
            await self.api.get_charger_custom_mode_list(deviceSn=self.device_sn)
        except CLOUD_ERRORS as err:
            raise HomeAssistantError(f"Anker cloud error: {err}") from err
