"""GTK 3 adapter for the desktop pet (PyGObject).

    from desktop_pet.gtk import GtkPet
    pet = GtkPet(window)     # a Gtk.Window that already has its content
    pet.start()

The window's content is moved into a Gtk.Overlay and the pet is drawn on a DrawingArea
above it, so it works on X11 and Wayland alike. The DrawingArea's input region is kept to
the pet's body: every other click reaches the app underneath.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .core import GNSS_ACTS, PIXEL, Bounds, Ledge, Pet, act_view, frame, skin_named  # noqa: E402

FRAME_MS = 16
PERCH_REFRESH_S = 0.5
MIN_PERCH = 56
DEFAULT_PERCHES = (
    Gtk.Button, Gtk.Entry, Gtk.ComboBox, Gtk.TextView, Gtk.TreeView, Gtk.ProgressBar, Gtk.Frame,
    Gtk.Notebook, Gtk.Scale, Gtk.Label, Gtk.ListBox, Gtk.Switch,
)
_SHAPES = {
    "heart": ((".x.x.", "xxxxx", ".xxx.", "..x.."), "#E0557A"),
    "vein": ((".x.x.", "xx.xx", ".....", "xx.xx", ".x.x."), "#C8432B"),
}
_TEAR = "#5DB8F0"
_PUFF = "#7D8691"
_MARK = "#D97757"
_SLEEP = "#7A8BA8"
_DOT_OFF = "#C9CED6"


def _rgb(colour: str) -> tuple[float, float, float]:
    return tuple(int(colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


class GtkPet:
    def __init__(self, window: Gtk.Window, skin: str = "clawd", acts: dict | str | None = None,
                 perches: Iterable[type] | Callable | None = None) -> None:
        self.window = window
        self.pet = Pet(0.0, 0.0)
        self.pet.skin = skin_named(skin)
        self.pet.acts = dict(GNSS_ACTS if acts == "gnss" else (acts or {}))
        self._perch_test = perches if callable(perches) else None
        self._perch_classes = tuple(perches) if perches is not None and not callable(perches) else DEFAULT_PERCHES
        self.overlay = Gtk.Overlay()
        content = window.get_child()
        if content is not None:
            window.remove(content)
            self.overlay.add(content)
        window.add(self.overlay)
        self.area = Gtk.DrawingArea()
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                             | Gdk.EventMask.POINTER_MOTION_MASK)
        self.area.connect("draw", self._draw)
        self.area.connect("button-press-event", self._press)
        self.area.connect("motion-notify-event", self._move)
        self.area.connect("button-release-event", self._release)
        self.area.connect("realize", lambda _area: self._shape())
        self.overlay.add_overlay(self.area)
        self.overlay.show_all()
        self._perches: list = []
        self._perches_age = PERCH_REFRESH_S
        self._last = 0.0
        self._source = None
        self._samples: list[tuple[float, float, float]] = []
        self._grip = (0.0, 0.0)

    # -- the app's side ------------------------------------------------------------------

    def start(self) -> None:
        self.pet.x, self.pet.y = self.overlay.get_allocated_width() / 2, -60.0
        self._last = time.monotonic()
        self._source = GLib.timeout_add(FRAME_MS, self._tick)

    def stop(self) -> None:
        if self._source is not None:
            GLib.source_remove(self._source)
            self._source = None
        self.area.hide()

    def set_skin(self, key: str) -> None:
        self.pet.skin = skin_named(key)

    # -- each frame ------------------------------------------------------------------------

    def _tick(self) -> bool:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        if not self.window.get_mapped():
            return True
        self._perches_age += dt
        if self._perches_age >= PERCH_REFRESH_S:
            self._perches = list(self._find_perches(self.overlay))
            self._perches_age = 0.0
        self.pet.step(dt, self._ledges(), self._cursor(), self._bounds())
        self._shape()
        self.area.queue_draw()
        return True

    def _is_perch(self, widget) -> bool:
        if self._perch_test is not None:
            return bool(self._perch_test(widget))
        return isinstance(widget, self._perch_classes)

    def _find_perches(self, parent):
        if not isinstance(parent, Gtk.Container):
            return
        for widget in parent.get_children():
            if widget is self.area:
                continue
            if widget.get_mapped() and widget.get_allocated_width() >= MIN_PERCH and self._is_perch(widget):
                yield widget
            yield from self._find_perches(widget)

    def _ledges(self) -> list[Ledge]:
        width, height = self.overlay.get_allocated_width(), self.overlay.get_allocated_height()
        ledges = [Ledge(0.0, float(width), float(height))]
        for widget in self._perches:
            if not widget.get_mapped():
                continue
            placed = widget.translate_coordinates(self.overlay, 0, 0)
            if placed is None:
                continue
            x, y = placed
            left, right = max(x, 0), min(x + widget.get_allocated_width(), width)
            if 0 < y < height and right - left >= MIN_PERCH:
                ledges.append(Ledge(float(left), float(right), float(y), widget))
        return ledges

    def _cursor(self) -> tuple[float, float]:
        gdk_window = self.overlay.get_window()
        seat = Gdk.Display.get_default().get_default_seat() if gdk_window else None
        if seat is None:
            return self.pet.x, self.pet.y - 5000.0
        _window, x, y, _mask = gdk_window.get_device_position(seat.get_pointer())
        allocation = self.overlay.get_allocation()
        return float(x - allocation.x), float(y - allocation.y)

    def _bounds(self) -> Bounds:
        return Bounds(0.0, 0.0, float(self.overlay.get_allocated_width()),
                      float(self.overlay.get_allocated_height()))

    def body_rect(self) -> tuple[int, int, int, int]:
        skin = self.pet.skin
        return (int(self.pet.x - skin.width / 2), int(self.pet.y - skin.height), int(skin.width), int(skin.height))

    def _shape(self) -> None:
        # Gtk.Overlay wraps each overlay child in a window of its own, the size of the whole
        # overlay; it takes the clicks unless it gets the same input region as the pet.
        if not self.area.get_realized():
            return
        region = cairo.Region(cairo.RectangleInt(*self.body_rect()))
        self.area.input_shape_combine_region(region)
        wrapper = self.area.get_window().get_parent()
        if wrapper is not None and wrapper != self.overlay.get_window():
            wrapper.input_shape_combine_region(region, 0, 0)

    # -- drawing ---------------------------------------------------------------------------

    def _draw(self, _area, context) -> bool:
        pet = self.pet
        rows = frame(pet)
        palette = pet.skin.palette
        across = PIXEL * (1.0 + pet.squash)
        down = PIXEL * (1.0 - pet.squash)
        left = pet.x - len(rows[0]) * across / 2
        top = pet.y - len(rows) * down
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if cell in palette:
                    context.set_source_rgb(*_rgb(palette[cell]))
                    context.rectangle(left + c * across, top + r * down, across + 0.5, down + 0.5)
                    context.fill()
        dots = act_view(pet).dots
        if dots is not None:
            for i in range(3):
                context.set_source_rgb(*_rgb(_SLEEP if i < dots else _DOT_OFF))
                context.rectangle(pet.x - 11 + i * 8, pet.y - pet.skin.height - 12, 5, 5)
                context.fill()
        for particle in pet.particles:
            x, y = pet.x + particle.x, pet.y + particle.y
            alpha = max(0.0, min(1.0, particle.life * 2.0))
            if particle.kind == "tear":
                context.set_source_rgba(*_rgb(_TEAR), alpha)
                context.rectangle(x - 1.5, y, 3, 5)
                context.fill()
            elif particle.kind == "puff":
                size = 4 + (0.6 - particle.life) * 10
                context.set_source_rgba(*_rgb(_PUFF), alpha)
                context.rectangle(x - size / 2, y - size / 2, size, size)
                context.fill()
            elif particle.kind in _SHAPES:
                shape, colour = _SHAPES[particle.kind]
                context.set_source_rgba(*_rgb(colour), alpha)
                for r, row in enumerate(shape):
                    for c, mark in enumerate(row):
                        if mark == "x":
                            context.rectangle(x - 7.5 + c * 3, y + r * 3, 3, 3)
                context.fill()
            elif particle.kind != "ring":
                context.set_source_rgba(*_rgb(_SLEEP if particle.kind == "z" else _MARK), alpha)
                context.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                context.set_font_size(14)
                extent = context.text_extents(particle.kind)
                context.move_to(x - extent.width / 2, y + extent.height / 2)
                context.show_text(particle.kind)
        return False

    # -- picking it up ---------------------------------------------------------------------

    def _local(self, event) -> tuple[float, float]:
        placed = self.area.translate_coordinates(self.overlay, int(event.x), int(event.y))
        return (float(placed[0]), float(placed[1])) if placed else (event.x, event.y)

    def _press(self, _area, event) -> bool:
        if event.button != 1:
            return False
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self._samples = []
            self.pet.cheer()
            return True
        x, y = self._local(event)
        self._grip = (self.pet.x - x, self.pet.y - y)
        self._samples = [(time.monotonic(), x, y)]
        self.pet.grab()
        return True

    def _move(self, _area, event) -> bool:
        if not self._samples:
            return False
        x, y = self._local(event)
        self.pet.drag_to(x + self._grip[0], y + self._grip[1])
        self._shape()
        now = time.monotonic()
        self._samples = [s for s in self._samples if now - s[0] < 0.1] + [(now, x, y)]
        return True

    def _release(self, _area, _event) -> bool:
        if not self._samples:
            return False
        first, last = self._samples[0], self._samples[-1]
        span = last[0] - first[0]
        self.pet.throw(*(((last[1] - first[1]) / span, (last[2] - first[2]) / span) if span > 0 else (0.0, 0.0)))
        self._samples = []
        return True
