#!/usr/bin/env python3
"""
Test script to verify cursor movement works in the current environment.

Run this on your Crostini machine to test if cursor warping works visually.
"""

import time
from Xlib import display as xdisplay, X
from Xlib.ext import xtest


def main():
    # Connect to display
    d = xdisplay.Display()
    screen = d.screen()
    root = screen.root

    # Get current position
    pointer = root.query_pointer()
    current_x = pointer.root_x
    current_y = pointer.root_y
    print(f"Current position: ({current_x}, {current_y})")

    # Calculate new position (500 pixels left, clamped to 0)
    new_x = max(0, current_x - 500)
    new_y = current_y
    print(f"Target position: ({new_x}, {new_y})")

    # Give user time to observe
    print("\nWatch the cursor...")
    time.sleep(1)

    # Method 1: warp_pointer
    print("\n--- Testing warp_pointer ---")
    root.warp_pointer(new_x, new_y)
    d.sync()
    time.sleep(0.5)
    pointer = root.query_pointer()
    print(f"X server reports position: ({pointer.root_x}, {pointer.root_y})")
    warp_worked = (pointer.root_x == new_x)
    print(f"Internal position updated: {warp_worked}")
    print(">>> Did the cursor VISUALLY move? (y/n)")

    time.sleep(2)  # Let user observe

    # Move back to original for next test
    print("\nMoving back to original position...")
    root.warp_pointer(current_x, current_y)
    d.sync()
    time.sleep(1)

    # Method 2: XTest fake_input
    print("\n--- Testing XTest fake_input (MotionNotify) ---")
    xtest.fake_input(d, X.MotionNotify, detail=0, x=new_x, y=new_y)
    d.sync()
    time.sleep(0.5)
    pointer = root.query_pointer()
    print(f"X server reports position: ({pointer.root_x}, {pointer.root_y})")
    xtest_worked = (pointer.root_x == new_x)
    print(f"Internal position updated: {xtest_worked}")
    print(">>> Did the cursor VISUALLY move? (y/n)")

    time.sleep(2)  # Let user observe

    # Summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"warp_pointer - Internal position updated: {warp_worked}")
    print(f"XTest fake_input - Internal position updated: {xtest_worked}")
    print()
    print("If internal position updates but cursor doesn't VISUALLY move,")
    print("then Crostini/compositor is blocking visual cursor warping.")
    print("This is expected in Wayland-based environments.")

    d.close()


if __name__ == "__main__":
    main()
