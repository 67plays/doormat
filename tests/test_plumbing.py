"""The plumbing behind the windows, which is not platform-specific at all.

The three window suites beside this one open real windows and each runs on
exactly one platform. What is left over is arithmetic and translation
tables: a DIB's row padding, a wheel notch's sign, which Tk keysym a virtual
key code is. Those are plain functions on purpose, and they are checked
here, on every platform the suite runs on -- which is how the Win32 tables
stayed right for the years nobody ran them on Windows.

The backend chooser is here too, for the same reason: picking a backend is
not something any one platform does.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import doormat                                     # noqa: E402


def eq(a, b, msg=""):
    assert a == b, f"{msg}: {a!r} != {b!r}"



def test_dib_stride_rounds_rows_up_to_four_bytes():
    from doormat.win32 import dib_stride
    eq(dib_stride(4, 24), 12, "a multiple of four needs no padding")
    eq(dib_stride(5, 24), 16, "15 bytes of pixels round up to 16")
    eq(dib_stride(999, 24), 3000, "2997 bytes of pixels round up to 3000")
    # The reason this backend presents 32bpp: no row ever needs padding, so
    # the frame is one buffer and the whole class of off-by-one row smears
    # cannot happen.
    for width in range(1, 40):
        eq(dib_stride(width, 32), width * 4,
           f"32bpp width {width} should need no padding")


def test_rgb_becomes_bgr_without_moving_a_pixel():
    from doormat.win32 import bgra_from_rgb
    # Two pixels: pure red, then pure green.
    out = bgra_from_rgb(bytearray([255, 0, 0, 0, 255, 0]), 2, 1)
    eq(bytes(out), b"\x00\x00\xff\x00\x00\xff\x00\x00", "channel order")
    eq(len(out), 2 * 1 * 4, "four bytes per pixel")


def test_the_dib_is_top_down_and_row_order_survives():
    """A DIB is bottom-up by default and we declare a negative height
    instead, so the rows must come out in the order they went in. Getting
    this wrong flips the whole page upside down."""
    from doormat.win32 import bgra_from_rgb
    pixels = bytearray([1, 2, 3, 4, 5, 6,        # row 0
                        7, 8, 9, 10, 11, 12])    # row 1
    out = bgra_from_rgb(pixels, 2, 2)
    eq(bytes(out[0:4]), b"\x03\x02\x01\x00", "first pixel of the first row")
    eq(bytes(out[8:12]), b"\x09\x08\x07\x00", "first pixel of the second row")


def test_a_padded_source_stride_is_compacted():
    from doormat.win32 import bgra_from_rgb
    # Three bytes of pixels per row plus two bytes of slack.
    pixels = bytearray([10, 20, 30, 99, 99,
                        40, 50, 60, 99, 99])
    out = bgra_from_rgb(pixels, 1, 2, stride=5)
    eq(bytes(out), b"\x1e\x14\x0a\x00\x3c\x32\x28\x00", "slack was skipped")


def test_the_bitmap_header_is_the_size_windows_expects():
    """GDI reads biSize to tell a BITMAPINFOHEADER from its successors, so a
    header that is not 40 bytes is rejected outright."""
    import ctypes
    from doormat.win32 import BITMAPINFOHEADER
    eq(ctypes.sizeof(BITMAPINFOHEADER), 40)


def test_packed_coordinates_can_be_negative():
    """A drag that leaves the window on the left or the top reports a
    negative coordinate, packed as an unsigned 16-bit field."""
    from doormat.win32 import lparam_point, signed_word
    eq(signed_word(0xFFFF), -1)
    eq(signed_word(0x8000), -32768)
    eq(signed_word(0x7FFF), 32767)
    eq(lparam_point((300 << 16) | 120), (120, 300))
    eq(lparam_point((0xFFFB << 16) | 0xFFF6), (-10, -5), "off the top-left")


def test_a_wheel_notch_stays_in_the_pixel_range():
    """browser.py treats |delta| < 30 as a pixel count and anything larger as
    line units, so a notch has to stay under 30 or one flick moves the page
    by a screenful."""
    from doormat.win32 import wheel_delta
    eq(wheel_delta(120), 20, "one notch forward")
    eq(wheel_delta(-120), -20, "one notch back")
    eq(wheel_delta(0), 0)
    for raw in (120, -120, 360, -360, 3600, -3600, 7, -7):
        delta = wheel_delta(raw)
        assert abs(delta) < 30, f"{raw} became {delta}, out of the pixel range"
        assert (delta > 0) == (raw > 0), f"{raw} lost its direction"


def test_modifier_bits_are_the_ones_the_browser_reads():
    from doormat.win32 import modifier_state
    from doormat.window import STATE_ALT, STATE_CONTROL, STATE_SHIFT
    eq(modifier_state(False, False, False), 0)
    eq(modifier_state(True, False, False), STATE_SHIFT)
    eq(modifier_state(False, True, False), STATE_CONTROL)
    eq(modifier_state(False, False, True), STATE_ALT)
    # browser.py tests `event.state & 0x4` directly for its shortcuts.
    assert modifier_state(False, True, False) & 0x4


def test_named_virtual_keys_map_to_tk_keysyms():
    from doormat.win32 import keysym_for_vk
    from doormat.window import STATE_CONTROL, STATE_SHIFT
    eq(keysym_for_vk(0x0D, 0), "Return")
    eq(keysym_for_vk(0x26, 0), "Up")
    eq(keysym_for_vk(0x21, 0), "Prior", "PageUp is Tk's Prior")
    eq(keysym_for_vk(0x7B, 0), "F12")
    eq(keysym_for_vk(0x09, 0), "Tab")
    # browser.py binds <Control-ISO_Left_Tab> for previous-tab, which is the
    # keysym X11 and Tk use for a shifted Tab.
    eq(keysym_for_vk(0x09, STATE_SHIFT), "ISO_Left_Tab")
    eq(keysym_for_vk(0x09, STATE_SHIFT | STATE_CONTROL), "ISO_Left_Tab")


def test_a_plain_letter_waits_for_the_character_message():
    """WM_CHAR is the only thing that has been through the user's keyboard
    layout, so an unmodified printable key is left to it."""
    from doormat.win32 import keysym_for_vk
    from doormat.window import STATE_ALT, STATE_CONTROL, STATE_SHIFT
    eq(keysym_for_vk(0x4C, 0), None, "plain L")
    eq(keysym_for_vk(0x4C, STATE_SHIFT), None, "shifted L")
    # Under Control the character message carries a control code (Ctrl-L is
    # 0x0C, not "l"), so the letter has to come from the virtual key.
    eq(keysym_for_vk(0x4C, STATE_CONTROL), "l", "Ctrl-L reaches <Control-l>")
    eq(keysym_for_vk(0x54, STATE_CONTROL), "t")
    eq(keysym_for_vk(0x53, STATE_CONTROL | STATE_SHIFT), "S",
       "Tk names a shifted letter by its shifted character")
    eq(keysym_for_vk(0x31, STATE_CONTROL), "1", "digits are not cased")
    eq(keysym_for_vk(0x25, STATE_ALT), "Left", "Alt-Left is still a named key")
    eq(keysym_for_vk(0xBA, STATE_CONTROL), None, "no guess at an OEM key")


def test_character_messages_become_keysyms():
    from doormat.win32 import keysym_for_char
    from doormat.window import STATE_CONTROL
    eq(keysym_for_char("z", 0), ("z", "z"))
    eq(keysym_for_char("é", 0), ("é", "é"), "the layout's own character")
    eq(keysym_for_char(" ", 0), ("space", " "), "Tk calls a space 'space'")
    eq(keysym_for_char("", 0), None, "half a surrogate pair carries nothing")
    # Return, Tab, Escape and Backspace each arrive twice: once as a named
    # virtual key and once as a control code. Only the first is the event.
    eq(keysym_for_char("\r", 0), None)
    eq(keysym_for_char("\x08", 0), None)
    eq(keysym_for_char("\x0c", STATE_CONTROL), None,
       "Ctrl-L was already delivered from the virtual key")


def test_key_sequences_are_offered_most_specific_first():
    """Tk fires exactly one binding, the most specific that matches, and a
    binding matches when its modifiers are a subset of those held."""
    from doormat.window import STATE_CONTROL, STATE_SHIFT, key_sequences
    names = key_sequences("l", STATE_CONTROL)
    eq(names[0], "<Control-l>")
    eq(names[-1], "<Key>", "the generic binding is always the last resort")
    assert "<l>" in names
    names = key_sequences("Up", 0)
    eq(names, ["<Up>", "<Key>"], "an unmodified named key")
    # browser.py binds <Control-Shift-s> for view-source and <Control-s> for
    # nothing, so the shifted spelling has to be offered and has to win.
    names = key_sequences("S", STATE_CONTROL | STATE_SHIFT)
    assert "<Control-Shift-s>" in names, names
    assert names.index("<Control-Shift-s>") < names.index("<Control-s>"), names
    # A subset match is what lets <Control-ISO_Left_Tab> catch Ctrl-Shift-Tab.
    names = key_sequences("ISO_Left_Tab", STATE_CONTROL | STATE_SHIFT)
    assert "<Control-ISO_Left_Tab>" in names, names


def test_win32_dpi_becomes_a_scale_factor():
    """Windows offers fractional scales, so 125% has to come out as 1.25 and
    not as 1 -- and a failed query, which comes back as zero, has to come out
    as 1.0 rather than dividing by nothing."""
    from doormat.win32 import scale_for_dpi
    eq(scale_for_dpi(96), 1.0, "96 DPI is 100%")
    eq(scale_for_dpi(120), 1.25, "125%")
    eq(scale_for_dpi(192), 2.0, "200%")
    eq(scale_for_dpi(0), 1.0, "a failed query is not a scale of zero")
    eq(scale_for_dpi(None), 1.0)


def test_xft_dpi_is_read_out_of_the_resource_database():
    """X has no request for "how dense is this display", so the scale comes
    from the setting the desktop environment writes into the root window and
    every other toolkit reads. Nothing else in the database is an answer."""
    from doormat.x11 import xft_dpi
    eq(xft_dpi("Xcursor.size:\t24\nXft.dpi:\t144\nXft.hinting:\t1\n"), 144.0)
    eq(xft_dpi("Xft.dpi: 96.5"), 96.5, "no tab, no newline, not whole")
    # A database that says nothing about DPI, which is every bare X server
    # and every CI runner, has to be no answer rather than a wrong one.
    eq(xft_dpi(""), None)
    eq(xft_dpi(None), None)
    eq(xft_dpi("Xft.dpi:\tenormous\n"), None)
    eq(xft_dpi("Xft.dpi:\t0\n"), None, "zero would be a division by nothing")
    # Matched on the whole name: another program's dpi setting is not ours.
    eq(xft_dpi("Emacs.Xft.dpi:\t192\n"), None)


def test_win32_module_is_importable_off_windows():
    """The backend chooser, pyflakes and this file all import it, so it has
    to load on a machine with no windll at all."""
    from doormat import win32
    if sys.platform != "win32":
        eq(win32.available(), False, "no Win32 window off Windows")
        try:
            win32.Win32Tk()
        except win32.Win32Unavailable:
            pass
        else:
            assert False, "a window opened on a platform with no Win32"

def test_a_backend_can_be_asked_for_by_name():
    """`none` is headless anywhere, a name that cannot run here raises, and
    nothing named at all is whatever the platform offers.

    The raise is the point. Asking for a backend and silently getting a
    headless root is the kind of thing you discover much later, from an empty
    screenshot, with nothing in the log that says why.
    """
    eq(doormat.platform_root("none"), None, "'none' stays headless everywhere")

    root = doormat.platform_root("")
    if sys.platform == "darwin":
        eq(root.__name__, "CocoaTk")
    elif sys.platform == "win32":
        eq(root.__name__, "Win32Tk")
    elif root is not None:
        # x11.py answers here too, and whether it can is a property of the
        # machine rather than of the platform: a desktop with a server
        # running gets X11Tk and headless CI gets None. Both are right, so
        # the only wrong answer is some *other* backend.
        eq(root.__name__, "X11Tk")

    for name in ("win32", "windows"):
        if sys.platform == "win32":
            eq(doormat.platform_root(name).__name__, "Win32Tk")
        else:
            try:
                doormat.platform_root(name)
            except RuntimeError as e:
                assert "Win32" in str(e), f"unhelpful message: {e}"
            else:
                assert False, f"display={name!r} should raise here"

    if sys.platform == "darwin":
        eq(doormat.platform_root("cocoa").__name__, "CocoaTk")
    else:
        try:
            doormat.platform_root("cocoa")
        except RuntimeError as e:
            assert "Cocoa" in str(e), f"unhelpful message: {e}"
        else:
            assert False, "display='cocoa' should raise here"


def test_the_environment_is_the_default_and_not_the_authority():
    """$DOORMAT_DISPLAY is consulted when the caller said nothing, and read
    when it is used rather than when the module was imported.

    The distinction between "said nothing" and "said no preference" is the
    reason the parameter defaults to None and not to "": an application with
    its own variable passes what it read straight through, and an unset
    variable of its own must not fall back to ours.
    """
    saved = os.environ.get("DOORMAT_DISPLAY")
    try:
        os.environ["DOORMAT_DISPLAY"] = "none"
        eq(doormat.platform_root(), None, "the variable was not read")
        eq(doormat.has_display(), False)
        # The argument beats the variable. Named here is a backend that
        # cannot run on this machine, so an implementation that consulted the
        # environment anyway would raise instead of answering.
        os.environ["DOORMAT_DISPLAY"] = \
            "cocoa" if sys.platform != "darwin" else "win32"
        eq(doormat.platform_root("none"), None,
           "the environment overrode an explicit argument")

        os.environ["DOORMAT_DISPLAY"] = "  NONE  "
        eq(doormat.platform_root(), None, "whitespace and case are not names")
    finally:
        if saved is None:
            os.environ.pop("DOORMAT_DISPLAY", None)
        else:
            os.environ["DOORMAT_DISPLAY"] = saved


def test_a_headless_root_is_what_you_get_when_there_is_no_window():
    """new_window() never fails for want of a display. It hands back the
    headless root, which runs everything except the pixels -- and that is
    what makes an offscreen render or a test possible with nothing
    installed."""
    win = doormat.new_window(display="none", width=321, height=123)
    try:
        eq(type(win).__name__, "Tk")
        eq((win.winfo_width(), win.winfo_height()), (321, 123))
        seen = []
        win.bind("<Key>", lambda e: seen.append(e.keysym))
        win.dispatch("<Key>", doormat.window.Event(keysym="a", char="a"))
        eq(seen, ["a"], "the headless root still routes events")
    finally:
        win.destroy()


def test_a_popup_is_the_same_kind_of_window_as_its_master():
    """Toplevel takes its class off the master, so a popup opened from a real
    window is real and one opened from a headless root stays headless. A
    library that always made a native popup would open a window in the middle
    of a test suite that asked for none."""
    win = doormat.new_window(display="none")
    try:
        popup = doormat.Toplevel(win)
        eq(type(popup).__name__, "Toplevel")
        popup.destroy()
    finally:
        win.destroy()


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("  ok ", name)
    total = sum(1 for n in globals() if n.startswith("test_"))
    print()
    print("ALL %d PLUMBING TESTS PASSED" % total)


if __name__ == "__main__":
    main()
