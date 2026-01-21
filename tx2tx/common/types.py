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
    WEST = "west"  # West client has control, cursor hidden
    EAST = "east"  # East client has control, cursor hidden
    NORTH = "north"  # North client has control, cursor hidden
    SOUTH = "south"  # South client has control, cursor hidden


@dataclass(frozen=True)
class Position:
    """Absolute pixel position on a screen"""

    x: int
    y: int

    def bounds_check(self, width: int, height: int) -> bool:
        """Check if position is within given bounds"""
        return 0 <= self.x < width and 0 <= self.y < height


@dataclass(frozen=True)
class NormalizedPoint:
    """Normalized coordinates in 0.0-1.0 range

    Represents a position relative to screen dimensions where:
    - x: 0.0 = left edge, 1.0 = right edge
    - y: 0.0 = top edge, 1.0 = bottom edge

    Used for transmitting coordinates between screens of different resolutions.
    """

    x: float  # 0.0-1.0
    y: float  # 0.0-1.0

    def __post_init__(self) -> None:
        """Validate that coordinates are in valid range"""
        # Allow slightly out of bounds for edge cases (like hide signal at -1.0)
        if not (-1.0 <= self.x <= 1.0) or not (-1.0 <= self.y <= 1.0):
            raise ValueError(
                f"NormalizedPoint coordinates must be in range [-1.0, 1.0], got ({self.x}, {self.y})"
            )


@dataclass(frozen=True)
class Screen:
    """A display screen with dimensions and coordinate space

    Encapsulates both the physical properties of a screen (pixel dimensions)
    and provides coordinate transformation between pixel positions and
    normalized points.
    """

    width: int
    height: int

    def contains(self, pos: Position) -> bool:
        """Check if pixel position is within screen bounds"""
        return pos.bounds_check(self.width, self.height)

    def normalize(self, pos: Position) -> NormalizedPoint:
        """Convert pixel position to normalized point

        Args:
            pos: Absolute pixel position

        Returns:
            Normalized point in 0.0-1.0 range

        Example:
            screen = Screen(width=1920, height=1080)
            pos = Position(x=960, y=540)  # Center of screen
            npt = screen.normalize(pos)   # NormalizedPoint(x=0.5, y=0.5)
        """
        return NormalizedPoint(x=pos.x / self.width, y=pos.y / self.height)

    def denormalize(self, npt: NormalizedPoint) -> Position:
        """Convert normalized point to pixel position

        Args:
            npt: Normalized point in 0.0-1.0 range

        Returns:
            Absolute pixel position

        Example:
            screen = Screen(width=1920, height=1080)
            npt = NormalizedPoint(x=0.5, y=0.5)
            pos = screen.denormalize(npt)  # Position(x=960, y=540)
        """
        return Position(x=int(npt.x * self.width), y=int(npt.y * self.height))


# Backward compatibility alias
ScreenGeometry = Screen


@dataclass(frozen=True)
class MouseEvent:
    """Mouse event data

    Supports both pixel positions (for local event injection) and normalized
    coordinates (for protocol transmission between different resolution screens).

    For MOUSE_MOVE over protocol: use normalized_point
    For button events: use position (local pixel coordinates)
    """

    event_type: EventType
    position: Optional[Position] = None  # Pixel coordinates (local use)
    normalized_point: Optional[NormalizedPoint] = None  # Normalized coords (protocol use)
    button: Optional[int] = None  # 1=left, 2=middle, 3=right

    def __post_init__(self) -> None:
        """Validate that at least one position type is provided"""
        if self.position is None and self.normalized_point is None:
            raise ValueError("MouseEvent must have either position or normalized_point")

    def buttonEvent_check(self) -> bool:
        """Check if this is a button press/release event"""
        return self.event_type in (EventType.MOUSE_BUTTON_PRESS, EventType.MOUSE_BUTTON_RELEASE)


@dataclass(frozen=True)
class KeyEvent:
    """Keyboard event data"""

    event_type: EventType
    keycode: int
    keysym: Optional[int] = None
    state: Optional[int] = None  # X11 modifier state (server-side use only)

    def pressEvent_check(self) -> bool:
        """Check if this is a key press (vs release)"""
        return self.event_type == EventType.KEY_PRESS


@dataclass(frozen=True)
class ScreenTransition:
    """Screen boundary crossing event"""

    direction: Direction
    position: Position
