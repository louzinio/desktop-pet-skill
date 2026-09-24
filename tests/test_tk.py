import os
import time

import pytest

tk = pytest.importorskip("tkinter")
if not os.environ.get("DISPLAY"):
    pytest.skip("Tk needs a display (run under xvfb-run)", allow_module_level=True)

from desktop_pet.core import Mood, Mulberry32  # noqa: E402
from desktop_pet.tk import TkPet  # noqa: E402


def _pump(root, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


@pytest.fixture
def window():
    root = tk.Tk()
    root.geometry("600x500+0+0")
    button = tk.Button(root, text="Save")
    button.place(x=200, y=300, width=200, height=40)
    root.update()
    yield root, button
    root.destroy()


def _landed(root, pet, seconds=4.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if pet.pet.ledge is not None and pet.pet.mood in (Mood.LAND, Mood.IDLE, Mood.WALK):
            return True
        time.sleep(0.005)
    return False


def test_the_pet_lands_on_the_button_under_it(window):
    root, button = window
    pet = TkPet(root)
    pet.pet.rng = Mulberry32(4)
    pet.start()
    assert _landed(root, pet)
    assert pet.pet.ledge.key is button
    assert pet.pet.y == 300.0
    pet.pet.mood, pet.pet.timer = Mood.IDLE, 60.0
    _pump(root, 1.0)
    assert pet.pet.ledge is not None and pet.pet.ledge.key is button, "it must stay on the button"
    pet.stop()


def test_the_pet_is_drawn_as_tiles_over_the_window(window):
    root, _ = window
    pet = TkPet(root, skin="cat")
    pet.pet.rng = Mulberry32(4)
    pet.start()
    assert _landed(root, pet)
    _pump(root, 0.1)
    shown = [tile for tile in pet._pool if tile.winfo_ismapped()]
    assert 10 < len(shown) < 80
    left = min(tile.winfo_x() for tile in shown)
    right = max(tile.winfo_x() + tile.winfo_width() for tile in shown)
    assert abs((left + right) / 2 - pet.pet.x) <= 3
    pet.stop()
    _pump(root, 0.05)
    assert not any(tile.winfo_ismapped() for tile in pet._pool)


def test_a_press_on_the_pet_picks_it_up_and_a_drag_throws_it(window):
    root, _ = window
    pet = TkPet(root)
    pet.pet.rng = Mulberry32(4)
    pet.start()
    assert _landed(root, pet)
    pet.pet.mood, pet.pet.timer = Mood.IDLE, 60.0
    _pump(root, 0.05)
    tile = next(tile for tile in pet._pool if tile.winfo_ismapped())
    x, y = tile.winfo_rootx() + 1, tile.winfo_rooty() + 1
    pet._press(type("E", (), {"x_root": x, "y_root": y})())
    assert pet.pet.mood is Mood.HELD
    pet._move(type("E", (), {"x_root": x + 60, "y_root": y - 80})())
    time.sleep(0.02)
    pet._move(type("E", (), {"x_root": x + 120, "y_root": y - 160})())
    pet._release(None)
    assert pet.pet.mood is Mood.AIR and pet.pet.vx > 0 and pet.pet.vy < 0
    pet.stop()
