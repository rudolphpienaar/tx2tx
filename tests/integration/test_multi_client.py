#!/usr/bin/env python3
"""Test with server and multiple clients (WEST and EAST)"""

import os
import subprocess
import time
from Xlib import display as xdisplay
from Xlib import X
from Xlib.ext import xtest


def move_cursor(disp, x, y):
    xtest.fake_input(disp, X.MotionNotify, detail=0, x=int(x), y=int(y))
    disp.sync()


def main():
    server = None
    client_west = None
    client_east = None

    try:
        # Start server with multi-client config
        print("=" * 60)
        print("Starting server (config_multi.yml)...")
        print("=" * 60)
        env = os.environ.copy()
        env["DISPLAY"] = ":0"

        server = subprocess.Popen(
            ["tx2tx", "--config", "tests/config_multi.yml"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )
        time.sleep(2)

        # Start Client West
        print("\n" + "="*60)
        print("Starting Client West...")
        print("="*60)
        client_west = subprocess.Popen(
            ["tx2tx", "--client", "client_west", "--config", "tests/config_multi.yml"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )
        time.sleep(1)

        # Start Client East
        print("\n" + "="*60)
        print("Starting Client East...")
        print("="*60)
        client_east = subprocess.Popen(
            ["tx2tx", "--client", "client_east", "--config", "tests/config_multi.yml"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )
        time.sleep(2)

        # Connect to display
        disp = xdisplay.Display()
        screen = disp.screen()
        root = screen.root
        geom = root.get_geometry()
        width, height = geom.width, geom.height
        mid_y = height // 2

        print(f"\nScreen: {width}x{height}")

        # ---------------------------------------------------------
        # Test 1: CENTER -> WEST
        # ---------------------------------------------------------
        print("\n" + "=" * 60)
        print("TEST 1: Moving to center...")
        move_cursor(disp, width // 2, mid_y)
        time.sleep(1)

        print("\nTEST 1: Moving LEFT quickly (CENTER → WEST)...")
        start_x = 400
        step = 40
        for x in range(start_x, -40, -step):
            move_cursor(disp, x, mid_y)
            time.sleep(0.02)
        time.sleep(1)

        pos = root.query_pointer()
        print("After LEFT boundary cross:")
        print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
        print(f"  Expected: (~{width-1}, {mid_y}) [right edge]")

        if pos.root_x > width - 100:
            print("  ✓ SUCCESS: Cursor moved to right edge (WEST active)!")
        else:
            print("  ✗ FAIL: Cursor not at right edge")

        # ---------------------------------------------------------
        # Test 2: WEST -> CENTER
        # ---------------------------------------------------------
        print("\n" + "=" * 60)
        print("TEST 2: Moving RIGHT (WEST → CENTER)...")
        start_x = width - 400
        step = 40
        for x in range(start_x, width + 40, step):
            move_cursor(disp, min(x, width - 1), mid_y)
            time.sleep(0.02)
        time.sleep(1)

        pos = root.query_pointer()
        print("After RIGHT boundary cross:")
        print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
        print(f"  Expected: (~1, {mid_y}) [left edge]")

        if pos.root_x < 100:
            print("  ✓ SUCCESS: Cursor returned to left edge (CENTER active)!")
        else:
            print("  ✗ FAIL: Cursor not at left edge")

        # ---------------------------------------------------------
        # Test 3: CENTER -> EAST
        # ---------------------------------------------------------
        print("\n" + "=" * 60)
        print("TEST 3: Moving back to center...")
        move_cursor(disp, width // 2, mid_y)
        time.sleep(1)

        print("\nTEST 3: Moving RIGHT quickly (CENTER → EAST)...")
        start_x = width - 400
        step = 40
        for x in range(start_x, width + 40, step):
            move_cursor(disp, min(x, width - 1), mid_y)
            time.sleep(0.02)
        time.sleep(1)

        pos = root.query_pointer()
        print("After RIGHT boundary cross:")
        print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
        print(f"  Expected: (~1, {mid_y}) [left edge]")

        if pos.root_x < 100:
            print("  ✓ SUCCESS: Cursor moved to left edge (EAST active)!")
        else:
            print("  ✗ FAIL: Cursor not at left edge")

        # ---------------------------------------------------------
        # Test 4: EAST -> CENTER
        # ---------------------------------------------------------
        print("\n" + "=" * 60)
        print("TEST 4: Moving LEFT (EAST → CENTER)...")
        start_x = 400
        step = 40
        for x in range(start_x, -40, -step):
            move_cursor(disp, x, mid_y)
            time.sleep(0.02)
        time.sleep(1)

        pos = root.query_pointer()
        print("After LEFT boundary cross:")
        print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
        print(f"  Expected: (~{width-1}, {mid_y}) [right edge]")

        if pos.root_x > width - 100:
            print("  ✓ SUCCESS: Cursor returned to right edge (CENTER active)!")
        else:
            print("  ✗ FAIL: Cursor not at right edge")

        # Show some server logs
        print("\n" + "=" * 60)
        print("Server output (last 40 lines):")
        print("=" * 60)
        server.terminate()
        server.wait(timeout=2)

        output = server.stdout.read()
        lines = output.split("\n")[-40:]
        for line in lines:
            if line.strip():
                print(line)

    except KeyboardInterrupt:
        print("\nInterrupted!")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        print("\nCleaning up...")
        if server:
            server.terminate()
        if client_west:
            client_west.terminate()
        if client_east:
            client_east.terminate()
        time.sleep(1)


if __name__ == "__main__":
    main()
