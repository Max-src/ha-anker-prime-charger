# Anker Prime Charger for Home Assistant

Monitor your charging devices and control your Anker Prime charger from Home Assistant.
See power and energy use for each port, choose charging modes, set timers and schedules,
and change the charger's clock and display settings.

Developed for my Anker Prime Charger (250W, 6 Ports, GaNPrime - model A2345). Will extend support to other Anker chargers in future.

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/A2345-main-charger-600x450.png" alt="Anker Prime Charger (250W, 6 Ports, GaNPrime - model A2345)">

[Installation](#installation) · [Setup](#setup) · [Using the integration](#using-the-integration) ·
[Automations](#automations) · [Compatibility](#compatibility) · [Troubleshooting](#troubleshooting)

## Features

|                      | What you can do                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------------------- |
| Power and energy     | View power, voltage, current and estimated energy for every physical port, plus charger totals  |
| Port controls        | Turn charging on or off, change port labels, and check whether a device is connected            |
| Charging modes       | Select AI power, Connection priority, Dual laptop, Low power or a saved custom profile          |
| Custom charging      | Set power limits and allowed fast-charging protocols, and manage up to four profiles            |
| Timers and schedules | Stop charging after a countdown or set repeating weekly on/off schedules                        |
| Screen and clock     | On its own Screen device: themes, clock screensaver schedule, brightness, timeout, clock format |
| Extra settings       | Access the app's test features, holiday screensaver and hidden-animation events                 |

This integration communicates through the **Anker cloud**, not directly over your local network:
the charger offers no local connection (none of its network ports accept connections). Both Home
Assistant and the charger need internet access. You can continue using the Anker app.

## Installation

### Before you start

- Use **Home Assistant 2026.9.0 or newer**.
- Set up your charger in the **Anker app**, connect it to Wi-Fi and check that you can control it.
- Have the login details for the Anker account that **owns** the charger. Shared accounts cannot
  use the connection required by this integration.
- Update the charger's firmware in the app, especially before using custom charging features.
- Check [Compatibility](#compatibility) before installing for a different model.

### HACS (recommended)

[HACS](https://hacs.xyz/docs/use/download/download/) must already be installed in Home Assistant.

1. Open **HACS** and search for **Anker Prime Charger**.
2. Open the integration's page and select **Download**.
3. Restart Home Assistant, then continue to [Setup](#setup).

**Not listed in HACS yet?** Until this integration is included in the default HACS catalog,
add it as a custom repository first:

1. In HACS, open the **three-dot menu** and select **Custom repositories**.
2. Enter `https://github.com/Max-src/ha-anker-prime-charger` as the repository URL.
3. Select **Integration** as the type and click **Add**.
4. Search for **Anker Prime Charger** and follow the download steps above.

### Manual installation

1. Download the repository using **Code > Download ZIP** on
   [GitHub](https://github.com/Max-src/ha-anker-prime-charger), then extract it.
2. Open your Home Assistant configuration folder, the folder containing `configuration.yaml`.
3. Create a `custom_components` folder there if it does not exist.
4. Copy **only** the `anker_prime_charger` folder from the download's `custom_components` folder
   into your Home Assistant `custom_components` folder. Keep all its files and subfolders.
5. Restart Home Assistant, then continue to [Setup](#setup).

The result should look like this, without an extra nested repository folder:

```text
config/
  configuration.yaml
  custom_components/
    anker_prime_charger/
      __init__.py
      manifest.json
      ...
      brand/
      solixapi/
      translations/
```

You do not need to copy the repository's tests, documentation or developer tools.

### Updating

Update through HACS, or replace the integration files manually using the same folder layout.
Restart Home Assistant afterwards to load the changes. You do not need to remove and re-add
the integration for a normal update.

## Setup

1. Go to **Settings > Devices & services > Add integration**.
2. Search for **Anker Prime Charger**.
3. Sign in with your Anker account's email and password.
4. Select your charger if prompted, then finish setup.

The integration finds the account's region automatically. No country, server address, charger
IP address or YAML configuration is needed.

To change the Anker email or password later, open the integration and choose **Reconfigure**.
The account must own the same charger; add the integration again for a different charger.

If you also use the `anker_solix` integration with MQTT on the same Anker account, consider
disabling its MQTT connection to avoid competing sessions.

## Using the integration

Open the integration under **Settings > Devices & services** to find your charger and its ports.
You can add their entities to dashboards or use them in automations.

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-charger-device.png" alt="The charger's device page in Home Assistant" width="700">

The charger has six child devices: **USB-C 1**, **USB-C 2**, **USB-C 3**, **USB-C 4**, **USB-A**
and **Screen**. The Screen device holds the display settings, the clock screensaver and the
hidden animations, named as in the charger's _Settings_ menu. The USB-A device contains
separate **A1** and **A2** readings, energy sensors and labels, but
its on/off switch, timer, schedule and custom power limit control **both USB-A ports together**.

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-port-device.png" alt="A USB-C port's device page in Home Assistant" width="700">

<details>
<summary>All entities</summary>

**Charger**

| Entity                                                                      | What it does                                                                                  |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Total output power, Total output energy                                     | Sum of all ports (W), and the energy delivered (kWh) for the Energy dashboard                 |
| Charging mode                                                               | AI power, Connection priority, Dual laptop, Low power, and `Custom: <name>` per saved profile |
| Priority ports                                                              | The one or two USB-C ports favoured in Connection priority mode                               |
| Automatic deactivation                                                      | Custom mode: leave it when a port set to 0 W is used                                          |
| Maximum compatibility, Custom charging mode, Charging device identification | The app's test features                                                                       |
| Fast updates                                                                | Readings every second for a while (see the options)                                           |
| Refresh                                                                     | Ask for the status now and re-read the cloud settings                                         |

**Screen**

| Entity                                               | What it does                                                                          |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Brightness, Timeout, Knob orientation, Clock format  | As in the charger's _Settings_ menu (Timeout: _Always on_, 30 seconds ... 30 minutes) |
| Clock screensaver                                    | Show the clock when the screen times out                                              |
| Clock screensaver start / end / days (+ days preset) | When the clock screensaver may be shown                                               |
| Clock theme                                          | Standard Style 1-3, Anker's stock themes and your own images (`Custom - <name>`)      |
| Time display                                         | The time over a custom image (stock themes always show it)                            |
| Holiday screensaver                                  | Festive themes on holidays, chosen by the charger (the guide's _Holiday Update_)      |
| Hidden animation, Unlocked animations                | Event when the screen plays a hidden animation; how many are unlocked                 |

**Each port** (USB-C 1-4, and USB-A for both USB-A ports)

| Entity                                                | What it does                                                                                                             |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| _(the port itself)_                                   | Charging on or off                                                                                                       |
| Power, Voltage, Current                               | Live readings. Power has the port's maximum as attribute `max_power` (USB-C 1 140 W, USB-C 2-4 100 W, each USB-A 22.5 W) |
| Energy                                                | Energy delivered (kWh), for the Energy dashboard                                                                         |
| Connected                                             | On while a device is plugged in                                                                                          |
| Label                                                 | The port's name in the Anker app                                                                                         |
| Custom power limit                                    | The port's limit in custom mode                                                                                          |
| Custom protocols (+ preset)                           | USB-C: optional fast-charging protocols allowed in custom mode (attribute `allowed`: what the port's power permits)      |
| Timer, Timer duration, Timer end                      | One-off countdown that turns the port off                                                                                |
| Schedule start / end, with time, days and days preset | Weekly on and off times                                                                                                  |

On the USB-A device, readings, energy and labels exist for **A1** and **A2** separately.

</details>

### Live readings and refresh

Power, voltage and current are requested every **30 seconds** by default. Use **Refresh** to
request the latest status and re-read cloud settings, or turn on **Fast updates** for readings
roughly every second while you watch a charging session.

Custom profiles, port labels, test features and the theme list are refreshed from the cloud
every **10 minutes**. Changes from the app may take until that refresh to appear.

In the integration's options you can change:

| Option                  | Default    | Range          |
| ----------------------- | ---------- | -------------- |
| Status request interval | 30 seconds | 10-600 seconds |
| Fast updates duration   | 10 minutes | 1-60 minutes   |

Fast updates stop automatically after the selected duration. Saving options reloads the integration.

### Energy dashboard

Use **Total output energy** to track the whole charger, or the individual **Energy** sensors
to track USB-C 1-4 and USB-A 1-2 separately.

1. Open **Settings > Dashboards > Energy**.
2. Add the energy sensors under **Individual devices**.
3. If you add both the total and the individual ports, assign **Total output energy** as the
   ports' **upstream device** to avoid counting the same energy twice.

Allow time for Home Assistant to collect hourly statistics before expecting dashboard data.

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-energy-dashboard.png" alt="Charger ports in the Energy dashboard" width="700">

**These are estimates of energy delivered to devices, not electricity drawn from the wall.**
They exclude conversion losses and standby consumption. Totals start at zero and are retained
across restarts. Time while Home Assistant is stopped or the charger is marked unavailable is
not counted. Short charging sessions between readings can be missed; Fast updates improve the
estimate but do not make it a calibrated energy measurement.

### Charging modes and profiles

Choose a mode using **Charging mode**:

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-charging-mode.png" alt="The Charging mode list with custom profiles" width="700">

| Mode                | Use it for                                                        |
| ------------------- | ----------------------------------------------------------------- |
| AI power            | Let the charger distribute power according to connected devices   |
| Connection priority | Give up to two selected **Priority ports** preference             |
| Dual laptop         | Prioritize charging two laptops on USB-C 1 and 2                  |
| Low power           | Use the charger's reduced-power allocation, for example overnight |
| Custom profiles     | Apply your own saved power limits and protocol settings           |

Enable **Custom charging mode** (one of the app's test features) to use custom profiles.
You can keep up to **four** profiles and select them as `Custom: <name>` in **Charging mode**.
The actual power drawn still depends on the connected device, its battery level and cable.

**Changing custom power limits or protocols briefly interrupts charging on all ports**, usually
for 2-4 seconds while devices renegotiate. To change several settings together, use the
**Set custom settings** action so the charger receives one combined change.

For USB-C protocols, **Custom protocols preset > All allowed at this power** is a useful default.
Available choices depend on the port's power limit. Standard USB Power Delivery remains
available even when these optional protocols are disabled.

<details>
<summary>How each mode shares power</summary>

From [Anker's user guide](https://support.anker.com/s/article/Anker-Prime-Charger-250W-6-Ports-GaNPrime-User-Guide-A2345).
Every mode keeps to the port maximums (USB-C 1 140 W, USB-C 2-4 100 W, each USB-A 22.5 W, both
USB-A together 24 W when other ports are busy) and to 250 W in total (240 W with two ports in use).

| Mode                | Power per port                                                                                                                                               |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| AI power            | Adjusted to what each device needs (high, medium or low)                                                                                                     |
| Connection priority | The priority ports get the most. Example with all six ports in use: 70 W and 65 W for the two priority ports, 45 W for the other USB-C ports, 24 W for USB-A |
| Dual laptop         | With one or two ports in use, like Connection priority. With three or more: fixed 100 W on USB-C 1 and 2, 20 W on USB-C 3, 15 W on USB-C 4, 15 W on USB-A    |
| Low power           | Fixed 65 W on USB-C 1, 20 W on USB-C 2-4, 15 W on USB-A (140 W in total)                                                                                     |
| Custom              | Your own limit per port: USB-C 0 W or 15 W up to its maximum, USB-A 0, 15 or 24 W                                                                            |

These are upper limits: a device only draws what it needs, and less as its battery fills.

</details>

<details>
<summary>Fast-charging protocols explained</summary>

In custom mode each USB-C port can allow or block these optional protocols. Standard USB Power
Delivery (5, 9, 15, 20 V, and 28 V on USB-C 1) always stays available, so blocking a protocol
never stops charging: the device falls back to standard USB PD, which can be slower for it.

| Protocol                      | What it is                                                                                                            | Typical devices                                                         | Needs at least |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | -------------- |
| UFCS (`ufcs`)                 | Universal Fast Charging Specification, a fast-charging standard shared by several phone makers                        | Recent Huawei, Honor, Oppo, Vivo, Xiaomi phones                         | 15 W           |
| 5-11V PPS (`pps11v`)          | USB PD _Programmable Power Supply_: the device asks for exactly the voltage it wants, which charges faster and cooler | Samsung _Super Fast Charging_, Google Pixel, most recent Android phones | 21 W           |
| PD 12V (`pd12v`)              | An optional fixed 12 V step of USB PD                                                                                 | A few tablets and accessories                                           | 21 W           |
| SCP (`scp`)                   | Huawei _SuperCharge Protocol_                                                                                         | Huawei and Honor phones                                                 | 23 W           |
| 5-16V PPS (`pps16v`)          | PPS up to 16 V                                                                                                        | Devices using PPS at higher power, e.g. some tablets                    | 45 W           |
| 4.5-21V PPS (`pps20v`)        | PPS over its widest range, up to 21 V                                                                                 | Some laptops and the fastest-charging PPS phones                        | 45 W           |
| Xiaomi HyperCharge (`xiaomi`) | Xiaomi's own fast charging                                                                                            | Xiaomi, Redmi and Poco phones                                           | 45 W           |

_Needs at least_: the port's custom power limit from which the charger allows it. The protocol
pickers also offer `huawei` (Huawei's high-power SuperCharge, known from other Anker chargers),
but this charger never allows it; Huawei and Honor phones use SCP or UFCS here.

When unsure, choose **Custom protocols preset > All allowed at this power** and let the device
pick what it supports.

</details>

### Timers and weekly schedules

- **Timer:** set **Timer duration**, then turn on **Timer**. The port turns off when the countdown
  ends. Durations range from 1 minute to 23 hours 55 minutes; the default is 60 minutes if unset.
  Changing the duration also changes a running timer. **Timer end** shows the end time, or
  _Unknown_ when no timer is running.
- **Schedule:** set the start/end times and days, then enable **Schedule start** and/or
  **Schedule end**. They repeat weekly and are enabled independently.
- **Days preset:** choose Every day, Weekdays, Weekends or None. For another combination, edit
  the days entity or use **Set days**; the preset then shows Custom.

### Screen and clock

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-screen-device.png" alt="The charger's Screen device page in Home Assistant" width="700">

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-clock-theme.png" alt="Choosing a clock theme" width="700">

Everything about the charger's screen is on its **Screen** device. Choose a **Clock theme**,
turn on **Clock screensaver**, and optionally set its start time, end time and days.
**Brightness**, **Timeout**, **Knob orientation** and **Clock format** (12/24-hour) are there
too.

The clock screensaver shows when the screen times out, so **Timeout** must not be **Always on**,
and the screen must not have been turned off using the knob.

Upload personal clock images through the Anker app first; they appear as `Custom - <name>` in
**Clock theme** after a refresh. **Time display** controls the time overlay on custom images;
stock themes always show it. **Holiday screensaver** shows festive themes chosen by the charger.

## Automations

Use the entities in Home Assistant's automation editor as you would any other switch, sensor
or selector. Extra actions are available under **Developer tools > Actions** and in automations.

| Action                                      | Target                | Purpose                                          |
| ------------------------------------------- | --------------------- | ------------------------------------------------ |
| `anker_prime_charger.set_custom_settings`   | The charger           | Apply several custom settings in one command     |
| `anker_prime_charger.create_custom_profile` | The charger           | Save the current settings as a new named profile |
| `anker_prime_charger.save_custom_profile`   | The charger           | Edit or rename an existing profile               |
| `anker_prime_charger.delete_custom_profile` | The charger           | Delete a named profile                           |
| `anker_prime_charger.set_days`              | A port, or the Screen | Choose a schedule's days with a day picker       |
| `anker_prime_charger.set_protocols`         | A USB-C port          | Choose allowed protocols with a picker           |

Actions target **devices**: the charger, or one of its port devices. In the action editor, pick
the device from the list; several ports can be targeted at once. An **area** or **label** works
too: the action applies to the devices in it that it suits (e.g. a profile action to the charger,
**Set protocols** to its USB-C ports). Port devices follow the charger's area. Saving a profile does **not**
apply it. Select the profile in **Charging mode** to activate it.

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-set-custom-settings.png" alt="The Set custom settings action in the action editor" width="700">

<details>
<summary>Action examples and custom settings</summary>

The examples use placeholders for device IDs. To get the real YAML, build the action in the
editor (choose the device from the list), then select **Edit in YAML**.

Custom settings accept `auto_deactivation`, `c1_power` through `c4_power`, `a_power`, and
`c1_protocols` through `c4_protocols`. For **Set custom settings**, unspecified fields keep their
current values. USB-C limits are 0 W or 15 W up to the port maximum (140 W for C1, 100 W for C2-C4).
USB-A accepts 0, 15 or 24 W for the pair. The combined limit cannot exceed 250 W.
Protocol choices are validated against the selected power.

Apply several settings at once (this switches the charger to custom mode):

```yaml
action: anker_prime_charger.set_custom_settings
target:
  device_id: <the charger's device id>
data:
  c1_power: 100
  c2_power: 45
  c2_protocols: [scp, ufcs, pps11v]
  c4_power: 0
```

Create a profile from the charger's current settings:

```yaml
action: anker_prime_charger.create_custom_profile
target:
  device_id: <the charger's device id>
data:
  name: Desk
```

Edit an existing profile. Add `new_name` to rename it, or `from_charger: true` to start from
the current charger settings instead of the saved profile:

```yaml
action: anker_prime_charger.save_custom_profile
target:
  device_id: <the charger's device id>
data:
  profile: Desk
  c1_power: 65
  c1_protocols: [ufcs, scp, pps11v, pps16v, pps20v]
```

Delete a profile:

```yaml
action: anker_prime_charger.delete_custom_profile
target:
  device_id: <the charger's device id>
data:
  profile: Desk
```

Choose schedule days (an empty list selects none). For a port, `schedule` picks its scheduled
`start` or `end`:

```yaml
action: anker_prime_charger.set_days
target:
  device_id: <the USB-C 1 port's device id>
data:
  schedule: end
  days: [mon, wed, fri]
```

Target the Screen device instead for the clock screensaver's days (no `schedule` needed):

```yaml
action: anker_prime_charger.set_days
target:
  device_id: <the Screen device's id>
data:
  days: [sat, sun]
```

Choose optional fast-charging protocols (an empty list disables them):

```yaml
action: anker_prime_charger.set_protocols
target:
  device_id: <the USB-C 1 port's device id>
data:
  protocols: [scp, ufcs, pps16v]
```

</details>

## Compatibility

Development and testing currently target the **Anker Prime Charger 250W, 6 ports (A2345)**.
Only this model is offered during setup; the features above describe this charger.

| Device                                                 | Status                                                             |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| Anker Prime Charger 250W (A2345)                       | Supported and tested                                               |
| Anker Prime Charging Station 240W 8-in-1 (A91B2)       | Not supported yet; a Wi-Fi model worth investigating with an owner |
| Anker Prime Charger 160W (A2687)                       | Not supported; Bluetooth only                                      |
| Anker Prime Wireless Charging Station 3-in-1 (A25X7)   | Not supported; Bluetooth only                                      |
| Anker 150W Charging Base for Prime power banks (A1903) | Not supported; nothing known about it yet                          |

Bluetooth-only devices cannot use this cloud integration. If you own an A91B2 and would like
to help test it, [open an issue](https://github.com/Max-src/ha-anker-prime-charger/issues).

Some features require newer charger firmware. Keep it updated through the Anker app and consult
[Anker's A2345 user guide](https://support.anker.com/s/article/Anker-Prime-Charger-250W-6-Ports-GaNPrime-User-Guide-A2345)
for hardware limits and charging-mode details.

## Troubleshooting

| Problem                                               | What to check                                                                                                          |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Integration does not appear                           | Restart Home Assistant after installation. For a manual install, check the folder layout above and refresh the browser |
| Charger is not found                                  | Confirm it is an A2345, online in the Anker app, and owned by the account you used to sign in                          |
| Entities are unavailable                              | Check charger power, Wi-Fi and internet access. Readings return when the charger answers again                         |
| App settings have not appeared                        | Use **Refresh**, or wait for the 10-minute cloud-settings refresh                                                      |
| App and Home Assistant power readings differ          | They can sample at different times; charging power changes with device demand                                          |
| Custom profiles are missing                           | Enable the **Custom charging mode** test feature and check for firmware updates                                        |
| Charging briefly stops after changing custom settings | The charger reapplies settings on all ports. Use **Set custom settings** for a combined change                         |
| USB-A ports switch together                           | This is a charger limitation; their power and energy readings are still separate                                       |
| Clock screen is not shown                             | On the Screen device: check **Clock screensaver**, its schedule, and that **Timeout** is not _Always on_               |
| A port does not reach its maximum power               | Check the charging mode, cable and device capabilities. Only USB-C 1 supports 140 W; charging slows as batteries fill  |

Renaming the charger is supported in Home Assistant only. Uploading clock images still requires
the Anker app. Hidden animations cannot be triggered on demand, individual holidays cannot be
chosen, and brightness below 20% has no visible effect.

For a bug report, [open an issue](https://github.com/Max-src/ha-anker-prime-charger/issues)
with your charger model, Home Assistant version and steps to reproduce the problem. Download
diagnostics from the device page if needed. Sensitive fields are redacted, but review any
diagnostics or logs before sharing them; never include account credentials or tokens.

<details>
<summary>Enable debug logging</summary>

Add this to `configuration.yaml` (merge it with an existing `logger` section if present),
then restart Home Assistant:

```yaml
logger:
  logs:
    custom_components.anker_prime_charger: debug
```

Disable debug logging again after collecting the relevant logs.

</details>

<details>
<summary>Reduce history database usage during Fast updates</summary>

Fast updates generate frequent sensor readings. You can exclude voltage and current from
Recorder in `configuration.yaml`, adjusting these example IDs to match your entities:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.250w_prime_charger_usb_*_voltage
      - sensor.250w_prime_charger_usb_*_current
```

Merge this with any existing `recorder` configuration. Keep the energy sensors, and any power
sensors you use in the Energy dashboard, included in Recorder.

</details>

## Development and credits

This integration uses the [anker-solix-api](https://github.com/thomluther/anker-solix-api)
library by thomluther. A copy is bundled with the integration, so no separate library setup
is required.

For contributing or investigating other models, see [Development](docs/DEVELOPMENT.md) and
the [protocol notes](docs/PROTOCOL.md). The [tools](tools) folder contains optional developer
scripts for investigating the charger's cloud and MQTT behavior; it is not required for installation.

## License

MIT, see [LICENSE](LICENSE). The bundled library retains its own
[MIT license](custom_components/anker_prime_charger/solixapi/LICENSE).
