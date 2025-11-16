#!/usr/bin/env python3
"""Detailed test with full log capture"""

import subprocess
import time
import threading
from Xlib import display as xdisplay


def stream_output(proc, prefix):
    """Stream process output in real-time"""
    for line in iter(proc.stdout.readline, ''):
        if line:
            print(f"{prefix} {line}", end='')


def main():
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

    # Stream server output
    server_thread = threading.Thread(
        target=stream_output,
        args=(server, "[SERVER]"),
        daemon=True
    )
    server_thread.start()
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

    # Stream client output
    client_thread = threading.Thread(
        target=stream_output,
        args=(client, "[CLIENT]"),
        daemon=True
    )
    client_thread.start()
    time.sleep(2)

    # Connect to display
    disp = xdisplay.Display()
    screen = disp.screen()
    root = screen.root
    geom = root.get_geometry()
    width, height = geom.width, geom.height
    mid_y = height // 2

    print(f"\nScreen: {width}x{height}\n")

    # Test 1: Move to center
    print("="*60)
    print("TEST: Moving to center...")
    print("="*60)
    root.warp_pointer(width // 2, mid_y)
    disp.sync()
    time.sleep(1)

    pos = root.query_pointer()
    print(f"Cursor at: ({pos.root_x}, {pos.root_y})\n")

    # Test 2: Trigger CENTER → WEST
    print("="*60)
    print("TEST: Triggering CENTER → WEST transition...")
    print("="*60)

    # Build velocity by moving quickly
    for x in [width//2, width//4, width//8, 50, 10, 0]:
        root.warp_pointer(x, mid_y)
        disp.sync()
        time.sleep(0.01)

    print("Waiting for server to react...")
    time.sleep(2)

    pos = root.query_pointer()
    print(f"\nAfter LEFT boundary cross:")
    print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
    print(f"  Expected: (~{width-1}, {mid_y})")

    if pos.root_x > width - 100:
        print("  ✓ Cursor moved to right edge!\n")
    else:
        print("  ✗ Cursor NOT at right edge\n")

    # Test 3: Trigger WEST → CENTER
    print("="*60)
    print("TEST: Triggering WEST → CENTER transition...")
    print("="*60)

    for x in [width-100, width-50, width-10, width-1]:
        root.warp_pointer(x, mid_y)
        disp.sync()
        time.sleep(0.01)

    print("Waiting for server to react...")
    time.sleep(2)

    pos = root.query_pointer()
    print(f"\nAfter RIGHT boundary cross:")
    print(f"  Cursor at: ({pos.root_x}, {pos.root_y})")
    print(f"  Expected: (~1, {mid_y})")

    if pos.root_x < 100:
        print("  ✓ Cursor moved to left edge!\n")
    else:
        print("  ✗ Cursor NOT at left edge\n")

    # Cleanup
    print("="*60)
    print("Cleaning up...")
    print("="*60)
    time.sleep(1)
    server.terminate()
    client.terminate()
    disp.close()


if __name__ == "__main__":
    main()
