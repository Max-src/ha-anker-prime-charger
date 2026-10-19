/**
 * Charger outputs card: the power of each port, as the Anker app shows it
 * below the charger: a "USB-C Output" panel (C1-C4) and a "USB-A Output"
 * panel (A1, A2). A port with a device plugged in has a coloured label and
 * shows its power, voltage and current; the others show "--". Tapping a port
 * opens its power sensor.
 *
 *   type: custom:anker-prime-charger-outputs-card
 *   device: <the charger's device id>   # optional: the first charger
 *   show_details: true                  # voltage and current (default true)
 */
import { css, html } from "./lib/lit-all.js";
import { ChargerCard } from "./card-base.js";
import { formatNumber, portStates, readPort } from "./charger.js";
import { defineOnce, registerCustomCard } from "./registration.js";
import { sharedStyles } from "./styles.js";

const PANELS = [
  { title: "USB-C Output", usbC: true },
  { title: "USB-A Output", usbC: false },
];

class ChargerOutputsCard extends ChargerCard {
  static cardSize = 4;

  static editorSchema = [
    {
      name: "show_details",
      label: "Show voltage and current",
      default: true,
      selector: { boolean: {} },
    },
  ];

  _watched(hass) {
    return this._charger.ports.flatMap((port) => portStates(hass, port));
  }

  _renderCharger(charger) {
    const ports = charger.ports.map((port) => readPort(this.hass, port));
    return html`<div class="panels">
      ${PANELS.map(
        (panel) => html`<ha-card class=${panel.usbC ? "usb-c" : "usb-a"}>
          <div class="title">${panel.title}</div>
          <div class="ports">
            ${ports.filter((port) => port.usb_c === panel.usbC).map((port) => this._renderPort(port))}
          </div>
        </ha-card>`,
      )}
    </div>`;
  }

  _renderPort(port) {
    const hass = this.hass;
    const details = this._config.show_details !== false;
    return html`<div
      class="port ${port.isConnected ? "connected" : ""}"
      role="button"
      tabindex="0"
      @click=${() => this._showMoreInfo(port.power)}
      @keydown=${(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this._showMoreInfo(port.power);
        }
      }}
    >
      <span class="label">${port.label}</span>
      <span class="power">
        <span class="value">${formatNumber(hass, port.watts)}</span>
        <span class="unit">W</span>
      </span>
      ${details
        ? html`<span class="details">
            ${formatNumber(hass, port.volts)}V / ${formatNumber(hass, port.amps)}A
          </span>`
        : ""}
    </div>`;
  }

  /** Open an entity's dialog, as Home Assistant's cards do. */
  _showMoreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static styles = [
    sharedStyles,
    css`
      :host {
        /* the Anker app's colour of a port without a device */
        --anker-port-idle-color: #c2c6c7;
      }
      .panels {
        display: grid;
        /* USB-C: two columns of ports; USB-A: one */
        grid-template-columns: 2fr 1fr;
        gap: var(--ha-section-card-gap, 8px);
      }
      ha-card {
        padding: 16px 12px;
        box-sizing: border-box;
        height: 100%;
      }
      .title {
        color: var(--secondary-text-color);
        text-align: center;
        font-size: 1.05em;
        margin-bottom: 12px;
      }
      .ports {
        display: grid;
        gap: 16px 4px;
      }
      .usb-c .ports {
        grid-template-columns: 1fr 1fr;
      }
      .port {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 6px;
        cursor: pointer;
        border-radius: 8px;
        outline: none;
      }
      .port:focus-visible {
        box-shadow: 0 0 0 2px var(--primary-color);
      }
      /* The text centred in a box of its own height (the font's line box
         has more room under the capitals than above them). */
      .label {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 2.6em;
        height: 1.4em;
        padding: 0 6px;
        box-sizing: border-box;
        border-radius: 4px;
        line-height: 1;
        font-weight: 500;
        color: #fff;
        background: var(--anker-port-idle-color);
      }
      /* Exactly: the box trimmed to the capitals, the same padding above and
         below (text-box applies to block containers, not to a flex box). */
      @supports (text-box-trim: trim-both) {
        .label {
          display: inline-block;
          height: auto;
          padding: 0.35em 6px;
          text-align: center;
          text-box: trim-both cap alphabetic;
        }
      }
      .connected .label {
        background: var(--anker-port-active-color);
      }
      .power {
        color: var(--primary-text-color);
        white-space: nowrap;
      }
      .value {
        font-size: 1.6em;
        font-weight: 700;
      }
      .unit {
        font-size: 1.1em;
      }
      .details {
        color: var(--secondary-text-color);
        font-size: 0.95em;
        white-space: nowrap;
      }
    `,
  ];
}

defineOnce("anker-prime-charger-outputs-card", ChargerOutputsCard);
registerCustomCard({
  type: "anker-prime-charger-outputs-card",
  name: "Anker Prime Charger outputs",
  description: "Power, voltage and current of each port, as in the Anker app.",
  preview: true,
});
