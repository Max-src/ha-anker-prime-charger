/**
 * A 3D model of the charger, drawn as SVG from any angle (the 3D card).
 *
 * The model, in millimetres (the real charger: 212 wide, 64 high, 140
 * deep): x to the right, y up, z toward the viewer; the front (the screen
 * and the USB-C ports) faces +z, the right side (the knob and the USB-A
 * ports) +x. The body is a rounded rectangle (the front's outline)
 * stretched back over the depth.
 *
 * Drawing: the model is turned (yaw around y, then pitch around x) and seen
 * from CAMERA_DISTANCE, a gentle perspective. Outlines are projected point by
 * point; small details on a surface (a port, the knob, the screen's text) are
 * drawn in the surface's own 2D coordinates with the transform of the
 * perspective at their place (accurate at their size). Surfaces facing away
 * from the camera are skipped; the rest are drawn back to front, each shaded
 * by how much it faces the light.
 */
import { css, svg } from "./lib/lit-all.js";
import { SCREEN } from "./charger-screensaver.js";

// The body
const W = 212;
const H = 64;
const D = 140;
const RADIUS = 10; // of the front's corners
const CORNER_STEPS = 5;

// The front: glass, screen text, USB-C ports (2D: u right, v down, mm)
const GLASS = { inset: 6, radius: 6 };
const USB_C = { ids: ["c1", "c2", "c3", "c4"], gap: 35, v: H - 12, width: 20, height: 5.5 };
// The power page: the total output; each USB-C port's power, just above it
// (whatever the screen shows; the USB-A ports': SIDE_POWER)
const POWER_PAGE = { total: H * 0.36, port: H - 21 };
// The display under the glass (2.4:1, as its 480 x 200 pixels), above the
// ports: where the clock screensaver is drawn
const DISPLAY = { width: 84, height: 35, v: 9 };
DISPLAY.u = (W - DISPLAY.width) / 2;
// The right side (2D: u from the front edge to the back, v down)
const KNOB = { u: 25, v: H * 0.55, radius: 11, height: 6 };
const USB_A = { ids: ["a1", "a2"], u: [67, 104], v: H * 0.55, width: 22, height: 9 };
// Each USB-A port's power, on the side just above it
const SIDE_POWER = { v: USB_A.v - 13 };
// Plugs: their size around the port, length, narrowing; cords
// Plugs (like Apple's braided cables): a soft white housing with rounded
// edges, out of a thin metal collar; its size around the port, length,
// narrowing; then the braided cord
const PLUG = {
  margin: 2,
  collar: 1.5,
  length: { usb_c: 26, usb_a: 28 },
  // corners, as a share of the housing's smaller half-size: USB-C rounded,
  // USB-A almost square
  roundness: { usb_c: 0.75, usb_a: 0.25 },
  taper: 0.94,
  steps: 4,
};
const CORD = { width: 6.5, reach: 85 };

// The view (SVG units: mm at the model's centre), the camera's distance from
// the centre (smaller: stronger perspective), the light (view space: top left)
const VIEW_BOX = { width: 360, height: 220 };

/** The view box at `zoom` (1: the whole charger; larger: nearer), centred. */
function viewBox(zoom) {
  const width = VIEW_BOX.width / zoom;
  const height = VIEW_BOX.height / zoom;
  return `${-width / 2} ${-height / 2} ${width} ${height}`;
}
const CAMERA_DISTANCE = 650;
const LIGHT = normalize([-0.45, 0.75, 0.55]);

// Colours (r, g, b)
const COLOURS = {
  body: [196, 201, 206],
  glass: "#0b0e12",
  plug: [244, 245, 246],
  collar: [176, 182, 188],
  cord: [236, 238, 240],
  knob: [208, 212, 216],
};

function normalize([x, y, z]) {
  const length = Math.hypot(x, y, z);
  return [x / length, y / length, z / length];
}
const plus = ([x, y, z], [dx, dy, dz], k = 1) => [x + dx * k, y + dy * k, z + dz * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const average = (list) =>
  list.reduce((sum, p) => plus(sum, p, 1 / list.length), [0, 0, 0]);

/** The view: turns model points and vectors, gives their place on screen. */
function viewer(yaw, pitch) {
  const a = (yaw * Math.PI) / 180;
  const b = (pitch * Math.PI) / 180;
  const [ca, sa, cb, sb] = [Math.cos(a), Math.sin(a), Math.cos(b), Math.sin(b)];
  /** A model vector in view space: x right, y up, z toward the viewer. */
  const turn = ([x, y, z]) => {
    const x1 = x * ca + z * sa;
    const z1 = -x * sa + z * ca;
    return [x1, y * cb - z1 * sb, y * sb + z1 * cb];
  };
  /** On screen (x right, y down) and how near (larger: nearer). */
  const project = (point) => {
    const [x, y, z] = turn(point);
    const scale = CAMERA_DISTANCE / (CAMERA_DISTANCE - z);
    return [x * scale, -y * scale, z];
  };
  return {
    project,
    /** "x,y" of model points, for an SVG polygon or path. */
    screen: (list) => list.map((p) => project(p).slice(0, 2).join(",")).join(" "),
    /** Whether a surface at `point` facing `normal` is seen by the camera. */
    facing: (normal, point) => {
      const toCamera = plus([0, 0, CAMERA_DISTANCE], turn(point), -1);
      return dot(turn(normal), toCamera) > 1e-6;
    },
    /** A colour lit by the light, by the direction its surface faces. */
    shade: (rgb, normal) => {
      const k = 0.62 + 0.45 * Math.max(0, dot(turn(normal), LIGHT));
      return `rgb(${rgb.map((c) => Math.min(255, Math.round(c * k))).join(",")})`;
    },
  };
}

/**
 * A flat surface: its corner (`origin`), its 2D axes in the model (`u`, `v`,
 * unit vectors) and the direction it faces (`normal`).
 */
function surface(origin, u, v, normal) {
  return { origin, u, v, normal };
}

/** A point of a surface (2D u, v; `out` above it), in the model. */
const at = (s, u, v, out = 0) => plus(plus(plus(s.origin, s.u, u), s.v, v), s.normal, out);

/**
 * The SVG transform drawing a surface's 2D coordinates as seen around (u, v)
 * (`out` above the surface): the perspective there, for a small detail.
 */
function placement(view, s, u, v, out = 0) {
  const [e, f] = view.project(at(s, u, v, out));
  const [ux, uy] = view.project(at(s, u + 1, v, out));
  const [vx, vy] = view.project(at(s, u, v + 1, out));
  const [a, b, c, d] = [ux - e, uy - f, vx - e, vy - f];
  return `matrix(${a} ${b} ${c} ${d} ${e - a * u - c * v} ${f - b * u - d * v})`;
}

/** A rounded rectangle's outline (2D points), corners of `r`. */
function roundedRect(x, y, width, height, r) {
  const corners = [
    [x + width - r, y + r, -90],
    [x + width - r, y + height - r, 0],
    [x + r, y + height - r, 90],
    [x + r, y + r, 180],
  ];
  const points = [];
  for (const [cx, cy, start] of corners) {
    for (let i = 0; i <= CORNER_STEPS; i++) {
      const angle = ((start + (90 * i) / CORNER_STEPS) * Math.PI) / 180;
      points.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)]);
    }
  }
  return points;
}

const FRONT = surface([-W / 2, H / 2, D / 2], [1, 0, 0], [0, -1, 0], [0, 0, 1]);
const BACK = surface([W / 2, H / 2, -D / 2], [-1, 0, 0], [0, -1, 0], [0, 0, -1]);
const RIGHT = surface([W / 2, H / 2, D / 2], [0, 0, -1], [0, -1, 0], [1, 0, 0]);
const FACE_OUTLINE = roundedRect(0, 0, W, H, RADIUS);

/** The front's outline in the x-y plane (clockwise from the top right), with
 * the direction each point faces. */
function outline() {
  // each corner's centre, and the direction its arc starts at (degrees)
  const corners = [
    [W / 2 - RADIUS, H / 2 - RADIUS, 90], // top right: from up to right
    [W / 2 - RADIUS, -H / 2 + RADIUS, 0], // bottom right: right to down
    [-W / 2 + RADIUS, -H / 2 + RADIUS, -90], // bottom left: down to left
    [-W / 2 + RADIUS, H / 2 - RADIUS, -180], // top left: left to up
  ];
  const points = [];
  for (const [cx, cy, start] of corners) {
    for (let i = 0; i <= CORNER_STEPS; i++) {
      const angle = ((start - (90 * i) / CORNER_STEPS) * Math.PI) / 180;
      const normal = [Math.cos(angle), Math.sin(angle), 0];
      points.push({ point: [cx + RADIUS * normal[0], cy + RADIUS * normal[1]], normal });
    }
  }
  return points;
}
const OUTLINE = outline();

/** The body's sides: strips around the outline, from the front to the back. */
function bodySides(view) {
  return OUTLINE.map(({ point, normal }, i) => {
    const next = OUTLINE[(i + 1) % OUTLINE.length];
    const facing = normalize(plus(normal, next.normal));
    const corners = [
      [...point, D / 2],
      [...next.point, D / 2],
      [...next.point, -D / 2],
      [...point, -D / 2],
    ];
    const middle = average(corners);
    if (!view.facing(facing, middle)) return null;
    const colour = view.shade(COLOURS.body, facing);
    return {
      depth: view.project(middle)[2],
      draw: svg`<polygon points=${view.screen(corners)} fill=${colour} stroke=${colour}
        stroke-width="0.6" stroke-linejoin="round" />`,
    };
  }).filter(Boolean);
}

/** A flat face of the body (its outline, then `details`), if seen. */
function face(view, s, details) {
  const middle = at(s, W / 2, H / 2);
  if (!view.facing(s.normal, middle)) return null;
  const outline = FACE_OUTLINE.map(([u, v]) => at(s, u, v));
  return {
    depth: view.project(middle)[2],
    draw: svg`<polygon points=${view.screen(outline)} fill=${view.shade(COLOURS.body, s.normal)} />
      ${details}`,
  };
}

/** A port's opening on a surface, centred at (u, v). */
function port(view, s, u, v, width, height, radius, active) {
  // on the side's metal (not the front's glass): a dark rim
  const classes = ["port", active ? "active" : "", s === RIGHT ? "side" : ""];
  return svg`<rect
    class=${classes.join(" ")}
    transform=${placement(view, s, u, v)}
    x=${u - width / 2} y=${v - height / 2} width=${width} height=${height} rx=${radius}
  />`;
}

/** The display's content (480 x 200), drawn in its place on the front. */
function display(view, content) {
  const k = DISPLAY.width / SCREEN.width;
  const centre = placement(view, FRONT, DISPLAY.u + DISPLAY.width / 2, DISPLAY.v + DISPLAY.height / 2);
  return svg`<g transform=${centre}>
    <g transform="translate(${DISPLAY.u} ${DISPLAY.v}) scale(${k})">${content}</g>
  </g>`;
}

/** Text on the front, centred at (u, v). */
function frontText(view, cls, u, v, value) {
  return svg`<text class=${cls} transform=${placement(view, FRONT, u, v)} x=${u} y=${v}>${value}</text>`;
}

/** What the screen shows (see chargerModel's `screen`), drawn on the glass. */
function screenContent(view, screen) {
  if (screen.mode === "clock") return display(view, screen.content);
  if (screen.mode === "off") return "";
  return frontText(view, "screen", W / 2, POWER_PAGE.total, screen.total);
}

/** Each USB-C port's power, just above it (over the screen). */
function usbCPower(view, portPower) {
  return USB_C.ids.map((id, i) =>
    portPower?.[id]
      ? frontText(view, "port-power", W / 2 + (i - 1.5) * USB_C.gap, POWER_PAGE.port, portPower[id])
      : "",
  );
}

function frontFace(view, inUse, screen, portPower) {
  const glass = roundedRect(
    GLASS.inset,
    GLASS.inset - 1,
    W - 2 * GLASS.inset,
    H - 2 * GLASS.inset + 2,
    GLASS.radius,
  ).map(([u, v]) => at(FRONT, u, v));
  const ports = USB_C.ids.map((id, i) =>
    port(view, FRONT, W / 2 + (i - 1.5) * USB_C.gap, USB_C.v, USB_C.width, USB_C.height, USB_C.height / 2, inUse.has(id)),
  );
  return face(view, FRONT, svg`
    <polygon class="glass" points=${view.screen(glass)} fill=${COLOURS.glass} />
    ${screenContent(view, screen)}
    ${usbCPower(view, portPower)}
    ${ports}
  `);
}

/** The right side's details (its surface is one of the body's strips). */
function rightDetails(view, inUse, portPower) {
  const middle = at(RIGHT, D / 2, H / 2);
  if (!view.facing(RIGHT.normal, middle)) return null;
  // the knob: discs stacked out from the side (its edge), then its top
  const knob = [];
  const edge = view.shade(COLOURS.knob.map((c) => c * 0.7), RIGHT.normal);
  for (let out = 0; out < KNOB.height; out += 0.5) {
    knob.push(svg`<circle transform=${placement(view, RIGHT, KNOB.u, KNOB.v, out)}
      cx=${KNOB.u} cy=${KNOB.v} r=${KNOB.radius} fill=${edge} />`);
  }
  const top = placement(view, RIGHT, KNOB.u, KNOB.v, KNOB.height);
  knob.push(svg`<circle transform=${top} cx=${KNOB.u} cy=${KNOB.v} r=${KNOB.radius}
      fill=${view.shade(COLOURS.knob, RIGHT.normal)} />
    <circle transform=${top} cx=${KNOB.u} cy=${KNOB.v} r=${KNOB.radius - 1.2}
      fill="url(#knob-top)" />`);
  const ports = USB_A.ids.map((id, i) =>
    port(view, RIGHT, USB_A.u[i], USB_A.v, USB_A.width, USB_A.height, 0.8, inUse.has(id)),
  );
  const power = USB_A.ids.map((id, i) => {
    const value = portPower?.[id];
    if (!value) return "";
    const u = USB_A.u[i];
    return svg`<text class="side-power" transform=${placement(view, RIGHT, u, SIDE_POWER.v)}
      x=${u} y=${SIDE_POWER.v}>${value}</text>`;
  });
  return {
    // just in front of the side, so drawn over it
    depth: view.project(middle)[2] + 0.01,
    draw: svg`${ports}${power}${knob}`,
  };
}

/**
 * A rounded rectangle around (0, 0), ± w and ± h, corners of `r`: points
 * going around, each with the direction it faces (2D: du, dv).
 */
function roundedProfile(w, h, r) {
  const corners = [
    [w - r, -h + r, -90],
    [w - r, h - r, 0],
    [-w + r, h - r, 90],
    [-w + r, -h + r, 180],
  ];
  const points = [];
  for (const [cu, cv, start] of corners) {
    for (let i = 0; i <= PLUG.steps; i++) {
      const angle = ((start + (90 * i) / PLUG.steps) * Math.PI) / 180;
      const [du, dv] = [Math.cos(angle), Math.sin(angle)];
      points.push({ u: cu + r * du, v: cv + r * dv, du, dv });
    }
  }
  return points;
}

/**
 * A rounded block out of surface `s` at (u, v): `profile` from `from` to
 * `to` above the surface, narrowing to `taper` at its end. Its faces seen
 * from the viewer, shaded from `colour` (a strip per profile step, so its
 * rounded edges shade smoothly), and its end.
 */
function roundedBlock(view, s, u, v, profile, from, to, taper, colour) {
  const ring = (out, k) => profile.map((p) => at(s, u + p.u * k, v + p.v * k, out));
  const base = ring(from, 1);
  const end = ring(to, taper);
  const faces = [];
  profile.forEach((p, i) => {
    const j = (i + 1) % profile.length;
    const q = profile[j];
    const normal = normalize(plus(plus([0, 0, 0], s.u, p.du + q.du), s.v, p.dv + q.dv));
    const quad = [base[i], base[j], end[j], end[i]];
    if (!view.facing(normal, average(quad))) return;
    const shade = view.shade(colour, normal);
    faces.push(svg`<polygon points=${view.screen(quad)} fill=${shade} stroke=${shade}
      stroke-width="0.5" stroke-linejoin="round" />`);
  });
  if (view.facing(s.normal, at(s, u, v, to))) {
    const shade = view.shade(colour, s.normal);
    faces.push(svg`<polygon points=${view.screen(end)} fill=${shade} stroke=${shade}
      stroke-width="0.5" stroke-linejoin="round" />`);
  }
  return faces;
}

/**
 * A plug of `kind` ("usb_c", "usb_a") in a port of surface `s` at (u, v),
 * `width` x `height` on the surface: the metal collar, then the white
 * housing. Its faces (those seen, nearest last) and where its end is.
 */
function plugAt(view, s, kind, u, v, width, height) {
  const w = width / 2 + PLUG.margin;
  const h = height / 2 + PLUG.margin;
  const length = PLUG.length[kind];
  const radius = Math.max(1.2, Math.min(w, h) * PLUG.roundness[kind]);
  const housing = roundedProfile(w, h, radius);
  const collar = roundedProfile(w - 1, h - 1, Math.max(0.5, radius - 1));
  const faces = [
    ...roundedBlock(view, s, u, v, collar, 0, PLUG.collar, 1, COLOURS.collar),
    ...roundedBlock(view, s, u, v, housing, PLUG.collar, length, PLUG.taper, COLOURS.plug),
  ];
  return { faces, end: at(s, u, v, length), centre: at(s, u, v, length / 2) };
}

/**
 * A braided cord from a plug's end: straight out, then down to the desk,
 * onward. Drawn as its outline, the cord, and two rows of short dashes that
 * cross like a braid.
 */
function cord(view, start, out, spread) {
  const desk = -H / 2 + CORD.width / 2;
  const p1 = plus(start, out, 25);
  const p3 = plus(plus([start[0], desk, start[2]], out, CORD.reach), spread);
  const p2 = plus(p3, out, -35);
  const points = [];
  for (let i = 0; i <= 24; i++) {
    const t = i / 24;
    const m = 1 - t;
    points.push(
      [0, 1, 2].map(
        (k) =>
          m * m * m * start[k] + 3 * m * m * t * p1[k] + 3 * m * t * t * p2[k] + t * t * t * p3[k],
      ),
    );
  }
  const line = view.screen(points);
  const colour = view.shade(COLOURS.cord, [0, 1, 0]);
  return svg`<polyline class="cord-edge" points=${line} />
    <polyline class="cord" points=${line} stroke=${colour} />
    <polyline class="braid" points=${line} />
    <polyline class="braid second" points=${line} />`;
}

// Draw order of the cables: the body sits between them
const AFTER_BODY = 1e6;

/**
 * A cable in a port: plug and cord. When the port's side faces the viewer,
 * the cable is in front of the whole body: drawn after it (by depth: the
 * body's faces are large, their middle can be nearer than a plug at their
 * edge). Otherwise it is behind: drawn before the body, which hides all of
 * it but what sticks out, and its cord before its plug.
 */
function cable(view, s, kind, u, v, width, height, spread) {
  const plug = plugAt(view, s, kind, u, v, width, height);
  const seen = view.facing(s.normal, at(s, u, v));
  const line = cord(view, plug.end, s.normal, spread);
  const depth = view.project(plug.centre)[2];
  return {
    depth: seen ? AFTER_BODY + depth : -AFTER_BODY + depth,
    draw: seen ? svg`${plug.faces}${line}` : svg`${line}${[...plug.faces].reverse()}`,
  };
}

/**
 * The charger seen from (yaw, pitch), in degrees. `inUse`: the ids of the
 * ports with a device ("c1" ... "a2"); `screen`: what its screen shows,
 * {mode: "power", total: "12.6 W"} (the power page), {mode: "clock",
 * content} (charger-screensaver.js: an SVG drawing in the display's
 * 480 x 200 coordinates) or {mode: "off"}; `portPower`: each port's power
 * written above it ({c1: "7.2W", a1: "2.5W"}), whatever the screen shows
 * (none: not written); `zoom`: 1 shows the whole charger, larger is nearer;
 * `cables`: a cable in each port in use (else only the port is lit).
 */
export function chargerModel({ yaw, pitch, zoom = 1, inUse, screen, portPower, cables = true }) {
  const view = viewer(yaw, pitch);
  const items = [
    ...bodySides(view),
    frontFace(view, inUse, screen, portPower),
    face(view, BACK, ""),
    rightDetails(view, inUse, portPower),
  ];
  USB_C.ids.forEach((id, i) => {
    if (!cables || !inUse.has(id)) return;
    const u = W / 2 + (i - 1.5) * USB_C.gap;
    // the cords fan out a little, as when they lie on a desk
    const spread = [(i - 1.5) * 18, 0, 0];
    items.push(cable(view, FRONT, "usb_c", u, USB_C.v, USB_C.width, USB_C.height, spread));
  });
  USB_A.ids.forEach((id, i) => {
    if (!cables || !inUse.has(id)) return;
    const spread = [0, 0, (0.5 - i) * 20];
    items.push(cable(view, RIGHT, "usb_a", USB_A.u[i], USB_A.v, USB_A.width, USB_A.height, spread));
  });
  const drawn = items.filter(Boolean).sort((a, b) => a.depth - b.depth);
  return svg`<svg viewBox=${viewBox(zoom)} xmlns="http://www.w3.org/2000/svg" role="img">
    <defs>
      <radialGradient id="knob-top" cx="0.4" cy="0.35" r="0.75">
        <stop offset="0" stop-color="#ffffff" stop-opacity="0.9" />
        <stop offset="1" stop-color="#ffffff" stop-opacity="0" />
      </radialGradient>
    </defs>
    ${drawn.map((item) => item.draw)}
  </svg>`;
}

/** The model's look (colours not set by its lighting). */
export const modelStyles = css`
  svg {
    display: block;
    width: 100%;
    height: auto;
  }
  .screen {
    fill: var(--anker-port-active-color);
    font: 600 22px var(--ha-font-family-body, Roboto, sans-serif);
    text-anchor: middle;
    dominant-baseline: middle;
  }
  .port-power {
    fill: #e8edf2;
    /* readable over the clock's picture too */
    stroke: #0b0e12;
    stroke-width: 1.6px;
    stroke-linejoin: round;
    paint-order: stroke;
    font: 600 8.5px var(--ha-font-family-body, Roboto, sans-serif);
    text-anchor: middle;
    dominant-baseline: middle;
  }
  .side-power {
    fill: #2f353c;
    font: 600 8.5px var(--ha-font-family-body, Roboto, sans-serif);
    text-anchor: middle;
    dominant-baseline: middle;
  }
  /* a port's opening, with a thin rim (metal on the glass, dark on the side's
     metal; on a lit port, its colour darker) */
  .port {
    fill: #30363d;
    stroke: #8b949d;
    stroke-width: 0.7px;
  }
  .port.side {
    stroke: #121519;
  }
  .port.active {
    fill: var(--anker-port-active-color);
    stroke: color-mix(in srgb, var(--anker-port-active-color) 55%, #0b0e12);
  }
  /* the braided cord: outline, cord, then two rows of dashes, staggered */
  .cord,
  .cord-edge,
  .braid {
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .cord {
    stroke-width: 6.5;
  }
  /* a thin dark line around the cord, as in a drawing */
  .cord-edge {
    stroke: #6f767d;
    stroke-width: 7.4;
  }
  .braid {
    stroke: #d2d7dc;
    stroke-width: 4.5;
    stroke-dasharray: 1.3 1.3;
    stroke-linecap: butt;
    transform: translate(0.6px, -0.6px);
  }
  .braid.second {
    stroke-dashoffset: 1.3;
    transform: translate(-0.6px, 0.6px);
  }
`;
