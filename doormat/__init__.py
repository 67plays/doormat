"""Where a window comes from.

A window here is a real one: an X11, Win32 or Cocoa window driven straight
through ``ctypes``, with its own event loop, its own input translation and
its own idea of what a frame is. No toolkit sits underneath, and nothing in
this package draws -- it asks the object you hand it for a surface of packed
RGB and puts that on the screen. `tests/support.py` writes the whole of that
contract down.

`window.Tk` is always the headless root: the same API with nowhere to put
the pixels, which is what a test suite and an offscreen render want. Opening
a window on a screen is a separate, explicit act -- ``new_window()``.
Nothing gets a native window by accident.

What genuinely varies is where the pixels go, and one name selects it:

    cocoa     the AppKit window, via ctypes (macOS)
    win32     the USER32/GDI window, via ctypes (Windows)
    x11       the Xlib window, via ctypes
    none      stay headless even where a window is possible

Empty -- the default -- means "use whatever this platform offers". Naming a
backend that cannot run here is an error rather than a silent fallback,
because asking for one and quietly getting a headless root is how you end up
with a blank screenshot and no idea why.

That name is an argument, defaulting to ``$DOORMAT_DISPLAY``, and it is read
when it is used rather than when this module is imported. An application
with its own variable passes it through:

    doormat.new_window(display=os.environ.get("MYAPP_DISPLAY", ""))
"""
import importlib
import os

from . import window

#: The environment variable consulted when no display is passed.
DISPLAY_VAR = "DOORMAT_DISPLAY"

# The native window backends, tried in order when nothing was asked for by
# name: (module, label, the names that select it, the root class). Each one
# answers `available()` for itself, so a backend that cannot run here simply
# says so and the next is tried. Cocoa comes first because on the one system
# that has both, XQuartz is the deliberate choice and Cocoa is the default.
# Win32 sits between them only because no system offers it alongside either.
NATIVE_BACKENDS = (
    ("cocoa", "Cocoa", ("cocoa", "macos", "darwin"), "CocoaTk"),
    ("win32", "Win32", ("win32", "windows"), "Win32Tk"),
    ("x11", "X11", ("x11", "linux", "xorg"), "X11Tk"),
)


def _requested(display):
    """The backend name in force: the argument, or the environment.

    None means "nobody said", which is the case that falls back to the
    variable. An empty string is a caller saying "no preference" out loud,
    and that is not the same thing -- it beats the environment.
    """
    if display is None:
        display = os.environ.get(DISPLAY_VAR, "")
    return display.strip().lower()


def Toplevel(master=None, **kwargs):
    """A secondary window of the same kind as its master."""
    factory = getattr(master, "toplevel_class", None)
    if factory is not None:
        return factory(master, **kwargs)
    return window.Toplevel(master, **kwargs)


def platform_root(display=None):
    """The native root-window class for this platform, or None.

    Returns the class rather than an instance so callers can still decide not
    to open anything -- and so the import only happens when it is wanted.
    """
    del _PROBLEMS[:]
    display = _requested(display)
    if display == "none":
        return None
    for module, label, names, root in NATIVE_BACKENDS:
        asked = display in names
        if display and not asked:
            continue
        try:
            backend_module = importlib.import_module("." + module, __package__)
        except ImportError as exc:
            # Asking for a backend by name and silently getting a headless
            # root is the kind of thing you discover from an empty screenshot.
            if asked:
                raise RuntimeError("no %s window available here: %s"
                                   % (label, exc)) from exc
            continue
        if backend_module.available():
            return getattr(backend_module, root)
        # Backends say why they cannot run -- "DISPLAY is not set" is a very
        # different problem from "this is not Linux", and the difference is
        # the whole of what a user needs to hear.
        reason = backend_module.unavailable_reason()
        if reason:
            _PROBLEMS.append("%s: %s" % (label, reason))
        if asked:
            raise RuntimeError("no %s window available here: %s"
                               % (label, reason or "unsupported platform"))
    return None


# Why the last platform_root() found nothing, for callers that want to say so.
_PROBLEMS = []


def display_problem():
    """A one-line explanation of why there is no window, or "".

    Only the reasons worth repeating survive: a backend that is simply for
    another operating system says nothing, because "Cocoa needs macOS" is
    noise on a Linux box that is missing its X server.
    """
    return "; ".join(_PROBLEMS)


def new_window(display=None, **kwargs):
    """A window on the screen if this platform has one, else a headless root.

    The fallback is not a failure mode: a headless root runs an application
    faithfully, which is what tests and offscreen rendering rely on. It just
    has nowhere to put the pixels.

    The remaining keywords go to the window: `width` and `height` in CSS
    pixels, `title`, and `icon` as a ``(width, height, rgba)`` triple. This
    package decodes no images, so the pixels come from the caller.
    """
    root = platform_root(display)
    if root is not None:
        return root(**kwargs)
    return window.Tk(**kwargs)


def has_display(display=None):
    """True when new_window() would open something visible."""
    return platform_root(display) is not None
