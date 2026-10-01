"""Constants for the Anker Prime Charger integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "anker_prime_charger"
LOGGER: Final = logging.getLogger(__package__)

# The only model supported so far (the only one developed and tested on).
# Other Prime chargers on Wi-Fi may follow: see "Adding a model" in
# docs/DEVELOPMENT.md for what is specific to this model.
MODEL: Final = "A2345"
MODEL_NAME: Final = "Prime Charger 250W"
MANUFACTURER: Final = "Anker"

CONF_COUNTRY: Final = "country"
CONF_DEVICE_SN: Final = "device_sn"
CONF_SERVER: Final = "server"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_FAST_UPDATES_MINUTES: Final = "fast_updates_minutes"

# Seconds between MQTT status requests. The charger only publishes its full
# status (message 0a00) when asked, so this is effectively the refresh rate.
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 600

# Fast updates (the app's real-time data) stop by themselves after this long.
DEFAULT_FAST_UPDATES_MINUTES: Final = 10
MIN_FAST_UPDATES_MINUTES: Final = 1
MAX_FAST_UPDATES_MINUTES: Final = 60

# The app's test features: key in the cloud "device_setting" -> endpoint that
# sets it. Request body: {"device_sn": sn, <key>: 0 | 1} (found with
# tools/probe_cloud.py; not documented upstream).
TEST_FEATURES: Final = {
    "compatibility_status": "mini_power/v1/app/setting/set_compatibility_status",
    "charging_mode_status": "mini_power/v1/app/setting/set_charging_mode_status",
    "charging_device_identity_status": (
        "mini_power/v1/app/setting/set_charging_device_identity_status"
    ),
}
