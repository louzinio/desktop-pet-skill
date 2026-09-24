# Toolkit recipes

Every adapter answers the same five questions. The ready ones (Qt-Python, Tk, GTK 3, web)
are in `assets/`; for anything else, answer them with the recipe below, write the adapter
around a port of the core (`porting.md`), and keep the pet **inside the app's window**
unless the user explicitly wants it roaming the desktop.

1. **Where does it draw?** A layer over the window's content that the toolkit composites.
2. **How do clicks pass through?** Only the pet's body may take the pointer.
3. **Where are the ledges?** The top edges of the window's visible widgets, in the layer's
   coordinates, keyed by the widget object -- plus a floor at the bottom.
4. **Where is the cursor?** In the same coordinates; last known position when outside.
5. **What ticks it?** A ~16 ms timer or the toolkit's frame clock, passing real elapsed time.

## Contents
- Linux display servers: X11 and Wayland
- Qt in C++ (Widgets) and QML
- GTK 4 (Python, C, Rust, Vala)
- GTK 3 in C / gtkmm
- wxWidgets / wxPython
- Java Swing
- JavaFX
- Electron: the whole desktop
- Flutter
- .NET: WPF, WinForms, Avalonia
- Rust: egui, iced, Slint
- Go: Fyne
- Terminal UIs (curses, Textual, ratatui)

## Linux display servers: X11 and Wayland

On **Wayland** a client cannot place its own top-level windows or read the pointer outside
its windows. An in-window layer needs neither, so it works on both; a desktop-roaming pet
(a small always-on-top window that moves itself) works only on X11 -- and on Windows and
macOS. Under XWayland (an X11 app on a Wayland session) the desktop mode moves only
within XWayland's rules; don't rely on it. When unsure, build the in-window layer.

## Qt in C++ (Widgets) and QML

**Widgets.** Port `core.py` to C++ (it is ~600 lines of plain arithmetic). Mirror
`qt.py`'s `WindowPet`: a `QWidget` child of the main window, sized to it, with
`Qt::WA_TransparentForMouseEvents`, `raise()`d every tick, painting with `QPainter::fillRect`.
Take presses with `qApp->installEventFilter(this)`: in `eventFilter`, return `true` for a
`MouseButtonPress` whose position (mapped to the main window) is inside the body, and for
the moves and release that follow; return `false` for everything else. Ledges: iterate
`window->findChildren<QWidget*>()`, keep visible ones of the perch classes, map with
`mapTo(window, QPoint(0, 0))`, key by the `QWidget*`. Cursor: `window->mapFromGlobal(QCursor::pos())`.
Tick: `QTimer` at 16 ms with `QElapsedTimer` for `dt`.

**QML.** Put a `Canvas` (or a `Repeater` of `Rectangle`s for the pixels) in an `Item`
anchored to fill the window's content with a high `z`. Drive the core from C++ (exposed as
a `QObject`), or use `pet-core.js` in QML's JavaScript engine: drop the `export` keywords,
and if the Qt version's engine lacks newer built-ins (`Object.hasOwn`, `??`), replace them.
Then run the replay check (`porting.md`) in that engine before trusting it. Put a `MouseArea` only the size of the body, moved with
the pet, for grabbing; leave the rest of the layer without a `MouseArea` so clicks reach
the items underneath. Ledges: walk `contentItem.children` recursively, use
`mapToItem(layer, 0, 0)`, key by the item.

## GTK 4 (Python, C, Rust, Vala)

GTK 4 has no input shapes. Use two overlay children in a `Gtk.Overlay` wrapped around the
window's content:

- a `Gtk.DrawingArea` filling the overlay, `set_can_target(False)`, drawing with cairo in
  its draw function -- it never takes the pointer;
- a small hit widget (an empty `Gtk.Box` the size of the body) added with
  `add_overlay`, `halign=START`, `valign=START`, moved each tick with
  `set_margin_start(x)` / `set_margin_top(y)`, carrying a `Gtk.GestureDrag` (grab, drag,
  throw) and a `Gtk.GestureClick` for double-clicks.

Ledges: walk `get_first_child()` / `get_next_sibling()`; `widget.compute_point(overlay,
Graphene.Point())` (4.12+) or `translate_coordinates` for the position; key by the widget.
Cursor: a `Gtk.EventControllerMotion` on the window (`propagation phase CAPTURE` so child
widgets don't hide it). Tick: `widget.add_tick_callback` with the frame clock's time.

## GTK 3 in C / gtkmm

Same structure as `gtk.py`: wrap the window's child in a `GtkOverlay`, add a
`GtkDrawingArea` overlay, draw with cairo, and every tick set the input shape of the
drawing area **and of its parent `GdkWindow`** to the body rectangle
(`gtk_widget_input_shape_combine_region`, `gdk_window_input_shape_combine_region`) --
GtkOverlay puts each overlay child in a window of its own the size of the overlay, and
that wrapper swallows every click unless it is shaped too.

## wxWidgets / wxPython

wx has no portable transparent child window. Two options:

- **In-window, on a canvas the app owns** (a `wx.Panel`/`wxPanel` it already paints, or a
  `wxGLCanvas`): draw the pet at the end of its `EVT_PAINT` handler and handle the mouse
  there; ledges are the app's own drawn items, which the app knows.
- **A shaped top-level frame**: `wx.Frame` with `wx.FRAME_SHAPED | wx.FRAME_NO_TASKBAR |
  wx.STAY_ON_TOP`, `SetShape(region)` each frame from the body's pixels, moved with `Move`.
  Works on X11, Windows and macOS, not on Wayland. Ledges: `GetChildren()` recursively with
  `GetScreenPosition()`.

## Java Swing

Use the root pane's **glass pane**: `frame.setGlassPane(petPane)`, `petPane.setVisible(true)`,
`setOpaque(false)`, paint in `paintComponent`. Override `contains(x, y)` to return true only
inside the body -- Swing then routes every other event to the components underneath, which
is exactly the click-through needed. Ledges: walk `frame.getContentPane()` with
`getComponents()`, `SwingUtilities.convertPoint(c, 0, 0, petPane)`, key by the component.
Tick: `javax.swing.Timer(16, ...)` with `System.nanoTime()` for `dt`. Cursor:
`MouseInfo.getPointerInfo()` converted with `SwingUtilities.convertPointFromScreen`.

## JavaFX

Wrap the scene root in a `StackPane` with a `Pane` layer on top. In the layer, a `Canvas`
with `setMouseTransparent(true)` for drawing and a `Region` the size of the body (moved
with `relocate`) for grabbing; set `setPickOnBounds(false)` on the layer so empty space
passes clicks through. Ledges: walk `Parent.getChildrenUnmodifiable()`,
`node.localToScene` then `layer.sceneToLocal`, key by the node. Tick: `AnimationTimer`.

## Electron: the whole desktop

Inside a window, use `pet-dom.js` in the renderer. For a pet that roams the desktop (not on
Wayland), open a second `BrowserWindow` with `transparent: true, frame: false,
alwaysOnTop: true, skipTaskbar: true, focusable: false`, size it to the pet, load a page
that draws it, and call `win.setIgnoreMouseEvents(true, { forward: true })` except while
the pointer is over the body. The main process moves it with `setPosition` and supplies
ledges from `screen.getAllDisplays()` work areas and the main window's bounds.

## Flutter

Wrap the app's page in a `Stack`; add an `IgnorePointer(child: CustomPaint(...))` that fills
it for drawing, and a `Positioned` `GestureDetector` the size of the body for
grabbing (`onPanStart/Update/End`, velocity from `DragEndDetails`). Ledges: give perch
widgets `GlobalKey`s (or walk the render tree) and read
`RenderBox.localToGlobal(Offset.zero)`; key by the render object. Tick: a `Ticker`.

## .NET: WPF, WinForms, Avalonia

- **WPF**: an `Adorner` on the window's root element, or a top-level `Canvas` in a `Grid`
  over the content, with `IsHitTestVisible=false` on the drawing and a small hit
  `Border` for the body. Ledges: `VisualTreeHelper` walk, `TransformToAncestor`.
- **WinForms**: no real transparency for child controls. Draw on a borderless top-level
  `Form` with `TransparencyKey` and `TopMost`, moved with the pet (Windows only), or paint
  in a control the app already owner-draws.
- **Avalonia**: like WPF -- an overlay `Canvas` with `IsHitTestVisible=false` and a
  body-sized hit control; runs on Linux (X11) as well.

## Rust: egui, iced, Slint

- **egui**: paint the pet in `ctx.layer_painter(LayerId::new(Order::Foreground, ...))` each
  frame and use an `egui::Area` the size of the body with `.interactable(true)` for the
  drag. Ledges come from the `Response::rect` of the widgets the app wants as perches
  (store them while building the UI), keyed by their `Id`. Request repaints every frame.
- **iced**: a `Canvas` program layered on top with `stack!`, returning
  `mouse::Interaction` and capturing events only inside the body.
- **Slint**: a top-level `Rectangle` layer with a `TouchArea` sized to the body; drive the
  core from Rust through properties.

## Go: Fyne

Put the content and a custom `fyne.Widget` layer in `container.NewStack`; the layer draws
pixel `canvas.Rectangle`s and implements `fyne.Draggable` only on a body-sized child.

## Terminal UIs (curses, Textual, ratatui)

Draw with the upper-half-block character `▀`: one terminal cell shows two pixels, the
foreground colour for the top one and the background colour for the bottom one (24-bit
colour where supported). Work in cell coordinates with the core scaled accordingly
(`PIXEL = 1` cell horizontally, half a cell vertically). Ledges are the top borders of
panels and widgets; the cursor is the mouse position if the terminal reports it, otherwise
the text cursor. There is no pick-up in most terminals -- skip grab and throw.
