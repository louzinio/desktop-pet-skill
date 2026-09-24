// Browser adapter for the desktop pet: web apps, Electron and Tauri renderers, anything with a DOM.
//
//   import { attachPet } from "./pet-dom.js";
//   const pet = attachPet();                  // walks on buttons, inputs, cards... of the page
//   pet.core.feel("happy", 3);                // the app can make it feel things
//   pet.stop();
//
// The pet is drawn on a small canvas that follows it; only a box the size of its body takes
// the pointer, so the page underneath stays clickable everywhere else.

import { ACT_PACKS, Bounds, Ledge, PIXEL, PROPS, Pet, actView, frame, skinNamed } from "./pet-core.js";

const WIDTH = 120;
const HEIGHT = 130;
const FEET = 124;
const MIN_PERCH = 56;
const PERCH_REFRESH_MS = 500;
export const DEFAULT_PERCHES = [
  "button", "input", "select", "textarea", "progress", "[role=button]", "[role=tab]", "nav", "header",
  "table", "img", "pre", "fieldset", "[data-pet-perch]",
].join(",");

const OUTLINE = "#8C95A8";
const SHAPES = {
  heart: [[".x.x.", "xxxxx", ".xxx.", "..x.."], "#E0557A"],
  vein: [[".x.x.", "xx.xx", ".....", "xx.xx", ".x.x."], "#C8432B"],
};
const MARK = "#D97757";
const SLEEP = "#7A8BA8";
const TEAR = "#5DB8F0";
const PUFF = "#7D8691";
const PROP_PIXEL = 3;
const TONES = { dim: "#7A8BA8", bad: "#E0442E", good: "#3FA34D" };
const SIGNAL = "#3E6FD8";
const NOISE = ["#9AA3B0", "#6B6B6B", "#E0442E", "#3E6FD8"];
const BAR_ON = "#3FA34D";
const BAR_OFF = "#C9CED6";

export function paintPet(ctx, pet, { width = WIDTH, feet = FEET, dark = false } = {}) {
  const rows = frame(pet);
  const palette = pet.skin.palette;
  const across = PIXEL * (1.0 + pet.squash);
  const down = PIXEL * (1.0 - pet.squash);
  const left = width / 2 - (rows[0].length * across) / 2;
  const top = feet - rows.length * down;
  const view = actView(pet);
  const colourAt = new Map();
  rows.forEach((row, r) => [...row].forEach((cell, c) => {
    if (cell in palette) colourAt.set(`${r},${c + (view.shift[r] ?? 0)}`, palette[cell]);
  }));
  const fill = (x, y, w, h, colour) => { ctx.fillStyle = colour; ctx.fillRect(x, y, w, h); };
  const outline = pet.skin.outline && dark;
  if (view.ghost !== null) {
    ctx.globalAlpha = outline ? 0.4 : 0.3;
    for (const [key, colour] of colourAt) {
      const [r, c] = key.split(",").map(Number);
      fill(left + c * across + view.ghost, top + r * down, across, down, outline ? OUTLINE : colour);
    }
    ctx.globalAlpha = 1.0;
  }
  if (outline) {
    for (const key of colourAt.keys()) {
      const [r, c] = key.split(",").map(Number);
      for (const [dr, dc] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        if (!colourAt.has(`${r + dr},${c + dc}`)) fill(left + (c + dc) * across, top + (r + dr) * down, across + 0.5, down + 0.5, OUTLINE);
      }
    }
  }
  for (const [key, colour] of colourAt) {
    const [r, c] = key.split(",").map(Number);
    fill(left + c * across, top + r * down, across + 0.5, down + 0.5, colour);
  }
  paintAct(ctx, pet, view, width, feet);
  paintParticles(ctx, pet, width, feet);
}

function paintParticles(ctx, pet, width, feet) {
  for (const p of pet.particles) {
    ctx.globalAlpha = Math.max(0, Math.min(1, p.life * 2));
    const x = width / 2 + p.x;
    const y = feet + p.y;
    if (p.kind === "tear") {
      ctx.fillStyle = TEAR; ctx.fillRect(x - 1.5, y, 3, 5);
    } else if (p.kind === "ring") {
      const grow = (0.4 - p.life) * 90;
      ctx.strokeStyle = SIGNAL; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.ellipse(x, y - 1, 10 + grow, 3 + grow / 8, 0, 0, Math.PI * 2); ctx.stroke();
    } else if (p.kind === "puff") {
      const size = 4 + (0.6 - p.life) * 10;
      ctx.fillStyle = PUFF; ctx.fillRect(x - size / 2, y - size / 2, size, size);
    } else if (p.kind in SHAPES) {
      const [shape, colour] = SHAPES[p.kind];
      ctx.fillStyle = colour;
      shape.forEach((row, r) => [...row].forEach((mark, c) => {
        if (mark === "x") ctx.fillRect(x - 7.5 + c * 3, y + r * 3, 3, 3);
      }));
    } else {
      ctx.fillStyle = p.kind === "z" ? SLEEP : MARK;
      ctx.font = "bold 14px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(p.kind, x, y);
    }
  }
  ctx.globalAlpha = 1.0;
}

function paintAct(ctx, pet, view, width, feet) {
  const top = feet - pet.skin.height;
  const centre = width / 2;
  if (view.noise !== null) {
    let seed = view.noise * 9301 + 49297;
    const next = (n) => { seed = (seed * 9301 + 49297) % 233280; return Math.floor((seed / 233280) * n); };
    for (let i = 0; i < 50; i++) {
      ctx.fillStyle = NOISE[next(NOISE.length)];
      ctx.fillRect(next(width / 3) * 3, next((top + 20) / 3) * 3, 3, 3);
    }
  }
  for (const [name, x, y, alpha] of view.props) {
    const [grid, palette] = PROPS[name];
    const left = centre + x - (grid[0].length * PROP_PIXEL) / 2;
    const upper = feet + y - (grid.length * PROP_PIXEL) / 2;
    ctx.globalAlpha = alpha;
    grid.forEach((row, r) => [...row].forEach((mark, c) => {
      if (mark in palette) {
        ctx.fillStyle = palette[mark];
        ctx.fillRect(left + c * PROP_PIXEL, upper + r * PROP_PIXEL, PROP_PIXEL, PROP_PIXEL);
      }
    }));
    ctx.globalAlpha = 1.0;
  }
  if (view.bars !== null) {
    for (let i = 0; i < 4; i++) {
      const height = 3 + i * 3;
      ctx.fillStyle = i < view.bars ? BAR_ON : BAR_OFF;
      ctx.fillRect(centre + 38 + i * 5, top - height, 3, height);
    }
  }
  if (view.wave !== null) {
    const base = top - 26;
    ctx.strokeStyle = SIGNAL; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(centre - 50, base);
    for (let i = 0; i < 5; i++) {
      const x = centre - 44 + i * 20;
      const high = base - (i === view.wave ? 10 : 4);
      ctx.lineTo(x, base); ctx.lineTo(x, high); ctx.lineTo(x + 6, high); ctx.lineTo(x + 6, base);
    }
    ctx.lineTo(centre + 50, base); ctx.stroke();
  }
  if (view.orbit !== null) {
    const cx = centre;
    const cy = top - 20;
    ctx.strokeStyle = BAR_OFF; ctx.lineWidth = 1;
    for (const tilt of [0, 60]) {
      ctx.save(); ctx.translate(cx, cy); ctx.rotate((tilt * Math.PI) / 180);
      ctx.beginPath(); ctx.ellipse(0, 0, 22, 7, 0, 0, Math.PI * 2); ctx.stroke();
      const phase = view.orbit + tilt / 30;
      ctx.fillStyle = SIGNAL; ctx.fillRect(22 * Math.cos(phase) - 2, 7 * Math.sin(phase) - 2, 4, 4);
      ctx.restore();
    }
    ctx.fillStyle = TONES.bad; ctx.fillRect(cx - 3, cy - 3, 6, 6);
  }
  if (view.dots !== null) {
    for (let i = 0; i < 3; i++) {
      ctx.fillStyle = i < view.dots ? TONES.dim : BAR_OFF;
      ctx.fillRect(centre - 11 + i * 8, top - 12, 5, 5);
    }
  }
  ctx.font = "bold 10px monospace"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (const [text, x, y, tone] of view.labels) {
    ctx.fillStyle = TONES[tone];
    ctx.fillText(text, centre + x, feet + y);
  }
}

export function attachPet({
  root = document.body, skin = "clawd", acts = null, perches = DEFAULT_PERCHES, dark = null, zIndex = 2147483000,
  rng = undefined,
} = {}) {
  const pet = new Pet(window.innerWidth / 2, -60, {
    rng,
    skin: skinNamed(skin),
    acts: acts === "gnss" ? ACT_PACKS.gnss : (acts ?? {}),
  });
  const ratio = window.devicePixelRatio || 1;
  const canvas = document.createElement("canvas");
  canvas.width = WIDTH * ratio;
  canvas.height = HEIGHT * ratio;
  Object.assign(canvas.style, {
    position: "fixed", left: "0", top: "0", width: `${WIDTH}px`, height: `${HEIGHT}px`,
    pointerEvents: "none", zIndex: String(zIndex), imageRendering: "pixelated",
  });
  canvas.dataset.desktopPet = "sprite";
  const hit = document.createElement("div");
  Object.assign(hit.style, { position: "fixed", left: "0", top: "0", cursor: "grab", zIndex: String(zIndex + 1), touchAction: "none" });
  hit.dataset.desktopPet = "body";
  root.append(canvas, hit);
  const ctx = canvas.getContext("2d");

  let cursor = [-5000, -5000];
  let perchList = [];
  let perchAge = Infinity;
  let last = performance.now();
  let frameId = null;
  let samples = [];
  let grip = [0, 0];
  const isDark = () => dark ?? window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;

  const onMove = (event) => { cursor = [event.clientX, event.clientY]; };
  const onInput = (event) => {
    const rect = event.target.getBoundingClientRect?.();
    if (rect) pet.watch(rect.left + rect.width / 2, rect.top + rect.height / 2);
  };
  document.addEventListener("pointermove", onMove, { passive: true });
  document.addEventListener("input", onInput, { passive: true });

  function findPerches() {
    return [...root.querySelectorAll(perches)].filter((el) => !el.dataset.desktopPet);
  }

  function ledges() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const out = [new Ledge(0, width, height)];
    for (const el of perchList) {
      if (!el.isConnected) continue;
      const rect = el.getBoundingClientRect();
      const left = Math.max(rect.left, 0);
      const right = Math.min(rect.right, width);
      if (rect.top > 0 && rect.top < height && right - left >= MIN_PERCH && rect.height > 0) {
        out.push(new Ledge(left, right, rect.top, el));
      }
    }
    return out;
  }

  function place() {
    canvas.style.transform = `translate(${Math.round(pet.x - WIDTH / 2)}px, ${Math.round(pet.y - FEET)}px)`;
    const { width, height } = pet.skin;
    Object.assign(hit.style, {
      width: `${width}px`, height: `${height}px`,
      transform: `translate(${Math.round(pet.x - width / 2)}px, ${Math.round(pet.y - height)}px)`,
    });
  }

  function tick(now) {
    frameId = requestAnimationFrame(tick);
    const dt = (now - last) / 1000;
    last = now;
    perchAge += dt * 1000;
    if (perchAge >= PERCH_REFRESH_MS) {
      perchList = findPerches();
      perchAge = 0;
    }
    pet.step(dt, ledges(), cursor, new Bounds(0, 0, window.innerWidth, window.innerHeight));
    place();
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, WIDTH, HEIGHT);
    paintPet(ctx, pet, { dark: isDark() });
  }

  hit.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    hit.setPointerCapture(event.pointerId);
    grip = [pet.x - event.clientX, pet.y - event.clientY];
    samples = [[performance.now() / 1000, event.clientX, event.clientY]];
    pet.grab();
    hit.style.cursor = "grabbing";
  });
  hit.addEventListener("pointermove", (event) => {
    if (!samples.length) return;
    pet.dragTo(event.clientX + grip[0], event.clientY + grip[1]);
    const now = performance.now() / 1000;
    samples = [...samples.filter((s) => now - s[0] < 0.1), [now, event.clientX, event.clientY]];
    place();
  });
  const release = () => {
    if (!samples.length) return;
    const first = samples[0];
    const lastSample = samples[samples.length - 1];
    const span = lastSample[0] - first[0];
    pet.throw(span > 0 ? (lastSample[1] - first[1]) / span : 0, span > 0 ? (lastSample[2] - first[2]) / span : 0);
    samples = [];
    hit.style.cursor = "grab";
  };
  hit.addEventListener("pointerup", release);
  hit.addEventListener("pointercancel", release);
  hit.addEventListener("dblclick", () => { samples = []; pet.cheer(); });

  place();
  frameId = requestAnimationFrame(tick);

  return {
    core: pet,
    canvas,
    hit,
    setSkin(key) { pet.skin = skinNamed(key); },
    stop() {
      cancelAnimationFrame(frameId);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("input", onInput);
      canvas.remove();
      hit.remove();
    },
  };
}
