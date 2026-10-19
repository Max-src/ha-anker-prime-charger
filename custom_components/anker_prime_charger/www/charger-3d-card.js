/**
 * Charger 3D card: the charger as a 3D model (charger-model.js), showing the
 * ports in use (with a cable) and the total output (on its screen).
 *
 * With "Rotate by dragging" (on by default) it turns when dragged (on touch
 * screens sideways, so the page still scrolls) or with the arrow keys; Home
 * or a double-click goes back to the default view. Each card remembers its
 * view in Home Assistant's frontend data of the user, so the next time (on
 * any device) the charger is seen as it was left. A card is told apart by
 * its view_id, given when it is created or first opened in the editor; a
 * card without one (an older one, or YAML) shares its charger's view.
 *
 * With "Show the clock screensaver", the screen shows the charger's selected
 * clock theme (charger-screensaver.js) with the current time, instead of the
 * total output: drawn whether or not the charger shows it right now (that
 * isn't reported).
 *
 *   type: custom:anker-prime-charger-3d-card
 *   device: <the charger's device id>   # optional: the first charger
 *   drag_to_rotate: true                # turn it by dragging (default true)
 *   show_screensaver: false             # the clock theme on its screen
 *   view_id: k3x9q2                     # set by the editor
 */
import { css, html } from "./lib/lit-all.js";
import { ChargerCard } from "./card-base.js";
import { chargerSummary, summaryStates } from "./charger.js";
import { chargerModel, modelStyles } from "./charger-model.js";
import { screensaverDrawing, screensaverStyles } from "./charger-screensaver.js";
import { defineOnce, registerCustomCard } from "./registration.js";
import { sharedStyles } from "./styles.js";

const DEFAULT_VIEW = { yaw: -35, pitch: 22 };
const PITCH_LIMIT = 80;
const DEGREES_PER_PIXEL = 0.5;
const KEY_STEP = 10; // degrees per arrow key press
const SAVE_DELAY = 500; // ms after the last turn
// The user's frontend data (Home Assistant): {view key: {yaw, pitch}}, the key
// being a card's view_id, or the charger's device id for a card without one
const VIEWS_KEY = "anker_prime_charger_3d_views";

/** A new card's view_id: short and random. */
const newViewId = () => Math.random().toString(36).slice(2, 10);

async function savedViews(hass) {
  try {
    return (await hass.callWS({ type: "frontend/get_user_data", key: VIEWS_KEY }))?.value || {};
  } catch {
    return {}; // not stored yet, or not available: the default view
  }
}

// Saves one after the other: each reads all the views, changes its own and
// writes them all, so two at once (two cards) would lose one of them
let saving = Promise.resolve();

function saveView(hass, key, view) {
  saving = saving.then(async () => {
    const views = await savedViews(hass);
    views[key] = view;
    try {
      await hass.callWS({ type: "frontend/set_user_data", key: VIEWS_KEY, value: views });
    } catch {
      // not saved: the view is kept until the page is reloaded
    }
  });
  return saving;
}

const clamp = (pitch) => Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch));
const round = (degrees) => Math.round(degrees * 10) / 10;

class Charger3dCard extends ChargerCard {
  static cardSize = 4;

  static properties = {
    ...ChargerCard.properties,
    _yaw: { state: true },
    _pitch: { state: true },
    _screensaver: { state: true },
    _now: { state: true },
  };

  static editorSchema = [
    {
      name: "drag_to_rotate",
      label: "Rotate by dragging",
      helper: "Turn the charger by dragging it (or with the arrow keys); its view is remembered.",
      default: true,
      selector: { boolean: {} },
    },
    {
      name: "show_screensaver",
      label: "Show the clock screensaver",
      helper:
        "The charger's screen shows its selected clock theme, with the time, instead of the total output.",
      default: false,
      selector: { boolean: {} },
    },
  ];

  constructor() {
    super();
    this._yaw = DEFAULT_VIEW.yaw;
    this._pitch = DEFAULT_VIEW.pitch;
  }

  /** A card of its own: a view_id, so its view is its own. */
  static completeConfig(config) {
    return config.view_id ? config : { ...config, view_id: newViewId() };
  }

  get _canRotate() {
    return this._config?.drag_to_rotate !== false;
  }

  get _showsScreensaver() {
    return this._config?.show_screensaver === true;
  }

  connectedCallback() {
    super.connectedCallback();
    this._tick();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearTimeout(this._clock);
    this._clock = undefined;
    // turned just before leaving the page: saved now
    if (this._saveTimer) this._saveView();
  }

  setConfig(config) {
    super.setConfig(config);
    if (this.isConnected) this._tick();
  }

  /** The clock: the time now, and again at the next minute (while shown). */
  _tick() {
    clearTimeout(this._clock);
    this._clock = undefined;
    if (!this._showsScreensaver || !this.isConnected) return;
    this._now = new Date();
    const next = 60000 - (Date.now() % 60000) + 50;
    this._clock = setTimeout(() => this._tick(), next);
  }

  /** Where the card's view is saved: its view_id, else its charger. */
  get _viewKey() {
    return this._config?.view_id || this._charger?.device_id;
  }

  _watched(hass) {
    const states = summaryStates(hass, this._charger);
    if (!this._showsScreensaver) return states;
    const screen = this._charger.screen || {};
    return [...states, ...[screen.theme, screen.time_display, screen.clock_format].map((id) => hass.states[id])];
  }

  /** The screensaver, asked again when the selected theme changes. */
  _loadScreensaver() {
    const charger = this._charger;
    const theme = charger?.screen?.theme;
    if (!this._showsScreensaver || !theme) return;
    const key = `${charger.device_id}|${this.hass.states[theme]?.state}`;
    if (key === this._screensaverKey) return;
    this._screensaverKey = key;
    this.hass
      .callWS({ type: "anker_prime_charger/screensaver", device_id: charger.device_id })
      .then((screensaver) => {
        if (this._screensaverKey === key) this._screensaver = screensaver;
      })
      .catch(() => {
        // not now: asked again with the next theme change or page load
        if (this._screensaverKey === key) this._screensaverKey = undefined;
      });
  }

  /** Once the charger is known: show it as it was left. */
  updated(changed) {
    super.updated(changed);
    this._loadScreensaver();
    const key = this._charger && this._viewKey;
    if (!key || key === this._viewOf) return;
    this._viewOf = key;
    savedViews(this.hass).then((views) => {
      const view = views[key];
      // not if the user is already turning it, or the card changed meanwhile
      if (!view || this._turned || this._viewKey !== key) return;
      this._yaw = Number(view.yaw) || DEFAULT_VIEW.yaw;
      this._pitch = clamp(Number(view.pitch) || 0);
    });
  }

  // --- Turning it ------------------------------------------------------------

  /** The view changed by the user: shown, and saved once they stop. */
  _turn(yaw, pitch) {
    this._turned = true;
    this._yaw = yaw;
    this._pitch = clamp(pitch);
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._saveView(), SAVE_DELAY);
  }

  /** Save the view now (a pending save is replaced). */
  _saveView() {
    clearTimeout(this._saveTimer);
    this._saveTimer = undefined;
    const key = this._viewKey;
    if (key) saveView(this.hass, key, { yaw: round(this._yaw % 360), pitch: round(this._pitch) });
  }

  _resetView() {
    this._turn(DEFAULT_VIEW.yaw, DEFAULT_VIEW.pitch);
  }

  _onPointerDown(event) {
    if (event.button !== 0) return;
    this._drag = { x: event.clientX, y: event.clientY, id: event.pointerId };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  _onPointerMove(event) {
    const drag = this._drag;
    if (!drag || drag.id !== event.pointerId) return;
    const yaw = this._yaw + (event.clientX - drag.x) * DEGREES_PER_PIXEL;
    // touch: sideways only (up and down scrolls the page)
    const pitch =
      event.pointerType === "touch"
        ? this._pitch
        : this._pitch + (event.clientY - drag.y) * DEGREES_PER_PIXEL;
    drag.x = event.clientX;
    drag.y = event.clientY;
    this._turn(yaw, pitch);
  }

  _onPointerUp(event) {
    if (this._drag?.id === event.pointerId) this._drag = undefined;
  }

  _onKeyDown(event) {
    const turns = {
      ArrowLeft: [-KEY_STEP, 0],
      ArrowRight: [KEY_STEP, 0],
      ArrowUp: [0, -KEY_STEP],
      ArrowDown: [0, KEY_STEP],
    };
    if (event.key === "Home") {
      this._resetView();
    } else if (turns[event.key]) {
      const [yaw, pitch] = turns[event.key];
      this._turn(this._yaw + yaw, this._pitch + pitch);
    } else {
      return;
    }
    event.preventDefault();
  }

  // --- Drawing ---------------------------------------------------------------

  _renderCharger(charger) {
    const { offline, inUse, screen } = chargerSummary(this.hass, charger);
    const model = chargerModel({
      yaw: this._yaw,
      pitch: this._pitch,
      inUse,
      screen,
      screensaver: this._screensaverContent(charger),
    });
    if (!this._canRotate) {
      return html`<ha-card>
        <div class=${offline ? "offline" : ""} title=${charger.name}>${model}</div>
      </ha-card>`;
    }
    return html`<ha-card>
      <div
        class="rotatable ${offline ? "offline" : ""}"
        title=${charger.name}
        tabindex="0"
        aria-label="${charger.name}: drag or use the arrow keys to turn it"
        @pointerdown=${this._onPointerDown}
        @pointermove=${this._onPointerMove}
        @pointerup=${this._onPointerUp}
        @pointercancel=${this._onPointerUp}
        @dblclick=${this._resetView}
        @keydown=${this._onKeyDown}
      >
        ${model}
      </div>
    </ha-card>`;
  }

  /** What the screen shows instead of the total output, or undefined. */
  _screensaverContent(charger) {
    const screensaver = this._screensaver;
    if (!this._showsScreensaver || !screensaver?.kind) return undefined;
    const state = (id) => (id ? this.hass.states[id]?.state : undefined);
    const screen = charger.screen || {};
    return screensaverDrawing({
      kind: screensaver.kind,
      imageUrl: screensaver.image_url,
      // the charger always shows the time on stock themes
      showTime: screensaver.kind === "stock" || state(screen.time_display) === "on",
      now: this._now || new Date(),
      clock24h: state(screen.clock_format) === "24h",
    });
  }

  static styles = [
    sharedStyles,
    modelStyles,
    screensaverStyles,
    css`
      ha-card {
        overflow: hidden;
      }
      .rotatable {
        cursor: grab;
        touch-action: pan-y; /* sideways drags turn it, the page scrolls */
        user-select: none;
        outline: none;
        border-radius: inherit;
      }
      .rotatable:active {
        cursor: grabbing;
      }
      .rotatable:focus-visible {
        box-shadow: inset 0 0 0 2px var(--primary-color);
      }
    `,
  ];
}

defineOnce("anker-prime-charger-3d-card", Charger3dCard);
registerCustomCard({
  type: "anker-prime-charger-3d-card",
  name: "Anker Prime Charger 3D",
  description: "The charger in 3D, which you can turn by dragging. Shows the ports in use and the total output.",
  preview: true,
});
