"""X11 pointer tracking and boundary detection"""

from typing import Optional

from tx2tx.common.types import Direction, Position, ScreenGeometry, ScreenTransition
from tx2tx.x11.display import DisplayManager


class PointerTracker:
    """Tracks pointer position and detects screen boundary crossings"""

    def __init__(
        self,
        display_manager: DisplayManager,
        edge_threshold: int = 0
    ) -> None:
        """
        Initialize pointer tracker

        Args:
            display_manager: X11 display manager
            edge_threshold: Distance from edge (in pixels) to trigger transition
        """
        self._display_manager: DisplayManager = display_manager
        self._edge_threshold: int = edge_threshold
        self._last_position: Optional[Position] = None

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

        return position

    def boundary_detect(
        self,
        position: Position,
        geometry: ScreenGeometry
    ) -> Optional[ScreenTransition]:
        """
        Detect if position is at screen boundary

        Args:
            position: Current pointer position
            geometry: Screen geometry

        Returns:
            ScreenTransition if at boundary, None otherwise
        """
        # Check left edge
        if position.x <= self._edge_threshold:
            return ScreenTransition(direction=Direction.LEFT, position=position)

        # Check right edge
        if position.x >= geometry.width - self._edge_threshold - 1:
            return ScreenTransition(direction=Direction.RIGHT, position=position)

        # Check top edge
        if position.y <= self._edge_threshold:
            return ScreenTransition(direction=Direction.TOP, position=position)

        # Check bottom edge
        if position.y >= geometry.height - self._edge_threshold - 1:
            return ScreenTransition(direction=Direction.BOTTOM, position=position)

        return None

    def positionLast_get(self) -> Optional[Position]:
        """Get last queried position"""
        return self._last_position
