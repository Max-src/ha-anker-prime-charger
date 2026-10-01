# How the Anker Prime Charger 250W (A2345) talks

What the integration relies on, and how each part was found. "Verified" means checked against a
real charger and the real Anker cloud with the scripts in `tools/` (see
[DEVELOPMENT.md](DEVELOPMENT.md)).

## Connections

- **MQTT (Anker's broker).** The charger publishes on `dt/anker_power/A2345/<serial>/…` and
  receives commands on `cmd/anker_power/A2345/<serial>/…`. The owner account can listen to both,
  which is how the app's commands were captured (`tools/watch_charger.py`).
- **REST (Anker cloud).** Settings stored in the cloud, under `mini_power/v1/app/…`. Requests are
  POSTs with a JSON body; the server answers `{"code": 0, "data": …}` on success. Incomplete
  requests get a 400 answer naming the missing field (`field "x" is not set`), which is how
  request formats were learned (`tools/common.py`, `discover_fields`).

Messages are binary: a header, a 2-byte message type (e.g. `0a00`), then fields (`a1`, `a2`, …:
name, length, type, value) and an XOR checksum. The vendored library encodes and decodes them;
`custom_components/anker_prime_charger/mqtt_extensions.py` adds what it doesn't know.

## Status

| What | How | Status |
|---|---|---|
| Full status | Status request `0200` → message `0a00` | Library |
| Theme message | Theme request `0202` → message `0a02` (theme id and link, clock flags, time display) | Library + ours |
| Live port values | Real-time trigger `020b` (no parameters) → message `0303` every second for 10 s | Verified: 10 messages, last at 10.2 s |
| Hidden animation played | Message `0305`, field `a2` = animation type | Verified (type 5 after unplugging a port 10 times within 60 s) |

## Commands decoded or corrected here

| What | Command | State |
|---|---|---|
| Time display (time on custom images) | `0222`, `a2`: 0 off / 1 on | `0a02` field `a6` (library: `unknown_0a02_a6`) — verified |
| Theme kind | `0205`, low 3 bits of `a2`: 0-2 Standard Style 1-3, 3 stock theme, 5 custom image | Low 3 bits of `clock_settings` — verified. The library reads them as two flags (`0x02`, `0x04`), which sends the wrong kind |
| Standard Styles | `0205` with kind 0-2, theme id 4, hash 0, app-internal image path (`assets/img/…/icl_a2345_themeN.png`) | Verified. With a Standard Style active the charger still reports the previous theme id |
| Port timer duration | `0209`, `a3` byte `01`: seconds. The library rounds to 300 s steps (the app's 5 minutes); the charger also takes whole minutes | Verified: a 1-minute timer switches the port off after 1 minute. `mqtt_extensions.py` sets the step to 60 s. A timer turned on with 0 s runs 60 min (the integration's default) |

The library's cache update drops values it doesn't know (`time_display`, the animation type), so
the coordinator keeps them itself; `tests/test_library_contract.py` notices if that changes.

## Charging modes

Status `usage_mode` and command `charger_usage_mode`: 1 AI power, 2 Connection priority (the
guide's *Port Priority*), 3 Dual laptop, 4 Low power (*Low Current*), 5 custom (with
`custom_profile_number`). Priority ports: the command takes a bitmask of USB-C ports (bit 0 =
C1), at most two; the status reports a flag per port (`usbc_N_priority`: 1 normal, 2 priority).

Power per port in each mode, from Anker's user guide (`A2345_UG_EN_V2_20250717.pdf`):

| Mode | Power per port |
|---|---|
| AI power | Depends on each device's need (high / medium / low) |
| Connection priority | One port: its maximum. Two ports: up to 240 W together. All six: 70 W and 65 W for the priority ports, 45 W for the other USB-C ports, 24 W for both USB-A |
| Dual laptop | One or two ports: as Connection priority. Three or more: fixed 100 / 100 / 20 / 15 W (C1-C4), 15 W USB-A |
| Low power | Fixed 65 / 20 / 20 / 20 W (C1-C4), 15 W USB-A |

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

  | Port power | Allowed |
  |---|---|
  | 15-20 W | UFCS |
  | 21-22 W | + 5-11V PPS, PD 12V |
  | 23-44 W | + SCP |
  | 45 W and more | + 5-16V PPS, 4.5-21V PPS, Xiaomi HyperCharge |

  No Huawei. Library names: `ufcs`, `pps11v`, `pd12v`, `scp`, `pps16v`, `pps20v`, `xiaomi`.
  The library also knows `huawei` (bit 6 of the protocol byte: `xiaomi:huawei:pps20v:pps16v:
  pps11v:pd12v:ufcs:scp`), presumably Huawei's own high-power SuperCharge on other Anker chargers.
  The cloud's table never allows it on the A2345 and the app doesn't show it; the actions accept
  the name, but it is refused while the table is loaded.
- **Changing a limit or protocols** can only be done with `0206`, which carries the whole set and
  the mode (5, custom); there is no per-port command. Verified with `tools/watch_charger` (live
  port values every second): changing one unused port's limit or protocols **in the app** sends
  the same `0206` as the integration (e.g. `a2` `05`, `a3` `01000f1619140f`, `a4`
  `0200000b00000b0000020000`), and every port drops to 0 W (status 0) at once, then renegotiates
  within 2-4 s. The same happens from Home Assistant. It is the charger's behaviour; the only way
  to limit it is to send several changes in one command.
- Around a custom-mode change the app also sends `0223` (`a2` `00` / `01`, meaning unknown) and
  `0214`; they don't avoid the cut. Status field `0a00` `bb` went from `01` to `00` after the
  app's change (not after the integration's): meaning unknown, perhaps "settings differ from the
  saved profile".

## Cloud settings (REST)

| What | Endpoint (`mini_power/v1/app/…`) and body | Status |
|---|---|---|
| Test features | `setting/set_<key>` with `{"device_sn", <key>: 0/1}` for `compatibility_status`, `charging_mode_status`, `charging_device_identity_status`; read with `setting/get_device_setting` | Verified (stored) |
| Two other flags | `antiloss_mode_status`, `temperature_mode_status`: same pattern, stored, but no visible effect | Not used |
| Profiles: list | `charging/get_charging_mode_list` `{"device_sn"}` | Library |
| Profiles: update | `charging/update_charging_mode`: the profile as listed + `device_sn` | Verified |
| Profiles: create | `charging/add_charging_mode`: a profile without `id`, with a free `number` (1-4) + `device_sn`; answers the new profile | Verified |
| Profiles: delete | `charging/delete_charging_mode` `{"id"}` | Verified |
| Port labels | `setting/set_port_remark` `{"device_sn", "port_name": "C1"…"A2", "remark"}` | Library |
| Unlocked animations | `egg/get_easter_egg_trigger_list` `{"device_sn"}` → `egg_trigger_list` | Verified |
| Custom images: list | `style/get_manual_clock_screensavers` `{"sn"}` | Library |
| Custom images: add / delete | `style/add_manual_clock_screensavers` `{"sn", "img_url", "hash_code"}` (a file already in Anker's storage), `style/delete_manual_clock_screensavers` `{"id"}` | Verified, not used (no upload endpoint) |
| Protocols per mode | `setting/get_protocol_status` / `set_protocol_status` (modes `ai`, `normal`) | Read verified; whether a change reaches the charger: `tools/validate.py` |

Clock images are baseline JPEGs of 480×200 pixels; the theme hash is the CRC32 of the file. The
charger only shows images from Anker's storage (one served by Home Assistant was tried).

## Not found

- **Renaming the charger:** `app/devicerelation/up_alias_name` needs `device_sn` + `alias_name` but
  answers "(10003) Failed to request"; five other candidates don't exist.
- **Energy statistics:** `power/get_day_power_data` refuses every date format tried. The charger
  doesn't report energy either, so the integration computes it from the power values.
- **Port protocol status:** `setting/get_port_protocol_status` needs a `version` that wasn't found.
- **Upload of clock images**, **playing hidden animations**, **choosing a holiday**, **brightness
  below 20 %**: no command or endpoint (or no effect).
