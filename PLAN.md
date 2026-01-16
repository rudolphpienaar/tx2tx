# Resumption State & Next Steps (as of 2026-01-16)

This document tracks the development plan. The section below outlines the current status to allow for asynchronous work.

## 1. CURRENT ISSUES UNDER INVESTIGATION

**Version:** 2.2.2

### Issue A: Cursor Warp - Visual vs Internal Position Mismatch 🔄

**Problem Description:**
When boundary is crossed, `warp_pointer()` updates X server's **internal** position (verified via `query_pointer()`), but the **visual** cursor does not move. This is a compositor/X server disconnect.

**Evidence from logs:**
```
[WARP] Warping cursor from (0, 258) to (1917, 258)
[X11] Calling root.warp_pointer(1917, 258)
[X11] After warp: actual position = (1917, 258)  ← X server says it worked!
```
But user reports cursor visually stays at left edge.

**Current Fix Attempt (commit a0abe93):**
- Switched from `warp_pointer()` to **XTest `fake_input(MotionNotify)`**
- XTest synthesizes actual mouse movement events that go through the input pipeline
- Compositors typically respect XTest events because they look like real user input
- New method: `cursorPosition_setViaXTest()` in `tx2tx/x11/display.py`

**Status:** 🔄 TESTING - Need to verify if XTest approach works visually

### Issue B: Mouse Events Not Reaching Client (REGRESSION) 🔄

**Problem Description:**
After transitioning to REMOTE context, mouse cursor movement wasn't happening on the client. This was a regression introduced in commit `c0f8fbd` (mouse transmission optimization).

**Root Cause:**
The optimization added `positionChanged_check()` which compares current position to `last_sent_position`. However, `last_sent_position` wasn't being reset when entering REMOTE context, potentially causing the first position to be skipped.

**Fix Applied (commit a0abe93):**
```python
# In transition code (tx2tx/server/main.py:450)
server_state.last_sent_position = None  # Ensure first position in new context is sent
```

**Status:** 🔄 TESTING - Added INFO-level `[MOUSE]` logging to verify events are being sent

### Issue C: Cursor Hiding → Gray X Cursor Fallback ✅

**Problem Description:**
True cursor hiding fails in Crostini because the visual cursor is rendered by ChromeOS compositor, not X11. Both XFixes and blank pixmap methods fail.

**Solution Implemented (commit 009e8ac):**
Added a 3-tier fallback in `cursor_hide()`:
1. XFixes `hide_cursor` (true invisibility) - fails in Crostini
2. Blank pixmap cursor (transparent) - fails in Crostini
3. **Gray X cursor from cursor font** - WORKS as visible indicator

The gray X cursor uses the standard X11 cursor font (`cursor`) which is universally supported. When in remote mode, instead of an invisible cursor, the user sees a distinct gray X shape.

**Status:** ✅ IMPLEMENTED - Acceptable UX compromise

## 2. Debug Logging Available

**Run with INFO level** to see:
- `[TRANSITION] Boundary crossed: ...` - boundary detection
- `[WARP] Warping cursor from ... to ...` - warp attempt
- `[MOUSE] Sending pos (x, y) to client_name` - **NEW** mouse event sending
- `[BOUNDARY] Returning from CONTEXT at (x, y)` - return detection

**Run with DEBUG level** for additional:
- `[X11] XTest fake_input MotionNotify to (x, y)` - XTest warp call
- `[X11] After XTest move: actual position = (x, y)` - position verification

## 3. Summary of Recent Progress

### Session 2026-01-16
- **FIX:** Use XTest `fake_input(MotionNotify)` instead of `warp_pointer()` for cursor warps
- **FIX:** Reset `last_sent_position` when entering REMOTE context
- **DEBUG:** Added INFO-level `[MOUSE]` logging for mouse event sending
- **FEAT:** Gray X cursor fallback when cursor hiding fails (Crostini compatibility)
- **FEAT:** Configurable panic key via config.yml (default: Scroll Lock, supports combos like Ctrl+Shift+Escape)

### Session 2026-01-15
- **REFACTOR:** Created ServerState singleton class with RPN naming convention
- **OPTIMIZE:** Mouse coordinates only transmitted when position changes
- **FEATURE:** Added version + commit hash to all log output
- **DEBUG:** Added extensive logging to trace cursor warp operations
- **FIX ATTEMPT:** Moved warp before pointer grab - did not resolve visual issue

## 4. Architecture Context

**How Cursor Transition SHOULD Work:**
1. User moves mouse to LEFT edge (x=0) on server display
2. Server detects boundary crossing
3. **Server warps cursor to RIGHT edge (x=1917)** ← THIS IS FAILING
4. Server grabs pointer/keyboard (desktop stops receiving input)
5. Server polls cursor position (should be x=1917)
6. Server normalizes (1917/1920 = 0.998) and sends to client
7. Client cursor appears at RIGHT edge (98% across screen) ✓

**Current broken behavior:**
1. User moves to x=0
2. Server tries to warp to x=1917
3. **Warp doesn't happen** - cursor stays at x=0
4. Server polls position → x=0
5. Server normalizes (0/1920 = 0.0) and sends to client
6. Client cursor appears at LEFT edge (wrong!) ✗

**Critical files:**
- `tx2tx/server/main.py:426-462` - Entry transition logic
- `tx2tx/x11/display.py:179-202` - X11 warp implementation
- `tx2tx/server/state.py` - ServerState singleton

## 5. Previous Implementation History (For Context)

### Problem
The cursor transition logic was overly complex with verification loops, race conditions, and bloated code that was hard to debug. Cursor appeared at wrong edge during transitions.

### Root Cause
- Trying to warp cursor THEN poll it to get first coordinate
- Race conditions between warp and poll
- Verification loops added complexity without solving the core issue
- Pointer grab failures caused transitions to abort

### Solution Implemented ✅
**Added boundary_crossed state flag to force cursor position verification:**

**Entry Transition** (`tx2tx/server/main.py:418-459`):
1. Calculate target warp position (opposite edge from crossing)
2. **Set `boundary_crossed = True`** with target warp position
3. Change context to REMOTE
4. Grab input and hide cursor
5. Continue to next iteration (REMOTE mode will handle warp)

**REMOTE Mode with Warp Verification** (`tx2tx/server/main.py:478-498`):
1. **Check `boundary_crossed` flag** at start of REMOTE mode
2. If True:
   - Warp cursor to target position
   - **Re-poll actual position** to verify warp succeeded
   - If position matches target (within 10px tolerance):
     - Clear `boundary_crossed` flag
     - Use fresh position
     - Continue with normal coordinate sending
   - If position doesn't match:
     - **Skip this iteration** (retry warp next time)
     - Log warning
3. Only send coordinates once `boundary_crossed = False`

**Return Transition** (`tx2tx/server/main.py:108-127`):
1. Ungrab keyboard/pointer (with error handling)
2. Warp to entry position (simple, no verification loop)
3. Show cursor
4. Reset tracker

### Why This Works
- **State flag approach**: Instead of trying to warp and immediately use the position, we set a flag and defer the warp
- **Verification loop**: Each iteration checks if cursor is actually at target position before sending coordinates
- **Retry mechanism**: If warp hasn't taken effect yet, skip that iteration and try again next time (20ms later)
- **No race conditions**: Never send coordinates until cursor position is verified
- **Self-healing**: If warp fails initially, it keeps retrying automatically until it succeeds
- Grab failures are handled gracefully instead of aborting
- Simple state machine: `boundary_crossed` flag controls when to warp vs when to send coordinates

### ServerState Singleton (`tx2tx/server/state.py`)
**Clean state management using singleton pattern with RPN naming:**

```python
class ServerState:
    context: ScreenContext              # Current screen context (CENTER/WEST/EAST/etc)
    last_center_switch_time: float      # Timestamp of last CENTER transition
    boundary_crossed: bool              # Flag indicating pending warp
    target_warp_position: Position      # Target position for pending warp
    last_sent_position: Position        # Last position sent to client (for change detection)

    def boundaryCrossed_set(position)   # Set flag and target position
    def boundaryCrossed_clear()         # Clear flag after successful warp
    def positionChanged_check(pos)      # Check if position changed since last sent
    def lastSentPosition_update(pos)    # Update last sent position
    def reset()                         # Reset all state to initial values
```

**Benefits:**
- Single source of truth for server state
- Clean API with RPN naming convention (`objectName_verb()`)
- No more mutable list references (`context_ref[0]`)
- Easy to extend with additional state
- Better type safety and IDE support

### Mouse Coordinate Optimization
**Only send coordinates when position changes:**

**Before:**
- Server sent mouse coordinates every 20ms regardless of movement
- 50 messages/second even when mouse stationary
- Unnecessary network and CPU usage

**After:**
- `positionChanged_check()` compares current position to last sent
- Only transmit when position changes by at least 1 pixel
- Dramatically reduces network traffic when mouse is stationary
- Button/key events still sent immediately regardless of position

### Remaining Issue (Issue #3)
**Cursor Hiding Failure:** The server mouse cursor may remain visible on the server screen even when it is supposed to be hidden (in Client context).
    *   *Details:* Both the "Blank Pixmap" hack (failed with `BadMatch`) and the `XFixes` extension (implemented but apparently ineffective) have failed to hide the cursor in certain environments.
    *   *Status:* This is an environment-specific issue and does not prevent core functionality. The cursor transitions now work correctly.

## 6. Next Action Plan
1.  **Test the Fix:** Perform real-world two-device test to verify cursor transitions work correctly at all edges (West, East, North, South)
2.  **Alternative Cursor Hiding (Optional):** If cursor hiding continues to fail in test environment, investigate compositor-specific hiding methods or accept visible cursor as known limitation
3.  **Multi-Client Testing:** Test with multiple clients in different positions
4.  **Performance Tuning:** Optimize polling intervals and verify low latency

---
---

# tx2tx Implementation Plan

## INVARIANT: Architectural Overview

### Core Principle: Server-Authoritative Dumb Terminal Model

**Server is ground truth:**
- Server maintains all state (ScreenContext, cursor visibility, transitions)
- Server detects ALL transitions (both directions) using its own screen edges
- Server sends normalized coordinates (0.0-1.0) to clients
- Clients are dumb terminals that only react when server sends data

**Why this works:**
- Hidden server cursor moves across the server screen while controlling remote client.
- **Center -> Remote:** Server detects cursor crossing outer edge (e.g., Left edge -> West Client).
- **Remote -> Center:** Server detects hidden cursor crossing inner edge (e.g., Right edge while in West Context -> Back to Center).
- No client-side state tracking, boundary detection, or decision making.
- No client geometry needed on server (normalized coordinates handle arbitrary resolutions).

**CRITICAL: Input Isolation During REMOTE Mode**

When context != CENTER, server must prevent desktop environment from seeing input events:
- **Pointer grab:** Capture mouse button clicks (prevent server desktop from reacting to clicks)
- **Keyboard grab:** Capture keyboard events (prevent typing/commands on server desktop)
- Server reads events from X11 event queue and forwards to client
- Server desktop environment sees NO events during REMOTE mode
- On return to CENTER: ungrab both, restore normal desktop interaction

### State Machine

#### Enums

```python
class ScreenContext(Enum):
    """Global context - which screen has active control"""
    CENTER = "center"  # Server (TX2TX) has control, cursor SHOWN
    WEST = "west"      # Client at west position has control, cursor HIDDEN
    EAST = "east"      # Client at east position has control, cursor HIDDEN
    NORTH = "north"    # Client at north position has control, cursor HIDDEN
    SOUTH = "south"    # Client at south position has control, cursor HIDDEN
```

#### State Transitions

```
STATE: context=CENTER
  - Server cursor visible on physical display
  - Server polls cursor position
  - Server monitors for boundary crossings at edges

  TRANSITION: CENTER → WEST (example)
    Server detects: cursor_x <= 0 with velocity >= threshold
    1. context = WEST
    2. Grab pointer (capture mouse button events)
    3. Grab keyboard (capture keyboard events)
    4. Hide server cursor
    5. Position server cursor at x = (server_width - 1), y = current_y (Right Edge)
    6. Start sending normalized positions to WEST client

STATE: context=WEST (or EAST/NORTH/SOUTH)
  - Server cursor hidden
  - Pointer and keyboard grabbed (server desktop sees NO input)
  - User moves mouse on server surface
  - Server continuously:
    - Polls hidden cursor position
    - Normalizes: norm_x = cursor_x / server_width
    - Sends normalized events to client
    - Checks for RETURN condition (e.g., hitting Right Edge while in WEST context)
  
  TRANSITION: WEST → CENTER (example)
    Server detects: cursor_x >= (server_width - 1) (Right Edge of Server)
    1. context = CENTER
    2. Send (-1, -1) to client (hide cursor signal)
    3. Position server cursor at x = 1, y = current_y (Left Edge)
    4. Show server cursor
    5. Ungrab keyboard/pointer
```

### Configuration

```yaml
server:
  name: "TX2TX"
  host: "0.0.0.0"
  port: 24800
  edge_threshold: 0
  velocity_threshold: 100
  poll_interval_ms: 20

clients:
  - name: "phomux"
    position: west
  - name: "tablet"
    position: east

logging:
  level: "INFO"
```

### Protocol

**Server → Client messages:**
```python
# Normal mouse movement (during context != CENTER)
MOUSE_MOVE(norm_x: float, norm_y: float)

# Hide cursor signal (transitioning back to CENTER)
MOUSE_MOVE(norm_x: -1.0, norm_y: -1.0)  # Special code

# Keyboard events
KEY_EVENT(...)
```

**Client → Server messages:**
- Handshake only (capabilities/screen info).
- NO control logic messages (e.g., SCREEN_ENTER is deprecated).

---

## CURRENT WORK: Implementation Roadmap

### ✅ Phase 1: Input Isolation (Completed)
- Pointer/Keyboard grabbing on server.
- Cursor hiding.

### ✅ Phase 2: Core State Machine (Completed)
- `ScreenContext` enum.
- Normalized coordinates.

### ✅ Phase 3: Server-Authoritative Return Logic (Completed)
- "Remote -> Center" transitions implemented purely on Server.
- Removed reliance on client messages for return transitions.

### ✅ Phase 4: Client Dumb Terminal (Completed)
- Client is purely reactive.
- Removed boundary detection and control logic from client.

### ✅ Phase 5: Event Forwarding (Completed)
- Mouse button events (clicks) forwarded to client.
- Keyboard events forwarded to client.
- Client denormalizes coordinates for all mouse events.

### ✅ Phase 6: Multi-Directional Support (Completed)
- Multi-client routing implemented.
- Messages routed only to the active client based on context.
- Handshake includes client name for identification.

### Phase 7: Performance Optimization (Next)
- Tune polling intervals.
- Minimize latency.

### Phase 8: Integration Testing
- Comprehensive multi-client simulation.
- Verify event forwarding under load.
