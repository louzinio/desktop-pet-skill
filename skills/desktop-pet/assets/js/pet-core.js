// The desktop pet's core -- physics, behaviour and pixel art -- ported line for line from
// assets/python/desktop_pet/core.py. No DOM here: pet-dom.js is the browser adapter.
// A seeded pet reproduces assets/reference_trace.json exactly; keep it that way when editing.

export const GRAVITY = 2200.0;
export const WALK_SPEED = 70.0;
export const MAX_JUMP_UP = 420.0;
export const MAX_JUMP_ACROSS = 700.0;
export const EDGE_MARGIN = 14.0;
export const CATCH_RADIUS = 30.0;
export const SHAKE_SPEED = 2600.0;
export const SLEEP_AFTER = 40.0;
export const MAX_SPEED = 2600.0;

export const Mood = Object.freeze({
  IDLE: "idle", WALK: "walk", CROUCH: "crouch", AIR: "air", LAND: "land",
  RIDE: "ride", HELD: "held", SLEEP: "sleep", ACT: "act",
});

export const GNSS_ACTS = Object.freeze({ gps: 3.0, jam: 3.0, spoof: 3.0, pps: 5.2, cesium: 4.0, holdover: 5.0 });
export const ACT_PACKS = Object.freeze({ gnss: GNSS_ACTS });
export const ACT_CHANCE = 0.12;
export const REACTIONS = Object.freeze({ yawn: 1.4, wave: 1.0, look: 2.4 });
// What the pet does on its own, between everything else; "oops" only for a skin drawn from behind.
export const EVERYDAY_ACTS = Object.freeze({
  groom: 2.6, stretch: 1.8, chase: 2.4, fly: 3.6, sneeze: 1.3, sit: 4.0, oops: 4.4, saw: 5.4,
});
export const OOPS_BACK = Object.freeze([0.3, 1.9]);
export const SAW_FROM = 0.8;
export const SAW_UNTIL = 4.4;
export const POKES_TO_FUME = 5;
export const POKE_WINDOW_S = 2.0;
export const SPEECH_S = 3.5;
export const EVERYDAY_CHANCE = 0.2;
export const DIZZY_SPEED = 1500.0;
export const DIZZY_S = 1.8;
export const PURR_AFTER = 0.5;
export const LOOK_CHANCE = 0.1;
export const STALK_SPEED = 22.0;

export class Mulberry32 {
  constructor(seed) { this.state = seed >>> 0; }
  random() {
    this.state = (this.state + 0x6D2B79F5) >>> 0;
    let t = this.state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  uniform(a, b) { return a + (b - a) * this.random(); }
  choice(seq) { return seq[Math.floor(this.random() * seq.length)]; }
}

export class MathRandom {
  random() { return Math.random(); }
  uniform(a, b) { return a + (b - a) * Math.random(); }
  choice(seq) { return seq[Math.floor(Math.random() * seq.length)]; }
}

const dist = (dx, dy) => Math.sqrt(dx * dx + dy * dy);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export class Ledge {
  constructor(left, right, y, key = null) { Object.assign(this, { left, right, y, key }); }
  holds(x, slack = 6.0) { return this.left - slack <= x && x <= this.right + slack; }
}

export class Bounds {
  constructor(left, top, right, bottom) { Object.assign(this, { left, top, right, bottom }); }
}

export class Particle {
  constructor(kind, x, y, vx, vy, life) { Object.assign(this, { kind, x, y, vx, vy, life }); }
}

export function ballistic([sx, sy], [tx, ty], lift) {
  const apex = Math.min(sy, ty) - lift;
  const vy = -Math.sqrt(2.0 * GRAVITY * (sy - apex));
  const rise = -vy / GRAVITY;
  const fall = Math.sqrt(2.0 * (ty - apex) / GRAVITY);
  return [(tx - sx) / (rise + fall), vy];
}

export class Pet {
  constructor(x, y, { rng = new MathRandom(), skin = CLAWD, acts = {} } = {}) {
    Object.assign(this, {
      x, y, rng, vx: 0.0, vy: 0.0, mood: Mood.AIR, facing: 1, ledge: null, timer: 0.0, clock: 0.0,
      walkPhase: 0.0, squash: 0.0, blink: 0.0, pouncing: false, launch: [0.0, 0.0], aimY: null,
      plannedY: null, rideOffset: [4.0, 0.0], quiet: 0.0, emotion: null, feelingLeft: 0.0, beat: 0.0,
      particles: [], skin, nextBlink: 3.0, cursor: [0.0, 0.0], cursorStill: 0.0, cursorSpeed: 0.0,
      cursorVelocity: [0.0, 0.0], act: null, actTime: 0.0, actBeat: 0.0, lastAct: null, thinking: false,
      acts: { ...acts }, gaze: null, gazeLeft: 0.0, away: 0.0, target: null, ear: 0.0, nextEar: 5.0,
      dizzy: 0.0, vyAtLanding: 0.0, petting: 0.0, purrBeat: 0.0, speech: null, speechLeft: 0.0, pokes: [],
    });
  }

  get purring() {
    return this.petting >= PURR_AFTER && [Mood.IDLE, Mood.SLEEP, Mood.LAND, Mood.ACT].includes(this.mood);
  }

  get breathing() {
    if (this.mood === Mood.SLEEP) return 0.06 * Math.sin(this.clock * 1.3);
    if (this.mood === Mood.IDLE || (this.mood === Mood.ACT && this.act === "sit")) {
      return (this.purring ? 0.05 : 0.025) * Math.sin(this.clock * (this.purring ? 3.2 : 2.2));
    }
    return 0.0;
  }

  get tailUp() {
    if (this.mood === Mood.SLEEP) return false;
    if (this.purring || this.mood === Mood.AIR) return true;
    const rate = this.expression === "angry" ? 6.0 : (this.expression === "sad" ? 0.0 : 1.6);
    return rate > 0.0 && Math.trunc(this.clock * rate) % 2 === 0;
  }

  get flyAt() {
    if (this.act !== "fly" || this.actTime >= 3.0) return null;
    const t = this.actTime;
    return [30.0 * Math.cos(t * 2.6), -this.skin.height - 26.0 + 10.0 * Math.sin(t * 5.3)];
  }

  get facingAway() {
    return this.act === "oops" && OOPS_BACK[0] <= this.actTime && this.actTime < OOPS_BACK[1];
  }

  get expression() {
    if (this.emotion !== null || this.act === null) return this.emotion;
    const t = this.actTime;
    if ((this.act === "jam" && 0.8 <= t && t < 2.2) || (this.act === "spoof" && t >= 1.8)) return "angry";
    if (this.act === "holdover" && t >= 1.0) return "sad";
    if (this.act === "oops" && t >= OOPS_BACK[1]) return "embarrassed";
    return null;
  }

  get eyesClosed() {
    if (this.mood === Mood.SLEEP || this.blink > 0.0 || this.purring) return true;
    if (this.act === "yawn" && this.actTime < 0.9) return true;
    if (this.act === "stretch" && this.actTime < 1.3) return true;
    if (this.act === "sneeze" && 0.3 <= this.actTime && this.actTime < 0.9) return true;
    return this.act === "groom" && Math.trunc(this.actTime * 3) % 2 === 1;
  }

  get armsRaised() {
    if (this.mood === Mood.HELD || this.mood === Mood.RIDE || (this.mood === Mood.AIR && this.vy < 0)) return true;
    if (this.act === "wave") return Math.trunc(this.actTime * 6) % 2 === 0;
    if (this.act === "yawn") return this.actTime < 0.9;
    if (this.act === "stretch") return 0.4 <= this.actTime && this.actTime < 1.3;
    if (this.act === "fly") return 3.0 <= this.actTime && this.actTime < 3.5;
    if (this.act === "saw") {
      return SAW_FROM <= this.actTime && this.actTime < SAW_UNTIL && Math.trunc(this.actTime * 7) % 2 === 0;
    }
    return this.act === "cesium" || (this.act === "gps" && this.actTime >= 1.2);
  }

  look() {
    if (this.act === "spoof" && this.actTime >= 0.4) return -1;
    if (this.act === "oops" && this.actTime >= OOPS_BACK[1]) return -1;
    if (this.act === "saw") return this.facing;
    const fly = this.flyAt;
    if (fly !== null) return Math.abs(fly[0]) < 10 ? 0 : (fly[0] > 0 ? 1 : -1);
    if (this.act === "look") return [-1, 1, 0][Math.trunc(this.actTime / 0.8) % 3];
    if (this.gaze !== null) {
      const dx = this.gaze[0] - this.x;
      return Math.abs(dx) < 24 ? 0 : (dx > 0 ? 1 : -1);
    }
    const [cx, cy] = this.cursor;
    if (dist(cx - this.x, cy - this.y) < 900) {
      const dx = cx - this.x;
      return Math.abs(dx) < 24 ? 0 : (dx > 0 ? 1 : -1);
    }
    return this.facing;
  }

  step(dt, ledges, cursor, bounds) {
    dt = Math.max(0.0, Math.min(dt, 0.05));
    this.clock += dt;
    this.trackCursor(dt, cursor);
    this.tickFace(dt);
    this.tickParticles(dt);
    this.squash *= Math.exp(-10.0 * dt);
    if (Math.abs(this.squash) < 0.01) this.squash = 0.0;
    this.tickFeeling(dt);
    this.tickPetting(dt);
    if (this.speechLeft > 0.0) {
      this.speechLeft = Math.max(0.0, this.speechLeft - dt);
      if (this.speechLeft === 0.0) this.speech = null;
    }
    if (this.dizzy > 0.0) this.dizzy = Math.max(0.0, this.dizzy - dt);
    if (this.mood !== Mood.ACT) this.act = null;
    const handler = {
      [Mood.IDLE]: this.grounded, [Mood.WALK]: this.grounded, [Mood.SLEEP]: this.sleeping,
      [Mood.CROUCH]: this.crouching, [Mood.AIR]: this.flying, [Mood.LAND]: this.landing,
      [Mood.RIDE]: this.riding, [Mood.HELD]: this.held, [Mood.ACT]: this.acting,
    }[this.mood];
    handler.call(this, dt, ledges);
    this.keepInside(bounds, ledges);
  }

  grab() {
    this.mood = Mood.HELD;
    this.ledge = null;
    this.pouncing = false;
    this.vx = this.vy = 0.0;
    this.say("!");
  }

  dragTo(x, y) { this.x = x; this.y = y; }

  throw(vx, vy) {
    this.vx = clamp(vx, -MAX_SPEED, MAX_SPEED);
    this.vy = clamp(vy, -MAX_SPEED, MAX_SPEED);
    this.mood = Mood.AIR;
    this.pouncing = false;
    this.aimY = null;
  }

  cheer() {
    this.say("heart");
    if ([Mood.IDLE, Mood.WALK, Mood.SLEEP, Mood.LAND].includes(this.mood)) {
      this.vy = -520.0;
      this.vx = 0.0;
      this.mood = Mood.AIR;
      this.ledge = null;
    }
  }

  // A click on it. One too many, too fast, and it is fed up -- cross, and tells you so.
  poke() {
    this.pokes = this.pokes.filter((at) => this.clock - at < POKE_WINDOW_S);
    this.pokes.push(this.clock);
    if (this.pokes.length < POKES_TO_FUME) return;
    this.pokes = [];
    this.speech = this.skin.fedUp;
    this.speechLeft = SPEECH_S;
    this.feel("angry", SPEECH_S);
  }

  watch(x, y, seconds = 1.5) { this.gaze = [x, y]; this.gazeLeft = seconds; }

  startle() {
    if (![Mood.IDLE, Mood.WALK, Mood.LAND, Mood.SLEEP, Mood.ACT].includes(this.mood)) return;
    this.act = null;
    this.say("!");
    this.squash = -0.2;
    this.leave(0.0, -330.0);
  }

  perform(act) {
    const known = Object.hasOwn(this.acts, act) || Object.hasOwn(REACTIONS, act) || Object.hasOwn(EVERYDAY_ACTS, act);
    if (act === "oops" && !this.skin.back) return false;
    if (!known || this.ledge === null || ![Mood.IDLE, Mood.WALK, Mood.LAND].includes(this.mood)) return false;
    this.act = act; this.actTime = 0.0; this.actBeat = 0.0;
    this.mood = Mood.ACT;
    this.vx = 0.0;
    if (act === "wave") this.say("hi");
    return true;
  }

  endAct() {
    this.act = null;
    this.mood = Mood.IDLE;
    this.timer = this.rng.uniform(0.8, 2.0);
  }

  acting(dt, ledges) {
    if (!this.stand(ledges)) return;
    const before = this.actTime;
    this.actTime += dt;
    const t = this.actTime;
    const act = this.act;
    const reached = (moment) => before < moment && moment <= t;
    if (act === "yawn") {
      this.squash = t < 0.9 ? -0.16 : 0.1;
      if (t >= REACTIONS.yawn) {
        this.act = null;
        this.mood = Mood.SLEEP;
        this.timer = 0.0;
      }
      return;
    }
    if (act === "gps" && reached(GNSS_ACTS.gps)) {
      this.endAct();
      this.say("FIX");
      this.cheer();
      return;
    }
    if (act === "jam" && t >= 2.2) {
      this.walkPhase += dt * 16.0;
    } else if (act === "spoof") {
      if (reached(1.8)) this.say("!");
      if (reached(2.4)) {
        for (const side of [-1, 1]) {
          this.particles.push(new Particle("puff", ghostOffset(2.4), -this.skin.height / 2, side * 50.0, -30.0, 0.6));
        }
      }
    } else if (act === "pps" && t >= 1.0 && Math.floor(before) < Math.floor(t)) {
      this.squash = 0.12;
      this.particles.push(new Particle("ring", 0.0, 0.0, 0.0, 0.0, 0.4));
    } else if (act === "holdover" && t >= 1.0) {
      this.actBeat -= dt;
      if (this.actBeat <= 0.0) {
        this.actBeat = 0.8;
        const side = this.rng.choice([-1, 1]);
        this.particles.push(new Particle("tear", side * (this.skin.width / 2 + 3), -this.skin.height * 0.85,
          side * 18.0, 40.0, 0.6));
      }
    } else if (act === "groom") {
      this.squash = 0.05 * Math.sin(t * 12.0);
    } else if (act === "stretch") {
      this.squash = t < 1.2 ? 0.3 * Math.sin(Math.PI * Math.min(t, 1.2) / 1.2) : -0.1;
    } else if (act === "chase") {
      this.walkPhase += dt * 14.0;
      if (Math.floor(before / 0.22) < Math.floor(t / 0.22)) this.facing = -this.facing;
      if (reached(EVERYDAY_ACTS.chase - 0.05)) {
        this.say("?");
        this.dizzy = 1.0;
      }
    } else if (act === "fly") {
      if (reached(2.8)) this.squash = 0.25;
      if (reached(3.0)) {
        this.squash = -0.25;
        this.say("!");
        const fx = 30.0 * Math.cos(3.0 * 2.6);
        const fy = -this.skin.height - 26.0;
        this.particles.push(new Particle("puff", fx, fy, 0.0, -20.0, 0.5));
      }
    } else if (act === "sneeze") {
      if (t < 0.8) this.squash = -0.18 * Math.min(1.0, t / 0.6);
      if (reached(0.8)) {
        this.squash = 0.28;
        for (const spread of [-25.0, 0.0, 25.0]) {
          this.particles.push(new Particle("puff", this.facing * this.skin.width / 2, -this.skin.height * 0.55,
            this.facing * 110.0, spread, 0.5));
        }
      }
    } else if (act === "sit") {
      this.squash = Math.max(this.squash, 0.1);
    } else if (act === "oops") {
      const [backFrom, backUntil] = OOPS_BACK;
      if (backFrom <= t && t < backUntil) this.squash = 0.05 * Math.sin(t * 11.0);
      if (reached(backUntil)) {
        this.squash = -0.2;
        this.say("!");
      } else if (t >= backUntil) {
        this.squash = Math.max(this.squash, 0.12);
        this.actBeat -= dt;
        if (this.actBeat <= 0.0) {
          this.actBeat = 0.7;
          const side = this.rng.choice([-1, 1]);
          this.particles.push(new Particle("tear", side * (this.skin.width / 2 + 2), -this.skin.height * 0.9,
            side * 12.0, 30.0, 0.6));
        }
      }
    } else if (act === "saw") {
      const [plankX, plankY] = sawPlankAt(this);
      if (SAW_FROM <= t && t < SAW_UNTIL) {
        this.actBeat -= dt;
        if (this.actBeat <= 0.0) {
          this.actBeat = 0.12;
          const x = plankX + this.rng.uniform(-3, 3);
          this.particles.push(new Particle("dust", x, plankY + 4, this.rng.uniform(-25, 25), 70.0, 0.5));
        }
      }
      if (reached(SAW_UNTIL)) {
        this.particles.push(new Particle("puff", plankX, plankY, 0.0, -20.0, 0.5));
        this.say("heart");
      }
    }
    const length = Object.hasOwn(this.acts, act) ? this.acts[act]
      : (Object.hasOwn(REACTIONS, act) ? REACTIONS[act] : (EVERYDAY_ACTS[act] ?? 0.0));
    if (t >= length) this.endAct();
  }

  feel(emotion, seconds) {
    if (this.mood === Mood.ACT) this.endAct();
    if (emotion === this.emotion) {
      this.feelingLeft = Math.max(this.feelingLeft, seconds);
      return;
    }
    this.emotion = emotion;
    this.feelingLeft = seconds;
    this.beat = 0.0;
    if (this.mood === Mood.SLEEP) {
      this.mood = Mood.IDLE;
      this.timer = 1.0;
    }
    if (emotion === "angry") this.say("vein");
    else if (emotion === "sad") this.pouncing = false;
  }

  tickFeeling(dt) {
    if (this.emotion === null) return;
    this.feelingLeft -= dt;
    if (this.feelingLeft <= 0.0) {
      this.emotion = null;
      return;
    }
    const grounded = [Mood.IDLE, Mood.WALK, Mood.LAND].includes(this.mood);
    if (this.emotion === "sad") this.squash = Math.max(this.squash, 0.08);
    this.beat -= dt;
    if (this.beat > 0.0) return;
    if (this.emotion === "sad") {
      this.beat = 0.9;
      for (const [row, column] of this.skin.tears) {
        const [x, y] = this.skin.offset(row, column);
        this.particles.push(new Particle("tear", x, y, 0.0, 70.0, 0.6));
      }
    } else if (this.emotion === "angry") {
      this.beat = 0.45;
      for (const side of [-1, 1]) {
        const x = side * this.skin.width * 0.4;
        const y = -this.skin.height * 0.83;
        this.particles.push(new Particle("puff", x, y, side * 30.0, -60.0, 0.6));
      }
      if (grounded) {
        this.squash = 0.25;
        this.leave(0.0, -260.0);
      }
    } else if (this.emotion === "happy") {
      this.beat = 0.8;
      this.cheer();
    }
  }

  trackCursor(dt, cursor) {
    const [px, py] = this.cursor;
    const [cx, cy] = cursor;
    const moved = dist(cx - px, cy - py);
    if (dt > 0) {
      this.cursorVelocity = [(cx - px) / dt, (cy - py) / dt];
      this.cursorSpeed = moved / dt;
    }
    this.cursorStill = moved < 1.0 ? this.cursorStill + dt : 0.0;
    this.quiet = moved < 1.0 ? this.quiet + dt : 0.0;
    this.cursor = [cx, cy];
    if (this.gaze !== null) {
      this.gazeLeft -= dt;
      if (this.gazeLeft <= 0.0) this.gaze = null;
    }
    if (dist(cx - this.x, cy - this.y) > 400) this.away += dt;
  }

  tickFace(dt) {
    if (this.blink > 0.0) this.blink = Math.max(0.0, this.blink - dt);
    this.nextBlink -= dt;
    if (this.nextBlink <= 0.0) {
      this.blink = 0.12;
      this.nextBlink = this.rng.uniform(2.0, 6.0);
    }
    if (this.ear > 0.0) this.ear = Math.max(0.0, this.ear - dt);
    this.nextEar -= dt;
    if (this.nextEar <= 0.0) {
      this.ear = 0.18;
      this.nextEar = this.rng.uniform(4.0, 10.0);
    }
  }

  // The cursor moving over it, gently, is a hand stroking it: it purrs and stays put for it.
  tickPetting(dt) {
    const [cx, cy] = this.cursor;
    const over = dist(cx - this.x, cy - (this.y - this.skin.height / 2)) < this.skin.width * 0.6;
    const stroking = over && this.cursorStill < 0.3 && this.cursorSpeed < 900.0;
    if (stroking && [Mood.IDLE, Mood.WALK, Mood.SLEEP, Mood.LAND, Mood.ACT].includes(this.mood)) {
      this.petting += dt;
    } else if (!over) {
      this.petting = Math.max(0.0, this.petting - dt * 2.0);
    }
    if (!this.purring) return;
    if (this.mood === Mood.WALK) this.mood = Mood.IDLE;
    this.timer = Math.max(this.timer, 1.0);
    this.purrBeat -= dt;
    if (this.purrBeat <= 0.0) {
      this.purrBeat = 0.9;
      this.say(this.rng.choice(["heart", "~"]));
    }
  }

  tickParticles(dt) {
    for (const p of this.particles) {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.life -= dt;
    }
    this.particles = this.particles.filter((p) => p.life > 0.0);
  }

  say(kind) {
    const drift = this.rng.uniform(-10, 10);
    const top = -this.skin.height - 8.0;
    this.particles.push(new Particle(kind, this.rng.uniform(-6, 6), top, drift, -26.0, 1.1));
  }

  grounded(dt, ledges) {
    if (!this.stand(ledges)) return;
    if (this.mood === Mood.WALK) {
      this.walkPhase += dt * 9.0;
      this.x += this.facing * WALK_SPEED * (PACE[this.emotion] ?? 1.0) * dt;
      const ledge = this.ledge;
      if (this.x <= ledge.left + EDGE_MARGIN || this.x >= ledge.right - EDGE_MARGIN) {
        this.atEdge(ledge);
        if (this.mood === Mood.AIR) return;
      }
    }
    this.timer -= dt;
    if (this.dizzy > 0.0) return;
    if (this.quiet > SLEEP_AFTER && this.mood === Mood.IDLE) {
      this.perform("yawn");
      return;
    }
    const [cx, cy] = this.cursor;
    if (dist(cx - this.x, cy - this.y) < 220) {
      if (this.away > 4.0 && this.emotion === null) {
        this.away = 0.0;
        this.perform("wave");
        return;
      }
      this.away = 0.0;
    }
    if (this.timer <= 0.0) this.decide(ledges);
  }

  atEdge(ledge) {
    const roll = this.rng.random();
    if (roll < 0.55) {
      this.facing = this.x >= ledge.right - EDGE_MARGIN ? -1 : 1;
      this.x = Math.min(Math.max(this.x, ledge.left + EDGE_MARGIN), ledge.right - EDGE_MARGIN);
    } else if (roll < 0.8) {
      this.leave(this.facing * WALK_SPEED * 1.6, -380.0);
    } else {
      this.leave(this.facing * WALK_SPEED, 0.0);
    }
  }

  leave(vx, vy, aimY = null) {
    this.vx = vx; this.vy = vy;
    this.mood = Mood.AIR;
    this.ledge = null;
    this.aimY = aimY;
  }

  decide(ledges) {
    this.timer = this.rng.uniform(1.2, 3.5);
    const [cx, cy] = this.cursor;
    const near = dist(cx - this.x, cy - this.y) < 600;
    const reachable = this.y - cy <= MAX_JUMP_UP && Math.abs(cx - this.x) <= MAX_JUMP_ACROSS;
    let pounceChance = near && this.cursorStill > 0.6 ? 0.45 : 0.12;
    if (this.emotion === "angry") pounceChance = near ? 0.6 : 0.25;
    let roll = this.rng.random();
    if (this.emotion !== "sad" && reachable && roll < pounceChance) {
      this.aim([cx + this.rideOffset[0], cy + this.rideOffset[1]], true);
      return;
    }
    if (this.emotion === null && this.rng.random() < LOOK_CHANCE) {
      this.perform("look");
      return;
    }
    if (this.emotion === null && this.rng.random() < EVERYDAY_CHANCE) {
      const choices = Object.keys(EVERYDAY_ACTS)
        .filter((act) => act !== this.lastAct && (act !== "oops" || this.skin.back));
      this.perform(this.rng.choice(choices));
      this.lastAct = this.act;
      if (this.act !== null) return;
    }
    if (this.emotion === null && this.rng.random() < ACT_CHANCE) {
      const choices = Object.keys(this.acts).filter((act) => act !== this.lastAct);
      if (choices.length) {
        this.perform(this.rng.choice(choices));
        this.lastAct = this.act;
        if (this.act !== null) return;
      }
    }
    roll = this.rng.random();
    if (this.emotion === "sad" && roll < 0.7) {
      this.mood = Mood.IDLE;
    } else if (roll < 0.4) {
      this.mood = Mood.WALK;
      this.facing = this.rng.choice([-1, 1]);
    } else if (roll < 0.65) {
      this.mood = Mood.IDLE;
    } else {
      const target = this.pickLedge(ledges);
      if (target === null) this.mood = Mood.WALK;
      else this.aim(target);
    }
  }

  pickLedge(ledges) {
    const options = [];
    for (const ledge of ledges) {
      if (ledge === this.ledge || ledge.right - ledge.left < 2 * EDGE_MARGIN) continue;
      const tx = this.rng.uniform(ledge.left + EDGE_MARGIN, ledge.right - EDGE_MARGIN);
      if (Math.abs(tx - this.x) <= MAX_JUMP_ACROSS && this.y - ledge.y <= MAX_JUMP_UP) options.push([tx, ledge.y]);
    }
    return options.length ? this.rng.choice(options) : null;
  }

  aim(target, pounce = false) {
    this.launch = ballistic([this.x, this.y], target, this.rng.uniform(50.0, 110.0));
    this.plannedY = target[1];
    this.target = target;
    this.facing = target[0] >= this.x ? 1 : -1;
    this.pouncing = pounce;
    this.mood = Mood.CROUCH;
    this.timer = pounce ? 0.35 : 0.18;
    if (pounce && this.stalks) this.timer = 0.9;
    if (pounce) this.say("!");
  }

  get stalks() { return this.skin.stalks; }

  crouching(dt, ledges) {
    if (!this.stand(ledges)) return;
    const creeping = this.pouncing && this.stalks;
    this.squash = creeping ? 0.32 : 0.22;
    if (creeping) {
      this.x += this.facing * STALK_SPEED * dt;
      this.walkPhase += dt * 5.0;
    }
    this.timer -= dt;
    if (this.timer <= 0.0) {
      this.squash = -0.2;
      if (creeping && this.target !== null) this.launch = ballistic([this.x, this.y], this.target, 60.0);
      this.leave(this.launch[0], this.launch[1], this.plannedY);
    }
  }

  sleeping(dt, ledges) {
    if (!this.stand(ledges)) return;
    this.timer -= dt;
    if (this.timer <= 0.0) {
      this.particles.push(new Particle("z", 10.0, -this.skin.height - 4.0, 14.0, -22.0, 1.6));
      this.timer = 1.1;
    }
    const [cx, cy] = this.cursor;
    if (this.quiet === 0.0 && dist(cx - this.x, cy - this.y) < 250) {
      this.mood = Mood.IDLE;
      this.timer = 0.6;
      this.say("!");
    }
  }

  stand(ledges) {
    const ledge = Pet.refresh(this.ledge, ledges);
    if (ledge !== null && this.ledge !== null && ledge.key !== null) this.x += ledge.left - this.ledge.left;
    if (ledge === null || !ledge.holds(this.x)) {
      this.leave(0.0, 0.0);
      return false;
    }
    this.ledge = ledge;
    this.y = ledge.y;
    return true;
  }

  static refresh(ledge, ledges) {
    if (ledge === null) return null;
    if (ledge.key === null) {
      return ledges.find((item) => item.key === null && item.y === ledge.y && item.left === ledge.left) ?? null;
    }
    return ledges.find((item) => item.key === ledge.key) ?? null;
  }

  flying(dt, ledges) {
    const before = this.y;
    this.vy = Math.min(this.vy + GRAVITY * dt, MAX_SPEED);
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    if (this.pouncing && this.nearCursor()) {
      this.catchCursor();
      return;
    }
    if (this.vy <= 0.0) return;
    const landing = ledges.filter((ledge) => before <= ledge.y + 0.5 && this.y >= ledge.y && ledge.holds(this.x)
      && (this.aimY === null || ledge.y >= this.aimY - 1.0));
    if (landing.length) {
      const ledge = landing.reduce((best, item) => (item.y < best.y ? item : best));
      this.y = ledge.y;
      this.ledge = ledge;
      this.squash = Math.min(0.35, 0.12 + this.vy / 4000.0);
      this.vyAtLanding = this.vy;
      this.vx = this.vy = 0.0;
      if (this.pouncing) this.say("?");
      const hard = this.vyAtLanding >= DIZZY_SPEED;
      this.pouncing = false;
      this.aimY = null;
      this.mood = Mood.LAND;
      this.timer = 0.25;
      if (hard) {
        this.dizzy = DIZZY_S;
        this.timer = DIZZY_S;
      }
    }
  }

  held(dt) { this.walkPhase += dt * 16.0; }

  nearCursor() {
    const [cx, cy] = this.cursor;
    const [ox, oy] = this.rideOffset;
    return dist(cx + ox - this.x, cy + oy - this.y) <= CATCH_RADIUS;
  }

  catchCursor() {
    this.mood = Mood.RIDE;
    this.pouncing = false;
    this.aimY = null;
    this.timer = this.rng.uniform(2.5, 6.0);
    this.vx = this.vy = 0.0;
    this.say("heart");
  }

  landing(dt, ledges) {
    if (!this.stand(ledges)) return;
    this.timer -= dt;
    if (this.timer <= 0.0) {
      this.mood = Mood.IDLE;
      this.timer = this.rng.uniform(0.6, 1.8);
    }
  }

  riding(dt) {
    const [cx, cy] = this.cursor;
    this.x = cx + this.rideOffset[0];
    this.y = cy + this.rideOffset[1];
    this.walkPhase += dt * 14.0;
    if (this.cursorSpeed > SHAKE_SPEED) {
      const [vx, vy] = this.cursorVelocity;
      this.say("!");
      this.throw(vx * 0.6, vy * 0.6 - 200.0);
      return;
    }
    this.timer -= dt;
    if (this.timer <= 0.0) this.leave(this.rng.choice([-1, 1]) * 160.0, -420.0);
  }

  keepInside(bounds, ledges) {
    if (this.x < bounds.left + EDGE_MARGIN) {
      this.x = bounds.left + EDGE_MARGIN;
      this.vx = Math.abs(this.vx) * 0.5;
      this.facing = 1;
    } else if (this.x > bounds.right - EDGE_MARGIN) {
      this.x = bounds.right - EDGE_MARGIN;
      this.vx = -Math.abs(this.vx) * 0.5;
      this.facing = -1;
    }
    if (this.y < bounds.top + 40 && this.vy < 0) {
      this.y = bounds.top + 40;
      this.vy = 0.0;
    }
    if (this.y > bounds.bottom + 200) {
      const floor = ledges.length ? ledges.reduce((best, item) => (item.y > best.y ? item : best)) : null;
      this.x = floor ? (floor.left + floor.right) / 2 : (bounds.left + bounds.right) / 2;
      this.y = bounds.top + 60;
      this.vx = this.vy = 0.0;
      this.mood = Mood.AIR;
      this.ledge = null;
    }
  }
}

// -- pixel art ---------------------------------------------------------------------------

export const PIXEL = 4;

const BODY = [
  "..oooooooooooo..", "..oooooooooooo..", "..oooooooooooo..", "..oooooooooooo..",
  "oooooooooooooooo", "..oooooooooooo..", "..oooooooooooo..",
];
const ARMS_UP = [
  "..oooooooooooo..", "..oooooooooooo..", "o.oooooooooooo.o", "oooooooooooooooo",
  "..oooooooooooo..", "..oooooooooooo..", "..oooooooooooo..",
];
const LEGS = {
  stand: ["...d.d....d.d...", "...d.d....d.d..."],
  walk_a: ["...d.d....d.d...", "...d......d....."],
  walk_b: ["...d.d....d.d...", ".....d......d..."],
  tuck: ["...d.d....d.d...", "................"],
  dangle: ["..d..d....d..d..", ".d....d..d....d."],
};
const SAD_BODY = [
  "..oooooooooooo..", "..oooooooooooo..", "..oooooooooooo..", "..oooooooooooo..",
  "..oooooooooooo..", "oooooooooooooooo", "..oooooooooooo..",
];
const EYE_COLUMNS = [4, 11];
const PACE = { sad: 0.45, angry: 1.8 };
const BROWS = { sad: [1, -1], angry: [-1, 1] };

function clawdFace(rows, pet) {
  const shift = pet.expression in BROWS ? 0 : pet.look();
  const brows = BROWS[pet.expression] ?? [0, 0];
  EYE_COLUMNS.forEach((column, i) => {
    const x = column + shift;
    rows[3][x] = "k";
    if (!pet.eyesClosed) rows[2][x + brows[i]] = "k";
  });
}

const CAT_BODY = [
  ".K..........K.", ".KK........KK.", ".KHKKKKKKKKHK.", "KKKKKKKKKKKKKK", "KKKKKKKKKKKKKK",
  "KKKKSSSSSSKKKK", "KKKSWWWWWWSKKK", ".KKSSWWWWSSKK.", "..KKSSSSSSKK..", "..KKKKZZKKKK..",
  ".CKHKKZZKKKKC.", "...KKKKKKKK..K",
];
const CAT_ARMS_UP = [...CAT_BODY.slice(0, 8), "C.KKSSSSSSKK.C", ".KKKKKZZKKKKK.", "..KHKKZZKKKK..", CAT_BODY[11]];
const CAT_GROOM = [...CAT_BODY.slice(0, 7), ".KKSSWWWWSSKC.", "..KKSSSSSSKKC.", "..KKKKZZKKKK..",
  ".CKHKKZZKKKK..", CAT_BODY[11]];
// From behind -- and the pink thong it did not mean anyone to see.
const CAT_BACK = [
  ".K..........K.", ".KK........KK.", ".KKKKKKKKKKKK.", "KKKKKKKKKKKKKK", "KKKKKKKKKKKKKK",
  "KKKKKKKKKKKKKK", "KKKKKKKKKKKKKK", ".KKKKKKKKKKKK.", "..KKKKKKKKKK..", "..KPPKKKKPPK..",
  ".CKKKPPPPKKKC.", "...KKKPPKKK..K",
];
const CAT_SAD_BODY = [...CAT_BODY.slice(0, 9), ".KKKKKZZKKKKK.", ".CKHKKZZKKKKC.", CAT_BODY[11]];
const CAT_LEGS = {
  stand: ["...KK....KK.K.", "..KKK....KKK.."],
  walk_a: ["..KK.....KK.K.", ".KK.......KK.."],
  walk_b: ["....KK..KK..K.", "....KK..KK...."],
  tuck: ["...KKK..KKK.K.", ".............."],
  dangle: ["..K..K..K..KK.", ".K....KK....K."],
};
const CAT_EYES = [2, 10];
const CAT_MOUTH = {
  sad: ["KKKSSMMMMSSKKK", ".KKSMSSSSMSKK."],
  angry: ["KKKSWMWWMWSKKK", ".KKSSWWWWSSKK."],
};

function catFace(rows, pet) {
  if (pet.eyesClosed) {
    for (const left of CAT_EYES) rows[4][left] = rows[4][left + 1] = "H";
  } else if (pet.expression === "sad") {
    rows[3][3] = rows[4][2] = rows[3][10] = rows[4][11] = "W";
  } else if (pet.expression === "angry") {
    rows[3][2] = rows[4][3] = rows[3][11] = rows[4][10] = "W";
  } else {
    const shift = pet.look();
    for (const left of CAT_EYES) rows[4][left + shift] = rows[4][left + 1 + shift] = "W";
  }
  if (pet.expression === "embarrassed") {
    rows[5][2] = rows[5][3] = rows[5][10] = rows[5][11] = "b";
    rows[7][6] = rows[7][7] = "M";
  }
  if (pet.expression in CAT_MOUTH) {
    [rows[6], rows[7]] = CAT_MOUTH[pet.expression].map((row) => [...row]);
  } else if (pet.act === "groom" && Math.trunc(pet.actTime * 6) % 2 === 0) {
    rows[7][7] = "p";
  } else if (pet.act === "sneeze" && pet.actTime < 0.8) {
    rows[6][6] = rows[6][7] = "M";
  }
  if (pet.dizzy > 0.0 && !pet.eyesClosed) {
    for (const left of CAT_EYES) {
      rows[3][left] = rows[4][left + 1] = "W";
      rows[4][left] = rows[3][left + 1] = "K";
    }
  }
  if (pet.ear > 0.0) {
    rows[0][1] = ".";
    rows[0][2] = "K";
  }
}

export class Skin {
  constructor(spec) {
    Object.assign(this, {
      outline: false, stalks: false, groom: null, tail: null, back: null, fedUp: "Hey! Stop poking me!", ...spec,
    });
  }
  get columns() { return this.body[0].length; }
  get rows() { return this.body.length + 2; }
  get height() { return this.rows * PIXEL; }
  get width() { return this.columns * PIXEL; }
  offset(row, column) { return [(column + 0.5 - this.columns / 2) * PIXEL, -(this.rows - row) * PIXEL]; }
}

export const CLAWD = new Skin({
  key: "clawd", name: "Clawd", body: BODY, armsUp: ARMS_UP, sadBody: SAD_BODY, legs: LEGS, face: clawdFace,
  palette: { o: "#D97757", r: "#C8432B", d: "#B4583A", k: "#1E1E1E" },
  angry: { o: "r" }, tears: [[3.5, 4.0], [3.5, 11.0]],
});
export const CAT = new Skin({
  key: "cat", name: "Amir Latex", body: CAT_BODY, armsUp: CAT_ARMS_UP, sadBody: CAT_SAD_BODY, legs: CAT_LEGS,
  face: catFace,
  palette: {
    K: "#16161C", H: "#3C4150", S: "#E8B99A", p: "#E4775F", W: "#FFFFFF", M: "#7A2E34", Z: "#D5DAE3", C: "#9EA7B8",
    P: "#FF5FA8", b: "#F2789A",
  },
  angry: { S: "p" }, tears: [[5.0, 2.5], [5.0, 11.5]], outline: true, stalks: true,
  groom: CAT_GROOM, tail: [[11, 13], [10, 13]], back: CAT_BACK, fedUp: "אין לי מפתח לשירותים פה!",
});
export const SKINS = { clawd: CLAWD, cat: CAT };

export function skinNamed(key) { return SKINS[key] ?? CLAWD; }

export function frame(pet) {
  const skin = pet.skin;
  if (pet.facingAway && skin.back) {
    return [...skin.back, ...skin.legs.stand];
  }
  let body;
  if (pet.act === "groom" && skin.groom) body = skin.groom;
  else if (pet.armsRaised) body = skin.armsUp;
  else body = pet.expression === "sad" ? skin.sadBody : skin.body;
  let rows = body.map((row) => [...row]);
  skin.face(rows, pet);
  if (pet.expression === "angry") rows = rows.map((row) => row.map((cell) => skin.angry[cell] ?? cell));
  rows.push(...skin.legs[legsFor(pet)].map((row) => [...row]));
  if (skin.tail && pet.tailUp) {
    const [[downRow, downCol], [upRow, upCol]] = skin.tail;
    if (rows[downRow][downCol] !== "." && rows[upRow][upCol] === ".") {
      rows[upRow][upCol] = rows[downRow][downCol];
      rows[downRow][downCol] = ".";
    }
  }
  return rows.map((row) => row.join(""));
}

function legsFor(pet) {
  const stepping = () => (Math.trunc(pet.walkPhase) % 2 === 0 ? "walk_a" : "walk_b");
  if ([Mood.WALK, Mood.RIDE, Mood.HELD].includes(pet.mood)) return stepping();
  if (pet.mood === Mood.AIR) return pet.vy < 0 ? "tuck" : "dangle";
  if (pet.mood === Mood.CROUCH && pet.pouncing && pet.stalks) return stepping();
  if (pet.act === "jam" && pet.actTime >= 2.2) return stepping();
  if (pet.act === "pps" && pet.actTime >= 1.0 && pet.actTime % 1.0 < 0.15) return "walk_a";
  if (pet.act === "chase") return stepping();
  if (pet.act === "sit" || pet.act === "groom" || (pet.act === "stretch" && pet.actTime < 1.2)) return "tuck";
  return "stand";
}

export const PROPS = {
  satellite: [["b.s.b", "bbsbb", "b.s.b"], { b: "#3E6FD8", s: "#9AA3B0" }],
  antenna: [["y...y", ".y.y.", "..g..", "..g..", "..g.."], { y: "#F2B632", g: "#6B6B6B" }],
  zigzag: [["x...x...x", ".x.x.x.x.", "..x...x.."], { x: "#E0442E" }],
  clock: [[".ggggg.", "gwwwwwg", "gwwkwwg", "gwwkkwg", "gwwwwwg", "gwwwwwg", ".ggggg."],
    { g: "#6B6B6B", w: "#FFFFFF", k: "#1E1E1E" }],
  plank: [["wwwwdwwwwwww", "dddddddddddd", "wwwwwwwdwwww"], { w: "#C8925A", d: "#A0703F" }],
  half_plank: [["wwwwdw", "dddddd", "wwwwww"], { w: "#C8925A", d: "#A0703F" }],
  saw: [["hhh.........", "hhbbbbbbbbbb", "hh.t.t.t.t.t"], { h: "#B5482F", b: "#C9CED6", t: "#8A929E" }],
};
// The saw held from the other side: handle towards the pet either way.
PROPS.saw_left = [PROPS.saw[0].map((row) => [...row].reverse().join("")), PROPS.saw[1]];

// Where the plank of a "saw" act is, from the feet: lifted off the floor to its paws, on the side it faces.
export function sawPlankAt(pet) {
  const lift = Math.min(1.0, pet.actTime / SAW_FROM);
  return [pet.facing * 30.0, -4.0 - lift * (pet.skin.height * 0.45 - 4.0)];
}

export function ghostOffset(t) { return -Math.min(40.0, Math.max(0.0, t - 0.4) * 30.0); }

export function actView(pet) {
  const view = {
    props: [], labels: [], shift: {}, ghost: null, noise: null, wave: null, orbit: null, bars: null, dots: null,
    fly: null, stars: null, speech: null,
  };
  const act = pet.act;
  const t = pet.actTime;
  const top = -pet.skin.height;
  if (pet.thinking && act === null && pet.mood !== Mood.SLEEP) view.dots = 1 + (Math.trunc(pet.clock * 3) % 3);
  if (pet.dizzy > 0.0) view.stars = pet.clock * 6.0;
  if (pet.speech) view.speech = pet.speech;
  const fly = pet.flyAt;
  if (fly !== null) view.fly = [fly[0], fly[1], Math.trunc(pet.clock * 20) % 2 === 0];
  if (act === "gps") {
    if (t < 1.2) {
      view.props.push(["satellite", 0.0, top - 44, Math.min(1.0, t)]);
      view.labels.push(["SEARCH", 0.0, top - 22, "dim"]);
    } else {
      for (const [x, y] of [[-40, 38], [0, 48], [40, 38]]) view.props.push(["satellite", x, top - y, 1.0]);
      view.props.push(["antenna", 0.0, top - 10, 1.0]);
      view.bars = Math.min(4, Math.trunc((t - 1.2) / 0.4));
    }
  } else if (act === "jam") {
    if (t < 0.8) {
      view.props.push(["zigzag", -38.0, top - 16, 1.0], ["zigzag", 38.0, top - 4, 1.0]);
    } else if (t < 2.2) {
      const seed = Math.trunc(t * 12);
      view.noise = seed;
      for (const row of [2, 3, 5, 6]) view.shift[row] = ((seed * (row + 3)) % 5) - 2;
      view.labels.push(["JAMMED", 0.0, top - 22, "bad"]);
    }
  } else if (act === "spoof") {
    if (0.4 <= t && t < 2.4) view.ghost = ghostOffset(t);
    if (1.8 <= t && t < 2.4) view.labels.push(["SPOOF!", 0.0, top - 34, "bad"]);
  } else if (act === "pps") {
    view.wave = t >= 1.0 ? Math.trunc(t) % 5 : -1;
    view.labels.push([`1PPS #${Math.trunc(t)}`, 0.0, top - 44, "dim"]);
  } else if (act === "cesium") {
    view.orbit = t * 4.0;
    if (t >= 2.0) view.labels.push(["Cs-133", 0.0, top - 46, "dim"]);
  } else if (act === "holdover") {
    if (t < 1.0) {
      view.props.push(["satellite", 0.0, top - 40, 0.3]);
      view.labels.push(["NO SV", 0.0, top - 20, "bad"]);
    } else {
      view.props.push(["clock", 0.0, top * 0.45, 1.0]);
      const text = t < 3.0 ? "HOLDOVER" : `+${((t - 1.0) * 1.6).toFixed(1)} ns`;
      view.labels.push([text, 0.0, top - 20, t < 3.0 ? "dim" : "bad"]);
    }
  } else if (act === "saw") {
    const [x, y] = sawPlankAt(pet);
    if (t < SAW_UNTIL) {
      view.props.push(["plank", x, y, 1.0]);
      if (t >= SAW_FROM) {
        const stroke = 7.0 * Math.sin((t - SAW_FROM) * 14.0);
        view.props.push([pet.facing > 0 ? "saw" : "saw_left", x + stroke, y - 8.0, 1.0]);
      }
    } else {
      const fall = t - SAW_UNTIL;
      const drop = Math.min(-4.0, y + 160.0 * fall * fall);
      for (const side of [-1, 1]) view.props.push(["half_plank", x + side * (9.0 + 25.0 * fall), drop, 1.0]);
    }
  }
  return view;
}
