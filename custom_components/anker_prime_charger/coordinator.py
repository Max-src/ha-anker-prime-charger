"""Coordinator for the Anker Prime Charger integration.

The charger is not reachable locally and the Anker cloud REST API has no live
data for it. Live data and controls go through Anker's cloud MQTT broker:
- we subscribe to the charger's topics,
- every poll we publish a "status request", which makes the charger reply
  with a full status message (ports, switches, display settings, ...),
- the vendored library decodes the binary messages into a flat dict stored at
  api.devices[sn]["mqtt_data"], and calls our callbacks.

Messages arrive on paho's network thread; they are handed to the event loop
before the library stores them, so the cache is only touched from the loop.
Values that arrive between polls are pushed to the entities without moving
the poll schedule (a message every second during fast updates must not
postpone the status requests), once per message, and only when a value
changed.

Settings that live in the Anker cloud are handled by cloud.CloudSettings,
refreshed in the background.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .cloud import CloudSettings
from .const import (
    CONF_FAST_UPDATES_MINUTES,
    CONF_SCAN_INTERVAL,
    DEFAULT_FAST_UPDATES_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MODEL_NAME,
)
from .helpers import to_int, translated
from .mqtt_extensions import EASTER_EGG_STATE, EXTRA_STATE_KEYS
from .solixapi.api import AnkerSolixApi
from .solixapi.mqtt_charger import SolixMqttDeviceCharger
from .solixapi.mqttcmdmap import SolixMqttCommands

type PrimeChargerConfigEntry = ConfigEntry[PrimeChargerCoordinator]

# How long the first refresh waits for the charger to answer the status request
FIRST_DATA_TIMEOUT: Final = 15
# Entities go unavailable after this many polls without any MQTT message,
# but never sooner than MIN_STALE_TIME (short intervals + cloud latency).
STALE_POLLS: Final = 3
MIN_STALE_TIME: Final = timedelta(seconds=90)
# The theme message (theme link, time display) only comes when asked, and only
# changes with a theme command or from the app: ask on every Nth poll.
THEME_REQUEST_POLLS: Final = 10
# Keys the library changes on every message: not a change of the charger's values
MESSAGE_KEYS: Final = ("last_update",)
# This charger's real-time trigger lasts 10 s (measured: 10 messages, one per
# second), so it is resent every 8 s while fast updates are on.
FAST_UPDATE_INTERVAL: Final = timedelta(seconds=8)


class PrimeChargerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keep the MQTT session alive, poll the status and push it to entities."""

    config_entry: PrimeChargerConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PrimeChargerConfigEntry,
        api: AnkerSolixApi,
        device_sn: str,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{device_sn}",
            # a poll mostly returns what we have (the reply comes as a message)
            always_update=False,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.api = api
        self.device_sn = device_sn
        self.cloud = CloudSettings(api, device_sn)
        # The charger's device in the device registry (set at setup); the port
        # devices are its child devices
        self.charger_device_id = ""
        self.mqtt_device: SolixMqttDeviceCharger | None = None
        self.last_message: datetime | None = None
        self._got_data = asyncio.Event()
        self._polls = 0
        self._cloud_task: asyncio.Task[None] | None = None
        self._egg_listeners: set[Callable[[int], None]] = set()
        # While the library handles a message: whether it reported new values
        self._in_message = False
        self._message_changed = False
        # Fast updates: the real-time trigger, resent until fast_updates_until
        self.fast_updates_until: datetime | None = None
        self._fast_unsubs: list[CALLBACK_TYPE] = []
        self._fast_error_logged = False

    @property
    def device(self) -> dict[str, Any]:
        """The library's entry for the charger (name, firmware, cloud settings)."""
        return self.api.devices.get(self.device_sn) or {}

    @property
    def charger_name(self) -> str:
        """The charger's name in the Anker app."""
        return self.device.get("alias") or self.device.get("name") or MODEL_NAME

    # --- MQTT -----------------------------------------------------------------

    async def _async_ensure_mqtt(self) -> SolixMqttDeviceCharger:
        """(Re)connect to the MQTT broker and subscribe to the charger topics."""
        session = self.api.mqttsession
        if not (session and session.is_connected()):
            LOGGER.debug("Connecting to Anker MQTT server")
            session = await self.api.startMqttSession(
                message_callback=self._mqtt_message
            )
            if not session:
                raise translated(UpdateFailed, "mqtt_connect_failed")
            self.api.mqtt_update_callback(self._mqtt_update)
        if self.mqtt_device is None:
            self.mqtt_device = SolixMqttDeviceCharger(self.api, self.device_sn)
        if not self.mqtt_device.is_subscribed():
            topic = f"{session.get_topic_prefix(deviceDict=self.device)}#"
            if (reason := session.subscribe(topic)) is not None:
                raise translated(
                    UpdateFailed, "mqtt_subscribe_failed", topic=topic, reason=reason
                )
        return self.mqtt_device

    def _mqtt_message(
        self,
        session: Any,
        topic: str,
        message: Any,
        data: Any,
        model: str,
        device_sn: str,
        values: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Handle a decoded MQTT message. Called from the paho network thread."""
        self.hass.loop.call_soon_threadsafe(
            self._async_mqtt_message,
            (session, topic, message, data, model, device_sn, values, *args),
            kwargs,
        )

    @callback
    def _async_mqtt_message(
        self, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        """Let the library store the values it knows, then add ours.

        Values decoded thanks to mqtt_extensions.py are dropped by the library.
        """
        self._in_message, self._message_changed = True, False
        try:
            self.api.mqtt_received(*args, **kwargs)
        finally:
            self._in_message = False
        changed = self._message_changed
        device_sn, values = args[5], args[6]
        if device_sn == self.device_sn and values:
            changed = self._async_extra_values(values) or changed
        if changed:
            self._async_handle_mqtt_update()

    @callback
    def _async_extra_values(self, values: dict[str, Any]) -> bool:
        """Fire hidden animations and store our values; whether any changed."""
        if (egg := to_int(values.get(EASTER_EGG_STATE))) is not None:
            # An event, not a state: every message counts, even the same type
            for listener in list(self._egg_listeners):
                listener(egg)
        extra = {
            key: values[key] for key in EXTRA_STATE_KEYS if values.get(key) is not None
        }
        mqtt_data = self.device.get("mqtt_data")
        if not extra or mqtt_data is None:
            return False
        changed = any(mqtt_data.get(key) != value for key, value in extra.items())
        mqtt_data.update(extra)
        return changed

    @callback
    def _mqtt_update(self, sn: str | None = None, *args: Any, **kwargs: Any) -> None:
        """The library updated the charger's values.

        Called from api.mqtt_received in _async_mqtt_message, which then pushes
        once for the whole message.
        """
        if sn != self.device_sn:
            return
        if self._in_message:
            self._message_changed = True
        else:
            self._async_handle_mqtt_update()

    @callback
    def _async_handle_mqtt_update(self) -> None:
        """A message from the charger: it is reachable, push its values."""
        self.last_message = dt_util.utcnow()
        self._got_data.set()
        recovered = not self.last_update_success
        self.last_update_success = True
        self._async_push(force=recovered)

    @callback
    def _async_push(self, force: bool = False) -> None:
        """Hand the current values to the entities, keeping the poll schedule.

        (async_set_updated_data would restart the poll interval.) Entities are
        only updated when a value changed, or with `force`.
        """
        data = self._snapshot()
        unchanged = self.data is not None and _values(data) == _values(self.data)
        self.data = data
        if force or not unchanged:
            self.async_update_listeners()

    def _snapshot(self) -> dict[str, Any]:
        """Copy of the charger's decoded values."""
        return dict(self.device.get("mqtt_data") or {})

    @callback
    def async_add_easter_egg_listener(
        self, listener: Callable[[int], None]
    ) -> CALLBACK_TYPE:
        """Call `listener(animation type)` when the charger plays a hidden animation."""
        self._egg_listeners.add(listener)
        return lambda: self._egg_listeners.discard(listener)

    # --- Polling --------------------------------------------------------------

    @property
    def stale_after(self) -> timedelta:
        """How long without any message before the data is considered stale."""
        interval = self.update_interval or timedelta(seconds=DEFAULT_SCAN_INTERVAL)
        return max(interval * STALE_POLLS, MIN_STALE_TIME)

    async def _async_update_data(self) -> dict[str, Any]:
        """Ask the charger for a full status message.

        The reply arrives asynchronously through the MQTT callback, so this
        mostly returns the values we already have.
        """
        mdev = await self._async_ensure_mqtt()
        if await mdev.status_request() is None:
            raise translated(UpdateFailed, "status_request_failed")
        if self._polls % THEME_REQUEST_POLLS == 0:
            await mdev.run_command(cmd=SolixMqttCommands.theme_request)
        self._polls += 1
        if self.cloud.refresh_due():
            self._start_cloud_refresh()
        if (
            self.last_message
            and dt_util.utcnow() - self.last_message > self.stale_after
        ):
            # The charger stopped answering (unplugged, offline). Mark entities
            # unavailable instead of showing frozen values; the next message
            # that arrives makes them available again.
            raise translated(
                UpdateFailed, "charger_silent", since=self.last_message.isoformat()
            )
        if not self._got_data.is_set():
            try:
                async with asyncio.timeout(FIRST_DATA_TIMEOUT):
                    await self._got_data.wait()
            except TimeoutError as err:
                raise translated(UpdateFailed, "no_mqtt_answer") from err
        return self._snapshot()

    # --- Cloud settings -------------------------------------------------------

    def _start_cloud_refresh(self) -> None:
        """Refresh the cloud settings in the background (one at a time)."""
        if self._cloud_task is None or self._cloud_task.done():
            self._cloud_task = self.config_entry.async_create_task(
                self.hass,
                self.async_refresh_cloud(),
                "anker_prime_charger cloud refresh",
            )

    async def async_refresh_cloud(self) -> None:
        """Read the cloud settings now and update the entities."""
        await self.cloud.async_refresh()
        self.async_update_listeners()

    async def async_set_test_feature(self, key: str, enabled: bool) -> None:
        """Turn a test feature on or off in the Anker cloud."""
        await self.cloud.async_set_test_feature(key, enabled)
        self.async_update_listeners()

    # --- Commands -------------------------------------------------------------

    async def async_send_command(
        self,
        cmd: str,
        value: Any = None,
        parm: str | None = None,
        expected: dict[str, Any] | None = None,
        parm_map: dict[str, Any] | None = None,
    ) -> None:
        """Send an MQTT command and optimistically apply the expected state.

        The library returns the state keys the device should report once the
        command is applied. `expected` adds states the library cannot infer
        (e.g. per-port priority flags derived from a port bitmask).
        """
        mdev = await self._async_ensure_mqtt()
        resp = await mdev.run_command(
            cmd=cmd, value=value, parm=parm, parm_map=dict(parm_map or {})
        )
        self._async_apply_reply(resp, cmd, expected)

    async def async_set_custom_profile(self, number: int | str) -> None:
        """Apply a saved custom profile (the library builds the command from it)."""
        mdev = await self._async_ensure_mqtt()
        resp = await mdev.set_custom_usage_profile(number=number)
        self._async_apply_reply(resp, f"custom profile {number}")

    @callback
    def _async_apply_reply(
        self, resp: Any, what: str, expected: dict[str, Any] | None = None
    ) -> None:
        if not isinstance(resp, dict):
            raise translated(HomeAssistantError, "command_refused", command=what)
        self.async_apply_state(resp | (expected or {}))

    @callback
    def async_apply_state(self, updates: dict[str, Any]) -> None:
        """Apply expected states now so entities don't flip back until the next status."""
        if mqtt_data := self.device.get("mqtt_data"):
            mqtt_data.update({k: v for k, v in updates.items() if k in mqtt_data})
            self._async_push()

    # --- Fast updates ---------------------------------------------------------

    @property
    def fast_updates(self) -> bool:
        """Whether fast updates (port values every second) are on."""
        return self.fast_updates_until is not None

    async def async_set_fast_updates(self, enabled: bool) -> None:
        """Turn fast updates on (they stop by themselves after a while) or off."""
        if enabled and not self.fast_updates:
            minutes = self.config_entry.options.get(
                CONF_FAST_UPDATES_MINUTES, DEFAULT_FAST_UPDATES_MINUTES
            )
            duration = timedelta(minutes=minutes)
            self.fast_updates_until = dt_util.utcnow() + duration
            self._fast_error_logged = False
            self._fast_unsubs = [
                async_track_time_interval(
                    self.hass, self._async_fast_tick, FAST_UPDATE_INTERVAL
                ),
                async_call_later(self.hass, duration, self._async_fast_updates_expired),
            ]
            await self._async_fast_tick()
        elif not enabled:
            self._stop_fast_updates()
        self.async_update_listeners()

    async def _async_fast_tick(self, _now: datetime | None = None) -> None:
        try:
            mdev = await self._async_ensure_mqtt()
            if await mdev.realtime_trigger() is None:
                raise HomeAssistantError("the real-time trigger could not be sent")
        except (HomeAssistantError, UpdateFailed) as err:
            # Keep trying (the connection may come back), but log it only once
            if not self._fast_error_logged:
                LOGGER.warning("Fast updates: %s", err)
                self._fast_error_logged = True
        else:
            self._fast_error_logged = False

    @callback
    def _async_fast_updates_expired(self, _now: datetime) -> None:
        self._stop_fast_updates()
        self.async_update_listeners()

    def _stop_fast_updates(self) -> None:
        for unsub in self._fast_unsubs:
            unsub()
        self._fast_unsubs = []
        self.fast_updates_until = None

    async def async_stop(self) -> None:
        """Stop fast updates and disconnect MQTT (paho joins a thread: off-loop)."""
        self._stop_fast_updates()
        await self.hass.async_add_executor_job(self.api.stopMqttSession)


def _values(data: dict[str, Any]) -> dict[str, Any]:
    """The charger's values, without the keys that change with every message."""
    return {k: v for k, v in data.items() if k not in MESSAGE_KEYS}
