#!/usr/bin/env python3
"""Test cursor operations in isolation"""

import time
import logging

from tx2tx.x11.display import DisplayManager
from tx2tx.common.types import Position

# Setup logging to see all debug messages
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    print("=" * 60)
    print("Testing cursor operations in isolation")
    print("=" * 60)

    dm = DisplayManager()

    try:
        # Connect
        print("\n[TEST] Connecting to display...")
        dm.connection_establish()
        geom = dm.screenGeometry_get()
        print(f"[TEST] Connected! Screen: {geom.width}x{geom.height}")

        # Get initial position

        disp = dm.display_get()
        root = disp.screen().root
        pos = root.query_pointer()
        print(f"[TEST] Initial cursor position: ({pos.root_x}, {pos.root_y})")

        # Test 1: Move cursor
        print("\n[TEST 1] Testing cursor move to center...")
        center = Position(x=geom.width // 2, y=geom.height // 2)
        dm.cursorPosition_set(center)
        time.sleep(0.5)

        pos = root.query_pointer()
        print(f"[TEST 1] After move: ({pos.root_x}, {pos.root_y})")
        if abs(pos.root_x - center.x) < 10:
            print("[TEST 1] ✓ PASS - Cursor moved successfully")
        else:
            print(f"[TEST 1] ✗ FAIL - Expected {center.x}, got {pos.root_x}")

        # Test 2: Hide cursor
        print("\n[TEST 2] Testing cursor hide...")
        try:
            dm.cursor_hide()
            print("[TEST 2] cursor_hide() returned successfully")
            time.sleep(1)
            print("[TEST 2] ✓ PASS - Cursor hide completed")
        except Exception as e:
            print(f"[TEST 2] ✗ FAIL - cursor_hide() raised: {e}")
            import traceback

            traceback.print_exc()
            return

        # Test 3: Move cursor while hidden
        print("\n[TEST 3] Testing cursor move while hidden...")
        right_edge = Position(x=geom.width - 1, y=geom.height // 2)
        try:
            dm.cursorPosition_set(right_edge)
            time.sleep(0.5)

            pos = root.query_pointer()
            print(f"[TEST 3] After move: ({pos.root_x}, {pos.root_y})")
            if abs(pos.root_x - right_edge.x) < 10:
                print("[TEST 3] ✓ PASS - Cursor moved to right edge")
            else:
                print(f"[TEST 3] ✗ FAIL - Expected {right_edge.x}, got {pos.root_x}")
        except Exception as e:
            print(f"[TEST 3] ✗ FAIL - cursorPosition_set() raised: {e}")
            import traceback

            traceback.print_exc()

        # Test 4: Show cursor
        print("\n[TEST 4] Testing cursor show...")
        try:
            dm.cursor_show()
            print("[TEST 4] cursor_show() returned successfully")
            time.sleep(1)
            print("[TEST 4] ✓ PASS - Cursor show completed")
        except Exception as e:
            print(f"[TEST 4] ✗ FAIL - cursor_show() raised: {e}")
            import traceback

            traceback.print_exc()

        # Test 5: Grab and ungrab
        print("\n[TEST 5] Testing pointer grab...")
        try:
            dm.pointer_grab()
            print("[TEST 5] pointer_grab() succeeded")
            time.sleep(1)

            dm.pointer_ungrab()
            print("[TEST 5] pointer_ungrab() succeeded")
            print("[TEST 5] ✓ PASS - Grab/ungrab completed")
        except Exception as e:
            print(f"[TEST 5] ✗ FAIL - {e}")
            import traceback

            traceback.print_exc()

        # Test 6: Full transition sequence
        print("\n[TEST 6] Testing full transition sequence...")
        try:
            # Move to left edge
            dm.cursorPosition_set(Position(x=10, y=geom.height // 2))
            time.sleep(0.2)

            print("[TEST 6] Step 1: Grabbing input...")
            dm.pointer_grab()
            dm.keyboard_grab()

            print("[TEST 6] Step 2: Hiding cursor...")
            dm.cursor_hide()

            print("[TEST 6] Step 3: Moving to right edge...")
            dm.cursorPosition_set(Position(x=geom.width - 1, y=geom.height // 2))
            time.sleep(0.5)

            pos = root.query_pointer()
            print(f"[TEST 6] Cursor after full sequence: ({pos.root_x}, {pos.root_y})")

            print("[TEST 6] Step 4: Showing cursor...")
            dm.cursor_show()

            print("[TEST 6] Step 5: Ungrabbing...")
            dm.keyboard_ungrab()
            dm.pointer_ungrab()

            if pos.root_x > geom.width - 10:
                print("[TEST 6] ✓ PASS - Full transition sequence works!")
            else:
                print(f"[TEST 6] ✗ FAIL - Cursor at {pos.root_x}, expected near {geom.width-1}")

        except Exception as e:
            print(f"[TEST 6] ✗ FAIL - {e}")
            import traceback

            traceback.print_exc()

        print("\n" + "=" * 60)
        print("Test completed")
        print("=" * 60)

    finally:
        dm.connection_close()


if __name__ == "__main__":
    main()
