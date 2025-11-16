"""Common types and data structures for tx2tx"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EventType(Enum):
    """Types of input events"""
    MOUSE_MOVE = "mouse_move"
    MOUSE_BUTTON_PRESS = "mouse_button_press"
    MOUSE_BUTTON_RELEASE = "mouse_button_release"
    KEY_PRESS = "key_press"
    KEY_RELEASE = "key_release"
    SCREEN_ENTER = "screen_enter"
    SCREEN_LEAVE = "screen_leave"


class Direction(Enum):
    """Screen edge directions"""
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class ScreenContext(Enum):
    """Global context - which screen has active control"""
    CENTER = "center"  # Server has control, cursor shown
    WEST = "west"      # West client has control, cursor hidden
    EAST = "east"      # East client has control, cursor hidden
    NORTH = "north"    # North client has control, cursor hidden
    SOUTH = "south"    # South client has control, cursor hidden


@dataclass(frozen=True)
class Position:
    """2D position coordinates"""
    x: int
    y: int

    def isWithinBounds(self, width: int, height: int) -> bool:
        """Check if position is within given bounds"""
        return 0 <= self.x < width and 0 <= self.y < height


@dataclass(frozen=True)
class ScreenGeometry:
    """Screen dimensions and properties"""
    width: int
    height: int

    def contains(self, pos: Position) -> bool:
        """Check if position is within screen bounds"""
        return pos.isWithinBounds(self.width, self.height)


@dataclass(frozen=True)
class MouseEvent:
    """Mouse event data"""
    event_type: EventType
    position: Position
    button: Optional[int] = None  # 1=left, 2=middle, 3=right

    def isButtonEvent(self) -> bool:
        """Check if this is a button press/release event"""
        return self.event_type in (
            EventType.MOUSE_BUTTON_PRESS,
            EventType.MOUSE_BUTTON_RELEASE
        )


@dataclass(frozen=True)
class KeyEvent:
    """Keyboard event data"""
    event_type: EventType
    keycode: int
    keysym: Optional[int] = None

    def isPressEvent(self) -> bool:
        """Check if this is a key press (vs release)"""
        return self.event_type == EventType.KEY_PRESS


@dataclass(frozen=True)
class ScreenTransition:
    """Screen boundary crossing event"""
    direction: Direction
    position: Position
