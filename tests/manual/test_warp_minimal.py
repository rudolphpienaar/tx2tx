
import time
from Xlib import X, display
from Xlib.ext import xtest

def test_warp():
    try:
        # Connect
        d = display.Display()
        screen = d.screen()
        root = screen.root
        width = screen.width_in_pixels
        height = screen.height_in_pixels
        
        print(f"Display: {d.get_display_name()}")
        print(f"Screen: {width}x{height}")
        
        # Get start pos
        data = root.query_pointer()
        start_x, start_y = data.root_x, data.root_y
        print(f"Start Pos: ({start_x}, {start_y})")
        
        # Target 1: Offset by 100 pixels
        target_x = (start_x + 100) % width
        target_y = (start_y + 100) % height
        
        print(f"\n[Test 1] Attempting XWarpPointer to ({target_x}, {target_y})...")
        root.warp_pointer(target_x, target_y)
        d.sync()
        time.sleep(0.5)
        
        data = root.query_pointer()
        new_x, new_y = data.root_x, data.root_y
        print(f"Result 1: ({new_x}, {new_y})")
        
        if abs(new_x - target_x) < 5 and abs(new_y - target_y) < 5:
            print(">>> SUCCESS: WarpPointer works!")
        else:
            print(">>> FAIL: WarpPointer ignored.")

        # Target 2: Offset another 100 pixels
        target_x = (new_x + 100) % width
        target_y = (new_y + 100) % height
        
        print(f"\n[Test 2] Attempting XTest FakeInput to ({target_x}, {target_y})...")
        xtest.fake_input(d, X.MotionNotify, detail=0, x=target_x, y=target_y)
        d.sync()
        time.sleep(0.5)
        
        data = root.query_pointer()
        new_x, new_y = data.root_x, data.root_y
        print(f"Result 2: ({new_x}, {new_y})")
        
        if abs(new_x - target_x) < 5 and abs(new_y - target_y) < 5:
            print(">>> SUCCESS: XTest works!")
        else:
            print(">>> FAIL: XTest ignored.")
            
    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    test_warp()
