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
EVERYDAY_ACTS: dict[str, float] = {
    "groom": 2.6,
    "stretch": 1.8,
    "chase": 2.4,
    "fly": 3.6,
    "sneeze": 1.3,
    "sit": 4.0,
    "oops": 4.4,
    "saw": 5.4,
}
"""What the pet does on its own, between everything else: washes a paw,
stretches, chases its tail, swats at a fly, sneezes, sits and loafs, picks
up a plank and saws it in two for the love of it ("saw") - and, for a skin
drawn from behind (the cat's), turns round with a pink thong showing and is
mortified ("oops")."""
OOPS_BACK = (0.3, 1.9)
"""When, into "oops", it has its back to you - the thong in full view."""
SAW_FROM, SAW_UNTIL = 0.8, 4.4
"""When, into "saw", the saw goes back and forth; after, the plank falls in two."""
POKES_TO_FUME = 5
POKE_WINDOW_S = 2.0
"""This many clicks on it within this many seconds, and it has had enough."""
SPEECH_S = 3.5
EVERYDAY_CHANCE = 0.2
DIZZY_SPEED = 1500.0
"""A landing faster than this - thrown, not jumped - leaves it seeing stars."""
DIZZY_S = 1.8
PURR_AFTER = 0.5
"""Seconds of the cursor moving over it before it starts to purr."""
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
    ear: float = 0.0
    _next_ear: float = 5.0
    dizzy: float = 0.0
    vy_at_landing: float = 0.0
    petting: float = 0.0
    _purr_beat: float = 0.0
    speech: str | None = None
    """A line in a bubble over its head, for ``speech_left`` seconds."""
    speech_left: float = 0.0
    _pokes: list[float] = field(default_factory=list)

    @property
    def facing_away(self) -> bool:
        return self.act == "oops" and OOPS_BACK[0] <= self.act_time < OOPS_BACK[1]

    @property
    def purring(self) -> bool:
        return self.petting >= PURR_AFTER and self.mood in (Mood.IDLE, Mood.SLEEP, Mood.LAND, Mood.ACT)

    @property
    def breathing(self) -> float:
        """A slow rise and fall while it stands or sleeps, added to the squash
        when drawn - deeper asleep, and deeper still purring."""
        if self.mood is Mood.SLEEP:
            return 0.06 * math.sin(self.clock * 1.3)
        if self.mood is Mood.IDLE or (self.mood is Mood.ACT and self.act == "sit"):
            return (0.05 if self.purring else 0.025) * math.sin(self.clock * (3.2 if self.purring else 2.2))
        return 0.0

    @property
    def tail_up(self) -> bool:
        """The tail's tip: swishing slowly while it stands, quickly when cross,
        held up while purring, down asleep."""
        if self.mood is Mood.SLEEP:
            return False
        if self.purring or self.mood is Mood.AIR:
            return True
        rate = 6.0 if self.expression == "angry" else (0.0 if self.expression == "sad" else 1.6)
        return rate > 0.0 and int(self.clock * rate) % 2 == 0

    @property
    def fly_at(self) -> tuple[float, float] | None:
        """Where the fly of a "fly" act is, from the cat's feet - ``None``
        once swatted."""
        if self.act != "fly" or self.act_time >= 3.0:
            return None
        t = self.act_time
        return 30.0 * math.cos(t * 2.6), -self.skin.height - 26.0 + 10.0 * math.sin(t * 5.3)

    @property
    def expression(self) -> str | None:
        if self.emotion is not None or self.act is None:
            return self.emotion
        t = self.act_time
        if (self.act == "jam" and 0.8 <= t < 2.2) or (self.act == "spoof" and t >= 1.8):
            return "angry"
        if self.act == "holdover" and t >= 1.0:
            return "sad"
        if self.act == "oops" and t >= OOPS_BACK[1]:
            return "embarrassed"
        return None

    @property
    def eyes_closed(self) -> bool:
        if self.mood is Mood.SLEEP or self.blink > 0.0 or self.purring:
            return True
        if self.act == "yawn" and self.act_time < 0.9:
            return True
        if self.act == "stretch" and self.act_time < 1.3:
            return True
        if self.act == "sneeze" and 0.3 <= self.act_time < 0.9:
            return True
        return self.act == "groom" and int(self.act_time * 3) % 2 == 1

    @property
    def arms_raised(self) -> bool:
        if self.mood in (Mood.HELD, Mood.RIDE) or (self.mood is Mood.AIR and self.vy < 0):
            return True
        if self.act == "wave":
            return int(self.act_time * 6) % 2 == 0
        if self.act == "yawn":
            return self.act_time < 0.9
        if self.act == "stretch":
            return 0.4 <= self.act_time < 1.3
        if self.act == "fly":
            return 3.0 <= self.act_time < 3.5
        if self.act == "saw":
            return SAW_FROM <= self.act_time < SAW_UNTIL and int(self.act_time * 7) % 2 == 0
        return self.act == "cesium" or (self.act == "gps" and self.act_time >= 1.2)

    def look(self) -> int:
        if self.act == "spoof" and self.act_time >= 0.4:
            return -1
        if self.act == "oops" and self.act_time >= OOPS_BACK[1]:
            return -1  # can't look you in the eye
        if self.act == "saw":
            return self.facing  # eyes on the work
        fly = self.fly_at
        if fly is not None:
            return 0 if abs(fly[0]) < 10 else (1 if fly[0] > 0 else -1)
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
        self._tick_petting(dt)
        if self.speech_left > 0.0:
            self.speech_left = max(0.0, self.speech_left - dt)
            if self.speech_left == 0.0:
                self.speech = None
        if self.dizzy > 0.0:
            self.dizzy = max(0.0, self.dizzy - dt)
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

    def poke(self) -> None:
        """A click on it. One too many, too fast, and it is fed up - cross,
        and tells you so."""
        self._pokes = [at for at in self._pokes if self.clock - at < POKE_WINDOW_S] + [self.clock]
        if len(self._pokes) < POKES_TO_FUME:
            return
        self._pokes = []
        self.speech, self.speech_left = self.skin.fed_up, SPEECH_S
        self.feel("angry", SPEECH_S)

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
        known = act in self.acts or act in REACTIONS or act in EVERYDAY_ACTS
        if act == "oops" and self.skin.back is None:
            return False  # nothing to see from behind
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
        elif act == "groom":
            self.squash = 0.05 * math.sin(t * 12.0)
        elif act == "stretch":
            self.squash = 0.3 * math.sin(math.pi * min(t, 1.2) / 1.2) if t < 1.2 else -0.1
        elif act == "chase":
            self.walk_phase += dt * 14.0
            if math.floor(before / 0.22) < math.floor(t / 0.22):
                self.facing = -self.facing
            if reached(EVERYDAY_ACTS["chase"] - 0.05):
                self._say("?")
                self.dizzy = 1.0
        elif act == "fly":
            if reached(2.8):
                self.squash = 0.25
            if reached(3.0):
                self.squash = -0.25
                self._say("!")
                fx, fy = 30.0 * math.cos(3.0 * 2.6), -self.skin.height - 26.0
                self.particles.append(Particle("puff", fx, fy, 0.0, -20.0, 0.5))
        elif act == "sneeze":
            if t < 0.8:
                self.squash = -0.18 * min(1.0, t / 0.6)
            if reached(0.8):
                self.squash = 0.28
                for spread in (-25.0, 0.0, 25.0):
                    self.particles.append(Particle("puff", self.facing * self.skin.width / 2,
                                                   -self.skin.height * 0.55,
                                                   self.facing * 110.0, spread, 0.5))
        elif act == "sit":
            self.squash = max(self.squash, 0.1)
        elif act == "oops":
            back_from, back_until = OOPS_BACK
            if back_from <= t < back_until:
                self.squash = 0.05 * math.sin(t * 11.0)  # a little wiggle, none the wiser
            if reached(back_until):
                self.squash = -0.2
                self._say("!")
            elif t >= back_until:
                self.squash = max(self.squash, 0.12)  # shrinking into itself
                self._act_beat -= dt
                if self._act_beat <= 0.0:
                    self._act_beat = 0.7
                    side = self.rng.choice((-1, 1))
                    self.particles.append(Particle("tear", side * (self.skin.width / 2 + 2),
                                                   -self.skin.height * 0.9, side * 12.0, 30.0, 0.6))
        elif act == "saw":
            plank_x, plank_y = saw_plank_at(self)
            if SAW_FROM <= t < SAW_UNTIL:
                self._act_beat -= dt
                if self._act_beat <= 0.0:
                    self._act_beat = 0.12
                    self.particles.append(Particle("dust", plank_x + self.rng.uniform(-3, 3), plank_y + 4,
                                                   self.rng.uniform(-25, 25), 70.0, 0.5))
            if reached(SAW_UNTIL):
                self.particles.append(Particle("puff", plank_x, plank_y, 0.0, -20.0, 0.5))
                self._say("heart")
        if t >= self.acts.get(act, REACTIONS.get(act, EVERYDAY_ACTS.get(act, 0.0))):
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
        if self.ear > 0.0:
            self.ear = max(0.0, self.ear - dt)
        self._next_ear -= dt
        if self._next_ear <= 0.0:
            self.ear = 0.18
            self._next_ear = self.rng.uniform(4.0, 10.0)

    def _tick_petting(self, dt: float) -> None:
        """The cursor moving over it, gently, is a hand stroking it: it purrs,
        eyes shut, tail up, a heart now and then - and stays put for it."""
        cx, cy = self._cursor
        over = _dist(cx - self.x, cy - (self.y - self.skin.height / 2)) < self.skin.width * 0.6
        # Moving over it lately, and not racing across: a hand, not a pass.
        stroking = over and self._cursor_still < 0.3 and self._cursor_speed < 900.0
        if stroking and self.mood in (Mood.IDLE, Mood.WALK, Mood.SLEEP, Mood.LAND, Mood.ACT):
            self.petting += dt
        elif not over:
            self.petting = max(0.0, self.petting - dt * 2.0)
        if not self.purring:
            return
        if self.mood is Mood.WALK:
            self.mood = Mood.IDLE
        self.timer = max(self.timer, 1.0)
        self._purr_beat -= dt
        if self._purr_beat <= 0.0:
            self._purr_beat = 0.9
            self._say(self.rng.choice(("heart", "~")))

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
        if self.dizzy > 0.0:
            return
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
        if self.emotion is None and self.rng.random() < EVERYDAY_CHANCE:
            choices = [act for act in EVERYDAY_ACTS
                       if act != self._last_act and (act != "oops" or self.skin.back is not None)]
            self.perform(self.rng.choice(choices))
            self._last_act = self.act
            if self.act is not None:
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
            self.vy_at_landing = self.vy
            self.vx = self.vy = 0.0
            if self.pouncing:
                self._say("?")
            hard = self.vy_at_landing >= DIZZY_SPEED
            self.pouncing = False
            self.aim_y = None
            self.mood = Mood.LAND
            self.timer = 0.25
            if hard:
                self.dizzy = DIZZY_S
                self.timer = DIZZY_S

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
CAT_GROOM = (
    *CAT_BODY[:7],
    ".KKSSWWWWSSKC.",
    "..KKSSSSSSKKC.",
    "..KKKKZZKKKK..",
    ".CKHKKZZKKKK..",
    CAT_BODY[11],
)
"""One paw up at its mouth, washing."""
CAT_SAD_BODY = (
    *CAT_BODY[:9],
    ".KKKKKZZKKKKK.",
    ".CKHKKZZKKKKC.",
    CAT_BODY[11],
)
CAT_BACK = (
    ".K..........K.",
    ".KK........KK.",
    ".KKKKKKKKKKKK.",
    "KKKKKKKKKKKKKK",
    "KKKKKKKKKKKKKK",
    "KKKKKKKKKKKKKK",
    "KKKKKKKKKKKKKK",
    ".KKKKKKKKKKKK.",
    "..KKKKKKKKKK..",
    "..KPPKKKKPPK..",
    ".CKKKPPPPKKKC.",
    "...KKKPPKKK..K",
)
"""From behind - and the pink thong it did not mean anyone to see."""
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
    if pet.expression == "embarrassed":
        rows[5][2] = rows[5][3] = rows[5][10] = rows[5][11] = "b"  # blushing
        rows[7][6] = rows[7][7] = "M"
    if pet.expression in _CAT_MOUTH:
        rows[6], rows[7] = (list(row) for row in _CAT_MOUTH[pet.expression])
    elif pet.act == "groom" and int(pet.act_time * 6) % 2 == 0:
        rows[7][7] = "p"  # the tongue, licking
    elif pet.act == "sneeze" and pet.act_time < 0.8:
        rows[6][6] = rows[6][7] = "M"  # the breath in
    if pet.dizzy > 0.0 and not pet.eyes_closed:
        for left in _CAT_EYES:
            rows[3][left] = rows[4][left + 1] = "W"
            rows[4][left] = rows[3][left + 1] = "K"
    if pet.ear > 0.0:
        rows[0][1], rows[0][2] = ".", "K"  # an ear twitches


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
    groom: tuple[str, ...] | None = None
    tail: tuple[tuple[int, int], tuple[int, int]] | None = None
    """The tail tip's cell down and up, for the swish."""
    back: tuple[str, ...] | None = None
    """The body from behind, no face - without one, no "oops"."""
    fed_up: str = "Hey! Stop poking me!"
    """What it says when clicked once too often, too fast."""

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
        "P": "#FF5FA8", "b": "#F2789A",
    },
    angry={"S": "p"},
    tears=((5.0, 2.5), (5.0, 11.5)),
    outline=True,
    stalks=True,
    groom=CAT_GROOM,
    tail=((11, 13), (10, 13)),
    back=CAT_BACK,
    fed_up="אין לי מפתח לשירותים פה!",
)
SKINS: dict[str, Skin] = {skin.key: skin for skin in (CLAWD, CAT)}


def skin_named(key: str) -> Skin:
    return SKINS.get(key, CLAWD)


def frame(pet: Pet) -> list[str]:
    skin = pet.skin
    if pet.facing_away and skin.back is not None:
        rows = [list(row) for row in skin.back]
        rows.extend(list(row) for row in skin.legs["stand"])
        return ["".join(row) for row in rows]
    if pet.act == "groom" and skin.groom is not None:
        body = skin.groom
    elif pet.arms_raised:
        body = skin.arms_up
    else:
        body = skin.sad_body if pet.expression == "sad" else skin.body
    rows = [list(row) for row in body]
    skin.face(rows, pet)
    if pet.expression == "angry":
        rows = [[skin.angry.get(cell, cell) for cell in row] for row in rows]
    rows.extend(list(row) for row in skin.legs[_legs(pet)])
    if skin.tail is not None and pet.tail_up:
        (down_row, down_col), (up_row, up_col) = skin.tail
        if rows[down_row][down_col] != "." and rows[up_row][up_col] == ".":
            rows[up_row][up_col], rows[down_row][down_col] = rows[down_row][down_col], "."
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
    if pet.act == "chase":
        return "walk_a" if int(pet.walk_phase) % 2 == 0 else "walk_b"
    if pet.act in ("sit", "groom") or (pet.act == "stretch" and pet.act_time < 1.2):
        return "tuck"
    return "stand"


PROPS: dict[str, tuple[tuple[str, ...], dict[str, str]]] = {
    "satellite": (("b.s.b", "bbsbb", "b.s.b"), {"b": "#3E6FD8", "s": "#9AA3B0"}),
    "antenna": (("y...y", ".y.y.", "..g..", "..g..", "..g.."), {"y": "#F2B632", "g": "#6B6B6B"}),
    "zigzag": (("x...x...x", ".x.x.x.x.", "..x...x.."), {"x": "#E0442E"}),
    "clock": (
        (".ggggg.", "gwwwwwg", "gwwkwwg", "gwwkkwg", "gwwwwwg", "gwwwwwg", ".ggggg."),
        {"g": "#6B6B6B", "w": "#FFFFFF", "k": "#1E1E1E"},
    ),
    "plank": (("wwwwdwwwwwww", "dddddddddddd", "wwwwwwwdwwww"), {"w": "#C8925A", "d": "#A0703F"}),
    "half_plank": (("wwwwdw", "dddddd", "wwwwww"), {"w": "#C8925A", "d": "#A0703F"}),
    "saw": (("hhh.........", "hhbbbbbbbbbb", "hh.t.t.t.t.t"),
            {"h": "#B5482F", "b": "#C9CED6", "t": "#8A929E"}),
}
PROPS["saw_left"] = (tuple(row[::-1] for row in PROPS["saw"][0]), PROPS["saw"][1])
"""The saw held from the other side: handle towards the cat either way."""


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
    fly: tuple[float, float, bool] | None = None
    """The fly: where, from the feet, and whether its wings are up."""
    stars: float | None = None
    """Dizzy: the phase of the stars going round its head."""
    speech: str | None = None
    """A line in a bubble over its head."""


def saw_plank_at(pet: Pet) -> tuple[float, float]:
    """Where the plank of a "saw" act is, from the feet: lifted off the floor
    to its paws, on the side it faces."""
    lift = min(1.0, pet.act_time / SAW_FROM)
    return pet.facing * 30.0, -4.0 - lift * (pet.skin.height * 0.45 - 4.0)


def ghost_offset(t: float) -> float:
    return -min(40.0, max(0.0, t - 0.4) * 30.0)


def act_view(pet: Pet) -> ActView:
    view = ActView()
    act, t, top = pet.act, pet.act_time, -pet.skin.height
    if pet.thinking and act is None and pet.mood is not Mood.SLEEP:
        view.dots = 1 + int(pet.clock * 3) % 3
    if pet.dizzy > 0.0:
        view.stars = pet.clock * 6.0
    if pet.speech:
        view.speech = pet.speech
    fly = pet.fly_at
    if fly is not None:
        view.fly = (fly[0], fly[1], int(pet.clock * 20) % 2 == 0)
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
    elif act == "saw":
        x, y = saw_plank_at(pet)
        if t < SAW_UNTIL:
            view.props.append(("plank", x, y, 1.0))
            if t >= SAW_FROM:
                stroke = 7.0 * math.sin((t - SAW_FROM) * 14.0)
                view.props.append(("saw" if pet.facing > 0 else "saw_left", x + stroke, y - 8.0, 1.0))
        else:
            fall = t - SAW_UNTIL
            drop = min(-4.0, y + 160.0 * fall * fall)
            for side in (-1, 1):
                view.props.append(("half_plank", x + side * (9.0 + 25.0 * fall), drop, 1.0))
    return view
