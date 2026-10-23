# Development

## Code layout

`custom_components/anker_prime_charger/`:

| Module                         | Responsibility                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `const.py`                     | Domain, supported model, option keys and defaults                                                                                                                                                                                                                                                                                                                                                                                              |
| `__init__.py`                  | Setup and unload of a charger, actions registration, retired entities cleanup                                                                                                                                                                                                                                                                                                                                                                  |
| `config_flow.py`               | Login (finds the account's country and server), options                                                                                                                                                                                                                                                                                                                                                                                        |
| `coordinator.py`               | MQTT connection, status polling, incoming messages (handed to the event loop; pushed without moving the poll schedule), commands, fast updates                                                                                                                                                                                                                                                                                                 |
| `fast_updates.py`              | Fast updates: resend the real-time trigger every 8 s until the duration runs out                                                                                                                                                                                                                                                                                                                                                               |
| `cloud.py`                     | Settings stored in the Anker cloud: background refresh, test features, port labels, profile requests                                                                                                                                                                                                                                                                                                                                           |
| `library.py`                   | **The only place that touches the vendored library's internals**: client creation, server override, raw cloud requests, the endpoint table                                                                                                                                                                                                                                                                                                     |
| `mqtt_extensions.py`           | What we add to or correct in the library's description of the charger's messages                                                                                                                                                                                                                                                                                                                                                               |
| `ports.py`                     | The five ports (USB-C 1-4, USB-A) and their child devices; how each port is named in MQTT, the custom mode and the cloud; maximum power, priority options. **The one place for port facts**: the other modules derive their tables from `PORTS`                                                                                                                                                                                                |
| `themes.py`                    | Clock themes: Standard Styles, theme list, current theme, theme command                                                                                                                                                                                                                                                                                                                                                                        |
| `screen.py`                    | The screen's page (power, clock or off), estimated: what wakes it (commands except the theme command, plugging in or out), Timeout, the clock's hours                                                                                                                                                                                                                                                                                          |
| `clock_images.py`              | Custom clock images: prepare (480x200 JPEG, optional frame), upload, add, rename, delete, list; names checked like the app (13 characters, unique). New frames: a function in `FRAMES`, plus its option in `services.yaml` and the `clock_image_frame` translations                                                                                                                                                                            |
| `custom_mode.py`               | Custom charging mode settings: limits, protocols, checks, the `0206` command                                                                                                                                                                                                                                                                                                                                                                   |
| `profiles.py`                  | Custom profiles in the cloud: save, create, delete                                                                                                                                                                                                                                                                                                                                                                                             |
| `schedules.py`                 | Port timers and schedules, clock screensaver schedule, days presets; schedules are addressed as `(port, part)`, port `None` = clock screensaver                                                                                                                                                                                                                                                                                                |
| `services.py`                  | The actions (profiles, Set custom settings, Set days, Set protocols); they target devices: the charger or a port                                                                                                                                                                                                                                                                                                                               |
| `helpers.py`                   | Value conversions (`to_number`, `to_int`, `is_on`, weekdays), `on_off`, `summed_power`, `translated` (errors with their message in `en.json` "exceptions")                                                                                                                                                                                                                                                                                     |
| `entity.py`                    | Base entity: on the charger's device, a port's child device or the Screen child device (`screen=True`), unique id `<serial>_<unique_key or key>`; available once the key is reported (`_needs_key = False` for entities not bound to one value)                                                                                                                                                                                                |
| `presets.py`                   | Preset selects (days, protocols): common values for a list a text entity edits                                                                                                                                                                                                                                                                                                                                                                 |
| `issues.py`                    | Repair issues: charger no longer in the account, charger offline for an hour (silence counted across setup retries)                                                                                                                                                                                                                                                                                                                            |
| `binary_sensor.py` … `time.py` | One file per Home Assistant platform, each with `PARALLEL_UPDATES` (0 read-only, 1 sending commands)                                                                                                                                                                                                                                                                                                                                           |
| `icons.json`                   | Entity and action icons, by translation key (the port switches use `usb_c_port` / `usb_a_port`, for the icon only)                                                                                                                                                                                                                                                                                                                             |
| `frontend.py`                  | Dashboard cards: serves `www/` (revalidated on every load), registers `cards.js` as a dashboard resource, websocket commands `anker_prime_charger/charger` (a charger's ports and screen, their entity ids) and `anker_prime_charger/screensaver` (the selected clock theme, its picture's key), and its picture at `/api/anker_prime_charger/screensaver_image/<device id>` (login needed; kept in memory, asked from Anker once per picture) |
| `www/`                         | The cards (Lit, plain ES modules, no build step); see _Dashboard cards_ below                                                                                                                                                                                                                                                                                                                                                                  |
| `solixapi/`                    | The vendored library, unchanged                                                                                                                                                                                                                                                                                                                                                                                                                |

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
- **Schedules** are addressed as `(port key, part)`, port `None` for the clock screensaver.
- **Devices**: the charger, a child device per port (`<serial>_<port key>`), and the **Screen**
  child device (`<serial>_screen`) for the display, clock screensaver, knob and hidden-animation
  entities (`screen=True` on the entity). Actions resolve all three (`services.Target`).
- **Entity id renames** (Home Assistant 2026.11+) update an entity in place instead of removing and
  adding it again, so `async_added_to_hass` / `async_will_remove_from_hass` don't run on a rename.
  Until 2027.11 an entity keeps the old behaviour unless every one of our classes that defines
  `async_prepare_to_add_to_hass`, `async_added_to_hass` or `async_will_remove_from_hass` also
  defines `async_entity_id_changed` (a `@callback` calling `super()`; a base class's hook doesn't
  count). Add it to any new such class; `tests/test_entity_id_changes.py` fails otherwise. Never
  key anything on an entity's own `entity_id`: use its unique id, or update the key in the hook.

## Tests

The tests use the real vendored library (command validation, encoding and decoding); only the
network is faked (`tests/conftest.py`: `FakeCloud`, `FakeMqttSession`). They need Linux (Home
Assistant doesn't run on Windows), e.g. WSL:

```bash
pip install pytest-homeassistant-custom-component
pytest
```

From Windows, in a WSL environment with the test requirements (here `/root/ha-test-venv`):

```powershell
$repo = (wsl -d Ubuntu -u root -- wslpath -a ($PWD.Path -replace '\\', '/')).Trim()
wsl -d Ubuntu -u root -- bash -c "cd '$repo' && /root/ha-test-venv/bin/python -m pytest tests -q"
```

`tests/test_library_contract.py` lists what the integration relies on in the library; run it first
after updating the library.

CI (`.github/workflows/tests.yml`) runs the tests against three Home Assistant versions, each
pinned by a `pytest-homeassistant-custom-component` release: **minimum** (the version in
`hacs.json`) and **stable** (the latest release) must pass; **latest** (often a beta) is an early
warning that may fail without blocking. It also runs weekly. When a new Home Assistant release is
out, bump the _stable_ pin, and the _minimum_ one together with `hacs.json`.

## Dashboard cards

The cards live in `www/`, served at `/anker_prime_charger/` and loaded by the dashboards as one
module, `cards.js` (a dashboard resource the integration adds, or `add_extra_js_url` when
resources are in YAML). They are plain ES modules: no build step, edit and reload the page.

| File                      | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cards.js`                | The module the dashboards load: imports each card                                                                                                                                                                                                                                                                                                                                                                                             |
| `card-base.js`            | `ChargerCard`, the shared base: config (`device`), loading the charger, rendering only when a shown state changed, editor, sizes                                                                                                                                                                                                                                                                                                              |
| `card-editor.js`          | The visual editor: Home Assistant's `ha-form`, the charger picker then each card's `editorSchema`; saves the card's `completeConfig`                                                                                                                                                                                                                                                                                                          |
| `charger.js`              | Asks the integration for the charger's ports (websocket, cached per entity registry), reads and formats a port; `chargerSummary` (offline, ports in use, screen text) for the 3D card                                                                                                                                                                                                                                                         |
| `charger-3d-card.js`      | The 3D card: what its screen shows (`screen`: auto, from the Page sensor, power, clock or off), each port's power above it (`show_port_power`), the cables (`show_cables`), turning and zooming it (drag, arrow keys, Ctrl + wheel, pinch, + and -; `drag_to_rotate`), each card's view remembered in the user's frontend data (`frontend/set_user_data`, key `anker_prime_charger_3d_views`, by the card's `view_id`, which the editor adds) |
| `charger-screensaver.js`  | The clock screensaver on the 3D card's screen (480 x 200): our Standard Styles, a theme's picture with the time; the date as the charger writes it                                                                                                                                                                                                                                                                                            |
| `screensaver-store.js`    | The 3D card's clock screensavers, kept in the browser (IndexedDB) by charger and theme, so they show at once on the next load; the picture fetched again only when its key changes                                                                                                                                                                                                                                                            |
| `charger-model.js`        | The 3D model in millimetres, drawn as SVG from any angle (see below); its styles (`modelStyles`)                                                                                                                                                                                                                                                                                                                                              |
| `charger-outputs-card.js` | The USB-C / USB-A output panels                                                                                                                                                                                                                                                                                                                                                                                                               |
| `registration.js`         | `defineOnce`, `registerCustomCard`: safe when the module is loaded twice                                                                                                                                                                                                                                                                                                                                                                      |
| `styles.js`               | Styles every card shares: `--anker-port-active-color` (a port in use), the offline look                                                                                                                                                                                                                                                                                                                                                       |
| `lib/lit-all.js`          | Lit 2.8.0 as one ES module (built with esbuild from `lit`; the cards can't import it by package name)                                                                                                                                                                                                                                                                                                                                         |

Cards find their entities through the integration (by unique id), never by entity id, so renamed
entities and devices keep working. A port is "in use" when its **Connected** binary sensor is on.

The 3D model is ours: no Anker artwork, logo or trademark (Anker's terms don't allow
republishing the app's images). Its geometry is at the top of `charger-model.js`.

The 3D model needs no 3D library: it is seen with a gentle perspective (`CAMERA_DISTANCE`).
Outlines are projected point by point; a small detail on a surface (screen text, a port, the
knob) is drawn in the surface's 2D coordinates with the perspective's transform at its place. Surfaces facing away are skipped, the rest drawn back to front and
shaded by how much they face the light. Cables are drawn after the body when their port's side is
seen, before it otherwise (the body's faces are too large to sort them by depth alone).

The README's screenshots of the cards are generated in a real Home Assistant frontend (CI does
it on main), and those of Home Assistant's pages for the charger from your own Home Assistant
(`npm run docs:pages`): see [DOCUMENTATION_SCREENSHOTS.md](DOCUMENTATION_SCREENSHOTS.md). A new
card or option gets its scenarios in `tests/card-docs-catalogue.json`; after adding or renaming
entities, run `npm run docs:pages` again.

To add a card: a `ChargerCard` subclass with `_watched()` (the states it shows),
`_renderCharger()`, optionally `editorSchema`; import it in `cards.js`; add its files to
`test_every_card_file_exists` in `tests/test_frontend.py`.

## Lint and format

```bash
ruff check custom_components tests tools
ruff format custom_components tests tools
```

The configuration is in `pyproject.toml` (close to Home Assistant's); the vendored library is
excluded.

Types are checked with strict mypy (the vendored library excluded):

```bash
mypy --strict --follow-imports=silent --ignore-missing-imports --exclude solixapi custom_components/anker_prime_charger
```

## Updating the vendored library

1. Replace `solixapi/` with the new upstream version and update `solixapi/VERSION.txt`.
2. Run `tests/test_library_contract.py`, then the whole suite.
3. If upstream now covers something `mqtt_extensions.py` adds or corrects, remove it there.

## How the protocol was found

By watching the MQTT messages of the owner's account while using the Anker app (what the app
sends, what the charger reports, which bytes change), and by probing the cloud's REST endpoints
(an incomplete request names its missing field). [PROTOCOL.md](PROTOCOL.md) records the results;
everything the integration relies on was checked against a real charger.

## Adding a model

Only the Prime Charger 250W (A2345) is supported so far; the README lists the other Prime
chargers and which ones could follow (only Wi-Fi models: the integration goes through the Anker
cloud). The integration's name and domain (`anker_prime_charger`) are model-neutral on purpose;
keep them that way.

First check that the model reaches Anker's cloud at all: the diagnostics'
`other_account_devices` must show `wifi_online: true` for it (see
[PROTOCOL.md](PROTOCOL.md#other-models-on-the-account)). Bluetooth-only models, like the
Prime Charger 160W (A2687), can't be supported by this integration.

What is specific to the A2345 today, and would become per-model:

| Where                | What                                                                                                           |
| -------------------- | -------------------------------------------------------------------------------------------------------------- |
| `const.py`           | `MODEL` / `MODEL_NAME`: the model the config flow offers, the device's model, the model sent in cloud requests |
| `mqtt_extensions.py` | Additions and corrections to the library's A2345 message map                                                   |
| `ports.py`           | The ports, their names and maximum power (a model with AC outlets needs outlet entries)                        |
| `custom_mode.py`     | Total power limit (`TOTAL_MAX`), USB-A options                                                                 |
| `themes.py`          | The Standard Styles' image paths                                                                               |
| Platforms            | Which entities exist: a model only gets the features it has                                                    |
| `tests/conftest.py`  | The test charger                                                                                               |

A new model needs someone who owns it: watch its MQTT messages while using each feature in the
app, compare with [PROTOCOL.md](PROTOCOL.md), and only expose what is verified.

## Deploy to Home Assistant (local)

`deploy.bat` (double-click) or `.\deploy.ps1 [-HaHost <ip>]` mirrors the integration to
`\\<ha>\config\custom_components\anker_prime_charger` over SMB (Samba share add-on), keeping the
library's login cache there. Restart Home Assistant afterwards. Both files are git-ignored.

## Releasing

See [RELEASING.md](RELEASING.md): bump the version, update `CHANGELOG.md`, tag, publish the
release; a workflow then attaches `anker_prime_charger.zip`, which HACS installs from.
