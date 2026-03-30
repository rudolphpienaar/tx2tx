"""Backend-neutral pointer tracking and boundary detection."""

import logging
import time
from collections import deque
from typing import Optional

from tx2tx.common.settings import settings
from tx2tx.common.types import Direction, Position, ScreenGeometry, ScreenTransition
from tx2tx.input.backend import DisplayBackend

logger = logging.getLogger(__name__)


class PointerTracker:
    """Tracks pointer position and detects screen boundary crossings."""

    def __init__(
        self,
        display_manager: DisplayBackend,
        edge_threshold: int = 0,
        velocity_threshold: float | None = None,
    ) -> None:
        self._display_manager: DisplayBackend = display_manager
        self._edge_threshold: int = edge_threshold
        self._velocity_threshold: float = (
            velocity_threshold
            if velocity_threshold is not None
            else settings.DEFAULT_VELOCITY_THRESHOLD
        )
        self._last_position: Optional[Position] = None
        self._position_history: deque[tuple[Position, float]] = deque(
            maxlen=settings.POSITION_HISTORY_SIZE
        )
        self._edge_contact_direction: Direction | None = None
        self._edge_contact_started_at: float = 0.0
        self._edge_contact_samples: int = 0

    def position_query(self) -> Position:
        position = self._display_manager.pointerPosition_get()
        self._last_position = position
        self._position_history.append((position, time.time()))
        return position

    def velocity_calculate(self) -> float:
        if len(self._position_history) < settings.MIN_SAMPLES_FOR_VELOCITY:
            return 0.0

        oldest_pos, oldest_time = self._position_history[0]
        newest_pos, newest_time = self._position_history[-1]
        time_delta = newest_time - oldest_time
        if time_delta <= 0:
            return 0.0

        distance = abs(newest_pos.x - oldest_pos.x) + abs(newest_pos.y - oldest_pos.y)
        return distance / time_delta

    def boundary_detect(
        self, position: Position, geometry: ScreenGeometry
    ) -> Optional[ScreenTransition]:
        direction: Direction | None = self.boundaryDirectionFromPosition_get(position, geometry)
        if direction is None:
            self._edgeContact_reset()
            return None

        self._edgeContact_update(direction)
        if not self._edgeContactConfirmed_check():
            logger.debug(
                "Boundary %s seen but awaiting confirmation (%s/%s)",
                direction.value,
                self._edge_contact_samples,
                settings.EDGE_CONFIRMATION_SAMPLES,
            )
            return None
        if not self._edgeContactDwellElapsed_check():
            logger.debug(
                "Boundary %s confirmed but awaiting dwell %.3fs/%.3fs",
                direction.value,
                self._edgeContactElapsed_seconds(),
                settings.EDGE_DWELL_SECONDS,
            )
            return None
        transition: ScreenTransition = ScreenTransition(direction=direction, position=position)
        self._edgeContact_reset()
        return transition

    def _edgeContact_update(self, direction: Direction) -> None:
        now: float = time.time()
        if self._edge_contact_direction != direction:
            self._edge_contact_direction = direction
            self._edge_contact_started_at = now
            self._edge_contact_samples = 1
            return
        self._edge_contact_samples += 1

    def _edgeContactConfirmed_check(self) -> bool:
        return self._edge_contact_samples >= settings.EDGE_CONFIRMATION_SAMPLES

    def _edgeContactElapsed_seconds(self) -> float:
        if self._edge_contact_started_at <= 0.0:
            return 0.0
        return time.time() - self._edge_contact_started_at

    def _edgeContactDwellElapsed_check(self) -> bool:
        return self._edgeContactElapsed_seconds() >= settings.EDGE_DWELL_SECONDS

    def _edgeContact_reset(self) -> None:
        self._edge_contact_direction = None
        self._edge_contact_started_at = 0.0
        self._edge_contact_samples = 0

    @staticmethod
    def boundaryDirectionFromPosition_get(
        position: Position, geometry: ScreenGeometry
    ) -> Direction | None:
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
        self._position_history.clear()
        self._last_position = None
        self._edgeContact_reset()

    def positionLast_get(self) -> Optional[Position]:
        return self._last_position
