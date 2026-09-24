import os
import shutil
import subprocess
import time

import pytest

if not os.environ.get("DISPLAY"):
    pytest.skip("GTK needs a display (run under xvfb-run)", allow_module_level=True)
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from desktop_pet.core import Mood, Mulberry32  # noqa: E402
from desktop_pet.gtk import GtkPet  # noqa: E402


def _pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.005)


@pytest.fixture
def window():
    win = Gtk.Window()
    win.set_default_size(600, 500)
    win.move(0, 0)
    fixed = Gtk.Fixed()
    button = Gtk.Button(label="Save")
    button.set_size_request(200, 40)
    fixed.put(button, 200, 300)
    other = Gtk.Button(label="Elsewhere")
    other.set_size_request(120, 30)
    fixed.put(other, 20, 440)
    win.add(fixed)
    win.show_all()
    _pump(0.3)
    yield win, button, other
    win.destroy()
    _pump(0.05)


def _landed(pet, seconds=4.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        _pump(0.01)
        if pet.pet.ledge is not None and pet.pet.mood in (Mood.LAND, Mood.IDLE, Mood.WALK):
            return True
    return False


def _screen(win, x, y):
    ox, oy = win.get_window().get_origin()[1:]
    return int(ox + x), int(oy + y)


def test_the_pet_lands_on_the_button_under_it(window):
    win, button, _ = window
    pet = GtkPet(win)
    pet.pet.rng = Mulberry32(4)
    _pump(0.1)
    pet.start()
    assert _landed(pet)
    assert pet.pet.ledge.key is button
    assert pet.pet.y == 300.0
    pet.pet.mood, pet.pet.timer = Mood.IDLE, 60.0
    _pump(0.5)
    assert pet.pet.ledge is not None and pet.pet.ledge.key is button
    pet.stop()


@pytest.mark.skipif(not shutil.which("xdotool"), reason="needs xdotool for real clicks")
def test_real_clicks_reach_the_app_except_on_the_pet(window):
    win, button, other = window
    pet = GtkPet(win)
    pet.pet.rng = Mulberry32(4)
    _pump(0.1)
    pet.start()
    assert _landed(pet)
    pet.pet.mood, pet.pet.timer = Mood.IDLE, 60.0
    _pump(0.1)
    clicked = []
    other.connect("clicked", lambda _b: clicked.append("other"))
    button.connect("clicked", lambda _b: clicked.append("save"))

    subprocess.run(["xdotool", "mousemove", *map(str, _screen(win, 80, 455)), "click", "1"], check=True)
    _pump(0.3)
    assert clicked == ["other"], "a click beside the pet must reach the app"

    left, top, width, height = pet.body_rect()
    subprocess.run(["xdotool", "mousemove", *map(str, _screen(win, left + width // 2, top + height // 2)),
                    "mousedown", "1"], check=True)
    _pump(0.3)
    assert pet.pet.mood is Mood.HELD, "a press on the pet picks it up"
    subprocess.run(["xdotool", "mousemove", *map(str, _screen(win, 450, 150)), "mouseup", "1"], check=True)
    _pump(0.3)
    assert pet.pet.mood is not Mood.HELD
    assert clicked == ["other"], "the press on the pet must not click the button under it"
    pet.stop()
