import json

import pytest
from make_trace import TRACE, check

from desktop_pet.core import ACT_PACKS, CAT, CLAWD, Bounds, Ledge, Mood, Mulberry32, Pet, act_view, frame

BOUNDS = Bounds(0.0, 0.0, 1000.0, 700.0)
FLOOR = Ledge(0.0, 1000.0, 700.0)


def _run(pet, seconds, ledges=(FLOOR,), cursor=(-5000.0, -5000.0)):
    for _ in range(int(seconds * 60)):
        pet.step(1 / 60, list(ledges), cursor, BOUNDS)


def test_the_core_reproduces_the_reference_trace():
    assert check(json.loads(TRACE.read_text(encoding="utf-8"))) == []


def test_a_dropped_pet_lands_on_the_highest_ledge_below_it():
    shelf = Ledge(300.0, 700.0, 400.0, "shelf")
    pet = Pet(500.0, 0.0, rng=Mulberry32(3))
    for _ in range(90):
        pet.step(1 / 60, [FLOOR, shelf], (-5000.0, -5000.0), BOUNDS)
        if pet.ledge is not None:
            break
    assert pet.ledge is not None and pet.ledge.key == "shelf"
    assert pet.y == 400.0


def test_a_ledge_that_moves_carries_the_pet_with_it():
    pet = Pet(500.0, 390.0, rng=Mulberry32(3))
    _run(pet, 0.5, ledges=(FLOOR, Ledge(300.0, 700.0, 400.0, "panel")))
    assert pet.ledge is not None and pet.ledge.key == "panel"
    before = pet.x
    pet.mood, pet.timer = Mood.IDLE, 10.0
    pet.step(1 / 60, [FLOOR, Ledge(350.0, 750.0, 400.0, "panel")], (-5000.0, -5000.0), BOUNDS)
    assert pet.x == pytest.approx(before + 50.0)


def test_the_pet_never_leaves_the_bounds():
    pet = Pet(500.0, 300.0, rng=Mulberry32(11))
    pet.throw(2600.0, -2600.0)
    for _ in range(600):
        pet.step(1 / 60, [FLOOR], (-5000.0, -5000.0), BOUNDS)
        assert BOUNDS.left < pet.x < BOUNDS.right
        assert pet.y >= BOUNDS.top


def test_without_an_act_pack_it_never_performs_one():
    pet = Pet(500.0, 690.0, rng=Mulberry32(5))
    _run(pet, 120)
    assert pet.acts == {}
    assert not pet.perform("gps")


def test_an_act_pack_is_opt_in():
    pet = Pet(500.0, 699.0, rng=Mulberry32(5))
    pet.acts = dict(ACT_PACKS["gnss"])
    _run(pet, 1)
    assert pet.perform("gps")
    assert act_view(pet).labels[0][0] == "SEARCH"


@pytest.mark.parametrize("skin", [CLAWD, CAT])
def test_every_frame_has_the_skin_s_shape(skin):
    pet = Pet(500.0, 0.0, rng=Mulberry32(2))
    pet.skin = skin
    for _ in range(600):
        pet.step(1 / 60, [FLOOR], (500.0, 600.0), BOUNDS)
        rows = frame(pet)
        assert len(rows) == skin.rows
        assert {len(row) for row in rows} == {skin.columns}
