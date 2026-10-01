"""Watch the charger and the app's commands while you use the Anker app.

Run it yourself (it asks for your Anker login; nothing is stored):
    powershell -ExecutionPolicy Bypass -File tools\\watch_charger.ps1 [name]

Read-only: it only asks the charger for its status (like Home Assistant does)
and reads lists from the Anker cloud. Between snapshots, do ONE thing in the
app (e.g. toggle "time display", or play an animation). The next snapshot
shows:
- the commands the app (or cloud) sent to the charger, field by field,
- what the charger reported on its own (e.g. after a hidden animation),
- which bytes of the charger's status and the cloud's image list changed.

It also keeps the charger's live port values coming (the real-time trigger,
as the app does on its main screen) and records every port's power each
second, so a snapshot shows any port whose power dropped since the previous
one (e.g. all ports cut for a moment when a custom power limit changes).

Results (serial masked, no login data) go to tools/watch_charger_results.json,
or tools/watch_charger_<name>_results.json with a name.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any

from common import anker_login, call

from custom_components.anker_prime_charger.solixapi.mqtt_charger import (
    SolixMqttDeviceCharger,
)
from custom_components.anker_prime_charger.solixapi.mqttcmdmap import SolixMqttCommands
from custom_components.anker_prime_charger.solixapi.mqtttypes import DeviceHexData

NAME = f"_{sys.argv[1]}" if len(sys.argv) > 1 else ""
RESULTS = Path(__file__).with_name(f"watch_charger{NAME}_results.json")
# Status fields that hold the clock / theme / display settings (0a00) and the
# theme message (0a02); everything else is shown only when it changes.
FOCUS = {"0a00": ["af", "b0", "b3", "b4", "b5", "b6", "b9"], "0a02": None}
# Hidden animations ("easter eggs") unlocked on this charger
EGG_LIST = "mini_power/v1/app/egg/get_easter_egg_trigger_list"
# Our own requests, not interesting in the command list (020b: real-time
# trigger, also sent by the app while it shows the charger)
OWN_COMMANDS = {"0200", "0202", "020b"}
# The real-time trigger lasts 10 s; resend it before it runs out
REALTIME_EVERY = 8
CUSTOM_LIST = "mini_power/v1/app/style/get_manual_clock_screensavers"

lock = threading.Lock()
received: list[dict[str, Any]] = []
# (seconds since start, {"usbc_1_power": W, "usbc_1_status": 0/1, ...})
live: list[tuple[float, dict[str, Any]]] = []
START = time.monotonic()


def on_message(session, topic, message, data, model, device_sn, values) -> None:
    """paho thread: keep the raw fields of every message and command."""
    if not isinstance(data, bytes | bytearray):
        return
    try:
        hd = DeviceHexData(model=model, hexbytes=bytes(data))
    except Exception as err:
        entry = {"type": "?", "error": str(err), "raw": bytes(data).hex()}
    else:
        entry = {
            "type": hd.msg_header.msgtype.hex(),
            "fields": {k: readable(f.f_value) for k, f in hd.msg_fields.items()},
        }
    # cmd/... topics carry commands to the charger (from the app or the cloud)
    entry["command"] = str(topic).startswith("cmd/")
    ports = {
        k: v
        for k, v in (values or {}).items()
        if k.startswith("usb") and k.endswith(("_power", "_status"))
    }
    with lock:
        received.append(entry)
        if ports and not entry["command"]:
            live.append((round(time.monotonic() - START, 1), ports))


def readable(value: bytes) -> str:
    """Hex, except links: shown as text and cut before their signature."""
    text = bytes(value).decode("ascii", "replace")
    if text.startswith(("http://", "https://")):
        return text.split("?")[0] + ("?<signed>" if "?" in text else "")
    return bytes(value).hex()


def bits(hex_value: str) -> str:
    """Show each byte also in binary, to spot single flag bits (cloud values as is)."""
    try:
        raw = bytes.fromhex(hex_value)
    except ValueError:
        return hex_value
    return " ".join(f"{b:02x}({b:08b})" for b in raw[:8]) + (
        " ..." if len(raw) > 8 else ""
    )


async def snapshot(
    api, mdev, sn: str
) -> tuple[dict, list[dict[str, Any]], list[tuple[float, dict[str, Any]]]]:
    """Latest fields per charger message type (plus the cloud's custom image
    list), the commands sent to the charger and the live port values since the
    previous snapshot.
    """
    await mdev.status_request()
    await mdev.run_command(cmd=SolixMqttCommands.theme_request)
    await asyncio.sleep(5)
    latest: dict[str, dict[str, str]] = {}
    commands: list[dict[str, Any]] = []
    with lock:
        timeline = list(live)
        live.clear()
        for msg in received:
            if msg.get("command"):
                if msg["type"] not in OWN_COMMANDS:
                    commands.append(msg)
            else:
                latest.setdefault(msg["type"], {}).update(msg.get("fields", {}))
        received.clear()
    # Per-image settings may be stored in the cloud instead of on the charger
    images = await call(api, CUSTOM_LIST, {"sn": sn})
    for item in ((images.get("data") or {}).get("list")) or []:
        latest[f"cloud image {item.get('id')}"] = {
            k: json.dumps(v) for k, v in item.items() if k != "img_url"
        }
    return latest, commands, timeline


def power_drops(timeline: list[tuple[float, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Ports whose power fell below half of what they had before, then came back."""
    drops = []
    keys = sorted({k for _, v in timeline for k in v if k.endswith("_power")})
    for key in keys:
        values = [(t, float(v[key])) for t, v in timeline if key in v]
        if len(values) < 2:
            continue
        before = values[0][1]
        low_t, low = min(values, key=lambda item: item[1])
        if before >= 1 and low < before / 2:
            drops.append(
                {
                    "port": key,
                    "before": before,
                    "lowest": low,
                    "at": low_t,
                    "now": values[-1][1],
                }
            )
    return drops


def show_live(timeline: list[tuple[float, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Print the port power drops since the previous snapshot."""
    if not timeline:
        print("  (no live port values: is the charger online?)")
        return []
    drops = power_drops(timeline)
    span = (
        f"{len(timeline)} live readings over {timeline[-1][0] - timeline[0][0]:.0f} s"
    )
    if not drops:
        print(f"  live port power: no drop ({span})")
    for d in drops:
        print(
            f"  POWER DROP {d['port']}: {d['before']} W -> {d['lowest']} W "
            f"at {d['at']} s, now {d['now']} W ({span})"
        )
    return drops


async def keep_live(mdev) -> None:
    """Resend the real-time trigger so the port values keep coming."""
    while True:
        await mdev.realtime_trigger()
        await asyncio.sleep(REALTIME_EVERY)


def show_commands(commands: list[dict[str, Any]]) -> None:
    for cmd in commands:
        print(f"  APP/CLOUD COMMAND {cmd['type']}:")
        for field, value in cmd.get("fields", {}).items():
            if field != "fe":
                print(f"          {field}: {bits(value)}")


def show(latest: dict, previous: dict | None) -> list[dict[str, Any]]:
    changes = []
    for mtype in sorted(set(latest) | set(previous or {})):
        now, before = latest.get(mtype, {}), (previous or {}).get(mtype, {})
        focus = FOCUS.get(mtype, [])
        for field in sorted(set(now) | set(before)):
            if field == "fe":  # message timestamp
                continue
            changed = previous is not None and now.get(field) != before.get(field)
            if changed:
                changes.append(
                    {
                        "type": mtype,
                        "field": field,
                        "before": before.get(field),
                        "after": now.get(field),
                    }
                )
            if changed or (previous is None and (focus is None or field in focus)):
                mark = "CHANGED " if changed else ""
                print(f"  {mark}{mtype}.{field}: {bits(now.get(field) or '')}")
                if changed:
                    print(f"          was: {bits(before.get(field) or '')}")
    if previous is not None and not changes:
        print("  (no change in the charger's status)")
    return changes


async def main() -> None:
    results: dict[str, Any] = {"snapshots": []}
    async with anker_login(RESULTS, results) as (api, sn):
        print("\n== Hidden animations (easter eggs) from the Anker cloud (read-only)")
        results["easter_eggs"] = await call(api, EGG_LIST, {"device_sn": sn})
        print(json.dumps(results["easter_eggs"], indent=2, ensure_ascii=False)[:3000])

        mqtt = await api.startMqttSession(message_callback=on_message)
        if not mqtt:
            raise SystemExit("Could not connect to the Anker MQTT server")
        device = api.devices[sn]
        mqtt.subscribe(f"{mqtt.get_topic_prefix(deviceDict=device)}#")
        # Commands to the charger (from the app or the cloud)
        mqtt.subscribe(f"{mqtt.get_topic_prefix(deviceDict=device, publish=True)}#")
        mdev = SolixMqttDeviceCharger(api, sn)
        live_task = asyncio.create_task(keep_live(mdev))
        await asyncio.sleep(2)

        print("\n== Snapshots. Do ONE thing in the app (or on the charger), then")
        print(
            "   type a short note (e.g. 'time display off') and press Enter; 'q' quits."
        )
        previous = None
        label = "start"
        loop = asyncio.get_running_loop()
        while True:
            latest, commands, timeline = await snapshot(api, mdev, sn)
            print(f"\n-- snapshot '{label}'")
            show_commands(commands)
            drops = show_live(timeline) if previous is not None else []
            changes = show(latest, previous)
            results["snapshots"].append(
                {
                    "label": label,
                    "commands": commands,
                    "messages": latest,
                    "changes": changes,
                    "power_drops": drops,
                    "live": timeline,
                }
            )
            previous = latest
            label = (await loop.run_in_executor(None, input, "\nnote> ")).strip()
            if label.lower() == "q":
                live_task.cancel()
                break
            label = label or f"snapshot {len(results['snapshots'])}"


if __name__ == "__main__":
    asyncio.run(main())
