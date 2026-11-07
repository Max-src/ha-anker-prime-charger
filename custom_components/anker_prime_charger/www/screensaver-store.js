/**
 * The clock screensavers the 3D card shows, at once on the next page load.
 *
 * A charger's screensaver (anker_prime_charger/screensaver: its kind, name
 * and picture key) and its picture (from the integration, which keeps it)
 * are kept in the browser (IndexedDB), by charger and selected theme: the
 * last one of each charger only. The database is opened when a card first
 * asks (not on dashboards without a 3D card). A card gets the kept one right
 * away, then the integration's: only when that is another picture is the
 * picture fetched again. Cards of the same charger share them, and ask once
 * per page.
 *
 * When the picture can't be fetched, the screensaver is shown without it
 * (the time alone, as charger-screensaver.js draws a picture that didn't
 * come), and asked for again by the next card or on the next page load.
 *
 * The browser may refuse to keep them (private window, no IndexedDB): then
 * they are asked for on every page load, as without this.
 */

const DATABASE = "anker_prime_charger";
const STORE = "screensavers";
const IMAGE_URL = "/api/anker_prime_charger/screensaver_image/";

// "<device id>|<selected theme>" -> {kind, name, image_key, blob}: the
// browser's, read when the first card asks
const kept = new Map();
// "<device id>|<selected theme>" -> {kind, name, image_key, image_url}: shown
const known = new Map();
// "<device id>|<selected theme>" -> Promise of the integration's (once per page)
const asked = new Map();
// "<device id>|<selected theme>" -> Set of callbacks (cards showing it)
const listeners = new Map();

let database; // Promise of the browser's database (undefined: can't keep anything)
let loaded; // Promise: the kept screensavers are read

/** The browser's database, opened on first use. */
function openDatabase() {
  database ??= new Promise((resolve) => {
    try {
      const request = indexedDB.open(DATABASE, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(undefined);
      request.onblocked = () => resolve(undefined);
    } catch {
      resolve(undefined);
    }
  });
  return database;
}

/** Read the kept screensavers (once). */
function loadKept() {
  loaded ??= openDatabase().then(
    (db) =>
      new Promise((resolve) => {
        if (!db) return resolve();
        try {
          const tx = db.transaction(STORE);
          // a failed read: nothing kept, as in a private window
          tx.onerror = tx.onabort = () => resolve();
          const request = tx.objectStore(STORE).openCursor();
          request.onsuccess = () => {
            const cursor = request.result;
            if (!cursor) return resolve();
            kept.set(cursor.key, cursor.value);
            cursor.continue();
          };
        } catch {
          resolve();
        }
      }),
  );
  return loaded;
}

/** The device id part of a key. */
const deviceOf = (key) => key.slice(0, key.indexOf("|"));

/** Keep `value` as the charger's screensaver (its other one is dropped). */
async function store(key, value) {
  const others = [...kept.keys()].filter((other) => other !== key && deviceOf(other) === deviceOf(key));
  for (const other of others) kept.delete(other);
  kept.set(key, value);
  const db = await openDatabase();
  if (!db) return;
  try {
    const tx = db.transaction(STORE, "readwrite");
    // not kept (storage full, say): asked for again next time
    tx.onerror = tx.onabort = () => {};
    const objects = tx.objectStore(STORE);
    for (const other of others) objects.delete(other);
    objects.put(value, key);
  } catch {
    // not kept: asked for again next time
  }
}

/** The screensaver as cards draw it: a kept picture becomes a link. */
function shown({ kind, name, image_key, blob }) {
  return { kind, name, image_key, image_url: blob ? URL.createObjectURL(blob) : null };
}

/** Show `value` for `key` on the cards (the replaced link is freed). */
function publish(key, value) {
  const previous = known.get(key);
  known.set(key, value);
  for (const listener of listeners.get(key) || []) listener(value);
  if (previous?.image_url && previous.image_url !== value.image_url) {
    URL.revokeObjectURL(previous.image_url);
  }
}

/** The kept screensaver of `key`, if there is one and none is shown yet. */
function showKept(key) {
  if (!known.has(key) && kept.get(key)?.kind) publish(key, shown(kept.get(key)));
}

/** The picture of the charger's screensaver, from the integration (undefined: not there). */
async function fetchPicture(hass, deviceId, imageKey) {
  try {
    const response = await hass.fetchWithAuth(IMAGE_URL + encodeURIComponent(deviceId));
    // the theme changed meanwhile: that picture is for another key
    if (!response.ok || response.headers.get("X-Image-Key") !== imageKey) return undefined;
    return await response.blob();
  } catch {
    return undefined; // offline, say
  }
}

/**
 * The integration's screensaver; the picture fetched only when it is new.
 * `missing`: it has a picture that couldn't be fetched (not kept).
 */
async function ask(hass, deviceId, key) {
  const answer = await hass.callWS({ type: "anker_prime_charger/screensaver", device_id: deviceId });
  const value = { kind: answer.kind, name: answer.name, image_key: answer.image_key || null };
  const before = kept.get(key);
  if (value.image_key && value.image_key === before?.image_key && before.blob) {
    value.blob = before.blob;
  } else if (value.image_key) {
    value.blob = await fetchPicture(hass, deviceId, value.image_key);
    if (!value.blob) return { value, missing: true };
  }
  if (value.kind) store(key, value);
  return { value, missing: false };
}

/** Whether the shown screensaver of `key` differs from `value`. */
function differs(key, value, missing) {
  const current = known.get(key);
  // without its picture: shown so, unless a picture of it is shown already
  if (missing) return current?.image_key !== value.image_key || !current?.image_url;
  return current?.kind !== value.kind || current?.image_key !== value.image_key || current?.name !== value.name;
}

/**
 * The screensaver of charger `deviceId` while `theme` (the theme select's
 * state) is selected: `onValue` gets the one known on this page or kept by
 * the browser (at once when there is one), then the integration's when it
 * differs. Returns a function that stops the calls (the card left, or
 * another theme is selected). A failure leaves it as it is (asked again by
 * the next card, or on the next page load).
 */
export function watchScreensaver(hass, deviceId, theme, onValue) {
  const key = `${deviceId}|${theme}`;
  if (!listeners.has(key)) listeners.set(key, new Set());
  listeners.get(key).add(onValue);
  showKept(key);
  if (known.has(key)) onValue(known.get(key));
  if (!asked.has(key)) {
    const done = (async () => {
      await loadKept();
      showKept(key);
      const { value, missing } = await ask(hass, deviceId, key);
      if (differs(key, value, missing)) publish(key, shown(value));
      if (missing) asked.delete(key); // the picture: asked again next time
    })();
    done.catch(() => asked.delete(key));
    asked.set(key, done);
  }
  return () => listeners.get(key)?.delete(onValue);
}
