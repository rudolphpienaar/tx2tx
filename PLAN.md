# tx2tx Implementation Plan

## INVARIANT: Architectural Overview

### Core Principle: Server-Authoritative Dumb Terminal Model

**Server is ground truth:**
- Server maintains all state (ScreenContext, cursor visibility, transitions)
- Server detects ALL transitions (both directions) using its own screen edges
- Server sends normalized coordinates (0.0-1.0) to clients
- Clients are dumb terminals that only react when server sends data

**Why this works:**
- Hidden server cursor has full range of motion (~2959px travel on 2960px screen)
- Server detects LEFT edge crossing → transition to WEST client
- Server detects (would-be) RIGHT edge crossing of hidden cursor → transition back to CENTER
- No client-side state tracking, boundary detection, or decision making
- No client geometry needed on server (normalized coordinates handle arbitrary resolutions)

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

**Server state:**
- `context: ScreenContext` - Single global state variable
- Cursor visibility is deterministic: `CENTER` → SHOWN, any other → HIDDEN

**Client state:**
- None. Clients are stateless, only react to server commands

#### State Transitions

```
STATE: context=CENTER
  - Server cursor visible on physical display
  - User controls server screen normally
  - Server polls cursor position
  - Server does NOT send anything to clients
  - Server monitors for boundary crossings at edges

  TRANSITION: CENTER → WEST (example)
    Server detects: cursor_x <= 0 with velocity >= threshold
    1. context = WEST
    2. Grab pointer (capture mouse button events)
    3. Grab keyboard (capture keyboard events)
    4. Hide server cursor
    5. Position server cursor at x = (server_width - 1), y = current_y
    6. Start sending normalized positions to WEST client

STATE: context=WEST (or EAST/NORTH/SOUTH)
  - Server cursor hidden, positioned away from triggering edge
  - Pointer and keyboard grabbed (server desktop sees NO input)
  - User sees and controls client cursor
  - Server continuously:
    - Polls hidden cursor position for movement
    - Reads X11 event queue for button/keyboard events
    - Normalizes all input: norm_x = cursor_x / server_width, norm_y = cursor_y / server_height
    - Sends normalized events to client (MOUSE_MOVE, MOUSE_BUTTON, KEY_EVENT)
  - Client receives events:
    - Calculates: actual_x = norm_x * client_width, actual_y = norm_y * client_height
    - Moves cursor, clicks buttons, types characters on client display
    - Shows cursor (if not already visible)

  TRANSITION: WEST → CENTER (example)
    Server detects: cursor_x >= (server_width - 1) with velocity >= threshold
    (This means client cursor would be hitting its right edge due to normalized coordinates)
    1. context = CENTER
    2. Send (-1, -1) to client (special code: hide cursor)
    3. Stop sending positions to client
    4. Position server cursor at x = 1, y = current_y
    5. Show server cursor
    6. Ungrab keyboard (return keyboard to desktop)
    7. Ungrab pointer (return mouse to desktop)
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

**Client naming:**
- Server CLI: `tx2tx` (always runs as "TX2TX")
- Client CLI: `tx2tx --client phomux` (reads position from config)

### Protocol

**Server → Client messages:**
```python
# Normal mouse movement (during context != CENTER)
MOUSE_MOVE(norm_x: float, norm_y: float)

# Hide cursor signal (transitioning back to CENTER)
MOUSE_MOVE(norm_x: -1.0, norm_y: -1.0)  # Special code

# Keyboard events (when implemented)
KEY_EVENT(...)
```

**Client → Server messages:**
- None required for cursor control
- (Future: handshake on connect to exchange capabilities)

### Normalized Coordinates

**Server calculation:**
```python
norm_x = cursor_x / server_geometry.width   # 0.0 to 1.0
norm_y = cursor_y / server_geometry.height  # 0.0 to 1.0
```

**Client calculation:**
```python
if norm_x == -1.0 and norm_y == -1.0:
    cursor_hide()
else:
    actual_x = int(norm_x * client_geometry.width)
    actual_y = int(norm_y * client_geometry.height)
    cursor_show()
    cursor_move(actual_x, actual_y)
```

**Why normalized coordinates:**
- Server doesn't need to know client screen resolution
- Client can change resolution without server reconfiguration
- Handles arbitrary client geometries automatically
- Clean separation of concerns

### Logging Format

**Server logging:**
```
<timestamp> | <destination> | server_x, server_y | context | <message>

Examples:
15:26 20251105 | phomux | 0, 924 | WEST | norm=(0.0000, 0.5000)
15:26 20251105 | TX2TX | 2959, 924 | WEST | hidden_cursor
15:27 20251105 | phomux | 2959, 1000 | CENTER | HIDE (-1, -1)
```

**Client logging:**
```
<timestamp> | client_name | cursor_x, cursor_y | <message>

Examples:
15:26 | phomux | 2133, 1075 | cursor_visible
15:26 | phomux | 2100, 1050 | moved
15:27 | phomux | -1, -1 | cursor_hidden
```

### What Gets Removed (Complexity)

**Server:**
- Delta calculation (`last_remote_position`, calculating `delta_x`, `delta_y`)
- Cursor warping to center during REMOTE mode
- `cursor_just_warped` flag and skip-after-warp logic
- Edge margin detection for warping (100px threshold)
- Client geometry tracking (no longer needed with normalized coords)
- SCREEN_LEAVE, SCREEN_ENTER protocol messages
- Coordinate transformation between server/client spaces

**Client:**
- `monitoring_boundaries` flag
- Boundary detection for re-entry
- SCREEN_ENTER message sending
- State tracking (REMOTE vs LOCAL mode)
- Velocity calculations
- Relative vs absolute movement distinction
- `mousePointer_moveRelative()` usage
- Special REMOTE mode handling branches

### What Stays (Simplicity)

**Server:**
- Boundary detection at ALL edges (for CENTER → WEST/EAST/NORTH/SOUTH and reverse)
- Velocity threshold check (prevents accidental transitions)
- PointerTracker for querying cursor position
- Cursor hide/show control

**Client:**
- Absolute position injection via `mousePointer_move()`
- Screen geometry tracking (for normalized coordinate conversion)
- Cursor hide/show control

---

## CURRENT WORK: Implementation Roadmap

### Overview

This implementation follows the server-authoritative dumb terminal model. The roadmap is organized into phases that can be executed sequentially with testing at each step.

### ✅ Phase 1: Implement Input Isolation (COMPLETED)

**Goal:** Implement cursor hide/show AND pointer/keyboard grab to isolate input during REMOTE mode.

**File:** `tx2tx/x11/display.py`

**Implementation - Pointer and Keyboard Grab:**
```python
def pointer_grab(self) -> None:
    """Grab pointer to capture all mouse events (prevents desktop from seeing them)"""
    display = self.display_get()
    screen = display.screen()
    root = screen.root

    result = root.grab_pointer(
        True,  # owner_events - we receive events
        X.PointerMotionMask | X.ButtonPressMask | X.ButtonReleaseMask,
        X.GrabModeAsync,
        X.GrabModeAsync,
        X.None,  # Don't confine to window
        0,       # Don't change cursor
        X.CurrentTime
    )

    if result == 0:  # GrabSuccess
        display.sync()
        logger.debug("Pointer grabbed successfully")
    else:
        raise RuntimeError(f"Failed to grab pointer: result {result}")

def pointer_ungrab(self) -> None:
    """Release pointer grab (return mouse events to desktop)"""
    display = self.display_get()
    display.ungrab_pointer(X.CurrentTime)
    display.sync()
    logger.debug("Pointer ungrabbed")

def keyboard_grab(self) -> None:
    """Grab keyboard to capture all keyboard events (prevents desktop from seeing them)"""
    display = self.display_get()
    screen = display.screen()
    root = screen.root

    result = root.grab_keyboard(
        True,  # owner_events - we receive events
        X.GrabModeAsync,
        X.GrabModeAsync,
        X.CurrentTime
    )

    if result == 0:  # GrabSuccess
        display.sync()
        logger.debug("Keyboard grabbed successfully")
    else:
        raise RuntimeError(f"Failed to grab keyboard: result {result}")

def keyboard_ungrab(self) -> None:
    """Release keyboard grab (return keyboard events to desktop)"""
    display = self.display_get()
    display.ungrab_keyboard(X.CurrentTime)
    display.sync()
    logger.debug("Keyboard ungrabbed")
```

**Implementation - Cursor Hiding:**
```python
def cursor_hide(self) -> None:
    """Hide cursor using XFixes extension with pixmap fallback"""
    if self._cursor_hidden:
        return
        
    display = self.display_get()
    screen = display.screen()
    root = screen.root
    
    # Try XFixes first (modern, simple)
    try:
        if display.has_extension('XFIXES') or display.query_extension('XFIXES'):
            root.xfixes_hide_cursor()
            display.sync()
            self._cursor_hidden = True
            return
    except (AttributeError, Exception):
        pass
    
    # Fallback: Create invisible pixmap cursor
    pixmap = root.create_pixmap(1, 1, 1)
    gc = pixmap.create_gc(foreground=0, background=0)
    pixmap.fill_rectangle(gc, 0, 0, 1, 1)
    
    invisible_cursor = pixmap.create_cursor(
        pixmap, (0, 0, 0), (0, 0, 0), 0, 0
    )
    root.change_attributes(cursor=invisible_cursor)
    display.sync()
    
    self._blank_cursor = invisible_cursor
    self._cursor_hidden = True

def cursor_show(self) -> None:
    """Show cursor"""
    if not self._cursor_hidden:
        return
        
    display = self.display_get()
    screen = display.screen()
    root = screen.root
    
    # Try XFixes first
    try:
        if display.has_extension('XFIXES') or display.query_extension('XFIXES'):
            root.xfixes_show_cursor()
            display.sync()
            self._cursor_hidden = False
            return
    except (AttributeError, Exception):
        pass
    
    # Fallback: Restore default cursor
    root.change_attributes(cursor=X.None)
    display.sync()
    self._cursor_hidden = False
```

**Testing:**
```python
# Test cursor hiding
display_manager.cursor_hide()
time.sleep(2)  # Cursor should be invisible
display_manager.cursor_show()
time.sleep(2)  # Cursor should be visible

# Test input grabbing
display_manager.pointer_grab()
display_manager.keyboard_grab()
# Try clicking and typing - desktop should NOT respond
time.sleep(5)
display_manager.keyboard_ungrab()
display_manager.pointer_ungrab()
# Desktop should respond again
```

**Commit:** "Implement input isolation: cursor hiding and pointer/keyboard grab"

---

### ✅ Phase 2: Add ScreenContext Enum (COMPLETED)

**Goal:** Define the new state enum.

**File:** `tx2tx/common/types.py`

**Add:**
```python
class ScreenContext(Enum):
    """Global context - which screen has active control"""
    CENTER = "center"  # Server has control, cursor shown
    WEST = "west"      # West client has control, cursor hidden
    EAST = "east"
    NORTH = "north"
    SOUTH = "south"
```

**Commit:** "Add ScreenContext enum for global state tracking"

---

### 🔄 Phase 3: Strip Out Broken Complexity (CURRENT)

**Goal:** Remove all the delta tracking, warping, and complex REMOTE mode logic.

**File:** `tx2tx/server/main.py`

**Delete these variables (around line 264):**
```python
last_remote_position = [None]
cursor_just_warped = [False]
```

**Delete entire REMOTE mode block (around lines 349-394)** and replace with:
```python
elif control_state_ref[0] == ControlState.REMOTE:
    # TODO: Will be replaced with normalized coordinate transmission
    pass
```

**Delete SCREEN_LEAVE creation logic** in LOCAL→REMOTE transition (around lines 319-331).

**Simplify to:**
```python
# Hide cursor and position away from edge
display_manager.cursor_hide()
edge_position = Position(x=screen_geometry.width - 1, y=position.y)
display_manager.cursorPosition_set(edge_position)

# Switch to remote control
control_state_ref[0] = ControlState.REMOTE
logger.info("[STATE] Switched to REMOTE control")
```

**File:** `tx2tx/client/main.py`

**Delete relative movement branch** (lines 167-174).

**Simplify mouse event handling:**
```python
elif message.msg_type == MessageType.MOUSE_EVENT:
    if injector:
        mouse_event = MessageParser.mouseEvent_parse(message)
        if mouse_event.event_type == EventType.MOUSE_MOVE:
            injector.mouseEvent_inject(mouse_event)
```

**Delete boundary detection and SCREEN_ENTER sending** (lines 309-333).

**File:** `tx2tx/x11/injector.py`

**Delete:** `mousePointer_moveRelative()` method entirely (lines 44-68).

**Verification:**
- `grep -r "last_remote_position" .` → 0 results
- `grep -r "cursor_just_warped" .` → 0 results
- `grep -r "delta_x\|delta_y" tx2tx/server/` → 0 results in server
- `grep -r "mousePointer_moveRelative" .` → 0 results
- `mypy tx2tx/` → passes

**Commit:** "Strip out delta tracking and cursor warping complexity"

---

### Phase 4: Update Configuration for Named Clients

**Goal:** Support named clients with positions in config.

**File:** `config.yml`

**Update:**
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
  # Future clients can be added here

logging:
  level: "INFO"
  format: "%(asctime)s | %(message)s"
```

**File:** `tx2tx/common/config.py`

**Add dataclasses:**
```python
@dataclass
class ClientConfig:
    name: str
    position: str  # "west", "east", "north", "south"

@dataclass
class ServerConfig:
    name: str
    host: str
    port: int
    edge_threshold: int
    velocity_threshold: float
    poll_interval_ms: int

@dataclass
class Config:
    server: ServerConfig
    clients: list[ClientConfig]
    logging: LoggingConfig
```

**File:** `tx2tx/client/main.py` and `tx2tx/server/main.py`

**Add CLI argument:**
```python
parser.add_argument(
    "--client",
    type=str,
    default=None,
    help="Client name from config (e.g., 'phomux')"
)
```

**Commit:** "Add named client configuration support"

---

### Phase 5: Implement Normalized Coordinates

**Goal:** Server sends normalized (0.0-1.0) coordinates, client scales to actual resolution.

**File:** `tx2tx/server/main.py`

**Replace REMOTE mode block with:**
```python
elif context[0] != ScreenContext.CENTER:
    # Send normalized coordinates to active client
    norm_x = position.x / screen_geometry.width
    norm_y = position.y / screen_geometry.height
    
    mouse_event = MouseEvent(
        event_type=EventType.MOUSE_MOVE,
        position=Position(x=int(norm_x * 10000), y=int(norm_y * 10000))
    )
    move_msg = MessageBuilder.mouseEventMessage_create(mouse_event)
    network.messageToAll_broadcast(move_msg)
    
    logger.debug(f"[{context[0].value.upper()}] Sent norm=({norm_x:.4f}, {norm_y:.4f})")
```

**Note:** Position currently stores integers. We encode normalized floats as integers by multiplying by 10000.

**File:** `tx2tx/client/main.py`

**Update mouse event handling:**
```python
elif message.msg_type == MessageType.MOUSE_EVENT:
    if injector:
        mouse_event = MessageParser.mouseEvent_parse(message)
        
        # Decode normalized coordinates (encoded as int * 10000)
        norm_x = mouse_event.position.x / 10000.0
        norm_y = mouse_event.position.y / 10000.0
        
        # Check for hide signal
        if norm_x < 0 or norm_y < 0:
            display_manager.cursor_hide()
            logger.info("Cursor hidden")
        else:
            # Scale to client resolution
            client_geom = display_manager.screenGeometry_get()
            actual_x = int(norm_x * client_geom.width)
            actual_y = int(norm_y * client_geom.height)
            
            # Show cursor and move
            display_manager.cursor_show()
            injector.mousePointer_move(Position(x=actual_x, y=actual_y))
            logger.debug(f"Cursor at ({actual_x}, {actual_y})")
```

**Commit:** "Implement normalized coordinate transmission"

---

### Phase 6: Implement Full State Machine

**Goal:** Complete CENTER ↔ WEST transitions with proper cursor positioning.

**File:** `tx2tx/server/main.py`

**CENTER → WEST transition:**
```python
if context[0] == ScreenContext.CENTER:
    # Detect boundary crossing
    transition = pointer_tracker.boundary_detect(position, screen_geometry)
    
    if transition and transition.direction == Direction.WEST:
        logger.info(f"[BOUNDARY] Crossed WEST edge at ({position.x}, {position.y})")
        
        # Transition to WEST context
        context[0] = ScreenContext.WEST
        
        # Hide cursor and position at opposite edge
        display_manager.cursor_hide()
        edge_pos = Position(x=screen_geometry.width - 1, y=position.y)
        display_manager.cursorPosition_set(edge_pos)
        
        logger.info(f"[STATE] → WEST, cursor hidden at ({edge_pos.x}, {edge_pos.y})")
```

**WEST → CENTER transition:**
```python
elif context[0] == ScreenContext.WEST:
    # Check if returning (cursor hits right edge)
    if position.x >= (screen_geometry.width - 1):
        velocity = pointer_tracker.velocity_calculate()
        if velocity >= config.server.velocity_threshold:
            logger.info(f"[BOUNDARY] Returning from WEST at ({position.x}, {position.y})")
            
            # Send hide signal to client
            hide_event = MouseEvent(
                event_type=EventType.MOUSE_MOVE,
                position=Position(x=-10000, y=-10000)  # -1.0 encoded
            )
            hide_msg = MessageBuilder.mouseEventMessage_create(hide_event)
            network.messageToAll_broadcast(hide_msg)
            
            # Transition to CENTER
            context[0] = ScreenContext.CENTER
            
            # Position cursor at left edge and show
            entry_pos = Position(x=1, y=position.y)
            display_manager.cursorPosition_set(entry_pos)
            display_manager.cursor_show()
            
            logger.info(f"[STATE] → CENTER, cursor shown at ({entry_pos.x}, {entry_pos.y})")
```

**Commit:** "Implement full CENTER ↔ WEST state transitions"

---

### Phase 7: Testing and Validation

**Test sequence:**
1. Start server: `tx2tx`
2. Start client: `tx2tx --client phomux`
3. Move mouse left from server, cross x=0
   - Verify: server cursor disappears
   - Verify: client cursor appears at right edge
   - Verify: client cursor follows server mouse movements
4. Move mouse right on server (controlling client), reach client right edge
   - Verify: client cursor disappears
   - Verify: server cursor reappears at left edge
5. Repeat cycle multiple times
6. Check logs match expected format

**Success criteria:**
- Smooth transitions in both directions
- No ping-pong loops
- Cursor movements responsive
- Log output clear and informative

---

### Phase 8: Future Enhancements

**After core functionality works:**
1. Add EAST, NORTH, SOUTH support (generalize edge detection)
2. Add keyboard event forwarding
3. Optimize polling interval
4. Add clipboard synchronization
5. Performance profiling and optimization

---

### Commit Strategy

Each phase should be a separate commit:
1. "Implement input isolation: cursor hiding and pointer/keyboard grab"
2. "Add ScreenContext enum for global state tracking"
3. "Strip out delta tracking and cursor warping complexity"
4. "Add named client configuration support"
5. "Implement normalized coordinate transmission"
6. "Implement full CENTER ↔ WEST state transitions with input grab/ungrab"
7. "Update documentation and tests"

