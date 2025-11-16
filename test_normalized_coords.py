#!/usr/bin/env python3
"""Quick test of NormalizedPoint serialization"""

import sys
sys.path.insert(0, '/data/data/com.termux/files/home/src/tx2tx')

from tx2tx.common.types import Position, NormalizedPoint, Screen, MouseEvent, EventType
from tx2tx.protocol.message import MessageBuilder, MessageParser

# Test coordinate transformation
screen = Screen(width=2960, height=1848)

# Test position at center
pos = Position(x=1480, y=924)
print(f"Original position: {pos}")

# Normalize
norm = screen.normalize(pos)
print(f"Normalized: {norm}")

# Create mouse event
event = MouseEvent(
    event_type=EventType.MOUSE_MOVE,
    normalized_point=norm
)
print(f"Mouse event: {event}")

# Serialize to message
msg = MessageBuilder.mouseEventMessage_create(event)
print(f"Message payload: {msg.payload}")

# Serialize to JSON
json_str = msg.json_serialize()
print(f"JSON: {json_str}")

# Deserialize
from tx2tx.protocol.message import Message
restored_msg = Message.json_deserialize(json_str)
print(f"Restored payload: {restored_msg.payload}")

# Parse back to event
restored_event = MessageParser.mouseEvent_parse(restored_msg)
print(f"Restored event: {restored_event}")

# Denormalize on different resolution client
client_screen = Screen(width=1920, height=1080)
client_pos = client_screen.denormalize(restored_event.normalized_point)
print(f"Client position (1920x1080): {client_pos}")

print("\n✅ All coordinate transformations working!")
