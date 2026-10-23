/**
 * The clock screensavers the 3D card shows, at once on the next page load.
 *
 * A charger's screensaver (anker_prime_charger/screensaver: its kind, name
 * and picture key) and its picture (from the integration, which keeps it)
 * are kept in the browser (IndexedDB), by charger and selected theme, and
 * read when this module loads. A card gets the kept one right away, then the
 * integration's: only when that is another picture is the picture fetched
 * again. Cards of the same charger share them, and ask once per page.
 *
 * The browser may refuse to keep them (private window, no IndexedDB): then
 * they are asked for on every page load, as without this.
 */

const DATABASE = "anker_prime_charger";
const STORE = "screensavers";
const IMAGE_URL = "/api/anker_prime_charger/screensaver_image/";

// "<device id>|<selected theme>" -> {kind, name, image_key, blob}: the
// browser's, read once when this module loads (before any card needs them)
const kept = new Map();
// "<device id>|<selected theme>" -> {kind, name, image_key, image_url}: shown
const known = new Map();
// "<device id>|<selected theme>" -> Promise of the integration's (once per page)
const asked = new Map();
// "<device id>|<selected theme>" -> Set of callbacks (cards showing it)
const listeners = new Map();

/** The browser's database (undefined if it can't keep anything). */
const database = new Promise((resolve) => {
  try {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(undefined);
  } catch {
    resolve(undefined);
  }
});

const loaded = database.then(
  (db) =>
    new Promise((resolve) => {
      if (!db) return resolve();
      try {
        const request = db.transaction(STORE).objectStore(STORE).openCursor();
        request.onsuccess = () => {
          const cursor = request.result;
          if (!cursor) return resolve();
          kept.set(cursor.key, cursor.value);
          cursor.continue();
        };
        request.onerror = () => resolve();
      } catch {
        resolve();
      }
    }),
);

async function store(key, value) {
  kept.set(key, value);
  const db = await database;
  try {
    db?.transaction(STORE, "readwrite").objectStore(STORE).put(value, key);
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

/** The picture of the charger's screensaver, from the integration. */
async function fetchPicture(hass, deviceId, imageKey) {
  const response = await hass.fetchWithAuth(IMAGE_URL + encodeURIComponent(deviceId));
  // the theme changed meanwhile: that picture is for another key
  if (!response.ok || response.headers.get("X-Image-Key") !== imageKey) return undefined;
  return response.blob();
}

/** The integration's screensaver; the picture fetched only when it is new. */
async function ask(hass, deviceId, key) {
  const answer = await hass.callWS({ type: "anker_prime_charger/screensaver", device_id: deviceId });
  const value = { kind: answer.kind, name: answer.name, image_key: answer.image_key || null };
  const before = kept.get(key);
  if (value.image_key && value.image_key === before?.image_key && before.blob) {
    value.blob = before.blob;
  } else if (value.image_key) {
    value.blob = await fetchPicture(hass, deviceId, value.image_key);
    if (!value.blob) throw Error("The clock picture is not available");
  }
  if (value.kind) store(key, value);
  return value;
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
      await loaded;
      showKept(key);
      const value = await ask(hass, deviceId, key);
      const current = known.get(key);
      if (current?.kind !== value.kind || current?.image_key !== value.image_key || current?.name !== value.name) {
        publish(key, shown(value));
      }
    })();
    done.catch(() => asked.delete(key));
    asked.set(key, done);
  }
  return () => listeners.get(key)?.delete(onValue);
}
