# tx2tx

X11 KVM for termux-x11: seamless mouse/keyboard sharing between X11 desktops.

A simpler, higher-level alternative to Synergy/Barrier designed specifically for termux-x11 environments.

## What It Does

Attempts to share mouse and keyboard across multiple Android devices running termux-x11, similar to Synergy/Barrier but working at the X11 protocol level.

## Status

**Implemented:**
- ✅ Network communication (TCP client/server)
- ✅ X11 connection and screen geometry detection
- ✅ Boundary detection on all edges (both directions)
- ✅ Bidirectional control switching (LOCAL ↔ REMOTE transitions)
- ✅ Mouse movement capture and forwarding
- ✅ Mouse button capture and forwarding (press/release)
- ✅ Keyboard event capture and forwarding (press/release)
- ✅ Event injection via XTest extension
- ✅ Cursor confinement during remote control
- ✅ Full type hints (Python 3.11+ conventions, mypy strict mode)

**Not yet tested:**
- Two-device setup (need to verify on actual hardware)

**Not implemented:**
- Screen layout configuration (which edge leads to which client)
- Coordinate mapping between different screen sizes
- Multi-client support

## Why tx2tx

Barrier and Synergy don't work in termux-x11 due to Android sandboxing blocking XRecord and `/dev/input` access. tx2tx uses XTest and XQueryPointer which are available in termux-x11.

## HOWTO: Test Between Two Devices

### Prerequisites
- Two Android devices with termux-x11 installed and running
- Both devices on the same WiFi network
- Both devices have Python and pip installed

### Installation (on both devices)

```bash
git clone https://github.com/rudolphpienaar/tx2tx.git
cd tx2tx
pip install -e .
```

**Note for termux users:** Do not use a regular Python venv in termux. Termux's system python-xlib is patched to find X11 sockets in the correct location. If you need isolation, use: `python -m venv --system-site-packages .venv`

### Device 1: Run as Server

```bash
# Find your IP address (note the inet address)
ip addr show wlan0 | grep "inet "
# Example output: inet 192.168.1.100/24

# Start the server
tx2tx
```

You should see:
```
INFO - tx2tx server v0.1.0
INFO - Listening on 0.0.0.0:24800
INFO - Screen geometry: 2960x1848
INFO - Server running. Press Ctrl+C to stop.
```

### Device 2: Run as Client

```bash
# Connect to server (replace with Device 1's IP from above)
tx2tx --server 192.168.1.100:24800
```

You should see:
```
INFO - tx2tx client v0.1.0
INFO - Connecting to 192.168.1.100:24800
INFO - Screen geometry: 2960x1848
INFO - XTest extension verified, event injection ready
INFO - Connected to server
INFO - Client running. Press Ctrl+C to stop.
```

### Testing

**Step 1: Server → Client transition**

On Device 1 (server), slowly move your mouse cursor to any edge of the screen. Watch the server log for:
```
INFO - Boundary crossed: right at (2959, 924)
INFO - Switched to REMOTE control
DEBUG - Cursor confined
DEBUG - Keyboard grabbed for event capture
```

The client should show:
```
INFO - Received screen_leave from server
INFO - Switched to ACTIVE mode
```

Now the client device should receive:
- Mouse movements (cursor follows your movements on server)
- Mouse button clicks (try clicking - should work on client)
- Keyboard input (try typing - should work on client)

**Step 2: Client → Server transition**

On Device 2 (client), move the cursor to any edge. Watch the client log for:
```
INFO - Client boundary crossed: left at (0, 500)
INFO - Sent screen_enter to server
INFO - Switched to PASSIVE mode
```

The server should show:
```
INFO - Client re-entry at left edge
INFO - Switched to LOCAL control
DEBUG - Cursor released
DEBUG - Keyboard released
```

Control returns to the server! You can now repeat the cycle.

### Current Limitations

**Screen Layout:** Not configurable yet. ANY edge crossing switches control to the client. You cannot specify "client is to the right of server" or define screen arrangement.

**Coordinate Mapping:** No coordinate transformation between different screen sizes yet.

See [TESTING.md](TESTING.md) for troubleshooting.

## Project Structure

```
tx2tx/
├── pyproject.toml          # Project metadata and build config
├── requirements.txt        # Core dependencies
├── README.md              # This file
├── config.yml             # Configuration file
├── test_feasibility.py    # Feasibility test script
└── tx2tx/
    ├── __init__.py
    ├── common/             # Shared types and utilities
    │   ├── __init__.py
    │   ├── types.py        # Data classes (Position, MouseEvent, etc.)
    │   └── config.py       # Configuration loading
    ├── x11/                # X11 interaction layer
    │   ├── __init__.py
    │   ├── display.py      # Display connection + cursor confinement
    │   ├── pointer.py      # Pointer tracking and boundary detection
    │   ├── capturer.py     # Event capture (keyboard + mouse buttons)
    │   └── injector.py     # Event injection via XTest
    ├── protocol/           # Network protocol
    │   ├── __init__.py
    │   └── message.py      # Protocol messages and serialization
    ├── server/             # Server implementation
    │   ├── __init__.py
    │   ├── network.py      # Server network handling
    │   └── main.py         # Server entry point
    └── client/             # Client implementation
        ├── __init__.py
        ├── network.py      # Client network handling
        └── main.py         # Client entry point
```

## How It Works

### Server (Control Flow)

**LOCAL mode (server has control):**
1. Polls cursor position via XQueryPointer
2. Detects boundary crossings
3. When cursor hits edge:
   - Sends SCREEN_LEAVE message to client
   - Confines cursor to edge position (prevents visible movement)
   - Grabs keyboard to capture all input
   - Switches to REMOTE mode

**REMOTE mode (client has control):**
1. Captures keyboard events (key press/release)
2. Captures mouse button events (button press/release)
3. Polls mouse position for movement tracking
4. Broadcasts all events to client
5. Waits for SCREEN_ENTER message from client

**Return to LOCAL:**
1. Receives SCREEN_ENTER from client (cursor hit client edge)
2. Releases keyboard grab
3. Releases cursor confinement
4. Positions cursor at appropriate server edge
5. Switches back to LOCAL mode

### Client (Control Flow)

**PASSIVE mode (server has control):**
- Receives and buffers messages
- Ignores input events (not injecting)

**ACTIVE mode (client has control):**
1. Receives events from server:
   - Mouse movements → injects via XTest fake_input MotionNotify
   - Mouse buttons → injects via XTest ButtonPress/Release
   - Keyboard → injects via XTest KeyPress/Release
2. Monitors own cursor position for boundary detection
3. When cursor hits edge:
   - Sends SCREEN_ENTER message to server
   - Switches back to PASSIVE mode

### Protocol

Simple JSON messages over TCP sockets:
- `hello` - Handshake
- `screen_leave` - Server → Client (entering remote control)
- `screen_enter` - Client → Server (returning local control)
- `mouse_event` - Movement, button press/release
- `key_event` - Key press/release
- `keepalive` - Connection health check

## Contributing

Contributions welcome. Code uses complete type hints and RPN naming convention (`object_verb` format).

## License

MIT
