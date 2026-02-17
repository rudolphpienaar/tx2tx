"""
Client message-dispatch and event-injection policies.

This module translates protocol messages into local injection operations and
contains the mouse normalization policy used by the client runtime.
"""

from __future__ import annotations

import logging

from tx2tx.common.types import EventType, MouseEvent
from tx2tx.input.backend import DisplayBackend, InputInjector
from tx2tx.protocol.message import Message, MessageParser, MessageType
from tx2tx.x11.software_cursor import SoftwareCursor

logger = logging.getLogger(__name__)

__all__ = [
    "serverMessage_handle",
    "mouseMessage_handle",
    "mouseEventForInjection_build",
    "keyMessage_handle",
]


def serverMessage_handle(
    message: Message,
    injector: InputInjector | None = None,
    display_manager: DisplayBackend | None = None,
    software_cursor: SoftwareCursor | None = None,
) -> None:
    """
    Dispatch a single server message to the proper handler.

    Args:
        message:
            Incoming protocol message.
        injector:
            Optional injector used for input replay.
        display_manager:
            Optional display backend.
        software_cursor:
            Optional software cursor overlay.
    """
    logger.info("Received %s from server", message.msg_type.value)

    if message.msg_type == MessageType.HELLO:
        logger.info("Server handshake: %s", message.payload)
        return
    if message.msg_type == MessageType.SCREEN_INFO:
        logger.info("Server screen info: %s", message.payload)
        return
    if message.msg_type == MessageType.SCREEN_LEAVE:
        logger.debug("Received SCREEN_LEAVE (informational)")
        return
    if message.msg_type == MessageType.SCREEN_ENTER:
        logger.debug("Received SCREEN_ENTER (informational)")
        return
    if message.msg_type == MessageType.MOUSE_EVENT:
        mouseMessage_handle(message, injector, display_manager, software_cursor)
        return
    if message.msg_type == MessageType.KEY_EVENT:
        keyMessage_handle(message, injector)
        return

    logger.debug("Message: %s", message.msg_type.value)


def mouseMessage_handle(
    message: Message,
    injector: InputInjector | None,
    display_manager: DisplayBackend | None,
    software_cursor: SoftwareCursor | None,
) -> None:
    """
    Handle incoming mouse event message.

    Args:
        message:
            Incoming protocol message.
        injector:
            Optional input injector.
        display_manager:
            Optional display backend.
        software_cursor:
            Optional software cursor.
    """
    if injector is None or display_manager is None:
        logger.warning("Received mouse event but injector or display_manager not available")
        return

    mouse_event: MouseEvent = MessageParser.mouseEvent_parse(message)
    actual_event: MouseEvent | None = mouseEventForInjection_build(
        mouse_event=mouse_event,
        display_manager=display_manager,
        software_cursor=software_cursor,
    )
    if actual_event is None:
        return

    try:
        injector.mouseEvent_inject(actual_event)
    except ValueError as exc:
        logger.warning("Failed to inject mouse event: %s", exc)
        return

    if actual_event.event_type == EventType.MOUSE_MOVE and actual_event.position is not None:
        logger.debug("Cursor at (%s, %s)", actual_event.position.x, actual_event.position.y)
        return
    logger.info("Mouse %s: button=%s", actual_event.event_type.value, actual_event.button)


def mouseEventForInjection_build(
    mouse_event: MouseEvent,
    display_manager: DisplayBackend,
    software_cursor: SoftwareCursor | None,
) -> MouseEvent | None:
    """
    Build local injection mouse event from protocol mouse message.

    Args:
        mouse_event:
            Parsed protocol mouse event.
        display_manager:
            Local display backend.
        software_cursor:
            Optional software cursor overlay.

    Returns:
        Injection-ready mouse event, or `None` for consume-only signals.
    """
    if mouse_event.normalized_point is None:
        return mouse_event

    norm_point = mouse_event.normalized_point
    if norm_point.x < 0 or norm_point.y < 0:
        if software_cursor is not None:
            software_cursor.hide()
        display_manager.cursor_hide()
        logger.info("Cursor hidden")
        return None

    client_screen = display_manager.screenGeometry_get()
    pixel_position = client_screen.coordinates_denormalize(norm_point)
    if software_cursor is not None:
        software_cursor.show()
        software_cursor.move(pixel_position.x, pixel_position.y)
    display_manager.cursor_show()
    return MouseEvent(
        event_type=mouse_event.event_type,
        position=pixel_position,
        button=mouse_event.button,
    )


def keyMessage_handle(message: Message, injector: InputInjector | None) -> None:
    """
    Handle incoming key event message.

    Args:
        message:
            Incoming protocol message.
        injector:
            Optional input injector.
    """
    if injector is None:
        logger.warning("Received key event but injector not available")
        return

    key_event = MessageParser.keyEvent_parse(message)
    injector.keyEvent_inject(key_event)
    if key_event.keysym is not None:
        logger.info(
            "Key %s: keycode=%s keysym=%#x",
            key_event.event_type.value,
            key_event.keycode,
            key_event.keysym,
        )
        return
    logger.info("Key %s: keycode=%s", key_event.event_type.value, key_event.keycode)
