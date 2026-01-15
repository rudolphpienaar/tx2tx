# Resumption State & Next Steps (as of 2026-01-15)

This document tracks the development plan. The section below outlines the current status to allow for asynchronous work.

## 1. CURRENT BLOCKER: Cursor Warp Not Working ❌

**Version:** 2.1.4 (pending commit)

### Problem Description
When boundary is crossed (e.g., cursor moves from x=0 LEFT edge), the cursor should visually jump to the opposite edge (x=1917 RIGHT edge). **The cursor NEVER warps.** It stays at x=0 and client receives wrong coordinates.

**Cursor hiding does NOT work** - user always sees cursor on server screen, so warp should be visually observable.

### What We've Tried (All Failed)
1. ❌ Verification loops after warp - no effect
2. ❌ Deferred warp with `boundary_crossed` flag - no effect
3. ❌ Warp BEFORE grabbing pointer (thought grab prevented warp) - no effect
4. ❌ Added 10ms delay after warp - no effect
5. ❌ Multiple sync() calls - no effect

### Current State of Code
**Entry Transition** (`tx2tx/server/main.py:426-462`):
```python
# Detect boundary crossing at x=0 (LEFT edge)
warp_pos = Position(x=screen_geometry.width - 3, y=transition.position.y)  # x=1917

# Warp cursor BEFORE grab
logger.info(f"[WARP] Warping cursor from ({transition.position.x}, {transition.position.y}) to ({warp_pos.x}, {warp_pos.y})")
display_manager.cursorPosition_set(warp_pos)
time.sleep(0.01)  # 10ms delay

# Then grab pointer/keyboard
display_manager.pointer_grab()
display_manager.keyboard_grab()
```

**X11 Warp Implementation** (`tx2tx/x11/display.py:179-202`):
```python
def cursorPosition_set(self, position: Position) -> None:
    display = self.display_get()
    root = screen.root

    logger.debug(f"[X11] Calling root.warp_pointer({position.x}, {position.y})")
    root.warp_pointer(position.x, position.y)
    display.sync()
    logger.debug(f"[X11] display.sync() completed")

    # Verify immediately
    pointer_data = root.query_pointer()
    actual_x = pointer_data.root_x
    actual_y = pointer_data.root_y
    logger.debug(f"[X11] After warp: actual position = ({actual_x}, {actual_y})")
```

### Debug Logging In Place
**Run with DEBUG logging enabled**, logs will show:
1. `[TRANSITION] Boundary crossed: pos=(0,y)` - boundary detection
2. `[WARP] Warping cursor from (0, y) to (1917, y)` - warp attempt
3. `[X11] Calling root.warp_pointer(1917, y)` - X11 call
4. `[X11] display.sync() completed` - sync completion
5. `[X11] After warp: actual position = (?, ?)` - **CRITICAL: Check this value**

### Next Steps for Debugging
1. **Run test and examine logs** - specifically the `[X11] After warp: actual position = (?, ?)` line
2. **If actual position != target**: X server is ignoring `warp_pointer()` call
   - May be compositor/window manager blocking warps
   - May be security policy in Crostini/Xephyr
   - May need to use different X11 API or XTest extension
3. **If actual position == target but cursor doesn't MOVE visually**: Display refresh issue
4. **If logs don't appear**: `cursorPosition_set()` is not being called at all

### Hypotheses
- **Most likely**: X server/compositor is blocking `XWarpPointer` calls for security/UX reasons
- Window manager may have "no mouse warping" policy
- Xephyr/Crostini may sandbox/filter warp commands
- May need alternative approach: XTest extension, or change architecture to not rely on warping

## 2. Summary of Recent Progress (Last Session)
- **REFACTOR (2026-01-15):** Created ServerState singleton class (`tx2tx/server/state.py`) with RPN naming convention (`boundaryCrossed_set()`, `boundaryCrossed_clear()`)
- **OPTIMIZE (2026-01-15):** Mouse coordinates only transmitted when position changes (saves bandwidth when stationary)
- **FEATURE (2026-01-15):** Added version + commit hash to all log output (e.g., `[v2.1.3.1eea]`)
- **DEBUG (2026-01-15):** Added extensive logging to trace cursor warp operations
- **FIX ATTEMPT (2026-01-15):** Moved warp before pointer grab - did not resolve issue

## 3. Architecture Context

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

## 4. Previous Implementation History (For Context)

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

## 4. Next Action Plan
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
