# doormat

Native windows, input and an event loop for Python, through `ctypes` alone.
X11, Win32 and Cocoa. No toolkit, no extension module, no dependencies.

Not a binding to a GUI library — there is no GUI library underneath. `x11.py`
talks to `libX11` the way an Xlib program does, `win32.py` registers a window
class and runs a message pump, `cocoa.py` builds an `NSWindow` and a
subclassed `NSView` through the Objective-C runtime. `dependencies = []` in
`pyproject.toml`, and the intent is to keep it that way.

Written for [FeetBrowser](https://github.com/JuiceyDew/FeetBrowser), which
owns its whole stack, and split out because none of it knows a browser
exists.

## It does not draw

That is the design. A window is handed a *canvas* — any object at all — and
asks it for a frame:

```
canvas.dirty            true when what is on screen is stale
canvas.render()         a surface
canvas.cursor           a cursor name, or absent

surface.pixels          packed RGB, three bytes per pixel
surface.width           in device pixels
surface.height
surface.stride          bytes per row
```

A canvas the window keeps hears about three more — `device_size()`,
`resize()` and `set_scale()` — when the window changes underneath it. That is
the whole contract: no base class to inherit and nothing to import. Whatever
produced those bytes — a rasteriser, a decoder, a `bytearray` you filled in
a loop — is the caller's business. `tests/support.py` is a complete
implementation in 60 lines, and the window suites present *that* rather than
a real renderer: a test that draws with the genuine article proves the pair
works together, but a test that draws with this proves the window asks for
nothing it did not say it would.

## Use

```
pip install git+https://github.com/67plays/doormat
```

```python
import doormat

win = doormat.new_window(width=800, height=600, title="hello")
win.canvas = MyCanvas(800, 600)
win.bind("<Button-1>", lambda e: print("click at", e.x, e.y))
win.bind("<Control-q>", lambda e: win.quit())
win.mainloop()
```

`new_window()` opens a real window where the platform has one and returns a
headless root where it does not — same API, nowhere to put the pixels, which
is what makes a test suite or an offscreen render possible with nothing
installed. Nothing gets a native window by accident: `window.Tk()` is always
the headless one.

`$DOORMAT_DISPLAY` picks a backend by name — `x11`, `win32`, `cocoa`, or
`none` to stay headless where a window was possible. Naming one that cannot
run here raises, rather than silently handing back a headless root, because
that is a failure you otherwise discover from a blank screenshot. An
application with its own variable passes it in instead:
`doormat.new_window(display=os.environ.get("MYAPP_DISPLAY", ""))`.

## The API

Tk's shape, because that is what the browser was already written against and
it is a reasonable shape: `bind`/`unbind` with `<Control-Shift-s>` sequence
names, `after`/`after_idle`/`after_cancel`, `mainloop`/`quit`,
`title`/`geometry`/`minsize`, `clipboard_get`/`clipboard_append`,
`protocol("WM_DELETE_WINDOW", ...)`, `winfo_width`. An event carries `x`,
`y`, `keysym`, `char`, `state`, `delta`, `num`.

Two of Tk's binding rules are reproduced exactly, in `window.key_sequences`,
because everything above depends on them: a binding matches when its
modifiers are a *subset* of those actually held, and only the most specific
match fires.

## Backends

| | |
|---|---|
| `window.py` | the headless base — bindings, timers, the loop |
| `x11.py` | Xlib: `XCreateImage`/`XPutImage`, `XSetWMProtocols`, `_NET_WM_NAME`, `_NET_WM_ICON`, both selections, `Xft.dpi` |
| `win32.py` | `RegisterClassExW`, a `WNDPROC` message pump, `StretchDIBits`, per-monitor v2 DPI |
| `cocoa.py` | `NSWindow` and a runtime-built `NSView` subclass, `NSPasteboard`, `backingScaleFactor` |
| `asmx11.py` | the odd-visual pixel packer, in x86-64 assembly |
| `asm/x11pack.S` | that kernel's source |

Each backend answers `available()` for itself and says *why* when the answer
is no — "DISPLAY is not set" and "this is not Linux" are very different
problems and the difference is the whole of what a user needs to hear.

Clipboard support is not a `clipboard_get` that only works on one of them.
X11's is the real ICCCM dance: claiming both `CLIPBOARD` and `PRIMARY`,
answering `TARGETS` and `UTF8_STRING` conversion requests from other clients,
and reading one back by converting into a property of our own. A mouse
selection claims `PRIMARY` only — a drag over some text is a copy, but not
*the* copy — which is the behaviour every X11 user expects and almost no
cross-platform toolkit gets right.

HiDPI is handled the same way in all three: everything above measures in CSS
pixels, the framebuffer is allocated at the device ratio, drawing multiplies
and input divides back out. `$DOORMAT_SCALE` overrides what the platform
reported, so 2x is testable on whatever machine you have.

## The assembly

An X server whose TrueColor visual is depth 15 or 16 — or whose channel masks
do not fall on byte boundaries — cannot be handed packed RGB. Every pixel has
to be pushed through three 256-entry lookup tables and written back at the
server's own width and endianness, which in Python is a loop per pixel and
the slowest thing in the backend by a distance.

`asm/x11pack.S` is that loop, hand-written in x86-64. No C: it is compiled on
first use straight into a shared object, cached under a hash of its own
source, and loaded with `ctypes`. Where there is no compiler — or the host is
not Linux on x86-64 — the byte-identical Python loop runs instead and nothing
notices but the clock. `asmx11.using_assembly()` says which you got.

## Tests

Real windows, not stubs. The suites open, map, draw into and send genuine
events to dozens of actual windows; a stubbed window cannot catch the typo
that costs you every mouse click. Each suite skips cleanly off its own
platform, so all three run everywhere and the two that cannot do anything say
so.

```
./test.sh
```

`DOORMAT_QUIET=1` — which `test.sh` sets — drops exactly three manners:
centring, raising, and taking the keyboard. The windows are still created and
still tested; they simply stop making the machine unusable for the length of
the run.

## Licence

MIT, same as FeetBrowser.
