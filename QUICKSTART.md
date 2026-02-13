# tx2tx Quick Start Guide

tx2tx supports server/client input sharing with X11 and Wayland backends.

## Status

**Working:**
- Network communication (TCP client/server)
- X11 connection and screen geometry detection
- Boundary detection on all edges (left, right, top, bottom)
- Mouse movement forwarding
- Mouse button forwarding
- Keyboard forwarding
- Return path from REMOTE to CENTER context
- Panic key recovery
- Event injection via XTest extension
- Configuration via YAML
- Automatic client reconnection

**Current limitations:**
- Diagonal layout transitions are not fully implemented
- Wayland requires a privileged helper and device permissions
- `max_clients` defaults to 1 unless configured otherwise

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

For Wayland backend support:

```bash
pip install -e ".[wayland]"
```

## Run

### X11 server

```bash
tx2tx
```

### X11 client

```bash
tx2tx --server <server-ip>:24800 --backend x11 --name <client-name>
```

### Wayland server

```bash
sudo tx2tx \
  --backend wayland \
  --wayland-pointer-provider gnome \
  --wayland-helper "tx2tx-wayland-helper --screen-width <W> --screen-height <H>" \
  --host 0.0.0.0 \
  --port 24800
```

## Configuration

Edit `config.yml`:

```yaml
server:
  host: "0.0.0.0"
  port: 24800
  edge_threshold: 1
  velocity_threshold: 50
  poll_interval_ms: 20
  panic_key: "F12"
  max_clients: 1

clients:
  - name: "penguin"
    position: "east"

client:
  server_address: "localhost:24800"
  reconnect:
    enabled: true
    max_attempts: 5
    delay_seconds: 2

backend:
  name: "x11"  # or "wayland"
```

## Troubleshooting

- `Address already in use`

```bash
tx2tx --port 25000
```

- `XTest extension not available`

This means your X11 server does not support injection. Use an X11 environment with XTest support.

- Wayland helper permissions errors

Ensure helper access to `/dev/input/*` and `/dev/uinput`, or run with sufficient privileges.

- Client cannot connect

```bash
tx2tx --server <server-ip>:24800
```

## Related docs

- `README.md`
- `docs/overview.adoc`
- `docs/architecture.adoc`
