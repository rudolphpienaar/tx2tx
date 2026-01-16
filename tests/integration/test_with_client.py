#!/usr/bin/env python3
"""Test with both server and client running"""

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
    client = None

    try:
        # Start server
        print("=" * 60)
        print("Starting server...")
        print("=" * 60)
        env = os.environ.copy()
        env["DISPLAY"] = ":0"

        server = subprocess.Popen(
            ["tx2tx"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        time.sleep(2)

        # Start client
        print("\n" + "=" * 60)
        print("Starting client...")
        print("=" * 60)
        client = subprocess.Popen(
            ["tx2tx", "--client", "phomux"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
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

        # Move to center
        print("\n" + "=" * 60)
        print("TEST: Moving to center...")
        print("=" * 60)
        move_cursor(disp, width // 2, mid_y)
        time.sleep(1)

        pos = root.query_pointer()
        print(f"Cursor at: ({pos.root_x}, {pos.root_y})")

        # Move left quickly to trigger transition
        print("\n" + "=" * 60)
        print("TEST: Moving left quickly (trigger CENTER → WEST)...")
        print("=" * 60)

        # Quick movements to build velocity
        # We need to ensure the server (polling every 20ms) catches the movement
        # and sees a high velocity.
        # Move from 200 to -10 in steps of 20, sleeping 15ms
        start_x = 200
        step = 20
        for x in range(start_x, -20, -step):
            move_cursor(disp, x, mid_y)
            time.sleep(0.015)  # 15ms, slightly faster than server poll (20ms)

        time.sleep(1)  # Wait for server to react

        pos = root.query_pointer()
        print("\nAfter crossing LEFT boundary:")
        print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
        print(f"  Expected: (~{width-1}, {mid_y}) [right edge]")

        if pos.root_x > width - 100:
            print("  ✓ SUCCESS: Cursor moved to right edge!")
        else:
            print("  ✗ FAIL: Cursor not at right edge")

        # Move right to return
        print("\n" + "=" * 60)
        print("TEST: Moving right (trigger WEST → CENTER)...")
        print("=" * 60)

        start_x = width - 200
        step = 40
        # Approach edge fast
        for x in range(start_x, width, step):
            move_cursor(disp, min(x, width-1), mid_y)
            time.sleep(0.015)
        
        # Hit edge explicitly to ensure we are there
        move_cursor(disp, width-1, mid_y)
        time.sleep(0.015)
        # One more time to be sure server catches it, but history still has motion
        move_cursor(disp, width-1, mid_y)

        time.sleep(1)

        pos = root.query_pointer()
        print("\nAfter crossing RIGHT boundary:")
        print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
        print(f"  Expected: (~1, {mid_y}) [left edge]")

        if pos.root_x < 100:
            print("  ✓ SUCCESS: Cursor moved to left edge!")
        else:
            print("  ✗ FAIL: Cursor not at left edge")

        # Show some server logs
        print("\n" + "=" * 60)
        print("Server output (last 20 lines):")
        print("=" * 60)
        server.terminate()
        server.wait(timeout=2)

        # Read remaining output
        output = server.stdout.read()
        lines = output.split("\n")[-20:]
        for line in lines:
            if line.strip():
                print(line)

    except KeyboardInterrupt:
        print("\nInterrupted!")
    finally:
        print("\nCleaning up...")
        if server:
            server.terminate()
        if client:
            client.terminate()
        time.sleep(1)


if __name__ == "__main__":
    main()
