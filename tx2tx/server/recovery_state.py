"""
Server recovery and CENTER revert policy.

This module owns the state and display recovery sequence used when server logic
must force a return from REMOTE to CENTER context. The workflow keeps input
unlocking and cursor restoration deterministic while isolating side-effect-heavy
operations from runtime orchestration code.
"""

from __future__ import annotations

import time
from typing import Protocol

from tx2tx.common.types import Position, Screen, ScreenContext
from tx2tx.input.backend import DisplayBackend
from tx2tx.server.state import RuntimeStateProtocol
from tx2tx.x11.pointer import PointerTracker

__all__ = [
    "state_revertToCenter",
    "runtimeStateForCenterRevert_update",
    "centerRevertEntryPosition_get",
    "displayUngrabForCenterRevert_attempt",
    "cursorShowForCenterRevert_apply",
    "cursorWarpForCenterRevert_attempt",
    "localInputUnlock_bestEffort",
]

_REVERT_ENTRY_OFFSET_PX: int = 30
_UNGRAB_SETTLE_SECONDS: float = 0.05
_CURSOR_SHOW_SETTLE_SECONDS: float = 0.05


class LoggerProtocol(Protocol):
    """Minimal logger contract for recovery policy."""

    def info(self, msg: str, *args: object) -> None:
        """Emit info-level message."""
        ...

    def warning(self, msg: str, *args: object) -> None:
        """Emit warning-level message."""
        ...

    def error(self, msg: str, *args: object) -> None:
        """Emit error-level message."""
        ...


def state_revertToCenter(
    display_manager: DisplayBackend,
    screen_geometry: Screen,
    position: Position,
    pointer_tracker: PointerTracker,
    runtime_state: RuntimeStateProtocol,
    logger: LoggerProtocol,
) -> None:
    """
    Revert runtime from REMOTE context back to CENTER safely.

    Args:
        display_manager:
            Active display backend.
        screen_geometry:
            Local screen geometry.
        position:
            Current pointer position.
        pointer_tracker:
            Pointer tracker to reset after revert.
        runtime_state:
            Mutable runtime-state instance.
        logger:
            Runtime logger.
    """
    if runtime_state.context == ScreenContext.CENTER:
        return

    logger.warning("[SAFETY] Reverting from %s to CENTER", runtime_state.context.value.upper())

    previous_context: ScreenContext = runtimeStateForCenterRevert_update(runtime_state)
    entry_position: Position = centerRevertEntryPosition_get(
        previous_context=previous_context,
        current_position=position,
        screen_geometry=screen_geometry,
    )

    try:
        displayUngrabForCenterRevert_attempt(display_manager, logger)
        cursorShowForCenterRevert_apply(display_manager)
        cursorWarpForCenterRevert_attempt(display_manager, entry_position, logger)
        pointer_tracker.reset()
        logger.info("[STATE] → CENTER (revert) - Cursor at (%s, %s)", entry_position.x, entry_position.y)
    except Exception as exc:
        logger.error("Emergency revert failed: %s", exc)
        localInputUnlock_bestEffort(display_manager)


def runtimeStateForCenterRevert_update(runtime_state: RuntimeStateProtocol) -> ScreenContext:
    """
    Update runtime state fields for forced transition into CENTER.

    Args:
        runtime_state:
            Mutable runtime-state instance.

    Returns:
        Previous context before switching to CENTER.
    """
    runtime_state.boundaryCrossed_clear()
    runtime_state.last_sent_position = None
    runtime_state.active_remote_client_name = None

    previous_context: ScreenContext = runtime_state.context
    runtime_state.context = ScreenContext.CENTER
    runtime_state.last_center_switch_time = time.time()
    return previous_context


def centerRevertEntryPosition_get(
    previous_context: ScreenContext,
    current_position: Position,
    screen_geometry: Screen,
) -> Position:
    """
    Calculate safe CENTER entry position based on previous REMOTE context.

    Args:
        previous_context:
            Context prior to revert.
        current_position:
            Current pointer position.
        screen_geometry:
            Local screen geometry.

    Returns:
        Entry position located safely inside local display bounds.
    """
    if previous_context == ScreenContext.WEST:
        return Position(x=_REVERT_ENTRY_OFFSET_PX, y=current_position.y)
    if previous_context == ScreenContext.EAST:
        return Position(x=screen_geometry.width - _REVERT_ENTRY_OFFSET_PX, y=current_position.y)
    if previous_context == ScreenContext.NORTH:
        return Position(x=current_position.x, y=_REVERT_ENTRY_OFFSET_PX)
    return Position(x=current_position.x, y=screen_geometry.height - _REVERT_ENTRY_OFFSET_PX)


def displayUngrabForCenterRevert_attempt(
    display_manager: DisplayBackend,
    logger: LoggerProtocol,
) -> None:
    """
    Attempt keyboard/pointer ungrab sequence before CENTER warp.

    Args:
        display_manager:
            Active display backend.
        logger:
            Runtime logger.
    """
    try:
        display_manager.keyboard_ungrab()
        display_manager.pointer_ungrab()
        display_manager.connection_sync()
        time.sleep(_UNGRAB_SETTLE_SECONDS)
    except Exception as exc:
        logger.warning("Ungrab failed: %s", exc)


def cursorShowForCenterRevert_apply(display_manager: DisplayBackend) -> None:
    """
    Ensure cursor is visible before final CENTER entry warp.

    Args:
        display_manager:
            Active display backend.
    """
    display_manager.cursor_show()
    display_manager.connection_sync()
    time.sleep(_CURSOR_SHOW_SETTLE_SECONDS)


def cursorWarpForCenterRevert_attempt(
    display_manager: DisplayBackend,
    entry_position: Position,
    logger: LoggerProtocol,
) -> None:
    """
    Attempt final cursor warp to post-revert CENTER entry position.

    Args:
        display_manager:
            Active display backend.
        entry_position:
            Calculated safe CENTER entry position.
        logger:
            Runtime logger.
    """
    try:
        logger.info(
            "[WARP RETURN] Teleporting to entry position (%s, %s)",
            entry_position.x,
            entry_position.y,
        )
        display_manager.cursorPosition_set(entry_position)
        display_manager.connection_sync()
    except Exception as exc:
        logger.error("Warp failed during revert: %s", exc)


def localInputUnlock_bestEffort(display_manager: DisplayBackend) -> None:
    """
    Best-effort local input unlock fallback for failed revert sequence.

    Args:
        display_manager:
            Active display backend.
    """
    try:
        display_manager.cursor_show()
        display_manager.keyboard_ungrab()
        display_manager.pointer_ungrab()
    except Exception:
        pass
