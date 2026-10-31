/**
 * What the cards know of a charger, and how they read its ports.
 *
 * The integration answers the websocket command anker_prime_charger/charger
 * with the charger's ports (C1-C4, A1, A2) and, for each, the entity ids of
 * its readings, found by unique id (frontend.py). The answer is kept per
 * entity registry: Home Assistant replaces hass.entities when an entity is
 * added, removed or renamed, and the next read asks again.
 */

export const DOMAIN = "anker_prime_charger";
// The charger's device in the device registry (the device picker's filter)
export const MODEL_NAME = "Prime Charger 250W";

// hass.entities -> Map(device id or "" for the first charger -> Promise)
const answers = new WeakMap();
const NO_ENTITIES = {}; // hass.entities before Home Assistant sent it

/**
 * The charger of `deviceId` (or the first one set up when empty):
 * {device_id, name, model, total_power, ports: [{id, label, usb_c,
 * connected, power, voltage, current, switch, device}]} (`switch`: the
 * port's on/off switch, the same one for A1 and A2). Rejects with the integration's
 * message (e.g. "Charger not found").
 */
export function loadCharger(hass, deviceId = "") {
  const registry = hass.entities || NO_ENTITIES;
  let byDevice = answers.get(registry);
  if (!byDevice) {
    byDevice = new Map();
    answers.set(registry, byDevice);
  }
  if (!byDevice.has(deviceId)) {
    const message = { type: `${DOMAIN}/charger` };
    if (deviceId) message.device_id = deviceId;
    const answer = hass.callWS(message);
    // a failed request is asked again next time
    answer.catch(() => byDevice.delete(deviceId));
    byDevice.set(deviceId, answer);
  }
  return byDevice.get(deviceId);
}

/** The state objects a port shows (for change detection). */
export function portStates(hass, port) {
  return [port.connected, port.power, port.voltage, port.current, port.device, port.switch].map(
    (entityId) => (entityId ? hass.states[entityId] : undefined),
  );
}

function number(state) {
  const value = Number(state?.state);
  return state && state.state !== "" && Number.isFinite(value) ? value : null;
}

/**
 * A port as the cards show it: whether a device is plugged in (connected:
 * true / false, null when unknown), its readings (numbers, null when
 * unknown), the device's brand as the charger identifies it (USB-C; null
 * when unknown) and whether the port is switched on (isOn: true / false, null
 * when unknown). Readings of a port without a device are not shown (null).
 */
export function readPort(hass, port) {
  const status = port.connected ? hass.states[port.connected]?.state : undefined;
  const connected = status === "on" ? true : status === "off" ? false : null;
  const reading = (entityId) =>
    connected && entityId ? number(hass.states[entityId]) : null;
  const device = port.device ? hass.states[port.device]?.state : undefined;
  const switched = port.switch ? hass.states[port.switch]?.state : undefined;
  return {
    ...port,
    isConnected: connected,
    watts: reading(port.power),
    volts: reading(port.voltage),
    amps: reading(port.current),
    deviceName:
      connected && device && !["unknown", "unavailable"].includes(device) ? device : null,
    isOn: switched === "on" ? true : switched === "off" ? false : null,
  };
}

/**
 * What the 3D card shows of the charger: whether the charger is offline
 * (none of its ports reports), the ids of the ports a device is plugged into,
 * the total output ("12.6 W") and each port's power ({c1: "7.2W"}, the ports
 * in use), as its power page shows them.
 */
export function chargerSummary(hass, charger) {
  const ports = charger.ports.map((port) => readPort(hass, port));
  const offline = ports.every((port) => port.isConnected === null);
  const total = Number(hass.states[charger.total_power]?.state);
  return {
    offline,
    inUse: new Set(ports.filter((port) => port.isConnected).map((port) => port.id)),
    total: offline || !Number.isFinite(total) ? "--" : `${formatNumber(hass, total)} W`,
    portPower: Object.fromEntries(
      ports
        .filter((port) => port.isConnected && port.watts !== null)
        .map((port) => [port.id, `${formatNumber(hass, port.watts)}W`]),
    ),
  };
}

/** The state objects chargerSummary reads (for change detection). */
export function summaryStates(hass, charger) {
  return [
    hass.states[charger.total_power],
    ...charger.ports.flatMap((port) => [hass.states[port.connected], hass.states[port.power]]),
  ];
}

// The user's number format (profile setting) -> the locale formatting it
const NUMBER_LOCALES = {
  comma_decimal: "en-US", // 1,234.5
  decimal_comma: "de", // 1.234,5
  space_comma: "fr", // 1 234,5
  none: "en-US",
};

function numberLocale(hass) {
  const format = hass.locale?.number_format;
  if (format === "system") return undefined; // the browser's
  return NUMBER_LOCALES[format] || hass.locale?.language || hass.language;
}

/** `value` with `digits` decimals in the user's number format, or "--". */
export function formatNumber(hass, value, digits = 1) {
  if (value === null || value === undefined) return "--";
  return new Intl.NumberFormat(numberLocale(hass), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    useGrouping: hass.locale?.number_format !== "none",
  }).format(value);
}
