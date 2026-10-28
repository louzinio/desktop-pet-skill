# The core, for adapter writers

`assets/python/desktop_pet/core.py` and its line-for-line port `assets/js/pet-core.js`.
Names below are Python's; the JavaScript ones are the camelCase equivalents
(`drag_to` -> `dragTo`, `act_view` -> `actView`, `act_time` -> `actTime`).

## Contents
- The frame loop
- Coordinates
- Ledges
- Drawing a frame
- Particles
- Acts and act_view
- Input: grabbing, dragging, throwing
- What the app can call
- Skins
- Adding an act
- Testing an integration

## The frame loop

```python
pet.step(dt, ledges, cursor, bounds)   # ~60 times a second
```

- `dt` -- seconds since the last step. The core clamps it to 0.05, so a stalled event loop
  never makes the pet tunnel through a ledge.
- `ledges` -- a fresh `list[Ledge]` every frame (positions change as the window scrolls,
  resizes or re-lays out).
- `cursor` -- `(x, y)` of the pointer. When it is outside the window, pass its last known
  position or one far away; don't pass `None`.
- `bounds` -- `Bounds(left, top, right, bottom)`: the space the pet may occupy.

Then read `pet.x, pet.y` (its feet) and draw.

## Coordinates

One space for everything: y grows downwards, units are logical pixels. In-window adapters
use the window's own coordinates (0,0 at its top-left) -- that is what makes them work on
Wayland. `pet.y` is the line its feet stand on, so a pet standing on a ledge has
`pet.y == ledge.y`.

## Ledges

```python
Ledge(left, right, y, key)
```

The top edge of something: from `left` to `right` at height `y`. Always include a floor --
`Ledge(0, width, height)` for a window -- or the pet falls out, gets caught by `bounds`
and is dropped back in from the top.

`key` identifies the surface across frames and **is compared by identity** (`is` / `===`).
Pass the widget object itself. When a keyed ledge moves between frames, the pet standing on
it moves with it; a key that is a fresh string or tuple every frame looks like a new ledge
each time and the pet falls off. Keyless ledges (`key=None`) are matched by `y` and `left`,
which is right for fixed things like the floor.

Good perches are things with a visible top edge at least ~56 px wide: buttons, fields,
combo boxes, lists and tables, progress bars, group boxes and cards, tab bars, toolbars.
Skip the pet's own widgets, invisible or zero-size widgets, and anything outside the window.

## Drawing a frame

```python
rows = frame(pet)            # e.g. 9 strings of 16 letters for Clawd, 14 x 14 for the cat
palette = pet.skin.palette   # letter -> "#RRGGBB"; letters not in it are transparent
```

Each letter is one `PIXEL` (4 px) square. Squash and stretch, plus a slow breath while it
stands or sleeps:

```
squash = pet.squash + pet.breathing
across = PIXEL * (1 + squash)
down   = PIXEL * (1 - squash)
left   = pet.x - len(rows[0]) * across / 2
top    = pet.y - len(rows) * down
cell (r, c) -> rectangle(left + c * across, top + r * down, across, down)
```

Draw them as filled rectangles with no antialiasing (add half a pixel to width and height
to avoid hairline gaps when `squash` is not zero). `pet.skin.width`/`height` give the
body's unsquashed size -- use them for the hit area.

If `pet.skin.outline` is true and the app is dark, draw a one-cell `#8C95A8` border around
the filled cells first (the cat is almost black and vanishes on a dark theme otherwise).

## Particles

`pet.particles` -- short-lived marks, each with `kind, x, y, life` (seconds left). `x, y`
are relative to the pet's feet. Fade with `alpha = clamp(life * 2, 0, 1)`.

| kind | draw |
| --- | --- |
| `tear` | 3 x 5 px `#5DB8F0` |
| `dust` | 3 x 3 px sawdust `#D9B07A` |
| `puff` | grey `#7D8691` square, `4 + (0.6 - life) * 10` px wide |
| `heart`, `vein` | 5-wide pixel shapes at 3 px per cell (see `_SHAPES` in qt.py) |
| `ring` | a growing blue ellipse (1PPS act only) |
| anything else | the kind itself as bold text, e.g. `!`, `?`, `z`, `hi`, `FIX` |

An adapter that cannot draw text (Tk tiles) may skip the text kinds; the pet still works.

## Acts and act_view

`act_view(pet)` returns what the current act needs drawn around the pet: `props` (small
pixel sprites from `PROPS`), `labels` (text with a tone), `shift` (rows offset sideways),
`ghost` (a translucent copy offset by x), `noise`, `wave`, `orbit`, `bars`, `dots`
(thinking), `fly` (the fly of the "fly" act: x, y and whether its wings are up), `stars`
(the phase of three stars going round its head while dizzy) and `speech` (a line to show in
a bubble over its head -- wrap it to the pet's 120 px box, and lay it out right to left
when it is Hebrew or Arabic). All positions are relative to the feet. It is empty for a pet
with no act. Every adapter draws the props; the Tk one shows `speech` in a label.

### Everyday acts

Besides the opt-in packs, the pet does things on its own (`EVERYDAY_ACTS`): washes a paw
(`groom`), `stretch`es, `chase`s its tail (and ends dizzy), swats a `fly`, `sneeze`s,
`sit`s, and picks up a plank and `saw`s it in two. A skin drawn from behind (`Skin.back`,
the cat's) also has `oops`: it turns round with a pink thong in full view, then turns back
blushing. Stroke it with the cursor and it purrs (`pet.purring`); throw it hard and it lands
seeing stars (`pet.dizzy`).

## Input: grabbing, dragging, throwing

On a press inside the body's rectangle (`pet.x - width/2 .. pet.x + width/2`,
`pet.y - height .. pet.y`):

```python
grip = (pet.x - press_x, pet.y - press_y); pet.grab()
# on every move while pressed:
pet.drag_to(x + grip[0], y + grip[1])       # keep the last ~0.1 s of (time, x, y) samples
# on release:
pet.throw(vx, vy)                            # velocity from the first and last sample
```

Every press on the body also calls `pet.poke()`: five within two seconds and it is fed up --
cross, saying `pet.skin.fed_up` in a bubble ("Hey! Stop poking me!" for Clawd; the cat says
it has no key to the toilets here). A double-click is `pet.cheer()`, unless that left it
fed up. In the Qt adapter a right-click on the pet opens the skin menu. Every press outside the body must reach the app: the
adapters get that from an input region (GTK), a hit box only as big as the body (web), an
application event filter that only takes presses on the body (Qt), or by being made of
opaque tiles only where the pet is (Tk).

## What the app can call

| Call | Effect |
| --- | --- |
| `pet.feel("happy" / "sad" / "angry", seconds)` | bouncing hearts, slow and tearful, or fuming and hopping |
| `pet.cheer()` | a heart and a jump |
| `pet.startle()` | "!" and a hop |
| `pet.watch(x, y)` | looks at a point for 1.5 s (typing in a field) |
| `pet.poke()` | a click on it -- see above |
| `pet.thinking = True/False` | three dots above its head |
| `pet.perform(name)` | an act or reaction (`"wave"`, `"look"`, `"yawn"`, or an enabled act) |
| `pet.skin = skin_named("cat")` | changes skin |
| `pet.acts = dict(ACT_PACKS["gnss"])` | turns the GNSS skits on |

## Skins

```python
Skin(key, name, body, arms_up, sad_body, legs, face, palette, angry, tears, outline=False, stalks=False,
     groom=None, tail=None, back=None, fed_up="Hey! Stop poking me!")
```

`body`, `arms_up`, `sad_body` are equal-sized row tuples; `legs` maps `stand`, `walk_a`,
`walk_b`, `tuck`, `dangle` to two extra rows; `face(rows, pet)` edits the rows in place for
eyes, blinking and expressions; `angry` swaps palette letters when furious; `tears` are
(row, column) spots tears fall from. Optional: `groom` (the body with a paw at its mouth),
`tail` (the tail tip's cell down and up, for the swish), `back` (the body from behind --
without one there is no "oops") and `fed_up` (what it says when poked too often). Register
a new skin in `SKINS`. In JavaScript the fields are `armsUp`, `sadBody` and `fedUp`.

## Adding an act

Say a music app wants a "beat" skit:

1. Add it to an act table the app enables: `pet.acts = {"beat": 4.0}` (seconds).
2. In `Pet._acting`, give it behaviour while `self.act == "beat"` (bounce on each beat by
   setting `self.squash`, add particles).
3. In `act_view`, return what it needs drawn (`view.labels.append(("♪", 0, top - 30, "dim"))`).

A new act only changes what happens while it runs. To be sure an edit left everything else
alone, check the vendored copy against the reference trace -- it must still pass when the
new act is not enabled:

```bash
python <skill>/scripts/make_trace.py --check --core path/to/folder/holding/desktop_pet
```

## Testing an integration

The skill's repository tests every adapter the same way; copy the shape into the app's
suite when it can run its UI headless:

1. Build a window with a button at a known place, start the pet with
   `pet.pet.rng = Mulberry32(4)` (so the run is repeatable) and pump the event loop until
   `pet.pet.ledge` is set -- assert `ledge.key is button` and `pet.pet.y == button_top`.
2. Click a second button away from the pet -- assert its handler ran.
3. Press on the pet's body -- assert `pet.pet.mood is Mood.HELD` and that the widget under
   it did not get the click.
