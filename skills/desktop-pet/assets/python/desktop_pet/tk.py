"""Tkinter adapter for the desktop pet.

    from desktop_pet.tk import TkPet
    pet = TkPet(root)        # root is the app's Tk() or a Toplevel
    pet.start()

Tk widgets cannot be transparent, so the pet is drawn as a handful of small coloured
frames -- one per run of same-coloured pixels -- placed over the window. Everything else
in the window stays clickable. The body, the face, the feelings and the tears, puffs,
hearts and veins and the thinking dots are drawn; the text marks ("!", "z"...) and the act
props are not.
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable, Iterable

from .core import GNSS_ACTS, PIXEL, Bounds, Ledge, Pet, act_view, frame, skin_named

FRAME_MS = 16
PERCH_REFRESH_S = 0.5
MIN_PERCH = 56
DEFAULT_PERCHES = frozenset({
    "Button", "TButton", "Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox", "Text", "Listbox",
    "Treeview", "TNotebook", "TProgressbar", "Labelframe", "TLabelframe", "Scale", "TScale",
    "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton", "Canvas", "Label", "TLabel",
    "Menubutton", "TMenubutton",
})
_SHAPES = {
    "heart": ((".x.x.", "xxxxx", ".xxx.", "..x.."), "#E0557A"),
    "vein": ((".x.x.", "xx.xx", ".....", "xx.xx", ".x.x."), "#C8432B"),
}
_TEAR = "#5DB8F0"
_PUFF = "#7D8691"
_DOT_ON = "#7A8BA8"
_DOT_OFF = "#C9CED6"


class TkPet:
    def __init__(self, root, skin: str = "clawd", acts: dict | str | None = None,
                 perches: Iterable[str] | Callable | None = None) -> None:
        self.root = root
        self.pet = Pet(0.0, 0.0)
        self.pet.skin = skin_named(skin)
        self.pet.acts = dict(GNSS_ACTS if acts == "gnss" else (acts or {}))
        self._perch_test = perches if callable(perches) else None
        self._perch_classes = frozenset(perches) if perches is not None and not callable(perches) else DEFAULT_PERCHES
        self._pool: list[tk.Frame] = []
        self._used = 0
        self._perches: list = []
        self._perches_age = PERCH_REFRESH_S
        self._last = 0.0
        self._job = None
        self._samples: list[tuple[float, float, float]] = []
        self._grip = (0.0, 0.0)

    # -- the app's side ------------------------------------------------------------------

    def start(self) -> None:
        self.root.update_idletasks()
        self.pet.x, self.pet.y = self.root.winfo_width() / 2, -60.0
        self._last = time.monotonic()
        self._job = self.root.after(FRAME_MS, self._tick)

    def stop(self) -> None:
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
        for tile in self._pool:
            tile.place_forget()

    def set_skin(self, key: str) -> None:
        self.pet.skin = skin_named(key)

    # -- each frame ------------------------------------------------------------------------

    def _tick(self) -> None:
        self._job = self.root.after(FRAME_MS, self._tick)
        now = time.monotonic()
        dt, self._last = now - self._last, now
        if not self.root.winfo_viewable():
            return
        self._perches_age += dt
        if self._perches_age >= PERCH_REFRESH_S:
            self._perches = list(self._find_perches(self.root))
            self._perches_age = 0.0
        self.pet.step(dt, self._ledges(), self._cursor(), self._bounds())
        self._draw()

    def _is_perch(self, widget) -> bool:
        if self._perch_test is not None:
            return bool(self._perch_test(widget))
        return widget.winfo_class() in self._perch_classes

    def _find_perches(self, parent):
        for widget in parent.winfo_children():
            if widget in self._pool or isinstance(widget, (tk.Toplevel, tk.Menu)):
                continue
            if widget.winfo_ismapped() and widget.winfo_width() >= MIN_PERCH and self._is_perch(widget):
                yield widget
            yield from self._find_perches(widget)

    def _local(self, widget) -> tuple[int, int]:
        return widget.winfo_rootx() - self.root.winfo_rootx(), widget.winfo_rooty() - self.root.winfo_rooty()

    def _ledges(self) -> list[Ledge]:
        width, height = self.root.winfo_width(), self.root.winfo_height()
        ledges = [Ledge(0.0, float(width), float(height))]
        for widget in self._perches:
            try:
                if not widget.winfo_ismapped():
                    continue
                x, y = self._local(widget)
                right = min(x + widget.winfo_width(), width)
            except tk.TclError:
                continue
            left = max(x, 0)
            if 0 < y < height and right - left >= MIN_PERCH:
                ledges.append(Ledge(float(left), float(right), float(y), widget))
        return ledges

    def _cursor(self) -> tuple[float, float]:
        x, y = self.root.winfo_pointerxy()
        return float(x - self.root.winfo_rootx()), float(y - self.root.winfo_rooty())

    def _bounds(self) -> Bounds:
        return Bounds(0.0, 0.0, float(self.root.winfo_width()), float(self.root.winfo_height()))

    # -- drawing ---------------------------------------------------------------------------

    def _tile(self, x: float, y: float, width: float, height: float, colour: str) -> None:
        if self._used == len(self._pool):
            tile = tk.Frame(self.root, borderwidth=0, highlightthickness=0, cursor="hand2", takefocus=0)
            tile.bind("<ButtonPress-1>", self._press)
            tile.bind("<B1-Motion>", self._move)
            tile.bind("<ButtonRelease-1>", self._release)
            tile.bind("<Double-Button-1>", lambda _event: self.pet.cheer())
            self._pool.append(tile)
        tile = self._pool[self._used]
        self._used += 1
        tile.configure(background=colour)
        tile.place(x=round(x), y=round(y), width=max(1, round(width)), height=max(1, round(height)))
        tile.lift()

    def _draw(self) -> None:
        self._used = 0
        pet = self.pet
        rows = frame(pet)
        palette = pet.skin.palette
        across = PIXEL * (1.0 + pet.squash)
        down = PIXEL * (1.0 - pet.squash)
        left = pet.x - len(rows[0]) * across / 2
        top = pet.y - len(rows) * down
        for r, row in enumerate(rows):
            c = 0
            while c < len(row):
                cell = row[c]
                end = c + 1
                while end < len(row) and row[end] == cell:
                    end += 1
                if cell in palette:
                    self._tile(left + c * across, top + r * down, (end - c) * across, down, palette[cell])
                c = end
        dots = act_view(pet).dots
        if dots is not None:
            for i in range(3):
                self._tile(pet.x - 11 + i * 8, pet.y - pet.skin.height - 12, 5, 5, _DOT_ON if i < dots else _DOT_OFF)
        for particle in pet.particles:
            x, y = pet.x + particle.x, pet.y + particle.y
            if particle.kind == "tear":
                self._tile(x - 1.5, y, 3, 5, _TEAR)
            elif particle.kind == "puff":
                size = 4 + (0.6 - particle.life) * 10
                self._tile(x - size / 2, y - size / 2, size, size, _PUFF)
            elif particle.kind in _SHAPES:
                shape, colour = _SHAPES[particle.kind]
                for r, row in enumerate(shape):
                    for c, mark in enumerate(row):
                        if mark == "x":
                            self._tile(x - 7.5 + c * 3, y + r * 3, 3, 3, colour)
        for tile in self._pool[self._used:]:
            tile.place_forget()

    # -- picking it up ---------------------------------------------------------------------

    def _press(self, event) -> None:
        x, y = event.x_root - self.root.winfo_rootx(), event.y_root - self.root.winfo_rooty()
        self._grip = (self.pet.x - x, self.pet.y - y)
        self._samples = [(time.monotonic(), float(x), float(y))]
        self.pet.grab()

    def _move(self, event) -> None:
        if not self._samples:
            return
        x, y = event.x_root - self.root.winfo_rootx(), event.y_root - self.root.winfo_rooty()
        self.pet.drag_to(x + self._grip[0], y + self._grip[1])
        now = time.monotonic()
        self._samples = [s for s in self._samples if now - s[0] < 0.1] + [(now, float(x), float(y))]

    def _release(self, _event) -> None:
        if not self._samples:
            return
        first, last = self._samples[0], self._samples[-1]
        span = last[0] - first[0]
        self.pet.throw(*(((last[1] - first[1]) / span, (last[2] - first[2]) / span) if span > 0 else (0.0, 0.0)))
        self._samples = []
