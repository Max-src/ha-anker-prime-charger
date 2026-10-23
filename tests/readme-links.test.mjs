// The documentation's links to files of this repository (images, docs, the
// license) point to files that exist, so a moved or deleted one fails here.
// node --test
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RAW = "https://raw.githubusercontent.com/Max-src/ha-anker-prime-charger/main/";
const DOCUMENTS = ["README.md", "CHANGELOG.md", "docs/DEVELOPMENT.md", "docs/DOCUMENTATION_SCREENSHOTS.md", "docs/PROTOCOL.md"];

/** The repository files a Markdown document links to (relative to the root). */
function linkedFiles(document) {
  const text = fs.readFileSync(path.join(root, document), "utf8");
  const files = [];
  for (const [, url] of text.matchAll(/src="([^"]+)"/g)) {
    if (url.startsWith(RAW)) files.push(url.slice(RAW.length));
  }
  for (const [, url] of text.matchAll(/\]\(([^)\s]+)\)/g)) {
    if (/^(https?:|mailto:|#)/.test(url)) continue;
    files.push(path.posix.join(path.posix.dirname(document), url.split("#")[0]));
  }
  return files;
}

for (const document of DOCUMENTS) {
  test(`${document}: every linked file exists`, () => {
    const missing = linkedFiles(document).filter((file) => !fs.existsSync(path.join(root, file)));
    assert.deepEqual(missing, []);
  });
}
