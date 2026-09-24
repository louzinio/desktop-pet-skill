"""The desktop pet: physics, behaviour and pixel art, with no GUI dependency.

An adapter feeds it the world once per frame -- `Pet.step(dt, ledges, cursor, bounds)` --
and draws `frame(pet)`, `act_view(pet)` and `pet.particles`. See references/core-api.md.
This file is meant to be vendored into the host app and edited there.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

GRAVITY = 2200.0
WALK_SPEED = 70.0
MAX_JUMP_UP = 420.0
MAX_JUMP_ACROSS = 700.0
EDGE_MARGIN = 14.0
CATCH_RADIUS = 30.0
SHAKE_SPEED = 2600.0
SLEEP_AFTER = 40.0
MAX_SPEED = 2600.0


class Mood(Enum):
    IDLE = "idle"
    WALK = "walk"
    CROUCH = "crouch"
    AIR = "air"
    LAND = "land"
    RIDE = "ride"
    HELD = "held"
    SLEEP = "sleep"
    ACT = "act"


GNSS_ACTS: dict[str, float] = {
    "gps": 3.0,
    "jam": 3.0,
    "spoof": 3.0,
    "pps": 5.2,
    "cesium": 4.0,
    "holdover": 5.0,
}
ACT_PACKS: dict[str, dict[str, float]] = {"gnss": GNSS_ACTS}
ACT_CHANCE = 0.12
REACTIONS: dict[str, float] = {"yawn": 1.4, "wave": 1.0, "look": 2.4}
LOOK_CHANCE = 0.1
STALK_SPEED = 22.0


class Rng(Protocol):
    def random(self) -> float: ...
    def uniform(self, a: float, b: float) -> float: ...
    def choice(self, seq): ...


class Mulberry32:
    """A tiny seeded generator with the same output in every language.

    The JavaScript core ships the same one, so a seeded pet behaves identically in both;
    tests/reference_trace.json is how a port to another language proves it is faithful.
    """

    def __init__(self, seed: int) -> None:
        self._state = seed & 0xFFFFFFFF

    def random(self) -> float:
        self._state = (self._state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self._state
        t = _imul(t ^ (t >> 15), t | 1)
        t ^= (t + _imul(t ^ (t >> 7), t | 61)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.random()

    def choice(self, seq):
        return seq[int(self.random() * len(seq))]


def _imul(a: int, b: int) -> int:
    return (a * b) & 0xFFFFFFFF


def _dist(dx: float, dy: float) -> float:
    return math.sqrt(dx * dx + dy * dy)


@dataclass
class Ledge:
    left: float
    right: float
    y: float
    key: object = None

    def holds(self, x: float, slack: float = 6.0) -> bool:
        return self.left - slack <= x <= self.right + slack


@dataclass
class Bounds:
    left: float
    top: float
    right: float
    bottom: float


@dataclass
class Particle:
    kind: str
    x: float
    y: float
    vx: float
    vy: float
    life: float


@dataclass
class Pet:
    x: float
    y: float
    rng: Rng = field(default_factory=random.Random)
    vx: float = 0.0
    vy: float = 0.0
    mood: Mood = Mood.AIR
    facing: int = 1
    ledge: Ledge | None = None
    timer: float = 0.0
    clock: float = 0.0
    walk_phase: float = 0.0
    squash: float = 0.0
    blink: float = 0.0
    pouncing: bool = False
    launch: tuple[float, float] = (0.0, 0.0)
    aim_y: float | None = None
    _planned_y: float | None = None
    ride_offset: tuple[float, float] = (4.0, 0.0)
    quiet: float = 0.0
    emotion: str | None = None
    feeling_left: float = 0.0
    _beat: float = 0.0
    particles: list[Particle] = field(default_factory=list)
    skin: Skin = field(default_factory=lambda: CLAWD)
    _next_blink: float = 3.0
    _cursor: tuple[float, float] = (0.0, 0.0)
    _cursor_still: float = 0.0
    _cursor_speed: float = 0.0
    _cursor_velocity: tuple[float, float] = (0.0, 0.0)
    act: str | None = None
    act_time: float = 0.0
    _act_beat: float = 0.0
    _last_act: str | None = None
    thinking: bool = False
    acts: dict[str, float] = field(default_factory=dict)
    _gaze: tuple[float, float] | None = None
    _gaze_left: float = 0.0
    _away: float = 0.0
    _target: tuple[float, float] | None = None

    @property
    def expression(self) -> str | None:
        if self.emotion is not None or self.act is None:
            return self.emotion
        t = self.act_time
        if (self.act == "jam" and 0.8 <= t < 2.2) or (self.act == "spoof" and t >= 1.8):
            return "angry"
        if self.act == "holdover" and t >= 1.0:
            return "sad"
        return None

    @property
    def eyes_closed(self) -> bool:
        return self.mood is Mood.SLEEP or self.blink > 0.0 or (self.act == "yawn" and self.act_time < 0.9)

    @property
    def arms_raised(self) -> bool:
        if self.mood in (Mood.HELD, Mood.RIDE) or (self.mood is Mood.AIR and self.vy < 0):
            return True
        if self.act == "wave":
            return int(self.act_time * 6) % 2 == 0
        if self.act == "yawn":
            return self.act_time < 0.9
        return self.act == "cesium" or (self.act == "gps" and self.act_time >= 1.2)

    def look(self) -> int:
        if self.act == "spoof" and self.act_time >= 0.4:
            return -1
        if self.act == "look":
            return (-1, 1, 0)[int(self.act_time / 0.8) % 3]
        if self._gaze is not None:
            dx = self._gaze[0] - self.x
            return 0 if abs(dx) < 24 else (1 if dx > 0 else -1)
        cx, cy = self._cursor
        if _dist(cx - self.x, cy - self.y) < 900:
            dx = cx - self.x
            return 0 if abs(dx) < 24 else (1 if dx > 0 else -1)
        return self.facing

    def step(self, dt: float, ledges: list[Ledge], cursor: tuple[float, float], bounds: Bounds) -> None:
        dt = max(0.0, min(dt, 0.05))
        self.clock += dt
        self._track_cursor(dt, cursor)
        self._tick_face(dt)
        self._tick_particles(dt)
        self.squash *= math.exp(-10.0 * dt)
        if abs(self.squash) < 0.01:
            self.squash = 0.0
        self._tick_feeling(dt)
        if self.mood is not Mood.ACT:
            self.act = None

        handler = {
            Mood.IDLE: self._grounded,
            Mood.WALK: self._grounded,
            Mood.SLEEP: self._sleeping,
            Mood.CROUCH: self._crouching,
            Mood.AIR: self._flying,
            Mood.LAND: self._landing,
            Mood.RIDE: self._riding,
            Mood.HELD: self._held,
            Mood.ACT: self._acting,
        }[self.mood]
        handler(dt, ledges)
        self._keep_inside(bounds, ledges)

    def grab(self) -> None:
        self.mood = Mood.HELD
        self.ledge = None
        self.pouncing = False
        self.vx = self.vy = 0.0
        self._say("!")

    def drag_to(self, x: float, y: float) -> None:
        self.x, self.y = x, y

    def throw(self, vx: float, vy: float) -> None:
        self.vx = max(-MAX_SPEED, min(MAX_SPEED, vx))
        self.vy = max(-MAX_SPEED, min(MAX_SPEED, vy))
        self.mood = Mood.AIR
        self.pouncing = False
        self.aim_y = None

    def cheer(self) -> None:
        self._say("heart")
        if self.mood in (Mood.IDLE, Mood.WALK, Mood.SLEEP, Mood.LAND):
            self.vy = -520.0
            self.vx = 0.0
            self.mood = Mood.AIR
            self.ledge = None

    def watch(self, x: float, y: float, seconds: float = 1.5) -> None:
        self._gaze = (x, y)
        self._gaze_left = seconds

    def startle(self) -> None:
        if self.mood not in (Mood.IDLE, Mood.WALK, Mood.LAND, Mood.SLEEP, Mood.ACT):
            return
        self.act = None
        self._say("!")
        self.squash = -0.2
        self._leave(0.0, -330.0)

    def perform(self, act: str) -> bool:
        known = act in self.acts or act in REACTIONS
        if not known or self.ledge is None or self.mood not in (Mood.IDLE, Mood.WALK, Mood.LAND):
            return False
        self.act, self.act_time, self._act_beat = act, 0.0, 0.0
        self.mood = Mood.ACT
        self.vx = 0.0
        if act == "wave":
            self._say("hi")
        return True

    def _end_act(self) -> None:
        self.act = None
        self.mood = Mood.IDLE
        self.timer = self.rng.uniform(0.8, 2.0)

    def _acting(self, dt: float, ledges: list[Ledge]) -> None:
        if not self._stand(ledges):
            return
        before = self.act_time
        self.act_time += dt
        t = self.act_time
        act = self.act

        def reached(moment: float) -> bool:
            return before < moment <= t

        if act == "yawn":
            self.squash = -0.16 if t < 0.9 else 0.1
            if t >= REACTIONS["yawn"]:
                self.act = None
                self.mood = Mood.SLEEP
                self.timer = 0.0
            return
        if act == "gps" and reached(GNSS_ACTS["gps"]):
            self._end_act()
            self._say("FIX")
            self.cheer()
            return
        if act == "jam" and t >= 2.2:
            self.walk_phase += dt * 16.0
        elif act == "spoof":
            if reached(1.8):
                self._say("!")
            if reached(2.4):
                for side in (-1, 1):
                    self.particles.append(Particle("puff", ghost_offset(2.4), -self.skin.height / 2,
                                                   side * 50.0, -30.0, 0.6))
        elif act == "pps" and t >= 1.0 and math.floor(before) < math.floor(t):
            self.squash = 0.12
            self.particles.append(Particle("ring", 0.0, 0.0, 0.0, 0.0, 0.4))
        elif act == "holdover" and t >= 1.0:
            self._act_beat -= dt
            if self._act_beat <= 0.0:
                self._act_beat = 0.8
                side = self.rng.choice((-1, 1))
                self.particles.append(Particle("tear", side * (self.skin.width / 2 + 3),
                                               -self.skin.height * 0.85, side * 18.0, 40.0, 0.6))
        if t >= self.acts.get(act, REACTIONS.get(act, 0.0)):
            self._end_act()

    def feel(self, emotion: str, seconds: float) -> None:
        if self.mood is Mood.ACT:
            self._end_act()
        if emotion == self.emotion:
            self.feeling_left = max(self.feeling_left, seconds)
            return
        self.emotion = emotion
        self.feeling_left = seconds
        self._beat = 0.0
        if self.mood is Mood.SLEEP:
            self.mood = Mood.IDLE
            self.timer = 1.0
        if emotion == "angry":
            self._say("vein")
        elif emotion == "sad":
            self.pouncing = False

    def _tick_feeling(self, dt: float) -> None:
        if self.emotion is None:
            return
        self.feeling_left -= dt
        if self.feeling_left <= 0.0:
            self.emotion = None
            return
        grounded = self.mood in (Mood.IDLE, Mood.WALK, Mood.LAND)
        if self.emotion == "sad":
            self.squash = max(self.squash, 0.08)
        self._beat -= dt
        if self._beat > 0.0:
            return
        if self.emotion == "sad":
            self._beat = 0.9
            for row, column in self.skin.tears:
                x, y = self.skin.offset(row, column)
                self.particles.append(Particle("tear", x, y, 0.0, 70.0, 0.6))
        elif self.emotion == "angry":
            self._beat = 0.45
            for side in (-1, 1):
                x, y = side * self.skin.width * 0.4, -self.skin.height * 0.83
                self.particles.append(Particle("puff", x, y, side * 30.0, -60.0, 0.6))
            if grounded:
                self.squash = 0.25
                self._leave(0.0, -260.0)
        elif self.emotion == "happy":
            self._beat = 0.8
            self.cheer()

    def _track_cursor(self, dt: float, cursor: tuple[float, float]) -> None:
        px, py = self._cursor
        cx, cy = cursor
        moved = _dist(cx - px, cy - py)
        if dt > 0:
            self._cursor_velocity = ((cx - px) / dt, (cy - py) / dt)
            self._cursor_speed = moved / dt
        self._cursor_still = self._cursor_still + dt if moved < 1.0 else 0.0
        self.quiet = self.quiet + dt if moved < 1.0 else 0.0
        self._cursor = cursor
        if self._gaze is not None:
            self._gaze_left -= dt
            if self._gaze_left <= 0.0:
                self._gaze = None
        if _dist(cx - self.x, cy - self.y) > 400:
            self._away += dt

    def _tick_face(self, dt: float) -> None:
        if self.blink > 0.0:
            self.blink = max(0.0, self.blink - dt)
        self._next_blink -= dt
        if self._next_blink <= 0.0:
            self.blink = 0.12
            self._next_blink = self.rng.uniform(2.0, 6.0)

    def _tick_particles(self, dt: float) -> None:
        for particle in self.particles:
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.life -= dt
        self.particles = [p for p in self.particles if p.life > 0.0]

    def _say(self, kind: str) -> None:
        drift = self.rng.uniform(-10, 10)
        top = -self.skin.height - 8.0
        self.particles.append(Particle(kind, self.rng.uniform(-6, 6), top, drift, -26.0, 1.1))

    def _grounded(self, dt: float, ledges: list[Ledge]) -> None:
        if not self._stand(ledges):
            return
        if self.mood is Mood.WALK:
            self.walk_phase += dt * 9.0
            self.x += self.facing * WALK_SPEED * _PACE.get(self.emotion, 1.0) * dt
            ledge = self.ledge
            if self.x <= ledge.left + EDGE_MARGIN or self.x >= ledge.right - EDGE_MARGIN:
                self._at_edge(ledge)
                if self.mood is Mood.AIR:
                    return
        self.timer -= dt
        if self.quiet > SLEEP_AFTER and self.mood is Mood.IDLE:
            self.perform("yawn")
            return
        cx, cy = self._cursor
        if _dist(cx - self.x, cy - self.y) < 220:
            if self._away > 4.0 and self.emotion is None:
                self._away = 0.0
                self.perform("wave")
                return
            self._away = 0.0
        if self.timer <= 0.0:
            self._decide(ledges)

    def _at_edge(self, ledge: Ledge) -> None:
        roll = self.rng.random()
        if roll < 0.55:
            self.facing = -1 if self.x >= ledge.right - EDGE_MARGIN else 1
            self.x = min(max(self.x, ledge.left + EDGE_MARGIN), ledge.right - EDGE_MARGIN)
        elif roll < 0.8:
            self._leave(self.facing * WALK_SPEED * 1.6, -380.0)
        else:
            self._leave(self.facing * WALK_SPEED, 0.0)

    def _leave(self, vx: float, vy: float, aim_y: float | None = None) -> None:
        self.vx, self.vy = vx, vy
        self.mood = Mood.AIR
        self.ledge = None
        self.aim_y = aim_y

    def _decide(self, ledges: list[Ledge]) -> None:
        self.timer = self.rng.uniform(1.2, 3.5)
        cx, cy = self._cursor
        near = _dist(cx - self.x, cy - self.y) < 600
        reachable = self.y - cy <= MAX_JUMP_UP and abs(cx - self.x) <= MAX_JUMP_ACROSS
        pounce_chance = 0.45 if near and self._cursor_still > 0.6 else 0.12
        if self.emotion == "angry":
            pounce_chance = 0.6 if near else 0.25
        roll = self.rng.random()
        if self.emotion != "sad" and reachable and roll < pounce_chance:
            self._aim((cx + self.ride_offset[0], cy + self.ride_offset[1]), pounce=True)
            return
        if self.emotion is None and self.rng.random() < LOOK_CHANCE:
            self.perform("look")
            return
        if self.emotion is None and self.rng.random() < ACT_CHANCE:
            choices = [act for act in self.acts if act != self._last_act]
            if choices:
                self.perform(self.rng.choice(choices))
                self._last_act = self.act
                if self.act is not None:
                    return
        roll = self.rng.random()
        if self.emotion == "sad" and roll < 0.7:
            self.mood = Mood.IDLE
        elif roll < 0.4:
            self.mood = Mood.WALK
            self.facing = self.rng.choice((-1, 1))
        elif roll < 0.65:
            self.mood = Mood.IDLE
        else:
            target = self._pick_ledge(ledges)
            if target is None:
                self.mood = Mood.WALK
            else:
                self._aim(target)

    def _pick_ledge(self, ledges: list[Ledge]) -> tuple[float, float] | None:
        options = []
        for ledge in ledges:
            if ledge is self.ledge or ledge.right - ledge.left < 2 * EDGE_MARGIN:
                continue
            tx = self.rng.uniform(ledge.left + EDGE_MARGIN, ledge.right - EDGE_MARGIN)
            if abs(tx - self.x) <= MAX_JUMP_ACROSS and self.y - ledge.y <= MAX_JUMP_UP:
                options.append((tx, ledge.y))
        return self.rng.choice(options) if options else None

    def _aim(self, target: tuple[float, float], pounce: bool = False) -> None:
        self.launch = ballistic((self.x, self.y), target, self.rng.uniform(50.0, 110.0))
        self._planned_y = target[1]
        self._target = target
        self.facing = 1 if target[0] >= self.x else -1
        self.pouncing = pounce
        self.mood = Mood.CROUCH
        self.timer = 0.35 if pounce else 0.18
        if pounce and self.stalks:
            self.timer = 0.9
        if pounce:
            self._say("!")

    @property
    def stalks(self) -> bool:
        return self.skin.stalks

    def _crouching(self, dt: float, ledges: list[Ledge]) -> None:
        if not self._stand(ledges):
            return
        creeping = self.pouncing and self.stalks
        self.squash = 0.32 if creeping else 0.22
        if creeping:
            self.x += self.facing * STALK_SPEED * dt
            self.walk_phase += dt * 5.0
        self.timer -= dt
        if self.timer <= 0.0:
            self.squash = -0.2
            if creeping and self._target is not None:
                self.launch = ballistic((self.x, self.y), self._target, 60.0)
            self._leave(*self.launch, aim_y=self._planned_y)

    def _sleeping(self, dt: float, ledges: list[Ledge]) -> None:
        if not self._stand(ledges):
            return
        self.timer -= dt
        if self.timer <= 0.0:
            self.particles.append(Particle("z", 10.0, -self.skin.height - 4.0, 14.0, -22.0, 1.6))
            self.timer = 1.1
        cx, cy = self._cursor
        if self.quiet == 0.0 and _dist(cx - self.x, cy - self.y) < 250:
            self.mood = Mood.IDLE
            self.timer = 0.6
            self._say("!")

    def _stand(self, ledges: list[Ledge]) -> bool:
        ledge = self._refresh(self.ledge, ledges)
        if ledge is not None and self.ledge is not None and ledge.key is not None:
            self.x += ledge.left - self.ledge.left
        if ledge is None or not ledge.holds(self.x):
            self._leave(0.0, 0.0)
            return False
        self.ledge = ledge
        self.y = ledge.y
        return True

    @staticmethod
    def _refresh(ledge: Ledge | None, ledges: list[Ledge]) -> Ledge | None:
        if ledge is None:
            return None
        if ledge.key is None:
            return next((item for item in ledges if item.key is None and item.y == ledge.y
                         and item.left == ledge.left), None)
        return next((item for item in ledges if item.key is ledge.key), None)

    def _flying(self, dt: float, ledges: list[Ledge]) -> None:
        before = self.y
        self.vy = min(self.vy + GRAVITY * dt, MAX_SPEED)
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.pouncing and self._near_cursor():
            self._catch()
            return
        if self.vy <= 0.0:
            return
        landing = [
            ledge for ledge in ledges
            if before <= ledge.y + 0.5 and self.y >= ledge.y and ledge.holds(self.x)
            and (self.aim_y is None or ledge.y >= self.aim_y - 1.0)
        ]
        if landing:
            ledge = min(landing, key=lambda item: item.y)
            self.y = ledge.y
            self.ledge = ledge
            self.squash = min(0.35, 0.12 + self.vy / 4000.0)
            self.vx = self.vy = 0.0
            if self.pouncing:
                self._say("?")
            self.pouncing = False
            self.aim_y = None
            self.mood = Mood.LAND
            self.timer = 0.25

    def _held(self, dt: float, ledges: list[Ledge]) -> None:
        self.walk_phase += dt * 16.0

    def _near_cursor(self) -> bool:
        cx, cy = self._cursor
        ox, oy = self.ride_offset
        return _dist(cx + ox - self.x, cy + oy - self.y) <= CATCH_RADIUS

    def _catch(self) -> None:
        self.mood = Mood.RIDE
        self.pouncing = False
        self.aim_y = None
        self.timer = self.rng.uniform(2.5, 6.0)
        self.vx = self.vy = 0.0
        self._say("heart")

    def _landing(self, dt: float, ledges: list[Ledge]) -> None:
        if not self._stand(ledges):
            return
        self.timer -= dt
        if self.timer <= 0.0:
            self.mood = Mood.IDLE
            self.timer = self.rng.uniform(0.6, 1.8)

    def _riding(self, dt: float, ledges: list[Ledge]) -> None:
        cx, cy = self._cursor
        self.x, self.y = cx + self.ride_offset[0], cy + self.ride_offset[1]
        self.walk_phase += dt * 14.0
        if self._cursor_speed > SHAKE_SPEED:
            vx, vy = self._cursor_velocity
            self._say("!")
            self.throw(vx * 0.6, vy * 0.6 - 200.0)
            return
        self.timer -= dt
        if self.timer <= 0.0:
            self._leave(self.rng.choice((-1, 1)) * 160.0, -420.0)

    def _keep_inside(self, bounds: Bounds, ledges: list[Ledge]) -> None:
        if self.x < bounds.left + EDGE_MARGIN:
            self.x = bounds.left + EDGE_MARGIN
            self.vx = abs(self.vx) * 0.5
            self.facing = 1
        elif self.x > bounds.right - EDGE_MARGIN:
            self.x = bounds.right - EDGE_MARGIN
            self.vx = -abs(self.vx) * 0.5
            self.facing = -1
        if self.y < bounds.top + 40 and self.vy < 0:
            self.y = bounds.top + 40
            self.vy = 0.0
        if self.y > bounds.bottom + 200:
            floor = max(ledges, key=lambda item: item.y) if ledges else None
            self.x = (floor.left + floor.right) / 2 if floor else (bounds.left + bounds.right) / 2
            self.y = bounds.top + 60
            self.vx = self.vy = 0.0
            self.mood = Mood.AIR
            self.ledge = None


def ballistic(start: tuple[float, float], target: tuple[float, float], lift: float) -> tuple[float, float]:
    sx, sy = start
    tx, ty = target
    apex = min(sy, ty) - lift
    vy = -math.sqrt(2.0 * GRAVITY * (sy - apex))
    rise = -vy / GRAVITY
    fall = math.sqrt(2.0 * (ty - apex) / GRAVITY)
    return (tx - sx) / (rise + fall), vy


PIXEL = 4

BODY = (
    "..oooooooooooo..",
    "..oooooooooooo..",
    "..oooooooooooo..",
    "..oooooooooooo..",
    "oooooooooooooooo",
    "..oooooooooooo..",
    "..oooooooooooo..",
)
ARMS_UP = (
    "..oooooooooooo..",
    "..oooooooooooo..",
    "o.oooooooooooo.o",
    "oooooooooooooooo",
    "..oooooooooooo..",
    "..oooooooooooo..",
    "..oooooooooooo..",
)
LEGS = {
    "stand": ("...d.d....d.d...", "...d.d....d.d..."),
    "walk_a": ("...d.d....d.d...", "...d......d....."),
    "walk_b": ("...d.d....d.d...", ".....d......d..."),
    "tuck": ("...d.d....d.d...", "................"),
    "dangle": ("..d..d....d..d..", ".d....d..d....d."),
}
SAD_BODY = (
    "..oooooooooooo..",
    "..oooooooooooo..",
    "..oooooooooooo..",
    "..oooooooooooo..",
    "..oooooooooooo..",
    "oooooooooooooooo",
    "..oooooooooooo..",
)
EYE_COLUMNS = (4, 11)
_PACE = {"sad": 0.45, "angry": 1.8}
_BROWS = {"sad": (1, -1), "angry": (-1, 1)}


def _clawd_face(rows: list[list[str]], pet: Pet) -> None:
    shift = 0 if pet.expression in _BROWS else pet.look()
    for column, brow in zip(EYE_COLUMNS, _BROWS.get(pet.expression, (0, 0)), strict=True):
        x = column + shift
        rows[3][x] = "k"
        if not pet.eyes_closed:
            rows[2][x + brow] = "k"


CAT_BODY = (
    ".K..........K.",
    ".KK........KK.",
    ".KHKKKKKKKKHK.",
    "KKKKKKKKKKKKKK",
    "KKKKKKKKKKKKKK",
    "KKKKSSSSSSKKKK",
    "KKKSWWWWWWSKKK",
    ".KKSSWWWWSSKK.",
    "..KKSSSSSSKK..",
    "..KKKKZZKKKK..",
    ".CKHKKZZKKKKC.",
    "...KKKKKKKK..K",
)
CAT_ARMS_UP = (
    *CAT_BODY[:8],
    "C.KKSSSSSSKK.C",
    ".KKKKKZZKKKKK.",
    "..KHKKZZKKKK..",
    CAT_BODY[11],
)
CAT_SAD_BODY = (
    *CAT_BODY[:9],
    ".KKKKKZZKKKKK.",
    ".CKHKKZZKKKKC.",
    CAT_BODY[11],
)
CAT_LEGS = {
    "stand": ("...KK....KK.K.", "..KKK....KKK.."),
    "walk_a": ("..KK.....KK.K.", ".KK.......KK.."),
    "walk_b": ("....KK..KK..K.", "....KK..KK...."),
    "tuck": ("...KKK..KKK.K.", ".............."),
    "dangle": ("..K..K..K..KK.", ".K....KK....K."),
}
_CAT_EYES = (2, 10)
_CAT_MOUTH = {
    "sad": ("KKKSSMMMMSSKKK", ".KKSMSSSSMSKK."),
    "angry": ("KKKSWMWWMWSKKK", ".KKSSWWWWSSKK."),
}


def _cat_face(rows: list[list[str]], pet: Pet) -> None:
    if pet.eyes_closed:
        for left in _CAT_EYES:
            rows[4][left] = rows[4][left + 1] = "H"
    elif pet.expression == "sad":
        rows[3][3], rows[4][2], rows[3][10], rows[4][11] = "W", "W", "W", "W"
    elif pet.expression == "angry":
        rows[3][2], rows[4][3], rows[3][11], rows[4][10] = "W", "W", "W", "W"
    else:
        shift = pet.look()
        for left in _CAT_EYES:
            rows[4][left + shift] = rows[4][left + 1 + shift] = "W"
    if pet.expression in _CAT_MOUTH:
        rows[6], rows[7] = (list(row) for row in _CAT_MOUTH[pet.expression])


@dataclass(frozen=True)
class Skin:
    key: str
    name: str
    body: tuple[str, ...]
    arms_up: tuple[str, ...]
    sad_body: tuple[str, ...]
    legs: dict[str, tuple[str, str]]
    face: Callable[[list[list[str]], Pet], None]
    palette: dict[str, str]
    angry: dict[str, str]
    tears: tuple[tuple[float, float], ...]
    outline: bool = False
    stalks: bool = False

    @property
    def columns(self) -> int:
        return len(self.body[0])

    @property
    def rows(self) -> int:
        return len(self.body) + 2

    @property
    def height(self) -> float:
        return self.rows * PIXEL

    @property
    def width(self) -> float:
        return self.columns * PIXEL

    def offset(self, row: float, column: float) -> tuple[float, float]:
        return (column + 0.5 - self.columns / 2) * PIXEL, -(self.rows - row) * PIXEL


CLAWD = Skin(
    key="clawd",
    name="Clawd",
    body=BODY,
    arms_up=ARMS_UP,
    sad_body=SAD_BODY,
    legs=LEGS,
    face=_clawd_face,
    palette={"o": "#D97757", "r": "#C8432B", "d": "#B4583A", "k": "#1E1E1E"},
    angry={"o": "r"},
    tears=((3.5, 4.0), (3.5, 11.0)),
)
CAT = Skin(
    key="cat",
    name="Amir Latex",
    body=CAT_BODY,
    arms_up=CAT_ARMS_UP,
    sad_body=CAT_SAD_BODY,
    legs=CAT_LEGS,
    face=_cat_face,
    palette={
        "K": "#16161C", "H": "#3C4150", "S": "#E8B99A", "p": "#E4775F",
        "W": "#FFFFFF", "M": "#7A2E34", "Z": "#D5DAE3", "C": "#9EA7B8",
    },
    angry={"S": "p"},
    tears=((5.0, 2.5), (5.0, 11.5)),
    outline=True,
    stalks=True,
)
SKINS: dict[str, Skin] = {skin.key: skin for skin in (CLAWD, CAT)}


def skin_named(key: str) -> Skin:
    return SKINS.get(key, CLAWD)


def frame(pet: Pet) -> list[str]:
    skin = pet.skin
    body = skin.arms_up if pet.arms_raised else (skin.sad_body if pet.expression == "sad" else skin.body)
    rows = [list(row) for row in body]
    skin.face(rows, pet)
    if pet.expression == "angry":
        rows = [[skin.angry.get(cell, cell) for cell in row] for row in rows]
    rows.extend(list(row) for row in skin.legs[_legs(pet)])
    return ["".join(row) for row in rows]


def _legs(pet: Pet) -> str:
    if pet.mood in (Mood.WALK, Mood.RIDE, Mood.HELD):
        return "walk_a" if int(pet.walk_phase) % 2 == 0 else "walk_b"
    if pet.mood is Mood.AIR:
        return "tuck" if pet.vy < 0 else "dangle"
    if pet.mood is Mood.CROUCH and pet.pouncing and pet.stalks:
        return "walk_a" if int(pet.walk_phase) % 2 == 0 else "walk_b"
    if pet.act == "jam" and pet.act_time >= 2.2:
        return "walk_a" if int(pet.walk_phase) % 2 == 0 else "walk_b"
    if pet.act == "pps" and pet.act_time >= 1.0 and pet.act_time % 1.0 < 0.15:
        return "walk_a"
    return "stand"


PROPS: dict[str, tuple[tuple[str, ...], dict[str, str]]] = {
    "satellite": (("b.s.b", "bbsbb", "b.s.b"), {"b": "#3E6FD8", "s": "#9AA3B0"}),
    "antenna": (("y...y", ".y.y.", "..g..", "..g..", "..g.."), {"y": "#F2B632", "g": "#6B6B6B"}),
    "zigzag": (("x...x...x", ".x.x.x.x.", "..x...x.."), {"x": "#E0442E"}),
    "clock": (
        (".ggggg.", "gwwwwwg", "gwwkwwg", "gwwkkwg", "gwwwwwg", "gwwwwwg", ".ggggg."),
        {"g": "#6B6B6B", "w": "#FFFFFF", "k": "#1E1E1E"},
    ),
}


@dataclass
class ActView:
    props: list[tuple[str, float, float, float]] = field(default_factory=list)
    labels: list[tuple[str, float, float, str]] = field(default_factory=list)
    shift: dict[int, int] = field(default_factory=dict)
    ghost: float | None = None
    noise: int | None = None
    wave: int | None = None
    orbit: float | None = None
    bars: int | None = None
    dots: int | None = None


def ghost_offset(t: float) -> float:
    return -min(40.0, max(0.0, t - 0.4) * 30.0)


def act_view(pet: Pet) -> ActView:
    view = ActView()
    act, t, top = pet.act, pet.act_time, -pet.skin.height
    if pet.thinking and act is None and pet.mood is not Mood.SLEEP:
        view.dots = 1 + int(pet.clock * 3) % 3
    if act == "gps":
        if t < 1.2:
            view.props.append(("satellite", 0.0, top - 44, min(1.0, t)))
            view.labels.append(("SEARCH", 0.0, top - 22, "dim"))
        else:
            view.props += [("satellite", x, top - y, 1.0) for x, y in ((-40, 38), (0, 48), (40, 38))]
            view.props.append(("antenna", 0.0, top - 10, 1.0))
            view.bars = min(4, int((t - 1.2) / 0.4))
    elif act == "jam":
        if t < 0.8:
            view.props += [("zigzag", -38.0, top - 16, 1.0), ("zigzag", 38.0, top - 4, 1.0)]
        elif t < 2.2:
            seed = int(t * 12)
            view.noise = seed
            view.shift = {row: (seed * (row + 3)) % 5 - 2 for row in (2, 3, 5, 6)}
            view.labels.append(("JAMMED", 0.0, top - 22, "bad"))
    elif act == "spoof":
        if 0.4 <= t < 2.4:
            view.ghost = ghost_offset(t)
        if 1.8 <= t < 2.4:
            view.labels.append(("SPOOF!", 0.0, top - 34, "bad"))
    elif act == "pps":
        view.wave = int(t) % 5 if t >= 1.0 else -1
        view.labels.append((f"1PPS #{int(t)}", 0.0, top - 44, "dim"))
    elif act == "cesium":
        view.orbit = t * 4.0
        if t >= 2.0:
            view.labels.append(("Cs-133", 0.0, top - 46, "dim"))
    elif act == "holdover":
        if t < 1.0:
            view.props.append(("satellite", 0.0, top - 40, 0.3))
            view.labels.append(("NO SV", 0.0, top - 20, "bad"))
        else:
            view.props.append(("clock", 0.0, top * 0.45, 1.0))
            text = "HOLDOVER" if t < 3.0 else f"+{(t - 1.0) * 1.6:.1f} ns"
            view.labels.append((text, 0.0, top - 20, "dim" if t < 3.0 else "bad"))
    return view
