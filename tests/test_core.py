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


def _standing(skin=CAT):
    pet = Pet(500.0, 700.0, rng=Mulberry32(1))
    pet.skin = skin
    pet.ledge, pet.mood, pet.timer = FLOOR, Mood.IDLE, 99.0
    return pet


def _play(pet, act, every=1 / 60):
    """Plays ``act`` through, ``(t, frame, view)`` while it lasts."""
    assert pet.perform(act)
    seen = []
    while pet.act == act:
        pet.step(every, [FLOOR], (-5000.0, -5000.0), BOUNDS)
        if pet.act == act:
            seen.append((pet.act_time, frame(pet), act_view(pet)))
    return seen


@pytest.mark.parametrize("skin", [CLAWD, CAT], ids=lambda skin: skin.key)
def test_every_everyday_act_plays_through_and_ends(skin):
    from desktop_pet.core import EVERYDAY_ACTS

    for act in EVERYDAY_ACTS:
        pet = _standing(skin)
        if act == "oops" and skin.back is None:
            assert not pet.perform(act)  # nothing to show from behind
            continue
        seen = _play(pet, act)
        assert seen and pet.act is None, act
        assert all(len(row) == skin.columns for _t, rows, _view in seen for row in rows), act


def test_oops_shows_the_thong_from_behind_then_blushes():
    from desktop_pet.core import OOPS_BACK

    seen = _play(_standing(), "oops")
    behind = [rows for t, rows, _view in seen if OOPS_BACK[0] <= t < OOPS_BACK[1]]
    after = [rows for t, rows, _view in seen if t >= OOPS_BACK[1] + 0.1]
    assert behind and all("P" in "".join(rows) and "W" not in "".join(rows) for rows in behind)
    assert after and all("b" in "".join(rows) for rows in after)


def test_saw_lifts_a_plank_saws_it_and_drops_two_halves():
    from desktop_pet.core import SAW_FROM, SAW_UNTIL

    seen = _play(_standing(), "saw")
    sawing = [view for t, _rows, view in seen if SAW_FROM <= t < SAW_UNTIL]
    assert sawing and all({"plank", "saw"} <= {name for name, *_ in view.props} for view in sawing)
    split = [view for t, _rows, view in seen if t >= SAW_UNTIL]
    assert split and all([name for name, *_ in view.props] == ["half_plank"] * 2 for view in split)


@pytest.mark.parametrize("skin", [CLAWD, CAT], ids=lambda skin: skin.key)
def test_poked_too_often_too_fast_it_says_its_line(skin):
    from desktop_pet.core import POKES_TO_FUME, SPEECH_S

    pet = _standing(skin)
    for _ in range(POKES_TO_FUME):
        pet.poke()
        _run(pet, 0.1)
    assert pet.speech == skin.fed_up and pet.emotion == "angry"
    assert act_view(pet).speech == skin.fed_up
    _run(pet, SPEECH_S)
    assert pet.speech is None


def test_clicks_now_and_then_never_annoy_it():
    from desktop_pet.core import POKE_WINDOW_S, POKES_TO_FUME

    pet = _standing()
    for _ in range(3 * POKES_TO_FUME):
        pet.poke()
        _run(pet, POKE_WINDOW_S / (POKES_TO_FUME - 1) + 0.05)
    assert pet.speech is None


def test_thrown_hard_it_lands_seeing_stars():
    pet = _standing()
    pet.throw(0.0, 0.0)
    pet.y, pet.vy = 690.0, 2000.0
    pet.step(1 / 60, [FLOOR], (-5000.0, -5000.0), BOUNDS)
    assert pet.mood is Mood.LAND and pet.dizzy > 0.0 and act_view(pet).stars is not None


def test_stroked_with_the_cursor_it_purrs():
    pet = _standing()
    for i in range(90):
        x = 500.0 + (6.0 if i % 20 < 10 else -6.0)
        pet.step(1 / 60, [FLOOR], (x, 672.0), BOUNDS)
    assert pet.purring and pet.eyes_closed and pet.tail_up
