# tx2tx

X11 KVM for termux-x11: seamless mouse/keyboard sharing between X11 desktops.

A simpler, higher-level alternative to Synergy/Barrier designed specifically for termux-x11 environments.

## What It Does

Attempts to share mouse and keyboard across multiple Android devices running termux-x11, similar to Synergy/Barrier but working at the X11 protocol level.

## Status

**Implemented and unit tested:**
- Network communication (TCP client/server)
- X11 connection and screen geometry detection
- Boundary detection on all edges
- Mouse movement event capture and forwarding
- Event injection via XTest extension

**Not yet tested:** Two-device setup (need to verify on actual hardware)

**Not implemented:**
- Screen layout configuration (which edge leads to which client)
- Coordinate mapping between different screen sizes
- Return path (switching back from client to server)
- Mouse button capture/forwarding
- Keyboard event capture/forwarding
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
pip install -r requirements.txt
```

### Device 1: Run as Server

```bash
cd ~/tx2tx

# Find your IP address (note the inet address)
ip addr show wlan0 | grep "inet "
# Example output: inet 192.168.1.100/24

# Start the server
PYTHONPATH=src python -m tx2tx.server.main --config config.yml
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
cd ~/tx2tx

# Connect to server (replace with Device 1's IP from above)
PYTHONPATH=src python -m tx2tx.client.main --server 192.168.1.100:24800
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

On Device 1 (server), slowly move your mouse cursor to any edge of the screen. Watch the server log for:
```
INFO - Boundary crossed: right at (2959, 924)
INFO - Switched to REMOTE control
```

The client should now show the cursor moving as you move the mouse on Device 1.

### Current Limitations

**Screen Layout:** Not configurable yet. ANY edge crossing switches control to the client. You cannot specify "client is to the right of server" or define screen arrangement.

**One-Way Control:** Once the client takes control, there's no way to switch back without restarting the server.

**Mouse Only:** Only mouse movements work. Clicks and keyboard not yet implemented.

See [TESTING.md](TESTING.md) for troubleshooting.

## Project Structure

```
tx2tx/
├── pyproject.toml          # Project metadata and build config
├── requirements.txt        # Core dependencies
├── README.md              # This file
├── test_feasibility.py    # Feasibility test script
└── src/
    └── tx2tx/
        ├── __init__.py
        ├── common/         # Shared types and utilities
        │   ├── __init__.py
        │   └── types.py    # Data classes (Position, MouseEvent, etc.)
        ├── x11/            # X11 interaction layer
        │   ├── __init__.py
        │   ├── display.py  # Display connection management
        │   ├── pointer.py  # Pointer tracking and boundary detection
        │   └── injector.py # Event injection via XTest
        ├── protocol/       # Network protocol
        │   ├── __init__.py
        │   └── message.py  # Protocol messages and serialization
        ├── server/         # Server implementation
        │   ├── __init__.py
        │   └── main.py     # Server entry point
        └── client/         # Client implementation
            ├── __init__.py
            └── main.py     # Client entry point
```

## How It Works

**Server:** Polls cursor position, detects edge crossings, broadcasts movements to clients.

**Client:** Receives events from server, injects them into local X11 display via XTest.

**Protocol:** Simple JSON messages over TCP sockets.

## Contributing

Contributions welcome. Code uses complete type hints and RPN naming convention (`object_verb` format).

## License

MIT
