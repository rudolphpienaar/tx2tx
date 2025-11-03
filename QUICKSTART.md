# tx2tx Quick Start Guide

## What's Been Built

tx2tx is now functional as an MVP! It can:
- Detect when your cursor crosses a screen boundary
- Send mouse movement events to a remote display
- Inject those events into the remote X11 display

## Status

**Working:**
- Network communication (TCP client/server)
- X11 connection and screen geometry detection
- Boundary detection on all edges (left, right, top, bottom)
- Mouse movement tracking and forwarding
- Event injection via XTest extension
- Configuration via YAML
- Automatic client reconnection

**Not Yet Implemented:**
- Cursor hiding on server when in REMOTE mode
- Return path (switching from REMOTE back to LOCAL)
- Mouse button event capture/forwarding
- Keyboard event capture/forwarding
- Multi-client support

## Testing Now

### Option 1: Single Display (Proof of Concept)

Test that all components work on one display:

```bash
cd ~/src/tx2tx

# Terminal 1: Start server
tx2tx --server

# Terminal 2: Start client (different terminal)
tx2tx --client localhost:24800
```

**What to observe:**
1. Both connect successfully
2. Move cursor to screen edge
3. Server logs "Boundary crossed" and "Switched to REMOTE control"
4. Client logs "Received screen_leave from server"
5. Client starts injecting mouse movement events
6. You may see cursor jumping (both server and client controlling same display)

### Option 2: Two Devices (Real Use Case)

**On Device 1 (Server):**
```bash
cd ~/src/tx2tx

# Get your IP address
ip addr show wlan0 | grep "inet "
# Example output: inet 192.168.1.100/24

# Start server
tx2tx --server
```

**On Device 2 (Client):**
```bash
cd ~/src/tx2tx

# Connect to server (replace with actual IP)
tx2tx --client 192.168.1.100:24800
```

**Test the connection:**
1. On Device 1, move cursor slowly to the RIGHT edge of screen
2. Watch server log for "Boundary crossed: right at (X, Y)"
3. On Device 2, cursor should start moving
4. Move Device 1 cursor around - Device 2 cursor follows

## Files Overview

```
tx2tx/
├── config.yml                  # Configuration file
├── pyproject.toml             # Python project metadata
├── requirements.txt           # Dependencies
├── TESTING.md                 # Detailed testing guide
├── QUICKSTART.md              # This file
├── test_feasibility.py        # XTest verification script
└── src/tx2tx/
    ├── common/
    │   ├── config.py          # YAML config loader
    │   └── types.py           # Data classes
    ├── x11/
    │   ├── display.py         # X11 connection
    │   ├── pointer.py         # Cursor tracking
    │   └── injector.py        # Event injection
    ├── protocol/
    │   └── message.py         # Network protocol
    ├── server/
    │   ├── network.py         # TCP server
    │   └── main.py            # Server entry point
    └── client/
        ├── network.py         # TCP client
        └── main.py            # Client entry point
```

## Configuration

Edit `config.yml` to customize:

```yaml
server:
  host: "0.0.0.0"          # Server bind address
  port: 24800              # Server port
  edge_threshold: 0        # Pixels from edge to trigger
  poll_interval_ms: 20     # Cursor polling rate

client:
  server_address: "localhost:24800"  # Where to connect
  reconnect:
    enabled: true
    max_attempts: 5
    delay_seconds: 2

logging:
  level: "INFO"            # DEBUG for verbose output
```

## Troubleshooting

**"Address already in use"**
```bash
# Use a different port
tx2tx --server --port 25000
```

**"XTest extension not available"**
- This means your X11 server doesn't support event injection
- termux-x11 DOES support it (verified in test_feasibility.py)
- Try reconnecting to X11 display

**Client can't connect**
```bash
# On server device, verify it's listening
# Check if both devices on same network
# Try pinging: ping <server-ip>
```

**No boundary detection**
- Move cursor VERY slowly to the edge
- Try different edges (left, right, top, bottom)
- Check server logs for "Boundary crossed" messages
- Set `edge_threshold: 5` in config for easier triggering

**Cursor not moving on client**
- Check client logs for "Received mouse_event"
- Verify "XTest extension verified" appears
- Try DEBUG logging level

## Next Steps

To get to a complete MVP:
1. Implement cursor hiding on server in REMOTE mode
2. Add screen re-entry detection (switch back to LOCAL)
3. Capture and forward mouse button clicks
4. Capture and forward keyboard events
5. Add proper coordinate mapping for different screen sizes

See TESTING.md for detailed testing scenarios and troubleshooting.
