# tx2tx

X11 KVM for termux-x11: seamless mouse/keyboard sharing between X11 desktops.

A simpler, higher-level alternative to Synergy/Barrier designed specifically for termux-x11 environments.

## What It Does

Share your mouse and keyboard across multiple Android devices running termux-x11. Move your cursor off the edge of one screen and it appears on another, just like a multi-monitor setup.

## Status

**Working:** Mouse tracking, boundary detection, movement forwarding, and event injection between displays.

**In Progress:** Bidirectional control (return path), mouse clicks, keyboard events.

## Why tx2tx

Barrier and Synergy don't work in termux-x11 due to Android sandboxing. tx2tx works at the X11 protocol level using XTest and XQueryPointer, which are available in termux-x11 without privileged access.

## Quick Start

```bash
# Clone and install
git clone https://github.com/rudolphpienaar/tx2tx.git
cd tx2tx
pip install -r requirements.txt

# Device 1 (Server) - Get your IP first
ip addr show wlan0 | grep "inet "
PYTHONPATH=src python -m tx2tx.server.main --config config.yml

# Device 2 (Client) - Connect to server
PYTHONPATH=src python -m tx2tx.client.main --server 192.168.1.XXX:24800
```

Move your cursor to the edge of Device 1's screen and watch it appear on Device 2.

See [QUICKSTART.md](QUICKSTART.md) and [TESTING.md](TESTING.md) for detailed instructions.

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
