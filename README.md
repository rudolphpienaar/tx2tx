# tx2tx

tx2tx is a cross-platform KVM-style input sharing tool that bridges gaps where existing solutions like Synergy or Barrier fall short. It started as a termux-x11 to termux-x11 experiment and has evolved into a practical way to share keyboard and mouse across mixed X11 and Wayland environments.

## What It Does

- Runs a server on a primary machine and clients on secondary machines
- Captures keyboard and mouse on the server and forwards to the active client
- Supports X11 backends directly and Wayland backends via a privileged helper
- Works across machines on the same network using a lightweight TCP protocol

## Why tx2tx

Many existing input sharing tools rely on APIs that are blocked or unavailable on some platforms, especially Android and modern Wayland desktops. tx2tx focuses on backend-specific implementations that can still function in those environments.

## Backends

- `x11`: Direct X11 capture and injection using python-xlib and XTest
- `wayland`: A privileged helper (`tx2tx-wayland-helper`) that uses evdev and uinput for capture and injection

Wayland requires a helper command and appropriate permissions for `/dev/input/*` and `/dev/uinput`.

## Quick Start

### Wayland Server + X11 Client

Example with a Wayland server and an X11 client:

```bash
# Wayland server (requires helper and permissions)
sudo tx2tx \
  --backend wayland \
  --wayland-helper "tx2tx-wayland-helper --screen-width <W> --screen-height <H>" \
  --host 0.0.0.0 \
  --port 24800

# X11 client
tx2tx --server <server-ip>:24800 --backend x11 --name <client-name>
```

Notes:
- `screen-width` and `screen-height` must be the compositor's logical desktop size.
- The Wayland helper needs access to `/dev/input/*` and `/dev/uinput`.
- `evdev` does not currently publish wheels for Python 3.14. Use Python 3.11 or 3.12 for Wayland support.
- Wayland keyboard events are mapped from Linux evdev keycodes to X11 keycodes using the standard +8 offset.
- For Wayland on GNOME, use the GNOME Shell extension in `gnome-extension/` and set `TX2TX_GNOME_POINTER=1` to enable accurate pointer tracking.
- For Wayland, you can use `--wayland-calibrate` to warp the cursor to center on startup and sync helper state.

### GNOME Pointer Provider (Wayland)

On GNOME Wayland, accurate global pointer position is only available via GNOME Shell.
Install the included extension and enable the DBus provider:

```bash
mkdir -p ~/.local/share/gnome-shell/extensions
cp -r gnome-extension/tx2tx-pointer@tx2tx ~/.local/share/gnome-shell/extensions/
gnome-extensions enable tx2tx-pointer@tx2tx
```

Then run the server with:

```bash
TX2TX_GNOME_POINTER=1 sudo -E .venv/bin/tx2tx \\
  --backend wayland \\
  --wayland-helper "/home/rudolph/src/tx2tx/.venv/bin/tx2tx-wayland-helper --screen-width <W> --screen-height <H>" \\
  --host 0.0.0.0 \\
  --port 24800
```

`sudo -E` preserves `DBUS_SESSION_BUS_ADDRESS` and `XDG_RUNTIME_DIR` so the helper can reach the GNOME session bus.
For the DBus provider, ensure `python3-gi` is available to the helper. Easiest path is to create the venv with system site packages:

```bash
python3.12 -m venv --system-site-packages .venv
```

Compute logical desktop size on GNOME:

```bash
gdbus call --session \
  --dest org.gnome.Mutter.DisplayConfig \
  --object-path /org/gnome/Mutter/DisplayConfig \
  --method org.gnome.Mutter.DisplayConfig.GetCurrentState
```

Use the monitor layout section of the output to calculate the full bounding width/height.

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

### Run Server (X11)

```bash
tx2tx
```

### Run Server (Wayland)

```bash
sudo tx2tx \
  --backend wayland \
  --wayland-helper "tx2tx-wayland-helper --screen-width <W> --screen-height <H>"
```

### Run Client (X11)

```bash
tx2tx --server <server-ip>:24800 --backend x11
```

## Configuration

See `config.yml` for defaults. You can override most settings with CLI flags. The backend can be configured either in the config file or with `--backend`.

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

- Wayland helper needs elevated permissions or device access rules
- Screen geometry for Wayland is the compositor's logical desktop size, not a single monitor size

## Documentation

- `docs/overview.adoc`
- `docs/architecture.adoc`

## License

MIT
