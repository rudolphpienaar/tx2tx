"""Network protocol messages for tx2tx communication"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

from tx2tx.common.types import (
    Direction,
    EventType,
    KeyEvent,
    MouseEvent,
    NormalizedPoint,
    Position,
    ScreenTransition,
)


class MessageType(Enum):
    """Types of protocol messages"""

    HELLO = "hello"
    SCREEN_INFO = "screen_info"
    SCREEN_ENTER = "screen_enter"
    SCREEN_LEAVE = "screen_leave"
    MOUSE_EVENT = "mouse_event"
    KEY_EVENT = "key_event"
    KEEPALIVE = "keepalive"
    HINT_SHOW = "hint_show"
    HINT_HIDE = "hint_hide"
    ERROR = "error"


@dataclass
class Message:
    """Base protocol message"""

    msg_type: MessageType
    payload: Dict[str, Any]

    def json_serialize(self) -> str:
        """
        Serialize message to JSON string
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        data = {"msg_type": self.msg_type.value, "payload": self.payload}
        return json.dumps(data)

    @staticmethod
    def json_deserialize(data: str) -> "Message":
        """
        Deserialize message from JSON string
        
        Args:
            data: JSON string
        
        Returns:
            Deserialized Message object
        """
        parsed = json.loads(data)
        msg_type = MessageType(parsed["msg_type"])
        payload = parsed["payload"]
        return Message(msg_type=msg_type, payload=payload)


class MessageBuilder:
    """Builds protocol messages from events and data"""

    @staticmethod
    def helloMessage_create(
        version: str = "0.1.0",
        screen_width: int | None = None,
        screen_height: int | None = None,
        client_name: str | None = None,
    ) -> Message:
        """
        Create hello/handshake message
        
        Args:
            version: version value.
            screen_width: screen_width value.
            screen_height: screen_height value.
            client_name: client_name value.
        
        Returns:
            Result value.
        """
        payload: dict[str, Any] = {"version": version}
        if screen_width is not None and screen_height is not None:
            payload["screen_width"] = screen_width
            payload["screen_height"] = screen_height
        if client_name is not None:
            payload["client_name"] = client_name

        return Message(msg_type=MessageType.HELLO, payload=payload)

    @staticmethod
    def screenInfoMessage_create(width: int, height: int) -> Message:
        """
        Create screen info message
        
        Args:
            width: width value.
            height: height value.
        
        Returns:
            Result value.
        """
        """Create screen info message"""
        return Message(msg_type=MessageType.SCREEN_INFO, payload={"width": width, "height": height})

    @staticmethod
    def screenEnterMessage_create(transition: ScreenTransition) -> Message:
        """
        Create screen enter message
        
        Args:
            transition: transition value.
        
        Returns:
            Result value.
        """
        """Create screen enter message"""
        return Message(
            msg_type=MessageType.SCREEN_ENTER,
            payload={
                "direction": transition.direction.value,
                "x": transition.position.x,
                "y": transition.position.y,
            },
        )

    @staticmethod
    def screenLeaveMessage_create(transition: ScreenTransition) -> Message:
        """
        Create screen leave message
        
        Args:
            transition: transition value.
        
        Returns:
            Result value.
        """
        """Create screen leave message"""
        return Message(
            msg_type=MessageType.SCREEN_LEAVE,
            payload={
                "direction": transition.direction.value,
                "x": transition.position.x,
                "y": transition.position.y,
            },
        )

    @staticmethod
    def mouseEventMessage_create(event: MouseEvent) -> Message:
        """
        Create mouse event message
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        payload: Dict[str, Any] = {
            "event_type": event.event_type.value,
        }

        # Prefer normalized_point for protocol (resolution-independent)
        if event.normalized_point is not None:
            payload["norm_x"] = event.normalized_point.x
            payload["norm_y"] = event.normalized_point.y
        elif event.position is not None:
            # Fallback to pixel position (for button events)
            payload["x"] = event.position.x
            payload["y"] = event.position.y
        else:
            raise ValueError("MouseEvent must have either position or normalized_point")

        if event.button is not None:
            payload["button"] = event.button

        return Message(msg_type=MessageType.MOUSE_EVENT, payload=payload)

    @staticmethod
    def keyEventMessage_create(event: KeyEvent) -> Message:
        """
        Create keyboard event message
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        """Create keyboard event message"""
        payload: Dict[str, Any] = {"event_type": event.event_type.value, "keycode": event.keycode}
        if event.keysym is not None:
            payload["keysym"] = event.keysym

        return Message(msg_type=MessageType.KEY_EVENT, payload=payload)

    @staticmethod
    def keepaliveMessage_create() -> Message:
        """
        Create keepalive message
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Create keepalive message"""
        return Message(msg_type=MessageType.KEEPALIVE, payload={})

    @staticmethod
    def errorMessage_create(error: str) -> Message:
        """
        Create error message
        
        Args:
            error: error value.
        
        Returns:
            Result value.
        """
        """Create error message"""
        return Message(msg_type=MessageType.ERROR, payload={"error": error})

    @staticmethod
    def hintShowMessage_create(label: str, timeout_ms: int) -> Message:
        """
        Create hint-show message.

        Args:
            label: Overlay label text.
            timeout_ms: Hide timeout in milliseconds.

        Returns:
            Hint-show message.
        """
        return Message(
            msg_type=MessageType.HINT_SHOW,
            payload={"label": label, "timeout_ms": timeout_ms},
        )

    @staticmethod
    def hintHideMessage_create() -> Message:
        """
        Create hint-hide message.

        Returns:
            Hint-hide message.
        """
        return Message(msg_type=MessageType.HINT_HIDE, payload={})


class MessageParser:
    """Parses protocol messages into events and data"""

    @staticmethod
    def mouseEvent_parse(msg: Message) -> MouseEvent:
        """
        Parse mouse event from message
        
        
        
        
        Deserializes mouse event from protocol. Handles both normalized coordinates
        (norm_x, norm_y) and pixel coordinates (x, y).
        
        Args:
            msg: Protocol message
        
        Returns:
            MouseEvent object
        """
        payload = msg.payload
        event_type = EventType(payload["event_type"])

        # Check for normalized coordinates (v2.0 protocol)
        if "norm_x" in payload and "norm_y" in payload:
            return MouseEvent(
                event_type=event_type,
                normalized_point=NormalizedPoint(x=payload["norm_x"], y=payload["norm_y"]),
                button=payload.get("button"),
            )
        # Fallback to pixel coordinates (v1.0 protocol or button events)
        elif "x" in payload and "y" in payload:
            return MouseEvent(
                event_type=event_type,
                position=Position(x=payload["x"], y=payload["y"]),
                button=payload.get("button"),
            )
        else:
            raise ValueError("MouseEvent message must contain either (norm_x, norm_y) or (x, y)")

    @staticmethod
    def keyEvent_parse(msg: Message) -> KeyEvent:
        """
        Parse key event from message
        
        Args:
            msg: Protocol message
        
        Returns:
            KeyEvent object
        """
        payload = msg.payload
        return KeyEvent(
            event_type=EventType(payload["event_type"]),
            keycode=payload["keycode"],
            keysym=payload.get("keysym"),
        )

    @staticmethod
    def screenTransition_parse(msg: Message) -> ScreenTransition:
        """
        Parse screen transition from message
        
        Args:
            msg: Protocol message
        
        Returns:
            ScreenTransition object
        """
        payload = msg.payload
        return ScreenTransition(
            direction=Direction(payload["direction"]),
            position=Position(x=payload["x"], y=payload["y"]),
        )
