# tx2tx Refactor Map

## Goals
- Reduce mixed concerns in runtime-critical paths.
- Lower cyclomatic complexity in top offenders.
- Preserve behavior and protocol compatibility.
- Increase testability by isolating pure logic from I/O side effects.

## Current Hotspots
- `tx2tx/server/main.py`
  - `_process_polling_loop` mixes network lifecycle, state transitions, input capture, and protocol send.
  - `server_run` mixes config/bootstrap/runtime loop wiring.
- `tx2tx/wayland/helper_daemon.py`
  - `InputDeviceManager` currently combines discovery, grab policy, event processing, and queueing.
  - `_command_handle` is an if/elif dispatcher with side effects.
- `tx2tx/wayland/backend.py`
  - `_keysym_from_evdev` duplicates key mapping logic in one function.
- `tx2tx/client/main.py`
  - `serverMessage_handle` mixes parsing, coordinate transforms, cursor policy, and injection.
- `tx2tx/cli.py`
  - `main` combines role resolution, args mutation, logging policy, and execution dispatch.

## Execution Plan
1. Extract shared/pure logic first:
   - Move Wayland keysym resolution into a dedicated mapping module.
2. Replace branch-heavy dispatch with table-driven dispatch:
   - Wayland helper command routing.
3. Split orchestration from handlers in entrypoints:
   - CLI role dispatch helpers.
   - Client message-type handlers.
4. Split server loop into focused handlers:
   - CENTER context transition handling.
   - REMOTE context forwarding/return handling.
5. Follow-up phase (not in this change-set):
   - Break `InputDeviceManager` into `DeviceRegistry`, `GrabManager`, `EventStream`.
   - Move server state-machine logic to dedicated module(s).

## Acceptance Criteria
- `ruff check` passes.
- `pytest tests/unit` passes.
- No protocol payload shape changes.
- Complexity errors reduced for modified functions.
