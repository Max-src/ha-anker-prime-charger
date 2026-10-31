/**
 * Charger 3D card: the charger as a 3D model (charger-model.js), showing the
 * ports in use (lit, with a cable unless `show_cables` is off) and the total
 * output (on its screen).
 *
 * With "Rotate by dragging" (on by default) it turns when dragged (on touch
 * screens sideways, so the page still scrolls) or with the arrow keys, and
 * zooms with Ctrl + the mouse wheel (a touchpad's pinch), a pinch on touch
 * screens, or + and - (the wheel alone still scrolls the page); Home or a
 * double-click goes back to the default view. Each card remembers its
 * view in Home Assistant's frontend data of the user, so the next time (on
 * any device) the charger is seen as it was left; the browser keeps a copy
 * (localStorage), so it is drawn that way at once. A card is told apart by
 * its view_id, given when it is created or first opened in the editor; a
 * card without one (an older one, or YAML) shares its charger's view.
 *
 * Its screen shows one of the charger's pages (`screen`): the power page (the
 * total output), the clock screensaver (the selected clock theme with the
 * current time, charger-screensaver.js), or nothing (the screen off).
 * Whatever it shows, each port's power can be written above it
 * (`show_port_power`: the USB-C ports' over the screen, as the charger's
 * power page shows them; the USB-A ports' on the side). Auto shows the one the charger shows, as the
 * integration estimates it (its Page sensor; the charger doesn't report it).
 *
 * The clock screensaver comes from screensaver-store.js (kept by the browser:
 * at once from the second page load on). The first time, the screen stays
 * dark until it is there, as the charger's screen would.
 *
 * Tapping a port (around it, its power or its cable) opens its power sensor,
 * its history, as on the outputs card (`port_history`, on by default). A
 * press that moves more than a few pixels turns the charger instead. Under
 * the mouse, the port is highlighted (touch screens have no hover).
 *
 * With `show_controls`, buttons in its top left corner (empty in the default
 * view: the charger's top edge is lowest there) zoom out and in and
 * turn it left and right (held down, they repeat). They work also when it can't be dragged.
 *
 *   type: custom:anker-prime-charger-3d-card
 *   device: <the charger's device id>   # optional: the first charger
 *   drag_to_rotate: true                # turn it by dragging (default true)
 *   screen: auto                        # auto (default), power, clock or off
 *   show_port_power: true               # each port's power above it (default true)
 *   show_cables: true                   # a cable in each port in use (default true)
 *   port_history: true                  # tap a port: its power history (default true)
 *   show_controls: false                # zoom and turn buttons (default false)
 *   view_id: k3x9q2                     # set by the editor
 */
import { css, html } from "./lib/lit-all.js";
import { ChargerCard } from "./card-base.js";
import { chargerSummary, summaryStates } from "./charger.js";
import { chargerModel, modelStyles } from "./charger-model.js";
import { screensaverDrawing, screensaverStyles } from "./charger-screensaver.js";
import { watchScreensaver } from "./screensaver-store.js";
import { defineOnce, registerCustomCard } from "./registration.js";
import { sharedStyles } from "./styles.js";

const DEFAULT_VIEW = { yaw: -35, pitch: 22, zoom: 1 };
const ZOOM_LIMITS = [0.6, 3];
const KEY_ZOOM = 1.1; // per + or - press (or button)
// per pixel of wheel: a mouse's notch (100 px) zooms about 10 %
const WHEEL_ZOOM = 0.001;
const WHEEL_LINE = 33; // px per line, for wheels that count lines (Firefox)
const PAGES = ["power", "clock", "off"]; // the charger's screen
const PITCH_LIMIT = 80;
const DEGREES_PER_PIXEL = 0.5;
const KEY_STEP = 10; // degrees per arrow key press
const BUTTON_TURN = 15; // degrees per press of a turn button
const REPEAT = { delay: 400, every: 90 }; // ms: a held button repeats
const SAVE_DELAY = 500; // ms after the last turn
const TAP_SLOP = 6; // px a tap may move (more: a drag)
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

/** The browser's copy of the views (the last ones seen or saved here). */
function keptViews() {
  try {
    return JSON.parse(localStorage.getItem(VIEWS_KEY)) || {};
  } catch {
    return {}; // none, or the browser keeps nothing
  }
}

function keepView(key, view) {
  try {
    localStorage.setItem(VIEWS_KEY, JSON.stringify({ ...keptViews(), [key]: view }));
  } catch {
    // not kept: drawn from Home Assistant's copy, a moment later
  }
}

// Saves one after the other: each reads all the views, changes its own and
// writes them all, so two at once (two cards) would lose one of them
let saving = Promise.resolve();

function saveView(hass, key, view) {
  keepView(key, view);
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

/** The id of the port ("c1") an event happened on, if any (charger-model.js). */
function portAt(event) {
  for (const element of event.composedPath()) {
    if (element === event.currentTarget) break;
    const id = element.getAttribute?.("data-port");
    if (id) return id;
  }
  return undefined;
}

const clamp = (pitch) => Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch));
const clampZoom = (zoom) => Math.max(ZOOM_LIMITS[0], Math.min(ZOOM_LIMITS[1], zoom));
const round = (degrees) => Math.round(degrees * 10) / 10;

class Charger3dCard extends ChargerCard {
  static cardSize = 4;

  static properties = {
    ...ChargerCard.properties,
    _yaw: { state: true },
    _pitch: { state: true },
    _zoom: { state: true },
    _screensaver: { state: true },
    _now: { state: true },
    _hover: { state: true },
  };

  static editorSchema = [
    {
      name: "drag_to_rotate",
      label: "Rotate by dragging",
      helper:
        "Turn the charger by dragging it (or with the arrow keys), zoom with Ctrl + the mouse wheel, a pinch, or + and -; its view is remembered.",
      default: true,
      selector: { boolean: {} },
    },
    {
      name: "show_cables",
      label: "Show plugged-in cables",
      helper: "A cable in each port with a device; off, those ports are only lit.",
      default: true,
      selector: { boolean: {} },
    },
    {
      name: "show_port_power",
      label: "Show each port's power",
      helper: "Above each port with a device, whatever the screen shows.",
      default: true,
      selector: { boolean: {} },
    },
    {
      name: "show_controls",
      label: "Show zoom and turn buttons",
      helper: "Buttons in the corner to zoom out and in and turn it left and right.",
      default: false,
      selector: { boolean: {} },
    },
    {
      name: "port_history",
      label: "Tap a port for its history",
      helper: "Tapping a port, its power or its cable opens the port's power history, as on the outputs card.",
      default: true,
      selector: { boolean: {} },
    },
    {
      name: "screen",
      label: "The screen shows",
      helper:
        "Auto: what the charger shows (estimated). Power: the total output. Clock: the selected clock theme, with the time.",
      default: "auto",
      selector: {
        button_toggle: {
          options: [
            { value: "auto", label: "Auto" },
            { value: "power", label: "Power" },
            { value: "clock", label: "Clock" },
            { value: "off", label: "Off" },
          ],
        },
      },
    },
  ];

  constructor() {
    super();
    this._yaw = DEFAULT_VIEW.yaw;
    this._pitch = DEFAULT_VIEW.pitch;
    this._zoom = DEFAULT_VIEW.zoom;
    this._pointers = new Map(); // touch pointers down: id -> {x, y}
  }

  /**
   * A card of its own: a view_id, so its view is its own. An earlier card's
   * show_screensaver becomes `screen`.
   */
  static completeConfig(config) {
    let completed = config;
    if ("show_screensaver" in completed) {
      const { show_screensaver: clock, ...rest } = completed;
      completed = { ...rest, screen: rest.screen ?? (clock ? "clock" : "power") };
    }
    return completed.view_id ? completed : { ...completed, view_id: newViewId() };
  }

  get _canRotate() {
    return this._config?.drag_to_rotate !== false;
  }

  get _tappable() {
    return this._config?.port_history !== false;
  }

  /** What the screen shows: "auto", "power", "clock" or "off". */
  get _screenMode() {
    const { screen, show_screensaver: clock } = this._config || {};
    if (PAGES.includes(screen) || screen === "auto") return screen;
    // a card from before `screen`
    if (clock !== undefined) return clock === true ? "clock" : "power";
    return "auto";
  }

  /** Whether the clock may show (then the screensaver and time are kept). */
  get _showsScreensaver() {
    return ["clock", "auto"].includes(this._screenMode);
  }

  /** The page shown: the mode, or with Auto the estimated one (else power). */
  _page(charger) {
    const mode = this._screenMode;
    if (mode !== "auto") return mode;
    const page = charger.screen?.page && this.hass.states[charger.screen.page]?.state;
    return PAGES.includes(page) ? page : "power";
  }

  connectedCallback() {
    super.connectedCallback();
    this._tick();
    this.requestUpdate(); // back on the page: follows its screensaver again
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearTimeout(this._clock);
    this._clock = undefined;
    this._stopRepeat();
    this._stopScreensaver?.();
    this._stopScreensaver = this._screensaverKey = undefined;
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
    const ids = [screen.page, screen.theme, screen.time_display, screen.clock_format];
    return [...states, ...ids.map((id) => hass.states[id])];
  }

  /** The screensaver of the selected theme (followed while it is selected). */
  _loadScreensaver() {
    const charger = this._charger;
    const theme = charger?.screen?.theme;
    if (!this._showsScreensaver || !theme) return;
    const selected = this.hass.states[theme]?.state;
    const key = `${charger.device_id}|${selected}`;
    if (key === this._screensaverKey) return;
    this._stopScreensaver?.();
    this._screensaverKey = key;
    // the one shown so far stays until the new one is there
    this._stopScreensaver = watchScreensaver(this.hass, charger.device_id, selected, (screensaver) => {
      this._screensaver = screensaver;
    });
  }

  /** The view as it was left, before drawing: the browser's copy, then Home Assistant's. */
  _loadView() {
    const key = this._charger && this._viewKey;
    if (!key || key === this._viewOf) return;
    this._viewOf = key;
    const show = (view) => {
      // not if the user is already turning it, or the card changed meanwhile
      if (!view || this._turned || this._viewKey !== key) return;
      this._yaw = Number(view.yaw) || DEFAULT_VIEW.yaw;
      this._pitch = clamp(Number(view.pitch) || 0);
      this._zoom = clampZoom(Number(view.zoom) || DEFAULT_VIEW.zoom);
    };
    show(keptViews()[key]);
    savedViews(this.hass).then((views) => {
      show(views[key]);
      if (views[key]) keepView(key, views[key]);
    });
  }

  /** Before each drawing: what it shows known as early as possible. */
  willUpdate(changed) {
    super.willUpdate(changed);
    this._loadView();
    this._loadScreensaver();
  }

  /** Whether the clock should show and isn't there yet (the first time). */
  _clockPending(charger) {
    return this._page(charger) === "clock" && !this._screensaver;
  }

  // --- Turning it ------------------------------------------------------------

  /** The view changed by the user: shown, and saved once they stop. */
  _turn(yaw, pitch, zoom = this._zoom) {
    this._turned = true;
    this._yaw = yaw;
    this._pitch = clamp(pitch);
    this._zoom = clampZoom(zoom);
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._saveView(), SAVE_DELAY);
  }

  _zoomBy(factor) {
    this._turn(this._yaw, this._pitch, this._zoom * factor);
  }

  /** Save the view now (a pending save is replaced). */
  _saveView() {
    clearTimeout(this._saveTimer);
    this._saveTimer = undefined;
    const key = this._viewKey;
    if (!key) return;
    const view = { yaw: round(this._yaw % 360), pitch: round(this._pitch) };
    saveView(this.hass, key, { ...view, zoom: Math.round(this._zoom * 100) / 100 });
  }

  _resetView() {
    this._turn(DEFAULT_VIEW.yaw, DEFAULT_VIEW.pitch, DEFAULT_VIEW.zoom);
  }

  /**
   * The port under the mouse (pen too), highlighted: the one pressed while a
   * tap is pending, none while dragging. Touch has no hover.
   */
  _onHover(event) {
    if (!this._tappable || event.pointerType === "touch") return;
    const port = this._tap ? this._tap.port : event.buttons ? undefined : portAt(event);
    if (port !== this._hover) this._hover = port;
  }

  _onLeave() {
    this._hover = undefined;
  }

  /** A double-click goes back to the default view, unless on a port (opened). */
  _onDoubleClick(event) {
    if (this._tappable && portAt(event)) return;
    this._resetView();
  }

  /** Two touch pointers' distance (a pinch), or undefined. */
  _pinchDistance() {
    if (this._pointers.size !== 2) return undefined;
    const [a, b] = [...this._pointers.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  _onPointerDown(event) {
    if (event.button !== 0) return;
    if (event.pointerType === "touch") {
      this._pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      // a second finger: a pinch, no more turning
      if (this._pointers.size === 2) {
        this._drag = undefined;
        this._pinch = this._pinchDistance();
      }
    }
    if (this._pointers.size < 2) this._drag = { x: event.clientX, y: event.clientY, id: event.pointerId };
    // a tap on a port, unless it moves (or a second finger comes)
    const port = this._tappable && this._pointers.size < 2 ? portAt(event) : undefined;
    this._tap = port ? { port, x: event.clientX, y: event.clientY, id: event.pointerId } : undefined;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  _onPointerMove(event) {
    const tap = this._tap;
    if (tap?.id === event.pointerId && Math.hypot(event.clientX - tap.x, event.clientY - tap.y) > TAP_SLOP) {
      this._tap = undefined;
    }
    this._onHover(event);
    if (this._pointers.has(event.pointerId)) {
      this._pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const distance = this._pinchDistance();
      if (distance && this._pinch) {
        this._zoomBy(distance / this._pinch);
        this._pinch = distance;
        return;
      }
    }
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
    const tap = this._tap;
    if (tap?.id === event.pointerId) {
      this._tap = undefined;
      if (event.type === "pointerup") this._openPort(tap.port);
    }
    this._hover = undefined; // the next move finds it again
    this._pointers.delete(event.pointerId);
    if (this._pointers.size < 2) this._pinch = undefined;
    if (this._drag?.id === event.pointerId) this._drag = undefined;
  }

  /** Ctrl + the wheel (a touchpad's pinch comes this way too) zooms; the wheel alone scrolls the page. */
  _onWheel(event) {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const pixels = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? event.deltaY * WHEEL_LINE : event.deltaY;
    this._zoomBy(Math.exp(-pixels * WHEEL_ZOOM));
  }

  // --- The buttons -----------------------------------------------------------

  /** The buttons' actions, by name. */
  get _controls() {
    return [
      { name: "Zoom out", icon: "mdi:magnify-minus-outline", act: () => this._zoomBy(1 / KEY_ZOOM) },
      { name: "Zoom in", icon: "mdi:magnify-plus-outline", act: () => this._zoomBy(KEY_ZOOM) },
      { name: "Turn left", icon: "mdi:rotate-left", act: () => this._turn(this._yaw - BUTTON_TURN, this._pitch) },
      { name: "Turn right", icon: "mdi:rotate-right", act: () => this._turn(this._yaw + BUTTON_TURN, this._pitch) },
    ];
  }

  /** A button pressed: acts at once, then again while held. */
  _onControlDown(event, control) {
    if (event.button !== 0) return;
    event.preventDefault(); // no focus ring, no text selection
    this._stopRepeat();
    control.act();
    this._repeat = setTimeout(() => {
      this._repeat = setInterval(control.act, REPEAT.every);
    }, REPEAT.delay);
  }

  _stopRepeat() {
    clearTimeout(this._repeat);
    clearInterval(this._repeat);
    this._repeat = undefined;
  }

  /** A click from the keyboard (Enter, space: no pointer, detail 0) acts once;
   * a pointer's has already acted when pressed. */
  _onControlClick(event, control) {
    if (event.detail === 0) control.act();
  }

  _renderControls() {
    if (this._config.show_controls !== true) return "";
    return html`<div class="controls">
      ${this._controls.map(
        (control) => html`<button
          title=${control.name}
          aria-label=${control.name}
          @pointerdown=${(event) => this._onControlDown(event, control)}
          @pointerup=${this._stopRepeat}
          @pointerleave=${this._stopRepeat}
          @pointercancel=${this._stopRepeat}
          @click=${(event) => this._onControlClick(event, control)}
        >
          <ha-icon icon=${control.icon}></ha-icon>
        </button>`,
      )}
    </div>`;
  }

  /** Enter or space on a port's tap area opens it; whether it did. */
  _onPortKey(event) {
    if (!this._tappable || (event.key !== "Enter" && event.key !== " ")) return false;
    const port = portAt(event);
    if (!port) return false;
    event.preventDefault();
    this._openPort(port);
    return true;
  }

  /** Not rotatable: a click on a port opens it. */
  _onClick(event) {
    const port = this._tappable ? portAt(event) : undefined;
    if (port) this._openPort(port);
  }

  /** Open a port's power sensor (its history), as Home Assistant's cards do. */
  _openPort(id) {
    const entityId = this._charger?.ports.find((port) => port.id === id)?.power;
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }),
    );
  }

  _onKeyDown(event) {
    if (this._onPortKey(event)) return;
    const turns = {
      ArrowLeft: [-KEY_STEP, 0],
      ArrowRight: [KEY_STEP, 0],
      ArrowUp: [0, -KEY_STEP],
      ArrowDown: [0, KEY_STEP],
    };
    const zooms = { "+": KEY_ZOOM, "=": KEY_ZOOM, "-": 1 / KEY_ZOOM };
    if (event.key === "Home") {
      this._resetView();
    } else if (zooms[event.key]) {
      this._zoomBy(zooms[event.key]);
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
    const { offline, inUse, total, portPower } = chargerSummary(this.hass, charger);
    const model = chargerModel({
      yaw: this._yaw,
      pitch: this._pitch,
      zoom: this._zoom,
      inUse,
      screen: this._screen(charger, total),
      portPower: this._config.show_port_power === false ? undefined : portPower,
      cables: this._config.show_cables !== false,
      tappable: this._tappable,
      hovered: this._hover,
    });
    if (!this._canRotate) {
      return html`<ha-card>
        <div
          class=${offline ? "offline" : ""}
          title=${charger.name}
          @click=${this._onClick}
          @keydown=${this._onPortKey}
          @pointermove=${this._onHover}
          @pointerleave=${this._onLeave}
        >
          ${model}
        </div>
        ${this._renderControls()}
      </ha-card>`;
    }
    return html`<ha-card>
      <div
        class="rotatable ${offline ? "offline" : ""}"
        title=${charger.name}
        tabindex="0"
        aria-label="${charger.name}: drag or use the arrow keys to turn it, + and - to zoom"
        @pointerdown=${this._onPointerDown}
        @pointermove=${this._onPointerMove}
        @pointerup=${this._onPointerUp}
        @pointercancel=${this._onPointerUp}
        @pointerleave=${this._onLeave}
        @wheel=${this._onWheel}
        @dblclick=${this._onDoubleClick}
        @keydown=${this._onKeyDown}
      >
        ${model}
      </div>
      ${this._renderControls()}
    </ha-card>`;
  }

  /** What the screen shows (chargerModel's `screen`). */
  _screen(charger, total) {
    const mode = this._page(charger);
    if (mode === "off") return { mode };
    // the clock once the screensaver is known; dark until then (the first
    // time), the power page while the charger hasn't reported its theme
    const content = mode === "clock" ? this._screensaverContent(charger) : undefined;
    if (content) return { mode, content };
    if (this._clockPending(charger)) return { mode: "off" };
    return { mode: "power", total };
  }

  /** The clock screensaver's drawing, or undefined while it isn't known. */
  _screensaverContent(charger) {
    const screensaver = this._screensaver;
    if (!screensaver?.kind) return undefined;
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
        position: relative;
        overflow: hidden;
      }
      .controls {
        position: absolute;
        left: 8px;
        top: 8px;
        display: flex;
        gap: 4px;
      }
      .controls button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        padding: 0;
        border: 1px solid var(--divider-color);
        border-radius: 50%;
        background: color-mix(in srgb, var(--card-background-color, #fff) 85%, transparent);
        color: var(--secondary-text-color);
        cursor: pointer;
        touch-action: manipulation; /* quick taps: no double-tap zoom */
        --mdc-icon-size: 18px;
      }
      .controls button:hover {
        color: var(--primary-color);
        border-color: var(--primary-color);
      }
      .controls button:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }
      .controls ha-icon {
        display: flex;
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
