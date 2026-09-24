import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt = pytest.importorskip("desktop_pet.qt", exc_type=ImportError)

from desktop_pet.core import Mood, Mulberry32  # noqa: E402

QtWidgets, QtCore = qt.QtWidgets, qt.QtCore


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def _window(app):
    window = QtWidgets.QWidget()
    window.resize(600, 500)
    button = QtWidgets.QPushButton("Save", window)
    button.setGeometry(200, 300, 200, 40)
    other = QtWidgets.QPushButton("Elsewhere", window)
    other.setGeometry(20, 440, 120, 30)
    window.show()
    _pump(app, 0.05)
    return window, button, other


def _landed(app, pet, seconds=4.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if pet.pet.mood in (Mood.LAND, Mood.IDLE, Mood.WALK) and pet.pet.ledge is not None:
            return True
        time.sleep(0.005)
    return False


def _click(widget, x, y, press_only=False):
    point = QtCore.QPoint(x, y)
    for kind in ("MouseButtonPress",) if press_only else ("MouseButtonPress", "MouseButtonRelease"):
        event = qt.QtGui.QMouseEvent(
            qt._event(kind), QtCore.QPointF(point), QtCore.QPointF(widget.mapToGlobal(point)),
            qt._enum("MouseButton", "LeftButton"), qt._enum("MouseButton", "LeftButton"),
            qt._enum("KeyboardModifier", "NoModifier"),
        ) if hasattr(QtCore, "QPointF") and qt.BINDING in ("PySide6", "PyQt6") else qt.QtGui.QMouseEvent(
            qt._event(kind), point, widget.mapToGlobal(point), qt._enum("MouseButton", "LeftButton"),
            qt._enum("MouseButton", "LeftButton"), qt._enum("KeyboardModifier", "NoModifier"),
        )
        QtWidgets.QApplication.sendEvent(widget, event)


def test_the_pet_lands_on_the_button_under_it(app):
    window, button, _ = _window(app)
    pet = qt.WindowPet(window)
    pet.pet.rng = Mulberry32(4)
    pet.start()
    assert _landed(app, pet)
    assert pet.pet.ledge.key is button
    assert pet.pet.y == 300.0
    pet.stop()
    window.close()


def test_clicks_beside_the_pet_still_reach_the_app(app):
    window, button, other = _window(app)
    pet = qt.WindowPet(window)
    pet.pet.rng = Mulberry32(4)
    pet.start()
    assert _landed(app, pet)
    clicked = []
    other.clicked.connect(lambda: clicked.append(True))
    _click(other, 10, 10)
    assert clicked == [True]
    pet.stop()
    window.close()


def test_a_press_on_the_pet_picks_it_up_instead_of_clicking_below(app):
    window, button, _ = _window(app)
    pet = qt.WindowPet(window)
    pet.pet.rng = Mulberry32(4)
    pet.start()
    assert _landed(app, pet)
    pet.pet.mood, pet.pet.timer = Mood.IDLE, 60.0
    clicked = []
    button.clicked.connect(lambda: clicked.append(True))
    left, top, width, height = pet.body_rect()
    at = QtCore.QPoint(int(left + width / 2), int(top + height / 2))
    _click(window, at.x(), at.y(), press_only=True)
    assert pet.pet.mood is Mood.HELD
    assert clicked == []
    pet.stop()
    window.close()


def test_the_pet_draws_without_error_in_every_state(app):
    window, _, _ = _window(app)
    pet = qt.WindowPet(window, acts="gnss", skin="cat")
    pet.pet.rng = Mulberry32(9)
    pet.start()
    assert _landed(app, pet)
    for act in ("gps", "jam", "spoof", "pps", "cesium", "holdover"):
        pet.pet.mood, pet.pet.act = Mood.IDLE, None
        assert pet.pet.perform(act)
        for _ in range(8):
            _pump(app, 0.1)
            window.grab()
    pet.pet.feel("sad", 1.0)
    _pump(app, 0.3)
    window.grab()
    pet.stop()
    window.close()


def test_the_desktop_pet_roams_as_its_own_window(app):
    window, _, _ = _window(app)
    pet = qt.DesktopPet(window)
    pet.pet.rng = Mulberry32(4)
    pet.start()
    _pump(app, 1.5)
    assert pet.isWindow()
    pet.grab()
    pet.stop()
    window.close()
