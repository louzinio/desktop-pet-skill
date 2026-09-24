---
name: desktop-pet
description: Adds a living pixel-art pet (Clawd, or the cat "Amir Latex") to an existing desktop or web app. It stands on the app's own buttons and fields, walks, jumps between them, chases and rides the cursor, can be picked up and thrown, falls asleep, watches the user type, and shows the app's moods. Ready adapters for Qt (PySide6/PyQt6/PySide2/PyQt5), Tkinter, GTK 3 and web/Electron/Tauri, plus a verified core to port to any other toolkit or language (C++ Qt, GTK 4, Swing, JavaFX, wx, Flutter, egui, terminal UIs). Use this whenever someone wants a pet, mascot, companion, buddy, critter or "something cute that walks around" in their app or GUI, wants to put Clawd or the cat into a project, or asks to add the companion from OFIR to another app -- on Linux, Windows or macOS, X11 or Wayland -- even if they don't say "desktop pet".
---

# Desktop pet

A small pixel creature that lives on an app's window. The behaviour, physics and pixel art
are one dependency-free core; a thin adapter per toolkit feeds it the world and draws it.
Your job is to vendor the core and the right adapter into the target app, attach it to the
main window, wire a few of the app's own events to the pet's feelings, and prove it works.

## What you are building

Every frame the adapter calls

```
pet.step(dt, ledges, cursor, bounds)
```

- **ledges** -- horizontal surfaces the pet can stand on: the top edge of each visible
  button, field, list, card..., plus a floor at the bottom of the window. Each carries a
  `key` (the widget object itself) so the pet rides along when the widget moves.
- **cursor** and **bounds** -- in the same coordinate space as the ledges.

then draws `frame(pet)` (rows of palette letters, feet at `pet.x, pet.y`), `act_view(pet)`
and `pet.particles`. It also turns presses on the pet's body into `grab()`, `drag_to()` and
`throw()`, and lets every other click fall through to the app. That is the whole contract;
`references/core-api.md` has the details.

## Workflow

### 1. Find the toolkit and the main window

```bash
python <skill>/scripts/detect_toolkit.py /path/to/app
```

It reports the toolkit(s) with evidence files, the files that probably build the main
window, and whether a ready adapter exists. Read the entry point and the main-window file
yourself before deciding -- an app can import two toolkits, and the busiest is not always
the one that owns the window.

### 2. Pick the path

| Toolkit | Path |
| --- | --- |
| Python + Qt (PySide6, PyQt6, PySide2, PyQt5) | `assets/python/desktop_pet/qt.py` -- `WindowPet` |
| Python + Tkinter / ttk / customtkinter | `assets/python/desktop_pet/tk.py` -- `TkPet` |
| Python + GTK 3 (PyGObject) | `assets/python/desktop_pet/gtk.py` -- `GtkPet` |
| Web page, Electron, Tauri, any webview | `assets/js/pet-core.js` + `assets/js/pet-dom.js` -- `attachPet()` |
| Anything else | read its section in `references/toolkits.md`, then port the core per `references/porting.md` |

Prefer the **in-window** mode everywhere. It works on X11, Wayland, Windows and macOS
because the pet never has to position a window of its own -- Wayland does not allow that.
Qt also has `DesktopPet`, which roams the whole screen as its own window; offer it only
when the user asks for that and runs X11, Windows or macOS.

### 3. Vendor the files

Copy, don't install -- the point is that the app gains no dependency.

- **Python**: copy `assets/python/desktop_pet/` into the app's package (for example
  `<app>/desktop_pet/` or `<app>/third_party/desktop_pet/`). Keep `__init__.py`, `core.py`
  and only the adapter the app needs; drop the others so nothing imports a toolkit the app
  does not have. Fix the import to match where you put it (`from .desktop_pet.qt import ...`).
- **JavaScript**: copy `pet-core.js` and `pet-dom.js` next to the app's other static
  scripts and import them as ES modules (or let the app's bundler pick them up).
- Keep the MIT notice: a `LICENSE` line or header comment crediting
  `github.com/louzinio/desktop-pet-skill` in the vendored folder.

### 4. Attach it to the main window

Create the pet once the main window exists and is shown, keep a reference to it for the
window's lifetime (a garbage-collected pet stops moving), and stop it when the window
closes. Minimal forms:

```python
# Qt -- after main_window.show()
from .desktop_pet.qt import WindowPet
self.pet = WindowPet(main_window)            # skin="cat" for Amir Latex
self.pet.start()
```

```python
# Tkinter -- after the widgets are built, before root.mainloop()
from .desktop_pet.tk import TkPet
pet = TkPet(root)
pet.start()
```

```python
# GTK 3 -- after window.add(content); it moves the content into a Gtk.Overlay
from .desktop_pet.gtk import GtkPet
pet = GtkPet(window)
pet.start()
```

```js
// Web / Electron renderer / Tauri
import { attachPet } from "./pet-dom.js";
const pet = attachPet();          // attachPet({ skin: "cat", perches: "button,.card" })
```

Guard the start so a problem in the pet can never take the app down: wrap it in the app's
usual error handling and log instead of raising. The pet must not steal focus, change the
app's layout, or block clicks anywhere but on its own body -- the adapters are built that
way; keep it so if you edit them.

### 5. Make it optional

Give the user a way to turn it off that fits the app: a checkbox or menu item in existing
settings if there are settings, otherwise an environment variable (`APPNAME_PET=0`) read
where you attach it. Ask the user whether it should start on or off if they have not said.

### 6. Wire the app's moods (this is what makes it feel native)

Find two to four real events in the app and connect them. Look for places that already
show a message, finish a job, or report an error:

| App event | Call |
| --- | --- |
| something succeeded (saved, built, sent, test passed) | `pet.pet.cheer()` or `pet.pet.feel("happy", 3)` |
| an error or failure | `pet.pet.feel("angry", 6)` -- or `"sad"` if it is a loss rather than a fault |
| a long job starts / ends | `pet.pet.thinking = True` / `False` (three dots over its head) |
| a dialog or popup opens | `pet.pet.startle()` (the Qt adapter does this by itself) |

(`pet.pet` in Python adapters, `pet.core` on the web.) Don't wire every event; a pet that
reacts to everything is noise.

### 7. Tune where it stands

The defaults treat buttons, inputs, lists, progress bars, labels and similar as perches.
Pass `perches=` (widget classes, class names, a CSS selector, or a predicate) when the app
needs something different -- for example, exclude a full-window text editor whose top edge
is just under the toolbar, or add the app's own card/panel class. Each adapter exports its
defaults as `DEFAULT_PERCHES`, so "the defaults but not the editor" is one line:

```python
from .desktop_pet.tk import DEFAULT_PERCHES, TkPet
pet = TkPet(root, perches=DEFAULT_PERCHES - {"Text"})                       # Tk: class names
pet = WindowPet(win, perches=lambda w: isinstance(w, DEFAULT_PERCHES) and w is not editor)  # Qt
```

### 8. Prove it works

Run the app and look -- a screenshot is the evidence, not a guess:

- Qt: `QT_QPA_PLATFORM=offscreen` and `window.grab().save("pet.png")` after a few seconds.
- Tk / GTK on Linux without a display: run it under `xvfb-run -a`, and take the
  screenshot with ImageMagick (`import -window root pet.png`) or the toolkit's own snapshot.
- Web: open the page in a browser (Playwright if headless) and screenshot.

Check three things and report them: the pet landed on a real widget (`pet.pet.ledge.key`
is that widget), a click beside the pet still reaches the app, and a press on the pet
picks it up. If the app has a test suite and a headless way to run its UI, add a test for
the first two; `references/core-api.md` ends with how.

## Customising

- **Skins** live in `core.py` / `pet-core.js`: rows of letters, a palette, a face function.
  Add one by copying `CAT` and redrawing the rows; `stalks=True` makes it creep before
  pouncing, `outline=True` gives it a light edge on dark themes.
- **Acts** are optional skits it performs now and then. None are on by default; the GNSS
  pack from OFIR (satellite fix, jamming, spoofing, 1PPS, cesium, holdover) is
  `acts="gnss"`. For a themed app you can add one: a duration in the act table, its
  behaviour in `_acting`, its drawing in `act_view` -- see `references/core-api.md`.

## Porting to another language

If the app is C++, Rust, Java, Dart, C#... port `core.py` rather than re-inventing the
behaviour, and prove the port against `assets/reference_trace.json` -- a scripted world
with the expected state after each of 4,400 steps, for two skins. `references/porting.md`
walks through it; `scripts/check_js_core.mjs` is a complete replay check to translate.
