#!/usr/bin/env python3
"""Test click-through window using XShape"""

from Xlib import X, display
from Xlib.ext import shape
import time

def main():
    d = display.Display()
    root = d.screen().root
    
    # Create window
    win = root.create_window(
        100, 100, 100, 100, 0,
        d.screen().root_depth,
        X.InputOutput,
        X.CopyFromParent,
        background_pixel=0xFF0000,
        override_redirect=True
    )
    
    # Make it click-through using XShape
    # We set the "Input" shape to an empty region
    try:
        # Check if shape extension exists
        if not d.has_extension('SHAPE'):
            print("Shape extension not available")
            return

        # Create a 1x1 pixmap for masking (though we want EMPTY)
        # Actually, to make it fully input transparent, we can just set the
        # ShapeInput rectangle to nothing?
        
        # Method: Use XFixes SetWindowShapeRegion if available?
        # Or standard Shape extension:
        # shape.rectangles(win, shape.SO_Set, shape.SK_Input, 0, 0, [])
        # SK_Input is kind of new (XShape 1.1).
        
        # Let's try passing an empty list of rectangles to ShapeInput
        # Note: python-xlib shape extension support might vary
        
        # Standard Shape Bounding (visual) vs Shape Input (mouse)
        # 0 = ShapeBounding, 1 = ShapeClip, 2 = ShapeInput
        SK_Input = 2 
        
        print("Applying Input Shape Mask (Empty)...")
        shape.rectangles(win, shape.SO_Set, SK_Input, 0, 0, [])
        
    except Exception as e:
        print(f"Failed to apply shape: {e}")

    win.map()
    d.sync()
    
    print("Red box at 100,100. Try to click THROUGH it.")
    print("If you can click the window BEHIND it, test passed.")
    time.sleep(5)
    
    win.destroy()
    d.sync()

if __name__ == "__main__":
    main()
