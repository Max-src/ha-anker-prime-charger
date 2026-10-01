"""Check whether cloud-side settings actually reach the charger.

Run it yourself (it asks for your Anker login; nothing is stored):
    powershell -ExecutionPolicy Bypass -File tools\\validate.ps1

A setting changed in the Anker cloud only matters if the cloud then sends the
charger a command. This listens to the charger's command channel (MQTT, the
same as tools/watch_charger.py) while it changes a setting, then restores it:

  1  Protocols per charging mode (AI / normal; no app screen found): turn one
     protocol off in AI mode, record what reaches the charger, restore.
  2  The test features (Maximum compatibility, Custom charging mode, Charging
     device identification): flip each one, record what reaches the charger,
     restore.

Each check asks first and verifies the restore. Earlier checks (creating and
deleting profiles, energy statistics, renaming, ...) are documented in
docs/PROTOCOL.md.

Results (serial, user id hash and signed links masked) are written to
tools/validate_results.json.
"""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
import threading
from typing import Any

from common import SETTING, anker_login, ask, call, ok, read_settings

from custom_components.anker_prime_charger.solixapi.mqtttypes import DeviceHexData

RESULTS = Path(__file__).with_name("validate_results.json")
WAIT = 8  # seconds to collect what reaches the charger after a change
TEST_FEATURES = {
    "compatibility_status": "Maximum compatibility",
    "charging_mode_status": "Custom charging mode",
    "charging_device_identity_status": "Charging device identification",
}


class CommandWatcher:
    """Collects the commands sent to the charger (MQTT cmd topic)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._commands: list[dict[str, Any]] = []

    def on_message(self, session, topic, message, data, model, device_sn, values):
        """Paho thread: keep commands to the charger, except our own requests."""
        if not str(topic).startswith("cmd/") or not isinstance(data, bytes | bytearray):
            return
        try:
            hd = DeviceHexData(model=model, hexbytes=bytes(data))
        except Exception:
            return
        with self._lock:
            self._commands.append(
                {
                    "type": hd.msg_header.msgtype.hex(),
                    "fields": {k: f.f_value.hex() for k, f in hd.msg_fields.items()},
                }
            )

    async def collect(self) -> list[dict[str, Any]]:
        """Commands that arrive within WAIT seconds from now."""
        with self._lock:
            self._commands.clear()
        await asyncio.sleep(WAIT)
        with self._lock:
            return list(self._commands)


def show(commands: list[dict[str, Any]]) -> str:
    return ", ".join(c["type"] for c in commands) or "none"


async def check_mode_protocols(api, sn: str, watcher: CommandWatcher) -> dict[str, Any]:
    print("\n== 1: protocols per charging mode")
    read = await call(api, SETTING + "get_protocol_status", {"device_sn": sn})
    before = read.get("data") or {}
    ai = next((m for m in before.get("modes") or [] if m.get("mode") == "ai"), None)
    target = next(
        (p for p in (ai or {}).get("protocols") or [] if p.get("status")), None
    )
    if not target:
        return {"skipped": "no protocol turned on in AI mode", "read": read}
    name = target["protocol_key"]
    if not ask(f"Turn '{name}' off in AI mode for {WAIT} s, then back on?"):
        return {"skipped": "declined"}
    changed = copy.deepcopy(before)
    for mode in changed["modes"]:
        for protocol in mode["protocols"]:
            if mode["mode"] == "ai" and protocol["protocol_key"] == name:
                protocol["status"] = False
    out: dict[str, Any] = {"protocol": name, "before": before}
    out["set"] = await call(
        api, SETTING + "set_protocol_status", changed | {"device_sn": sn}
    )
    out["commands_after_change"] = await watcher.collect()
    stored = await call(api, SETTING + "get_protocol_status", {"device_sn": sn})
    out["stored"] = (stored.get("data") or {}) == changed
    print(
        f"  set -> {ok(out['set'])}; stored: {out['stored']}; "
        f"commands to the charger: {show(out['commands_after_change'])}"
    )
    out["restore"] = await call(
        api, SETTING + "set_protocol_status", before | {"device_sn": sn}
    )
    out["commands_after_restore"] = await watcher.collect()
    after = await call(api, SETTING + "get_protocol_status", {"device_sn": sn})
    out["restored"] = (after.get("data") or {}) == before
    print(
        f"  restored: {out['restored']}; commands: {show(out['commands_after_restore'])}"
    )
    if not out["restored"]:
        print("  !! Not restored. Check the charging settings in the app.")
    return out


async def check_test_features(api, sn: str, watcher: CommandWatcher) -> dict[str, Any]:
    print("\n== 2: test features")
    out: dict[str, Any] = {}
    for key, label in TEST_FEATURES.items():
        original = int(bool((await read_settings(api, sn)).get(key)))
        if not ask(
            f"Switch '{label}' {'off' if original else 'on'} for {WAIT} s, then back?"
        ):
            out[key] = {"skipped": "declined"}
            continue
        endpoint = SETTING + f"set_{key}"
        flip = await call(api, endpoint, {"device_sn": sn, key: 1 - original})
        commands = await watcher.collect()
        restore = await call(api, endpoint, {"device_sn": sn, key: original})
        restore_commands = await watcher.collect()
        restored = int(bool((await read_settings(api, sn)).get(key))) == original
        out[key] = {
            "flip": flip,
            "commands_after_change": commands,
            "restore": restore,
            "commands_after_restore": restore_commands,
            "restored": restored,
        }
        print(
            f"  {label}: commands to the charger: {show(commands)}; restored: {restored}"
        )
        if not restored:
            print(f"  !! '{label}' was not restored. Set it back in the app.")
    return out


async def main() -> None:
    results: dict[str, Any] = {}
    async with anker_login(RESULTS, results) as (api, sn):
        watcher = CommandWatcher()
        mqtt = await api.startMqttSession(message_callback=watcher.on_message)
        if not mqtt:
            raise SystemExit("Could not connect to the Anker MQTT server")
        device = api.devices[sn]
        mqtt.subscribe(f"{mqtt.get_topic_prefix(deviceDict=device, publish=True)}#")
        await asyncio.sleep(2)
        results["mode_protocols"] = await check_mode_protocols(api, sn, watcher)
        results["test_features"] = await check_test_features(api, sn, watcher)


if __name__ == "__main__":
    asyncio.run(main())
