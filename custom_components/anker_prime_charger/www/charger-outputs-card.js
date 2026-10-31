/**
 * Charger outputs card: the power of each port, as the Anker app shows it
 * below the charger: a "USB-C Output" panel (C1-C4) and a "USB-A Output"
 * panel (A1, A2). A port with a device plugged in has a coloured label and
 * shows its power, voltage and current, and on USB-C the device's brand once
 * the charger identifies it; the others show "--". Tapping a port opens its
 * power sensor, its history (`port_history`, on by default); under the mouse,
 * the port is highlighted, as on the 3D card.
 *
 * With `show_switches`, a small on/off button right of each port's label.
 * A1's and A2's are the same switch (the charger switches both USB-A ports
 * together): both show its state, either turns both on or off.
 *
 *   type: custom:anker-prime-charger-outputs-card
 *   device: <the charger's device id>   # optional: the first charger
 *   show_details: true                  # voltage and current (default true)
 *   show_switches: false                # on/off buttons (default false)
 *   port_history: true                  # tap a port: its power history (default true)
 */
import { css, html } from "./lib/lit-all.js";
import { ChargerCard } from "./card-base.js";
import { formatNumber, portStates, readPort } from "./charger.js";
import { defineOnce, registerCustomCard } from "./registration.js";
import { sharedStyles } from "./styles.js";

// Material Design's "power" icon (mdi:power), 24 x 24: drawn here, so that it
// is centred in its button (its box is shifted half a unit: the symbol spans
// y 3-20, so its middle is 11.5)
const POWER_ICON =
  "M16.56,5.44L15.11,6.89C16.84,7.94 18,9.83 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12C6,9.83 " +
  "7.16,7.94 8.88,6.88L7.44,5.44C5.36,6.88 4,9.28 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12C20,9.28 " +
  "18.64,6.88 16.56,5.44M13,3H11V13H13";

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
    {
      name: "show_switches",
      label: "Show on/off buttons",
      helper: "A button next to each port. A1 and A2 share theirs: the charger turns both USB-A ports on or off together.",
      default: false,
      selector: { boolean: {} },
    },
    {
      name: "port_history",
      label: "Tap a port for its history",
      helper: "Tapping a port opens its power history; the port under the mouse is highlighted.",
      default: true,
      selector: { boolean: {} },
    },
  ];

  _watched(hass) {
    return this._charger.ports.flatMap((port) => portStates(hass, port));
  }

  _renderCharger(charger) {
    const ports = charger.ports.map((port) => readPort(this.hass, port));
    const switches = this._config.show_switches === true;
    // the ports each switch turns on or off: "A1 + A2" for the shared one
    const switched = (port) =>
      ports
        .filter((other) => other.switch === port.switch)
        .map((other) => other.label)
        .join(" + ");
    return html`<div class="panels">
      ${PANELS.map(
        (panel) => html`<ha-card class=${panel.usbC ? "usb-c" : "usb-a"}>
          <div class="title">${panel.title}</div>
          <div class="ports">
            ${ports
              .filter((port) => port.usb_c === panel.usbC)
              .map(
                (port) => html`<div class="cell">
                  ${this._renderPort(port)}
                  ${switches ? this._renderSwitch(port, switched(port)) : ""}
                </div>`,
              )}
          </div>
        </ha-card>`,
      )}
    </div>`;
  }

  /** The on/off button of a port's switch (`label`: the port(s) it switches). */
  _renderSwitch(port, label) {
    if (!port.switch) return "";
    const on = port.isOn;
    const unknown = on === null;
    const action = unknown ? `${label}: unknown` : `Turn ${label} ${on ? "off" : "on"}`;
    return html`<button
      class="switch ${on ? "on" : ""}"
      ?disabled=${unknown}
      aria-pressed=${on ? "true" : "false"}
      aria-label=${action}
      title=${action}
      @click=${() => this._switch(port.switch, !on)}
    >
      <svg viewBox="0 -0.5 24 24" aria-hidden="true"><path d=${POWER_ICON} /></svg>
    </button>`;
  }

  /** Turn a switch on or off (Home Assistant shows a failure). */
  _switch(entityId, on) {
    this.hass
      .callService("switch", on ? "turn_on" : "turn_off", { entity_id: entityId })
      .catch(() => {});
  }

  _renderPort(port) {
    const hass = this.hass;
    const details = this._config.show_details !== false;
    const content = html`<span class="label">${port.label}</span>
      <span class="power">
        <span class="value">${formatNumber(hass, port.watts)}</span>
        <span class="unit">W</span>
      </span>
      ${details
        ? html`<span class="details">
            ${formatNumber(hass, port.volts)}V / ${formatNumber(hass, port.amps)}A
          </span>`
        : ""}
      ${port.deviceName ? html`<span class="device">${port.deviceName}</span>` : ""}`;
    const connected = port.isConnected ? "connected" : "";
    if (this._config.port_history === false) {
      return html`<div class="port ${connected}">${content}</div>`;
    }
    return html`<div
      class="port tappable ${connected}"
      role="button"
      tabindex="0"
      aria-label="${port.label}: power history"
      @click=${() => this._showMoreInfo(port.power)}
      @keydown=${(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this._showMoreInfo(port.power);
        }
      }}
    >
      ${content}
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
      /* a port, and its button right of its label (the label stays centred) */
      .cell {
        position: relative;
        display: flex;
        flex-direction: column;
        min-width: 0;
      }
      .switch {
        position: absolute;
        top: calc(0.7em - 11px); /* centred on the label (1.4em high) */
        left: calc(50% + 1.3em + 6px); /* the label is 2.6em wide */
        display: grid;
        place-items: center;
        width: 22px;
        height: 22px;
        padding: 0;
        border: 1px solid var(--divider-color);
        border-radius: 50%;
        box-sizing: border-box;
        background: none;
        color: var(--secondary-text-color);
        cursor: pointer;
      }
      .switch svg {
        display: block;
        width: 14px;
        height: 14px;
        fill: currentColor;
      }
      .switch:not(:disabled):hover {
        border-color: var(--primary-color);
      }
      .switch.on {
        border-color: var(--anker-port-active-color);
        background: var(--anker-port-active-color);
        color: #fff;
      }
      .switch:disabled {
        opacity: 0.5;
        cursor: default;
      }
      .switch:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
      }
      .port {
        position: relative;
        isolation: isolate; /* its highlight stays behind its text */
        display: flex;
        flex-direction: column;
        align-items: center;
        align-self: stretch; /* the whole cell's width: easy to tap */
        gap: 6px;
        border-radius: 8px;
        outline: none;
      }
      .port.tappable {
        cursor: pointer;
      }
      /* What a tap opens: a tint around the port (a little beyond its text),
         under the mouse or focused from the keyboard. As on the 3D card. */
      .port.tappable::before {
        content: "";
        position: absolute;
        inset: -6px -2px;
        z-index: -1;
        border-radius: 10px;
        pointer-events: none;
      }
      @media (hover: hover) {
        .port.tappable:hover::before {
          background: color-mix(in srgb, var(--primary-color) 12%, transparent);
          box-shadow: inset 0 0 0 1px var(--primary-color);
        }
      }
      .port.tappable:focus-visible::before {
        box-shadow: inset 0 0 0 2px var(--primary-color);
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
      .device {
        color: var(--secondary-text-color);
        font-size: 0.85em;
        max-width: 100%;
        overflow: hidden;
        text-overflow: ellipsis;
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
