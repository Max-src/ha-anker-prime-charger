"""Custom charging profiles stored in the Anker cloud (the app's custom modes).

A profile has per port ("C1".."C4", "A"): "power" in W, "max_power" and a
0/1 flag per protocol (scp, ufcs, pps11v, pps16v, pps20v, pd12v, huawei,
xiaomi), plus "number" (1-4), "name", "auto_exit", "total_power" (the sum of
the port powers), "max_total_power" (250) and "has_charge_protocol" (1).

Verified with tools/probe_profiles.py and tools/validate.py, on
mini_power/v1/app/charging/:
- update_charging_mode: the profile as listed, plus "device_sn";
- add_charging_mode: the same without "id", with a free "number"; the cloud
  answers with the new profile;
- delete_charging_mode: {"id": <profile id>}.
The app allows up to 4 profiles.
"""

from __future__ import annotations

import copy
from typing import Any, Final

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from . import custom_mode
from .coordinator import PrimeChargerCoordinator

MAX_PROFILES: Final = 4
# Profile port names -> custom_mode port keys, and their maximum power
PROFILE_PORTS: Final = {"C1": "c1", "C2": "c2", "C3": "c3", "C4": "c4", "A": "a"}
PORT_MAX_POWER: Final = {"C1": 140, "C2": 100, "C3": 100, "C4": 100, "A": 24}


def saved_profiles(coordinator: PrimeChargerCoordinator) -> list[dict[str, Any]]:
    """The profiles the Anker cloud reported last."""
    return list(coordinator.cloud.profiles.values())


def find_profile(coordinator: PrimeChargerCoordinator, name: str) -> dict[str, Any]:
    """A saved profile by name (case-insensitive)."""
    profiles = saved_profiles(coordinator)
    for profile in profiles:
        if str(profile.get("name", "")).strip().lower() == name.strip().lower():
            return profile
    names = ", ".join(str(p.get("name")) for p in profiles) or "none"
    raise ServiceValidationError(
        f"No custom profile named '{name}' (profiles: {names})"
    )


def profile_settings(profile: dict[str, Any]) -> custom_mode.CustomSettings:
    """The settings stored in a profile."""
    limits: dict[str, int] = {}
    protocols: dict[str, list[str]] = {}
    for item in profile.get("power_settings") or []:
        if (port := PROFILE_PORTS.get(str(item.get("name")))) is None:
            continue
        limits[port] = int(item.get("power") or 0)
        if port != "a":
            protocols[port] = custom_mode.ordered(
                [name for name in custom_mode.PROTOCOLS if item.get(name)]
            )
    if set(limits) != set(custom_mode.PORTS):
        raise HomeAssistantError(f"Profile '{profile.get('name')}' is incomplete")
    return custom_mode.CustomSettings(
        limits=limits, protocols=protocols, auto_exit=bool(profile.get("auto_exit"))
    )


def new_profile_template(number: int) -> dict[str, Any]:
    """An empty profile in the structure the cloud lists."""
    return {
        "number": number,
        "name": "",
        "total_power": 0,
        "max_total_power": custom_mode.TOTAL_MAX,
        "auto_exit": 0,
        "has_charge_protocol": 1,
        "power_settings": [
            {
                "name": name,
                "power": 0,
                "max_power": max_power,
                "input_power": 0,
                "input_max_power": 0,
            }
            | dict.fromkeys(custom_mode.PROTOCOLS, 0)
            for name, max_power in PORT_MAX_POWER.items()
        ],
    }


def build_profile(
    profile: dict[str, Any], settings: custom_mode.CustomSettings, name: str
) -> dict[str, Any]:
    """The profile as the cloud expects it, with new settings and name."""
    new = copy.deepcopy(profile)
    new["name"] = name
    new["auto_exit"] = int(settings.auto_exit)
    new["total_power"] = sum(settings.limits.values())
    for item in new.get("power_settings") or []:
        if (port := PROFILE_PORTS.get(str(item.get("name")))) is None:
            continue
        item["power"] = settings.limits[port]
        if port != "a":
            for protocol in custom_mode.PROTOCOLS:
                item[protocol] = int(protocol in settings.protocols[port])
    return new


def check_name(name: str | None) -> str:
    """A non-empty profile name."""
    if not (name := (name or "").strip()):
        raise ServiceValidationError("The profile name can't be empty")
    return name


async def _async_cloud(
    coordinator: PrimeChargerCoordinator, endpoint: str, body: dict[str, Any]
) -> None:
    """Send a profile request, then update the entities with the new profiles."""
    await coordinator.cloud.async_profile_request(endpoint, body)
    coordinator.async_update_listeners()


async def async_save_profile(
    coordinator: PrimeChargerCoordinator,
    profile_name: str,
    new_name: str | None = None,
    from_charger: bool = False,
    limits: dict[str, float] | None = None,
    protocols: dict[str, list[str]] | None = None,
    auto_exit: bool | None = None,
) -> None:
    """Change a saved profile in the Anker cloud.

    Starts from the profile's own settings, or from the charger's current
    custom settings with `from_charger`, then applies the given changes with
    the same checks as the charger's custom mode.
    """
    profile = find_profile(coordinator, profile_name)
    base = (
        custom_mode.current_settings(coordinator)
        if from_charger
        else profile_settings(profile)
    )
    settings = custom_mode.resolve(coordinator, base, limits, auto_exit, protocols)
    name = check_name(new_name or profile.get("name"))
    body = build_profile(profile, settings, name) | {"device_sn": coordinator.device_sn}
    await _async_cloud(coordinator, "update_charging_mode", body)


async def async_create_profile(
    coordinator: PrimeChargerCoordinator,
    name: str,
    limits: dict[str, float] | None = None,
    protocols: dict[str, list[str]] | None = None,
    auto_exit: bool | None = None,
) -> None:
    """Create a profile from the charger's current custom settings plus changes."""
    name = check_name(name)
    profiles = saved_profiles(coordinator)
    if any(str(p.get("name", "")).strip().lower() == name.lower() for p in profiles):
        raise ServiceValidationError(f"A custom profile named '{name}' already exists")
    used = {p.get("number") for p in profiles}
    number = next((n for n in range(1, MAX_PROFILES + 1) if n not in used), None)
    if number is None:
        raise ServiceValidationError(
            f"The charger holds at most {MAX_PROFILES} custom profiles; delete one first"
        )
    base = custom_mode.current_settings(coordinator)
    settings = custom_mode.resolve(coordinator, base, limits, auto_exit, protocols)
    body = build_profile(new_profile_template(number), settings, name) | {
        "device_sn": coordinator.device_sn
    }
    await _async_cloud(coordinator, "add_charging_mode", body)


async def async_delete_profile(coordinator: PrimeChargerCoordinator, name: str) -> None:
    """Delete a saved profile."""
    profile = find_profile(coordinator, name)
    await _async_cloud(coordinator, "delete_charging_mode", {"id": profile.get("id")})
    # The library keeps its old list when the cloud returns none (last one
    # deleted), so drop the deleted profile from its cache as well
    coordinator.cloud.profiles.pop(str(profile.get("id")), None)
    coordinator.async_update_listeners()
