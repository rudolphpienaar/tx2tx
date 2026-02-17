# Resumption State & Next Steps (as of 2026-01-16)

IMPORTANT: This file is legacy and partially stale.
Authoritative rewrite planning now lives in:
- `docs/rewrite_plan.adoc`
- `docs/rewrite_status.adoc`

This document tracks the development plan. The section below outlines the current status to allow for asynchronous work.

## 1. CURRENT ISSUES UNDER INVESTIGATION

**Version:** 2.2.5 (Verified Fixes)

### Issue A: Cursor Warp - Visual vs Internal Position Mismatch ⛔ UNFIXABLE
**Status:** ⛔ PERMANENT LIMITATION - Cannot be fixed from within X11 on Crostini.
**Workaround:** Accept that cursor visually jumps or use the Overlay Window workaround.

### Issue B: Mouse Events Not Reaching Client (REGRESSION) ✅ FIXED
**Status:** ✅ FIXED - `last_sent_position` reset logic implemented.

### Issue C: Cursor Appearance in Remote Mode
**Status:** ✅ MITIGATED via Overlay Window
- **Root Window Cursor:** Ignored by compositor.
- **Stippled Overlay:** ⛔ FAILED/UNSAFE. Causes X11 session freeze (verified).
- **Fullscreen Overlay:** ✅ IMPLEMENTED. Uses a transparent input-only window (or nearly transparent) to display the "Remote Mode" cursor. This is working.

## 2. Code Analysis Verification (2026-01-16)
A deep scan of the codebase confirmed that the critical logic issues identified in previous analysis have been **FIXED** in the current codebase:
- **Direction Mapping:** Logic correctly maps LEFT/RIGHT/TOP/BOTTOM to WEST/EAST/NORTH/SOUTH contexts.
- **Warp Positioning:** Cursor warps to the correct opposite edge based on direction.
- **Return Logic:** Return conditions check the correct edges based on context.
- **Entry Positioning:** Entry position is calculated correctly based on previous context.
- **Safety:** Error handling ensures `ungrab` happens if transitions fail.

## 3. Architecture Context

**How Cursor Transition Works:**
1. **Detection:** Server detects boundary crossing (e.g., Left Edge).
2. **Warp:** Server warps cursor to opposite edge (e.g., Right Edge) using `XTest` or `warp_pointer`.
3. **State Change:** Context updates to `WEST`.
4. **Grab:** Server grabs pointer/keyboard to isolate input.
5. **Overlay:** Server shows cursor overlay window to indicate "Remote Mode".
6. **Transmission:** Server sends normalized coordinates to client.

**Return to Center:**
1. **Detection:** Server detects cursor hitting the "internal" return edge (e.g., Right Edge while in WEST context).
2. **Ungrab:** Server releases pointer/keyboard.
3. **Hide Overlay:** Server hides cursor overlay.
4. **State Change:** Context updates to `CENTER`.
5. **Warp:** Server warps cursor to entry position (Left Edge).

## 4. Next Action Plan

1.  **Integration Verification:**
    - Run `tests/integration/test_simple.py` to verify basic loop functionality and ensure no regressions.
    - Validate that the server starts and handles connections correctly.

2.  **Multi-Client Simulation:**
    - Verify that `tests/integration/test_detailed.py` (or similar) can simulate multiple clients.
    - Ensure routing logic sends events only to the active client.

3.  **Performance Tuning:**
    - Optimize `poll_interval_ms` and `velocity_threshold` based on testing feedback.

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

### ✅ Phase 7: Performance Optimization (Completed)
- Tuned polling intervals.
- Minimized latency.
- Verified cursor transitions and warp logic.
- Fixed Split Brain X11 issue in test harness.
- Fixed Client Name propagation bug.

### Phase 8: Integration Testing (Next)
- Comprehensive multi-client simulation.
- Verify event forwarding under load.
