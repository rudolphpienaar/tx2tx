"""
Server polling-loop orchestration layer.

This module isolates deterministic orchestration performed once per server
polling tick. It does not encode transition-policy decisions directly; instead,
it coordinates transport intake, disconnect policy, pointer telemetry sampling,
and context dispatch through explicit callback contracts.

Design goals:
1. Keep functions single-responsibility and easy to test.
2. Keep runtime control flow shallow and explicit.
3. Separate orchestration mechanics from context-specific behavior.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from tx2tx.common.config import Config
from tx2tx.common.settings import settings
from tx2tx.common.types import Position, Screen, ScreenContext
from tx2tx.input.backend import DisplayBackend, InputCapturer, InputEvent
from tx2tx.protocol.message import Message
from tx2tx.server.network import ClientConnection, ServerNetwork
from tx2tx.x11.pointer import PointerTracker

_LAST_POS_LOG_TIME: float = 0.0
_MIN_POLL_INTERVAL_SECONDS: float = 0.005


class JumpHotkeyConfigProtocol(Protocol):
    """
    Runtime jump-hotkey configuration contract.

    The polling loop intentionally depends on a minimal interface to reduce
    coupling with the full config model.
    """

    enabled: bool
    prefix_keysym: int
    prefix_alt_keysyms: set[int]
    prefix_keycodes: set[int]
    prefix_modifier_mask: int
    timeout_seconds: float
    action_keysyms_to_context: dict[int, ScreenContext]
    action_keycodes_to_context: dict[int, ScreenContext]


class ServerStateProtocol(Protocol):
    """
    Shared server-state read contract.

    The polling loop requires only current logical context.
    """

    context: ScreenContext


class LoggerProtocol(Protocol):
    """Logger contract used by orchestration helpers."""

    def debug(self, msg: str, *args: object) -> None:
        """Emit debug-level message."""
        ...

    def warning(self, msg: str, *args: object) -> None:
        """Emit warning-level message."""
        ...


class ClientMessageHandleProtocol(Protocol):
    """Callback contract for handling one inbound client message."""

    def __call__(
        self,
        client: ClientConnection,
        message: Message,
        network: ServerNetwork,
    ) -> None:
        """Handle one inbound message from one connected client."""
        ...


class CenterContextProcessProtocol(Protocol):
    """Callback contract for CENTER-context processing."""

    def __call__(
        self,
        network: ServerNetwork,
        display_manager: DisplayBackend,
        pointer_tracker: PointerTracker,
        screen_geometry: Screen,
        position: Position,
        velocity: float,
        context_to_client: dict[ScreenContext, str],
    ) -> None:
        """Execute one CENTER-context processing step."""
        ...


class RemoteContextProcessProtocol(Protocol):
    """Callback contract for REMOTE-context processing."""

    def __call__(
        self,
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
    ) -> None:
        """Execute one REMOTE-context processing step."""
        ...


class JumpHotkeyEventsProcessProtocol(Protocol):
    """Callback contract for jump-hotkey event parsing."""

    def __call__(
        self,
        input_events: list[InputEvent],
        modifier_state: int,
        jump_hotkey: JumpHotkeyConfigProtocol,
    ) -> tuple[list[InputEvent], ScreenContext | None]:
        """
        Parse jump-hotkey input sequence.

        Returns parsed residual events and optional target context.
        """
        ...


class JumpHotkeyActionApplyProtocol(Protocol):
    """Callback contract for applying a resolved jump-hotkey action."""

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
        """Apply jump action and return whether transition was applied."""
        ...


@dataclass
class PollingLoopCallbacks:
    """
    Callback bundle used by polling-loop orchestration.

    Attributes:
        clientMessage_handle:
            Handler for one decoded inbound client message.
        centerContext_process:
            CENTER-context behavior executor.
        remoteContext_process:
            REMOTE-context behavior executor.
        jumpHotkeyEvents_process:
            Parser for jump-hotkey sequence extraction.
        jumpHotkeyAction_apply:
            Action applier for resolved jump target.
    """

    clientMessage_handle: ClientMessageHandleProtocol
    centerContext_process: CenterContextProcessProtocol
    remoteContext_process: RemoteContextProcessProtocol
    jumpHotkeyEvents_process: JumpHotkeyEventsProcessProtocol
    jumpHotkeyAction_apply: JumpHotkeyActionApplyProtocol


@dataclass
class PollingLoopDependencies:
    """
    Dependency bundle consumed by one polling-loop iteration.

    Attributes:
        network:
            Server transport/controller for connections and messaging.
        display_manager:
            Active display backend abstraction.
        pointer_tracker:
            Pointer telemetry source for position and velocity.
        screen_geometry:
            Authoritative local screen dimensions.
        config:
            Loaded runtime configuration.
        context_to_client:
            Mapping from logical screen context to configured client name.
        panic_keysyms:
            Panic-key keysyms that force CENTER safety return.
        panic_modifiers:
            Required modifier mask for panic-key activation.
        x11native:
            Whether session is native X11.
        input_capturer:
            Keyboard/mouse input capture interface.
        jump_hotkey:
            Runtime jump-hotkey configuration.
        die_on_disconnect:
            Whether server should stop when a client disconnects.
        client_count_previous:
            Previous tick client count for disconnect-edge detection.
    """

    network: ServerNetwork
    display_manager: DisplayBackend
    pointer_tracker: PointerTracker
    screen_geometry: Screen
    config: Config
    context_to_client: dict[ScreenContext, str]
    panic_keysyms: set[int]
    panic_modifiers: int
    x11native: bool
    input_capturer: InputCapturer
    jump_hotkey: JumpHotkeyConfigProtocol
    die_on_disconnect: bool = False
    client_count_previous: int | None = None


def pollingLoop_process(
    deps: PollingLoopDependencies,
    callbacks: PollingLoopCallbacks,
    server_state: ServerStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Execute one server polling-loop iteration.

    Processing sequence:
    1. Accept/process network input.
    2. Apply disconnect policy.
    3. Skip pointer/context work when no clients are connected.
    4. Sample and log pointer telemetry.
    5. Dispatch to CENTER/REMOTE context handler path.
    6. Sleep using configured poll interval.

    Args:
        deps:
            Runtime dependency bundle.
        callbacks:
            Behavior callbacks for network and context operations.
        server_state:
            Shared runtime state exposing current context.
        logger:
            Logger used for telemetry and policy warnings.
    """
    networkMessages_process(deps, callbacks)
    should_continue: bool = disconnectPolicy_apply(deps, logger)
    if not should_continue:
        return

    if deps.network.clients_count() <= 0:
        loopDelay_sleep(deps)
        return

    position, velocity = pointerState_sample(deps)
    pointerTelemetry_log(position, velocity, deps.screen_geometry, logger)

    context_handled: bool = contextDispatch_process(
        deps=deps,
        callbacks=callbacks,
        server_state=server_state,
        position=position,
        velocity=velocity,
    )
    if context_handled:
        loopDelay_sleep(deps)
        return

    loopDelay_sleep(deps)


def networkMessages_process(deps: PollingLoopDependencies, callbacks: PollingLoopCallbacks) -> None:
    """
    Process transport side effects for one polling tick.

    This function accepts pending connections and drains inbound client data.

    Args:
        deps:
            Runtime dependency bundle.
        callbacks:
            Callback bundle containing client message handler.
    """
    deps.network.connections_accept()

    def message_handler(client: ClientConnection, message: Message) -> None:
        callbacks.clientMessage_handle(client, message, deps.network)

    deps.network.clientData_receive(message_handler)


def disconnectPolicy_apply(deps: PollingLoopDependencies, logger: LoggerProtocol) -> bool:
    """
    Apply optional shutdown-on-disconnect policy.

    Args:
        deps:
            Runtime dependency bundle.
        logger:
            Logger used when shutdown policy is triggered.

    Returns:
        `True` when loop should continue, `False` when server is stopped.
    """
    if not deps.die_on_disconnect:
        deps.client_count_previous = deps.network.clients_count()
        return True

    previous_client_count: int = (
        deps.network.clients_count()
        if deps.client_count_previous is None
        else deps.client_count_previous
    )
    current_client_count: int = deps.network.clients_count()
    deps.client_count_previous = current_client_count
    if current_client_count >= previous_client_count:
        return True

    logger.warning("[NETWORK] Client disconnected and --die-on-disconnect is set. Shutting down.")
    deps.network.is_running = False
    return False


def pointerState_sample(deps: PollingLoopDependencies) -> tuple[Position, float]:
    """
    Sample pointer position and instantaneous velocity.

    Args:
        deps:
            Runtime dependency bundle.

    Returns:
        Tuple of sampled `(position, velocity)`.
    """
    position: Position = deps.pointer_tracker.position_query()
    velocity: float = deps.pointer_tracker.velocity_calculate()
    return position, velocity


def pointerTelemetry_log(
    position: Position,
    velocity: float,
    screen_geometry: Screen,
    logger: LoggerProtocol,
) -> None:
    """
    Emit pointer telemetry logs for diagnostics.

    Position logs are rate-limited to reduce steady-state noise. Near-edge logs
    remain high-fidelity to support transition debugging.

    Args:
        position:
            Current pointer position.
        velocity:
            Current pointer velocity.
        screen_geometry:
            Local screen geometry used for bounds checks.
        logger:
            Logger used for telemetry output.
    """
    global _LAST_POS_LOG_TIME

    now: float = time.time()
    if (now - _LAST_POS_LOG_TIME) >= 0.5:
        logger.debug(
            "[POS] x=%s/%s y=%s/%s",
            position.x,
            screen_geometry.width - 1,
            position.y,
            screen_geometry.height - 1,
        )
        _LAST_POS_LOG_TIME = now

    near_edge: bool = pointerNearEdge_check(position, screen_geometry)
    if near_edge:
        logger.debug("[EDGE] pos=(%s,%s) vel=%.1f", position.x, position.y, velocity)


def pointerNearEdge_check(position: Position, screen_geometry: Screen) -> bool:
    """
    Check whether pointer is near any local screen edge.

    Args:
        position:
            Current pointer position.
        screen_geometry:
            Local screen geometry.

    Returns:
        `True` when pointer is within 4 pixels of any edge.
    """
    near_horizontal_edge: bool = position.x >= screen_geometry.width - 5 or position.x <= 4
    near_vertical_edge: bool = position.y >= screen_geometry.height - 5 or position.y <= 4
    return near_horizontal_edge or near_vertical_edge


def contextDispatch_process(
    deps: PollingLoopDependencies,
    callbacks: PollingLoopCallbacks,
    server_state: ServerStateProtocol,
    position: Position,
    velocity: float,
) -> bool:
    """
    Dispatch context-specific processing for one polling tick.

    Args:
        deps:
            Runtime dependency bundle.
        callbacks:
            Callback bundle for CENTER and REMOTE handlers.
        server_state:
            Shared server state exposing current context.
        position:
            Current pointer position.
        velocity:
            Current pointer velocity.

    Returns:
        `True` when caller should treat the tick as already handled.
    """
    if server_state.context == ScreenContext.CENTER:
        return centerContextDispatch_process(deps, callbacks, position, velocity)

    remoteContextDispatch_process(deps, callbacks, position, velocity)
    return False


def centerContextDispatch_process(
    deps: PollingLoopDependencies,
    callbacks: PollingLoopCallbacks,
    position: Position,
    velocity: float,
) -> bool:
    """
    Execute CENTER-context processing path.

    Jump-hotkey handling is evaluated first because it may consume input and
    perform immediate context transition.

    Args:
        deps:
            Runtime dependency bundle.
        callbacks:
            Callback bundle containing CENTER and jump-hotkey handlers.
        position:
            Current pointer position.
        velocity:
            Current pointer velocity.

    Returns:
        `True` when jump-hotkey path handled this polling tick.
    """
    jump_handled: bool = centerJumpHotkey_process(deps, callbacks, position)
    if jump_handled:
        return True

    callbacks.centerContext_process(
        network=deps.network,
        display_manager=deps.display_manager,
        pointer_tracker=deps.pointer_tracker,
        screen_geometry=deps.screen_geometry,
        position=position,
        velocity=velocity,
        context_to_client=deps.context_to_client,
    )
    return False


def centerJumpHotkey_process(
    deps: PollingLoopDependencies,
    callbacks: PollingLoopCallbacks,
    position: Position,
) -> bool:
    """
    Evaluate and apply jump-hotkey actions while in CENTER context.

    Args:
        deps:
            Runtime dependency bundle.
        callbacks:
            Callback bundle containing hotkey parse/apply functions.
        position:
            Current pointer position used by action applier.

    Returns:
        `True` when a jump action is resolved and applied.
    """
    if not deps.jump_hotkey.enabled:
        return False

    input_events, modifier_state = deps.input_capturer.inputEvents_read()
    _, jump_target_context = callbacks.jumpHotkeyEvents_process(
        input_events=input_events,
        modifier_state=modifier_state,
        jump_hotkey=deps.jump_hotkey,
    )
    if jump_target_context is None:
        return False

    _ = callbacks.jumpHotkeyAction_apply(
        target_context=jump_target_context,
        network=deps.network,
        display_manager=deps.display_manager,
        pointer_tracker=deps.pointer_tracker,
        screen_geometry=deps.screen_geometry,
        position=position,
        context_to_client=deps.context_to_client,
    )
    return True


def remoteContextDispatch_process(
    deps: PollingLoopDependencies,
    callbacks: PollingLoopCallbacks,
    position: Position,
    velocity: float,
) -> None:
    """
    Execute REMOTE-context processing path.

    Args:
        deps:
            Runtime dependency bundle.
        callbacks:
            Callback bundle containing remote context handler.
        position:
            Current pointer position.
        velocity:
            Current pointer velocity.
    """
    callbacks.remoteContext_process(
        network=deps.network,
        display_manager=deps.display_manager,
        pointer_tracker=deps.pointer_tracker,
        screen_geometry=deps.screen_geometry,
        config=deps.config,
        position=position,
        velocity=velocity,
        context_to_client=deps.context_to_client,
        x11native=deps.x11native,
        input_capturer=deps.input_capturer,
        panic_keysyms=deps.panic_keysyms,
        panic_modifiers=deps.panic_modifiers,
        jump_hotkey=deps.jump_hotkey,
    )


def loopDelay_sleep(deps: PollingLoopDependencies) -> None:
    """
    Sleep for configured polling-loop delay.

    Args:
        deps:
            Runtime dependency bundle.
    """
    configured_interval_seconds: float = (
        deps.config.server.poll_interval_ms / settings.POLL_INTERVAL_DIVISOR
    )
    sleep_interval_seconds: float = max(_MIN_POLL_INTERVAL_SECONDS, configured_interval_seconds)
    time.sleep(sleep_interval_seconds)
