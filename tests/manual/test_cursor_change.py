#!/usr/bin/env python3
"""
Test script to verify cursor changing works in the current environment.

Run this on your Crostini machine to test if cursor appearance can be changed.
"""

import time
from Xlib import display as xdisplay, X

# X11 cursor font constants
XC_X_CURSOR = 0  # X shape
XC_CROSSHAIR = 34  # Crosshair +
XC_PIRATE = 88  # Skull and crossbones
XC_WATCH = 150  # Watch/hourglass


def main():
    # Connect to display
    d = xdisplay.Display()
    screen = d.screen()
    root = screen.root

    print("=" * 50)
    print("CURSOR CHANGE TEST")
    print("=" * 50)
    print(f"Display: {d.get_display_name()}")
    print(f"Screen size: {screen.width_in_pixels}x{screen.height_in_pixels}")
    print()

    # Test 1: Change root window cursor using cursor font
    print("--- Test 1: Root window cursor (cursor font) ---")
    print("Attempting to change root window cursor to X shape...")
    try:
        cursor_font = d.open_font("cursor")
        x_cursor = cursor_font.create_glyph_cursor(
            cursor_font,
            XC_X_CURSOR,
            XC_X_CURSOR + 1,
            (65535, 0, 0),  # Red foreground
            (65535, 65535, 65535),  # White background
        )
        cursor_font.close()

        root.change_attributes(cursor=x_cursor)
        d.sync()
        print("SUCCESS: change_attributes(cursor=...) completed without error")
        print(">>> Move cursor over desktop background - is it a RED X? (y/n)")
        time.sleep(3)
    except Exception as e:
        print(f"FAILED: {e}")

    # Test 2: Try XFixes hide
    print()
    print("--- Test 2: XFixes hide_cursor ---")
    try:
        if d.has_extension("XFIXES"):
            print("XFixes extension available")
            d.xfixes.hide_cursor(root)
            d.sync()
            print("SUCCESS: hide_cursor completed without error")
            print(">>> Is the cursor hidden? (y/n)")
            time.sleep(3)

            # Show it again
            d.xfixes.show_cursor(root)
            d.sync()
            print("Called show_cursor")
        else:
            print("XFixes extension NOT available")
    except Exception as e:
        print(f"FAILED: {e}")

    # Test 3: Create a window and set its cursor
    print()
    print("--- Test 3: Window-specific cursor ---")
    print("Creating a test window with pirate cursor...")
    try:
        cursor_font = d.open_font("cursor")
        pirate_cursor = cursor_font.create_glyph_cursor(
            cursor_font,
            XC_PIRATE,
            XC_PIRATE + 1,
            (0, 0, 0),  # Black foreground
            (65535, 65535, 65535),  # White background
        )
        cursor_font.close()

        # Create a small window
        window = root.create_window(
            100,
            100,  # position
            400,
            300,  # size
            2,  # border width
            screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=screen.white_pixel,
            event_mask=X.ExposureMask,
            cursor=pirate_cursor,
        )
        window.map()
        d.sync()

        print("SUCCESS: Created window with pirate cursor")
        print(">>> Move cursor INTO the white window - is it a skull? (y/n)")
        time.sleep(5)

        window.destroy()
        d.sync()
    except Exception as e:
        print(f"FAILED: {e}")

    # Test 4: Define cursor on root with different method
    print()
    print("--- Test 4: XDefineCursor equivalent ---")
    print("Attempting define_cursor on root window...")
    try:
        cursor_font = d.open_font("cursor")
        watch_cursor = cursor_font.create_glyph_cursor(
            cursor_font,
            XC_WATCH,
            XC_WATCH + 1,
            (0, 0, 65535),  # Blue foreground
            (65535, 65535, 65535),  # White background
        )
        cursor_font.close()

        # Try using the cursor attribute differently
        root.change_attributes(cursor=watch_cursor)
        d.flush()
        d.sync()
        print("SUCCESS: define_cursor completed")
        print(">>> Is cursor a BLUE watch/hourglass over desktop? (y/n)")
        time.sleep(3)
    except Exception as e:
        print(f"FAILED: {e}")

    # Reset to default
    print()
    print("--- Resetting cursor to default ---")
    try:
        root.change_attributes(cursor=X.NONE)
        d.sync()
        print("Reset complete")
    except Exception as e:
        print(f"Reset failed: {e}")

    print()
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print("If all calls succeeded but cursor never changed visually,")
    print("then Crostini compositor is ignoring X11 cursor settings.")
    print("This is the same root cause as the warp issue.")

    d.close()


if __name__ == "__main__":
    main()
