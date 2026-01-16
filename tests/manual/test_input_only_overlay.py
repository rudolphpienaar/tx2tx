#!/usr/bin/env python3
"""
Test script to verify if an InputOnly window can provide transparency
while still changing the cursor appearance.
"""

import time
import sys
from Xlib import display as xdisplay, X

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
    print("TEST: InputOnly Transparent Overlay")
    print("=" * 60)

    # Create Pirate Cursor
    cursor_font = d.open_font("cursor")
    cursor = cursor_font.create_glyph_cursor(
        cursor_font, XC_PIRATE, XC_PIRATE + 1, (0, 0, 0), (65535, 65535, 65535)
    )
    cursor_font.close()

    print("\n[1/2] Creating InputOnly window...")
    # For InputOnly windows:
    # - depth must be 0
    # - visual must be CopyFromParent (0)
    # - background attributes are NOT allowed
    try:
        window = root.create_window(
            0,
            0,
            width,
            height,
            0,
            0,  # depth MUST be 0
            X.InputOnly,  # class
            X.CopyFromParent,  # visual
            override_redirect=True,
            cursor=cursor,
            event_mask=0,
        )
        window.map()
        window.configure(stack_mode=X.Above)
        d.sync()

        print("      InputOnly window mapped.")
        print("      >>> Is the screen transparent (desktop visible)?")
        print("      >>> Is the cursor a SKULL AND CROSSBONES?")

        time.sleep(5)
    except Exception as e:
        print(f"FAILED: {e}")
    finally:
        print("\n[2/2] Cleaning up...")
        window.destroy()
        d.sync()
        print("Done.")


if __name__ == "__main__":
    main()
