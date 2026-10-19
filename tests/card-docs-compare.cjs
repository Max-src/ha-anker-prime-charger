/**
 * How documentation captures are compared (tests/card-docs.cjs).
 *
 * Two captures "match" when they have the same size, no pixel differs by more
 * than CHANNEL_TOLERANCE in any channel, and at most NOISE_FRACTION of the
 * pixels differ at all. Not an exact byte comparison on purpose: Chromium's
 * software rasterizer isn't bit-exact between processes on anti-aliased edges
 * (rounded corners, the 3D model's slanted faces, scaled glyphs), which moves
 * a few edge pixels by a few levels. Real non-determinism (a font not loaded,
 * an element at another phase, a layout shift) moves pixels by far more, or
 * touches far more of them, so it still shows. If a capture fails with small
 * deltas only, look at the diff image (test-results/card-docs/) before
 * raising the limits.
 */
const { PNG } = require("pngjs");

const CHANNEL_TOLERANCE = 24;
const NOISE_FRACTION = 0.005;

const sameSize = (a, b) => a.width === b.width && a.height === b.height;

/** The largest channel delta of a pixel of two same-size images. */
function pixelDelta(a, b, offset) {
  let delta = 0;
  for (let channel = 0; channel < 4; channel++) {
    delta = Math.max(delta, Math.abs(a.data[offset + channel] - b.data[offset + channel]));
  }
  return delta;
}

/** How many pixels differ by more than `tolerance`, and the largest delta. */
function differences(a, b, tolerance) {
  let count = 0;
  let maxDelta = 0;
  for (let offset = 0; offset < a.data.length; offset += 4) {
    const delta = pixelDelta(a, b, offset);
    maxDelta = Math.max(maxDelta, delta);
    if (delta > tolerance) count++;
  }
  return { count, maxDelta };
}

/** Whether two decoded PNGs show the same thing (rendering noise aside). */
function imagesMatch(a, b) {
  return (
    sameSize(a, b) &&
    differences(a, b, CHANNEL_TOLERANCE).count === 0 &&
    differences(a, b, 0).count <= a.width * a.height * NOISE_FRACTION
  );
}

/** The first of `pngs` that matches another one, or undefined. */
function matchingCapture(pngs) {
  return pngs.find((png, i) => pngs.slice(i + 1).some((other) => imagesMatch(png, other)));
}

/** How two captures differ, for the log. */
function describeDifference(a, b) {
  if (!sameSize(a, b)) return `size ${a.width}x${a.height} vs ${b.width}x${b.height}`;
  const real = differences(a, b, CHANNEL_TOLERANCE);
  const any = differences(a, b, 0);
  return (
    `${real.count} pixels differ by more than ${CHANNEL_TOLERANCE}; ` +
    `${any.count} differ at all (max channel delta ${any.maxDelta})`
  );
}

/** A diff image: real differences magenta, rendering noise yellow, the rest
 * faded; blank where the sizes differ. */
function diffImage(a, b) {
  const diff = new PNG({ width: a.width, height: a.height });
  if (!sameSize(a, b)) return diff;
  for (let offset = 0; offset < a.data.length; offset += 4) {
    const delta = pixelDelta(a, b, offset);
    const grey = 160 + Math.round((a.data[offset] + a.data[offset + 1] + a.data[offset + 2]) / 8);
    const colour = delta > CHANNEL_TOLERANCE ? [255, 0, 255] : delta ? [255, 220, 0] : [grey, grey, grey];
    diff.data.set([...colour, 255], offset);
  }
  return diff;
}

module.exports = { CHANNEL_TOLERANCE, NOISE_FRACTION, imagesMatch, matchingCapture, describeDifference, diffImage };
