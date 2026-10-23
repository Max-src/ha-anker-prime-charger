# Documentation screenshots

The README's screenshots are generated, so they show the integration as it is:

- **the dashboard cards** (`images/cards/`), with a synthetic charger, in CI: most of this page;
- **Home Assistant's pages for the charger** (`images/pages/`): the integration, the charger's,
  a port's and the Screen's device pages, the clock theme and charging mode lists, and the Set
  custom settings action, from a real charger, on your computer (see
  [Home Assistant's pages](#home-assistants-pages)).

Only the Energy dashboard's (`images/screenshot-energy-dashboard.png`) is taken by hand: it shows
whatever else that Home Assistant's Energy settings hold. The prose, tables and YAML are written
by hand too. `npm test` also checks that every file the documentation links to exists.

For the cards, automation only replaces the galleries between a card's markers,

```
<!-- card-docs:3d:variations:start --> ... <!-- card-docs:3d:variations:end -->
```

and fails on missing, duplicate or reversed markers.

## The scenarios

[tests/card-docs-catalogue.json](../tests/card-docs-catalogue.json) lists every image: per card
(`3d`, `outputs`), its **variations** (a scenario each) and **editors** (the visual editor). A
scenario has a `title` (the caption) and may set `ports` (the readings `[W, V, A]` of each port
with a device; the default is C1, C2 and A2 in use), `offline`, `dark` (Home Assistant's dark
theme), `width` (the column, default 420 px), `config` (the card's options, e.g. `{"screen": "clock"}`) and, for the 3D card,
`view` (`{yaw, pitch}`, as if turned by dragging) and `screensaver` (the selected theme: `kind`
`style_1` to `style_3`, `stock` or `custom`, with our own picture; `time_display`;
`clock_format` `12h` or `24h`). The clock always shows Wednesday 14 January 2026, 08:40. Add a scenario there: its image and caption
follow. The image is `images/cards/<card>-<name>.png` (`<card>-editor-<name>.png` for an editor).

A new scenario has no image until the Documentation Screenshots workflow captures it; until
then `npm run docs:check` lists it as pending instead of failing.

## How they are captured

[tests/card-docs.cjs](../tests/card-docs.cjs) opens a real, logged-in Home Assistant dashboard
with Playwright, so the cards get Home Assistant's fonts, theme and elements (`ha-card`,
`ha-form`). The cards' files are served from the checkout, and
[tests/card-docs-browser.js](../tests/card-docs-browser.js) gives each card a synthetic charger
(the integration's answer and its entities' states), so that Home Assistant needs neither the
integration nor a charger. Nothing is saved there: the theme is changed in memory only.

Each image is captured in fresh browser contexts until two captures match: normally twice, a
third time when the first two differ, so a single odd capture is outvoted. "Match" allows the
small anti-aliasing noise of Chromium's software rendering
([tests/card-docs-compare.cjs](../tests/card-docs-compare.cjs)); a missing font, an element
caught mid-change or a layout shift still differ. A verified image is written only when it
differs from the committed one, so a run never commits noise.

One image never fails a run: an image that can't be verified keeps its committed version and is
listed in the run's summary with the reason; its captures and a diff image (magenta: real
differences, yellow: noise) are in `test-results/card-docs/`, which CI uploads as the
`card-documentation-diagnostics` artifact. The run fails only when nothing could be captured.

## Running it yourself

Node 22, then `npm ci` and `npx playwright install chromium` (on Linux
`npx playwright install --with-deps chromium`).

Against your own Home Assistant, with a long-lived access token (your profile, *Security*). The
token is only used in memory; the cards' files come from the checkout, not from that Home
Assistant, which isn't changed. In PowerShell:

```powershell
$env:DOCS_HA_URL = 'http://homeassistant.local:8123'
$env:DOCS_HA_TOKEN = Get-Content C:\Users\me\.ha_token
npm run docs:update
```

Against a fresh disposable Home Assistant on localhost (Docker), let the runner onboard it:
`DOCS_HA_ONBOARD=1 npm run docs:update`. Onboarding only works on a Home Assistant that was
never set up, and is refused for anything but localhost.

- `npm run docs:screenshots` captures the images (`DOCS_FILTER=3d-dark` for the matching ones).
- `npm run docs:readme` rebuilds the README galleries from the images; `npm run docs:check`
  fails when they are stale.
- `npm run docs:update` does both. `npm test` tests the gallery generator.

Images captured on another Home Assistant version or platform can differ slightly (fonts,
form elements) from CI's: CI's are the ones committed.

## In CI

[Documentation Screenshots](../.github/workflows/documentation-screenshots.yaml) runs on pull
requests and pushes to main that touch the cards, their tooling or the README, monthly, and on
request. It boots a pinned Home Assistant container (the "stable" version of the tests), onboards
it, captures, and checks the galleries. Pull requests only get the images as artifacts. On main,
a second job commits the changed images and galleries (`[docs-generated]` in the message, which
keeps it from running again on its own commit), unless main moved on meanwhile. It never changes
anything else. Branch protection must allow that push, or the job fails visibly and the images
stay available as artifacts.

When a scenario is removed from the catalogue, delete its image in the same change: unrelated
images are never deleted automatically.

## Home Assistant's pages

These need the real integration and a charger (Anker's cloud), which CI doesn't have, so they
are captured from your own Home Assistant: run it after adding, renaming or removing entities,
or when Home Assistant's pages change. In PowerShell:

```powershell
$env:DOCS_HA_URL = 'http://homeassistant.local:8123'
$env:DOCS_HA_TOKEN = Get-Content C:\Users\me\.ha_token
npm run docs:pages
```

[tests/ha-docs.cjs](../tests/ha-docs.cjs) lists the images and what each shows; `DOCS_FILTER`
keeps the matching ones. Each is captured in a fresh browser in Home Assistant's default light
theme, whatever your profile's, and written to `images/pages/`. Nothing is changed in Home
Assistant: pages are opened, a list opened by clicking, and the actions page filled through that
browser's storage only.

What identifies your charger is replaced on the page before each capture: its serial number,
Wi-Fi and Bluetooth addresses, and the device and config entry ids (as `ASHV911G00000001`,
`AA:BB:CC:DD:EE:01`, `AA:BB:CC:DD:EE:02` and `0123456789abcdef0123456789abcdef`). An image still
showing one of them is not written. Everything else is your charger as it is: its readings,
settings, profile names, port labels and the area of its devices, so look at the images before
committing them.

When Home Assistant's pages change, a selector may no longer match: that image is reported as
not captured (the run fails) and its committed version stays.
