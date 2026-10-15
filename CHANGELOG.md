# Changelog

Notable changes to the Anker Prime Charger integration. Earlier versions are described in the
[GitHub releases](https://github.com/Max-src/ha-anker-prime-charger/releases).

## [Unreleased]

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
