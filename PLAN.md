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

### ✅ Phase 3: Strip Out Broken Complexity (COMPLETED)

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

### ✅ Phase 4: Update Configuration for Named Clients (COMPLETED)

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

### ✅ Phase 5: Implement Normalized Coordinates (COMPLETED)

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

### ✅ Phase 6: Implement Full State Machine (COMPLETED)

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

### 🔄 Phase 7: Input Isolation Testing (CURRENT)

**Goal:** Verify that pointer/keyboard grab prevents server desktop from seeing input during REMOTE mode.

**Test sequence:**

1. **Baseline test - CENTER mode:**
   ```bash
   tx2tx
   ```
   - Move mouse on server screen → cursor should move normally
   - Click on server desktop → clicks should register
   - Type on server → keyboard input should work
   - Verify: All input works normally

2. **Start client and test transition:**
   ```bash
   # On server (TX2TX):
   tx2tx

   # On client (phomux):
   tx2tx --client phomux
   ```

3. **Test CENTER → WEST transition:**
   - Move mouse left, cross x=0 boundary
   - Verify: Server cursor disappears
   - Verify: Client cursor appears
   - Verify: Client cursor follows server mouse
   - **CRITICAL: Try clicking on server desktop while in WEST mode**
     - Expected: Server desktop should NOT react to clicks
     - Expected: Logs show "[INPUT] Grabbed pointer and keyboard"
   - **CRITICAL: Try typing while in WEST mode**
     - Expected: Server desktop should NOT see keyboard input
     - Expected: No text appears in server terminal or apps
   - Verify: Only client receives input events

4. **Test cursor movement in WEST mode:**
   - Move mouse in various patterns
   - Verify: Client cursor follows smoothly
   - Verify: Normalized coordinates work (check logs)
   - Verify: Cursor reaches all edges of client screen

5. **Test WEST → CENTER transition:**
   - Move mouse right on server (controlling client cursor)
   - Reach right edge of client screen (server cursor x = width-1)
   - Verify: Client cursor disappears
   - Verify: Server cursor reappears at left edge (x=1)
   - Verify: Logs show "[INPUT] Ungrabbed keyboard and pointer"
   - **CRITICAL: Try clicking on server desktop after return**
     - Expected: Server desktop SHOULD react normally
     - Expected: Clicks register on server apps/windows
   - **CRITICAL: Try typing after return**
     - Expected: Server desktop SHOULD receive keyboard input
     - Expected: Text appears normally in server apps

6. **Test rapid transitions:**
   - Move left (CENTER → WEST)
   - Immediately move right (WEST → CENTER)
   - Repeat 10 times rapidly
   - Verify: No ping-pong loops
   - Verify: No stuck grab state
   - Verify: Hysteresis works (200ms delay prevents immediate re-trigger)

7. **Test edge cases:**
   - Cross boundary very slowly (below velocity threshold)
     - Expected: Should NOT trigger transition
   - Cross boundary quickly
     - Expected: Should trigger transition
   - Try to click during transition
     - Expected: No crashes, clean state handling

**Success criteria:**
- ✅ Smooth transitions in both directions
- ✅ No ping-pong loops
- ✅ Server desktop ISOLATED from input during WEST mode (pointer and keyboard grabbed)
- ✅ Server desktop RECEIVES input normally in CENTER mode (pointer and keyboard ungrabbed)
- ✅ Cursor movements responsive and accurate
- ✅ Normalized coordinates work across different resolutions
- ✅ Log output clear and informative
- ✅ No crashes or stuck states

**Known issues to watch for:**
- Grab failing (check logs for "Failed to grab" errors)
- Desktop still receiving input during REMOTE mode (grab not working)
- Cursor not showing after return to CENTER (ungrab not working)
- Keyboard input leaking to server during REMOTE mode

---

### Phase 8: Mouse Button Events

**Goal:** Forward mouse button clicks to client during REMOTE mode.

**File:** `tx2tx/server/main.py`

**Implementation - Read X11 Event Queue:**

Add after pointer_tracker initialization:
```python
# X11 event reading for button events
from Xlib import X

def read_button_events(display_manager):
    """Read pending button events from X11 queue"""
    display = display_manager.display_get()

    events = []
    while display.pending_events() > 0:
        event = display.next_event()

        if event.type == X.ButtonPress:
            events.append(MouseEvent(
                event_type=EventType.MOUSE_BUTTON_PRESS,
                position=Position(x=event.root_x, y=event.root_y),
                button=event.detail  # 1=left, 2=middle, 3=right
            ))
        elif event.type == X.ButtonRelease:
            events.append(MouseEvent(
                event_type=EventType.MOUSE_BUTTON_RELEASE,
                position=Position(x=event.root_x, y=event.root_y),
                button=event.detail
            ))

    return events
```

**In main loop during REMOTE mode:**
```python
elif context_ref[0] != ScreenContext.CENTER:
    # ... existing position transmission code ...

    # Read and forward button events
    button_events = read_button_events(display_manager)
    for event in button_events:
        # Normalize position
        norm_x = event.position.x / screen_geometry.width
        norm_y = event.position.y / screen_geometry.height

        normalized_event = MouseEvent(
            event_type=event.event_type,
            position=Position(x=int(norm_x * 10000), y=int(norm_y * 10000)),
            button=event.button
        )
        msg = MessageBuilder.mouseEventMessage_create(normalized_event)
        network.messageToAll_broadcast(msg)
        logger.debug(f"[BUTTON] {event.event_type.value} button={event.button}")
```

**File:** `tx2tx/client/main.py`

**Update event handling:**
```python
elif message.msg_type == MessageType.MOUSE_EVENT:
    if injector:
        mouse_event = MessageParser.mouseEvent_parse(message)

        # Handle button events
        if mouse_event.isButtonEvent():
            # Decode normalized coordinates
            norm_x = mouse_event.position.x / 10000.0
            norm_y = mouse_event.position.y / 10000.0

            client_geom = display_manager.screenGeometry_get()
            actual_x = int(norm_x * client_geom.width)
            actual_y = int(norm_y * client_geom.height)

            # Inject button event at normalized position
            event_with_position = MouseEvent(
                event_type=mouse_event.event_type,
                position=Position(x=actual_x, y=actual_y),
                button=mouse_event.button
            )
            injector.mouseEvent_inject(event_with_position)
            logger.debug(f"[BUTTON] {mouse_event.event_type.value} at ({actual_x}, {actual_y})")

        # ... existing MOUSE_MOVE handling ...
```

**File:** `tx2tx/x11/injector.py`

**Update injection to handle buttons:**
```python
def mouseEvent_inject(self, event: MouseEvent) -> None:
    """Inject mouse event (move or button)"""
    display = self._display_manager.display_get()

    if event.event_type == EventType.MOUSE_MOVE:
        # Move cursor
        self.mousePointer_move(event.position)

    elif event.isButtonEvent():
        # First move to position
        self.mousePointer_move(event.position)

        # Then inject button event
        from Xlib.ext.xtest import fake_input
        from Xlib import X

        button_map = {1: 1, 2: 2, 3: 3}  # Left, Middle, Right
        x11_button = button_map.get(event.button, 1)

        if event.event_type == EventType.MOUSE_BUTTON_PRESS:
            fake_input(display, X.ButtonPress, x11_button)
        else:
            fake_input(display, X.ButtonRelease, x11_button)

        display.sync()
```

**Testing:**
1. Transition to WEST mode
2. Click left button while on client
   - Verify: Client registers click at cursor position
3. Try middle and right button clicks
   - Verify: All buttons work
4. Click and drag
   - Verify: Drag operations work on client

**Commit:** "Add mouse button event forwarding"

---

### Phase 9: Keyboard Event Forwarding

**Goal:** Forward keyboard events to client during REMOTE mode.

**File:** `tx2tx/server/main.py`

**Add keyboard event reading:**
```python
def read_keyboard_events(display_manager):
    """Read pending keyboard events from X11 queue"""
    display = display_manager.display_get()

    events = []
    while display.pending_events() > 0:
        event = display.next_event()

        if event.type == X.KeyPress:
            events.append(KeyEvent(
                event_type=EventType.KEY_PRESS,
                keycode=event.detail,
                keysym=display.keycode_to_keysym(event.detail, 0)
            ))
        elif event.type == X.KeyRelease:
            events.append(KeyEvent(
                event_type=EventType.KEY_RELEASE,
                keycode=event.detail,
                keysym=display.keycode_to_keysym(event.detail, 0)
            ))

    return events
```

**In main loop during REMOTE mode:**
```python
# Read and forward keyboard events
keyboard_events = read_keyboard_events(display_manager)
for event in keyboard_events:
    msg = MessageBuilder.keyEventMessage_create(event)
    network.messageToAll_broadcast(msg)
    logger.debug(f"[KEY] {event.event_type.value} keycode={event.keycode}")
```

**File:** `tx2tx/common/protocol.py`

**Add KeyEvent message builder:**
```python
@staticmethod
def keyEventMessage_create(event: KeyEvent) -> Message:
    """Create keyboard event message"""
    payload = {
        "event_type": event.event_type.value,
        "keycode": event.keycode,
        "keysym": event.keysym
    }
    return Message(
        msg_type=MessageType.KEY_EVENT,
        payload=json.dumps(payload).encode('utf-8')
    )
```

**File:** `tx2tx/client/main.py`

**Add keyboard event handling:**
```python
elif message.msg_type == MessageType.KEY_EVENT:
    if injector:
        key_event = MessageParser.keyEvent_parse(message)
        injector.keyEvent_inject(key_event)
        logger.debug(f"[KEY] Injected {key_event.event_type.value}")
```

**File:** `tx2tx/x11/injector.py`

**Add keyboard injection:**
```python
def keyEvent_inject(self, event: KeyEvent) -> None:
    """Inject keyboard event"""
    from Xlib.ext.xtest import fake_input
    from Xlib import X

    display = self._display_manager.display_get()

    if event.event_type == EventType.KEY_PRESS:
        fake_input(display, X.KeyPress, event.keycode)
    else:
        fake_input(display, X.KeyRelease, event.keycode)

    display.sync()
```

**Testing:**
1. Transition to WEST mode
2. Type on server keyboard
   - Verify: Server desktop does NOT see input (grabbed)
   - Verify: Client receives and displays keystrokes
3. Test special keys (Ctrl, Alt, Shift, Enter, Backspace)
   - Verify: Modifier keys work correctly
4. Test key combinations (Ctrl+C, Alt+Tab, etc.)
   - Verify: Combinations work on client

**Note:** Keysym mapping may differ between server and client. Future enhancement: send keysyms and have client translate to local keycodes.

**Commit:** "Add keyboard event forwarding"

---

### Phase 10: Multi-Directional Support (EAST/NORTH/SOUTH)

**Goal:** Generalize edge detection to support all four directions.

**File:** `tx2tx/server/main.py`

**Generalize transition logic:**
```python
if context_ref[0] == ScreenContext.CENTER:
    transition = pointer_tracker.boundary_detect(position, screen_geometry)

    if transition:
        # Determine which context based on direction
        direction_to_context = {
            Direction.LEFT: ScreenContext.WEST,
            Direction.RIGHT: ScreenContext.EAST,
            Direction.TOP: ScreenContext.NORTH,
            Direction.BOTTOM: ScreenContext.SOUTH
        }

        new_context = direction_to_context[transition.direction]
        context_ref[0] = new_context

        # Calculate opposite edge position
        if transition.direction == Direction.LEFT:
            edge_pos = Position(x=screen_geometry.width - 1, y=position.y)
        elif transition.direction == Direction.RIGHT:
            edge_pos = Position(x=1, y=position.y)
        elif transition.direction == Direction.TOP:
            edge_pos = Position(x=position.x, y=screen_geometry.height - 1)
        else:  # BOTTOM
            edge_pos = Position(x=position.x, y=1)

        # Hide, grab, position
        display_manager.pointer_grab()
        display_manager.keyboard_grab()
        display_manager.cursor_hide()
        display_manager.cursorPosition_set(edge_pos)

        logger.info(f"[STATE] → {new_context.value.upper()}")

elif context_ref[0] != ScreenContext.CENTER:
    # Determine which edge we should watch for return
    return_edges = {
        ScreenContext.WEST: lambda p, g: p.x >= g.width - 1,
        ScreenContext.EAST: lambda p, g: p.x <= 0,
        ScreenContext.NORTH: lambda p, g: p.y >= g.height - 1,
        ScreenContext.SOUTH: lambda p, g: p.y <= 0
    }

    should_return = return_edges[context_ref[0]](position, screen_geometry)

    if should_return:
        # ... existing return logic ...
```

**File:** `config.yml`

**Update for multiple clients:**
```yaml
clients:
  - name: "phomux"
    position: west
  - name: "tablet"
    position: east
  - name: "laptop"
    position: north
```

**File:** `tx2tx/server/main.py`

**Add client routing:**
```python
# Map contexts to client names
context_to_client = {}
for client_config in config.clients:
    position_to_context = {
        "west": ScreenContext.WEST,
        "east": ScreenContext.EAST,
        "north": ScreenContext.NORTH,
        "south": ScreenContext.SOUTH
    }
    context = position_to_context[client_config.position]
    context_to_client[context] = client_config.name

# When sending events, send only to active client
if context_ref[0] != ScreenContext.CENTER:
    target_client_name = context_to_client[context_ref[0]]

    # Send event only to target client
    network.messageToClient_send(target_client_name, msg)
```

**Commit:** "Add multi-directional support (EAST/NORTH/SOUTH)"

---

### Phase 11: Performance Optimization

**Goal:** Optimize polling, reduce latency, minimize CPU usage.

**File:** `config.yml`

**Tunable parameters:**
```yaml
server:
  poll_interval_ms: 8  # Reduce from 20ms to 8ms for 120Hz responsiveness
  velocity_threshold: 50  # Lower threshold for easier transitions
  edge_threshold: 0  # Stay at 0 for immediate detection
```

**File:** `tx2tx/server/main.py`

**Adaptive polling:**
```python
# Use faster polling during REMOTE mode, slower during CENTER
if context_ref[0] == ScreenContext.CENTER:
    poll_interval = config.server.poll_interval_ms / 1000.0
else:
    poll_interval = config.server.poll_interval_ms / 2000.0  # 2x faster when remote

time.sleep(poll_interval)
```

**File:** `tx2tx/network/server.py`

**Add message batching:**
```python
# Batch multiple position updates if network is slow
position_buffer = []

def send_batched():
    if position_buffer:
        # Send only the latest position (discard intermediate ones)
        latest = position_buffer[-1]
        network.messageToAll_broadcast(latest)
        position_buffer.clear()
```

**Testing:**
- Measure CPU usage during idle (CENTER mode)
- Measure CPU usage during active control (REMOTE mode)
- Measure latency from server mouse movement to client cursor movement
- Target: <10ms latency, <5% CPU during idle, <15% during active

**Commit:** "Optimize polling and reduce latency"

---

### Phase 12: Future Enhancements

**After core functionality is stable:**

1. **Clipboard synchronization:**
   - Monitor clipboard changes on server and client
   - Sync clipboard content when transitioning contexts
   - Handle text, images, and files

2. **Display scaling compensation:**
   - Handle different DPI settings between server and client
   - Adjust mouse acceleration/sensitivity
   - Optional coordinate scaling factors in config

3. **Security hardening:**
   - Add authentication for client connections
   - Encrypt network traffic (TLS)
   - Validate all input from network

4. **Error recovery:**
   - Auto-reconnect client if connection drops
   - Graceful handling of display disconnection
   - State recovery after crashes

5. **Configuration UI:**
   - Web-based config editor
   - Real-time connection monitoring
   - Visual layout editor for multi-screen setup

6. **Platform support:**
   - Wayland support (currently X11 only)
   - Windows support (via Win32 API)
   - macOS support (via Quartz/CGEvent)

---

### Commit Strategy

Each phase should be a separate commit:

**Completed (v2.0.0):**
1. ✅ "Implement input isolation: cursor hiding and pointer/keyboard grab (v2.0.0 Phase 1)"
2. ✅ "Add ScreenContext enum for global state tracking (v2.0.0 Phase 2)"
3. ✅ "Strip out delta tracking and cursor warping complexity (v2.0.0 Phase 3)"
4. ✅ "Add named client configuration support (v2.0.0 Phase 4)"
5. ✅ "Implement normalized coordinates and full state machine (v2.0.0 Phases 5-6)"

**Current:**
6. 🔄 "Test and validate input isolation" (Phase 7 - in progress)

**Upcoming (v2.1.0+):**
7. ⏳ "Add mouse button event forwarding (v2.1.0 Phase 8)"
8. ⏳ "Add keyboard event forwarding (v2.1.0 Phase 9)"
9. ⏳ "Add multi-directional support: EAST/NORTH/SOUTH (v2.2.0 Phase 10)"
10. ⏳ "Optimize polling and reduce latency (v2.3.0 Phase 11)"
11. ⏳ "Future enhancements (v3.0.0+ Phase 12)"

---

## Version Roadmap

**v2.0.0 (Current):** ✅ Core server-authoritative architecture with CENTER ↔ WEST transitions
- Input isolation via pointer/keyboard grab
- Normalized coordinates
- Full state machine
- Named client configuration

**v2.1.0 (Next):** Mouse and keyboard event forwarding
- Button clicks forwarded to client
- Keyboard typing forwarded to client
- Full input control on remote client

**v2.2.0:** Multi-directional support
- EAST, NORTH, SOUTH edges
- Multiple simultaneous clients
- Client routing by position

**v2.3.0:** Performance optimization
- Adaptive polling rates
- Latency reduction
- CPU usage optimization
- Message batching

**v3.0.0+:** Advanced features
- Clipboard synchronization
- Display scaling
- Security hardening
- Error recovery
- Cross-platform support

