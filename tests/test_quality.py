"""Repair issues, device addresses, icons and platform settings."""

from __future__ import annotations

from datetime import timedelta
import importlib
import json
from pathlib import Path
import re

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
import yaml

from custom_components.anker_prime_charger import PLATFORMS, issues
from custom_components.anker_prime_charger.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from .conftest import DEVICE, SN, FakeCloud
from .helpers import device_id

COMPONENT = Path(__file__).parents[1] / "custom_components" / DOMAIN
# Translation keys used only for icons (the port switches take the port's name)
ICON_ONLY_KEYS = {"usb_c_port", "usb_a_port"}


def issue(
    hass: HomeAssistant, kind: str, entry: MockConfigEntry
) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{kind}_{entry.entry_id}")


async def wait(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta
) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_missing_charger_raises_an_issue_until_it_is_back(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """A charger missing from the account shows a repair issue, gone once it's back."""
    cloud.devices = []
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    found = issue(hass, "charger_not_found", entry)
    assert found is not None
    assert found.translation_placeholders == {"name": entry.title, "serial": SN}

    cloud.devices = [dict(DEVICE)]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert issue(hass, "charger_not_found", entry) is None


async def test_offline_issue_after_an_hour_of_silence(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """No message for an hour shows a repair issue; the next message removes it."""
    await wait(hass, freezer, timedelta(minutes=59))
    assert issue(hass, "charger_offline", setup_entry) is None

    await wait(hass, freezer, timedelta(minutes=2))
    offline = issue(hass, "charger_offline", setup_entry)
    assert offline is not None
    assert offline.severity is ir.IssueSeverity.WARNING
    assert "since" in offline.translation_placeholders

    cloud.mqtt.pending_reply = {"usbc_1_power": 12.0}
    await wait(hass, freezer, timedelta(seconds=30))
    assert issue(hass, "charger_offline", setup_entry) is None


async def test_offline_issue_when_silent_from_startup(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """A charger offline since Home Assistant started also gets the issue.

    Setup keeps failing (no first status), so the silence counts from the
    first attempt. Backdated instead of waiting: with the clock frozen, the
    first-status timeout would never end.
    """
    cloud.charger_silent = True
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert issue(hass, "charger_offline", entry) is None

    hass.data[issues.DATA_SILENT_SINCE][entry.entry_id] -= timedelta(hours=1)
    await hass.config_entries.async_reload(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert issue(hass, "charger_offline", entry) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    assert issue(hass, "charger_offline", entry) is None


async def test_device_has_its_addresses(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """The charger's Wi-Fi and Bluetooth addresses are device connections."""
    cloud.devices[0] |= {"wifi_mac": "AABBCCDDEEFF", "bt_ble_mac": "112233445566"}
    await hass.config_entries.async_setup(entry.entry_id)
    device = dr.async_get(hass).async_get(device_id(hass))
    assert device is not None
    assert device.connections == {
        (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff"),
        (dr.CONNECTION_BLUETOOTH, "11:22:33:44:55:66"),
    }


def test_every_platform_sets_parallel_updates() -> None:
    """Read-only platforms 0, platforms that send commands 1."""
    read_only = {"binary_sensor", "event", "sensor"}
    for platform in PLATFORMS:
        module = importlib.import_module(f"custom_components.{DOMAIN}.{platform}")
        assert (0 if platform in read_only else 1) == module.PARALLEL_UPDATES, platform


def test_icons_match_entities_and_actions() -> None:
    """Every icon is for an existing entity (and state) or action, none missing."""
    icons = json.loads((COMPONENT / "icons.json").read_text(encoding="utf-8"))
    strings = json.loads(
        (COMPONENT / "translations" / "en.json").read_text(encoding="utf-8")
    )
    for platform, entities in icons["entity"].items():
        for key, icon in entities.items():
            if key in ICON_ONLY_KEYS:
                continue
            translated = strings["entity"][platform].get(key)
            assert translated is not None, f"{platform}.{key}"
            states = set(icon.get("state", {})) - {"on", "off"}
            assert states <= set(translated.get("state", {})), f"{platform}.{key}"
    actions = yaml.safe_load((COMPONENT / "services.yaml").read_text(encoding="utf-8"))
    assert set(icons["services"]) == set(actions)


def test_translations_contain_no_html() -> None:
    """Hassfest rejects angle-bracket text in translation strings."""
    strings = (COMPONENT / "translations" / "en.json").read_text(encoding="utf-8")
    assert not re.findall(r"<[^>\n]*>", strings)
