"""A small GTK 3 window with the pet in it:  python3 examples/gtk_app.py [--cat]"""

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "desktop-pet" / "assets" / "python"))

from desktop_pet.gtk import GtkPet  # noqa: E402


def main() -> None:
    window = Gtk.Window(title="Desktop pet -- GTK")
    window.set_default_size(640, 480)
    window.connect("destroy", Gtk.main_quit)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=12)
    box.pack_start(Gtk.Entry(margin_top=28), False, False, 0)
    progress = Gtk.ProgressBar()
    progress.set_fraction(0.4)
    box.pack_start(progress, False, False, 0)
    row = Gtk.Box(spacing=8)
    box.pack_end(row, False, False, 0)
    buttons = {name: Gtk.Button(label=name) for name in ("Save", "Fail", "Work")}
    for button in buttons.values():
        row.pack_start(button, True, True, 0)
    window.add(box)
    window.show_all()

    pet = GtkPet(window, skin="cat" if "--cat" in sys.argv else "clawd")
    pet.start()
    buttons["Save"].connect("clicked", lambda _b: pet.pet.cheer())
    buttons["Fail"].connect("clicked", lambda _b: pet.pet.feel("angry", 5))

    def work(_button) -> None:
        pet.pet.thinking = True
        GLib.timeout_add(3000, lambda: setattr(pet.pet, "thinking", False))

    buttons["Work"].connect("clicked", work)
    Gtk.main()


if __name__ == "__main__":
    main()
