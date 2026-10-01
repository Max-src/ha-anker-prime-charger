# Development

## Code layout

`custom_components/anker_prime_charger/`:

| Module | Responsibility |
|---|---|
| `const.py` | Domain, supported model, option keys and defaults |
| `__init__.py` | Setup and unload of a charger, actions registration, retired entities cleanup |
| `config_flow.py` | Login (finds the account's country and server), options |
| `coordinator.py` | MQTT connection, status polling, incoming messages (handed to the event loop; pushed without moving the poll schedule), commands, fast updates |
| `cloud.py` | Settings stored in the Anker cloud: background refresh, test features, port labels, profile requests |
| `library.py` | **The only place that touches the vendored library's internals**: client creation, server override, raw cloud requests, the endpoint table |
| `mqtt_extensions.py` | What we add to or correct in the library's description of the charger's messages |
| `ports.py` | The five ports (USB-C 1-4, USB-A) and their child devices; how each port is named in MQTT, the custom mode and the cloud; maximum power, priority options. **The one place for port facts**: the other modules derive their tables from `PORTS` |
| `themes.py` | Clock themes: Standard Styles, theme list, current theme, theme command |
| `custom_mode.py` | Custom charging mode settings: limits, protocols, checks, the `0206` command |
| `profiles.py` | Custom profiles in the cloud: save, create, delete |
| `schedules.py` | Port timers and schedules, clock display schedule, days presets; schedules are addressed as `(port, part)`, port `None` = clock display |
| `services.py` | The profile actions, Set custom settings, Set days and Set protocols |
| `helpers.py` | Value conversions (`to_number`, `to_int`, `is_on`, weekdays), `on_off`, `summed_power`, `translated` (errors with their message in `en.json` "exceptions") |
| `entity.py` | Base entity: on the charger's device or a port's child device, unique id `<serial>_<unique_key or key>`; available once the key is reported (`_needs_key = False` for entities not bound to one value) |
| `binary_sensor.py` … `time.py` | One file per Home Assistant platform |
| `solixapi/` | The vendored library, unchanged |

Entities read the charger's values from `coordinator.data` (the decoded MQTT values) and cloud
settings from `coordinator.cloud`. Changes go through `coordinator.async_send_command` (MQTT) or
`coordinator.cloud` (REST), never through the library directly.

### Conventions

- **Port facts** (names, maximum power, profile names, priority bits) only in `ports.PORTS`; other
  modules derive their tables from it.
- **Unique ids never change**: they keep users' entities, history and Energy dashboard. A new
  entity class reproduces the old id with `unique_key`. An entity that goes away is listed in
  `RETIRED_ENTITIES` (`__init__.py`) so it is removed from the registry.
- **Errors shown to users** are raised with `helpers.translated(<error class>, "<key>", …)`; the
  message is in `translations/en.json` under `exceptions.<key>.message`, with `{placeholders}`.
- **Translations**: `[%key:…%]` references are only resolved for Home Assistant's own
  integrations, so repeated strings are written out in `en.json`.
- **Availability**: an entity is available once its key is reported; entities not bound to one
  value set `_needs_key = False` and add their own conditions to `available`.
- **Coordinator updates**: values pushed by the charger go through `_async_push` (keeps the poll
  schedule); `async_set_updated_data` would restart the poll interval.
- **Schedules** are addressed as `(port key, part)`, port `None` for the clock display.

## Tests

The tests use the real vendored library (command validation, encoding and decoding); only the
network is faked (`tests/conftest.py`: `FakeCloud`, `FakeMqttSession`). They need Linux (Home
Assistant doesn't run on Windows), e.g. WSL:

```bash
pip install pytest-homeassistant-custom-component
pytest
```

From Windows, in the WSL test environment the `tools/*.ps1` launchers use (`/root/ha-test-venv`):

```powershell
$repo = (wsl -d Ubuntu -u root -- wslpath -a ($PWD.Path -replace '\\', '/')).Trim()
wsl -d Ubuntu -u root -- bash -c "cd '$repo' && /root/ha-test-venv/bin/python -m pytest tests -q"
```

`tests/test_library_contract.py` lists what the integration relies on in the library; run it first
after updating the library.

## Lint and format

```bash
ruff check custom_components tests tools
ruff format custom_components tests tools
```

The configuration is in `pyproject.toml` (close to Home Assistant's); the vendored library is
excluded.

## Updating the vendored library

1. Replace `solixapi/` with the new upstream version and update `solixapi/VERSION.txt`.
2. Run `tests/test_library_contract.py`, then the whole suite.
3. If upstream now covers something `mqtt_extensions.py` adds or corrects, remove it there.

## Investigation scripts (`tools/`)

Each script runs in the WSL test environment through its `.ps1` launcher. It asks for the Anker
login in the terminal (kept in memory only), asks before every change and undoes it, deletes the
library's login cache when done, and writes its results (serial, user id hash and signed links
masked; git-ignored) next to it.

| Script | Purpose |
|---|---|
| `watch_charger` | Read-only. Snapshots while you use the app: the app's commands to the charger, what the charger reports, which bytes changed. The way to decode new settings |
| `validate` | Whether cloud-side settings (protocols per mode, test features) actually reach the charger |
| `probe_cloud` | Found the test features' request format |
| `probe_themes` | Clock image format and the custom image endpoints |
| `probe_profiles` | Profile update format |

`tools/common.py` holds what they share (login, requests, field discovery, masking).

## Adding a model

Only the Prime Charger 250W (A2345) is supported so far; the README lists the other Prime
chargers and which ones could follow (only Wi-Fi models: the integration goes through the Anker
cloud). The integration's name and domain (`anker_prime_charger`) are model-neutral on purpose;
keep them that way.

What is specific to the A2345 today, and would become per-model:

| Where | What |
|---|---|
| `const.py` | `MODEL` / `MODEL_NAME`: the model the config flow offers, the device's model, the model sent in cloud requests |
| `mqtt_extensions.py` | Additions and corrections to the library's A2345 message map |
| `ports.py` | The ports, their names and maximum power (a model with AC outlets needs outlet entries) |
| `custom_mode.py` | Total power limit (`TOTAL_MAX`), USB-A options |
| `themes.py` | The Standard Styles' image paths |
| Platforms | Which entities exist: a model only gets the features it has |
| `tests/conftest.py`, `tools/common.py` | The test charger and the model the scripts look for |

A new model needs someone who owns it: run `tools/watch_charger` while using each feature in the
app, compare with [PROTOCOL.md](PROTOCOL.md), and only expose what is verified.

## Deploy to Home Assistant (local)

`deploy.bat` (double-click) or `.\deploy.ps1 [-HaHost <ip>]` mirrors the integration to
`\\<ha>\config\custom_components\anker_prime_charger` over SMB (Samba share add-on), keeping the
library's login cache there. Restart Home Assistant afterwards. Both files are git-ignored.

## Publishing

Before the first release on GitHub, fill in the repository links:
`manifest.json` (`documentation`, `issue_tracker`, `codeowners`).
