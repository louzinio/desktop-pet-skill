# IDLE with the pet

What the skill did to IDLE (Python 3.12's `idlelib`), as a worked example on a real app:

1. `scripts/detect_toolkit.py` found Tk and pointed at `pyshell.py`.
2. `core.py`, `tk.py` and `__init__.py` were copied to `idlelib/desktop_pet/`.
3. `pyshell.patch` attaches the pet to the shell window in `PyShell.begin()` (off with
   `IDLE_PET=0`, and never able to stop the shell opening), keeps it off the shell's
   full-window text widget, and wires four moods: thinking while code runs, angry at a
   `SyntaxError`, startled when the interpreter restarts.

```bash
cp -r /usr/lib/python3.12/idlelib .
mkdir idlelib/desktop_pet
cp <skill>/assets/python/desktop_pet/{__init__,core,tk}.py idlelib/desktop_pet/
patch -p0 < <this folder>/pyshell.patch
PYTHONPATH=. python3 -m idlelib
```
