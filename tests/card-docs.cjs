/**
 * Captures the dashboard cards' documentation screenshots
 * (docs/DOCUMENTATION_SCREENSHOTS.md): npm run docs:screenshots
 *
 * Every image of tests/card-docs-catalogue.json is rendered in the real Home
 * Assistant frontend at DOCS_HA_URL (its fonts, theme and elements) with
 * synthetic charger state (tests/card-docs-browser.js); the cards' files are
 * served from this checkout, so that Home Assistant needs neither the
 * integration nor a charger. Logged in with DOCS_HA_TOKEN (a long-lived
 * access token) or, for a fresh disposable Home Assistant on localhost, by
 * onboarding it (DOCS_HA_ONBOARD=1). DOCS_FILTER keeps the images whose name
 * contains it.
 *
 * Each image is captured in fresh browser contexts until two captures match
 * (tests/card-docs-compare.cjs: equal but for rendering noise): normally
 * twice, a third time when the first two differ. A verified image is written
 * only when it differs from the committed one, so a run never commits noise.
 * An image that can't be verified keeps its committed version and is
 * reported, its captures and a diff saved in test-results/card-docs/. The
 * run fails only when nothing at all could be captured.
 */
const assert = require("node:assert/strict");
const { randomBytes } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { chromium, request } = require("playwright");
const { PNG } = require("pngjs");
const { describeDifference, diffImage, imagesMatch, matchingCapture } = require("./card-docs-compare.cjs");
const catalogue = require("./card-docs-catalogue.json");
const { imageFile } = require("./card-docs-readme.cjs");

const root = path.resolve(__dirname, "..");
const WWW = path.join(root, "custom_components", "anker_prime_charger", "www");
const DIAGNOSTICS = path.join(root, "test-results", "card-docs");
const origin = new URL(process.env.DOCS_HA_URL || "http://127.0.0.1:8123").origin;
const CLIENT_ID = `${origin}/`;
const PAGE_TIMEOUT = 90000;

/** Every image to capture: its file and how to render it. */
function images() {
  const list = [];
  for (const [kind, definition] of Object.entries(catalogue)) {
    for (const group of ["variations", "editors"]) {
      for (const [name, options] of Object.entries(definition[group] || {})) {
        const scenario = typeof options === "string" ? { title: options } : options;
        list.push({ file: imageFile(kind, group, name), kind, element: definition.element, group, scenario });
      }
    }
  }
  const filter = process.env.DOCS_FILTER;
  return filter ? list.filter((image) => path.basename(image.file).includes(filter)) : list;
}

// --- Logging in ---------------------------------------------------------------

/** A browser storage state logged in with `tokens` (as the frontend keeps them). */
function storageState(tokens) {
  const value = { ...tokens, hassUrl: origin, clientId: CLIENT_ID, expires: Date.now() + tokens.expires_in * 1000 };
  return { cookies: [], origins: [{ origin, localStorage: [{ name: "hassTokens", value: JSON.stringify(value) }] }] };
}

/** Onboard a fresh disposable Home Assistant (localhost only): its tokens. */
async function onboard() {
  assert.ok(
    ["127.0.0.1", "localhost", "[::1]"].includes(new URL(origin).hostname),
    "Onboarding is only for a disposable Home Assistant on localhost",
  );
  const api = await request.newContext({ baseURL: origin });
  try {
    const user = await api.post("/api/onboarding/users", {
      data: { client_id: CLIENT_ID, name: "Documentation", username: "docs", password: randomBytes(24).toString("hex"), language: "en" },
    });
    assert.ok(user.ok(), "Onboarding failed: is this Home Assistant fresh (not onboarded yet)?");
    const { auth_code: code } = await user.json();
    const token = await api.post("/auth/token", { form: { grant_type: "authorization_code", code, client_id: CLIENT_ID } });
    assert.ok(token.ok(), "Onboarding failed: no tokens");
    const tokens = await token.json();
    const headers = { Authorization: `Bearer ${tokens.access_token}` };
    for (const step of ["core_config", "analytics", "integration"]) {
      const data = step === "integration" ? { client_id: CLIENT_ID, redirect_uri: CLIENT_ID } : {};
      const result = await api.post(`/api/onboarding/${step}`, { headers, data });
      assert.ok(result.ok(), `Onboarding step failed: ${step}`);
    }
    return tokens;
  } finally {
    await api.dispose();
  }
}

async function login() {
  if (process.env.DOCS_HA_TOKEN) {
    const tenYears = 10 * 365 * 24 * 3600;
    return storageState({ access_token: process.env.DOCS_HA_TOKEN, token_type: "Bearer", expires_in: tenYears });
  }
  assert.ok(process.env.DOCS_HA_ONBOARD === "1", "Set DOCS_HA_TOKEN (a long-lived access token), or DOCS_HA_ONBOARD=1 for a fresh disposable localhost Home Assistant");
  return storageState(await onboard());
}

// --- Capturing ------------------------------------------------------------------

/** Serve the cards' files from this checkout, whatever that Home Assistant has. */
async function serveCards(context) {
  await context.route("**/anker_prime_charger/**", async (route) => {
    const relative = decodeURIComponent(new URL(route.request().url()).pathname).replace(/^\/anker_prime_charger\//, "");
    const file = path.resolve(WWW, relative);
    if (!file.startsWith(WWW + path.sep) || !fs.existsSync(file)) return route.fulfill({ status: 404 });
    await route.fulfill({ path: file, contentType: "text/javascript" });
  });
}

/** One capture of an image, in a fresh context: its PNG. */
async function capture(browser, state, image) {
  const context = await browser.newContext({
    storageState: state,
    viewport: { width: 1280, height: 1400 },
    deviceScaleFactor: 2,
    locale: "en-GB",
    timezoneId: "UTC",
    colorScheme: image.scenario.dark ? "dark" : "light",
    reducedMotion: "reduce",
  });
  try {
    await serveCards(context);
    const page = await context.newPage();
    page.setDefaultTimeout(PAGE_TIMEOUT);
    await page.goto(`${origin}/lovelace/0`);
    await page.waitForFunction(
      () => document.querySelector("home-assistant")?.hass?.connected && customElements.get("ha-card") && typeof window.loadCardHelpers === "function",
    );
    await page.addScriptTag({ type: "module", url: `${origin}/anker_prime_charger/cards.js` });
    await page.waitForFunction((element) => !!customElements.get(element), image.element);
    await page.addScriptTag({ path: path.join(__dirname, "card-docs-browser.js") });
    await page.evaluate((image) => window.cardDocs.mount(image), image);
    return await page.locator("#card-docs").screenshot({ type: "png" });
  } finally {
    await context.close();
  }
}

/** The image's verified capture ({buffer, png}), or the reason there is none. */
async function verify(browser, state, image) {
  const captures = [];
  let wanted = 2;
  for (let pass = 0; pass < wanted; pass++) {
    const buffer = await capture(browser, state, image);
    captures.push({ buffer, png: PNG.sync.read(buffer) });
    if (pass === 1 && !imagesMatch(captures[0].png, captures[1].png)) {
      console.warn(`  ${image.file}: two captures differ (${describeDifference(captures[0].png, captures[1].png)}), capturing a third`);
      wanted = 3;
    }
  }
  const verified = matchingCapture(captures.map((c) => c.png));
  if (verified) return { capture: captures.find((c) => c.png === verified) };
  fs.mkdirSync(DIAGNOSTICS, { recursive: true });
  const base = path.join(DIAGNOSTICS, path.basename(image.file, ".png"));
  captures.forEach((c, i) => fs.writeFileSync(`${base}-${i + 1}.png`, c.buffer));
  fs.writeFileSync(`${base}-diff.png`, PNG.sync.write(diffImage(captures[0].png, captures[1].png)));
  return { reason: `${captures.length} captures all differ (${describeDifference(captures[0].png, captures[1].png)}); see ${path.relative(root, base)}-*.png` };
}

async function main() {
  const list = images();
  assert.ok(list.length, "No image matches DOCS_FILTER");
  const state = await login();
  const browser = await chromium.launch({
    args: ["--disable-gpu", "--disable-lcd-text", "--force-color-profile=srgb", "--font-render-hinting=none"],
  });
  const outcome = { written: [], unchanged: [], kept: [] };
  try {
    for (const image of list) {
      console.log(`${image.file}: ${image.scenario.title}`);
      let result;
      try {
        result = await verify(browser, state, image);
      } catch (error) {
        result = { reason: error.message.split("\n")[0] };
      }
      if (!result.capture) {
        console.warn(`  kept the committed image: ${result.reason}`);
        outcome.kept.push(`${image.file}: ${result.reason}`);
        continue;
      }
      const file = path.join(root, image.file);
      if (fs.existsSync(file) && imagesMatch(PNG.sync.read(fs.readFileSync(file)), result.capture.png)) {
        outcome.unchanged.push(image.file);
        continue;
      }
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, result.capture.buffer);
      console.log("  written");
      outcome.written.push(image.file);
    }
  } finally {
    await browser.close();
  }
  report(outcome);
  assert.ok(outcome.written.length + outcome.unchanged.length, "Nothing could be captured");
}

function report({ written, unchanged, kept }) {
  const lines = [
    `Documentation screenshots: ${written.length} written, ${unchanged.length} unchanged, ${kept.length} kept as committed`,
    ...written.map((file) => `- written: ${file}`),
    ...kept.map((entry) => `- kept (not verified): ${entry}`),
  ];
  console.log(`\n${lines.join("\n")}`);
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${lines.join("\n")}\n`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
