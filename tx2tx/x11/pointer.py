"""Pointer tracking and boundary detection"""

import logging
import time
from collections import deque
from typing import Optional

from tx2tx.common.settings import settings
from tx2tx.common.types import Direction, Position, ScreenGeometry, ScreenTransition
from tx2tx.input.backend import DisplayBackend

logger = logging.getLogger(__name__)


class PointerTracker:
    """Tracks pointer position and detects screen boundary crossings"""

    def __init__(
        self,
        display_manager: DisplayBackend,
        edge_threshold: int = 0,
        velocity_threshold: float | None = None,
    ) -> None:
        """
        Initialize pointer tracker
        
        Args:
            display_manager: display_manager value.
            edge_threshold: edge_threshold value.
            velocity_threshold: velocity_threshold value.
        
        Returns:
            Result value.
        """
        self._display_manager: DisplayBackend = display_manager
        self._edge_threshold: int = edge_threshold
        self._velocity_threshold: float = (
            velocity_threshold
            if velocity_threshold is not None
            else settings.DEFAULT_VELOCITY_THRESHOLD
        )
        self._last_position: Optional[Position] = None
        # Track recent positions for velocity calculation (position, timestamp)
        self._position_history: deque[tuple[Position, float]] = deque(
            maxlen=settings.POSITION_HISTORY_SIZE
        )

    def position_query(self) -> Position:
        """
        Query current pointer position
        
        Args:
            None.
        
        Returns:
            Current pointer position.
        """
        position = self._display_manager.pointerPosition_get()
        self._last_position = position

        # Store in history with timestamp for velocity calculation
        self._position_history.append((position, time.time()))

        return position

    def velocity_calculate(self) -> float:
        """
        Calculate current pointer velocity based on recent position history
        
        Args:
            None.
        
        Returns:
            Pointer velocity in pixels per second.
        """
        if len(self._position_history) < settings.MIN_SAMPLES_FOR_VELOCITY:
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
        self, position: Position, geometry: ScreenGeometry
    ) -> Optional[ScreenTransition]:
        """
        Detect if position is at screen boundary with sufficient velocity
        
        Args:
            position: Current pointer position
            geometry: Screen geometry
        
        Returns:
            ScreenTransition if at boundary with sufficient velocity, None otherwise
        """
        direction: Direction | None = self.boundaryDirectionFromPosition_get(position, geometry)
        if direction is None:
            return None

        if settings.EDGE_CONFIRMATION_SAMPLES > 1 and len(self._position_history) >= 2:
            previous_position: Position = self._position_history[-2][0]
            previous_direction: Direction | None = self.boundaryDirectionFromPosition_get(
                previous_position, geometry
            )
            if previous_direction != direction:
                logger.debug(
                    "Boundary %s seen but awaiting confirmation sample (prev=%s)",
                    direction.value,
                    previous_direction.value if previous_direction else "none",
                )
                return None

        # If at boundary, check velocity (momentum/edge resistance)
        velocity = self.velocity_calculate()
        logger.info(
            f"At boundary {direction.value}: velocity={velocity:.1f}, threshold={self._velocity_threshold}"
        )
        if velocity >= self._velocity_threshold:
            return ScreenTransition(direction=direction, position=position)
        # else: At boundary but not enough momentum - don't transition

        return None

    @staticmethod
    def boundaryDirectionFromPosition_get(
        position: Position, geometry: ScreenGeometry
    ) -> Direction | None:
        """
        Resolve strict boundary direction for a position.

        Args:
            position: Pointer position.
            geometry: Screen geometry.

        Returns:
            Boundary direction if at strict edge, else None.
        """
        if position.x <= 0:
            return Direction.LEFT
        if position.x >= geometry.width - 1:
            return Direction.RIGHT
        if position.y <= 0:
            return Direction.TOP
        if position.y >= geometry.height - 1:
            return Direction.BOTTOM
        return None

    def reset(self) -> None:
        """
        Reset tracker state (clear history)
        
        
        
        Useful after forced cursor moves (warps) to prevent false velocity spikes
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        self._position_history.clear()
        self._last_position = None

    def positionLast_get(self) -> Optional[Position]:
        """
        Get last queried position
        
        Args:
            None.
        
        Returns:
            Last tracked pointer position, if any.
        """
        """Get last queried position"""
        return self._last_position
