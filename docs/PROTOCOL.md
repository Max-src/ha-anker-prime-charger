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

The library's cache update drops values it doesn't know (`time_display`, the animation type), so
the coordinator keeps them itself; `tests/test_library_contract.py` notices if that changes.

## Custom charging mode

The charger keeps one set of custom settings: profile number, automatic deactivation
(`auto_exit_switch`), a power limit per port and allowed protocols per USB-C port (status `0a00`
fields `b8`, `ba`). Command `0206` sends the whole set and switches to the custom mode; the
charger then re-applies power on all ports (connected devices briefly disconnect, also with the
app).

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
- **Energy statistics:** `power/get_day_power_data` refuses every date format tried.
- **Port protocol status:** `setting/get_port_protocol_status` needs a `version` that wasn't found.
- **Upload of clock images**, **playing hidden animations**, **choosing a holiday**, **brightness
  below 20 %**: no command or endpoint (or no effect).
