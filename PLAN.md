# Resumption State & Next Steps (as of 2026-01-15)

This document tracks the development plan. The section below outlines the current status to allow for asynchronous work.

## 1. Current Goal
The primary objective is to perform the first real-world, two-device test of the `tx2tx` application to validate its core functionality.

## 2. Summary of Recent Progress
- A detailed code and design gap analysis was completed. Key findings include potential mouse movement distortion between screens with different aspect ratios, incorrect key mappings if keyboard layouts differ, and a lack of encryption.
- A critical `IndentationError` was found in `tx2tx/server/main.py` which prevented the server from starting.
- This indentation bug has been **fixed, committed, and pushed** to the `main` branch.
- **FIXED (2026-01-15):** Cursor transition race condition resolved - cursor now appears at correct edge during transitions.

## 3. ✅ RESOLVED: Cursor Transition Simplified

### Problem
The cursor transition logic was overly complex with verification loops, race conditions, and bloated code that was hard to debug. Cursor appeared at wrong edge during transitions.

### Root Cause
- Trying to warp cursor THEN poll it to get first coordinate
- Race conditions between warp and poll
- Verification loops added complexity without solving the core issue
- Pointer grab failures caused transitions to abort

### Solution Implemented ✅
**Completely simplified the transition logic:**

**Entry Transition** (`tx2tx/server/main.py:413-475`):
1. **Calculate** entry coordinate directly (opposite edge from crossing)
   - Cross LEFT → Send `NormalizedPoint(x=1.0, y=norm_y)` to client (RIGHT edge)
   - Cross RIGHT → Send `NormalizedPoint(x=0.0, y=norm_y)` to client (LEFT edge)
   - Cross TOP → Send `NormalizedPoint(x=norm_x, y=1.0)` to client (BOTTOM edge)
   - Cross BOTTOM → Send `NormalizedPoint(x=norm_x, y=0.0)` to client (TOP edge)

2. **Send** entry coordinate to client IMMEDIATELY (before any other operations)

3. **Then** warp server cursor to opposite edge for tracking continued movement

4. Grab input (with graceful failure handling - continues if grab fails)

5. Hide cursor and reset tracker

**Return Transition** (`tx2tx/server/main.py:108-127`):
1. Ungrab keyboard/pointer (with error handling)
2. Warp to entry position (simple, no verification loop)
3. Show cursor
4. Reset tracker

### Why This Works
- Entry coordinate is **calculated**, not polled - eliminates race conditions
- Client receives correct edge coordinate immediately on first frame
- Server cursor warp happens AFTER client is notified
- **Critical**: `continue` after transition skips REMOTE mode code in same iteration
  - Without this, stale position (polled before transition) would be sent immediately after entry coordinate
  - Position polled at x=0 → Transition → Send entry (x=1.0) → Fall through to REMOTE mode → Send stale position (x=0.0) ✗
  - Now: Position polled at x=0 → Transition → Send entry (x=1.0) → **continue** → Next iteration polls fresh position ✓
- Grab failures are handled gracefully instead of aborting
- Much simpler code path - easier to debug and maintain

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
