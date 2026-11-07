# Changelog

Notable changes to the Anker Prime Charger integration. Earlier versions are described in the
[GitHub releases](https://github.com/Max-src/ha-anker-prime-charger/releases).

## [Unreleased]

## [0.19.0] - 2026-11-07

### Added

- **Firmware** update entity on the charger: the installed firmware (as the charger reports
  it), a newer one when the Anker cloud offers it (checked daily; install it in the Anker app),
  and the progress while the charger installs it. The charger's firmware on its device page now
  follows the charger.
- Dashboard cards in French (and in English otherwise), following your Home Assistant language.
- **Wake screen** button on the Screen device: wakes the charger's screen on its power page, as a
  press on the knob does (it resends the screen's Timeout as it is).
- 3D card: tap the **knob** to wake the charger's screen (option **Pressing the knob**, on by
  default), and optional **arrows** beside the screen that dim and brighten it (option **Arrows
  beside the screen**: Brightness). The card's screen dims with the brightness.

### Changed

- **Fewer entities enabled by default** (new installations only; existing entities keep their
  setting): each port's Voltage and Current, the port schedules (Schedule start / end and their
  times), port Labels, Custom protocols (+ preset) and the three test features. Enable them on
  the device page when you need them.
- **Port schedule days:** the days text and days preset entities of each port schedule are
  removed (20 entities). The days are now the `weekdays` attribute of **Schedule start** /
  **Schedule end**; change them with the **Set days** action. The clock screensaver keeps its
  days entities.
- **Charging mode:** custom profiles are listed by their name (`Desk`) instead of
  `Custom: Desk`, which couldn't be translated. Update automations that select a profile.
- **Fast updates** also send the real-time trigger the Anker app sends, which asks for 5 minutes
  of readings. If the charger honours it (checked once, at the first fast updates), the trigger
  is sent every 4.5 minutes instead of every 8 seconds; otherwise nothing changes.
- **Energy** is added up with the mean of the power at two readings (trapezoidal rule), so a
  device plugged in or out between two readings counts for half the interval.
- The login cache and the MQTT certificates are kept in Home Assistant's `.storage` folder
  instead of the integration's folder: they survive updates of the integration (no new login
  after each one), and file names no longer contain the account's email. The old files are
  deleted.
- 3D card: the parts keep their place in the page while it turns (keyboard focus stays on the
  port), a saved front view (0°) is restored as such, and the clock picture is fetched only when
  needed.
- Lit 3 for the cards.
- The outputs card is greyed out while the charger is offline, as the 3D card is.
- Cards: screen readers get labels for the tap areas and buttons, and an on/off button whose
  state is unknown says so (mixed) instead of off.
- The clock image list loads the images' previews at the same time instead of one by one.
- Documentation: PROTOCOL.md describes the 5-minute real-time trigger (`0057`) and the firmware
  versions request (`0030` → `0830`), and why there is no Matter, HomeKit or local network
  access; the README's Known limitations say so too.

### Fixed

- A dropped MQTT connection no longer blocks Home Assistant while it reconnects: paho's own
  reconnection is left to work for 90 seconds (the values stay meanwhile), then the session is
  replaced off the event loop.
- Deleting the clock image on screen: if the cloud refuses, the screen now stays as it was
  (it switched to Standard Style 1 first). Adding an image with a name: if naming it fails, the
  error says under which name it was added.
- The 3D card's screen stayed dark when the clock picture could not be downloaded; it now shows
  the plain clock.
- The picture download of the cards is limited in size, and not repeated when two cards ask at
  once.
- Reloading or removing the integration left the MQTT client's network thread running, and
  cleared the charger's last values.
- A command from Home Assistant that changed no value (the same brightness, say) didn't show as
  a screen wake on **Page**.
- Removing the integration now also removes the cards' module when dashboards are in YAML mode.
- 3D card: a touch interrupted (by a notification, say) could make the next touch count as a
  pinch.

## [0.18.0] - 2026-10-31

### Added

- Dashboard cards, loaded automatically and set up with the visual editor:
  - **Anker Prime Charger 3D**: the charger in 3D, with a cable in each port in use and the total
    output on its screen. Turn it by dragging (or with the arrow keys) and zoom (Ctrl + wheel,
    pinch, + and -); each card remembers its view for your user. Its screen shows what the charger shows (Auto, from the **Page** sensor),
    or always the power page (the total output), the charger's clock screensaver (the selected
    theme, with the time) or nothing. Each port's power can be written above it, whatever the
    screen shows, and the cables can be hidden.
    Tapping a port (around it, its power or its cable) opens its power history, as on the
    outputs card (**Tap a port for its history**, on by default; the port under the mouse is
    highlighted); a drag still turns it. **Show zoom and turn buttons** (off by default) adds
    buttons in its corner to zoom and turn it. Zooming with the wheel
    or + and - goes in smaller steps (about 10 %).
  - **Anker Prime Charger outputs**: each port's power, voltage and current, as in the Anker app.
    Tapping a port opens its power history (**Tap a port for its history**, on by default; the
    port under the mouse is highlighted, as on the 3D card). **Show on/off buttons** (off by default) adds a small button next to each port's label; A1's
    and A2's both turn the two USB-A ports on or off, as the charger switches them together.
- Clock image actions: **Add clock image** (from *My media* or a file, cropped to the screen,
  optionally with the app's dark edges), **Rename clock image**, **Delete clock image** and
  **List clock images**.
- **Page** sensor on the Screen device: what the screen shows (power page, clock or off),
  estimated from what wakes it (plugging in or out, commands from Home Assistant), the Timeout and
  the clock screensaver's hours. The charger doesn't report it.
- Repairs: when the charger is no longer in the Anker account, and when it has been offline for
  an hour. Both clear on their own.
- Icons for the entities and actions; the charger's device lists its Wi-Fi and Bluetooth
  addresses.
- **Connected device** sensor on each USB-C port: the brand of the plugged-in device as the
  charger identifies it (Apple, Samsung, Anker, ...; else its USB vendor id), with its USB
  vendor and product ids as attributes. The outputs card shows it under the port.
- **Fault** on each port and **Overheating** on the charger: problem sensors from the faults the
  charger reports.
- **Firmware update** and **Firmware update progress** on the charger: on while the charger
  installs an update, and how far it is.

### Fixed

- **Maximum compatibility** and **Charging device identification** now change the charger
  itself, as the app does (they only changed the setting stored in the Anker cloud, which the
  charger ignores), and show the charger's own state. Turning off **Custom charging mode** also
  tells the charger, as the app does.
- Choosing a custom image as the clock theme sends a fresh link to it: the link read with the
  image list expires after 5 minutes, and the charger then couldn't download the image.
- The clock theme no longer shows as unknown for about 30 seconds every 5 minutes (and most of
  the time while the screen's values are updated quickly): the updated library couldn't read the
  theme id in some of the charger's messages.

### Changed

- A USB-C port's readings are named after the port, as the USB-A ones already were: **C1 power**,
  **C1 voltage**, **C1 current**, **C1 energy**, **C1 connected** and **C1 label** (they were
  **Power**, **Voltage**, ...), so the port shows in their dialogs too. Entity ids don't change.
- Choosing the charging mode that is already active no longer sends it again (every mode change
  restarts the ports for a few seconds).
- An unnamed custom image shows as `Custom <number>`, as in the Anker app.
- Updated the bundled Anker library (anker-solix-api, 2026-10-30). It now knows the time display,
  the clock theme kinds and the test features of the A2345, so the integration uses its
  definitions instead of its own; nothing changes for the entities.

### Documentation

- README: removing the integration, how data is updated, known limitations, the dashboard cards
  (with generated screenshots), and what triggers the hidden animations.
- The screenshots of Home Assistant's pages (the integration, the charger, a port, the Screen,
  the lists and the Set custom settings action) are generated too, from a real charger with its
  serial number and addresses replaced, and show the current entities.
- The README describes manual installation only, from `anker_prime_charger.zip` or the
  repository; the HACS installation, update and removal steps were removed.

## [0.17.0] - 2026-10-15

### Added

- Diagnostics list the other devices on your Anker account (model, firmware and how they
  connect, without serial numbers or names), to help add support for more models.

### Changed

- Releases now ship `anker_prime_charger.zip`, and HACS installs the integration from it
  (`hacs.json` `zip_release`). This lets HACS show how many times the integration was
  downloaded. Counting starts with the first release that has the zip; HACS shows the count of
  the current release only. Older releases (0.16.0) still install from the repository files.
- Entities opt in to Home Assistant 2026.11's in-place entity ID changes: renaming an entity ID
  no longer removes and re-adds it, and an energy sensor keeps counting through a rename.

### Documentation

- The Prime Charger 160W (A2687) is Bluetooth only and can't be supported; the README points to
  the HaSolixBLE integration for it.
- Manual installation can use `anker_prime_charger.zip` from the latest release.
