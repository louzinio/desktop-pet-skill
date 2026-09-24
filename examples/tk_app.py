"""A small Tkinter window with the pet in it:  python examples/tk_app.py [--cat]"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "desktop-pet" / "assets" / "python"))

from desktop_pet.tk import TkPet  # noqa: E402


def main() -> None:
    root = tk.Tk()
    root.title("Desktop pet -- Tk")
    root.geometry("640x480")
    ttk.Entry(root).pack(fill="x", padx=12, pady=(40, 12))
    progress = ttk.Progressbar(root, value=40)
    progress.pack(fill="x", padx=12, pady=12)
    row = ttk.Frame(root)
    row.pack(side="bottom", fill="x", padx=12, pady=12)
    pet = TkPet(root, skin="cat" if "--cat" in sys.argv else "clawd")
    ttk.Button(row, text="Save", command=pet.pet.cheer).pack(side="left", expand=True, fill="x")
    ttk.Button(row, text="Fail", command=lambda: pet.pet.feel("angry", 5)).pack(side="left", expand=True, fill="x")

    def work() -> None:
        pet.pet.thinking = True
        root.after(3000, lambda: setattr(pet.pet, "thinking", False))

    ttk.Button(row, text="Work", command=work).pack(side="left", expand=True, fill="x")
    pet.start()
    root.mainloop()


if __name__ == "__main__":
    main()
