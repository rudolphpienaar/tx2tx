# Testing tx2tx Between Two Displays

This guide explains how to test tx2tx with two actual termux-x11 instances.

## Prerequisites

- Two Android devices, OR
- One Android device with split-screen capability, OR
- One Android device where you can run two termux-x11 instances

## Method 1: Two Separate Devices

### Device 1 (Server)

1. Start termux-x11 and open a terminal
2. Navigate to the tx2tx directory:
   ```bash
   cd ~/src/tx2tx
   ```

3. Find your IP address:
   ```bash
   ip addr show wlan0 | grep inet
   ```
   Note the IP (e.g., 192.168.1.100)

4. Start the server:
   ```bash
   tx2tx
   ```

5. You should see:
   ```
   INFO - tx2tx server v0.1.0
   INFO - Listening on 0.0.0.0:24800
   INFO - Screen geometry: 2960x1848
   INFO - Server running. Press Ctrl+C to stop.
   ```

### Device 2 (Client)

1. Start termux-x11 and open a terminal
2. Navigate to the tx2tx directory:
   ```bash
   cd ~/src/tx2tx
   ```

3. Connect to the server (replace with Device 1's IP):
   ```bash
   tx2tx --server 192.168.1.100:24800
   ```

4. You should see:
   ```
   INFO - tx2tx client v0.1.0
   INFO - Connecting to 192.168.1.100:24800
   INFO - Screen geometry: 2960x1848
   INFO - XTest extension verified, event injection ready
   INFO - Connected to server
   INFO - Client running. Press Ctrl+C to stop.
   ```

### Testing the Connection

1. On Device 1 (Server), move your cursor to the edge of the screen
2. Watch the server log - you should see:
   ```
   INFO - Boundary crossed: right at (2959, 924)
   INFO - Switched to REMOTE control
   ```

3. On Device 2 (Client), you should see:
   ```
   INFO - Received screen_leave from server
   INFO - Server lost control at right edge (2959, 924)
   ```

4. On Device 2, the cursor should now be moving as you move the cursor on Device 1

## Method 2: Same Device, Two termux-x11 Instances

Some Android launchers allow running multiple instances of the same app:

1. Open termux-x11 (Instance 1)
2. Start the server as above
3. Use your launcher's multi-window or app cloning feature to open termux-x11 again (Instance 2)
4. Connect the client to localhost:24800

## Method 3: Single Display Test (Proof of Concept)

You can test on a single display to verify the components work:

```bash
cd ~/src/tx2tx

# Terminal 1: Start server
tx2tx

# Terminal 2: Start client (in another terminal session)
tx2tx --server localhost:24800
```

This proves:
- Network communication works
- Boundary detection works
- Event injection works (you'll see the cursor jumping as events are injected)

However, for the intended use case (seamless cursor transition between screens), you need two actual displays.

## Expected Behavior (Full MVP)

When working correctly between two displays:

1. **Initial State**: Cursor on Server display, Client display idle
2. **Boundary Cross**: Move cursor off the right edge of Server
3. **Transition**:
   - Server detects boundary crossing
   - Server sends screen_leave message to Client
   - Server switches to REMOTE mode
   - Server starts sending all mouse movements to Client
4. **Remote Control**:
   - Client receives mouse movement events
   - Client injects events into its X11 display
   - Cursor appears and moves on Client display
5. **Return** (TODO):
   - When cursor crosses back to Server edge on Client
   - Client notifies Server
   - Server switches back to LOCAL mode
   - Cursor returns to Server display

## Troubleshooting

### Server won't start
- Check if port 24800 is already in use: `netstat -ln | grep 24800`
- Use a different port: `--port 24801`

### Client can't connect
- Verify server IP address
- Check both devices are on same network
- Try `ping <server-ip>` from client device
- Check firewall settings

### Cursor doesn't move on client
- Verify XTest extension: Should see "XTest extension verified" in client log
- Check client is receiving events: Look for "Received mouse_event" in logs
- Verify X11 permissions

### Boundary detection not working
- Check edge_threshold in config.yml
- Move cursor slowly to the very edge
- Check server logs for "Boundary crossed" messages

## Current Limitations

- Mouse stays visible on server in REMOTE mode (cursor hiding not implemented)
- No return path (stuck in REMOTE mode, need to restart)
- Only mouse movement events (no clicks yet)
- No keyboard events
- Single client only
