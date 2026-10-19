"""Repair issues of the Anker Prime Charger integration (Settings > Repairs).

Raised for problems only the user can fix, and removed once they are gone:

- charger_not_found: the charger is no longer in the Anker account (removed
  from it, or moved to another account). Setup keeps retrying meanwhile.
- charger_offline: no message from the charger for OFFLINE_AFTER (unplugged,
  off Wi-Fi, or Home Assistant can't reach the Anker cloud). The entities are
  unavailable meanwhile.

A bad login has no issue here: Home Assistant asks for it (reauthentication).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

CHARGER_NOT_FOUND: Final = "charger_not_found"
CHARGER_OFFLINE: Final = "charger_offline"
OFFLINE_AFTER: Final = timedelta(hours=1)

# entry id -> when the charger was last heard from, or first found silent;
# kept across setup retries (a charger offline at startup never sends one)
DATA_SILENT_SINCE: HassKey[dict[str, datetime]] = HassKey(f"{DOMAIN}_silent_since")

SEVERITY: Final = {
    CHARGER_NOT_FOUND: ir.IssueSeverity.ERROR,
    CHARGER_OFFLINE: ir.IssueSeverity.WARNING,
}


def _issue_id(kind: str, entry: ConfigEntry) -> str:
    return f"{kind}_{entry.entry_id}"


@callback
def silent_since(hass: HomeAssistant, entry: ConfigEntry) -> datetime:
    """When the charger was last heard from (now, the first time)."""
    return hass.data.setdefault(DATA_SILENT_SINCE, {}).setdefault(
        entry.entry_id, dt_util.utcnow()
    )


@callback
def async_heard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A message from the charger: restart the count, remove the offline issue."""
    hass.data.setdefault(DATA_SILENT_SINCE, {})[entry.entry_id] = dt_util.utcnow()
    async_clear(hass, entry, CHARGER_OFFLINE)


@callback
def async_check_offline(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise the offline issue after OFFLINE_AFTER without a message."""
    since = silent_since(hass, entry)
    if dt_util.utcnow() - since >= OFFLINE_AFTER:
        local = dt_util.as_local(since).strftime("%Y-%m-%d %H:%M")
        async_raise(hass, entry, CHARGER_OFFLINE, since=local)


@callback
def async_raise(
    hass: HomeAssistant, entry: ConfigEntry, kind: str, **placeholders: str
) -> None:
    """Show the issue (once: raising it again only updates it)."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(kind, entry),
        is_fixable=False,
        severity=SEVERITY[kind],
        translation_key=kind,
        translation_placeholders={"name": entry.title, **placeholders},
    )


@callback
def async_clear(hass: HomeAssistant, entry: ConfigEntry, *kinds: str) -> None:
    """Remove the issues (nothing happens for those not shown)."""
    for kind in kinds or tuple(SEVERITY):
        ir.async_delete_issue(hass, DOMAIN, _issue_id(kind, entry))
