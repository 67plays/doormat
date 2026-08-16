"""Photograph a real X11 window and write it to a PNG.

Every other test in this package proves a piece: that an XImage is built with
the right stride, that the visual's masks were read correctly, that
XPutImage was called. This proves the whole path at once, and from the far
end -- it draws into a canvas, presents it, and then asks the *server* what
is actually on that window. Nothing between the framebuffer and the screen
can be wrong and still produce the right picture.

The picture is checked, not just written. Red, green and blue swatches have
to come back present, big enough to be the swatches, and in the order they
were drawn: a visual's channel masks and the server's byte order are exactly
what a wrong answer permutes, and a permutation is invisible in a file size.

Meant for CI under `xvfb-run`, at more than one depth, where the PNG is also
uploaded so a human can look at it afterwards.

    python tests/x11_shot.py [out.png]
"""
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from doormat import x11                            # noqa: E402
from tests import support                          # noqa: E402
from tests import test_x11 as helpers              # noqa: E402

# Left to right, because the order is the assertion. The header band across
# the top is a fourth colour that has to survive as a large flat area, which
# is what catches a stride that is wrong by a byte -- a shear is obvious in
# a block and invisible in a swatch.
HEADER = (0x2F, 0x6F, 0xB0)
SWATCHES = ((0xD9, 0x2B, 0x2B), (0x2B, 0xD9, 0x4F), (0x2B, 0x6B, 0xD9))
BACKGROUND = (0xF4, 0xF6, 0xF8)


def paint(canvas):
    """Draw the test card: a header band and three swatches in a row."""
    width, height = canvas.width, canvas.height
    canvas.fill_rect(0, 0, width, height, BACKGROUND)
    canvas.fill_rect(0, 0, width, 120, HEADER)
    for index, colour in enumerate(SWATCHES):
        left = 60 + index * 140
        canvas.fill_rect(left, 220, left + 100, 320, colour)
        # A black border on each, so a swatch that bled into its neighbour
        # shows up as a missing edge rather than as a slightly larger count.
        canvas.fill_rect(left, 220, left + 100, 224, (0, 0, 0))
        canvas.fill_rect(left, 316, left + 100, 320, (0, 0, 0))


def capture(window):
    """The window's pixels, straight off the X server, as ``(w, h, rgb)``.

    Decoded through the visual's masks rather than through the backend's own
    byte offsets. That is deliberate: reusing the backend's arithmetic would
    only prove it agrees with itself, and this has to be able to disagree.
    """
    raw, line = helpers.grab(window)
    fmt = x11._state["format"]
    size = fmt.bits_per_pixel // 8
    order = "little" if fmt.byte_order == x11.LSB_FIRST else "big"
    masks = (fmt.red_mask, fmt.green_mask, fmt.blue_mask)
    width, height = window.width, window.height
    rgb = bytearray(width * height * 3)
    dst = 0
    for y in range(height):
        at = y * line
        for _ in range(width):
            value = int.from_bytes(raw[at:at + size], order)
            for channel, mask in enumerate(masks):
                rgb[dst + channel] = helpers._channel(value, mask)
            at += size
            dst += 3
    return width, height, rgb


def write_png(path, width, height, rgb):
    """A truecolour PNG, with `zlib` doing the only hard part.

    Written out here rather than reached for, because this package decodes
    and encodes no images and is not about to acquire a dependency to hand a
    human something to look at. Filter type 0 on every row: the artifact is
    read once and never served.
    """
    stride = width * 3
    raw = b"".join(b"\x00" + bytes(rgb[y * stride:(y + 1) * stride])
                   for y in range(height))

    def chunk(kind, payload):
        body = kind + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", header))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        fh.write(chunk(b"IEND", b""))


def check(width, height, rgb):
    """Say what is wrong with the photograph, or None if it is right.

    Colours are matched within a tolerance rather than exactly, because a
    5-6-5 visual has no way to store the ones that were drawn: #d92b2b comes
    back as #de282b at depth 16 and there is nothing wrong with that. The
    slack is far smaller than the distance between any two of these four, so
    a genuinely permuted channel still cannot pass.
    """
    tolerance = 12
    wanted = SWATCHES + (HEADER,)
    counts = {colour: 0 for colour in wanted}
    sum_x = dict(counts)
    for y in range(height):
        row = y * width * 3
        for x in range(width):
            at = row + x * 3
            for colour in wanted:
                if all(abs(rgb[at + c] - colour[c]) <= tolerance
                       for c in range(3)):
                    counts[colour] += 1
                    sum_x[colour] += x
                    break
    if counts[HEADER] < 5000:
        return "the header band is missing (%d px of #2f6fb0)" % counts[HEADER]
    for colour in SWATCHES:
        if counts[colour] < 2000:
            return ("the #%02x%02x%02x swatch is missing (%d px)"
                    % (colour + (counts[colour],)))
    middles = [sum_x[colour] / counts[colour] for colour in SWATCHES]
    if not middles[0] < middles[1] < middles[2]:
        return ("red, green and blue came out at x=%s, which is not the "
                "order they were drawn in" % [round(m) for m in middles])
    return None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "x11-window.png"
    if not x11.available():
        sys.exit("no X11 display: %s" % (x11.unavailable_reason() or "?"))

    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)

    # An odd width on purpose: a scanline-padding mistake is invisible at a
    # round 1000 pixels and shears the whole picture at 1003.
    window = x11.X11Tk(width=1003, height=701, title="doormat on X11")
    if not helpers.wait_ready(window):
        sys.exit("the window never reached the screen")
    window.canvas = support.Canvas(*window.to_device(window.width,
                                                     window.height))
    paint(window.canvas)
    window.present()
    helpers.pump(window, 5)

    width, height, rgb = capture(window)
    write_png(path, width, height, rgb)
    window.destroy()

    size = os.path.getsize(path)
    print("wrote %s (%dx%d, %d bytes)" % (path, width, height, size))
    problem = check(width, height, rgb)
    if problem:
        sys.exit("the window came out wrong: %s" % problem)
    print("red, green and blue arrived in order; the header band is there")


if __name__ == "__main__":
    main()
