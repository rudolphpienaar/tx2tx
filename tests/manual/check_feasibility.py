#!/usr/bin/env python3
"""
Quick feasibility test for tx2tx in termux-x11
Tests if we can:
1. Connect to X11
2. Query pointer position (for boundary detection)
3. Use XTest extension (for event injection)
"""

import sys

try:
    from Xlib import X, display
    from Xlib.ext import xtest
except ImportError:
    print("❌ ERROR: python-xlib not installed")
    print("Install with: pkg install python-xlib")
    sys.exit(1)


def test_x11_connection():
    """Test if we can connect to X11"""
    try:
        d = display.Display()
        print("✅ X11 connection successful")
        print(f"   Display: {d.get_display_name()}")
        screen = d.screen()
        root = screen.root
        geom = root.get_geometry()
        print(f"   Screen size: {geom.width}x{geom.height}")
        return d
    except Exception as e:
        print(f"❌ Cannot connect to X11: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_pointer_query(d):
    """Test if we can query pointer position"""
    try:
        screen = d.screen()
        root = screen.root
        geom = root.get_geometry()
        pointer = root.query_pointer()
        print("✅ Pointer query works")
        print(f"   Current position: ({pointer.root_x}, {pointer.root_y})")
        print(f"   Screen boundaries: 0-{geom.width}, 0-{geom.height}")
        return True
    except Exception as e:
        print(f"❌ Pointer query failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_xtest_extension(d):
    """Test if XTest extension is available"""
    try:
        # Check if extension exists
        ext_info = d.query_extension("XTEST")
        if not ext_info:
            print("❌ XTest extension not available")
            return False

        print("✅ XTest extension available")

        # Try to get the version
        try:
            version = d.xtest_query_version()
            print(f"   Version: {version.major_version}.{version.minor_version}")
        except Exception:
            print("   (version query not supported, but extension exists)")

        # Test if we can fake a tiny mouse movement (won't be noticeable)
        screen = d.screen()
        root = screen.root
        pointer = root.query_pointer()
        current_x, current_y = pointer.root_x, pointer.root_y

        # Move mouse 0 pixels (should be safe)
        xtest.fake_input(d, X.MotionNotify, detail=0, x=current_x, y=current_y)
        d.sync()

        print("✅ XTest event injection works!")
        print("   (tested with no-op motion event)")

        return True

    except Exception as e:
        print(f"❌ XTest test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_xinput2_extension(d):
    """Test if XInput2 is available (optional, nice to have)"""
    try:
        ext_info = d.query_extension("XInputExtension")
        if ext_info:
            print("✅ XInput2 extension available (bonus!)")
            return True
        else:
            print("ℹ️  XInput2 not available (not critical)")
            return False
    except Exception as e:
        print(f"ℹ️  XInput2 check failed (not critical): {e}")
        return False


def main():
    print("=" * 60)
    print("tx2tx Feasibility Test for termux-x11")
    print("=" * 60)
    print()

    # Test 1: X11 Connection
    print("Test 1: X11 Connection")
    print("-" * 40)
    d = test_x11_connection()
    if not d:
        print("\n❌ FATAL: Cannot connect to X11")
        print("Make sure DISPLAY is set and termux-x11 is running")
        return False
    print()

    # Test 2: Pointer Query
    print("Test 2: Pointer Position Query")
    print("-" * 40)
    pointer_ok = test_pointer_query(d)
    print()

    # Test 3: XTest Extension (CRITICAL)
    print("Test 3: XTest Extension (CRITICAL for injection)")
    print("-" * 40)
    xtest_ok = test_xtest_extension(d)
    print()

    # Test 4: XInput2 (optional)
    print("Test 4: XInput2 Extension (optional)")
    print("-" * 40)
    test_xinput2_extension(d)
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if xtest_ok and pointer_ok:
        print("✅ tx2tx is FEASIBLE in termux-x11!")
        print()
        print("You have everything needed:")
        print("  • Pointer position tracking (for boundary detection)")
        print("  • XTest extension (for event injection)")
        print()
        print("Implementation approach:")
        print("  1. Poll cursor position with XQueryPointer")
        print("  2. Detect when cursor crosses screen boundary")
        print("  3. Send coordinates to remote tx2tx instance")
        print("  4. Remote instance uses XTest to inject events")
        return True
    else:
        print("❌ tx2tx may NOT be feasible")
        if not pointer_ok:
            print("  • Cannot query pointer position")
        if not xtest_ok:
            print("  • Cannot inject events via XTest")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
