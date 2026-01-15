# Resumption State & Next Steps (as of 2026-01-15)

This document tracks the development plan. The section below outlines the current status to allow for asynchronous work.

## 1. Current Goal
The primary objective is to perform the first real-world, two-device test of the `tx2tx` application to validate its core functionality.

## 2. Summary of Recent Progress
- A detailed code and design gap analysis was completed. Key findings include potential mouse movement distortion between screens with different aspect ratios, incorrect key mappings if keyboard layouts differ, and a lack of encryption.
- A critical `IndentationError` was found in `tx2tx/server/main.py` which prevented the server from starting.
- This indentation bug has been **fixed, committed, and pushed** to the `main` branch.

## 3. Current Blocker: Cursor Transition & Hiding Failures
Despite significant refactoring, the core user experience of moving the mouse between screens is broken in the current test environment (Debian Trixie/Crostini).

### Symptoms
1.  **Wrong Edge on Entry:** When the server mouse crosses the West edge (to enter the West client), the Client cursor appears on the **West** (far left) edge of the client screen instead of the expected **East** (right) edge.
    *   *Implication:* The server is sending `x=0.0` (Left) coordinates to the client initially, implying the server's hidden cursor was not successfully warped to the Right edge before polling occurred.

2.  **Stuck on Return:** When returning from the Client to the Server, the Server mouse cursor remains stuck on the **East** edge of the server screen.
    *   *Implication:* The return logic (Ungrab -> Warp to Left) is failing or being overridden by the Window Manager, causing the cursor to revert to its exit position (Right edge).

3.  **Cursor Hiding Failure:** The server mouse cursor remains visible on the server screen even when it is supposed to be hidden (in Client context).
    *   *Details:* Both the "Blank Pixmap" hack (failed with `BadMatch`) and the `XFixes` extension (implemented but apparently ineffective) have failed to hide the cursor.

### Attempted Fixes (Failed)
1.  **Reordering Operations:** changed transition logic to `Warp -> Reset Velocity -> Grab -> Hide` to ensure the WM processes the move before input locking.
2.  **Return Logic:** Changed return logic to `Ungrab -> Warp -> Reset Velocity -> Show` to ensure the desktop regains control before the cursor is moved.
3.  **Velocity Spike Prevention:** Added `PointerTracker.reset()` to clear velocity history after warps, preventing "ping-pong" loops where the warp itself triggers a return transition.
4.  **XFixes Integration:** Refactored `display.py` to use `XFixes.hide_cursor` as the primary method, falling back to blank cursor.

### Hypotheses for Root Cause
- **Window Manager Interference:** The specific Window Manager (or Compositor) in the test environment may be ignoring `XWarpPointer` commands when the pointer is grabbed, or immediately reverting them upon ungrab.
- **XWayland/Crostini Limitations:** Even if running in a nested X server (Xephyr), the underlying interaction with the host (ChromeOS/Wayland) might be introducing lag or coordinate normalization issues.
- **Race Conditions:** The X server is asynchronous. Even with `display.sync()`, the "Warp" event might be processed *after* the "Poll" event in the next loop iteration, causing one frame of bad data (`x=0`) to be sent to the client.

## 4. Next Action Plan
1.  **Isolate the Environment:** Verify if these issues persist in a pure, native X11 environment (outside of Crostini/Xephyr) if possible, to rule out virtualization artifacts.
2.  **Debug Event Loop:** Add millisecond-level logging to the server loop to trace exactly *when* the coordinates change relative to the Warp command.
3.  **Alternative Hiding:** If XFixes fails, investigate if the application is running on a specific window vs root window, and ensure the hide command targets the correct window.
4.  **Review Coordinates:** Dump the raw `normalized_x` values sent to the client to confirm if it's sending `0.0` or `1.0`.

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
