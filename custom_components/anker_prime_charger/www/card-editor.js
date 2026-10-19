/**
 * The visual editor of the charger cards: Home Assistant's own form
 * (ha-form), so the charger picker and the options look and behave like
 * those of the built-in cards. Each card gives its options as an ha-form
 * schema (its static editorSchema); the charger picker comes first. A card
 * can also complete the config it edits (its static completeConfig, e.g. an
 * id of its own): the completed config is reported, so it is saved.
 */
import { LitElement, html } from "./lib/lit-all.js";
import { DOMAIN, MODEL_NAME } from "./charger.js";
import { defineOnce } from "./registration.js";

const DEVICE_FIELD = {
  name: "device",
  // only chargers (their ports and screen are devices of the integration too)
  selector: { device: { filter: { integration: DOMAIN, model: MODEL_NAME } } },
};

/** Labels of the options, by name (a schema item can give its own: label). */
const LABELS = {
  device: "Charger",
};

/**
 * ha-form is part of Home Assistant's frontend but loaded on demand: make
 * sure it is, by asking for the editor of a built-in card that uses it.
 */
async function loadHaForm() {
  if (customElements.get("ha-form")) return;
  const helpers = await window.loadCardHelpers?.();
  const card = await helpers?.createCardElement({ type: "entities", entities: [] });
  await card?.constructor?.getConfigElement?.();
}

class ChargerCardEditor extends LitElement {
  static properties = {
    hass: { attribute: false },
    schema: { attribute: false },
    complete: { attribute: false },
    _config: { state: true },
    _ready: { state: true },
  };

  constructor() {
    super();
    this.schema = [];
    this.complete = (config) => config;
    loadHaForm().finally(() => {
      this._ready = true;
    });
  }

  setConfig(config) {
    const completed = this.complete(config);
    this._config = completed;
    if (completed !== config) this._report(completed);
  }

  render() {
    if (!this._ready || !this.hass || !this._config) return html``;
    return html`<ha-form
      .hass=${this.hass}
      .data=${this._withDefaults()}
      .schema=${[DEVICE_FIELD, ...this.schema]}
      .computeLabel=${(item) => item.label ?? LABELS[item.name] ?? item.name}
      .computeHelper=${(item) => item.helper}
      @value-changed=${this._valueChanged}
    ></ha-form>`;
  }

  /** The config with the schema's defaults for unset options: ha-form shows
   * an unset option as empty (a boolean as off), not as its default. */
  _withDefaults() {
    const data = { ...this._config };
    for (const item of this.schema) {
      if (data[item.name] === undefined && item.default !== undefined) {
        data[item.name] = item.default;
      }
    }
    return data;
  }

  _valueChanged(event) {
    event.stopPropagation();
    // keep the card's type and options ha-form doesn't know
    const config = { ...this._config, ...event.detail.value };
    this._config = config;
    this._report(config);
  }

  /** Report the edited config to Home Assistant's card editor. */
  _report(config) {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

defineOnce("anker-prime-charger-card-editor", ChargerCardEditor);
