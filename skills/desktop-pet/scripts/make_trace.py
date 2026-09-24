"""Writes the reference trace every port of the core is checked against.

A trace is a scripted world (ledges, a cursor path, a few throws and feelings) fed to a
seeded pet, with the pet's state recorded after every step. The inputs are stored with
the outputs, so a port only has to replay them -- it never re-implements the script.

    python make_trace.py                          # rewrite ../assets/reference_trace.json
    python make_trace.py --check                  # compare the skill's core against it
    python make_trace.py --check --core app/pkg   # compare a vendored copy (the folder holding desktop_pet/)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_core_at = next((sys.argv[i + 1] for i, arg in enumerate(sys.argv[:-1]) if arg == "--core"), None)
sys.path.insert(0, str(Path(_core_at).resolve() if _core_at else HERE.parent / "assets" / "python"))

from desktop_pet.core import (  # noqa: E402
    ACT_PACKS,
    Bounds,
    Ledge,
    Mulberry32,
    Pet,
    act_view,
    frame,
    skin_named,
)

TRACE = HERE.parent / "assets" / "reference_trace.json"
STEPS = 4400
BOUNDS = (0.0, 0.0, 1200.0, 800.0)
LEDGE_SETS = [
    [[0.0, 1200.0, 800.0, None], [100.0, 400.0, 600.0, "panel"], [500.0, 900.0, 480.0, "button"],
     [700.0, 1100.0, 650.0, "list"]],
    [[0.0, 1200.0, 800.0, None], [140.0, 440.0, 600.0, "panel"], [500.0, 900.0, 480.0, "button"]],
]
SCENARIOS = [
    {"name": "clawd-with-acts", "seed": 1, "skin": "clawd", "acts": "gnss"},
    {"name": "cat-without-acts", "seed": 7, "skin": "cat", "acts": None},
]


_ACT_STEPS = {2000: "gps", 2400: "jam", 2800: "spoof", 3200: "pps", 3600: "cesium", 4000: "holdover"}


def _inputs(step: int) -> dict:
    dt = (1 / 60, 1 / 50, 1 / 75)[step % 3] if step % 97 else 0.1
    t = step / 60.0
    if 1000 <= step < 1040:
        cursor = [600.0 + 900.0 * math.sin(step), 300.0 + 700.0 * math.cos(step)]
    elif 700 <= step < 1000:
        cursor = [650.0, 470.0]
    elif step >= 1700:
        cursor = [1190.0, 20.0]
    else:
        cursor = [600.0 + 400.0 * math.sin(t * 0.7), 400.0 + 250.0 * math.cos(t * 0.5)]
    events: list = []
    if step == 300:
        events = [["grab"], ["drag_to", 300.0, 200.0]]
    elif step == 305:
        events = [["drag_to", 340.0, 180.0]]
    elif step == 310:
        events = [["throw", 900.0, -600.0]]
    elif step == 1100:
        events = [["feel", "angry", 4.0]]
    elif step == 1300:
        events = [["feel", "sad", 5.0]]
    elif step == 1700:
        events = [["cheer"]]
    elif step == 1750:
        events = [["watch", 800.0, 300.0]]
    elif step == 1800:
        events = [["startle"]]
    elif step == 1850:
        events = [["perform", "wave"]]
    elif step >= 2000 and step % 400 < 150 and step // 400 * 400 in _ACT_STEPS:
        events = [["perform", _ACT_STEPS[step // 400 * 400]]]
    return {"dt": dt, "cursor": [round(v, 6) for v in cursor], "ledges": 1 if 1000 <= step < 1400 else 0,
            "events": events}


def _ledges(index: int, keys: dict) -> list[Ledge]:
    return [Ledge(left, right, y, keys.setdefault(key, key) if key else None)
            for left, right, y, key in LEDGE_SETS[index]]


def _apply(pet: Pet, event: list) -> None:
    name, *args = event
    getattr(pet, name)(*args)


def _state(pet: Pet, step: int) -> dict:
    view = act_view(pet)
    state = {
        "x": pet.x, "y": pet.y, "vx": pet.vx, "vy": pet.vy, "mood": pet.mood.value,
        "facing": pet.facing, "act": pet.act, "emotion": pet.emotion,
        "ledge": None if pet.ledge is None else [pet.ledge.left, pet.ledge.y],
        "particles": [[p.kind, p.x, p.y] for p in pet.particles],
        "view": [len(view.props), [label[0] for label in view.labels], view.ghost, view.bars, view.dots],
    }
    if step % 10 == 0:
        state["frame"] = frame(pet)
    return state


def run(scenario: dict, inputs: list[dict]) -> list[dict]:
    pet = Pet(600.0, 100.0, rng=Mulberry32(scenario["seed"]))
    pet.skin = skin_named(scenario["skin"])
    pet.acts = dict(ACT_PACKS[scenario["acts"]]) if scenario["acts"] else {}
    keys: dict = {}
    states = []
    for step, given in enumerate(inputs):
        for event in given["events"]:
            _apply(pet, event)
        pet.step(given["dt"], _ledges(given["ledges"], keys), tuple(given["cursor"]), Bounds(*BOUNDS))
        states.append(_state(pet, step))
    return states


def _close(a, b, path: str) -> str | None:
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None or abs(a - b) > 1e-6 * max(1.0, abs(a), abs(b)):
            return f"{path}: expected {a!r}, got {b!r}"
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{path}: expected {len(a)} items, got {len(b)}"
        for index, (x, y) in enumerate(zip(a, b, strict=True)):
            problem = _close(x, y, f"{path}[{index}]")
            if problem:
                return problem
        return None
    if isinstance(a, dict) and isinstance(b, dict):
        for key in a:
            problem = _close(a[key], b.get(key), f"{path}.{key}")
            if problem:
                return problem
        return None
    return None if a == b else f"{path}: expected {a!r}, got {b!r}"


def build() -> dict:
    inputs = [_inputs(step) for step in range(STEPS)]
    return {
        "about": "Inputs and expected pet state per step; see references/porting.md.",
        "bounds": BOUNDS,
        "ledge_sets": LEDGE_SETS,
        "inputs": inputs,
        "scenarios": [{**scenario, "states": run(scenario, inputs)} for scenario in SCENARIOS],
    }


def check(trace: dict) -> list[str]:
    problems = []
    for scenario in trace["scenarios"]:
        states = run(scenario, trace["inputs"])
        for step, (want, got) in enumerate(zip(scenario["states"], states, strict=True)):
            problem = _close(want, got, f"{scenario['name']} step {step}")
            if problem:
                problems.append(problem)
                break
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--core", help="the folder that holds the desktop_pet package to check")
    args = parser.parse_args()
    if args.check:
        problems = check(json.loads(TRACE.read_text(encoding="utf-8")))
        print("\n".join(problems) or "the core reproduces the reference trace")
        return 1 if problems else 0
    TRACE.write_text(json.dumps(build(), separators=(",", ":")), encoding="utf-8")
    print(f"wrote {TRACE} ({TRACE.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
