/**
 * What every charger card shares, so a card only describes what it shows:
 *
 * - its config (setConfig: `device`, the charger's device id; empty = the
 *   first charger), and the charger it shows (this._charger, loaded from the
 *   integration; this._error when that failed). Loaded again when the device
 *   or the entity registry changes (an entity renamed, a charger set up);
 * - renders only when something it shows changed: Home Assistant hands out a
 *   new `hass` on every state change anywhere (_watched(): the state objects
 *   a card shows, compared by reference);
 * - the visual editor (static editorSchema and completeConfig, see
 *   card-editor.js) and the stub config of a new card (the first charger,
 *   completed);
 * - its size in dashboards (static cardSize, gridRows).
 */
import { LitElement, html } from "./lib/lit-all.js";
import { loadCharger } from "./charger.js";
import "./card-editor.js";

export class ChargerCard extends LitElement {
  static properties = {
    _charger: { state: true },
    _error: { state: true },
  };

  /** ha-form schema of the card's options, after the charger picker. */
  static editorSchema = [];
  /** The config the editor saves, completed (override; the same if complete). */
  static completeConfig(config) {
    return config;
  }
  static cardSize = 3; // masonry dashboards: rows of 50 px
  static gridRows = "auto"; // sections dashboards

  static getConfigElement() {
    const editor = document.createElement("anker-prime-charger-card-editor");
    editor.schema = this.editorSchema;
    editor.complete = (config) => this.completeConfig(config);
    return editor;
  }

  /** A new card shows the first charger. */
  static async getStubConfig(hass) {
    let device = ""; // no charger yet: the card says so
    try {
      device = (await loadCharger(hass)).device_id;
    } catch {
      // keep it empty
    }
    return this.completeConfig({ device });
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    const device = config.device ?? "";
    if (device !== this._config?.device) {
      this._charger = undefined;
      this._error = undefined;
    }
    this._config = { ...config, device };
    this._load();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._load();
    const watched = this._charger ? this._watched(hass) : [];
    const changed =
      watched.length !== this._lastWatched?.length ||
      watched.some((state, i) => state !== this._lastWatched[i]);
    this._lastWatched = watched;
    if (changed || first) this.requestUpdate();
  }

  get hass() {
    return this._hass;
  }

  /** The state objects the card shows (override). */
  _watched(_hass) {
    return [];
  }

  /** Load the charger, unless it is loaded (or loading) for this device and
   * entity registry. A failure isn't retried until one of them changes. */
  _load() {
    if (this._loading || !this._hass || !this._config) return;
    const device = this._config.device;
    const entities = this._hass.entities;
    const loaded = this._loadedFor;
    if (loaded && loaded.device === device && loaded.entities === entities) return;
    // an answer for a device no longer configured is dropped
    const current = () => device === this._config.device;
    this._loading = loadCharger(this._hass, device)
      .then((charger) => {
        if (!current()) return;
        this._charger = charger;
        this._error = undefined;
      })
      .catch((err) => {
        if (!current()) return;
        this._charger = undefined;
        this._error = err?.message || String(err);
      })
      .finally(() => {
        if (current()) this._loadedFor = { device, entities };
        this._loading = undefined;
        this._lastWatched = this._charger ? this._watched(this._hass) : [];
        this._load(); // the device or registry changed meanwhile
      });
  }

  /** The card's content once the charger is known (override). */
  _renderCharger(_charger) {
    return html``;
  }

  render() {
    if (this._error) {
      return html`<ha-card>
        <ha-alert alert-type="warning">${this._error}</ha-alert>
      </ha-card>`;
    }
    if (!this._charger) return html`<ha-card class="loading"></ha-card>`;
    return this._renderCharger(this._charger);
  }

  getCardSize() {
    return this.constructor.cardSize;
  }

  getGridOptions() {
    return { columns: 12, rows: this.constructor.gridRows, min_columns: 6 };
  }
}
