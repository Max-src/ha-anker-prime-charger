"""Fast updates: the charger's live port values every second, for a while.

The charger only sends its live port values (message 0303, once a second)
for 10 s after a real-time trigger, so the trigger is resent every 8 s until
the duration set in the options runs out (or the switch turns it off).
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

if TYPE_CHECKING:
    from .coordinator import PrimeChargerCoordinator

# This charger's real-time trigger lasts 10 s (measured: 10 messages, one per
# second), so it is resent every 8 s while fast updates are on.
RESEND_INTERVAL: Final = timedelta(seconds=8)


class FastUpdates:
    """Turns fast updates on and off for one charger (coordinator.fast_updates)."""

    def __init__(self, coordinator: PrimeChargerCoordinator) -> None:
        """Initialize."""
        self._coordinator = coordinator
        # When they stop by themselves; None while off
        self.until: datetime | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._error_logged = False

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
            self.until = dt_util.utcnow() + duration
            self._error_logged = False
            self._unsubs = [
                async_track_time_interval(
                    coordinator.hass, self._async_trigger, RESEND_INTERVAL
                ),
                async_call_later(coordinator.hass, duration, self._async_expired),
            ]
            await self._async_trigger()
        elif not enabled:
            self.stop()
        coordinator.async_update_listeners()

    async def _async_trigger(self, _now: datetime | None = None) -> None:
        try:
            mdev = await self._coordinator.async_ensure_mqtt()
            if await mdev.realtime_trigger() is None:
                raise HomeAssistantError("the real-time trigger could not be sent")
        except (HomeAssistantError, UpdateFailed) as err:
            # Keep trying (the connection may come back), but log it only once
            if not self._error_logged:
                LOGGER.warning("Fast updates: %s", err)
                self._error_logged = True
        else:
            self._error_logged = False

    @callback
    def _async_expired(self, _now: datetime) -> None:
        self.stop()
        self._coordinator.async_update_listeners()

    def stop(self) -> None:
        """Stop fast updates (without updating the entities)."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        self.until = None
