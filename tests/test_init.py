"""Setup, unload and failure handling."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.anker_prime_charger import library
from custom_components.anker_prime_charger.const import DOMAIN
from custom_components.anker_prime_charger.solixapi import errors
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .conftest import EMAIL, SN, FakeCloud
from .helpers import entity_id, state


async def test_setup_and_unload(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Setup connects MQTT, subscribes and polls; unload disconnects."""
    assert setup_entry.state is ConfigEntryState.LOADED
    mqtt = cloud.mqtt
    assert mqtt.subscriptions == {f"dt/anker_power/A2345/{SN}/#"}
    # the first poll: status request, then theme request (time display)
    # status, theme, firmware versions
    assert mqtt.published_types == ["0200", "0202", "0030"]
    assert (
        hass.states.get(entity_id(hass, "sensor", "total_output_power")).state == "10.8"
    )

    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    assert not mqtt.connected
    assert cloud.api.mqttsession is None


async def test_setup_uses_stored_server(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """The server found during setup is used, not the country default (SG -> eu)."""
    assert cloud.api.apisession.region == "com"


async def test_setup_auth_failure_starts_reauth(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """Rejected credentials put the entry in error and start a reauth flow."""
    cloud.bind_error = errors.AuthorizationError("expired")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_setup_retries_when_cloud_down(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """Network problems are retried later."""
    cloud.bind_error = errors.ConnectError("down")
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retries_when_charger_missing(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """A charger missing from the account is retried later."""
    cloud.devices = []
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retries_when_charger_silent(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """No answer to the first status request is retried later."""
    cloud.charger_silent = True
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_stale_data_marks_unavailable_then_recovers(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entities go unavailable when the charger stops answering, and come back."""
    power = entity_id(hass, "sensor", "usbc_1_power")
    switch = entity_id(hass, "switch", "usbc_1_switch")
    assert hass.states.get(power).state == "6.3"

    # Charger goes silent. Polls within the stale window keep the values.
    async def poll() -> None:
        freezer.tick(timedelta(seconds=30))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    for _ in range(2):
        await poll()
    assert hass.states.get(power).state == "6.3"

    # Third unanswered poll: the last message is now just over 90 s old
    # (it arrived slightly before the poll clock started), so it's stale.
    await poll()
    assert hass.states.get(power).state == STATE_UNAVAILABLE
    assert hass.states.get(switch).state == STATE_UNAVAILABLE

    # The charger answers again.
    cloud.mqtt.pending_reply = {"usbc_1_power": 12.0}
    await poll()
    assert hass.states.get(power).state == "12.0"
    assert hass.states.get(switch).state == "on"


async def test_messages_keep_the_poll_schedule(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """Messages between polls (e.g. fast updates) don't postpone the next status request."""
    coordinator = setup_entry.runtime_data
    scheduled = coordinator._unsub_refresh
    assert scheduled is not None
    cloud.mqtt.deliver({"usbc_1_power": 5.0})
    await hass.async_block_till_done()
    assert state(hass, "sensor", "usbc_1_power") == "5.0"
    assert coordinator._unsub_refresh is scheduled


async def test_unchanged_messages_dont_update_entities(
    hass: HomeAssistant, cloud: FakeCloud, setup_entry: MockConfigEntry
) -> None:
    """A message that changes no value (only its timestamp) doesn't notify entities."""
    coordinator = setup_entry.runtime_data
    updates = []
    unsub = coordinator.async_add_listener(lambda: updates.append(1))
    cloud.mqtt.deliver({"usbc_1_power": 9.0})
    await hass.async_block_till_done()
    assert len(updates) == 1
    cloud.mqtt.deliver({"usbc_1_power": 9.0})
    await hass.async_block_till_done()
    assert len(updates) == 1
    unsub()


async def test_mqtt_subscription_failure_retries(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """A subscription paho refuses fails the setup, which Home Assistant retries."""
    cloud.subscribe_error = 4  # MQTT_ERR_NO_CONN
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "failed: 4" in entry.reason


async def test_login_cache_in_storage(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """The login cache goes to .storage, without the email in its name.

    What earlier versions left in the library's folder is deleted; the cache
    goes with the account's last entry.
    """
    old = library.LIBRARY_CACHE_DIR / f"{EMAIL}.json"

    def leave_old_cache() -> None:
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text("{}", encoding="utf-8")

    await hass.async_add_executor_job(leave_old_cache)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not await hass.async_add_executor_job(old.exists)

    auth = Path(cloud.api.apisession._authFile)
    assert auth.parent == Path(hass.config.path(".storage", DOMAIN))
    assert EMAIL not in auth.name
    await hass.async_add_executor_job(auth.write_text, "{}")
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not await hass.async_add_executor_job(auth.exists)


async def test_mqtt_reconnects_after_disconnect(
    hass: HomeAssistant,
    cloud: FakeCloud,
    setup_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A dropped connection is left to paho for a while, then replaced.

    Meanwhile the values stay (while fresh); the new session subscribes again.
    """
    first = cloud.mqtt
    first.connected = False
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert cloud.api.startMqttSession.await_count == 1  # paho is reconnecting
    assert state(hass, "sensor", "usbc_1_power") == "6.3"

    for _ in range(3):  # 90 s later: paho didn't manage
        freezer.tick(timedelta(seconds=30))
        async_fire_time_changed(hass)
        # (the poll stops paho in the executor)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert cloud.api.startMqttSession.await_count == 2
    assert cloud.mqtt is not first
    assert cloud.mqtt.connected
    assert cloud.mqtt.subscriptions == {f"dt/anker_power/A2345/{SN}/#"}
    assert state(hass, "sensor", "usbc_1_power") == "6.3"
