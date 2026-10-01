# Anker Prime Charger for Home Assistant

A custom integration for Anker Prime chargers connected to the Anker app over Wi-Fi: live power
per port, and nearly everything the Anker app controls, from port switches to custom charging
profiles and clock themes.

## Supported devices

| Model | | Status |
|---|---|---|
| **A2345** | Anker Prime Charger 250W (6 ports, GaNPrime) | ✅ Supported: developed and tested on this charger |
| A91B2 | Anker Prime Charging Station 240W 8-in-1 (2 AC outlets, 4 USB-C, 2 USB-A) | 🟡 Possible: Wi-Fi, and the [library](https://github.com/thomluther/anker-solix-api) knows its status and AC outlet switches. Needs an owner to test it ([help wanted](#help-wanted-other-models)) |
| A2687 | Anker Prime Charger 160W (3 USB-C) | ❌ Bluetooth only: no cloud connection to reach it |
| A25X7 | Anker Prime Wireless Charging Station 3-in-1 | ❌ Bluetooth only: no cloud connection to reach it |

So far the integration was only developed and tested on the **Prime Charger 250W (A2345)**; the
rest of this page describes it. It only offers A2345 chargers when it is added.

Keep the charger's firmware up to date (in the app): according to Anker's user guide, *Dual laptop*
needs 1.1.14 or later, *Holiday updates* 1.1.1.4 or later, and the test features (custom charging
mode and profiles) 1.2.1.0 or later.

It is built on the MIT-licensed [anker-solix-api](https://github.com/thomluther/anker-solix-api)
library by thomluther, vendored in `custom_components/anker_prime_charger/solixapi/`
(`solixapi/VERSION.txt` gives the upstream commit). How the charger was decoded is in
[docs/PROTOCOL.md](docs/PROTOCOL.md); how the code is organised is in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## How it works

The charger has no local connection. Everything goes through the Anker cloud, like the app:

- **Live data and controls** go through Anker's MQTT server. Every 30 seconds (adjustable) the
  integration asks the charger for its status, and it answers within a second or two.
- **Settings stored in the Anker cloud** (custom profiles, port labels, test features, the theme
  list) are read every 10 minutes and changed directly. If the cloud is unreachable, only those
  entities are affected.

## Install

1. Copy `custom_components/anker_prime_charger` into `<Home Assistant config>/custom_components/`
   and restart Home Assistant.
2. Settings → Devices & services → Add integration → **Anker Prime Charger**.
3. Log in with the Anker account that **owns** the charger (a shared account can't use MQTT). The
   app and Home Assistant can use the same account at the same time. There is no country or
   server to choose: the integration finds them.

If you also use the `anker_solix` integration with MQTT on the same account, consider disabling it
to avoid two MQTT sessions.

### Options

| Option | Default | |
|---|---|---|
| Status request interval | 30 s | How often the charger is asked for its status (10-600 s) |
| Fast updates duration | 10 min | How long *Fast updates* run before stopping by themselves (1-60 min) |

Saving the options reloads the integration. Values that arrive between two status requests (e.g.
during *Fast updates*) are shown right away and don't delay the next request.

## Devices and entities

The charger is one device, and each port is a child device of it (Home Assistant 2026.9 and
later): **USB-C 1-4** and **USB-A**. The USB-A device covers both USB-A ports, because the charger
has a single control for both; their readings and labels are still separate (*A1 …*, *A2 …*). All
entities are enabled.

### Each port

| Entity | Notes |
|---|---|
| *(the port itself)* | The port on or off |
| Power, voltage, current | Per physical port (USB-A: *A1 …* and *A2 …*). Power has the port's maximum as attribute `max_power`: USB-C 1 140 W, USB-C 2-4 100 W, each USB-A 22.5 W |
| Energy | Energy delivered (kWh), for the Energy dashboard. Per physical port (USB-A: *A1 energy*, *A2 energy*) |
| Connected | On while a device is connected |
| Label | The port's name in the Anker app (USB-A: *A1 label*, *A2 label*) |
| Custom power limit | The port's maximum power in the custom charging mode: USB-C 0 W or 15-140 W (C1) / 15-100 W (C2-C4); USB-A 0, 15 or 24 W |
| Custom protocols (+ preset) | USB-C: the fast-charging protocols allowed in the custom charging mode, e.g. `scp,ufcs,pps11v`, `all` or `none`. Which ones are possible depends on the port's power (attribute `allowed`): 15-20 W `ufcs`; 21-22 W + `pps11v`, `pd12v`; 23-44 W + `scp`; 45 W and more + `pps16v`, `pps20v`, `xiaomi`. *Custom protocols preset*: All allowed at this power / None / Custom (pick those in *Custom protocols* or with the *Set protocols* action) |
| Timer, Timer duration, Timer end | Turn the port off after a duration in minutes (1 min to 23 h 55; the app only offers 5-minute steps) |
| Schedule start / end (+ time, days, days preset) | Scheduled start and end, each with its time and days (`mon,tue,…`, `all` or `none`). *Days preset*: Every day / Weekdays / Weekends / None (*Custom* for other days; pick those in *days* or with the *Set days* action). *Custom* stays selected, also after a restart, until the days change |

**Timer or schedule?** The *timer* is a one-off countdown: turn it on and the port switches off
after *Timer duration* (60 min if none is set; changing the duration applies to a running timer).
*Timer end* shows when, and is *Unknown* while no timer runs. The *schedule* repeats every week:
the port switches on at the start time and off at the end time, on the chosen days; start and end
are each turned on separately.

### Charger

| Entity | Notes |
|---|---|
| Total output power | Sum of all ports |
| Total output energy | Energy delivered by all ports (kWh), for the Energy dashboard |
| Charging mode | AI power / Connection priority / Dual laptop / Low power, and `Custom: <name>` for each custom profile (when *Custom charging mode* is on) |
| Priority ports | USB-C ports that get power first in Connection priority mode (up to two) |
| Automatic deactivation | Custom mode: when a port set to 0 W is used, go back to the previous mode |
| Maximum compatibility, Custom charging mode, Charging device identification | The app's *Test features* |
| Clock theme | Standard Style 1-3 (built into the charger), Anker's stock themes, and your images from the app (`Custom - <name>`) |
| Clock display | Show the clock screen |
| Time display | Show the time on top of a custom image (stock themes always show it) |
| Clock display start / end / days (+ days preset) | When the clock screen is shown |
| Holiday updates | Festive clock screens on holidays (the charger picks them) |
| Display brightness, Display timeout, Knob direction, Clock format | As in the app |
| Fast updates | Port values every second instead of every poll, until it stops by itself (see *Options*) |
| Refresh | Asks for the status now and re-reads the cloud settings |
| Hidden animation | Event when the charger plays a hidden animation (attribute `animation_type`) |
| Unlocked animations | How many hidden animations are unlocked, with their type and date |

### Energy dashboard

The charger only reports power, so the *Energy* sensors add up power × time themselves, at every
value the charger sends (the last value counts until the next one). Good to know:

- They start at 0 kWh: the charger keeps no energy history.
- Time while the charger is unreachable or Home Assistant is stopped isn't counted; the totals are
  kept across restarts.
- Precision follows the status request interval: a device that charges for a few seconds between
  two requests can be missed. *Fast updates* make it exact while they run.

Add them under Settings → Dashboards → Energy → **Individual devices**. If you add both *Total
output energy* and the per-port sensors, set *Total output energy* as the ports' **upstream
device**, or the same energy is counted twice. Data shows in the dashboard from the next full hour.

### Charging modes

How the charger shares its 250 W, from [Anker's user guide](https://support.anker.com/s/article/Anker-Prime-Charger-250W-6-Ports-GaNPrime-User-Guide-A2345)
(the names in the guide are in brackets). Every mode respects the port maximums: USB-C 1 140 W,
USB-C 2-4 100 W, each USB-A 22.5 W (both together 24 W when other ports are in use), and 240 W
in total with only two ports in use.

| Mode | How power is shared |
|---|---|
| AI power (*AI Power Mode*, the default) | Detects each device's need (high, medium or low) and adjusts the split |
| Connection priority (*Port Priority Mode*) | Up to two *Priority ports* get the most power; the others get what is left (e.g. all six ports: 70 W and 65 W for the priority ports, 45 W for the other USB-C ports, 24 W for USB-A) |
| Dual laptop (*Dual-Laptop Mode*) | With one or two ports in use, like Connection priority. With three or more: fixed 100 W on USB-C 1 and 2, 20 W on USB-C 3, 15 W on USB-C 4, 15 W on USB-A |
| Low power (*Low Current Mode*) | Fixed: 65 W on USB-C 1, 20 W on USB-C 2-4, 15 W on USB-A. Meant for overnight charging |
| Custom (needs the *Custom charging mode* test feature) | Your own limit per port: USB-C 0 W or 15 W up to its maximum, USB-A 0, 15 or 24 W; up to 4 saved profiles |

The power shown is what each device asks for: it drops as a battery gets full, whatever the mode.

### Fast-charging protocols

In the custom charging mode, each USB-C port can allow or block extra fast-charging protocols
(*Custom protocols*). Standard USB Power Delivery (5, 9, 15 and 20 V, plus 28 V on USB-C 1) is
not one of them: the charger always offers it. Blocking a protocol doesn't stop a device from
charging; it falls back to standard USB PD, which can be slower for that device.

| Protocol | Name in the app | What it is | Typical devices | From |
|---|---|---|---|---|
| `ufcs` | UFCS | Universal Fast Charging Specification: a Chinese industry standard shared by several phone makers, so their phones fast-charge on any UFCS charger | Recent Huawei, Honor, Oppo, Vivo, Xiaomi phones | 15 W |
| `pps11v` | 5-11V PPS | USB PD *Programmable Power Supply* up to 11 V: the phone asks for exactly the voltage and current it wants, in small steps, which charges faster and cooler | Samsung *Super Fast Charging*, Google Pixel, most recent Android phones | 21 W |
| `pd12v` | PD 12V | An optional fixed 12 V step of USB PD | A few tablets and accessories; rarely needed | 21 W |
| `scp` | SCP | Huawei *SuperCharge Protocol*: low voltage, high current | Huawei and Honor phones | 23 W |
| `pps16v` | 5-16V PPS | PPS up to 16 V | Devices that use PPS at higher power, e.g. some tablets | 45 W |
| `pps20v` | 4.5-21V PPS | PPS over the widest range, up to 21 V | Some laptops and the fastest-charging PPS phones | 45 W |
| `xiaomi` | Xiaomi HyperCharge | Xiaomi's own fast charging | Xiaomi, Redmi and Poco phones | 45 W |

*From*: the port's custom power needed to allow it (Anker's cloud table, the attribute `allowed`).
When unsure, allow everything the power permits (*Custom protocols preset* → *All allowed at
this power*): the device picks what it supports.

**Huawei:** the library also knows a `huawei` protocol (Huawei's own high-power SuperCharge, on
other Anker chargers). This charger never allows it at any power, and the app doesn't show it;
Huawei and Honor phones use SCP or UFCS here.

**Clock screen:** the charger only shows the clock when the display timeout is not *Never* (the
guide's *Always On*), the clock screensaver is selected and the screen wasn't turned off with the
knob.

**About the custom power limits and protocols:** the charger keeps one set of custom-mode
settings. Changing a limit or protocols switches the charger to the custom mode and makes it
re-apply power on **all** ports, which briefly disconnects the connected devices. The charger has
no command for a single port, so each change does this: to change several values at once, use the
[set custom settings](#action-set-custom-settings) action rather than the entities one by one. Nothing
is sent when a value doesn't change.

## Actions: custom profiles

Profiles are the app's custom modes (at most 4). The actions target the **Charging mode** entity.
The settings fields are optional: `auto_deactivation`, `c1_power` … `c4_power`, `a_power`,
`c1_protocols` … `c4_protocols`. They are checked like in the app (power steps, protocols allowed
at each power, 250 W in total).

| Action | |
|---|---|
| `anker_prime_charger.save_custom_profile` | Change a profile (`profile`, optional `new_name`); with `from_charger: true` start from the charger's current custom settings |
| `anker_prime_charger.create_custom_profile` | Create a profile (`name`) from the charger's current custom settings |
| `anker_prime_charger.delete_custom_profile` | Delete a profile (`profile`) |

```yaml
action: anker_prime_charger.save_custom_profile
target:
  entity_id: select.250w_prime_charger_charging_mode
data:
  profile: Desk
  c1_power: 65
  c1_protocols: [ufcs, scp, pps11v, pps16v, pps20v]
```

Saving doesn't apply a profile: select it in *Charging mode* for that.

## Action: set custom settings

`anker_prime_charger.set_custom_settings` changes several of the charger's custom-mode settings at
once: the same optional fields as the profile actions (`auto_deactivation`, `c1_power` …
`a_power`, `c1_protocols` … `c4_protocols`), checked the same way; unset fields keep their value.
It targets the **Charging mode** entity and switches the charger to the custom mode.

Any custom-mode change makes the charger cut every port for 2-4 seconds while devices
renegotiate (also when done in the app). Changing the entities one by one does that each time;
this action sends everything in one command, so it happens once. Nothing is sent if nothing
changes.

```yaml
action: anker_prime_charger.set_custom_settings
target:
  entity_id: select.250w_prime_charger_charging_mode
data:
  c1_power: 100
  c2_power: 45
  c2_protocols: [scp, ufcs, pps11v]
  c4_power: 0
```

## Action: set days

`anker_prime_charger.set_days` sets the days of a schedule with a day picker. It targets a *days*
entity: a port's *Schedule start days* / *Schedule end days*, or the charger's *Clock display days*.
No days selected: none.

```yaml
action: anker_prime_charger.set_days
target:
  entity_id: text.250w_prime_charger_usb_c_1_schedule_end_days
data:
  days: [mon, wed, fri]
```

## Action: set protocols

`anker_prime_charger.set_protocols` sets the fast-charging protocols a USB-C port allows in the
custom charging mode, with a picker. It targets the port's *Custom protocols* entity. No protocols
selected: none. Like every custom-mode change, it briefly disconnects the charging devices.

```yaml
action: anker_prime_charger.set_protocols
target:
  entity_id: text.250w_prime_charger_usb_c_1_custom_protocols
data:
  protocols: [scp, ufcs, pps16v]
```

## Limitations

- **USB-A:** one on/off, timer, schedule and power limit for both USB-A ports (the charger has a
  single control for both).
- **Renaming the charger** only works in Home Assistant (device page); the Anker cloud's rename
  call couldn't be found.
- **Adding clock images** only works in the app (no upload endpoint was found); they then appear
  in *Clock theme*.
- **Hidden animations** can't be played on demand; the charger plays them on its own.
- **Holidays** can't be chosen; *Holiday updates* is a single on/off.
- **Display brightness** stops at 20 %, like in the app (lower values have no visible effect).

## Help wanted: other models

The integration reaches a charger through the Anker cloud, like the app away from home, so only
chargers on Wi-Fi can be supported; Bluetooth-only chargers never connect to the cloud.

The **Prime Charging Station 240W (A91B2)** is the next candidate: according to the library, its
status and live port values are the same as the 250W's, plus its two AC outlets. What else it
shares with the 250W (clock themes, custom profiles, timers, …) is unknown. If you own one and
would like to help, open an issue: testing it means installing the integration and running the
capture scripts in `tools/` while using the app (see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)).

## Recorder

*Fast updates* change about 20 sensors every second while on. To keep them out of the history
database, exclude them in `configuration.yaml`, for example:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.250w_prime_charger_usb_*_voltage
      - sensor.250w_prime_charger_usb_*_current
```

Don't exclude the *Energy* sensors (the Energy dashboard needs their history) nor, if you use
them, the *Power* sensors.

## Troubleshooting

- **A port doesn't reach 140 W:** only USB-C 1 does, with a cable rated 140 W or more. A 16"
  MacBook Pro with M1/M2 needs a USB-C to MagSafe cable; M3 and later also charge at 140 W over
  USB-C. Every device draws less as its battery gets full (Anker's user guide).
- **Values differ from the app:** the app shows values the charger sends to the cloud now and
  then; the integration asks the charger directly, so it is usually closer to the charger's screen.
- **The clock screen doesn't show:** see *Clock screen* under [Charging modes](#charging-modes).
- **Entities are unavailable:** the charger stopped answering (unplugged, offline, Wi-Fi). They
  come back with its next answer.

Diagnostics can be downloaded from the device page (email, password, tokens, serials, network
details and image links are removed). Debug logging:

```yaml
logger:
  logs:
    custom_components.anker_prime_charger: debug
```

## License

MIT, see [LICENSE](LICENSE). The vendored library keeps its own MIT license
(`custom_components/anker_prime_charger/solixapi/LICENSE`).
