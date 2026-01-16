#!/usr/bin/env python3
"""
Test script to verify if a Stippled Background (Checkerboard) provides
pseudo-transparency while still enforcing the custom cursor.

If this works:
- Screen should look "dimmed" or "grid-like" (50% black pixels).
- Cursor should be PIRATE everywhere (or at least flicker Pirate).
"""

import time
import sys
from Xlib import display as xdisplay, X

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
    print("TEST: Stippled (Checkerboard) Overlay")
    print("=" * 60)

    cursor_font = d.open_font("cursor")
    cursor = cursor_font.create_glyph_cursor(
        cursor_font, XC_PIRATE, XC_PIRATE + 1, (65535, 0, 0), (65535, 65535, 65535)  # Red Pirate
    )
    cursor_font.close()

    print("\n[1/2] Creating Stippled Bitmap...")

    # Create a 2x2 bitmap pattern
    # 1 0
    # 0 1
    # This is a standard 50% checkerboard
    bitmap_data = bytes([0x02, 0x01])  # Binary: 10, 01 ? No, rows are byte-aligned usually.
    # Actually, XCreateBitmapFromData expects data in specific format.
    # Let's create a pixmap and draw points manually to be safe.

    stipple = root.create_pixmap(2, 2, 1)  # 2x2, depth 1
    gc = stipple.create_gc(foreground=0, background=0)
    stipple.fill_rectangle(gc, 0, 0, 2, 2)  # Clear to 0

    gc.change(foreground=1)
    stipple.fill_rectangle(gc, 0, 0, 1, 1)
    stipple.fill_rectangle(gc, 1, 1, 1, 1)

    print("      Stipple created.")

    print("\n[2/2] Creating Window with ParentRelative background...")
    # Wait, we want the window to HAVE the stipple as background.
    # But windows usually take a pixel value or a pixmap.

    window = root.create_window(
        0,
        0,
        width,
        height,
        0,
        screen.root_depth,
        X.InputOutput,
        X.CopyFromParent,
        background_pixmap=0,  # We will set it later
        override_redirect=True,
        cursor=cursor,
        event_mask=0,
    )

    # Now set the background to use the stipple
    # We need a GC that tiles the stipple?
    # No, we can set window attribute 'background_pixmap' to a pixmap of depth=root_depth.
    # But our stipple is depth 1.
    # We need to tile the stipple into a pixmap of the window's depth?
    # Or rely on 'background_pixmap' accepting ParentRelative?

    # Simpler approach: Create a window with a transparent background? No, we tried that.
    # We want to draw Black pixels where the stipple is 1, and Nothing where it is 0?
    # That requires Shape extension again.

    # Let's try shaping the window using the stipple!
    # If we tile the 2x2 stipple across the whole screen into a bitmap,
    # and use THAT as the Shape Mask...

    print("      Tiling stipple for Shape Mask (this might be slow)...")

    try:
        from Xlib.ext import shape

        # Create a full-screen bitmap
        mask = window.create_pixmap(width, height, 1)

        # Use a GC to tile the stipple
        gc_tile = mask.create_gc(foreground=1, background=0, fill_style=X.FillTiled, tile=stipple)

        mask.fill_rectangle(gc_tile, 0, 0, width, height)

        # Apply shape
        SK_Bounding = getattr(shape, "SK_Bounding", 0)
        if not hasattr(shape, "SK_Bounding"):
            SK_Bounding = getattr(shape, "ShapeBounding", 0)
        SO_Set = getattr(shape, "SO_Set", 0)
        if not hasattr(shape, "SO_Set"):
            SO_Set = getattr(shape, "ShapeSet", 0)

        window.shape_mask(SO_Set, SK_Bounding, 0, 0, mask)

        # Set background to black (so the '1' bits are black)
        window.change_attributes(background_pixel=0)

        window.map()
        window.configure(stack_mode=X.Above)
        d.sync()

        print("      Window mapped with Stippled Shape.")
        print("      >>> Is the screen dimmed/grid-like? (You should see desktop through holes)")
        print("      >>> Is the cursor RED PIRATE?")

    except Exception as e:
        print(f"FAILED: {e}")

    time.sleep(5)

    print("\nCleaning up...")
    window.destroy()
    d.sync()
    print("Done.")


if __name__ == "__main__":
    main()
