# tx2tx

tx2tx is a network KVM-style input sharing tool for mixed Linux desktop environments. It runs a server on your primary machine, clients on secondary machines, and forwards mouse and keyboard events across X11 and Wayland backends.

## What It Does

- Shares one local keyboard and mouse with multiple remote clients.
- Supports X11 server/client and Wayland server (via helper) to X11 client workflows.
- Uses named clients with physical placement (`west`, `east`, `north`, `south`) and context-aware routing.
- Provides both edge-based transitions and prefix hotkey jumps.
- Includes reconnect handling, panic-key recovery, and safety fallback to `CENTER`.

## Why tx2tx

Many software KVM tools break in constrained display stacks or mixed backend setups. tx2tx focuses on backend-specific capture/injection paths so input sharing stays reliable when environments differ across machines.

## Recent Features

- Wayland helper hardening for long-running sessions (reduced idle spin/runaway CPU risk).
- Strict REMOTE transition guard: refuse REMOTE mode when required typing keyboard grab fails.
- Scroll wheel capture/injection path for mixed backend sessions.
- Prefix jump-hotkey flow (`Ctrl+/` then action key by default) for deterministic context switching.
- Runtime architecture split into focused server/client modules with improved test coverage.

## Backends

- `x11`: direct capture and injection with `python-xlib` and XTest.
- `wayland`: helper-based capture/injection using `evdev` + `uinput`.

Wayland mode requires helper access to `/dev/input/*` and `/dev/uinput` (typically via `sudo` or udev rules).

## Quick Start

### Wayland Server + X11 Client

```bash
# Wayland server (Mercury-style launch)
sudo --preserve-env=PATH,WAYLAND_DISPLAY,XDG_RUNTIME_DIR,DBUS_SESSION_BUS_ADDRESS,DISPLAY \
  tx2tx \
  --backend wayland \
  --wayland-pointer-provider helper \
  --wayland-calibrate \
  --wayland-helper "tx2tx-wayland-helper" \
  --host <server-ip> \
  --port 24800

# X11 client
tx2tx --server <server-ip>:24800 --backend x11 --name <client-name>
```

Notes:
- `--wayland-helper "tx2tx-wayland-helper"` is usually sufficient; width/height args are optional.
- `--wayland-pointer-provider gnome` is available on GNOME sessions if helper pointer coords drift.
- Use `--name` on clients to match names configured in `config.yml`.

### X11 Server + X11 Client

```bash
# X11 server
tx2tx --backend x11 --host <server-ip> --port 24800

# X11 client
tx2tx --server <server-ip>:24800 --backend x11 --name <client-name>
```

### Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

For Wayland support:

```bash
pip install -e ".[wayland]"
```

## Configuration

See `config.yml` for defaults. Key areas:
- `clients`: named client layout and positions.
- `server.jump_hotkey`: prefix-based context jumps (default mapping `1/2/0`).
- `server.panic_key`: immediate return-to-center safety key.
- `backend`: backend selection and Wayland helper configuration.

CLI flags override config values.

## Project Structure

```
tx2tx/
├── docs/                  # Architecture and overview docs
├── tx2tx/
│   ├── client/            # Client implementation
│   ├── server/            # Server implementation
│   ├── protocol/          # Message definitions and serialization
│   ├── common/            # Shared types and settings
│   ├── x11/               # X11 backend
│   ├── wayland/           # Wayland backend + helper daemon
│   └── input/             # Backend factory and interfaces
```

## Notes

- tx2tx started as a termux-x11 experiment, but the current architecture targets broader mixed X11/Wayland use.
- Wayland helper support is platform/compositor dependent and still more constrained than pure X11 paths.

## Documentation

- `docs/overview.adoc`
- `docs/architecture.adoc`
- `docs/devstart.adoc`
- `docs/problem.adoc`
- `docs/limitations.adoc`

## License

MIT
