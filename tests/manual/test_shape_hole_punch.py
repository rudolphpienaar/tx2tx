#!/usr/bin/env python3
"""
Test script to verify Shape Extension behavior using a "Hole Punch" strategy.

Instead of making the window empty (which might make it disappear entirely),
we will make a window that is FULL SCREEN but has a HOLE in the center.

If this works:
- Center of screen should be transparent (see desktop)
- Edges should be black
- Cursor should be PIRATE over the black edges
- Cursor should be NORMAL over the hole (unless Input shape is separate)
"""

import time
import sys
from Xlib import display as xdisplay, X
from Xlib.ext import shape

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
    print("TEST: Shape Extension 'Hole Punch'")
    print("=" * 60)

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

    print("\n[2/3] Punching a hole in the center...")

    # 1. Create a bitmap that is 1 (opaque) everywhere
    pm = window.create_pixmap(width, height, 1)
    gc = pm.create_gc(foreground=1, background=0)
    pm.fill_rectangle(gc, 0, 0, width, height)

    # 2. Draw a 0 (transparent) rectangle in the middle
    hole_w, hole_h = 400, 300
    hole_x = (width - hole_w) // 2
    hole_y = (height - hole_h) // 2

    gc_clear = pm.create_gc(foreground=0, background=0)
    pm.fill_rectangle(gc_clear, hole_x, hole_y, hole_w, hole_h)

    # 3. Apply as Bounding Shape
    try:
        SK_Bounding = getattr(shape, "SK_Bounding", 0)
        if not hasattr(shape, "SK_Bounding"):
            SK_Bounding = getattr(shape, "ShapeBounding", 0)

        SO_Set = getattr(shape, "SO_Set", 0)
        if not hasattr(shape, "SO_Set"):
            SO_Set = getattr(shape, "ShapeSet", 0)

        window.shape_mask(SO_Set, SK_Bounding, 0, 0, pm)
        d.sync()
        print("      Hole punched.")

        print(f"      >>> Is there a rectangular hole in the middle? ({hole_w}x{hole_h})")
        print("      >>> Move cursor to EDGE (Black area) -> Should be PIRATE")
        print("      >>> Move cursor to CENTER (Hole) -> Should be NORMAL")

    except Exception as e:
        print(f"      Shape failed: {e}")

    # 4. Try to fix the hole for INPUT only
    print("\n[2b/3] Attempting to patch the Input Shape hole...")
    try:
        # Create a full 1s bitmap
        pm_full = window.create_pixmap(width, height, 1)
        gc_full = pm_full.create_gc(foreground=1, background=0)
        pm_full.fill_rectangle(gc_full, 0, 0, width, height)

        SK_Input = getattr(shape, "SK_Input", 2)
        if not hasattr(shape, "SK_Input"):
            SK_Input = getattr(shape, "ShapeInput", 2)

        window.shape_mask(SO_Set, SK_Input, 0, 0, pm_full)
        d.sync()
        print("       Input shape patched to full screen.")
        print("       >>> Now move cursor to CENTER (Hole). Is it PIRATE?")

    except Exception as e:
        print(f"       Input shape patch failed: {e}")

    time.sleep(5)

    print("\n[3/3] Cleaning up...")
    window.destroy()
    d.sync()
    print("Done.")


if __name__ == "__main__":
    main()
