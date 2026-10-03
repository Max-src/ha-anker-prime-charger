"""Diagnostics for the Anker Prime Charger integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_SN
from .coordinator import PrimeChargerConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_DEVICE_SN,
    "sn",
    "alias",
    "name",
    "user_id",
    "owner_user_id",
    "auth_token",
    "wifi_name",
    "wifi_mac",
    "bt_ble_id",
    "bt_ble_mac",
    "local_ip",
    "ip_address",
    "site_id",
    "theme_url",
    # custom clock images: signed links with temporary credentials
    "image_url",
    "img_url",
    "short_url",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PrimeChargerConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    cloud = coordinator.cloud
    session = coordinator.api.mqttsession
    mqtt_data = coordinator.device.get("mqtt_data") or {}
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "last_message": _iso(coordinator.last_message),
            "stale_after": str(coordinator.stale_after),
            "fast_updates_until": _iso(coordinator.fast_updates.until),
        },
        "cloud": {
            "last_refresh": _iso(cloud.refreshed),
            "protocol_ranges": cloud.protocol_ranges,
            "unlocked_animations": cloud.easter_eggs,
        },
        "mqtt": {
            "connected": bool(session and session.is_connected()),
            "subscribed": bool(
                coordinator.mqtt_device and coordinator.mqtt_device.is_subscribed()
            ),
            "host": getattr(session, "host", None),
        },
        "device": async_redact_data(
            {k: v for k, v in coordinator.device.items() if k != "mqtt_data"},
            TO_REDACT,
        ),
        "mqtt_data": async_redact_data(dict(mqtt_data), TO_REDACT),
    }


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None
