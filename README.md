# Anker Prime Charger for Home Assistant

Monitor your charging devices and control your Anker Prime charger from Home Assistant.
See power and energy use for each port, choose charging modes, set timers and schedules,
and change the charger's clock and display settings.

Developed for my Anker Prime Charger (250W, 6 Ports, GaNPrime - model A2345). Will extend support to other Anker chargers in future.

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/A2345-main-charger-600x450.png" alt="Anker Prime Charger (250W, 6 Ports, GaNPrime - model A2345)">

[Installation](#installation) · [Setup](#setup) · [Using the integration](#using-the-integration) ·
[Automations](#automations) · [Compatibility](#compatibility) · [Known limitations](#known-limitations) · [Troubleshooting](#troubleshooting)

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
| Dashboard cards      | The charger and its port outputs as in the Anker app, set up with the visual editor             |

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

The simplest way: download `anker_prime_charger.zip` from the
[latest release](https://github.com/Max-src/ha-anker-prime-charger/releases/latest) and
extract it into a new `custom_components/anker_prime_charger` folder in your Home Assistant
configuration folder (the folder containing `configuration.yaml`). The zip holds the
integration's files directly. Then restart Home Assistant and continue to [Setup](#setup).

Or copy it from the repository:

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

### Removing the integration

1. Go to **Settings > Devices & services**, open **Anker Prime Charger**, and in the menu (⋮)
   of the charger's entry choose **Delete**. Its devices and entities are removed with it.
2. To remove the files too: in HACS, open **Anker Prime Charger** and choose **Remove**; for a
   manual install, delete the `custom_components/anker_prime_charger` folder.
3. Restart Home Assistant.

Nothing changes on the charger or in your Anker account: its settings, custom profiles and clock
images stay, and the Anker app keeps working.

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
and **Screen**. Give the charger an area and leave the child devices' area empty: they follow
the charger's. The Screen device holds the display settings, the clock screensaver and the
hidden animations, named as in the charger's _Settings_ menu. The USB-A device contains
separate **A1** and **A2** readings, energy sensors and labels, but
its on/off switch, timer, schedule and custom power limit control **both USB-A ports together**.

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-port-device.png" alt="A USB-C port's device page in Home Assistant">

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

### How data is updated

The charger sends its status through the Anker cloud (MQTT). Home Assistant asks for it every
**30 seconds** by default, and changes the charger reports in between (a port switched on the
charger, a device plugged in, a setting changed in the app) arrive as soon as it sends them.
A command from Home Assistant shows its result with the charger's next status, usually within
seconds. Use **Refresh** to request the latest status and re-read cloud settings, or turn on
**Fast updates** for readings roughly every second while you watch a charging session.

If the charger stops answering (unplugged, off Wi-Fi), its entities become unavailable after
about **90 seconds** without a status; after an **hour** a repair under **Settings > Repairs**
says so. Both clear on their own when it answers again.

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

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-charging-mode.png" alt="The Charging mode list with custom profiles">

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

**Changing the charging mode, or custom power limits or protocols, briefly interrupts charging
on all ports**, usually for 2-4 seconds while devices renegotiate their power. The charger's
firmware restarts every port to apply the new power split; the Anker app does exactly the same,
so it can't be avoided. To keep it to a minimum:

- Selecting the mode that is already active does nothing (no interruption). Selecting a custom
  profile always applies it, which restores its saved settings.
- To change several custom settings together, use the **Set custom settings** action: one
  interruption instead of one per setting.
- Change modes from automations at times you're unlikely to be charging, e.g. **Low power** at
  night and **AI power** in the morning.

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

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-screen-device.png" alt="The charger's Screen device page in Home Assistant">

<img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/screenshot-clock-theme.png" alt="Choosing a clock theme">

Everything about the charger's screen is on its **Screen** device. Choose a **Clock theme**,
turn on **Clock screensaver**, and optionally set its start time, end time and days.
**Brightness**, **Timeout**, **Knob orientation** and **Clock format** (12/24-hour) are there
too.

The clock screensaver shows when the screen times out, so **Timeout** must not be **Always on**,
and the screen must not have been turned off using the knob.

Your own clock images appear as `Custom - <name>` in **Clock theme**. Add, rename and delete
them with the [clock image actions](#automations) (or in the Anker app: they show here after
**Refresh**). An image without a name shows as `Custom <number>`, like in the app. **Time display** controls the time overlay on custom images;
stock themes always show it. **Holiday screensaver** shows festive themes chosen by the charger.

**Hidden animations.** The charger plays them on its own when you do certain things with it;
there is no command to start one, also not in the app (which plays its own copy on your phone).
**Hidden animation** fires an event each time one plays (attribute `animation_type`), and
**Unlocked animations** counts those you have unlocked. How to trigger them, from the app's hints:

| Animation (app name) | How                                                                        |
| -------------------- | -------------------------------------------------------------------------- |
| Feature 1            | Switch the charger's main screen 20 times within 10 seconds (with the knob) |
| Feature 2            | Plug and unplug a device on the same USB-C port 10 times within 60 seconds |
| Dizziness            | Plug and unplug on the same USB-C port 5 times within 10 seconds           |
| Play bad             | Switch the main screen 15 times within 10 seconds                          |
| Device Expert        | Have a device connected to every port at the same time                     |
| Feature Expert       | Change the port priority 10 times                                          |
| Power Expert         | Connect 3 high-performance laptops at the same time                        |

The first four play each time; the last three are achievements, unlocked once (listed in the
app's *Secret Features*).

Home Assistant can trigger two of them, but both interrupt charging, so they are a curiosity
rather than something to automate:

- changing **Priority ports** 10 times plays `animation_type` 1 (Feature Expert), every time.
  Each change briefly restarts the ports (like a charging mode change);
- switching a USB-C port **off and on** 10 times within 60 seconds counts as unplugging it and
  plays `animation_type` 5 (Feature 2). 5 times within 10 seconds (Dizziness) isn't enough.
  It power-cycles the device on that port, and after playing the charger ignores it for 3 to 5
  minutes.

The others need you at the charger. **Unlocked animations** (and the app's *Secret Features*)
only list what the Anker app recorded: the app records an animation when it is connected to
the charger while it plays, so an animation played with the app closed isn't added.

## Dashboard cards

The integration comes with two cards that show the charger as the Anker app does. They are
loaded automatically: nothing to install or add under **Resources**.

| Card                                 | Shows                                                                                    |
| ------------------------------------ | ---------------------------------------------------------------------------------------- |
| **Anker Prime Charger 3D**           | The charger in 3D, with a cable in each port in use and the total output on its screen; drag it to turn it |
| **Anker Prime Charger outputs**      | _USB-C Output_ and _USB-A Output_: each port's power, voltage and current; tap a port for its power history |

To add one, edit a dashboard, choose **Add card**, and search for **Anker**. The visual editor
lets you choose the **Charger** (the first one is preselected), for the outputs card whether to
**Show voltage and current**, and for the 3D card whether to **Rotate by dragging** (on by
default; off, the charger stays as it is shown) and to **Show the clock screensaver**: its screen
then shows the charger's selected clock theme with the current time (as the charger shows it:
always on stock themes, on your images when **Time display** is on), instead of the total output.
It is drawn whether or not the charger shows its screensaver at that moment, which the charger
doesn't report. The three Standard Styles are drawn in their spirit, not copied.

To turn the 3D card, drag it (on a touch screen, sideways: scrolling up and down still scrolls the
page), or click it and use the arrow keys. Double-click (or **Home**) goes back to the default
view. Each card remembers its view for your Home Assistant user, so the charger is shown as you
left it the next time, also on your other devices. (A 3D card from an earlier version gets its own
view once opened and saved in the editor; until then it shares its charger's.) While the charger
is offline, the 3D card is greyed out.

In the outputs card, a port's label is coloured while a device is plugged in; ports without a
device show `--`.

**Anker Prime Charger 3D** (the screenshots are generated, see
[docs/DOCUMENTATION_SCREENSHOTS.md](docs/DOCUMENTATION_SCREENSHOTS.md)):
<!-- card-docs:3d:variations:start -->
<table>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-overview.png" alt="Anker Prime Charger 3D: Three devices charging" width="280"><br>Three devices charging</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-all-ports.png" alt="Anker Prime Charger 3D: Every port in use" width="280"><br>Every port in use</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-turned.png" alt="Anker Prime Charger 3D: Turned by dragging: the right side and the back" width="280"><br>Turned by dragging: the right side and the back</td>
  </tr>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-screensaver-flip.png" alt="Anker Prime Charger 3D: Clock screensaver: Standard Style 1" width="280"><br>Clock screensaver: Standard Style 1</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-screensaver-digits.png" alt="Anker Prime Charger 3D: Clock screensaver: Standard Style 2" width="280"><br>Clock screensaver: Standard Style 2</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-screensaver-ring.png" alt="Anker Prime Charger 3D: Clock screensaver: Standard Style 3" width="280"><br>Clock screensaver: Standard Style 3</td>
  </tr>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-screensaver-image.png" alt="Anker Prime Charger 3D: Clock screensaver: an image, with the time (12h)" width="280"><br>Clock screensaver: an image, with the time (12h)</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-dark.png" alt="Anker Prime Charger 3D: Dark theme" width="280"><br>Dark theme</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-offline.png" alt="Anker Prime Charger 3D: The charger offline" width="280"><br>The charger offline</td>
  </tr>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-narrow.png" alt="Anker Prime Charger 3D: A narrow column (a phone)" width="280"><br>A narrow column (a phone)</td>
  </tr>
</table>
<!-- card-docs:3d:variations:end -->
Its visual editor:
<!-- card-docs:3d:editors:start -->
<table>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/3d-editor-options.png" alt="Anker Prime Charger 3D: The card&#39;s options" width="280"><br>The card&#39;s options</td>
  </tr>
</table>
<!-- card-docs:3d:editors:end -->
**Anker Prime Charger outputs**:
<!-- card-docs:outputs:variations:start -->
<table>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/outputs-overview.png" alt="Anker Prime Charger outputs: Three devices charging" width="280"><br>Three devices charging</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/outputs-compact.png" alt="Anker Prime Charger outputs: Without voltage and current" width="280"><br>Without voltage and current</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/outputs-dark.png" alt="Anker Prime Charger outputs: Dark theme" width="280"><br>Dark theme</td>
  </tr>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/outputs-offline.png" alt="Anker Prime Charger outputs: The charger offline" width="280"><br>The charger offline</td>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/outputs-narrow.png" alt="Anker Prime Charger outputs: A narrow column (a phone)" width="280"><br>A narrow column (a phone)</td>
  </tr>
</table>
<!-- card-docs:outputs:variations:end -->
Its visual editor:
<!-- card-docs:outputs:editors:start -->
<table>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/images/cards/outputs-editor-options.png" alt="Anker Prime Charger outputs: The card&#39;s options" width="280"><br>The card&#39;s options</td>
  </tr>
</table>
<!-- card-docs:outputs:editors:end -->

<details>
<summary>YAML</summary>

```yaml
type: custom:anker-prime-charger-3d-card
device: 0123456789abcdef0123456789abcdef # optional: the charger's device id
drag_to_rotate: true # turn it by dragging; its view is remembered (default true)
show_screensaver: false # its screen shows the clock screensaver (default false)
view_id: k3x9q2 # set by the editor: the card's own saved view
```

```yaml
type: custom:anker-prime-charger-outputs-card
device: 0123456789abcdef0123456789abcdef # optional
show_details: true # voltage and current under the power (default true)
```

Without `device`, a card shows the first charger. The device id is in the address of the
charger's device page (`/config/devices/device/<id>`). To show both cards like the app, put them
in a **Vertical stack**.

</details>

If your dashboards' resources are managed in YAML, the cards are still loaded on every page. After
updating the integration, reload the page (the cards follow the new version on the next load).

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
| `anker_prime_charger.add_clock_image`       | The Screen            | Upload your own image as a clock theme           |
| `anker_prime_charger.rename_clock_image`    | The Screen            | Rename one of your clock images                  |
| `anker_prime_charger.delete_clock_image`    | The Screen            | Delete one of your clock images                  |
| `anker_prime_charger.list_clock_images`     | The Screen            | Your clock images, for scripts                   |

Actions target **devices**: the charger, or one of its port devices. In the action editor, pick
the device from the list; several ports can be targeted at once. An **area** or **label** works
too: the action applies to the devices in it that it suits (e.g. a profile action to the charger,
**Set protocols** to its USB-C ports). Set an area on the charger only: its port and Screen devices follow it as long as they have no area of their own (leave theirs empty). Labels are not inherited: label each device. Saving a profile does **not**
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

Add your own clock image. Pick it in **Image** from *Media > My media* (upload it there first), or
give a `path` Home Assistant may read (e.g. in `/config/www` or `/media`). It is cut to the
screen's 480 x 200: `fit: fill` crops it to fill the screen, `fit: fit` keeps the whole image
with black bars. `frame: shade` darkens the image and shades its edges, like the Anker app
does to its uploads; the default `frame: none` keeps your image as it is. The name is optional (at most 13 characters, not already used); without one it
shows as `Custom <number>`, like in the app. `show: true` puts it on the screen right away. The
action returns the new image's `id` and `name`:

```yaml
action: anker_prime_charger.add_clock_image
target:
  device_id: <the Screen device's id>
data:
  path: /config/www/clock/beach.jpg
  name: Beach
  frame: shade
  show: true
response_variable: added
```

Rename or delete an image by its name, its **Clock theme** option or its id. Deleting the image
on the screen first switches the charger to *Standard Style - Theme 1*:

```yaml
action: anker_prime_charger.rename_clock_image
target:
  device_id: <the Screen device's id>
data:
  image: Custom 1
  new_name: Beach
```

```yaml
action: anker_prime_charger.delete_clock_image
target:
  device_id: <the Screen device's id>
data:
  image: Beach
```

`list_clock_images` returns your images (`id`, `name`, `option`, `on_screen` and a
`preview_url` valid for a few minutes), e.g. for a script that picks one at random.

</details>

## Compatibility

Development and testing currently target the **Anker Prime Charger 250W, 6 ports (A2345)**.
Only this model is offered during setup; the features above describe this charger.

| Device                                                 | Status                                                             |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| Anker Prime Charger 250W (A2345)                       | Supported and tested                                               |
| Anker Prime Charging Station 240W 8-in-1 (A91B2)       | Not supported yet; a Wi-Fi model worth investigating with an owner |
| Anker Prime Charger 160W (A2687)                       | Not supported; Bluetooth only (tested: no Wi-Fi). See below        |
| Anker Prime Wireless Charging Station 3-in-1 (A25X7)   | Not supported; Bluetooth only                                      |
| Anker 150W Charging Base for Prime power banks (A1903) | Not supported; nothing known about it yet                          |

Bluetooth-only devices cannot use this cloud integration: they appear in your Anker account,
because the app registers them over Bluetooth, but they never connect to Anker's cloud. For
the **Prime Charger 160W**, use the Bluetooth integration
[HaSolixBLE](https://github.com/flip-dots/HaSolixBLE) (a HACS custom repository): it reads each
port's power, voltage and current and can switch the ports and set their timers. The charger
must be within Bluetooth range of Home Assistant (or of an ESPHome Bluetooth proxy), and the
Anker app and Home Assistant can't be connected to it at the same time.

Both chargers can run side by side: this integration for the 250W, HaSolixBLE for the 160W.

If you own an A91B2 and would like to help test it,
[open an issue](https://github.com/Max-src/ha-anker-prime-charger/issues). The integration's
diagnostics list the other devices on your Anker account (model and how they connect, without
names or serial numbers), which is the first thing needed to look at a new model.

Some features require newer charger firmware. Keep it updated through the Anker app and consult
[Anker's A2345 user guide](https://support.anker.com/s/article/Anker-Prime-Charger-250W-6-Ports-GaNPrime-User-Guide-A2345)
for hardware limits and charging-mode details.

## Known limitations

- **Cloud only.** The charger has no local connection, so Home Assistant and the charger both
  need internet access, and the Anker cloud must be up.
- **The account must own the charger.** A shared account can't connect to it. One charger per
  integration entry; add the integration again for another one.
- **Mode changes interrupt charging.** Changing the charging mode, custom settings or the port
  priority restarts all ports for 2-4 seconds; the app does the same.
- **The two USB-A ports switch together** (one switch on the charger), though their readings
  are separate.
- **Energy is estimated** from the power readings; the charger doesn't count energy itself.
- **Not available from the cloud:** renaming the charger (Home Assistant only), choosing a
  holiday theme, brightness below 20 % (no visible effect), and starting a hidden animation on
  demand (see *Screen and clock*).
- **Other models** aren't supported yet; Bluetooth-only ones can't be (see
  [Compatibility](#compatibility)).

## Troubleshooting

| Problem                                               | What to check                                                                                                          |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Integration does not appear                           | Restart Home Assistant after installation. For a manual install, check the folder layout above and refresh the browser |
| Charger is not found                                  | Confirm it is an A2345, online in the Anker app, and owned by the account you used to sign in                          |
| Repair: the charger is no longer in your Anker account | It was removed from the account or moved to another one. Add it back in the Anker app, or delete the integration's entry |
| Repair: the charger is offline                        | No status for an hour: check its power and 2.4 GHz Wi-Fi in the Anker app, and Home Assistant's internet access      |
| Entities are unavailable                              | Check charger power, Wi-Fi and internet access. Readings return when the charger answers again                         |
| App settings have not appeared                        | Use **Refresh**, or wait for the 10-minute cloud-settings refresh                                                      |
| App and Home Assistant power readings differ          | They can sample at different times; charging power changes with device demand                                          |
| Custom profiles are missing                           | Enable the **Custom charging mode** test feature and check for firmware updates                                        |
| Charging briefly stops after changing mode or custom settings | The charger restarts all ports to apply a new power split (also with the app). Use **Set custom settings** for a combined change |
| USB-A ports switch together                           | This is a charger limitation; their power and energy readings are still separate                                       |
| Clock screen is not shown                             | On the Screen device: check **Clock screensaver**, its schedule, and that **Timeout** is not _Always on_               |
| A port does not reach its maximum power               | Check the charging mode, cable and device capabilities. Only USB-C 1 supports 140 W; charging slows as batteries fill  |

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
