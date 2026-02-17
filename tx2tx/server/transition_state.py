"""
Server transition-policy implementation.

This module owns CENTER<->REMOTE transition policy and REMOTE-mode dispatch
behavior. It is intentionally isolated from polling-loop mechanics so the
runtime loop can stay orchestration-focused.

Policy responsibilities:
1. Resolve edge-triggered context transitions.
2. Enter and leave REMOTE context with safety invariants.
3. Route pointer and input events to the correct client.
4. Enforce early-wayland warp and return-boundary behavior.
5. Apply jump-hotkey actions and panic-key fallbacks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from tx2tx.common.config import Config
from tx2tx.common.settings import settings
from tx2tx.common.types import (
    Direction,
    EventType,
    KeyEvent,
    MouseEvent,
    NormalizedPoint,
    Position,
    Screen,
    ScreenContext,
)
from tx2tx.input.backend import DisplayBackend, InputCapturer, InputEvent
from tx2tx.protocol.message import Message, MessageBuilder
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.server.runtime_loop import JumpHotkeyConfigProtocol
from tx2tx.server.state import RuntimeStateProtocol
from tx2tx.x11.pointer import PointerTracker

_REMOTE_RETURN_GUARD_SECONDS: float = 0.6

__all__ = [
    "TransitionCallbacks",
    "centerContext_process",
    "contextFromDirection_get",
    "jumpHotkeyAction_apply",
    "remoteContextEnter_process",
    "remoteContext_process",
    "remoteInputEvents_send",
    "remoteMotionPosition_send",
    "remoteReturnBoundary_check",
    "remoteReturn_process",
    "remoteTargetClientName_get",
    "remoteWarpEnforcement_apply",
    "transitionParkingPosition_get",
    "transitionTargetClient_resolve",
]


class LoggerProtocol(Protocol):
    """Minimal logging contract used by transition policy."""

    def debug(self, msg: str, *args: object) -> None:
        """Emit debug-level log message."""
        ...

    def info(self, msg: str, *args: object) -> None:
        """Emit info-level log message."""
        ...

    def warning(self, msg: str, *args: object) -> None:
        """Emit warning-level log message."""
        ...

    def error(self, msg: str, *args: object, exc_info: bool = False) -> None:
        """Emit error-level log message."""
        ...


class PanicKeyCheckProtocol(Protocol):
    """Panic-key evaluator callback contract."""

    def __call__(
        self,
        events: list[InputEvent],
        panic_keysyms: set[int],
        required_modifiers: int,
        current_modifiers: int,
    ) -> bool:
        """Return True when panic key sequence is active."""
        ...


class JumpHotkeyEventsProcessProtocol(Protocol):
    """Jump-hotkey parser callback contract."""

    def __call__(
        self,
        input_events: list[InputEvent],
        modifier_state: int,
        jump_hotkey: JumpHotkeyConfigProtocol,
    ) -> tuple[list[InputEvent], ScreenContext | None]:
        """Return filtered events and optional jump target."""
        ...


class JumpHotkeyActionApplyProtocol(Protocol):
    """Jump-hotkey action callback contract."""

    def __call__(
        self,
        target_context: ScreenContext,
        network: ServerNetwork,
        display_manager: DisplayBackend,
        pointer_tracker: PointerTracker,
        screen_geometry: Screen,
        position: Position,
        context_to_client: dict[ScreenContext, str],
    ) -> bool:
        """Apply resolved jump action and return handled state."""
        ...


class StateRevertToCenterProtocol(Protocol):
    """CENTER revert callback contract."""

    def __call__(
        self,
        display_manager: DisplayBackend,
        screen_geometry: Screen,
        position: Position,
        pointer_tracker: PointerTracker,
    ) -> None:
        """Revert server from REMOTE context back to CENTER."""
        ...


class RemoteWarpEnforcementApplyProtocol(Protocol):
    """REMOTE warp-enforcement callback contract."""

    def __call__(
        self,
        display_manager: DisplayBackend,
        screen_geometry: Screen,
        position: Position,
        x11native: bool,
    ) -> bool:
        """Return True when enforcement warps pointer and consumes step."""
        ...


class RemoteInputEventsSendProtocol(Protocol):
    """REMOTE input-forwarding callback contract."""

    def __call__(
        self,
        network: ServerNetwork,
        target_client_name: str,
        screen_geometry: Screen,
        input_events: list[InputEvent],
        display_manager: DisplayBackend,
        pointer_tracker: PointerTracker,
        position: Position,
    ) -> None:
        """Forward input events to remote destination."""
        ...


@dataclass
class TransitionCallbacks:
    """
    Injected behavior hooks required by transition policy.

    Attributes:
        panicKey_check:
            Panic-key evaluator.
        jumpHotkeyEvents_process:
            Jump-hotkey parser.
        jumpHotkeyAction_apply:
            Jump-hotkey action applier.
        state_revertToCenter:
            CENTER safety revert routine.
        remoteWarpEnforcement_apply:
            REMOTE warp-enforcement routine.
        remoteInputEvents_send:
            REMOTE input-forwarding routine.
    """

    panicKey_check: PanicKeyCheckProtocol
    jumpHotkeyEvents_process: JumpHotkeyEventsProcessProtocol
    jumpHotkeyAction_apply: JumpHotkeyActionApplyProtocol
    state_revertToCenter: StateRevertToCenterProtocol
    remoteWarpEnforcement_apply: RemoteWarpEnforcementApplyProtocol
    remoteInputEvents_send: RemoteInputEventsSendProtocol


def contextFromDirection_get(direction: Direction) -> ScreenContext | None:
    """
    Convert pointer boundary direction to logical target context.

    Args:
        direction:
            Boundary transition direction.

    Returns:
        Target logical context or `None` when direction is unsupported.
    """
    direction_to_context: dict[Direction, ScreenContext] = {
        Direction.LEFT: ScreenContext.WEST,
        Direction.RIGHT: ScreenContext.EAST,
        Direction.TOP: ScreenContext.NORTH,
        Direction.BOTTOM: ScreenContext.SOUTH,
    }
    return direction_to_context.get(direction)


def transitionTargetClient_resolve(
    network: ServerNetwork,
    new_context: ScreenContext,
    context_to_client: dict[ScreenContext, str],
    logger: LoggerProtocol,
) -> tuple[str, ClientConnection] | None:
    """
    Resolve connected target client for a requested context.

    Args:
        network:
            Active server network.
        new_context:
            Desired destination context.
        context_to_client:
            Configured context-to-client routing map.
        logger:
            Runtime logger.

    Returns:
        `(target_client_name, target_client_connection)` or `None`.
    """
    target_client_name: str | None = context_to_client.get(new_context)
    if not target_client_name:
        logger.error("No client configured for %s", new_context.value)
        return None

    target_client: ClientConnection | None = network.clientByName_get(target_client_name)
    if target_client is None:
        connected_names: list[str | None] = [client.name for client in network.clients]
        logger.error(
            "Transition blocked: target '%s' unresolved. Connected clients: %s",
            target_client_name,
            connected_names,
        )
        return None
    return target_client_name, target_client


def transitionParkingPosition_get(
    direction: Direction,
    transition_position: Position,
    screen_geometry: Screen,
) -> Position:
    """
    Compute local parking position after CENTER->REMOTE transition.

    Args:
        direction:
            Boundary direction that triggered transition.
        transition_position:
            Pointer position at boundary crossing.
        screen_geometry:
            Local screen geometry.

    Returns:
        Cursor parking position near opposite edge for compositor containment.
    """
    parking_offset: int = 30
    if direction == Direction.LEFT:
        return Position(x=screen_geometry.width - parking_offset, y=transition_position.y)
    if direction == Direction.RIGHT:
        return Position(x=parking_offset, y=transition_position.y)
    if direction == Direction.TOP:
        return Position(x=transition_position.x, y=screen_geometry.height - parking_offset)
    return Position(x=transition_position.x, y=parking_offset)


def _parkingPositionFromContext_get(
    target_context: ScreenContext,
    position: Position,
    screen_geometry: Screen,
    center_parking_enabled: bool = False,
) -> Position:
    """
    Resolve parking position for explicit target context.

    Args:
        target_context:
            Destination context.
        position:
            Current pointer position.
        screen_geometry:
            Local screen geometry.
        center_parking_enabled:
            Whether to park at local screen center instead of context seam.

    Returns:
        Parking position for immediate REMOTE context entry.
    """
    if center_parking_enabled:
        return Position(
            x=screen_geometry.width // 2,
            y=screen_geometry.height // 2,
        )
    if target_context == ScreenContext.WEST:
        return Position(x=screen_geometry.width - 30, y=position.y)
    if target_context == ScreenContext.EAST:
        return Position(x=30, y=position.y)
    if target_context == ScreenContext.NORTH:
        return Position(x=position.x, y=screen_geometry.height - 30)
    return Position(x=position.x, y=30)


def remoteContextEnter_process(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    target_context: ScreenContext,
    position: Position,
    context_to_client: dict[ScreenContext, str],
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
    center_parking_enabled: bool = False,
) -> bool:
    """
    Transition from CENTER into specific REMOTE context.

    Args:
        network:
            Active server network.
        display_manager:
            Display backend used for pointer/input grabs.
        pointer_tracker:
            Pointer tracker to reset after warp.
        screen_geometry:
            Local screen geometry.
        target_context:
            Destination REMOTE context.
        position:
            Current pointer position.
        context_to_client:
            Context-to-client routing map.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.
        center_parking_enabled:
            Whether to park pointer at local screen center on entry.

    Returns:
        `True` when transition succeeds, otherwise `False`.
    """
    if target_context == ScreenContext.CENTER:
        return True

    resolved_target: tuple[str, ClientConnection] | None = transitionTargetClient_resolve(
        network=network,
        new_context=target_context,
        context_to_client=context_to_client,
        logger=logger,
    )
    if resolved_target is None:
        return False

    target_client_name: str = resolved_target[0]
    warp_pos: Position = _parkingPositionFromContext_get(
        target_context=target_context,
        position=position,
        screen_geometry=screen_geometry,
        center_parking_enabled=center_parking_enabled,
    )

    server_state.context = target_context
    server_state.active_remote_client_name = target_client_name
    logger.debug("[CONTEXT] Changed to %s", target_context.value.upper())
    logger.info(
        "[WARP] Parking cursor at (%s, %s) for %s",
        warp_pos.x,
        warp_pos.y,
        target_context.value,
    )

    display_manager.cursorPosition_set(warp_pos)
    display_manager.keyboard_grab()
    display_manager.pointer_grab()
    display_manager.cursor_hide()

    pointer_tracker.reset()
    server_state.last_sent_position = None
    server_state.last_remote_switch_time = time.time()
    logger.info("[STATE] → %s context", target_context.value.upper())
    return True


def jumpHotkeyAction_apply(
    target_context: ScreenContext,
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    position: Position,
    context_to_client: dict[ScreenContext, str],
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
    state_revertToCenter: StateRevertToCenterProtocol,
) -> bool:
    """
    Apply jump-hotkey transition request.

    Args:
        target_context:
            Requested destination context from jump-hotkey sequence.
        network:
            Active server network.
        display_manager:
            Display backend.
        pointer_tracker:
            Pointer tracker.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        context_to_client:
            Context-to-client routing map.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.
        state_revertToCenter:
            Callback used for safety reversion to CENTER.

    Returns:
        `True` when request was handled.
    """
    if target_context == ScreenContext.CENTER:
        if server_state.context != ScreenContext.CENTER:
            logger.info("[HOTKEY] Jumping to CENTER")
            state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
        return True

    if server_state.context != ScreenContext.CENTER and server_state.context != target_context:
        logger.info(
            "[HOTKEY] Switching remote context %s -> %s",
            server_state.context.value.upper(),
            target_context.value.upper(),
        )
        state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
        position = pointer_tracker.position_query()

    if server_state.context == target_context:
        return True

    logger.info("[HOTKEY] Jumping to %s", target_context.value.upper())
    return remoteContextEnter_process(
        network=network,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        target_context=target_context,
        position=position,
        context_to_client=context_to_client,
        server_state=server_state,
        logger=logger,
        center_parking_enabled=True,
    )


def centerContext_process(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    position: Position,
    velocity: float,
    context_to_client: dict[ScreenContext, str],
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Process CENTER-context boundary transitions.

    Args:
        network:
            Active server network.
        display_manager:
            Display backend.
        pointer_tracker:
            Pointer tracker.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        velocity:
            Current pointer velocity.
        context_to_client:
            Context-to-client routing map.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.
    """
    if _hysteresisActive_check(server_state):
        return

    transition = pointer_tracker.boundary_detect(position, screen_geometry)
    if transition is None:
        return

    target_context: ScreenContext | None = contextFromDirection_get(transition.direction)
    if target_context is None:
        logger.error("Invalid transition direction: %s", transition.direction)
        return

    _transitionTelemetry_log(transition.position, transition.direction, velocity, target_context, logger)
    _transitionEnter_attempt(
        network=network,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        transition_position=transition.position,
        target_context=target_context,
        context_to_client=context_to_client,
        server_state=server_state,
        logger=logger,
    )


def _hysteresisActive_check(server_state: RuntimeStateProtocol) -> bool:
    """
    Check whether center transition hysteresis is currently active.

    Args:
        server_state:
            Mutable server state singleton.

    Returns:
        `True` when hysteresis delay has not elapsed.
    """
    elapsed_since_center_switch: float = time.time() - server_state.last_center_switch_time
    return elapsed_since_center_switch < settings.HYSTERESIS_DELAY_SEC


def _transitionTelemetry_log(
    transition_position: Position,
    transition_direction: Direction,
    velocity: float,
    target_context: ScreenContext,
    logger: LoggerProtocol,
) -> None:
    """
    Emit transition telemetry for edge crossing event.

    Args:
        transition_position:
            Boundary crossing position.
        transition_direction:
            Crossing direction.
        velocity:
            Pointer velocity at crossing.
        target_context:
            Destination context.
        logger:
            Runtime logger.
    """
    logger.info(
        "[TRANSITION] Boundary crossed: pos=(%s,%s), velocity=%.1fpx/s, direction=%s, CENTER → %s",
        transition_position.x,
        transition_position.y,
        velocity,
        transition_direction.value.upper(),
        target_context.value.upper(),
    )


def _transitionEnter_attempt(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    transition_position: Position,
    target_context: ScreenContext,
    context_to_client: dict[ScreenContext, str],
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Attempt REMOTE context entry and apply safety rollback on failure.

    Args:
        network:
            Active server network.
        display_manager:
            Display backend.
        pointer_tracker:
            Pointer tracker.
        screen_geometry:
            Local screen geometry.
        transition_position:
            Boundary crossing position.
        target_context:
            Desired destination context.
        context_to_client:
            Context-to-client routing map.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.
    """
    try:
        start_time: float = time.time()
        transition_success: bool = remoteContextEnter_process(
            network=network,
            display_manager=display_manager,
            pointer_tracker=pointer_tracker,
            screen_geometry=screen_geometry,
            target_context=target_context,
            position=transition_position,
            context_to_client=context_to_client,
            server_state=server_state,
            logger=logger,
            center_parking_enabled=False,
        )
        if not transition_success:
            return
        logger.info("[TIMING] transition_enter: %.3f sec", time.time() - start_time)
    except Exception as exc:
        logger.error("Transition failed: %s", exc, exc_info=True)
        _transitionFailure_recover(display_manager, server_state, logger)


def _transitionFailure_recover(
    display_manager: DisplayBackend,
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Recover to CENTER state after transition setup failure.

    Args:
        display_manager:
            Display backend.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.
    """
    try:
        display_manager.keyboard_ungrab()
        display_manager.pointer_ungrab()
        display_manager.cursor_show()
    except Exception:
        pass
    server_state.context = ScreenContext.CENTER
    server_state.active_remote_client_name = None
    server_state.last_center_switch_time = time.time()
    logger.warning("Reverted to CENTER after failed transition")


def remoteTargetClientName_get(
    context_to_client: dict[ScreenContext, str],
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> str | None:
    """
    Resolve active remote target client name from state and mapping.

    Args:
        context_to_client:
            Context-to-client routing map.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.

    Returns:
        Active target client name or `None`.
    """
    context_target_name: str | None = context_to_client.get(server_state.context)
    if context_target_name is not None:
        if server_state.active_remote_client_name != context_target_name:
            if server_state.active_remote_client_name is not None:
                logger.warning(
                    "Correcting stale remote target '%s' -> '%s' for context '%s'",
                    server_state.active_remote_client_name,
                    context_target_name,
                    server_state.context.value,
                )
            server_state.active_remote_client_name = context_target_name
        return context_target_name
    return server_state.active_remote_client_name


def remoteWarpEnforcement_apply(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    x11native: bool,
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> bool:
    """
    Enforce early REMOTE warp when compositor drifts pointer post-transition.

    Args:
        display_manager:
            Display backend.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        x11native:
            Native X11 mode flag.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.

    Returns:
        `True` when enforcement warped pointer and caller should return early.
    """
    if x11native or display_manager.session_isNative_check():
        return False
    if (time.time() - server_state.last_remote_switch_time) >= 0.5:
        return False

    target_pos: Position | None = _remoteEnforcementTargetPosition_get(
        server_state.context,
        position,
        screen_geometry,
    )
    if target_pos is None:
        return False
    if abs(position.x - target_pos.x) <= 100:
        return False

    logger.info(
        "[ENFORCE] Cursor at (%s,%s), enforcing warp to (%s,%s)",
        position.x,
        position.y,
        target_pos.x,
        target_pos.y,
    )
    display_manager.cursorPosition_set(target_pos)
    time.sleep(0.01)
    return True


def _remoteEnforcementTargetPosition_get(
    context: ScreenContext,
    position: Position,
    screen_geometry: Screen,
) -> Position | None:
    """
    Resolve temporary enforcement target for current REMOTE context.

    Args:
        context:
            Active remote context.
        position:
            Current pointer position.
        screen_geometry:
            Local screen geometry.

    Returns:
        Enforcement target position or `None` when not applicable.
    """
    if context == ScreenContext.WEST:
        return Position(x=screen_geometry.width - 3, y=position.y)
    if context == ScreenContext.EAST:
        return Position(x=2, y=position.y)
    return None


def remoteReturnBoundary_check(
    context: ScreenContext,
    position: Position,
    screen_geometry: Screen,
) -> bool:
    """
    Check if pointer reached REMOTE->CENTER return boundary.

    Args:
        context:
            Active remote context.
        position:
            Current pointer position.
        screen_geometry:
            Local screen geometry.

    Returns:
        `True` when return boundary is reached.
    """
    if context == ScreenContext.WEST:
        return position.x >= screen_geometry.width - 1
    if context == ScreenContext.EAST:
        return position.x <= 0
    if context == ScreenContext.NORTH:
        return position.y >= screen_geometry.height - 1
    if context == ScreenContext.SOUTH:
        return position.y <= 0
    return False


def remoteReturn_process(
    network: ServerNetwork,
    target_client_name: str | None,
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    pointer_tracker: PointerTracker,
    state_revertToCenter: StateRevertToCenterProtocol,
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Process REMOTE->CENTER return transition.

    Args:
        network:
            Active server network.
        target_client_name:
            Current destination client name.
        display_manager:
            Display backend.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        pointer_tracker:
            Pointer tracker.
        state_revertToCenter:
            CENTER safety revert callback.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.
    """
    logger.info(
        "[BOUNDARY] Returning from %s at (%s, %s)",
        server_state.context.value.upper(),
        position.x,
        position.y,
    )
    try:
        _remoteSoftwareCursor_hide(network, target_client_name)
        state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
    except Exception as exc:
        logger.error("Return transition failed: %s", exc, exc_info=True)
        server_state.context = ScreenContext.CENTER
        _localInputUnlock_bestEffort(display_manager)


def _remoteSoftwareCursor_hide(
    network: ServerNetwork,
    target_client_name: str | None,
) -> None:
    """
    Hide remote software cursor during REMOTE->CENTER return.

    Args:
        network:
            Active server network.
        target_client_name:
            Current destination client name.
    """
    if target_client_name is None:
        return
    hide_event = MouseEvent(
        event_type=EventType.MOUSE_MOVE,
        normalized_point=NormalizedPoint(x=-1.0, y=-1.0),
    )
    hide_msg = MessageBuilder.mouseEventMessage_create(hide_event)
    network.messageToClient_send(target_client_name, hide_msg)


def _localInputUnlock_bestEffort(display_manager: DisplayBackend) -> None:
    """
    Best-effort local input unlock used after transition failure.

    Args:
        display_manager:
            Display backend.
    """
    try:
        display_manager.cursor_show()
        display_manager.keyboard_ungrab()
        display_manager.pointer_ungrab()
    except Exception:
        pass


def remoteMotionPosition_send(
    network: ServerNetwork,
    target_client_name: str,
    screen_geometry: Screen,
    position: Position,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    state_revertToCenter: StateRevertToCenterProtocol,
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> bool:
    """
    Send pointer move event to active remote client when position changed.

    Args:
        network:
            Active server network.
        target_client_name:
            Destination client name.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        display_manager:
            Display backend.
        pointer_tracker:
            Pointer tracker.
        state_revertToCenter:
            CENTER safety revert callback.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.

    Returns:
        `True` when caller may continue event processing.
    """
    if not server_state.positionChanged_check(position):
        return True

    logger.debug("[MOUSE] Sending pos (%s, %s) to %s", position.x, position.y, target_client_name)
    normalized_point: NormalizedPoint = screen_geometry.coordinates_normalize(position)
    mouse_event = MouseEvent(
        event_type=EventType.MOUSE_MOVE,
        normalized_point=normalized_point,
    )
    move_msg: Message = MessageBuilder.mouseEventMessage_create(mouse_event)
    if network.messageToClient_send(target_client_name, move_msg):
        server_state.lastSentPosition_update(position)
        return True

    connected_names: list[str | None] = [client.name for client in network.clients]
    logger.error(
        "Failed to send movement to '%s'. Connected clients: %s. Reverting.",
        target_client_name,
        connected_names,
    )
    state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
    return False


def remoteInputEvents_send(
    network: ServerNetwork,
    target_client_name: str,
    screen_geometry: Screen,
    input_events: list[InputEvent],
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    position: Position,
    state_revertToCenter: StateRevertToCenterProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Forward captured keyboard/button events to active remote client.

    Args:
        network:
            Active server network.
        target_client_name:
            Destination client name.
        screen_geometry:
            Local screen geometry.
        input_events:
            Captured input event list.
        display_manager:
            Display backend.
        pointer_tracker:
            Pointer tracker.
        position:
            Current pointer position.
        state_revertToCenter:
            CENTER safety revert callback.
        logger:
            Runtime logger.
    """
    for event in input_events:
        message: Message | None = _inputEventMessage_build(event, screen_geometry, logger)
        if message is None:
            continue
        if network.messageToClient_send(target_client_name, message):
            continue
        logger.error("Failed to send %s to %s", event.event_type.value, target_client_name)
        state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
        break


def _inputEventMessage_build(
    event: InputEvent,
    screen_geometry: Screen,
    logger: LoggerProtocol,
) -> Message | None:
    """
    Build outbound protocol message for one captured input event.

    Args:
        event:
            Captured input event.
        screen_geometry:
            Local screen geometry.
        logger:
            Runtime logger.

    Returns:
        Outbound protocol message or `None` when event is unsupported.
    """
    if isinstance(event, MouseEvent) and event.position:
        normalized_position: NormalizedPoint = screen_geometry.coordinates_normalize(event.position)
        normalized_event = MouseEvent(
            event_type=event.event_type,
            normalized_point=normalized_position,
            button=event.button,
        )
        logger.debug("[BUTTON] %s button=%s", event.event_type.value, event.button)
        return MessageBuilder.mouseEventMessage_create(normalized_event)
    if isinstance(event, KeyEvent):
        logger.debug("[KEY] %s keycode=%s", event.event_type.value, event.keycode)
        return MessageBuilder.keyEventMessage_create(event)
    return None


def remoteContext_process(
    network: ServerNetwork,
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    config: Config,
    position: Position,
    velocity: float,
    context_to_client: dict[ScreenContext, str],
    x11native: bool,
    input_capturer: InputCapturer,
    panic_keysyms: set[int],
    panic_modifiers: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    callbacks: TransitionCallbacks,
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Execute one REMOTE-context processing step.

    Args:
        network:
            Active server network.
        display_manager:
            Display backend.
        pointer_tracker:
            Pointer tracker.
        screen_geometry:
            Local screen geometry.
        config:
            Loaded server config.
        position:
            Current pointer position.
        velocity:
            Current pointer velocity.
        context_to_client:
            Context-to-client routing map.
        x11native:
            Native X11 mode flag.
        input_capturer:
            Input capture backend.
        panic_keysyms:
            Panic-key keysyms.
        panic_modifiers:
            Panic-key modifier mask.
        jump_hotkey:
            Runtime jump-hotkey config.
        callbacks:
            Behavior callbacks for panic/jump/revert operations.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.
    """
    target_client_name: str | None = remoteTargetClientName_get(
        context_to_client=context_to_client,
        server_state=server_state,
        logger=logger,
    )
    if target_client_name is None:
        _remoteUnmappedTarget_recover(
            input_capturer=input_capturer,
            display_manager=display_manager,
            screen_geometry=screen_geometry,
            position=position,
            pointer_tracker=pointer_tracker,
            callbacks=callbacks,
            server_state=server_state,
            logger=logger,
        )
        return

    if _remoteWarpEnforcedAndHandled(
        display_manager=display_manager,
        screen_geometry=screen_geometry,
        position=position,
        x11native=x11native,
        target_client_name=target_client_name,
        network=network,
        input_capturer=input_capturer,
        panic_keysyms=panic_keysyms,
        panic_modifiers=panic_modifiers,
        jump_hotkey=jump_hotkey,
        context_to_client=context_to_client,
        pointer_tracker=pointer_tracker,
        callbacks=callbacks,
        server_state=server_state,
        logger=logger,
    ):
        return

    if _remoteReturnTriggered_check(
        context=server_state.context,
        position=position,
        screen_geometry=screen_geometry,
        velocity=velocity,
        velocity_threshold=config.server.velocity_threshold,
        remote_switch_age_seconds=(time.time() - server_state.last_remote_switch_time),
    ):
        remoteReturn_process(
            network=network,
            target_client_name=target_client_name,
            display_manager=display_manager,
            screen_geometry=screen_geometry,
            position=position,
            pointer_tracker=pointer_tracker,
            state_revertToCenter=callbacks.state_revertToCenter,
            server_state=server_state,
            logger=logger,
        )
        return

    motion_sent: bool = remoteMotionPosition_send(
        network=network,
        target_client_name=target_client_name,
        screen_geometry=screen_geometry,
        position=position,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        state_revertToCenter=callbacks.state_revertToCenter,
        server_state=server_state,
        logger=logger,
    )
    if not motion_sent:
        return

    _remoteInputPhase_process(
        network=network,
        target_client_name=target_client_name,
        input_capturer=input_capturer,
        panic_keysyms=panic_keysyms,
        panic_modifiers=panic_modifiers,
        jump_hotkey=jump_hotkey,
        context_to_client=context_to_client,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        position=position,
        callbacks=callbacks,
        logger=logger,
    )


def _remoteUnmappedTarget_recover(
    input_capturer: InputCapturer,
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    pointer_tracker: PointerTracker,
    callbacks: TransitionCallbacks,
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Recover when current REMOTE context has no resolvable target client.

    Args:
        input_capturer:
            Input capture backend.
        display_manager:
            Display backend.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        pointer_tracker:
            Pointer tracker.
        callbacks:
            Behavior callbacks.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.
    """
    _, _ = input_capturer.inputEvents_read()
    logger.error(
        "Active context %s has no connected client, reverting",
        server_state.context.value,
    )
    callbacks.state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)


def _remoteWarpEnforcedAndHandled(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    x11native: bool,
    target_client_name: str,
    network: ServerNetwork,
    input_capturer: InputCapturer,
    panic_keysyms: set[int],
    panic_modifiers: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    context_to_client: dict[ScreenContext, str],
    pointer_tracker: PointerTracker,
    callbacks: TransitionCallbacks,
    server_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> bool:
    """
    Handle early-return branch when REMOTE warp enforcement is applied.

    Args:
        display_manager:
            Display backend.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        x11native:
            Native X11 mode flag.
        target_client_name:
            Destination client name.
        network:
            Active server network.
        input_capturer:
            Input capture backend.
        panic_keysyms:
            Panic-key keysyms.
        panic_modifiers:
            Panic-key modifier mask.
        jump_hotkey:
            Runtime jump-hotkey config.
        context_to_client:
            Context-to-client routing map.
        pointer_tracker:
            Pointer tracker.
        callbacks:
            Behavior callbacks.
        server_state:
            Mutable server state singleton.
        logger:
            Runtime logger.

    Returns:
        `True` when branch consumed processing and caller should return.
    """
    warp_enforced: bool = callbacks.remoteWarpEnforcement_apply(
        display_manager=display_manager,
        screen_geometry=screen_geometry,
        position=position,
        x11native=x11native,
    )
    if not warp_enforced:
        return False

    _remoteInputPhase_process(
        network=network,
        target_client_name=target_client_name,
        input_capturer=input_capturer,
        panic_keysyms=panic_keysyms,
        panic_modifiers=panic_modifiers,
        jump_hotkey=jump_hotkey,
        context_to_client=context_to_client,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        screen_geometry=screen_geometry,
        position=position,
        callbacks=callbacks,
        logger=logger,
    )
    return True


def _remoteReturnTriggered_check(
    context: ScreenContext,
    position: Position,
    screen_geometry: Screen,
    velocity: float,
    velocity_threshold: float,
    remote_switch_age_seconds: float,
) -> bool:
    """
    Evaluate whether REMOTE->CENTER return boundary and velocity are satisfied.

    Args:
        context:
            Active remote context.
        position:
            Current pointer position.
        screen_geometry:
            Local screen geometry.
        velocity:
            Current pointer velocity.
        velocity_threshold:
            Configured threshold for edge resistance.
        remote_switch_age_seconds:
            Elapsed seconds since entering current REMOTE context.

    Returns:
        `True` when return conditions are satisfied.
    """
    if remote_switch_age_seconds < _REMOTE_RETURN_GUARD_SECONDS:
        return False
    at_return_boundary: bool = remoteReturnBoundary_check(context, position, screen_geometry)
    if not at_return_boundary:
        return False
    return velocity >= (velocity_threshold * 0.5)


def _remoteInputPhase_process(
    network: ServerNetwork,
    target_client_name: str,
    input_capturer: InputCapturer,
    panic_keysyms: set[int],
    panic_modifiers: int,
    jump_hotkey: JumpHotkeyConfigProtocol,
    context_to_client: dict[ScreenContext, str],
    display_manager: DisplayBackend,
    pointer_tracker: PointerTracker,
    screen_geometry: Screen,
    position: Position,
    callbacks: TransitionCallbacks,
    logger: LoggerProtocol,
) -> None:
    """
    Process REMOTE input phase: capture, hotkey/panic checks, and forwarding.

    Args:
        network:
            Active server network.
        target_client_name:
            Destination client name.
        input_capturer:
            Input capture backend.
        panic_keysyms:
            Panic-key keysyms.
        panic_modifiers:
            Panic-key modifier mask.
        jump_hotkey:
            Runtime jump-hotkey config.
        context_to_client:
            Context-to-client routing map.
        display_manager:
            Display backend.
        pointer_tracker:
            Pointer tracker.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        callbacks:
            Behavior callbacks.
        logger:
            Runtime logger.
    """
    input_events, modifier_state = input_capturer.inputEvents_read()

    filtered_events, jump_target_context = callbacks.jumpHotkeyEvents_process(
        input_events=input_events,
        modifier_state=modifier_state,
        jump_hotkey=jump_hotkey,
    )
    if jump_target_context is not None:
        _ = callbacks.jumpHotkeyAction_apply(
            target_context=jump_target_context,
            network=network,
            display_manager=display_manager,
            pointer_tracker=pointer_tracker,
            screen_geometry=screen_geometry,
            position=position,
            context_to_client=context_to_client,
        )
        return

    panic_pressed: bool = callbacks.panicKey_check(
        filtered_events,
        panic_keysyms,
        panic_modifiers,
        modifier_state,
    )
    if panic_pressed:
        logger.warning("[PANIC] Panic key pressed - forcing return to CENTER")
        callbacks.state_revertToCenter(display_manager, screen_geometry, position, pointer_tracker)
        return

    callbacks.remoteInputEvents_send(
        network=network,
        target_client_name=target_client_name,
        screen_geometry=screen_geometry,
        input_events=filtered_events,
        display_manager=display_manager,
        pointer_tracker=pointer_tracker,
        position=position,
    )
