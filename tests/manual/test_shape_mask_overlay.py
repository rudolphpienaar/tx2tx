#!/usr/bin/env python3
"""
Test script to verify if the X Shape Extension can be used to make
the window input-active but visually transparent (or partially so).

Corrected for python-xlib Shape constants.
"""

import time
import sys
from Xlib import display as xdisplay, X
from Xlib.ext import shape

# Standard cursor shapes
XC_PIRATE = 88


def main():
    try:
        d = xdisplay.Display()
    except Exception as e:
        print(f"Failed to connect to display: {e}")
        sys.exit(1)

    if not d.has_extension("SHAPE"):
        print("Error: SHAPE extension not available.")
        sys.exit(1)

    screen = d.screen()
    root = screen.root
    width = screen.width_in_pixels
    height = screen.height_in_pixels

    print("=" * 60)
    print("TEST: InputOutput Overlay with Shape Mask (Corrected)")
    print("=" * 60)

    # Create Pirate Cursor
    cursor_font = d.open_font("cursor")
    cursor = cursor_font.create_glyph_cursor(
        cursor_font, XC_PIRATE, XC_PIRATE + 1, (0, 0, 0), (65535, 65535, 65535)
    )
    cursor_font.close()

    print("\n[1/3] Creating Standard Black Overlay...")
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
    window.map()
    window.configure(stack_mode=X.Above)
    d.sync()
    time.sleep(1)

    print("\n[2/3] Applying Empty Shape Mask (Making it invisible)...")

    # Create an empty bitmap (depth 1)
    pm = window.create_pixmap(width, height, 1)
    gc = pm.create_gc(foreground=0, background=0)
    pm.fill_rectangle(gc, 0, 0, width, height)  # Clear all to 0

    # Set the window shape to this empty bitmap
    # python-xlib uses SO.Set and SK.Bounding usually
    try:
        # Try SK.Bounding and SO.Set first (standard in older python-xlib)
        # or ShapeBounding and ShapeSet
        SK_Bounding = getattr(shape, "SK_Bounding", 0)
        SO_Set = getattr(shape, "SO_Set", 0)

        # If SK_Bounding is 0, let's look for alternative names
        if not hasattr(shape, "SK_Bounding"):
            SK_Bounding = getattr(shape, "ShapeBounding", 0)
            SO_Set = getattr(shape, "ShapeSet", 0)

        window.shape_mask(SO_Set, SK_Bounding, 0, 0, pm)
        d.sync()
        print("      Window visually shaped to NOTHING (Bounding Shape).")
    except Exception as e:
        print(f"      Bounding shape failed: {e}")

    print("      >>> Is the screen visible?")
    print("      >>> Move mouse around. Is cursor PIRATE?")

    try:
        # Create a full rectangle bitmap
        pm_full = window.create_pixmap(width, height, 1)
        gc_full = pm_full.create_gc(foreground=1, background=0)
        pm_full.fill_rectangle(gc_full, 0, 0, width, height)

        # SK_Input is usually 2
        SK_Input = getattr(shape, "SK_Input", 2)
        if not hasattr(shape, "SK_Input"):
            SK_Input = getattr(shape, "ShapeInput", 2)

        print("\n[2b/3] Setting Input Shape to FULL SCREEN...")
        window.shape_mask(SO_Set, SK_Input, 0, 0, pm_full)
        d.sync()
        print("       Input shape set.")

    except Exception as e:
        print(f"       (Input shape setting failed: {e})")

    print("      >>> Is cursor PIRATE everywhere? (y/n)")
    time.sleep(5)

    print("\n[3/3] Cleaning up...")
    window.destroy()
    d.sync()
    print("Done.")


if __name__ == "__main__":
    main()
