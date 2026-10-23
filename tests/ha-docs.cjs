/**
 * Captures the README's screenshots of Home Assistant's own pages for the
 * charger (docs/DOCUMENTATION_SCREENSHOTS.md): npm run docs:pages
 *
 * Unlike the cards' (card-docs.cjs), these show the real integration: run it
 * against your own Home Assistant with a charger set up (DOCS_HA_URL, and
 * DOCS_HA_TOKEN: a long-lived access token). Nothing there is changed: pages
 * are opened, a list opened by clicking, and the actions page filled through
 * the browser's storage of this run only.
 *
 * What identifies the charger (its serial number, Wi-Fi and Bluetooth
 * addresses, device and config entry ids) is replaced on the page before
 * each capture, and a capture still showing any of it is refused. The values
 * themselves (power, energy, settings) are the charger's at that moment.
 * DOCS_FILTER keeps the images whose name contains it.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const IMAGES = path.join(root, "images", "pages");
const origin = new URL(process.env.DOCS_HA_URL || "http://127.0.0.1:8123").origin;
const DOMAIN = "anker_prime_charger";
const PAGE_TIMEOUT = 90000;
const SETTLE = 2500; // ms for a page's cards and charts to finish drawing
const PADDING = 16; // px around what is captured
const LIST_PADDING = 6; // px above and below an open list
const WIDTH = 1280; // the window: wide, for a page's columns
// A narrow window: a device's entity cards in one wide column (no names cut short)
const NARROW = 620;
const HEIGHT = 3200; // tall: Home Assistant scrolls its own container, not the page

// What replaces the charger's own identifiers in the images (as in the README)
const PLACEHOLDERS = {
  serial: "ASHV911G00000001",
  mac: "AA:BB:CC:DD:EE:01",
  bluetooth: "AA:BB:CC:DD:EE:02",
  device: "0123456789abcdef0123456789abcdef",
};

// --- What is captured -------------------------------------------------------------

/** Every image: its name, the page and what of it is captured. */
const SHOTS = [
  {
    name: "integration",
    title: "The integration's page: the charger and its port and Screen devices",
    url: () => `/config/integrations/integration/${DOMAIN}`,
    // the header (logo, version) down to the devices
    area: (page) => union(page, ["ha-config-integration-page .header", "ha-config-integration-page ha-config-entry-row"]),
  },
  {
    name: "charger-device",
    title: "The charger's device page",
    url: (devices) => `/config/devices/device/${devices.charger.id}`,
    area: async (page) => {
      await hide(page, "ha-config-device-page ha-card:has-text('Related')");
      return union(page, [
        "ha-device-info-card",
        "ha-config-device-page ha-card:has-text('Sub-devices')",
        "ha-device-entities-card",
      ]);
    },
  },
  {
    name: "port-device",
    title: "A USB-C port's device page",
    url: (devices) => `/config/devices/device/${devices.usbc_1.id}`,
    width: NARROW,
    area: (page) => union(page, ["ha-device-entities-card"]),
  },
  {
    name: "screen-device",
    title: "The Screen device page",
    url: (devices) => `/config/devices/device/${devices.screen.id}`,
    width: NARROW,
    area: (page) => union(page, ["ha-device-entities-card"]),
  },
  {
    name: "clock-theme",
    title: "Choosing a clock theme",
    url: (devices) => `/config/devices/device/${devices.screen.id}`,
    area: (page) => openList(page, "Clock theme"),
  },
  {
    name: "charging-mode",
    title: "The charging modes, with the custom profiles",
    url: (devices) => `/config/devices/device/${devices.charger.id}`,
    area: (page) => openList(page, "Charging mode"),
  },
  {
    name: "set-custom-settings",
    title: "The Set custom settings action",
    url: () => "/developer-tools/action",
    // the action, as the README's example (the actions page keeps it in the browser)
    storage: {
      "panel-dev-action-state-yaml-mode": "true",
      "panel-dev-action-state-service-data": JSON.stringify({
        action: `${DOMAIN}.set_custom_settings`,
        target: { device_id: PLACEHOLDERS.device },
        data: { c1_power: 15, c3_power: 45, c3_protocols: ["xiaomi"] },
      }),
    },
    area: async (page) => {
      // its parameters shown (the panel remembers whether it was open)
      const panel = page.locator("tools-action ha-expansion-panel");
      if (!(await panel.evaluate((el) => el.expanded))) {
        await page.getByText("All available parameters").click();
        await page.waitForTimeout(800);
      }
      return union(page, ["tools-action ha-card", "tools-action ha-expansion-panel"]);
    },
  },
];

/** The box around the first match of each selector (all matches of the last
 * kind: the cards of a column), padded; in page coordinates. */
async function union(page, selectors) {
  const boxes = [];
  for (const selector of selectors) {
    const matches = page.locator(selector);
    const count = await matches.count();
    assert.ok(count, `Nothing matches ${selector}: Home Assistant's page changed, update tests/ha-docs.cjs`);
    for (let i = 0; i < count; i++) {
      const box = await matches.nth(i).boundingBox();
      if (box && box.width && box.height) boxes.push(box);
    }
  }
  const scroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
  const left = Math.min(...boxes.map((b) => b.x)) - PADDING;
  const top = Math.min(...boxes.map((b) => b.y)) - PADDING;
  const right = Math.max(...boxes.map((b) => b.x + b.width)) + PADDING;
  const bottom = Math.max(...boxes.map((b) => b.y + b.height)) + PADDING;
  return { x: left + scroll.x, y: top + scroll.y, width: right - left, height: bottom - top };
}

/** Leave out what matches `selector` (the last card of a column: nothing
 * else moves; Home Assistant fades cards in, so it is not just made invisible). */
async function hide(page, selector) {
  const matches = page.locator(selector);
  for (let i = 0; i < (await matches.count()); i++) {
    await matches.nth(i).evaluate((el) => el.style.setProperty("display", "none", "important"));
  }
}

/** Open the list of the select labelled `label`: the select and its list. */
async function openList(page, label) {
  const select = page.locator("ha-select").filter({ hasText: label }).first();
  // near the top of the window, so its list opens downwards
  await select.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.waitForTimeout(300);
  await select.click();
  const menu = select.locator("ha-dropdown [role=menu]");
  await menu.waitFor({ state: "visible" });
  await page.waitForTimeout(800); // its opening animation
  const [a, b] = [await select.boundingBox(), await menu.boundingBox()];
  // sideways, the list's own edges: the page around it is not wanted
  const top = Math.min(a.y, b.y) - LIST_PADDING;
  const scroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
  return {
    x: b.x + scroll.x,
    y: top + scroll.y,
    width: b.width,
    height: Math.max(a.y + a.height, b.y + b.height) + LIST_PADDING - top,
  };
}

// --- The charger, and what identifies it ---------------------------------------------

/** The charger's devices (charger, screen, usbc_1 ...) and what to replace. */
async function charger(page) {
  const { devices, entries } = await page.evaluate(async (domain) => {
    const hass = document.querySelector("home-assistant").hass;
    const devices = await hass.callWS({ type: "config/device_registry/list" });
    const entries = await hass.callWS({ type: "config_entries/get", domain });
    return { devices: devices.filter((d) => d.identifiers.some(([d0]) => d0 === domain)), entries };
  }, DOMAIN);
  const main = devices.find((d) => !d.via_device_id);
  assert.ok(main, "No charger in this Home Assistant: set up the integration first");
  const serial = main.identifiers.find(([d0]) => d0 === DOMAIN)[1];
  const found = { charger: main };
  for (const device of devices) {
    const [, id] = device.identifiers.find(([d0]) => d0 === DOMAIN);
    if (id.startsWith(`${serial}_`)) found[id.slice(serial.length + 1)] = device;
  }
  for (const key of ["screen", "usbc_1"]) assert.ok(found[key], `The charger has no ${key} device`);

  // longest first: a serial inside an id is replaced with the id
  const replacements = [[serial, PLACEHOLDERS.serial]];
  for (const [kind, value] of main.connections) {
    const placeholder = kind === "bluetooth" ? PLACEHOLDERS.bluetooth : PLACEHOLDERS.mac;
    replacements.push([value.toUpperCase(), placeholder], [value.toLowerCase(), placeholder.toLowerCase()]);
  }
  for (const device of devices) replacements.push([device.id, PLACEHOLDERS.device]);
  for (const entry of entries) replacements.push([entry.entry_id, PLACEHOLDERS.device]);
  return { devices: found, replacements };
}

/** Replace `replacements` everywhere on the page (text, fields, links, titles);
 * the ones still found after (none, normally). */
function redact(page, replacements) {
  return page.evaluate((replacements) => {
    const swap = (text) => replacements.reduce((t, [from, to]) => t.split(from).join(to), text);
    const visit = (root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = swap(node.nodeValue);
        if (text !== node.nodeValue) node.nodeValue = text;
      }
      for (const el of root.querySelectorAll("*")) {
        for (const name of ["href", "title", "aria-label", "value"]) {
          const value = el.getAttribute(name);
          if (value && swap(value) !== value) el.setAttribute(name, swap(value));
        }
        if (typeof el.value === "string" && swap(el.value) !== el.value) el.value = swap(el.value);
        if (el.shadowRoot) visit(el.shadowRoot);
      }
    };
    visit(document);
    // what is left: in the text of the whole page, through its shadow roots
    const texts = [];
    const collect = (root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) texts.push(node.nodeValue);
      for (const el of root.querySelectorAll("*")) {
        if (typeof el.value === "string") texts.push(el.value);
        if (el.shadowRoot) collect(el.shadowRoot);
      }
    };
    collect(document);
    const all = texts.join("\n");
    return replacements.map(([from]) => from).filter((from) => all.includes(from));
  }, replacements);
}

// --- Capturing ------------------------------------------------------------------------

function storageState(token, extra = {}) {
  const tokens = {
    access_token: token,
    token_type: "Bearer",
    expires_in: 10 * 365 * 24 * 3600,
    hassUrl: origin,
    clientId: `${origin}/`,
    expires: Date.now() + 10 * 365 * 24 * 3600 * 1000,
  };
  const localStorage = {
    hassTokens: JSON.stringify(tokens),
    // Home Assistant's default theme, light, whatever the user's profile says
    selectedTheme: JSON.stringify({ theme: "default", dark: false }),
    ...extra,
  };
  return {
    cookies: [],
    origins: [{ origin, localStorage: Object.entries(localStorage).map(([name, value]) => ({ name, value })) }],
  };
}

async function open(browser, token, url, storage, width = WIDTH) {
  const context = await browser.newContext({
    storageState: storageState(token, storage),
    viewport: { width, height: HEIGHT },
    deviceScaleFactor: 2,
    locale: "en-GB",
    colorScheme: "light",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(PAGE_TIMEOUT);
  await page.goto(origin + url);
  await page.waitForFunction(() => document.querySelector("home-assistant")?.hass?.connected);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(SETTLE);
  return { context, page };
}

async function main() {
  const token = process.env.DOCS_HA_TOKEN;
  assert.ok(token, "Set DOCS_HA_URL and DOCS_HA_TOKEN (a long-lived access token) of a Home Assistant with a charger");
  const filter = process.env.DOCS_FILTER;
  const shots = SHOTS.filter((shot) => !filter || shot.name.includes(filter));
  assert.ok(shots.length, "No image matches DOCS_FILTER");
  fs.mkdirSync(IMAGES, { recursive: true });

  const browser = await chromium.launch({ args: ["--force-color-profile=srgb", "--font-render-hinting=none"] });
  const failed = [];
  try {
    const first = await open(browser, token, "/config/integrations/dashboard");
    const { devices, replacements } = await charger(first.page);
    await first.context.close();
    for (const shot of shots) {
      const file = path.join(IMAGES, `${shot.name}.png`);
      console.log(`${path.relative(root, file)}: ${shot.title}`);
      const { context, page } = await open(browser, token, shot.url(devices), shot.storage, shot.width);
      try {
        const clip = await shot.area(page);
        const left = await redact(page, replacements);
        assert.deepEqual(left, [], "The charger's identifiers are still shown: not captured");
        await page.screenshot({ path: file, clip, type: "png" });
      } catch (error) {
        console.warn(`  not captured: ${error.message.split("\n")[0]}`);
        failed.push(shot.name);
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  console.log(`\nHome Assistant pages: ${shots.length - failed.length} captured${failed.length ? `, failed: ${failed.join(", ")}` : ""}`);
  if (failed.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
