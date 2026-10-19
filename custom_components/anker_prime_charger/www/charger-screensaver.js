/**
 * The charger's clock screensaver, drawn as SVG for the 3D card's screen, in
 * the display's own coordinates (480 x 200, its resolution).
 *
 * Drawn to look like the charger's (the Anker app shows them in its Clock
 * Theme page), with nothing of Anker's copied: the digits are our own
 * segment-style digits, slanted and squared like the charger's; the date as
 * the charger writes it ("Jan. 14th / Tues."), narrow, under the time.
 *
 * - The Standard Styles are clocks the charger draws itself: 1 a flip clock
 *   (a grey tile per digit, split in the middle), 2 the time alone, 3 the
 *   time in icy blue inside a large glowing blue ring.
 * - A stock theme or a custom image is its picture (480 x 200), with the
 *   time over it: always on stock themes, on custom images when the
 *   charger's "Time display" is on.
 * - Without a picture (its link didn't come), the second Standard Style.
 */
import { css, svg } from "./lib/lit-all.js";

export const SCREEN = { width: 480, height: 200, radius: 34 };

const MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."];
const WEEKDAYS = ["Sun.", "Mon.", "Tues.", "Wed.", "Thur.", "Fri.", "Sat."];
const SLANT = -8; // degrees: the digits lean right

function ordinal(day) {
  if (day % 100 >= 11 && day % 100 <= 13) return `${day}th`;
  return `${day}${{ 1: "st", 2: "nd", 3: "rd" }[day % 10] || "th"}`;
}

/** The time's digits, as the charger shows them: "08:40" (12h: 13:05 is "01:05"). */
function clockDigits(now, clock24h) {
  let hours = now.getHours();
  if (!clock24h) hours = hours % 12 || 12;
  return [String(hours).padStart(2, "0"), String(now.getMinutes()).padStart(2, "0")];
}

/** The date, as the charger writes it: "Jan. 14th / Tues.". */
function clockDate(now) {
  return `${MONTHS[now.getMonth()]} ${ordinal(now.getDate())} / ${WEEKDAYS[now.getDay()]}`;
}

// --- The digits ------------------------------------------------------------------
//
// A digit is drawn with lines along a seven-segment layout: a box `width` x
// `height` whose lines are `stroke` thick, so its corners come out squared
// (slightly rounded). x0/x1: left/right; y0/ym/y1: top/middle/bottom.

const DIGIT_PATHS = {
  0: "M{x0} {y0}H{x1}V{y1}H{x0}Z",
  1: "M{x1} {y0}V{y1}",
  2: "M{x0} {y0}H{x1}V{ym}H{x0}V{y1}H{x1}",
  3: "M{x0} {y0}H{x1}V{y1}H{x0}M{x0} {ym}H{x1}",
  4: "M{x0} {y0}V{ym}H{x1}M{x1} {y0}V{y1}",
  5: "M{x1} {y0}H{x0}V{ym}H{x1}V{y1}H{x0}",
  6: "M{x1} {y0}H{x0}V{y1}H{x1}V{ym}H{x0}",
  7: "M{x0} {y0}H{x1}V{y1}",
  8: "M{x0} {y0}H{x1}V{y1}H{x0}ZM{x0} {ym}H{x1}",
  9: "M{x1} {ym}H{x0}V{y0}H{x1}V{y1}H{x0}",
};

function digitPath(digit, x, { width, height, stroke }) {
  const half = stroke / 2;
  const at = { x0: x + half, x1: x + width - half, y0: half, ym: height / 2, y1: height - half };
  return DIGIT_PATHS[digit].replace(/\{(\w+)\}/g, (_, key) => at[key].toFixed(2));
}

/**
 * The time ("08", "40") centred at (cx, cy): digits `size` = {width, height,
 * stroke, gap (between two digits), colon (the space of the colon)}. Its
 * paths are of class "digit", the colon's bars of class "colon".
 */
function timeDigits([hours, minutes], cx, cy, size) {
  const { width, height, stroke, gap, colon } = size;
  const total = 4 * width + 2 * gap + colon;
  const lefts = [0, width + gap, 2 * width + gap + colon, 3 * width + 2 * gap + colon];
  const paths = [...hours, ...minutes].map((digit, i) => digitPath(digit, lefts[i], size)).join("");
  const bar = { width: stroke * 0.95, height: height * 0.3 };
  const colonX = 2 * width + gap + colon / 2 - bar.width / 2;
  return svg`<g transform="translate(${cx - total / 2} ${cy - height / 2}) skewX(${SLANT})
      translate(${(height / 2) * Math.tan((-SLANT * Math.PI) / 180)} 0)">
    <path class="digit" d=${paths} stroke-width=${stroke} />
    <rect class="colon" x=${colonX} y=${height * 0.27 - bar.height / 2} width=${bar.width}
      height=${bar.height} rx=${bar.width / 2} />
    <rect class="colon" x=${colonX} y=${height * 0.73 - bar.height / 2} width=${bar.width}
      height=${bar.height} rx=${bar.width / 2} />
  </g>`;
}

/** The date, narrow, centred at (cx, y). */
function dateLine(date, cx, y, size) {
  return svg`<text class="date" transform="translate(${cx} ${y}) scale(0.88 1)"
    font-size=${size}>${date}</text>`;
}

// --- The screensavers --------------------------------------------------------------

const centre = SCREEN.width / 2;
const TIME = { width: 40, height: 60, stroke: 7.5, gap: 11, colon: 44 };
const TIME_Y = 88;
const DATE = { y: 147, size: 25 };

/** Standard Style 1: a flip clock, a grey tile per digit, split in the middle. */
function flipClock([hours, minutes], date) {
  const tile = { width: 64, height: 80, gap: 7, colon: 28, top: 34 };
  const digit = { width: 38, height: 58, stroke: 5.5 };
  const total = 4 * tile.width + 2 * tile.gap + tile.colon;
  const left = centre - total / 2;
  const lefts = [0, tile.width + tile.gap, 2 * tile.width + tile.gap + tile.colon, 3 * tile.width + 2 * tile.gap + tile.colon];
  const digits = [...hours, ...minutes];
  return svg`
    ${lefts.map((x, i) => {
      const tx = left + x;
      return svg`
        <rect class="tile" x=${tx} y=${tile.top} width=${tile.width} height=${tile.height} rx="6" />
        ${timeDigit(digits[i], tx + tile.width / 2, tile.top + tile.height / 2, digit)}
        <line class="tile-split" x1=${tx} y1=${tile.top + tile.height / 2}
          x2=${tx + tile.width} y2=${tile.top + tile.height / 2} />`;
    })}
    ${timeColon(centre, tile.top + tile.height / 2, digit)}
    ${dateLine(date, centre, 152, DATE.size)}`;
}

/** One digit centred at (cx, cy), slanted like the time's. */
function timeDigit(value, cx, cy, size) {
  const shift = (size.height / 2) * Math.tan((-SLANT * Math.PI) / 180);
  return svg`<g transform="translate(${cx - size.width / 2} ${cy - size.height / 2}) skewX(${SLANT}) translate(${shift} 0)">
    <path class="digit" d=${digitPath(value, 0, size)} stroke-width=${size.stroke} />
  </g>`;
}

/** The colon's two bars centred at (cx, cy), slanted like the digits. */
function timeColon(cx, cy, { height, stroke }) {
  const bar = { width: stroke * 1.2, height: height * 0.24 };
  const shift = (height / 2) * Math.tan((-SLANT * Math.PI) / 180);
  return svg`<g class="flip-colon" transform="translate(${cx - bar.width / 2} ${cy - height / 2}) skewX(${SLANT}) translate(${shift} 0)">
    <rect class="colon" y=${height * 0.3 - bar.height / 2} width=${bar.width} height=${bar.height} rx=${bar.width / 2} />
    <rect class="colon" y=${height * 0.72 - bar.height / 2} width=${bar.width} height=${bar.height} rx=${bar.width / 2} />
  </g>`;
}

/** Standard Style 2 (and the fallback): the time alone. */
function plainClock(time, date) {
  return svg`<g class="plain">${timeDigits(time, centre, TIME_Y, TIME)}${dateLine(date, centre, DATE.y, DATE.size)}</g>`;
}

/** Standard Style 3: the time in icy blue inside a large glowing blue ring. */
function ringClock(time, date) {
  const ring = { cx: 252, cy: 100, r: 172 };
  return svg`
    <defs>
      <linearGradient id="ring-colour" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#46d6ff" /><stop offset="0.2" stop-color="#1268ff" stop-opacity="0.55" />
        <stop offset="0.5" stop-color="#0a2a80" stop-opacity="0" />
        <stop offset="0.82" stop-color="#0d4fd6" stop-opacity="0.35" /><stop offset="1" stop-color="#1a63e8" stop-opacity="0.8" />
      </linearGradient>
      <linearGradient id="ice" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#f2f7ff" /><stop offset="1" stop-color="#a9bfd9" />
      </linearGradient>
    </defs>
    <circle class="ring glow" cx=${ring.cx} cy=${ring.cy} r=${ring.r} />
    <circle class="ring" cx=${ring.cx} cy=${ring.cy} r=${ring.r} />
    <g class="ice">${timeDigits(time, centre, TIME_Y, TIME)}${dateLine(date, centre, DATE.y, DATE.size)}</g>`;
}

/** The time over a picture: white, with a soft shadow so it reads on any picture. */
function timeOver(time, date) {
  return svg`
    <defs>
      <filter id="time-shadow" x="-10%" y="-20%" width="120%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.55" />
      </filter>
    </defs>
    <g class="over" filter="url(#time-shadow)">${timeDigits(time, centre, TIME_Y - 2, { ...TIME, width: 44, height: 66, stroke: 9 })}${dateLine(date, centre, DATE.y + 4, DATE.size)}</g>`;
}

/**
 * The screensaver, in screen coordinates (0, 0 to 480, 200): `kind`
 * ("style_1" ... "style_3", "stock", "custom"), `imageUrl` (a picture's
 * link), `showTime` (the time over a picture), `now` and `clock24h`.
 */
export function screensaverDrawing({ kind, imageUrl, showTime, now, clock24h }) {
  const time = clockDigits(now, clock24h);
  const date = clockDate(now);
  const picture = (kind === "stock" || kind === "custom") && imageUrl;
  let content;
  if (kind === "style_1") content = flipClock(time, date);
  else if (kind === "style_3") content = ringClock(time, date);
  else if (picture) {
    content = svg`<image href=${imageUrl} width=${SCREEN.width} height=${SCREEN.height}
      preserveAspectRatio="xMidYMid slice" />${showTime ? timeOver(time, date) : ""}`;
  } else content = plainClock(time, date);
  return svg`
    <defs>
      <clipPath id="screen-clip">
        <rect width=${SCREEN.width} height=${SCREEN.height} rx=${SCREEN.radius} />
      </clipPath>
      <filter id="ring-glow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="7" />
      </filter>
    </defs>
    <g clip-path="url(#screen-clip)">
      <rect class="screen-back" width=${SCREEN.width} height=${SCREEN.height} />
      ${content}
    </g>`;
}

/** The screensaver's look. */
export const screensaverStyles = css`
  .screen-back {
    fill: #000;
  }
  .digit {
    fill: none;
    stroke: #fff;
    stroke-linejoin: round;
    stroke-linecap: butt;
  }
  .colon {
    fill: #fff;
  }
  .plain .colon {
    fill: #8c8c8c;
  }
  .flip-colon .colon {
    fill: #bdbdbd;
  }
  .date {
    font-family: "Roboto Condensed", var(--ha-font-family-body, Roboto, sans-serif);
    font-weight: 600;
    text-anchor: middle;
    dominant-baseline: middle;
    letter-spacing: 0.5px;
    fill: #9e9e9e;
  }
  .plain .date {
    fill: #838383;
  }
  .tile {
    fill: #474747;
  }
  .tile-split {
    stroke: #000;
    stroke-width: 2.5;
  }
  .ring {
    fill: none;
    stroke: url(#ring-colour);
    stroke-width: 5;
  }
  .ring.glow {
    stroke-width: 16;
    filter: url(#ring-glow);
    opacity: 0.75;
  }
  .ice .digit {
    stroke: url(#ice);
  }
  .ice .colon {
    fill: #c5d4e6;
  }
  .ice .date {
    fill: #a9c4e6;
  }
  .over .date {
    fill: #e6e6e6;
  }
`;
