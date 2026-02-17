"""Unit tests for protocol message serialization/deserialization"""

import pytest
from tx2tx.common.types import (
    Direction,
    EventType,
    KeyEvent,
    MouseEvent,
    NormalizedPoint,
    Position,
    ScreenTransition,
)
from tx2tx.protocol.message import Message, MessageBuilder, MessageParser, MessageType


class TestMessageSerialization:
    """Test Message JSON serialization"""

    def test_serialize_deserialize_round_trip(self):
        """Test message can be serialized and deserialized"""
        msg = Message(msg_type=MessageType.HELLO, payload={"version": "2.0.0", "test": "data"})

        json_str = msg.json_serialize()
        restored = Message.json_deserialize(json_str)

        assert restored.msg_type == msg.msg_type
        assert restored.payload == msg.payload

    def test_serialize_contains_msg_type(self):
        """Test serialized message contains msg_type field"""
        msg = Message(msg_type=MessageType.KEEPALIVE, payload={})
        json_str = msg.json_serialize()

        assert '"msg_type": "keepalive"' in json_str


class TestMessageBuilder:
    """Test MessageBuilder creates correct messages"""

    def test_hello_message(self):
        """Test HELLO message creation"""
        msg = MessageBuilder.helloMessage_create(
            version="2.0.0", screen_width=1920, screen_height=1080
        )

        assert msg.msg_type == MessageType.HELLO
        assert msg.payload["version"] == "2.0.0"
        assert msg.payload["screen_width"] == 1920
        assert msg.payload["screen_height"] == 1080

    def test_hello_message_with_client_name(self):
        """Test HELLO message creation with client name"""
        msg = MessageBuilder.helloMessage_create(
            version="2.0.0", screen_width=1920, screen_height=1080, client_name="phomux"
        )

        assert msg.msg_type == MessageType.HELLO
        assert msg.payload["client_name"] == "phomux"

    def test_hello_message_without_screen(self):
        """Test HELLO message without screen dimensions"""
        msg = MessageBuilder.helloMessage_create(version="2.0.0")

        assert msg.msg_type == MessageType.HELLO
        assert msg.payload["version"] == "2.0.0"
        assert "screen_width" not in msg.payload

    def test_screen_info_message(self):
        """Test SCREEN_INFO message creation"""
        msg = MessageBuilder.screenInfoMessage_create(width=2560, height=1440)

        assert msg.msg_type == MessageType.SCREEN_INFO
        assert msg.payload["width"] == 2560
        assert msg.payload["height"] == 1440

    def test_screen_enter_message(self):
        """Test SCREEN_ENTER message creation"""
        transition = ScreenTransition(direction=Direction.LEFT, position=Position(x=0, y=500))
        msg = MessageBuilder.screenEnterMessage_create(transition)

        assert msg.msg_type == MessageType.SCREEN_ENTER
        assert msg.payload["direction"] == "left"
        assert msg.payload["x"] == 0
        assert msg.payload["y"] == 500

    def test_mouse_event_with_normalized_point(self):
        """Test MOUSE_EVENT with normalized coordinates"""
        event = MouseEvent(
            event_type=EventType.MOUSE_MOVE, normalized_point=NormalizedPoint(x=0.5, y=0.75)
        )
        msg = MessageBuilder.mouseEventMessage_create(event)

        assert msg.msg_type == MessageType.MOUSE_EVENT
        assert msg.payload["event_type"] == "mouse_move"
        assert msg.payload["norm_x"] == 0.5
        assert msg.payload["norm_y"] == 0.75
        assert "x" not in msg.payload  # Should use norm_x, not x

    def test_mouse_event_with_pixel_position(self):
        """Test MOUSE_EVENT with pixel coordinates (fallback)"""
        event = MouseEvent(
            event_type=EventType.MOUSE_BUTTON_PRESS, position=Position(x=100, y=200), button=1
        )
        msg = MessageBuilder.mouseEventMessage_create(event)

        assert msg.msg_type == MessageType.MOUSE_EVENT
        assert msg.payload["event_type"] == "mouse_button_press"
        assert msg.payload["x"] == 100
        assert msg.payload["y"] == 200
        assert msg.payload["button"] == 1

    def test_mouse_event_hide_signal(self):
        """Test MOUSE_EVENT hide signal (negative coordinates)"""
        event = MouseEvent(
            event_type=EventType.MOUSE_MOVE, normalized_point=NormalizedPoint(x=-1.0, y=-1.0)
        )
        msg = MessageBuilder.mouseEventMessage_create(event)

        assert msg.payload["norm_x"] == -1.0
        assert msg.payload["norm_y"] == -1.0

    def test_key_event_message(self):
        """Test KEY_EVENT message creation"""
        event = KeyEvent(event_type=EventType.KEY_PRESS, keycode=65, keysym=0x0041)  # 'A'
        msg = MessageBuilder.keyEventMessage_create(event)

        assert msg.msg_type == MessageType.KEY_EVENT
        assert msg.payload["event_type"] == "key_press"
        assert msg.payload["keycode"] == 65
        assert msg.payload["keysym"] == 0x0041

    def test_keepalive_message(self):
        """Test KEEPALIVE message creation"""
        msg = MessageBuilder.keepaliveMessage_create()

        assert msg.msg_type == MessageType.KEEPALIVE
        assert msg.payload == {}

    def test_error_message(self):
        """Test ERROR message creation"""
        msg = MessageBuilder.errorMessage_create("Connection failed")

        assert msg.msg_type == MessageType.ERROR
        assert msg.payload["error"] == "Connection failed"


class TestMessageParser:
    """Test MessageParser extracts correct data"""

    def test_parse_mouse_event_normalized(self):
        """Test parsing MOUSE_EVENT with normalized coordinates"""
        msg = Message(
            msg_type=MessageType.MOUSE_EVENT,
            payload={"event_type": "mouse_move", "norm_x": 0.5, "norm_y": 0.75},
        )

        event = MessageParser.mouseEvent_parse(msg)

        assert event.event_type == EventType.MOUSE_MOVE
        assert event.normalized_point is not None
        assert event.normalized_point.x == 0.5
        assert event.normalized_point.y == 0.75
        assert event.position is None

    def test_parse_mouse_event_pixels(self):
        """Test parsing MOUSE_EVENT with pixel coordinates"""
        msg = Message(
            msg_type=MessageType.MOUSE_EVENT,
            payload={"event_type": "mouse_button_press", "x": 100, "y": 200, "button": 1},
        )

        event = MessageParser.mouseEvent_parse(msg)

        assert event.event_type == EventType.MOUSE_BUTTON_PRESS
        assert event.position is not None
        assert event.position.x == 100
        assert event.position.y == 200
        assert event.button == 1
        assert event.normalized_point is None

    def test_parse_mouse_event_missing_coords(self):
        """Test parsing MOUSE_EVENT without coordinates raises error"""
        msg = Message(msg_type=MessageType.MOUSE_EVENT, payload={"event_type": "mouse_move"})

        with pytest.raises(ValueError, match="must contain either"):
            MessageParser.mouseEvent_parse(msg)

    def test_parse_key_event(self):
        """Test parsing KEY_EVENT"""
        msg = Message(
            msg_type=MessageType.KEY_EVENT,
            payload={"event_type": "key_press", "keycode": 65, "keysym": 0x0041},
        )

        event = MessageParser.keyEvent_parse(msg)

        assert event.event_type == EventType.KEY_PRESS
        assert event.keycode == 65
        assert event.keysym == 0x0041

    def test_parse_key_event_without_keysym(self):
        """Test parsing KEY_EVENT without keysym"""
        msg = Message(
            msg_type=MessageType.KEY_EVENT, payload={"event_type": "key_release", "keycode": 65}
        )

        event = MessageParser.keyEvent_parse(msg)

        assert event.event_type == EventType.KEY_RELEASE
        assert event.keycode == 65
        assert event.keysym is None

    def test_parse_screen_transition(self):
        """Test parsing SCREEN_ENTER/LEAVE"""
        msg = Message(
            msg_type=MessageType.SCREEN_ENTER, payload={"direction": "left", "x": 0, "y": 540}
        )

        transition = MessageParser.screenTransition_parse(msg)

        assert transition.direction == Direction.LEFT
        assert transition.position.x == 0
        assert transition.position.y == 540


class TestProtocolRoundTrip:
    """Test complete message round-trip (build → serialize → deserialize → parse)"""

    def test_mouse_move_round_trip(self):
        """Test MOUSE_MOVE with normalized coordinates survives round-trip"""
        # Build
        original_event = MouseEvent(
            event_type=EventType.MOUSE_MOVE, normalized_point=NormalizedPoint(x=0.3, y=0.7)
        )
        msg = MessageBuilder.mouseEventMessage_create(original_event)

        # Serialize
        json_str = msg.json_serialize()

        # Deserialize
        restored_msg = Message.json_deserialize(json_str)

        # Parse
        restored_event = MessageParser.mouseEvent_parse(restored_msg)

        assert restored_event.event_type == original_event.event_type
        assert restored_event.normalized_point.x == original_event.normalized_point.x
        assert restored_event.normalized_point.y == original_event.normalized_point.y

    def test_screen_transition_round_trip(self):
        """Test SCREEN_ENTER survives round-trip"""
        original = ScreenTransition(direction=Direction.RIGHT, position=Position(x=1919, y=500))
        msg = MessageBuilder.screenEnterMessage_create(original)

        json_str = msg.json_serialize()
        restored_msg = Message.json_deserialize(json_str)
        restored = MessageParser.screenTransition_parse(restored_msg)

        assert restored.direction == original.direction
        assert restored.position.x == original.position.x
        assert restored.position.y == original.position.y
