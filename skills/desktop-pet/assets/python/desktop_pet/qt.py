"""Qt adapter for the desktop pet: PySide6, PyQt6, PySide2 or PyQt5, whichever the app uses.

    from desktop_pet.qt import WindowPet
    pet = WindowPet(main_window)          # lives inside the window: X11, Wayland, Windows, macOS
    pet.start()

    from desktop_pet.qt import DesktopPet
    pet = DesktopPet(main_window)         # roams the whole screen: X11, Windows, macOS (not Wayland)

Both walk on the app's own widgets, follow the cursor, can be picked up and thrown, and
expose `.pet` (the core) so the app can make it feel things: `pet.pet.feel("happy", 3)`.
"""

from __future__ import annotations

import math
import os
import random
from collections.abc import Callable, Iterable

from .core import GNSS_ACTS, PIXEL, PROPS, SKINS, ActView, Bounds, Ledge, Pet, act_view, frame, skin_named

_BINDING = os.environ.get("DESKTOP_PET_QT", "")


def _import_qt():
    order = [_BINDING] if _BINDING else ["PySide6", "PyQt6", "PySide2", "PyQt5"]
    for name in order:
        try:
            core = __import__(f"{name}.QtCore", fromlist=["x"])
            gui = __import__(f"{name}.QtGui", fromlist=["x"])
            widgets = __import__(f"{name}.QtWidgets", fromlist=["x"])
        except ImportError:
            continue
        return name, core, gui, widgets
    raise ImportError("desktop_pet.qt needs PySide6, PyQt6, PySide2 or PyQt5")


BINDING, QtCore, QtGui, QtWidgets = _import_qt()
Qt = QtCore.Qt
QEvent = QtCore.QEvent
QPoint, QPointF, QRectF, QTimer, QElapsedTimer = (
    QtCore.QPoint, QtCore.QPointF, QtCore.QRectF, QtCore.QTimer, QtCore.QElapsedTimer,
)
QColor, QCursor, QFont, QGuiApplication, QPainter, QPen = (
    QtGui.QColor, QtGui.QCursor, QtGui.QFont, QtGui.QGuiApplication, QtGui.QPainter, QtGui.QPen,
)
QApplication, QMenu, QWidget = QtWidgets.QApplication, QtWidgets.QMenu, QtWidgets.QWidget


def _enum(scope: str, name: str):
    """Qt6 bindings only have scoped enums (Qt.WindowType.Tool); Qt5 ones only the flat names."""
    owner = getattr(Qt, scope, None)
    return getattr(owner, name) if owner is not None and hasattr(owner, name) else getattr(Qt, name)


def _scoped(owner, scope: str, name: str):
    inner = getattr(owner, scope, None)
    return getattr(inner, name) if inner is not None and hasattr(inner, name) else getattr(owner, name)


def _event(name: str):
    owner = getattr(QEvent, "Type", None)
    return getattr(owner, name) if owner is not None and hasattr(owner, name) else getattr(QEvent, name)


def _global_pos(event) -> tuple[float, float]:
    if hasattr(event, "globalPosition"):
        where = event.globalPosition()
        return where.x(), where.y()
    where = event.globalPos()
    return float(where.x()), float(where.y())


def _alive(widget) -> bool:
    try:
        widget.isVisible()
    except RuntimeError:
        return False
    return True


WIDTH = 120
HEIGHT = 130
FEET = 124
FRAME_MS = 16
PERCH_REFRESH_S = 0.5
MIN_PERCH = 56

DEFAULT_PERCHES = tuple(
    getattr(QtWidgets, name) for name in (
        "QLineEdit", "QComboBox", "QAbstractButton", "QAbstractSpinBox", "QAbstractItemView",
        "QPlainTextEdit", "QTextEdit", "QProgressBar", "QGroupBox", "QTabBar", "QToolBar",
        "QSlider", "QLabel",
    )
    if hasattr(QtWidgets, name)
)

_OUTLINE = "#8C95A8"
_HEART = ((".x.x.", "xxxxx", ".xxx.", "..x.."), "#E0557A")
_VEIN = ((".x.x.", "xx.xx", ".....", "xx.xx", ".x.x."), "#C8432B")
_SHAPES = {"heart": _HEART, "vein": _VEIN}
_MARK = "#D97757"
_SLEEP = "#7A8BA8"
_TEAR = "#5DB8F0"
_PUFF = "#7D8691"
_PROP_PIXEL = 3
_TONES = {"dim": "#7A8BA8", "bad": "#E0442E", "good": "#3FA34D"}
_SIGNAL = "#3E6FD8"
_NOISE = ("#9AA3B0", "#6B6B6B", "#E0442E", "#3E6FD8")
_BAR_ON = "#3FA34D"
_BAR_OFF = "#C9CED6"
_PICKER_CLICKS = 3
_PICKER_WINDOW_S = 0.8


def paint_pet(painter, pet: Pet, width: float = WIDTH, feet: float = FEET, dark: bool = False) -> None:
    """Draws the pet, its act and its particles, feet at (width / 2, feet) in painter coordinates."""
    colours = {cell: QColor(value) for cell, value in pet.skin.palette.items()}
    rows = frame(pet)
    across = PIXEL * (1.0 + pet.squash)
    down = PIXEL * (1.0 - pet.squash)
    left = width / 2 - len(rows[0]) * across / 2
    top = feet - len(rows) * down
    view = act_view(pet)
    colour_at = {
        (r, c + view.shift.get(r, 0)): colours[cell]
        for r, row in enumerate(rows) for c, cell in enumerate(row) if cell in colours
    }

    def cell(r: int, c: int):
        return QRectF(left + c * across, top + r * down, across + 0.5, down + 0.5)

    outline = pet.skin.outline and dark
    if view.ghost is not None:
        painter.setOpacity(0.4 if outline else 0.3)
        for (r, c), colour in colour_at.items():
            painter.fillRect(QRectF(left + c * across + view.ghost, top + r * down, across, down),
                             QColor(_OUTLINE) if outline else colour)
        painter.setOpacity(1.0)
    if outline:
        for r, c in colour_at:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (r + dr, c + dc) not in colour_at:
                    painter.fillRect(cell(r + dr, c + dc), QColor(_OUTLINE))
    for (r, c), colour in colour_at.items():
        painter.fillRect(cell(r, c), colour)
    _paint_act(painter, pet, view, width, feet)
    _paint_particles(painter, pet, width, feet)


def _paint_particles(painter, pet: Pet, width: float, feet: float) -> None:
    font = QFont()
    font.setBold(True)
    font.setPixelSize(14)
    for particle in pet.particles:
        painter.setOpacity(max(0.0, min(1.0, particle.life * 2.0)))
        x, y = width / 2 + particle.x, feet + particle.y
        if particle.kind == "tear":
            painter.fillRect(QRectF(x - 1.5, y, 3, 5), QColor(_TEAR))
        elif particle.kind == "ring":
            grow = (0.4 - particle.life) * 90
            painter.setPen(QPen(QColor(_SIGNAL), 2))
            painter.setBrush(_enum("BrushStyle", "NoBrush"))
            painter.drawEllipse(QPointF(x, y - 1), 10 + grow, 3 + grow / 8)
        elif particle.kind == "puff":
            size = 4 + (0.6 - particle.life) * 10
            painter.fillRect(QRectF(x - size / 2, y - size / 2, size, size), QColor(_PUFF))
        elif particle.kind in _SHAPES:
            shape, colour = _SHAPES[particle.kind]
            for r, row in enumerate(shape):
                for c, mark in enumerate(row):
                    if mark == "x":
                        painter.fillRect(QRectF(x - 7.5 + c * 3, y + r * 3, 3, 3), QColor(colour))
        else:
            painter.setFont(font)
            painter.setPen(QColor(_SLEEP if particle.kind == "z" else _MARK))
            painter.drawText(QRectF(x - 20, y - 10, 40, 20), _enum("AlignmentFlag", "AlignCenter"), particle.kind)
    painter.setOpacity(1.0)


def _paint_act(painter, pet: Pet, view: ActView, width: float, feet: float) -> None:
    top = feet - pet.skin.height
    centre = width / 2
    if view.noise is not None:
        rng = random.Random(view.noise)
        for _ in range(50):
            painter.fillRect(QRectF(rng.randrange(0, int(width), 3), rng.randrange(0, int(top) + 20, 3), 3, 3),
                             QColor(rng.choice(_NOISE)))
    for name, x, y, alpha in view.props:
        grid, palette = PROPS[name]
        left = centre + x - len(grid[0]) * _PROP_PIXEL / 2
        upper = feet + y - len(grid) * _PROP_PIXEL / 2
        painter.setOpacity(alpha)
        for r, row in enumerate(grid):
            for c, mark in enumerate(row):
                if mark in palette:
                    painter.fillRect(QRectF(left + c * _PROP_PIXEL, upper + r * _PROP_PIXEL, _PROP_PIXEL, _PROP_PIXEL),
                                     QColor(palette[mark]))
        painter.setOpacity(1.0)
    if view.bars is not None:
        for i in range(4):
            height = 3 + i * 3
            painter.fillRect(QRectF(centre + 38 + i * 5, top - height, 3, height),
                             QColor(_BAR_ON if i < view.bars else _BAR_OFF))
    if view.wave is not None:
        painter.setPen(QPen(QColor(_SIGNAL), 2))
        base = top - 26
        points = [QPointF(centre - 50, base)]
        for i in range(5):
            x = centre - 44 + i * 20
            high = base - (10 if i == view.wave else 4)
            points += [QPointF(x, base), QPointF(x, high), QPointF(x + 6, high), QPointF(x + 6, base)]
        points.append(QPointF(centre + 50, base))
        for a, b in zip(points, points[1:]):
            painter.drawLine(a, b)
    if view.orbit is not None:
        cx, cy = centre, top - 20
        painter.setBrush(_enum("BrushStyle", "NoBrush"))
        painter.setPen(QPen(QColor(_BAR_OFF), 1))
        for tilt in (0.0, 60.0):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(tilt)
            painter.drawEllipse(QPointF(0, 0), 22, 7)
            phase = view.orbit + tilt / 30.0
            painter.fillRect(QRectF(22 * math.cos(phase) - 2, 7 * math.sin(phase) - 2, 4, 4), QColor(_SIGNAL))
            painter.restore()
        painter.fillRect(QRectF(cx - 3, cy - 3, 6, 6), QColor(_TONES["bad"]))
    if view.dots is not None:
        for i in range(3):
            painter.fillRect(QRectF(centre - 11 + i * 8, top - 12, 5, 5),
                             QColor(_TONES["dim"] if i < view.dots else _BAR_OFF))
    font = QFont("Monospace")
    font.setStyleHint(_scoped(QFont, "StyleHint", "Monospace"))
    font.setBold(True)
    font.setPixelSize(10)
    painter.setFont(font)
    for text, x, y, tone in view.labels:
        painter.setPen(QColor(_TONES[tone]))
        painter.drawText(QRectF(centre + x - 50, feet + y - 7, 100, 14), _enum("AlignmentFlag", "AlignCenter"), text)


class _Base(QWidget):
    """What both modes share: the clock, the perches, the app's hints, and the skin menu."""

    def __init__(self, host, parent, flags, skin: str, acts: dict | None, dark: bool | None,
                 perches: Iterable[type] | Callable | None, on_skin: Callable[[str], None] | None) -> None:
        super().__init__(parent, flags) if flags is not None else super().__init__(parent)
        self._host = host
        self.pet = Pet(0.0, 0.0)
        self.pet.acts = dict(GNSS_ACTS if acts == "gnss" else (acts or {}))
        self.pet.skin = skin_named(skin)
        self._dark = dark
        self._perch_test = perches if callable(perches) else None
        self._perch_classes = tuple(perches) if perches is not None and not callable(perches) else DEFAULT_PERCHES
        self._perches: list = []
        self._perches_age = PERCH_REFRESH_S
        self._on_skin = on_skin
        self._clicks: list[float] = []
        self._samples: list[tuple[float, float, float]] = []
        self._grip = (0.0, 0.0)
        self._typed_in = None
        self._typed = ""
        self._modal = None
        self._elapsed = QElapsedTimer()
        self._since = QElapsedTimer()
        self._since.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # -- the app's side ------------------------------------------------------------------

    def start(self) -> None:
        self._elapsed.start()
        self._enter()
        self.show()
        self._timer.start(FRAME_MS)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def set_skin(self, key: str) -> None:
        self.pet.skin = skin_named(key)
        self.update()

    def skin_menu(self):
        menu = QMenu(self)
        for skin in SKINS.values():
            action = menu.addAction(skin.name)
            action.setCheckable(True)
            action.setChecked(skin is self.pet.skin)
            action.setData(skin.key)
        return menu

    # -- each frame ------------------------------------------------------------------------

    def _tick(self) -> None:
        dt = self._elapsed.restart() / 1000.0
        if not self._host_shown():
            return
        self._perches_age += dt
        if self._perches_age >= PERCH_REFRESH_S:
            self._perches = self._find_perches()
            self._perches_age = 0.0
        self._notice_typing()
        self._notice_popup()
        self.pet.step(dt, self._ledges(), self._cursor(), self._bounds())
        self._place()
        self.update()

    def _host_shown(self) -> bool:
        return _alive(self._host) and self._host.isVisible() and not self._host.isMinimized()

    def _is_perch(self, widget) -> bool:
        if self._perch_test is not None:
            return bool(self._perch_test(widget))
        return isinstance(widget, self._perch_classes)

    def _find_perches(self) -> list:
        return [
            widget for widget in self._host.findChildren(QWidget)
            if widget is not self and widget.isVisible() and widget.width() >= MIN_PERCH
            and not isinstance(widget, _Base) and self._is_perch(widget)
        ]

    def _widget_ledges(self, to_space: Callable) -> list[Ledge]:
        ledges = []
        host_left, host_top = to_space(self._host, 0, 0)
        host_right, host_bottom = to_space(self._host, self._host.width(), self._host.height())
        for widget in self._perches:
            if not _alive(widget) or not widget.isVisible():
                continue
            x, y = to_space(widget, 0, 0)
            if not host_top < y < host_bottom:
                continue
            left, right = max(x, host_left), min(x + widget.width(), host_right)
            if right - left >= MIN_PERCH:
                ledges.append(Ledge(float(left), float(right), float(y), widget))
        return ledges

    def _notice_typing(self) -> None:
        field = QApplication.focusWidget()
        if field is None or not hasattr(field, "text") or not self._host.isAncestorOf(field):
            self._typed_in = None
            return
        try:
            text = field.text()
        except TypeError:
            return
        if field is self._typed_in and text != self._typed:
            self.pet.watch(*self._to_pet_space(field, field.width() / 2, field.height() / 2))
        self._typed_in, self._typed = field, text

    def _notice_popup(self) -> None:
        modal = QApplication.activeModalWidget()
        if modal is not None and modal is not self._modal:
            self.pet.startle()
        self._modal = modal

    def _count_click(self) -> bool:
        now = self._since.elapsed() / 1000.0
        self._clicks = [t for t in self._clicks if now - t < _PICKER_WINDOW_S] + [now]
        return len(self._clicks) >= _PICKER_CLICKS

    def _pick_skin(self) -> None:
        chosen = self.skin_menu().exec(QCursor.pos()) if hasattr(QMenu, "exec") else self.skin_menu().exec_(QCursor.pos())
        if chosen is not None and chosen.data() != self.pet.skin.key:
            self.set_skin(chosen.data())
            self.pet.cheer()
            if self._on_skin is not None:
                self._on_skin(chosen.data())

    # -- picking it up ---------------------------------------------------------------------

    def _press(self, gx: float, gy: float) -> None:
        self._clicks_done = self._count_click()
        x, y = self._global_to_pet(gx, gy)
        self._grip = (self.pet.x - x, self.pet.y - y)
        self._samples = [(self._since.elapsed() / 1000.0, x, y)]
        self.pet.grab()

    def _move(self, gx: float, gy: float) -> None:
        x, y = self._global_to_pet(gx, gy)
        self.pet.drag_to(x + self._grip[0], y + self._grip[1])
        now = self._since.elapsed() / 1000.0
        self._samples = [s for s in self._samples if now - s[0] < 0.1] + [(now, x, y)]
        self._place()

    def _release(self) -> None:
        first, last = self._samples[0], self._samples[-1]
        span = last[0] - first[0]
        self.pet.throw(*(((last[1] - first[1]) / span, (last[2] - first[2]) / span) if span > 0 else (0.0, 0.0)))
        self._samples = []
        if getattr(self, "_clicks_done", False):
            self._clicks = []
            QTimer.singleShot(0, self._pick_skin)

    def _dark_now(self) -> bool:
        if self._dark is not None:
            return self._dark
        return self.palette().color(self.backgroundRole()).lightness() < 128 or \
            QApplication.palette().window().color().lightness() < 128

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.translate(*self._paint_origin())
        paint_pet(painter, self.pet, WIDTH, FEET, self._dark_now())
        painter.end()


class WindowPet(_Base):
    """The pet as a sprite inside `host`: every platform, Wayland included.

    It is click-through: the app keeps every click except the ones on the pet's own body,
    which pick it up. Coordinates are the host window's own.
    """

    def __init__(self, host, skin: str = "clawd", acts: dict | str | None = None, dark: bool | None = None,
                 perches: Iterable[type] | Callable | None = None,
                 on_skin: Callable[[str], None] | None = None) -> None:
        super().__init__(host, host, None, skin, acts, dark, perches, on_skin)
        self.setAttribute(_enum("WidgetAttribute", "WA_TransparentForMouseEvents"))
        self.resize(host.width(), host.height())
        QApplication.instance().installEventFilter(self)

    def _enter(self) -> None:
        self.pet.x, self.pet.y = self._host.width() / 2, -60.0
        self._place()

    def _to_pet_space(self, widget, x: float, y: float) -> tuple[float, float]:
        point = widget.mapTo(self._host, QPoint(int(x), int(y)))
        return float(point.x()), float(point.y())

    def _global_to_pet(self, gx: float, gy: float) -> tuple[float, float]:
        point = self._host.mapFromGlobal(QPoint(int(gx), int(gy)))
        return float(point.x()), float(point.y())

    def _ledges(self) -> list[Ledge]:
        floor = Ledge(0.0, float(self._host.width()), float(self._host.height()))
        return [floor, *self._widget_ledges(self._to_pet_space)]

    def _cursor(self) -> tuple[float, float]:
        pos = QCursor.pos()
        return self._global_to_pet(pos.x(), pos.y())

    def _bounds(self) -> Bounds:
        return Bounds(0.0, 0.0, float(self._host.width()), float(self._host.height()))

    def _place(self) -> None:
        if self.size() != self._host.size():
            self.resize(self._host.size())
        self.raise_()

    def _paint_origin(self) -> tuple[float, float]:
        return self.pet.x - WIDTH / 2, self.pet.y - FEET

    def body_rect(self) -> tuple[float, float, float, float]:
        skin = self.pet.skin
        return (self.pet.x - skin.width / 2, self.pet.y - skin.height, skin.width, skin.height)

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind not in (_event("MouseButtonPress"), _event("MouseMove"), _event("MouseButtonRelease"),
                        _event("MouseButtonDblClick")):
            return False
        if not isinstance(watched, QWidget) or watched.window() is not self._host.window():
            return False
        gx, gy = _global_pos(event)
        if kind == _event("MouseMove"):
            if self._samples:
                self._move(gx, gy)
                return True
            return False
        if kind == _event("MouseButtonRelease"):
            if self._samples:
                self._release()
                return True
            return False
        if event.button() != _enum("MouseButton", "LeftButton"):
            return False
        x, y = self._global_to_pet(gx, gy)
        left, top, width, height = self.body_rect()
        if not (left <= x <= left + width and top <= y <= top + height):
            return False
        if kind == _event("MouseButtonDblClick"):
            self._samples = []
            self.pet.cheer()
        else:
            self._press(gx, gy)
        return True

    def stop(self) -> None:
        super().stop()
        QApplication.instance().removeEventFilter(self)


class DesktopPet(_Base):
    """The pet as its own small always-on-top window, free to roam every screen.

    Needs a platform that lets a window place itself: X11, Windows, macOS. On Wayland use
    WindowPet -- the compositor ignores the moves and the pet would sit in one place.
    """

    def __init__(self, host, skin: str = "clawd", acts: dict | str | None = None, dark: bool | None = None,
                 perches: Iterable[type] | Callable | None = None,
                 on_skin: Callable[[str], None] | None = None) -> None:
        flags = (_enum("WindowType", "Tool") | _enum("WindowType", "FramelessWindowHint")
                 | _enum("WindowType", "WindowStaysOnTopHint") | _enum("WindowType", "WindowDoesNotAcceptFocus")
                 | _enum("WindowType", "NoDropShadowWindowHint"))
        super().__init__(host, None, flags, skin, acts, dark, perches, on_skin)
        self.setAttribute(_enum("WidgetAttribute", "WA_TranslucentBackground"))
        self.setAttribute(_enum("WidgetAttribute", "WA_ShowWithoutActivating"))
        self.setFixedSize(WIDTH, HEIGHT)
        self.setWindowTitle(self.pet.skin.name)

    def _enter(self) -> None:
        entrance = self._host.frameGeometry()
        self.pet.x, self.pet.y = float(entrance.center().x()), float(entrance.top() - 260)
        self._place()

    def _to_pet_space(self, widget, x: float, y: float) -> tuple[float, float]:
        point = widget.mapToGlobal(QPoint(int(x), int(y)))
        return float(point.x()), float(point.y())

    def _global_to_pet(self, gx: float, gy: float) -> tuple[float, float]:
        return gx, gy

    def _ledges(self) -> list[Ledge]:
        ledges = [
            Ledge(float(area.left()), float(area.right()), float(area.bottom() + 1))
            for area in (screen.availableGeometry() for screen in QGuiApplication.screens())
        ]
        outline = self._host.frameGeometry()
        ledges.append(Ledge(float(outline.left() + 12), float(outline.right() - 12), float(outline.top()), self._host))
        return ledges + self._widget_ledges(self._to_pet_space)

    def _cursor(self) -> tuple[float, float]:
        pos = QCursor.pos()
        return float(pos.x()), float(pos.y())

    def _bounds(self) -> Bounds:
        screen = QGuiApplication.primaryScreen()
        area = screen.virtualGeometry()
        return Bounds(float(area.left()), float(area.top()), float(area.right()), float(area.bottom()))

    def _place(self) -> None:
        self.move(round(self.pet.x - WIDTH / 2), round(self.pet.y - FEET))

    def _paint_origin(self) -> tuple[float, float]:
        return 0.0, 0.0

    def mousePressEvent(self, event) -> None:
        if event.button() == _enum("MouseButton", "LeftButton"):
            self._press(*_global_pos(event))

    def mouseMoveEvent(self, event) -> None:
        if self._samples:
            self._move(*_global_pos(event))

    def mouseReleaseEvent(self, event) -> None:
        if self._samples:
            self._release()

    def mouseDoubleClickEvent(self, event) -> None:
        self._samples = []
        self.pet.cheer()
