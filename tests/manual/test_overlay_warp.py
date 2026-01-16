#!/usr/bin/env python3
"""
Test script to verify if cursor warping works VISUALLY when inside the overlay window.

Hypothesis: Maybe the compositor allows warping if it happens 'inside' a fullscreen
override_redirect window that 'owns' the screen?
"""

import time
import sys
from Xlib import display as xdisplay, X
from Xlib.ext import xtest

# Standard cursor shape
XC_X_CURSOR = 0


def main():
    # Connect to display
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
    print("TEST: Cursor Warp inside Overlay Window")
    print("=" * 60)
    print(f"Screen: {width}x{height}")

    # 1. Create the overlay window (mimicking tx2tx/x11/display.py)
    print("\n[1/4] Creating fullscreen overlay window...")
    try:
        # Create cursor
        cursor_font = d.open_font("cursor")
        cursor = cursor_font.create_glyph_cursor(
            cursor_font,
            XC_X_CURSOR,
            XC_X_CURSOR + 1,
            (65535, 0, 0),
            (65535, 65535, 65535),  # Red X cursor
        )
        cursor_font.close()

        window = root.create_window(
            0,
            0,
            width,
            height,
            0,
            screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=0,
            override_redirect=True,
            cursor=cursor,
            event_mask=0,
        )

        window.map()
        window.configure(stack_mode=X.Above)
        d.sync()
        print("      Overlay created. You should see a RED X cursor.")
        time.sleep(1)
    except Exception as e:
        print(f"FAILED to create overlay: {e}")
        sys.exit(1)

    # 2. Warp to Center
    center_x, center_y = width // 2, height // 2
    print(f"\n[2/4] Attempting warp to CENTER ({center_x}, {center_y})...")

    # Method A: Warp Pointer
    root.warp_pointer(center_x, center_y)
    d.sync()

    # Verify Internal
    p = root.query_pointer()
    print(
        f"      Internal State: ({p.root_x}, {p.root_y}) "
        + ("MATCH" if p.root_x == center_x else "FAIL")
    )

    print("      >>> LOOK AT SCREEN: Is cursor in the center? (Wait 2s)")
    time.sleep(2)

    # 3. Warp to Edge (0, 0)
    print("\n[3/4] Attempting warp to TOP-LEFT (0, 0) using XTest...")
    xtest.fake_input(d, X.MotionNotify, detail=0, x=0, y=0)
    d.sync()

    # Verify Internal
    p = root.query_pointer()
    print(
        f"      Internal State: ({p.root_x}, {p.root_y}) " + ("MATCH" if p.root_x == 0 else "FAIL")
    )

    print("      >>> LOOK AT SCREEN: Did cursor jump to top-left? (Wait 2s)")
    time.sleep(2)

    # 4. Clean up
    print("\n[4/4] Cleaning up...")
    window.destroy()
    d.sync()
    print("Done.")


if __name__ == "__main__":
    main()
