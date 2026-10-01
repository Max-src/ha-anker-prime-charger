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

## Devices and entities

The charger is one device, and each port is a child device of it (Home Assistant 2026.9 and
later): **USB-C 1-4** and **USB-A**. The USB-A device covers both USB-A ports, because the charger
has a single control for both; their readings and labels are still separate (*A1 …*, *A2 …*). All
entities are enabled.

### Each port

| Entity | Notes |
|---|---|
| *(the port itself)* | The port on or off |
| Power, voltage, current | Per physical port (USB-A: *A1 …* and *A2 …*) |
| Connected | On while a device is connected |
| Label | The port's name in the Anker app (USB-A: *A1 label*, *A2 label*) |
| Custom power limit | The port's maximum power in the custom charging mode: USB-C 0 W or 15-140 W (C1) / 15-100 W (C2-C4); USB-A 0, 15 or 24 W |
| Custom protocols | USB-C: the fast-charging protocols allowed in the custom charging mode, e.g. `scp,ufcs,pps11v`, `all` or `none`. Which ones are possible depends on the port's power (attribute `allowed`) |
| Timer, Timer duration, Timer end | Turn the port off after a duration (5 min to 23 h 55, 5-minute steps) |
| Schedule start / end (+ time, days) | Scheduled start and end, each with its time and days (`mon,tue,…`, `all` or `none`) |

### Charger

| Entity | Notes |
|---|---|
| Total output power | Sum of all ports |
| Charging mode | AI power / Connection priority / Dual laptop / Low power, and `Custom: <name>` for each custom profile (when *Custom charging mode* is on) |
| Priority ports | USB-C ports that get power first in Connection priority mode (up to two) |
| Automatic deactivation | Custom mode: when a port set to 0 W is used, go back to the previous mode |
| Maximum compatibility, Custom charging mode, Charging device identification | The app's *Test features* |
| Clock theme | Standard Style 1-3 (built into the charger), Anker's stock themes, and your images from the app (`Custom - <name>`) |
| Clock display | Show the clock screen |
| Time display | Show the time on top of a custom image (stock themes always show it) |
| Clock display start / end / days | When the clock screen is shown |
| Holiday updates | Festive clock screens on holidays (the charger picks them) |
| Display brightness, Display timeout, Knob direction, Clock format | As in the app |
| Fast updates | Port values every second instead of every poll, until it stops by itself (see *Options*) |
| Refresh | Asks for the status now and re-reads the cloud settings |
| Hidden animation | Event when the charger plays a hidden animation (attribute `animation_type`) |
| Unlocked animations | How many hidden animations are unlocked, with their type and date |

**About the custom power limits and protocols:** the charger keeps one set of custom-mode
settings. Changing a limit or protocols switches the charger to the custom mode and makes it
re-apply power on **all** ports, which briefly disconnects the connected devices (the app does
the same). Nothing is sent when a value doesn't change.

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

## Troubleshooting

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
