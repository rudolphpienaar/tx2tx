#!/usr/bin/env python3
"""Phase 7 automated testing script"""

import subprocess
import time
import signal
import sys
from pathlib import Path

from Xlib import display as xdisplay, X
from Xlib.display import Display


class Harness:
    def __init__(self):
        self.server_proc = None
        self.client_proc = None
        self.display = None

    def setup(self):
        """Setup X11 connection"""
        self.display = xdisplay.Display()
        print("[SETUP] Connected to X11 display")

    def cleanup(self):
        """Cleanup processes and connections"""
        print("\n[CLEANUP] Stopping processes...")
        if self.server_proc:
            self.server_proc.terminate()
            self.server_proc.wait(timeout=5)
        if self.client_proc:
            self.client_proc.terminate()
            self.client_proc.wait(timeout=5)
        if self.display:
            self.display.close()
        print("[CLEANUP] Done")

    def start_server(self):
        """Start tx2tx server"""
        print("[SERVER] Starting server...")
        self.server_proc = subprocess.Popen(
            ["tx2tx"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={"DISPLAY": ":0"}
        )
        time.sleep(1)  # Give server time to start
        print("[SERVER] Server started")

    def start_client(self):
        """Start tx2tx client"""
        print("[CLIENT] Starting client...")
        self.client_proc = subprocess.Popen(
            ["tx2tx", "--client", "phomux"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={"DISPLAY": ":0"}
        )
        time.sleep(1)  # Give client time to connect
        print("[CLIENT] Client started")

    def get_cursor_position(self):
        """Get current cursor position"""
        screen = self.display.screen()
        root = screen.root
        pointer = root.query_pointer()
        return (pointer.root_x, pointer.root_y)

    def move_cursor(self, x, y):
        """Move cursor to position"""
        screen = self.display.screen()
        root = screen.root
        root.warp_pointer(x, y)
        self.display.sync()

    def is_cursor_visible(self):
        """Check if cursor is visible (rough heuristic)"""
        # This is difficult to detect reliably, so we'll rely on logs instead
        return None

    def get_screen_geometry(self):
        """Get screen dimensions"""
        screen = self.display.screen()
        root = screen.root
        geom = root.get_geometry()
        return (geom.width, geom.height)

    def test_baseline(self):
        """Test 1: Baseline - CENTER mode works normally"""
        print("\n" + "="*60)
        print("TEST 1: Baseline - CENTER mode")
        print("="*60)

        width, height = self.get_screen_geometry()
        print(f"[INFO] Screen geometry: {width}x{height}")

        # Move cursor to center
        center_x, center_y = width // 2, height // 2
        self.move_cursor(center_x, center_y)
        time.sleep(0.1)

        pos = self.get_cursor_position()
        print(f"[INFO] Cursor at center: ({pos[0]}, {pos[1]})")

        assert abs(pos[0] - center_x) < 10, "Cursor should be at center X"
        assert abs(pos[1] - center_y) < 10, "Cursor should be at center Y"

        print("[PASS] Baseline test passed")
        return True

    def test_center_to_west(self):
        """Test 2: CENTER → WEST transition"""
        print("\n" + "="*60)
        print("TEST 2: CENTER → WEST transition")
        print("="*60)

        width, height = self.get_screen_geometry()
        mid_y = height // 2

        # Start from center
        print("[ACTION] Moving to center...")
        self.move_cursor(width // 2, mid_y)
        time.sleep(0.5)

        # Move left in steps, crossing boundary
        print("[ACTION] Moving left toward boundary...")
        for x in range(width // 2, -1, -100):
            self.move_cursor(x, mid_y)
            time.sleep(0.05)

        # Cross the boundary
        print("[ACTION] Crossing left boundary...")
        self.move_cursor(0, mid_y)
        time.sleep(0.1)
        self.move_cursor(-5, mid_y)  # Force trigger
        time.sleep(0.5)

        # Check cursor position - should be repositioned to right edge
        pos = self.get_cursor_position()
        print(f"[INFO] After transition, cursor at: ({pos[0]}, {pos[1]})")
        print(f"[INFO] Expected near: ({width-1}, {mid_y})")

        # Server should have moved cursor to opposite edge
        if pos[0] >= width - 10:
            print("[PASS] Cursor repositioned to right edge ✓")
            return True
        else:
            print(f"[WARN] Cursor not at right edge: {pos[0]} (expected {width-1})")
            return False

    def test_west_to_center(self):
        """Test 3: WEST → CENTER transition"""
        print("\n" + "="*60)
        print("TEST 3: WEST → CENTER transition")
        print("="*60)

        width, height = self.get_screen_geometry()
        mid_y = height // 2

        # Assume we're in WEST mode from previous test
        print("[ACTION] Moving right from WEST...")

        # Move right in steps
        for x in range(width - 100, width, 10):
            self.move_cursor(x, mid_y)
            time.sleep(0.05)

        # Cross right boundary
        print("[ACTION] Crossing right boundary...")
        self.move_cursor(width - 1, mid_y)
        time.sleep(0.5)

        # Check cursor position - should be at left edge
        pos = self.get_cursor_position()
        print(f"[INFO] After return, cursor at: ({pos[0]}, {pos[1]})")
        print(f"[INFO] Expected near: (1, {mid_y})")

        if pos[0] <= 10:
            print("[PASS] Cursor repositioned to left edge ✓")
            return True
        else:
            print(f"[WARN] Cursor not at left edge: {pos[0]} (expected 1)")
            return False

    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*60)
        print("tx2tx Phase 7: Input Isolation Testing")
        print("="*60)

        try:
            self.setup()
            self.start_server()
            self.start_client()

            results = []

            # Run tests
            results.append(("Baseline", self.test_baseline()))
            results.append(("CENTER→WEST", self.test_center_to_west()))
            results.append(("WEST→CENTER", self.test_west_to_center()))

            # Summary
            print("\n" + "="*60)
            print("TEST SUMMARY")
            print("="*60)
            for name, passed in results:
                status = "✓ PASS" if passed else "✗ FAIL"
                print(f"{name:20} {status}")

            total = len(results)
            passed = sum(1 for _, p in results if p)
            print(f"\nTotal: {passed}/{total} tests passed")

            return all(p for _, p in results)

        finally:
            self.cleanup()


def main():
    """Main entry point"""
    harness = Harness()

    def signal_handler(sig, frame):
        print("\n[INTERRUPTED] Cleaning up...")
        harness.cleanup()
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        success = harness.run_all_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[ERROR] Test harness failed: {e}")
        import traceback
        traceback.print_exc()
        harness.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
