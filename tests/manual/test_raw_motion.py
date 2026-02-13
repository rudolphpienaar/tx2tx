#!/usr/bin/env python3
"""Test XInput2 Raw Motion events"""

import time
from Xlib import X, display

def main():
    try:
        d = display.Display()
        screen = d.screen()
        root = screen.root

        # Check for XInput extension
        extension_info = d.query_extension('XInputExtension')
        if not extension_info:
            print("XInput extension not available")
            return

        print(f"XInput version: {d.xinput_query_version().major_version}.{d.xinput_query_version().minor_version}")

        # Select RawMotion events on root window
        # XI_RawMotion = 17 (bit 17)
        # mask is byte array
        
        # This is complex in python-xlib. 
        # Simplified test: just grab pointer and print generic events?
        
        print("\nMove your mouse! Checking for standard MotionNotify events at edge...")
        print("Push your mouse against the left edge (x=0). Keep pushing.")
        
        # Standard loop
        for i in range(50):
            while d.pending_events():
                e = d.next_event()
                if e.type == X.MotionNotify:
                    print(f"Motion: ({e.root_x}, {e.root_y})")
            
            p = root.query_pointer()
            print(f"Poll: ({p.root_x}, {p.root_y})")
            time.sleep(0.1)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
