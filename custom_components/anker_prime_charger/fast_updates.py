"""Fast updates: the charger's live port values every second, for a while.

The charger sends its live port values (message 0303, once a second) after a
real-time trigger. Two triggers exist:
- 020b, which the library knows for this charger: 10 s of values (measured);
  resent every 8 s, it keeps them coming,
- 0057 with a duration, which the app sends with 300 s each time it opens the
  charger (mqtt_extensions.py). Whether this charger honours the duration is
  not known yet, so it is checked here, once: both are sent, then 020b is let
  run out; values still coming after that come from 0057.

Once 0057 is known to work, only it is sent (every 4.5 minutes instead of
every 8 s); if the values stop, 020b takes over again. Fast updates stop by
themselves after the duration set in the options (or with the switch).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_FAST_UPDATES_MINUTES, DEFAULT_FAST_UPDATES_MINUTES, LOGGER
from .mqtt_extensions import (
    TIMED_TRIGGER_COMMAND,
    TIMED_TRIGGER_SECONDS,
    TIMED_TRIGGER_SWITCH,
)

if TYPE_CHECKING:
    from .coordinator import PrimeChargerCoordinator

# The 020b trigger lasts 10 s (measured: 10 messages, one per second): it is
# resent every 8 s while it is needed. Also how often the values are checked.
RESEND_INTERVAL: Final = timedelta(seconds=8)
SHORT_TRIGGER: Final = timedelta(seconds=10)
# The 0057 trigger's duration (as the app sends it), and when it is resent
TIMED_SECONDS: Final = 300
TIMED_RESEND: Final = timedelta(seconds=270)
# Live values are "coming" when the last one is at most this old
LIVE_GAP: Final = timedelta(seconds=4)


class FastUpdates:
    """Turns fast updates on and off for one charger (coordinator.fast_updates)."""

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        self._coordinator = coordinator
        # When they stop by themselves; None while off
        self.until: datetime | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._error_logged = False
        # Whether the charger keeps the values coming for the 0057 duration:
        # None until checked (kept while Home Assistant runs)
        self.timed_trigger_works: bool | None = None
        self._on_since: datetime | None = None
        self._short_sent: datetime | None = None
        self._timed_sent: datetime | None = None
        # The tick that checks 0057 lets 020b run out (None: no check running)
        self._check_from: datetime | None = None

    @property
    def on(self) -> bool:
        """Whether fast updates are on."""
        return self.until is not None

    async def async_set(self, enabled: bool) -> None:
        """Turn fast updates on (they stop by themselves after a while) or off."""
        coordinator = self._coordinator
        if enabled and not self.on:
            minutes = coordinator.config_entry.options.get(
                CONF_FAST_UPDATES_MINUTES, DEFAULT_FAST_UPDATES_MINUTES
            )
            duration = timedelta(minutes=minutes)
            self._on_since = dt_util.utcnow()
            self.until = self._on_since + duration
            self._error_logged = False
            self._short_sent = self._timed_sent = self._check_from = None
            self._unsubs = [
                async_track_time_interval(
                    coordinator.hass, self._async_trigger, RESEND_INTERVAL
                ),
                async_call_later(coordinator.hass, duration, self._async_expired),
            ]
            await self._async_trigger()
        elif not enabled and self.on:
            self.stop()
            await self._async_timed_off()
        coordinator.async_update_listeners()

    async def _async_trigger(self, _now: datetime | None = None) -> None:
        try:
            await self._async_keep_values_coming(dt_util.utcnow())
        except (HomeAssistantError, UpdateFailed) as err:
            # Keep trying (the connection may come back), but log it only once
            if not self._error_logged:
                LOGGER.warning("Fast updates: %s", err)
                self._error_logged = True
        else:
            self._error_logged = False

    async def _async_keep_values_coming(self, now: datetime) -> None:
        """Send what is needed for the next seconds of live values."""
        coordinator = self._coordinator
        mdev = await coordinator.async_ensure_mqtt()
        last = coordinator.last_live_message
        coming = last is not None and now - last <= LIVE_GAP
        short_ran_out = (
            self._short_sent is not None and now - self._short_sent > SHORT_TRIGGER
        )

        if self._check_from is not None and short_ran_out:
            # The check: 020b ran out, are the values still coming?
            self._check_from = None
            self.timed_trigger_works = coming
            LOGGER.debug(
                "Fast updates: the charger %s the duration of the 0057 trigger",
                "honours" if coming else "ignores",
            )
        elif (
            self.timed_trigger_works
            and not coming
            and self._on_since is not None
            and now - self._on_since > SHORT_TRIGGER
        ):
            # They stopped: back to 020b until Home Assistant restarts
            LOGGER.debug("Fast updates: values stopped with 0057 alone, using 020b")
            self.timed_trigger_works = False

        if self.timed_trigger_works is not False and (
            self._timed_sent is None or now - self._timed_sent >= TIMED_RESEND
        ):
            if (
                await mdev.run_command(
                    cmd=TIMED_TRIGGER_COMMAND,
                    value=TIMED_SECONDS,
                    parm=TIMED_TRIGGER_SECONDS,
                )
                is not None
            ):
                self._timed_sent = now
            elif self.timed_trigger_works is None:
                self.timed_trigger_works = False

        if self.timed_trigger_works:
            return
        if (
            self.timed_trigger_works is None
            and self._timed_sent is not None
            and self._short_sent is not None
            and self._check_from is None
        ):
            # Let 020b run out once to see whether 0057 keeps the values coming
            self._check_from = now
            return
        if self._check_from is not None:
            return
        if await mdev.realtime_trigger() is None:
            raise HomeAssistantError("the real-time trigger could not be sent")
        self._short_sent = now

    @callback
    def _async_expired(self, _now: datetime) -> None:
        self.stop()
        self._coordinator.config_entry.async_create_background_task(
            self._coordinator.hass,
            self._async_timed_off(),
            "anker_prime_charger fast updates off",
        )
        self._coordinator.async_update_listeners()

    async def _async_timed_off(self) -> None:
        """End the 0057 trigger's duration early (no 5 more minutes of values)."""
        if not self.timed_trigger_works:
            return
        try:
            mdev = await self._coordinator.async_ensure_mqtt()
            await mdev.run_command(
                cmd=TIMED_TRIGGER_COMMAND,
                parm_map={TIMED_TRIGGER_SWITCH: "off", TIMED_TRIGGER_SECONDS: 30},
            )
        except (HomeAssistantError, UpdateFailed) as err:
            LOGGER.debug("Fast updates: could not end the trigger: %s", err)

    def stop(self) -> None:
        """Stop fast updates (without updating the entities)."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        self.until = None
        self._check_from = None
