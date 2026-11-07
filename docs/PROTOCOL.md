# How the Anker Prime Charger 250W (A2345) talks

What the integration relies on, and how each part was found. "Verified" means checked against a
real charger and the real Anker cloud (see
[DEVELOPMENT.md](DEVELOPMENT.md#how-the-protocol-was-found)).

## Connections

- **MQTT (Anker's broker).** The charger publishes on `dt/anker_power/A2345/<serial>/…` and
  receives commands on `cmd/anker_power/A2345/<serial>/…`. The owner account can listen to both,
  which is how the app's commands were captured.
- **REST (Anker cloud).** Settings stored in the cloud, under `mini_power/v1/app/…`. Requests are
  POSTs with a JSON body; the server answers `{"code": 0, "data": …}` on success. Incomplete
  requests get a 400 answer naming the missing field (`field "x" is not set`), which is how
  request formats were learned.

Messages are binary: a header, a 2-byte message type (e.g. `0a00`), then fields (`a1`, `a2`, …:
name, length, type, value) and an XOR checksum. The vendored library encodes and decodes them;
`custom_components/anker_prime_charger/mqtt_extensions.py` adds what it doesn't know.

## Status

| What                      | How                                                                                                                                                                                                                                            | Status                                                         |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Full status               | Status request `0200` → message `0a00`                                                                                                                                                                                                         | Library                                                        |
| Theme message             | Theme request `0202` → message `0a02` (theme id and link, clock flags, time display)                                                                                                                                                           | Library                                                        |
| Live port values          | Real-time trigger `020b` (no parameters) → message `0303` every second for 10 s                                                                                                                                                                | Verified: 10 messages, last at 10.2 s                          |
| Live values, longer       | Real-time trigger `0057`: `a2` `01` on / `00` off, `a3` the seconds (2 bytes; the app sends 300) → message `0303` every second for that long?                                                                                                    | The app sends it; the integration checks at run time whether the values keep coming (fast_updates.py) |
| Firmware versions         | `0030` with `a2` the account's user id (text, no length byte) → `0830`: `a1` `v0.2.9.7`, `a2` `v2.1.1.6` (the firmware the cloud lists), `a3`-`a5` the parts' names (`A2345`, `A2345_mcu`, `A2345_esp32`; which part `a1` is is not known)       | Captured from the app (2026-10); the integration asks daily      |
| Hidden animation played   | Message `0305`, field `a2` = animation type                                                                                                                                                                                                    | Verified (type 5 after unplugging a port 10 times within 60 s) |
| Port faults, overheating  | Status `0a00` field `a3`: bit 0 overheating, bits 1-4 USB-C 1-4, bit 5 USB-A (set after 5 readings with a fault, cleared after 10 without)                                                                                                     | Library (upstream decoding); not seen on this charger          |
| Firmware update           | Status `0a00` field `b2`: byte 0 busy (1 while an update is armed; the live values pause), byte 1 progress %; message `0306` during an update (`a2` state, `a3` progress)                                                                      | Library (upstream decoding); not seen on this charger          |
| Device on each USB-C port | Status `0a00` fields `bd` (USB vendor and product id per port; `fffa`/`fffb` without a device, 0 until read) and `be` (the charger brand and model numbers); live values `0303` `a8`/`a9`; `b7` byte 1: 6 when the ports can read them, else 2 | Library (upstream decoding); to verify on this charger         |

## Commands decoded or corrected here

| What                                 | Command                                                                                                                        | State                                                                                                                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Time display (time on custom images) | `0222`, `a2`: 0 off / 1 on                                                                                                     | `0a02` field `a6` (library: `clock_time_switch`) — verified                                                                                                                       |
| Theme kind                           | `0205`, low 3 bits of `a2`: 0-2 Standard Style 1-3, 3 stock theme, 5 custom image                                              | Low 3 bits of `clock_settings` — verified. The library now agrees (`theme_type`, options `theme_1`-`theme_3`, `stock`, `custom`)                                                     |
| Standard Styles                      | `0205` with kind 0-2, theme id 4, hash 0, app-internal image path (`assets/img/…/icl_a2345_themeN.png`)                        | Verified. With a Standard Style active the charger still reports the previous theme id                                                                                          |
| Port timer duration                  | `0209`, `a3` byte `01`: seconds. The library rounds to 300 s steps (the app's 5 minutes); the charger also takes whole minutes | Verified: a 1-minute timer switches the port off after 1 minute. `mqtt_extensions.py` sets the step to 60 s. A timer turned on with 0 s runs 60 min (the integration's default) |

Upstream anker-solix-api added the time display, the theme kinds and the test feature commands
in late October 2026; the integration uses its definitions since. The library's cache update
drops the identity values below (and the animation type), so the coordinator keeps them itself;
`tests/test_library_contract.py` notices if that changes.

## Charging modes

Status `usage_mode` and command `charger_usage_mode`: 1 AI power, 2 Connection priority (the
guide's _Port Priority_), 3 Dual laptop, 4 Low power (_Low Current_), 5 custom (with
`custom_profile_number`). Priority ports: the command takes a bitmask of USB-C ports (bit 0 =
C1), at most two; the status reports a flag per port (`usbc_N_priority`: 1 normal, 2 priority).

Power per port in each mode, from Anker's user guide (`A2345_UG_EN_V2_20250717.pdf`):

| Mode                | Power per port                                                                                                                                             |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AI power            | Depends on each device's need (high / medium / low)                                                                                                        |
| Connection priority | One port: its maximum. Two ports: up to 240 W together. All six: 70 W and 65 W for the priority ports, 45 W for the other USB-C ports, 24 W for both USB-A |
| Dual laptop         | One or two ports: as Connection priority. Three or more: fixed 100 / 100 / 20 / 15 W (C1-C4), 15 W USB-A                                                   |
| Low power           | Fixed 65 / 20 / 20 / 20 W (C1-C4), 15 W USB-A                                                                                                              |

Port maximums: C1 140 W (up to 28 V 5 A), C2-C4 100 W (20 V 5 A), each USB-A 22.5 W (10 V
2.25 A); both USB-A together 24 W when other ports are in use. Total 250 W (240 W with two ports
in use). The fixed values were matched to ports in the guide's port order (C1 → A); its diagrams
didn't survive text extraction.

## Custom charging mode

The charger keeps one set of custom settings: profile number, automatic deactivation
(`auto_exit_switch`), a power limit per port and allowed protocols per USB-C port (status `0a00`
fields `b8`, `ba`). Command `0206` sends the whole set and switches to the custom mode; the
charger then re-applies power on all ports (connected devices briefly disconnect).

- **Power limits** (Anker's user guide and the app): USB-C 0 W or 15 W up to 140 W (C1) / 100 W
  (C2-C4), 1 W steps; USB-A 0, 15 or 24 W; 250 W in total.
- **Protocols per power** (cloud: `setting/get_power_range_support_protocols`,
  `{"device_model": "A2345"}`), the same for all USB-C ports:

  | Port power    | Allowed                                      |
  | ------------- | -------------------------------------------- |
  | 15-20 W       | UFCS                                         |
  | 21-22 W       | + 5-11V PPS, PD 12V                          |
  | 23-44 W       | + SCP                                        |
  | 45 W and more | + 5-16V PPS, 4.5-21V PPS, Xiaomi HyperCharge |

  No Huawei. Library names: `ufcs`, `pps11v`, `pd12v`, `scp`, `pps16v`, `pps20v`, `xiaomi`.
  The library also knows `huawei` (bit 6 of the protocol byte: `xiaomi:huawei:pps20v:pps16v:
pps11v:pd12v:ufcs:scp`), presumably Huawei's own high-power SuperCharge on other Anker chargers.
  The cloud's table never allows it on the A2345 and the app doesn't show it; the actions accept
  the name, but it is refused while the table is loaded.

- **Changing a limit or protocols** can only be done with `0206`, which carries the whole set and
  the mode (5, custom); there is no per-port command. Verified by watching the charger's messages (live
  port values every second): changing one unused port's limit or protocols **in the app** sends
  the same `0206` as the integration (e.g. `a2` `05`, `a3` `01000f1619140f`, `a4`
  `0200000b00000b0000020000`), and every port drops to 0 W (status 0) at once, then renegotiates
  within 2-4 s. The same happens from Home Assistant. It is the charger's behaviour; the only way
  to limit it is to send several changes in one command. Switching between the built-in modes
  (`0206` with mode 1-4) does the same: the app sends only that one command (with the
  per-port protocols for a custom profile), with nothing before or after.
- Around a custom-mode change the app also sends `0223` and `0214` (see the test features
  below); they don't avoid the cut.
- **The test features**, captured 2026-10-22 (firmware 2.1.1.6, `com` server; each feature off,
  on, off in the app, then on and off from the cloud only, with a reconnect after each):

  | Feature                        | The app turning it on                | Turning it off                       | The charger's state                              | Cloud only                                          |
  | ------------------------------ | ------------------------------------ | ------------------------------------ | ------------------------------------------------ | --------------------------------------------------- |
  | Maximum compatibility          | `0214` `a2` `00`, and the cloud flag | `0214` `a2` `01`, and the cloud flag | `0a00` `bb`: `00` on, `01` off                   | No command; `bb` unchanged, also after reconnecting |
  | Charging device identification | `0223` `a2` `01`                     | `0223` `a2` `00`                     | `0a00` `bf`: `01` on, `00` off                   | No command; `bf` unchanged, also after reconnecting |
  | Custom charging mode           | The cloud flag only (no command)     | `0211` `a2` `00`, and the cloud flag | Nothing seen (the charger wasn't in custom mode) | Same as the app for "on"                            |
  - The charger, not the cloud, holds compatibility and identification: the app's identification
    switch left the cloud flag unchanged in one run (the charger on, the flag off), and changed it
    in another. The cloud flags can disagree with the charger.
  - Turning custom mode off also sent `0223` `00` (and identification went off, `bf` `01` to
    `00`), once; the coupling needs a confirming run.
  - Every time the app opens the charger it sends `020a` (the account's region and user id),
    `0214` `01` (also when compatibility was on, without turning it off: only `00` was seen to
    change `bb`), `0057` (`a2` `01`, `a3` 300, a real-time trigger) and sometimes `0030`, which
    the charger answers with `0830` (firmware versions of the charger, its MCU and ESP32 modules).
  - Replies: the charger answers `0214`, `0223`, `0211` and `020a` with `0a14`, `0a23`, `0a11`
    and `0a0a` (`a1` `34`).
  - So a change of the cloud flag alone doesn't change compatibility or identification on the
    charger: the integration's switches send the command too (since 2026-10-23).

## Cloud settings (REST)

| What                                 | Endpoint (`mini_power/v1/app/…`) and body                                                                                                                                                               | Status                                                            |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Test features                        | `setting/set_<key>` with `{"device_sn", <key>: 0/1}` for `compatibility_status`, `charging_mode_status`, `charging_device_identity_status`; read with `setting/get_device_setting`                      | Verified (stored)                                                 |
| Two other flags                      | `antiloss_mode_status`, `temperature_mode_status`: same pattern, stored, but no visible effect                                                                                                          | Not used                                                          |
| Profiles: list                       | `charging/get_charging_mode_list` `{"device_sn"}`                                                                                                                                                       | Library                                                           |
| Profiles: update                     | `charging/update_charging_mode`: the profile as listed + `device_sn`                                                                                                                                    | Verified                                                          |
| Profiles: create                     | `charging/add_charging_mode`: a profile without `id`, with a free `number` (1-4) + `device_sn`; answers the new profile                                                                                 | Verified                                                          |
| Profiles: delete                     | `charging/delete_charging_mode` `{"id"}`                                                                                                                                                                | Verified                                                          |
| Port labels                          | `setting/set_port_remark` `{"device_sn", "port_name": "C1"…"A2", "remark"}`                                                                                                                             | Library                                                           |
| Unlocked animations                  | `egg/get_easter_egg_trigger_list` `{"device_sn"}` → `egg_trigger_list`                                                                                                                                  | Verified                                                          |
| Custom images: list                  | `style/get_manual_clock_screensavers` `{"sn"}`                                                                                                                                                          | Library                                                           |
| Custom images: add / rename / delete | `style/add_manual_clock_screensavers` `{"sn", "img_url", "hash_code"}`, `style/set_manual_clock_screensaver_name` `{"sn", "screensaver_id", "name"}`, `style/delete_manual_clock_screensavers` `{"id"}` | Verified; used by the clock image actions (`clock_images.py`)     |
| Custom images: real link             | `style/get_url` `{"short_url"}` → `{"url"}` (a fresh signed link)                                                                                                                                       | Verified                                                          |
| Protocols per mode                   | `setting/get_protocol_status` / `set_protocol_status` (modes `ai`, `normal`)                                                                                                                            | Read verified; whether a change reaches the charger: not verified |

Clock images are baseline JPEGs of 480×200 pixels; the theme hash is the CRC32 of the file. The
charger only shows images from Anker's storage (one served by Home Assistant was tried).

**Uploading a custom image** (verified 2026-10-16 with an upload probe; the image showed in
the app and on the charger):

1. `POST app/cloudstor/get_app_up_token_general` (not under `mini_power`) with
   `{"file_name": "cropped_image.jpg", "content_type": "binary/octet-stream", "file_size": <bytes>,
"disable_ssl": false, "type": 106}` → `{"uptoken", "key_prefix"}`. `type` is a file type and
   is required: 106 is the clock image; 0, 1 and 2 exist but answer `80009` "violation of other parameter filling rules corresponding to
   file_type". No user or terminal id is needed.
2. `PUT` the file to `uptoken` (a pre-signed S3 link) with `Content-Type: binary/octet-stream` →
   HTTP 200.
3. `style/add_manual_clock_screensavers` with `img_url` = `key_prefix` (the object's path, e.g.
   `/anker_power/edge/screen_saver/2026/10/16/<account hash>/<random>.cropped_image.jpg`, which
   later shows as the image's `short_url`) and `hash_code` = `0x` + CRC32 in hex.
4. Show it with the theme command (`0205`, kind 5): the app puts the image link in field `a7`
   (stock themes use `a6`), the image id in `a3` and the CRC32 in `a4` (little-endian). The
   charger downloads the image from that link, so it must be fresh: the signed links (from the
   image list or `style/get_url`) expire after 5 minutes. The link goes without a length byte.

How the app handles custom images:

- Names: at most 13 characters, and not one already used.
- After a theme change the charger downloads the image; on failure the app shows "screen saver switching failure" and switches back to the previous theme.
- The app keeps its own copy of the custom image list and finds the current theme
  from the charger's theme id in that list. An image added elsewhere (e.g. from Home Assistant)
  isn't found until the app reloads it, so it shows another theme as selected for a while.
- With no custom image, the app disables the clock switch of the custom category.

## Other models on the account

The account's device list (`get_bind_devices`) includes every device the app registered, also
Bluetooth-only ones. The integration's diagnostics show them (`other_account_devices`). What
the fields mean:

- `wifi_online`: whether the device is connected to Anker's cloud. The A2345 reports `true`.
- `mqtt_supported`: set by the library for any device the account owns; it does **not** mean
  the device talks MQTT.

**Prime Charger 160W (A2687)**, checked 2026-10-15 (firmware 1.6.1.0): `wifi_online` is
`false`, and Anker describes it as connecting to the app over Bluetooth only. It never reaches
the cloud, so the integration can't support it. The library has no message map for it either.
Its Bluetooth protocol is decoded by [SolixBLE](https://github.com/flip-dots/SolixBLE) (used by
the [HaSolixBLE](https://github.com/flip-dots/HaSolixBLE) integration): per-port status,
voltage, current, power, on/off and timers, with the same `a1`, `a2`, … field layout as the
cloud messages but AES-GCM encryption and a different handshake.

## Not found

- **Local network access (2026-10-02):** the charger answers ping on the LAN, but a scan of all
  65,535 TCP ports found none open; it silently drops every connection (no reset), as it does for
  24 common UDP ports (DNS, NTP, SNMP, SSDP, mDNS, CoAP, Tuya-style 6666-6668, HF 48899, …). It
  doesn't announce itself over mDNS or SSDP. No local IP API was found in that test; the integration
  currently uses Anker's cloud. This does not rule out local Bluetooth control through SolixBLE,
  which still needs a nearby advertisement and connection test on this charger.
- **Matter, HomeKit:** no Prime charger is documented with either, and the charger announces no
  Matter or HomeKit service (no mDNS at all, above).
- **Bluetooth while on Wi-Fi (2026-11-07):** SolixBLE has a class for this charger
  (`devices/prime_charger_250w.py`: per-port values, on/off, timers; pairing needs a press on the
  dial). Its one reported test was with the charger removed from the app, and Anker's Wi-Fi
  devices are reported to stop Bluetooth once on Wi-Fi. A passive scan from a PC found no
  advertisement, but that PC saw only one device at all (weak radio), so it settles nothing.
  To check: scan for the charger's Bluetooth address (on its device page in Home Assistant, under
  Connections) next to the charger while it is on Wi-Fi.

- **Renaming the charger:** `app/devicerelation/up_alias_name` needs `device_sn` + `alias_name` but
  answers "(10003) Failed to request"; five other candidates don't exist.
- **Energy statistics:** `power/get_day_power_data` refuses every date format tried. The charger
  doesn't report energy either, so the integration computes it from the power values.
- **Port protocol status:** `setting/get_port_protocol_status` needs a `version` that wasn't found.
- **Playing hidden animations:** the app has no command for it either. Its hidden animations
  page only reads the unlocked list (`egg/get_easter_egg_trigger_list`) and plays the animations
  on the phone. The charger plays them on its own and reports each one (`0305`). The app's hints: main screen switched 20 times in 10 s (Feature 1) or 15 times (Play
  bad); same USB-C port plugged and unplugged 10 times in 60 s (Feature 2, type 5) or 5 times in
  10 s (Dizziness); every port in use (Device Expert); port priority changed 10 times (Feature
  Expert); 3 high-performance laptops at once (Power Expert).
  Verified 2026-10-17 from Home Assistant (3 rounds each):
  changing the port priority 10 times plays type 1 (Feature Expert) every round, right after the
  10th change, even in Connection priority mode. Switching a USB-C port off and on plays type 5
  once 10 cycles fall within 60 s (Feature 2); 5 cycles in 10 s alone played nothing. After it
  plays there is a cooldown: rounds 25 s, 1.5 min and 3 min later played nothing; rounds 5.4 min
  apart (`--pause 300`) played it every time. The cloud's unlocked list didn't
  change within a minute: the app probably adds new triggers there
  (`egg/add_easter_egg_trigger_record`), so it may need the app.
- **Choosing a holiday**, **brightness
  below 20 %**: no command or endpoint (or no effect).
