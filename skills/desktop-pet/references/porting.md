# Porting the core to another language

The behaviour is worth keeping exactly: the timings, the jump arcs, when it pounces, sleeps
or waves are what make the pet feel alive, and they were tuned by hand. So port
`assets/python/desktop_pet/core.py` line by line -- `assets/js/pet-core.js` is an example of
such a port -- and prove it against `assets/reference_trace.json`.

## The trace

```json
{
  "bounds": [0, 0, 1200, 800],
  "ledge_sets": [[[left, right, y, key-or-null], ...], ...],
  "inputs": [{"dt": 0.0167, "cursor": [x, y], "ledges": 0, "events": [["grab"], ["drag_to", 300, 200]]}, ...],
  "scenarios": [
    {"name": "clawd-with-acts", "seed": 1, "skin": "clawd", "acts": "gnss", "states": [...]},
    {"name": "cat-without-acts", "seed": 7, "skin": "cat", "acts": null, "states": [...]}
  ]
}
```

For each scenario: create `Pet(600, 100)` with `Mulberry32(seed)`, the named skin and act
pack; then for every input, apply its events in order (method name and arguments --
`grab`, `drag_to`, `throw`, `feel`, `cheer`, `watch`, `startle`, `perform`), build its
ledge set (the key strings are the keys -- compare them by value, they are the same object
in the original), call `step(dt, ledges, cursor, bounds)`, and compare with `states[i]`:

`x, y, vx, vy, mood, facing, act, emotion, ledge` (`[left, y]` or null), `particles`
(`[kind, x, y]` each), `view` (`[number of props, label texts, ghost, bars, dots]`), and
every tenth step `frame` (the rows). Numbers match within 1e-6 relative.

`scripts/check_js_core.mjs` does exactly this for JavaScript; translate it.

## What has to be identical

- **The random numbers.** Use `Mulberry32` from the core -- a 32-bit generator with a
  handful of integer operations -- and call `random`, `uniform(a, b) = a + (b - a) * r` and
  `choice(seq) = seq[floor(r * len)]` **in the same order** as the original. Every branch
  that draws a number draws it in the same place; a draw moved above an `if` shifts every
  later decision.
- **Distances** use `sqrt(dx*dx + dy*dy)`, not the language's `hypot` (which may differ in
  the last bit and flip a threshold thousands of steps later).
- **Integer truncation** of positive values (`int()` in Python) is `trunc`/`floor`.
- **Order of lists.** Particles are appended and filtered in order; "the lowest landing
  ledge" takes the first of equals; the act table keeps insertion order.
- **Identity.** A ledge is "the same" only if its key is the same object; keyless ledges
  match on `y` and `left`.
- **`dt` clamping** to `[0, 0.05]` happens first in `step`.
- **Text** in labels: `1PPS #<int>` and `+<value to one decimal> ns`.

When the replay fails, the message names the first step and field that differ: go to that
state in the Python original (`make_trace.py` is easy to instrument) and compare the branch
taken. Fix the port, never the trace.

## After it passes

Write the adapter (`toolkits.md`), then keep the replay check in the app's test suite if it
has one, so later edits to the vendored core are caught.
