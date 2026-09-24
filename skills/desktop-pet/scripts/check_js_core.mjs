// Replays assets/reference_trace.json through the JavaScript core and checks every step:
//   node check_js_core.mjs
// A port to another language is proved the same way -- translate this file.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ACT_PACKS, Bounds, Ledge, Mulberry32, Pet, actView, frame, skinNamed } from "../assets/js/pet-core.js";

const trace = JSON.parse(readFileSync(new URL("../assets/reference_trace.json", import.meta.url)));

function state(pet, step) {
  const view = actView(pet);
  const out = {
    x: pet.x, y: pet.y, vx: pet.vx, vy: pet.vy, mood: pet.mood, facing: pet.facing, act: pet.act, emotion: pet.emotion,
    ledge: pet.ledge === null ? null : [pet.ledge.left, pet.ledge.y],
    particles: pet.particles.map((p) => [p.kind, p.x, p.y]),
    view: [view.props.length, view.labels.map((label) => label[0]), view.ghost, view.bars, view.dots],
  };
  if (step % 10 === 0) out.frame = frame(pet);
  return out;
}

function close(want, got, path) {
  if (typeof want === "number" || typeof got === "number") {
    if (typeof want !== "number" || typeof got !== "number"
        || Math.abs(want - got) > 1e-6 * Math.max(1, Math.abs(want), Math.abs(got))) {
      return `${path}: expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`;
    }
    return null;
  }
  if (Array.isArray(want)) {
    if (!Array.isArray(got) || want.length !== got.length) return `${path}: expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`;
    for (let i = 0; i < want.length; i++) {
      const problem = close(want[i], got[i], `${path}[${i}]`);
      if (problem) return problem;
    }
    return null;
  }
  if (want !== null && typeof want === "object") {
    for (const key of Object.keys(want)) {
      const problem = close(want[key], got[key], `${path}.${key}`);
      if (problem) return problem;
    }
    return null;
  }
  return want === got ? null : `${path}: expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`;
}

for (const scenario of trace.scenarios) {
  test(`the JavaScript core reproduces the reference trace: ${scenario.name}`, () => {
    const pet = new Pet(600.0, 100.0, {
      rng: new Mulberry32(scenario.seed),
      skin: skinNamed(scenario.skin),
      acts: scenario.acts ? ACT_PACKS[scenario.acts] : {},
    });
    const bounds = new Bounds(...trace.bounds);
    trace.inputs.forEach((given, step) => {
      for (const [name, ...args] of given.events) {
        const method = { drag_to: "dragTo" }[name] ?? name;
        pet[method](...args);
      }
      const ledges = trace.ledge_sets[given.ledges].map(([left, right, y, key]) => new Ledge(left, right, y, key));
      pet.step(given.dt, ledges, given.cursor, bounds);
      const problem = close(scenario.states[step], state(pet, step), `${scenario.name} step ${step}`);
      assert.equal(problem, null, problem ?? "");
    });
  });
}
