#!/usr/bin/env python3
"""Test Software Cursor (Window Movement) feasibility on Crostini"""

import time
from Xlib import display as xdisplay, X

def main():
    try:
        d = xdisplay.Display()
        screen = d.screen()
        root = screen.root
        
        print("Creating 'Software Cursor' window (Red Square)...")
        
        # Create a small 20x20 red window
        # override_redirect=True means it bypasses the Window Manager (no title bar, floating)
        sw_cursor = root.create_window(
            100, 100,              # x, y
            20, 20,                # width, height
            0,                     # border
            screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=0xFF0000,  # Red (simplified, might need colormap)
            override_redirect=True
        )
        
        # Determine red color properly
        cmap = screen.default_colormap
        red = cmap.alloc_color(65535, 0, 0)
        sw_cursor.change_attributes(background_pixel=red.pixel)
        
        sw_cursor.map()
        d.sync()
        print("Window created at (100, 100). Do you see a red square?")
        time.sleep(2)
        
        print("Moving window diagonally across screen...")
        width = screen.width_in_pixels
        height = screen.height_in_pixels
        
        # Move loop
        for i in range(100):
            x = int(100 + (width - 200) * (i / 100))
            y = int(100 + (height - 200) * (i / 100))
            
            # Move the window
            sw_cursor.configure(x=x, y=y, stack_mode=X.Above)
            d.sync()
            time.sleep(0.02)
            
        print("Movement complete. Did the red square move smoothly?")
        time.sleep(1)
        
        sw_cursor.destroy()
        d.sync()
        print("Test complete.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
