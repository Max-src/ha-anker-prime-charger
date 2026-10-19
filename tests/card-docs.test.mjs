// The README gallery generator (tests/card-docs-readme.cjs): markers checked,
// the prose kept, missing images failed or listed.  node --test
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const { updateGalleries, imageFile } = createRequire(import.meta.url)("./card-docs-readme.cjs");

const catalogue = {
  demo: {
    title: "Demo card",
    variations: { a: { title: "First & best" }, b: { title: "Second" } },
    editors: { options: "Options" },
  },
};
const readme = (inner = "", editors = "") =>
  `Intro\n\n<!-- card-docs:demo:variations:start -->${inner}<!-- card-docs:demo:variations:end -->\n` +
  `Middle\n<!-- card-docs:demo:editors:start -->${editors}<!-- card-docs:demo:editors:end -->\nEnd\n`;
const all = () => true;

test("fills the galleries and keeps the prose", () => {
  const out = updateGalleries(readme("old"), catalogue, all);
  assert.match(out, /^Intro\n\n<!-- card-docs:demo:variations:start -->\n<table>/);
  assert.match(out, /<\/table>\n<!-- card-docs:demo:variations:end -->\nMiddle\n/);
  assert.match(out, /images\/cards\/demo-a\.png" alt="Demo card: First &amp; best" width="280"><br>First &amp; best/);
  assert.match(out, /images\/cards\/demo-editor-options\.png/);
  assert.doesNotMatch(out, /old/);
  assert.match(out, /End\n$/);
});

test("is stable: updating twice changes nothing more", () => {
  const once = updateGalleries(readme(), catalogue, all);
  assert.equal(updateGalleries(once, catalogue, all), once);
});

test("keeps Windows line endings", () => {
  const out = updateGalleries(readme().replaceAll("\n", "\r\n"), catalogue, all);
  assert.doesNotMatch(out, /[^\r]\n/);
});

test("fails on missing, duplicate or reversed markers", () => {
  assert.throws(() => updateGalleries("no markers", catalogue, all), /Missing or duplicate gallery start/);
  assert.throws(
    () => updateGalleries(readme() + "<!-- card-docs:demo:variations:start -->", catalogue, all),
    /Missing or duplicate gallery start/,
  );
  const reversed = readme().replace(
    "<!-- card-docs:demo:editors:start --><!-- card-docs:demo:editors:end -->",
    "<!-- card-docs:demo:editors:end --><!-- card-docs:demo:editors:start -->",
  );
  assert.throws(() => updateGalleries(reversed, catalogue, all), /Reversed gallery markers/);
});

test("a missing image fails, or is listed as pending", () => {
  const exists = (file) => file !== imageFile("demo", "variations", "b");
  assert.throws(() => updateGalleries(readme(), catalogue, exists), /Missing screenshot: images\/cards\/demo-b\.png/);
  const pending = [];
  const out = updateGalleries(readme(), catalogue, exists, { pending });
  assert.deepEqual(pending, ["images/cards/demo-b.png"]);
  assert.match(out, /demo-a\.png/);
  assert.doesNotMatch(out, /demo-b\.png/);
});
