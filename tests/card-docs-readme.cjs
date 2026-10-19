/**
 * The README's screenshot galleries, from tests/card-docs-catalogue.json
 * (docs/DOCUMENTATION_SCREENSHOTS.md).
 *
 * Only what is between a card's gallery markers is replaced:
 *
 *   <!-- card-docs:<kind>:variations:start --> ... <!-- card-docs:<kind>:variations:end -->
 *   <!-- card-docs:<kind>:editors:start -->    ... <!-- card-docs:<kind>:editors:end -->
 *
 * The prose around them is never touched. Missing, duplicate or reversed
 * markers fail. Run without arguments to update the README, with --check to
 * fail when it is stale (a scenario not captured yet is listed, not failed:
 * the Documentation Screenshots workflow captures it).
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const catalogue = require("./card-docs-catalogue.json");
// Absolute links: HACS shows the README from GitHub, where relative ones break
const IMAGE_URL = "https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/";
const COLUMNS = 3;
const WIDTH = 280;

const escape = (text) =>
  String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/** The image file of a catalogue entry, relative to the repository. */
function imageFile(kind, group, name) {
  return `images/cards/${kind}-${group === "editors" ? "editor-" : ""}${name}.png`;
}

/**
 * `source` (the README) with its galleries rebuilt. `exists(file)` says
 * whether an image is there; with `pending` (an array), missing images are
 * listed in it and left out instead of failing.
 */
function updateGalleries(source, definitions = catalogue, exists = (f) => fs.existsSync(path.join(root, f)), { pending } = {}) {
  const newline = source.includes("\r\n") ? "\r\n" : "\n";
  for (const [kind, definition] of Object.entries(definitions)) {
    for (const group of ["variations", "editors"]) {
      const entries = Object.entries(definition[group] || {});
      if (!entries.length) continue;
      const start = `<!-- card-docs:${kind}:${group}:start -->`;
      const end = `<!-- card-docs:${kind}:${group}:end -->`;
      assert.equal(source.split(start).length, 2, `Missing or duplicate gallery start: ${kind}/${group}`);
      assert.equal(source.split(end).length, 2, `Missing or duplicate gallery end: ${kind}/${group}`);
      const begin = source.indexOf(start) + start.length;
      const finish = source.indexOf(end);
      assert.ok(finish >= begin, `Reversed gallery markers: ${kind}/${group}`);
      const cells = entries.flatMap(([name, options]) => {
        const file = imageFile(kind, group, name);
        if (pending && !exists(file)) {
          pending.push(file);
          return [];
        }
        assert.ok(exists(file), `Missing screenshot: ${file}`);
        const title = typeof options === "string" ? options : options.title;
        const alt = escape(`${definition.title}: ${title}`);
        return [`    <td valign="top"><img src="${IMAGE_URL}${file}" alt="${alt}" width="${WIDTH}"><br>${escape(title)}</td>`];
      });
      const rows = [];
      for (let i = 0; i < cells.length; i += COLUMNS) rows.push("  <tr>", ...cells.slice(i, i + COLUMNS), "  </tr>");
      const table = cells.length ? ["", "<table>", ...rows, "</table>", ""] : ["", ""];
      source = source.slice(0, begin) + table.join(newline) + source.slice(finish);
    }
  }
  return source;
}

if (require.main === module) {
  const file = path.join(root, "README.md");
  const before = fs.readFileSync(file, "utf8");
  const check = process.argv.includes("--check");
  const pending = check ? [] : undefined;
  const after = updateGalleries(before, catalogue, undefined, { pending });
  if (check) {
    assert.equal(after, before, "The README's galleries are stale: run npm run docs:readme");
    for (const image of pending) console.log(`pending capture (Documentation Screenshots workflow): ${image}`);
  } else if (after !== before) {
    fs.writeFileSync(file, after);
    console.log("README galleries updated");
  }
}

module.exports = { updateGalleries, imageFile };
