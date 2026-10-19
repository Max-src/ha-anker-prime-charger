/**
 * Browser side of the documentation screenshots (tests/card-docs.cjs): mounts
 * one card, or its editor, in the real Home Assistant frontend with
 * synthetic charger state, for the runner to screenshot (#card-docs).
 *
 * The page is a real, logged-in Home Assistant dashboard: its fonts, theme
 * and elements (ha-card, ha-form...). Synthetic: the charger (the
 * integration's answer, see frontend.py) and the states of its entities. A
 * card gets a copy of the page's `hass` with those and its websocket calls
 * answered here, so that Home Assistant needs neither the integration nor a
 * charger. Loaded after the cards' module, as a plain script (window.cardDocs).
 */
window.cardDocs = (() => {
  const DEVICE = "docs-charger";
  const VIEW_ID = "docs"; // the 3D card's, so a scenario can give it a view
  // A port's [watts, volts, amps] while a device is plugged in: the usual
  // desk, unless the scenario says otherwise (`ports`)
  const PORTS = { c1: [7.2, 9.0, 0.8], c2: [1.5, 5.0, 0.3], a2: [3.5, 5.0, 0.7] };
  const ALL_PORTS = ["c1", "c2", "c3", "c4", "a1", "a2"];
  const SETTLE_TIMEOUT = 15000;

  const entityId = (port, reading) => `sensor.docs_charger_${port}_${reading}`;
  const connectedId = (port) => `binary_sensor.docs_charger_${port}_connected`;
  const TOTAL_ID = "sensor.docs_charger_total_output_power";
  const SCREEN = {
    theme: "select.docs_charger_clock_theme",
    time_display: "switch.docs_charger_time_display",
    clock_format: "select.docs_charger_clock_format",
  };
  // The time on the clock screensavers: fixed, so that captures match
  const NOW = new Date(2026, 0, 14, 8, 40, 0).getTime();
  // A picture for the stock and custom themes, ours (480 x 200): a sunset
  const PICTURE =
    "data:image/svg+xml," +
    encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="480" height="200">
      <defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#1b2a6b"/><stop offset="0.6" stop-color="#e2725b"/>
        <stop offset="1" stop-color="#f6c36b"/></linearGradient></defs>
      <rect width="480" height="200" fill="url(#sky)"/>
      <circle cx="350" cy="150" r="46" fill="#ffd98a"/>
      <path d="M0 170 L90 120 L170 165 L260 105 L360 175 L480 130 L480 200 L0 200 Z" fill="#2a1f3d"/>
    </svg>`);

  /** The integration's answer about the charger (frontend.py). */
  function charger() {
    return {
      device_id: DEVICE,
      name: "Anker Prime Charger",
      model: "A2345",
      total_power: TOTAL_ID,
      ports: ALL_PORTS.map((id) => ({
        id,
        label: id.toUpperCase(),
        usb_c: id.startsWith("c"),
        connected: connectedId(id),
        power: entityId(id, "power"),
        voltage: entityId(id, "voltage"),
        current: entityId(id, "current"),
      })),
      screen: SCREEN,
    };
  }

  /** The entities' states for a scenario: its ports' readings, or offline. */
  function states({ ports = PORTS, offline = false, screensaver = {} }) {
    const state = (value) => ({ state: offline ? "unavailable" : String(value), attributes: {} });
    const result = {};
    let total = 0;
    for (const id of ALL_PORTS) {
      const [watts, volts, amps] = ports[id] || [0, 0, 0];
      total += watts;
      result[connectedId(id)] = state(ports[id] ? "on" : "off");
      result[entityId(id, "power")] = state(watts);
      result[entityId(id, "voltage")] = state(volts);
      result[entityId(id, "current")] = state(amps);
    }
    result[TOTAL_ID] = state(total.toFixed(1));
    result[SCREEN.theme] = state(screensaver.kind || "style_2");
    result[SCREEN.time_display] = state(screensaver.time_display === false ? "off" : "on");
    result[SCREEN.clock_format] = state(screensaver.clock_format || "24h");
    return result;
  }

  /** The page's hass with the synthetic charger: its states, its answers. */
  function syntheticHass(hass, scenario) {
    return {
      ...hass,
      states: states(scenario),
      entities: {}, // one registry: the card asks about the charger once
      async callWS(message) {
        switch (message.type) {
          case "anker_prime_charger/charger":
            return charger();
          case "frontend/get_user_data":
            return { value: scenario.view ? { [VIEW_ID]: scenario.view } : null };
          case "frontend/set_user_data":
            return null;
          case "anker_prime_charger/screensaver": {
            const kind = scenario.screensaver?.kind || "style_2";
            const picture = kind === "stock" || kind === "custom";
            return { kind, name: kind, image_url: picture ? PICTURE : null };
          }
          default:
            throw Error(`Unexpected websocket command: ${message.type}`);
        }
      },
      callService() {
        throw Error("The documentation fixture calls no service");
      },
    };
  }

  /** Home Assistant's default theme, light or dark, applied to the page
   * (in memory: nothing is saved to the user's profile). */
  function applyTheme(host, dark) {
    if (typeof host._updateHass !== "function" || typeof host._applyTheme !== "function") {
      throw Error("Home Assistant's theme internals changed: update tests/card-docs-browser.js");
    }
    host._updateHass({ selectedTheme: { theme: "default", dark } });
    host._applyTheme(dark);
    if (host.hass.themes.darkMode !== dark) throw Error("The theme did not apply");
  }

  /** Every element under `root`, through open shadow roots. */
  function* elements(root) {
    for (const element of root.querySelectorAll("*")) {
      yield element;
      if (element.shadowRoot) yield* elements(element.shadowRoot);
    }
  }

  const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));

  async function until(condition, what) {
    const start = performance.now();
    while (!condition()) {
      if (performance.now() - start > SETTLE_TIMEOUT) throw Error(`Timed out waiting for ${what}`);
      await frame();
    }
  }

  // Transitions and animations off, in every shadow root too: a capture
  // mid-fade would differ from the next one
  const stillSheet = new CSSStyleSheet();
  stillSheet.replaceSync("*, *::before, *::after { transition: none !important; animation: none !important; }");

  /** Wait until nothing under `root` is still rendering. */
  async function settled(root) {
    await document.fonts.ready;
    for (let pass = 0; pass < 50; pass++) {
      let rendering = false;
      for (const element of elements(root)) {
        const shadow = element.shadowRoot;
        if (shadow && !shadow.adoptedStyleSheets.includes(stillSheet)) {
          shadow.adoptedStyleSheets = [...shadow.adoptedStyleSheets, stillSheet];
        }
        // a Lit element: updateComplete is false when another update follows
        if (element.updateComplete && (await element.updateComplete) === false) rendering = true;
      }
      await frame();
      if (!rendering && pass > 1) return;
    }
    throw Error("The card kept rendering");
  }

  const height = (element) => element?.getBoundingClientRect().height || 0;

  /** What a card must show, or the capture is wrong. */
  function checkCard(card) {
    const shadow = card.shadowRoot;
    if (shadow.querySelector("ha-alert")) throw Error(`The card shows an error: ${shadow.textContent.trim()}`);
    if (shadow.querySelector("ha-card.loading")) throw Error("The card is still loading its charger");
    if (!height(shadow.querySelector("ha-card"))) throw Error("The card has no height");
  }

  /** What an editor must show: its form, with every option rendered. */
  function checkEditor(editor, options) {
    const form = editor.shadowRoot.querySelector("ha-form");
    const selectors = form?.shadowRoot?.querySelectorAll("ha-selector") || [];
    if (selectors.length !== options) throw Error(`The editor shows ${selectors.length} of ${options} options`);
    for (const selector of selectors) {
      if (height(selector) < 20) throw Error("An option of the editor is not rendered yet");
    }
  }

  /**
   * Mount an image's subject in a fresh #card-docs container: the card with
   * the scenario's state and options, or (group "editors") its editor with
   * the page's own hass (the charger picker needs the registries).
   */
  /** Freeze the time (the clock screensavers show it). */
  function freezeTime() {
    if (Date.now() === NOW) return;
    const Real = Date;
    window.Date = class extends Real {
      constructor(...args) {
        super(...(args.length ? args : [NOW]));
      }
      static now() {
        return NOW;
      }
    };
  }

  async function mount({ element, group, scenario }) {
    const host = document.querySelector("home-assistant");
    if (!host?.hass?.connected || !customElements.get("ha-card")) {
      throw Error("A loaded, logged-in Home Assistant frontend is required");
    }
    const Card = customElements.get(element);
    if (!Card) throw Error(`Card not loaded: ${element}`);
    freezeTime();
    applyTheme(host, !!scenario.dark);
    document.getElementById("card-docs")?.remove();
    const container = document.createElement("div");
    container.id = "card-docs";
    container.style.cssText =
      `position:fixed;top:0;left:0;z-index:100000;box-sizing:border-box;padding:16px;` +
      `width:${scenario.width || 420}px;background:var(--primary-background-color);`;
    host.shadowRoot.append(container);

    const editor = group === "editors";
    const config = {
      type: `custom:${element}`,
      device: editor ? "" : DEVICE,
      view_id: VIEW_ID,
      ...scenario.config,
    };
    let subject;
    if (editor) {
      subject = await Card.getConfigElement();
      subject.hass = host.hass;
      subject.setConfig(config);
      const card = document.createElement("ha-card");
      card.style.padding = "16px";
      card.append(subject);
      container.append(card);
      const options = Card.editorSchema.length + 1; // and the charger picker
      await until(() => {
        try {
          checkEditor(subject, options);
          return true;
        } catch {
          return false;
        }
      }, "the editor's options");
      await settled(container);
      checkEditor(subject, options);
    } else {
      subject = document.createElement(element);
      subject.setConfig(config);
      subject.hass = syntheticHass(host.hass, scenario);
      container.append(subject);
      await until(() => !subject.shadowRoot?.querySelector("ha-card.loading"), "the charger");
      await settled(container);
      checkCard(subject);
    }
    if (container.scrollWidth > container.clientWidth) throw Error("Horizontal overflow");
  }

  return { mount };
})();
