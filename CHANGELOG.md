# Changelog

Notable changes to the Anker Prime Charger integration. Earlier versions are described in the
[GitHub releases](https://github.com/Max-src/ha-anker-prime-charger/releases).

## [Unreleased]

### Added

- Dashboard cards, loaded automatically and set up with the visual editor:
  - **Anker Prime Charger 3D**: the charger in 3D, with a cable in each port in use and the total
    output on its screen. Turn it by dragging (or with the arrow keys); each card remembers its
    view for your user. Optionally, its screen shows the charger's clock screensaver (the selected
    theme, with the time).
  - **Anker Prime Charger outputs**: each port's power, voltage and current, as in the Anker app.
- Clock image actions: **Add clock image** (from *My media* or a file, cropped to the screen,
  optionally with the app's dark edges), **Rename clock image**, **Delete clock image** and
  **List clock images**.
- Repairs: when the charger is no longer in the Anker account, and when it has been offline for
  an hour. Both clear on their own.
- Icons for the entities and actions; the charger's device lists its Wi-Fi and Bluetooth
  addresses.

### Changed

- Choosing the charging mode that is already active no longer sends it again (every mode change
  restarts the ports for a few seconds).
- An unnamed custom image shows as `Custom <number>`, as in the Anker app.

### Documentation

- README: removing the integration, how data is updated, known limitations, the dashboard cards
  (with generated screenshots), and what triggers the hidden animations.

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
