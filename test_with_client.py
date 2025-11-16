#!/usr/bin/env python3
"""Test with both server and client running"""

import subprocess
import time
import signal
import sys
from Xlib import display as xdisplay


def main():
    server = None
    client = None

    try:
        # Start server
        print("="*60)
        print("Starting server...")
        print("="*60)
        server = subprocess.Popen(
            ["tx2tx"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={"DISPLAY": ":0"}
        )
        time.sleep(2)

        # Start client
        print("\n" + "="*60)
        print("Starting client...")
        print("="*60)
        client = subprocess.Popen(
            ["tx2tx", "--client", "phomux"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={"DISPLAY": ":0"}
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
        print("\n" + "="*60)
        print("TEST: Moving to center...")
        print("="*60)
        root.warp_pointer(width // 2, mid_y)
        disp.sync()
        time.sleep(1)

        pos = root.query_pointer()
        print(f"Cursor at: ({pos.root_x}, {pos.root_y})")

        # Move left quickly to trigger transition
        print("\n" + "="*60)
        print("TEST: Moving left quickly (trigger CENTER → WEST)...")
        print("="*60)

        # Quick movements to build velocity
        for x in [width//2, width//4, width//8, 50, 10, 0, -5]:
            root.warp_pointer(x, mid_y)
            disp.sync()
            time.sleep(0.01)  # Fast

        time.sleep(1)  # Wait for server to react

        pos = root.query_pointer()
        print(f"\nAfter crossing LEFT boundary:")
        print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
        print(f"  Expected: (~{width-1}, {mid_y}) [right edge]")

        if pos.root_x > width - 100:
            print("  ✓ SUCCESS: Cursor moved to right edge!")
        else:
            print("  ✗ FAIL: Cursor not at right edge")

        # Move right to return
        print("\n" + "="*60)
        print("TEST: Moving right (trigger WEST → CENTER)...")
        print("="*60)

        for x in [width-100, width-50, width-10, width-1]:
            root.warp_pointer(x, mid_y)
            disp.sync()
            time.sleep(0.01)

        time.sleep(1)

        pos = root.query_pointer()
        print(f"\nAfter crossing RIGHT boundary:")
        print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
        print(f"  Expected: (~1, {mid_y}) [left edge]")

        if pos.root_x < 100:
            print("  ✓ SUCCESS: Cursor moved to left edge!")
        else:
            print("  ✗ FAIL: Cursor not at left edge")

        # Show some server logs
        print("\n" + "="*60)
        print("Server output (last 20 lines):")
        print("="*60)
        server.terminate()
        server.wait(timeout=2)

        # Read remaining output
        output = server.stdout.read()
        lines = output.split('\n')[-20:]
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
