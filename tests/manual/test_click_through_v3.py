#!/usr/bin/env python3
"""Test click-through window using XShape v3"""

from Xlib import X, display
from Xlib.ext import shape
import time

def main():
    d = display.Display()
    root = d.screen().root
    
    win = root.create_window(
        100, 100, 100, 100, 0,
        d.screen().root_depth,
        X.InputOutput,
        X.CopyFromParent,
        background_pixel=0xFF0000,
        override_redirect=True
    )
    
    try:
        if not d.has_extension('SHAPE'):
            print("Shape extension not available")
            return

        ShapeSet = 0
        ShapeInput = 2 
        
        # Try adding 'ordering' (Unsorted = 0)
        # shape.rectangles(window, operation, kind, x_offset, y_offset, rectangles)
        # Maybe it wants 'ordering' as a keyword or positional?
        print("Applying Input Shape Mask...")
        shape.rectangles(win, ShapeSet, ShapeInput, 0, 0, [], 0)
        print("Success?")
        
    except Exception as e:
        print(f"Failed to apply shape: {e}")

    win.map()
    d.sync()
    
    print("Red box at 100,100. Try to click THROUGH it.")
    time.sleep(5)
    
    win.destroy()
    d.sync()

if __name__ == "__main__":
    main()
