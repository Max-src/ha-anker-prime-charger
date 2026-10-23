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

| What                    | How                                                                                  | Status                                                         |
| ----------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| Full status             | Status request `0200` → message `0a00`                                               | Library                                                        |
| Theme message           | Theme request `0202` → message `0a02` (theme id and link, clock flags, time display) | Library + ours                                                 |
| Live port values        | Real-time trigger `020b` (no parameters) → message `0303` every second for 10 s      | Verified: 10 messages, last at 10.2 s                          |
| Hidden animation played | Message `0305`, field `a2` = animation type                                          | Verified (type 5 after unplugging a port 10 times within 60 s) |

## Commands decoded or corrected here

| What                                 | Command                                                                                                                        | State                                                                                                                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Time display (time on custom images) | `0222`, `a2`: 0 off / 1 on                                                                                                     | `0a02` field `a6` (library: `unknown_0a02_a6`) — verified                                                                                                                       |
| Theme kind                           | `0205`, low 3 bits of `a2`: 0-2 Standard Style 1-3, 3 stock theme, 5 custom image                                              | Low 3 bits of `clock_settings` — verified. The library reads them as two flags (`0x02`, `0x04`), which sends the wrong kind                                                     |
| Standard Styles                      | `0205` with kind 0-2, theme id 4, hash 0, app-internal image path (`assets/img/…/icl_a2345_themeN.png`)                        | Verified. With a Standard Style active the charger still reports the previous theme id                                                                                          |
| Port timer duration                  | `0209`, `a3` byte `01`: seconds. The library rounds to 300 s steps (the app's 5 minutes); the charger also takes whole minutes | Verified: a 1-minute timer switches the port off after 1 minute. `mqtt_extensions.py` sets the step to 60 s. A timer turned on with 0 s runs 60 min (the integration's default) |

The library's cache update drops values it doesn't know (`time_display`, the animation type), so
the coordinator keeps them itself; `tests/test_library_contract.py` notices if that changes.

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
  (`0206` with mode 1-4) does the same: the app's `setChargingMode` sends only that one command
  (adding the per-port protocols for a custom profile), with nothing before or after.
- Around a custom-mode change the app also sends `0223` and `0214` (see the test features
  below); they don't avoid the cut.
- Commands the app has for the A2345 that the integration doesn't send (from the app's command
  list; not yet tried on the charger):

  | Command         | App function                                             | Fields                                         | Status                                        |
  | --------------- | -------------------------------------------------------- | ---------------------------------------------- | --------------------------------------------- |
  | `0211`          | custom charging mode switch (the test feature)           | `a2`: `00` sent when it is turned off          | Captured (2026-10-22); see below              |
  | `0214`          | maximum compatibility switch (the test feature)          | `a2`: `00` enabled / `01` disabled             | Captured (2026-10-22); see below              |
  | `0223`          | charging device identification switch (the test feature) | `a2`: `01` enabled / `00` disabled             | Captured (2026-10-22); see below              |
  | `0215`          | UFCS outside custom mode                                 | `a2`: `01` enabled / `00` disabled             | APK-decoded; region/firmware gated            |
  | `021d`          | CN per-port protocol synchronization                     | `a2`: concatenated 16-bit little-endian values | Partial decode; not a general per-mode setter |
  | `0220` / `0221` | prepare image / send image data                          | Partial field map below                        | A2345 runtime support unverified              |

  **The test features, captured 2026-10-22** (firmware 2.1.1.6, `com` server; each feature off,
  on, off in the app, then on and off from the cloud only, with a reconnect after each):

  | Feature | The app turning it on | Turning it off | The charger's state | Cloud only |
  |---|---|---|---|---|
  | Maximum compatibility | `0214` `a2` `00`, and the cloud flag | `0214` `a2` `01`, and the cloud flag | `0a00` `bb`: `00` on, `01` off | No command; `bb` unchanged, also after reconnecting |
  | Charging device identification | `0223` `a2` `01` | `0223` `a2` `00` | `0a00` `bf`: `01` on, `00` off | No command; `bf` unchanged, also after reconnecting |
  | Custom charging mode | The cloud flag only (no command) | `0211` `a2` `00`, and the cloud flag | Nothing seen (the charger wasn't in custom mode) | Same as the app for "on" |

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

## Offline APK findings (2026-10-21)

Source: Anker Power **3.24.3**, existing Blutter ARM64 disassembly of `libapp.so`.
Addresses below identify this build only. These are static findings, not new hardware tests.
The local research archive is `C:/Users/Maxime/ANKER`; the full UI disassembly is in WSL at
`/root/anker_re/out_blutter/asm`. No app binaries or account captures belong in this repository.

### Test features and UFCS

Controller source: `charging/ble/device/A2345/a2345_device_controller.dart`.

| Function                               | Address     | Boolean encoding                     |
| -------------------------------------- | ----------- | ------------------------------------ |
| `setCustomChargeModeSwitch`            | `0x3e34684` | `tst #0x10; cset eq`: true becomes 1 |
| `setCompatibilitySwitch`               | `0x2777704` | `tst #0x10; cset ne`: true becomes 0 |
| `sendEquipmentIdentificationSwitchReq` | `0x2777514` | `tst #0x10; cset ne`: true becomes 0 |
| `setUFCSSwitch`                        | `0x3e56f90` | `tst #0x10; cset eq`: true becomes 1 |

The values become a one-byte list under key `0xa2`. The following shift is Dart small-integer
tagging, not an extra multiplication on the wire. In this binary, true has bit 4 clear and
false has it set; the laboratory logic includes explicit true/false constants and branches
confirming that interpretation. Do not reuse the REST 0/1 encoding for all four commands.
The 2026-10-22 capture contradicts the identification row: enabling it sent `0223` `01`. The
caller may pass the inverse of the switch state; the captured wire values above take precedence.

The laboratory UI passes its requested Boolean through to the controller. Its custom-mode
path saves the cloud setting (`setLaboratorySwitch`, `0x3e57780`), and the scheduled command
callback calls `setCustomChargeModeSwitch` (`0x3e57ed8`). Compatibility and identification
also have explicit device-command paths. `_dealResponse` (`0x2779740`) clears the custom-mode
and UFCS retry schedules on `0a11` and `0a15` respectively. An acknowledgement alone does not
prove the charging behavior changed or persisted.

The app's English strings clarify the intended behavior:

- UFCS enables that protocol **except in Custom Mode** (`a2345UFCSProtocolConfigurationTips`).
  The laboratory page shows this legacy UFCS control for CN devices when its newer-protocol
  capability flag (device offset `1351`) is false (`0x3e531a4` through `0x3e531d8`). The setter
  separately checks a feature-availability flag at offset `1339` (`0x3e56b04`). These offsets
  are app object fields, not wire fields; the firmware thresholds remain to be traced.
- Maximum compatibility is described as helping some drone battery compartments.
- Enabling maximum compatibility automatically disables charging device identification,
  according to `a2345MaximumCompatibilityInfo`. Future setters must account for this coupling;
  simply adding one MQTT write to each cloud switch is not sufficient.
- Identification displays the model of a charging device in the port information.

### Protocol management (`021d`)

`setProtocolManage` (`0x3b2fe9c`) wraps an already-built byte list in `a2` and sends `021d`.
Its BLE-connect synchronization caller, `_trySyncProtocolOnBleConnect` (`0x3b2f6ec`), exits
for non-CN devices and for firmware without the newer-protocol capability. It fetches
`getPortProtocolStatus` and parses `PortProtocolStatusResponse`.

In its success callback (`0x3b2fa30`), the app iterates `response.portList`, concatenates each
port's list at field offset `0x13`, then emits each integer as `[value & 255, (value >> 8) & 255]`
before sending `021d` (`0x3b2fd78`). Thus the byte order and flattening order are known; the
meaning of each integer, list cardinality, port ordering contract and cloud `version` argument
are not yet established. Do not equate these integers with the `0206` custom-mode bitmask.

The protocol-management UI additionally checks PD 12V versus Xiaomi HyperCharge conflicts
(`_checkPdMiConflict`, `0x3e62a74` onward) and limits protocol groups. These constraints and
the full response schema must be decoded before exposing this as an HA action.

### Direct image transfer (`0220` / `0221`)

`prepareSendScreensaverImage` (`0x26c8744`) builds the following value map. Argument positions
are relative to the Dart function's receiver; names remain deliberately unresolved.

| Field | Encoding / source                                                      |
| ----- | ---------------------------------------------------------------------- |
| `a2`  | One byte, incoming `x7` argument                                       |
| `a3`  | Four-byte little-endian integer, incoming `x6`                         |
| `a4`  | Four-byte little-endian integer, incoming `x5`                         |
| `a5`  | Four-byte little-endian integer, incoming `x2`                         |
| `a6`  | Constant byte `0a` (the disassembly's 20 is a tagged integer)          |
| `a7`  | Two-byte little-endian integer, stack argument `[fp+0x18]`             |
| `a8`  | Two-byte little-endian integer, stack argument `[fp+0x10]`             |
| `a9`  | UTF-8 incoming `x3`, only when `a2 == 0` and that argument is non-null |

`sendScreensaverImageData` (`0x26c727c`) sends `0221`: `a2` is the incoming `x3` integer
encoded in two bytes little-endian, and `a3` is the incoming `x2` byte list. A sequence/index
interpretation for `a2` is plausible but needs caller/acknowledgement confirmation.

Direct named UI callers found in the full charging disassembly are under
`a25x7screensaver_style`, not the A2345 screen. Shared or folded code can explain the A2345
controller labels. This is **not proof of working A2345 direct transfer**. Image metadata,
chunk limits, acknowledgements, retries, cancellation and finalization still need tracing.
Keep the working cloud upload path; do not send speculative image packets.

### Bluetooth integration preparation

Inspected [SolixBLE](https://github.com/flip-dots/SolixBLE) source on 2026-10-21:
`SolixBLE/devices/prime_charger_250w.py` and `SolixBLE/factory.py` on `main`.
The `PrimeCharger250w` class implements:

- Telemetry types `4303` / `ca00`, six separate ports, voltage and current divided by 1000,
  power divided by 100; telemetry fields `a2` through `a7` map C1-C4, A1, A2.
- `420b` keepalive with `a1 = 21`, every 10 seconds.
- `4207` port switches, zero-based port index and 1/0 state. USB-A control is grouped.
- `4209` timers, using its existing five-byte little-endian seconds encoder; confirm this
  against hardware before translating the integration's MQTT timer semantics.
- Current factory identification by advertised product type `b402` or name `A2345_XXXX`.
  Discovery on `main` is not proof the same API exists in the packaged PyPI release.

The proposed cloud-only / Bluetooth-only / both modes require capability-based routing, not
blind fallback of every command. Keep existing entity unique IDs; route supported port writes
to exactly one transport, never retry an uncertain write on the other transport automatically.
Track freshness per source, prefer one current reading per port and avoid counting both streams
as extra energy. Cloud-only settings, profiles and image management must be unavailable without
cloud access rather than appearing to succeed. Bluetooth-only setup must not require an Anker
password. Use HA's Bluetooth discovery/proxy APIs and SolixBLE's supported connection lifecycle;
do not start a competing raw scanner inside Home Assistant.

### Remaining work and acceptance checks

The captures below run with the local-only watcher (`tools/watch_charger.ps1 <plan>`, not
published), whose guided plans give the steps in order: `test-custom-mode`,
`test-compatibility`, `test-identification` (each off, on, off in the app, then the same from the
cloud only with a reconnect after each change; the cloud-only change asks first and is put back),
`ufcs` and `protocols`. Every snapshot records the commands the app sends, the charger's messages
and replies, the cloud's test feature flags and protocol settings, with the firmware and region.

- [x] Remove HACS installation instructions; document manual installation only.
- [x] Decode the four switch builders and document their differing polarity.
- [x] Identify UFCS's non-custom-mode scope and app visibility gates.
- [x] Partially decode `021d` and direct-image field layouts without sending writes.
- [x] Capture each of the three test features **off, on, off**, one at a time (2026-10-22, results
      above).
- [ ] For compatibility, capture identification before and after enabling it. Confirm which
      cloud calls and device commands implement the coupling, their order, and partial-failure
      behavior. (Seen once: turning custom mode off also sent `0223` `00`.)
- [x] Compare a cloud-only change with an app change and verify persistence after reconnect: a
      cloud-only change doesn't reach the charger.
- [x] Wire the test switches: compatibility and identification send `0214` / `0223`, then the
      cloud flag; their state is the charger's `bb` / `bf` (the cloud flag until reported); custom
      mode off also sends `0211` `00`. Confirmed from Home Assistant 2026-10-23: each switch
      turned on and back off, and the charger's next status agreed each time.
- [ ] What `0211` `00` does with a custom profile active (does the charger leave custom mode?).
- [ ] Trace UFCS capability thresholds and status parser; test supported hardware with a UFCS
      load outside custom mode. Confirm custom-mode protocol settings remain independent.
- [ ] Decode the CN protocol response model, `version` request value, individual integer
      meanings, UI constraints and acknowledgement path; capture a single-port change before writes.
- [ ] Trace direct-image metadata and the A25X7/shared call path, then establish A2345 support.
      Keep this lower priority than cloud upload and port control.
- [ ] Scan beside the charger while Wi-Fi stays connected, with the phone app closed. Record
      service UUIDs, product type, RSSI and connectability privately; repeat with the screen awake.
      A missing advertisement in a 20-second remote scan does not establish Wi-Fi/BLE exclusivity.
- [ ] Verify SolixBLE's released API, connect read-only and compare all six port measurements.
      Test disconnect/reconnect and HA proxy support before enabling BLE writes.
- [ ] Implement and test the three connection modes, capability-based availability, grouped
      USB-A control, timers, source freshness, identity migration and energy continuity. No Bluetooth
      runtime support has been added by this offline investigation.

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

**Uploading a custom image** (from the decompiled app 3.24.3, verified 2026-10-16 with
an upload probe; the image showed in the app and on the charger):

1. `POST app/cloudstor/get_app_up_token_general` (not under `mini_power`) with
   `{"file_name": "cropped_image.jpg", "content_type": "binary/octet-stream", "file_size": <bytes>,
"disable_ssl": false, "type": 106}` → `{"uptoken", "key_prefix"}`. `type` is a file type and
   is required: 106 is the clock image (the app uses 1108 in another mode of its crop page); 0, 1
   and 2 exist but answer `80009` "violation of other parameter filling rules corresponding to
   file_type". No user or terminal id is needed.
2. `PUT` the file to `uptoken` (a pre-signed S3 link) with `Content-Type: binary/octet-stream` →
   HTTP 200.
3. `style/add_manual_clock_screensavers` with `img_url` = `key_prefix` (the object's path, e.g.
   `/anker_power/edge/screen_saver/2026/10/16/<account hash>/<random>.cropped_image.jpg`, which
   later shows as the image's `short_url`) and `hash_code` = `0x` + CRC32 in hex.
4. Show it with the theme command (`0205`, kind 5): the app puts the image link in field `a7`
   (stock themes use `a6`), the image id in `a3` and the CRC32 in `a4` (little-endian).

What else the app's code shows (`a2345custom_clock`, `a2345clock_style`):

- Names: at most 13 characters, and not one already used.
- After a theme change the charger downloads the image and reports a download state; on failure
  the app shows "screen saver switching failure" and switches back to the previous theme.
- The app caches the custom image list (`cachedCustomScreensavers`) and finds the current theme
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

- **Renaming the charger:** `app/devicerelation/up_alias_name` needs `device_sn` + `alias_name` but
  answers "(10003) Failed to request"; five other candidates don't exist.
- **Energy statistics:** `power/get_day_power_data` refuses every date format tried. The charger
  doesn't report energy either, so the integration computes it from the power values.
- **Port protocol status:** `setting/get_port_protocol_status` needs a `version` that wasn't found.
- **Playing hidden animations:** the app has no command for it either. Its easter-egg page
  (`a2345easter_egg`) only reads the unlocked list (`egg/get_easter_egg_trigger_list`), records
  that you looked at them (`egg/report_easter_egg_trigger_status`), and plays its own Lottie copy
  on the phone. The charger plays them on its own and reports each one (`0305`). The app's hints
  (`a2345EasterEgg…Tips`): main screen switched 20 times in 10 s (Feature 1) or 15 times (Play
  bad); same USB-C port plugged and unplugged 10 times in 60 s (Feature 2, type 5) or 5 times in
  10 s (Dizziness); every port in use (Device Expert); port priority changed 10 times (Feature
  Expert); 3 high-performance laptops at once (Power Expert).
  Verified 2026-10-17 from Home Assistant (3 rounds each):
  changing the port priority 10 times plays type 1 (Feature Expert) every round, right after the
  10th change, even in Connection priority mode. Switching a USB-C port off and on plays type 5
  once 10 cycles fall within 60 s (Feature 2); 5 cycles in 10 s alone played nothing. After it
  plays there is a cooldown: rounds 25 s, 1.5 min and 3 min later played nothing; rounds 5.4 min
  apart (`--pause 300`) played it every time. The cloud's unlocked list didn't
  change within a minute: the app reports new triggers there (`uploadEasterEggTrigger`,
  `egg/add_easter_egg_trigger_record`), so it may need the app.
- **Choosing a holiday**, **brightness
  below 20 %**: no command or endpoint (or no effect).
