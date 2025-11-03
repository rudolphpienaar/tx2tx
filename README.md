# tx2tx

X11 KVM for termux-x11: seamless mouse/keyboard sharing between X11 desktops.

A simpler, higher-level alternative to Synergy/Barrier designed specifically for termux-x11 environments.

## Features

- **Proven feasible** - XTest and XQueryPointer work in termux-x11
- **Mouse sharing** - Move cursor across screens seamlessly
- **Keyboard sharing** - Type on any connected screen
- **Lightweight** - Pure Python, minimal dependencies
- **Works in Android** - No privileged system access required

## Project Status

**MVP Scaffolding Complete** - Core architecture in place, implementation pending.

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .

# With dev tools
pip install -e ".[dev]"
```

## Usage

### Server (captures events)

```bash
tx2tx-server --host 0.0.0.0 --port 24800
```

### Client (receives events)

```bash
tx2tx-client --server 192.168.1.100:24800
```

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

## Architecture

### Server Flow
1. Connect to X11 display
2. Poll cursor position continuously
3. Detect when cursor crosses screen boundary
4. Send events to connected clients

### Client Flow
1. Connect to X11 display
2. Verify XTest extension availability
3. Connect to server
4. Receive events from server
5. Inject events into local X11 using XTest

## Code Conventions

### Type Hinting
- **Complete type hints** on all functions (parameters + return types)
- Type hints for all class attributes
- Use `typing` module for complex types

### Naming Convention (RPN)
Format: `<object>[qualifier]_<verb>[adverb]` with camelCase

Examples:
- `screenGeometry_get()` - Get screen geometry
- `mouseEvent_inject()` - Inject mouse event
- `connection_establish()` - Establish connection
- `boundary_detect()` - Detect boundary crossing

## Technical Details

### Why tx2tx Works (vs Barrier)

**Barrier's problem:**
- Relies on XRecord extension or `/dev/input` access
- Android sandboxing blocks these low-level mechanisms

**tx2tx solution:**
- Works within X11 server process space
- Uses standard X11 protocol calls:
  - `XQueryPointer` - Query cursor position
  - `XTest` - Inject events
- No privileged system access needed

### Tested Components (termux-x11)

- X11 connection
- Pointer position querying
- XTest extension (event injection)
- XInput2 extension (bonus)

See `test_feasibility.py` for verification.

## Development

```bash
# Run feasibility test
python test_feasibility.py

# Type checking (when implemented)
mypy src/

# Code formatting (when implemented)
black src/

# Linting (when implemented)
ruff check src/
```

## License

MIT

## Contributing

Contributions welcome! Please ensure:
- Complete type hints on all code
- Follow RPN naming convention
- Add tests for new features
