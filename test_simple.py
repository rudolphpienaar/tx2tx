#!/usr/bin/env python3
"""Simple test to check if transitions are working"""

import subprocess
import time
from Xlib import display as xdisplay


def main():
    # Start server
    print("Starting server...")
    server = subprocess.Popen(
        ["tx2tx"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env={"DISPLAY": ":0"}
    )

    # Wait for server to start
    time.sleep(2)

    # Connect to display
    disp = xdisplay.Display()
    screen = disp.screen()
    root = screen.root
    geom = root.get_geometry()
    width, height = geom.width, geom.height
    mid_y = height // 2

    print(f"Screen: {width}x{height}")

    # Move to center
    print("Moving to center...")
    root.warp_pointer(width // 2, mid_y)
    disp.sync()
    time.sleep(1)

    # Start reading server output in background
    import threading
    def read_output():
        for line in server.stdout:
            print(f"[SERVER] {line}", end='')

    output_thread = threading.Thread(target=read_output, daemon=True)
    output_thread.start()

    # Move left slowly
    print("\nMoving left slowly (below velocity threshold)...")
    for x in range(width // 2, -10, -10):
        root.warp_pointer(x, mid_y)
        disp.sync()
        time.sleep(0.1)  # Slow movement

    time.sleep(2)
    pos = root.query_pointer()
    print(f"\nCursor after slow left movement: ({pos.root_x}, {pos.root_y})")

    # Move back to center
    print("\nMoving back to center...")
    root.warp_pointer(width // 2, mid_y)
    disp.sync()
    time.sleep(1)

    # Move left quickly
    print("\nMoving left quickly (above velocity threshold)...")
    for x in range(width // 2, -10, -100):
        root.warp_pointer(x, mid_y)
        disp.sync()
        time.sleep(0.01)  # Fast movement

    time.sleep(2)
    pos = root.query_pointer()
    print(f"\nCursor after fast left movement: ({pos.root_x}, {pos.root_y})")
    print(f"Expected at right edge: ~{width-1}")

    # Cleanup
    time.sleep(2)
    print("\nCleaning up...")
    server.terminate()
    server.wait()
    disp.close()


if __name__ == "__main__":
    main()
