#!/usr/bin/env python3
"""
Test script to verify if changing _NET_WM_WINDOW_OPACITY allows for a
transparent overlay that STILL changes the cursor.
"""

import time
import sys
import struct
from Xlib import display as xdisplay, X, Xatom

# Standard cursor shapes
XC_PIRATE = 88


def main():
    try:
        d = xdisplay.Display()
    except Exception as e:
        print(f"Failed to connect to display: {e}")
        sys.exit(1)

    screen = d.screen()
    root = screen.root
    width = screen.width_in_pixels
    height = screen.height_in_pixels

    print("=" * 60)
    print("TEST: InputOutput Overlay with Opacity Atom")
    print("=" * 60)

    # Create Pirate Cursor
    cursor_font = d.open_font("cursor")
    cursor = cursor_font.create_glyph_cursor(
        cursor_font, XC_PIRATE, XC_PIRATE + 1, (0, 0, 0), (65535, 65535, 65535)
    )
    cursor_font.close()

    print("\n[1/4] Creating Standard Black Overlay...")
    window = root.create_window(
        0,
        0,
        width,
        height,
        0,
        screen.root_depth,
        X.InputOutput,
        X.CopyFromParent,
        background_pixel=0,  # Black
        override_redirect=True,
        cursor=cursor,
        event_mask=0,
    )

    # Map it first
    window.map()
    window.configure(stack_mode=X.Above)
    d.sync()

    print("      Window mapped (should be BLACK with PIRATE cursor).")
    time.sleep(2)

    # Helper to set opacity
    def set_opacity(win, opacity_float):
        # Opacity is 0 to 0xFFFFFFFF
        val = int(opacity_float * 0xFFFFFFFF)
        atom = d.get_atom("_NET_WM_WINDOW_OPACITY")
        # Data is 32-bit unsigned int
        data = struct.pack("I", val)
        win.change_property(atom, Xatom.CARDINAL, 32, [val])
        d.sync()

    print("\n[2/4] Setting Opacity to 50%...")
    set_opacity(window, 0.5)
    print("      >>> Is screen 50% dark?")
    print("      >>> Is cursor still PIRATE? (y/n)")
    time.sleep(3)

    print("\n[3/4] Setting Opacity to 1% (Almost invisible)...")
    set_opacity(window, 0.01)
    print("      >>> Is screen visible?")
    print("      >>> Is cursor still PIRATE? (y/n)")
    time.sleep(3)

    print("\n[4/4] Setting Opacity to 0% (Fully invisible)...")
    set_opacity(window, 0.0)
    print("      >>> Is screen visible?")
    print("      >>> Is cursor still PIRATE? (y/n)")
    time.sleep(3)

    print("\nCleaning up...")
    window.destroy()
    d.sync()
    print("Done.")


if __name__ == "__main__":
    main()
