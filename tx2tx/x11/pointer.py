"""X11 pointer tracking and boundary detection"""

import time
from collections import deque
from typing import Optional

from tx2tx.common.types import Direction, Position, ScreenGeometry, ScreenTransition
from tx2tx.x11.display import DisplayManager


class PointerTracker:
    """Tracks pointer position and detects screen boundary crossings"""

    def __init__(
        self,
        display_manager: DisplayManager,
        edge_threshold: int = 0,
        velocity_threshold: float = 100.0  # pixels per second
    ) -> None:
        """
        Initialize pointer tracker

        Args:
            display_manager: X11 display manager
            edge_threshold: Distance from edge (in pixels) to trigger transition
            velocity_threshold: Minimum velocity (px/s) required to cross boundary
        """
        self._display_manager: DisplayManager = display_manager
        self._edge_threshold: int = edge_threshold
        self._velocity_threshold: float = velocity_threshold
        self._last_position: Optional[Position] = None
        # Track recent positions for velocity calculation (position, timestamp)
        self._position_history: deque[tuple[Position, float]] = deque(maxlen=5)

    def position_query(self) -> Position:
        """
        Query current pointer position

        Returns:
            Current pointer position
        """
        display = self._display_manager.display_get()
        screen = display.screen()
        root = screen.root
        pointer_data = root.query_pointer()

        position = Position(x=pointer_data.root_x, y=pointer_data.root_y)
        self._last_position = position

        # Store in history with timestamp for velocity calculation
        self._position_history.append((position, time.time()))

        return position

    def velocity_calculate(self) -> float:
        """
        Calculate current pointer velocity based on recent position history

        Returns:
            Velocity in pixels per second (Manhattan distance)
        """
        if len(self._position_history) < 2:
            return 0.0

        # Compare most recent position to oldest in history
        oldest_pos, oldest_time = self._position_history[0]
        newest_pos, newest_time = self._position_history[-1]

        time_delta = newest_time - oldest_time
        if time_delta <= 0:
            return 0.0

        # Manhattan distance (simpler than Euclidean, good enough for velocity)
        distance = abs(newest_pos.x - oldest_pos.x) + abs(newest_pos.y - oldest_pos.y)

        return distance / time_delta

    def boundary_detect(
        self,
        position: Position,
        geometry: ScreenGeometry
    ) -> Optional[ScreenTransition]:
        """
        Detect if position is at screen boundary with sufficient velocity

        Args:
            position: Current pointer position
            geometry: Screen geometry

        Returns:
            ScreenTransition if at boundary with sufficient velocity, None otherwise
        """
        # First check if we're at a boundary
        at_boundary = False
        direction = None

        # Check left edge
        if position.x <= self._edge_threshold:
            at_boundary = True
            direction = Direction.LEFT

        # Check right edge
        elif position.x >= geometry.width - self._edge_threshold - 1:
            at_boundary = True
            direction = Direction.RIGHT

        # Check top edge
        elif position.y <= self._edge_threshold:
            at_boundary = True
            direction = Direction.TOP

        # Check bottom edge
        elif position.y >= geometry.height - self._edge_threshold - 1:
            at_boundary = True
            direction = Direction.BOTTOM

        # If at boundary, check velocity (momentum/edge resistance)
        if at_boundary and direction is not None:
            velocity = self.velocity_calculate()
            if velocity >= self._velocity_threshold:
                return ScreenTransition(direction=direction, position=position)
            # else: At boundary but not enough momentum - don't transition

        return None

    def positionLast_get(self) -> Optional[Position]:
        """Get last queried position"""
        return self._last_position
