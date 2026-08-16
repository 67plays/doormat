"""A canvas that is only the protocol, for tests that need something to show.

The windows in this package never import a drawing library. They ask an
object they were handed for a frame, and what they require of it is small
enough to write down:

    canvas.dirty            true when the last frame is stale
    canvas.render()         a surface
    canvas.cursor           a cursor name, or absent

A canvas a window is allowed to keep also hears about the window changing
underneath it, which is three more:

    canvas.device_size()    the framebuffer's size in device pixels
    canvas.resize(w, h, d)  a new size, in CSS pixels and device pixels
    canvas.set_scale(s, d)  a new device-pixel ratio

    surface.pixels          packed RGB, three bytes per pixel
    surface.width           in device pixels
    surface.height          in device pixels
    surface.stride          bytes per row

That is the whole contract, and it is the reason a browser can drive these
windows without them knowing a browser exists. `Surface` and `Canvas` below
are the smallest honest implementation of it, which makes them the better
thing to test a window against: a test that presents a real rasteriser's
output proves the pair works together, but a test that presents *this*
proves the window asks for nothing it did not say it would.

Coordinates are device pixels here, not CSS pixels. Nothing in this package
scales; the caller renders at the size the window asked for.
"""


class Surface:
    """A packed-RGB framebuffer, addressable by rectangle."""

    def __init__(self, width, height, bg=(0, 0, 0)):
        self.width = width
        self.height = height
        self.stride = width * 3
        self.pixels = bytearray(self.stride * height)
        self.fill_rect(0, 0, width, height, bg)

    def fill_rect(self, x0, y0, x1, y1, colour):
        """Fill `[x0, x1) x [y0, y1)` with an ``(r, g, b)`` triple."""
        r, g, b = colour
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.width, x1), min(self.height, y1)
        row = bytes((r, g, b)) * max(0, x1 - x0)
        for y in range(y0, y1):
            start = y * self.stride + x0 * 3
            self.pixels[start:start + len(row)] = row

    def pixel(self, x, y):
        """The ``(r, g, b)`` at `x, y`, for reading a frame back."""
        at = y * self.stride + x * 3
        return tuple(self.pixels[at:at + 3])


class Canvas:
    """The smallest thing a window will accept as a source of frames."""

    def __init__(self, width, height, bg=(0, 0, 0)):
        self.background = bg
        self.surface = Surface(width, height, bg)
        self.dirty = True
        self.cursor = ""
        self.renders = 0

    @property
    def width(self):
        return self.surface.width

    @property
    def height(self):
        return self.surface.height

    def pack(self, **_ignored):
        """Accepted and ignored: the browser's canvas has one, so tests call
        it, and a window has no layout to put anything into."""

    def device_size(self):
        """The framebuffer's size in device pixels.

        A backend compares this against the size the window system says the
        window is, and resizes us when the two have drifted apart.
        """
        return (self.surface.width, self.surface.height)

    def resize(self, width, height, device=None):
        """Take a new size, in CSS pixels.

        `device` is that size in device pixels, which a backend passes when
        the window system told it exactly -- and it is the authority when it
        arrives, because putting a physical size through a fractional scale
        and back does not land where it started. Without one there is
        nothing here that scales, so the two are the same number.
        """
        self.surface = Surface(*(device or (width, height)),
                               bg=self.background)
        self.dirty = True

    def set_scale(self, scale, device=None):
        """Adopt a density the window has just been told about.

        Only the buffer's size matters here, and the platform either knows it
        -- in which case it is `device` -- or is about to say so in the
        resize that follows the scale change. Either way the frame on screen
        was drawn for the old density and has to be drawn again.
        """
        del scale
        if device:
            self.surface = Surface(*device, bg=self.background)
        self.dirty = True

    def fill_rect(self, x0, y0, x1, y1, colour):
        self.surface.fill_rect(x0, y0, x1, y1, colour)
        self.dirty = True

    def render(self, region=None):
        """Hand back the frame. `region` is accepted and ignored -- every
        item is already painted -- which is exactly what the real canvas
        does when it is asked for a partial frame it cannot narrow."""
        del region
        self.renders += 1
        self.dirty = False
        return self.surface


def rgb(text):
    """``"#ff8000"`` as an ``(r, g, b)`` triple.

    The tests were written against a canvas that took CSS colour strings,
    and the assertions read better in hex than in three decimals.
    """
    text = text.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
