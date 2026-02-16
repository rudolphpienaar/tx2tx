"""Unit tests for pointer tracking and boundary detection"""

import pytest
import time
from unittest.mock import Mock
from tx2tx.common.types import Direction, Position, Screen
from tx2tx.x11.pointer import PointerTracker


class TestPointerTrackerVelocityCalculation:
    """Test velocity calculation logic"""

    @pytest.fixture
    def mock_display_manager(self):
        """Create mock DisplayManager"""
        return Mock()

    @pytest.fixture
    def tracker(self, mock_display_manager):
        """Create PointerTracker with mocked display"""
        return PointerTracker(
            display_manager=mock_display_manager, edge_threshold=5, velocity_threshold=100.0
        )

    def test_velocity_calculate_insufficient_samples(self, tracker):
        """Test velocity calculation with insufficient samples returns 0"""
        # Empty history
        velocity = tracker.velocity_calculate()
        assert velocity == 0.0

        # Add one position (still insufficient, needs 2+)
        tracker._position_history.append((Position(x=100, y=100), time.time()))
        velocity = tracker.velocity_calculate()
        assert velocity == 0.0

    def test_velocity_calculate_zero_time_delta(self, tracker):
        """Test velocity calculation with zero time delta returns 0"""
        same_time = time.time()
        tracker._position_history.append((Position(x=100, y=100), same_time))
        tracker._position_history.append((Position(x=200, y=200), same_time))

        velocity = tracker.velocity_calculate()
        assert velocity == 0.0

    def test_velocity_calculate_manhattan_distance(self, tracker):
        """Test velocity calculation uses Manhattan distance"""
        start_time = time.time()
        end_time = start_time + 1.0  # 1 second elapsed

        # Move 100 pixels right, 50 pixels down in 1 second
        tracker._position_history.append((Position(x=0, y=0), start_time))
        tracker._position_history.append((Position(x=100, y=50), end_time))

        velocity = tracker.velocity_calculate()

        # Manhattan distance = |100-0| + |50-0| = 150
        # Velocity = 150 / 1.0 = 150 px/s
        assert velocity == 150.0

    def test_velocity_calculate_fast_movement(self, tracker):
        """Test velocity calculation for fast pointer movement"""
        start_time = time.time()

        # Simulate fast horizontal movement: 500 pixels in 0.5 seconds
        tracker._position_history.append((Position(x=0, y=100), start_time))
        tracker._position_history.append((Position(x=500, y=100), start_time + 0.5))

        velocity = tracker.velocity_calculate()

        # Manhattan distance = 500, time = 0.5s
        # Velocity = 500 / 0.5 = 1000 px/s
        assert velocity == 1000.0

    def test_velocity_calculate_slow_movement(self, tracker):
        """Test velocity calculation for slow pointer movement"""
        start_time = time.time()

        # Simulate slow movement: 50 pixels in 1 second
        tracker._position_history.append((Position(x=100, y=100), start_time))
        tracker._position_history.append((Position(x=125, y=125), start_time + 1.0))

        velocity = tracker.velocity_calculate()

        # Manhattan distance = |25| + |25| = 50
        # Velocity = 50 / 1.0 = 50 px/s
        assert velocity == 50.0

    def test_velocity_calculate_multi_sample_history(self, tracker):
        """Test velocity calculation uses oldest and newest samples"""
        start_time = time.time()

        # Add multiple samples - velocity should be based on oldest to newest
        tracker._position_history.append((Position(x=0, y=0), start_time))
        tracker._position_history.append((Position(x=50, y=0), start_time + 0.25))
        tracker._position_history.append((Position(x=100, y=0), start_time + 0.5))
        tracker._position_history.append((Position(x=150, y=0), start_time + 0.75))
        tracker._position_history.append((Position(x=200, y=0), start_time + 1.0))

        velocity = tracker.velocity_calculate()

        # Should compare first (0,0) to last (200,0) over 1.0 second
        # Manhattan distance = 200, time = 1.0s
        # Velocity = 200 px/s
        assert velocity == 200.0


class TestPointerTrackerBoundaryDetection:
    """Test boundary detection logic"""

    @pytest.fixture
    def mock_display_manager(self):
        """Create mock DisplayManager"""
        return Mock()

    @pytest.fixture
    def tracker(self, mock_display_manager):
        """Create PointerTracker with mocked display"""
        return PointerTracker(
            display_manager=mock_display_manager, edge_threshold=5, velocity_threshold=100.0
        )

    @pytest.fixture
    def screen(self):
        """Create test screen geometry"""
        return Screen(width=1920, height=1080)

    def test_boundary_detect_left_edge_with_velocity(self, tracker, screen):
        """Test detection at left edge with sufficient velocity"""
        # Setup velocity history (fast leftward movement)
        start_time = time.time()
        tracker._position_history.append((Position(x=200, y=500), start_time))
        tracker._position_history.append((Position(x=0, y=500), start_time + 0.09))
        tracker._position_history.append((Position(x=0, y=500), start_time + 0.1))

        # Current position at strict left edge
        position = Position(x=0, y=500)
        transition = tracker.boundary_detect(position, screen)

        assert transition is not None
        assert transition.direction == Direction.LEFT
        assert transition.position == position

    def test_boundary_detect_right_edge_with_velocity(self, tracker, screen):
        """Test detection at right edge with sufficient velocity"""
        # Setup velocity history (fast rightward movement)
        start_time = time.time()
        tracker._position_history.append((Position(x=1700, y=500), start_time))
        tracker._position_history.append((Position(x=1919, y=500), start_time + 0.09))
        tracker._position_history.append((Position(x=1919, y=500), start_time + 0.1))

        # Current position at strict right edge (width - 1)
        position = Position(x=1919, y=500)
        transition = tracker.boundary_detect(position, screen)

        assert transition is not None
        assert transition.direction == Direction.RIGHT
        assert transition.position == position

    def test_boundary_detect_top_edge_with_velocity(self, tracker, screen):
        """Test detection at top edge with sufficient velocity"""
        # Setup velocity history (fast upward movement)
        start_time = time.time()
        tracker._position_history.append((Position(x=960, y=200), start_time))
        tracker._position_history.append((Position(x=960, y=0), start_time + 0.09))
        tracker._position_history.append((Position(x=960, y=0), start_time + 0.1))

        position = Position(x=960, y=0)
        transition = tracker.boundary_detect(position, screen)

        assert transition is not None
        assert transition.direction == Direction.TOP
        assert transition.position == position

    def test_boundary_detect_bottom_edge_with_velocity(self, tracker, screen):
        """Test detection at bottom edge with sufficient velocity"""
        # Setup velocity history (fast downward movement)
        start_time = time.time()
        tracker._position_history.append((Position(x=960, y=900), start_time))
        tracker._position_history.append((Position(x=960, y=1079), start_time + 0.09))
        tracker._position_history.append((Position(x=960, y=1079), start_time + 0.1))

        # Bottom edge: y == height - 1
        position = Position(x=960, y=1079)
        transition = tracker.boundary_detect(position, screen)

        assert transition is not None
        assert transition.direction == Direction.BOTTOM
        assert transition.position == position

    def test_boundary_detect_at_edge_insufficient_velocity(self, tracker, screen):
        """Test no transition at edge with insufficient velocity"""
        # Setup slow movement (velocity < 100 px/s)
        start_time = time.time()
        tracker._position_history.append((Position(x=50, y=500), start_time))
        tracker._position_history.append((Position(x=0, y=500), start_time + 1.0))  # Only 50 px/s

        # At left edge but moving slowly
        position = Position(x=0, y=500)
        transition = tracker.boundary_detect(position, screen)

        assert transition is None  # Not enough velocity

    def test_boundary_detect_center_screen_with_velocity(self, tracker, screen):
        """Test no transition in center of screen even with velocity"""
        # Setup fast movement
        start_time = time.time()
        tracker._position_history.append((Position(x=800, y=500), start_time))
        tracker._position_history.append((Position(x=960, y=500), start_time + 0.1))

        # Fast movement but not at boundary
        position = Position(x=960, y=500)
        transition = tracker.boundary_detect(position, screen)

        assert transition is None

    def test_boundary_detect_exactly_at_threshold(self, tracker, screen):
        """Test no detection at threshold distance when not at strict edge"""
        # Setup velocity history
        start_time = time.time()
        tracker._position_history.append((Position(x=200, y=500), start_time))
        tracker._position_history.append((Position(x=5, y=500), start_time + 0.1))

        # x=5 is not strict edge in strict-edge mode
        position = Position(x=5, y=500)
        transition = tracker.boundary_detect(position, screen)

        assert transition is None

    def test_boundary_detect_just_inside_threshold(self, tracker, screen):
        """Test no detection just inside boundary threshold"""
        # Setup velocity history
        start_time = time.time()
        tracker._position_history.append((Position(x=200, y=500), start_time))
        tracker._position_history.append((Position(x=6, y=500), start_time + 0.1))

        # x=6 is just outside the left edge threshold (> 5)
        position = Position(x=6, y=500)
        transition = tracker.boundary_detect(position, screen)

        assert transition is None

    def test_boundary_detect_requires_two_consecutive_edge_samples(self, tracker, screen):
        """Test edge transition requires confirmation sample."""
        start_time = time.time()
        tracker._position_history.append((Position(x=200, y=500), start_time))
        tracker._position_history.append((Position(x=0, y=500), start_time + 0.1))

        first_transition = tracker.boundary_detect(Position(x=0, y=500), screen)
        assert first_transition is None

        tracker._position_history.append((Position(x=0, y=500), start_time + 0.12))
        second_transition = tracker.boundary_detect(Position(x=0, y=500), screen)
        assert second_transition is not None
        assert second_transition.direction == Direction.LEFT


class TestPointerTrackerEdgeCases:
    """Test edge cases and special scenarios"""

    @pytest.fixture
    def mock_display_manager(self):
        """Create mock DisplayManager"""
        return Mock()

    def test_custom_velocity_threshold(self, mock_display_manager):
        """Test tracker with custom velocity threshold"""
        tracker = PointerTracker(
            display_manager=mock_display_manager,
            edge_threshold=10,
            velocity_threshold=500.0,  # Much higher threshold
        )

        assert tracker._velocity_threshold == 500.0
        assert tracker._edge_threshold == 10

    def test_default_velocity_threshold(self, mock_display_manager):
        """Test tracker uses default velocity threshold when not specified"""
        tracker = PointerTracker(display_manager=mock_display_manager, edge_threshold=5)

        # Should use settings.DEFAULT_VELOCITY_THRESHOLD (100.0)
        assert tracker._velocity_threshold == 100.0

    def test_zero_edge_threshold(self, mock_display_manager):
        """Test boundary detection with zero edge threshold"""
        tracker = PointerTracker(
            display_manager=mock_display_manager, edge_threshold=0, velocity_threshold=100.0
        )

        screen = Screen(width=1920, height=1080)

        # Setup velocity
        start_time = time.time()
        tracker._position_history.append((Position(x=200, y=500), start_time))
        tracker._position_history.append((Position(x=0, y=500), start_time + 0.09))
        tracker._position_history.append((Position(x=0, y=500), start_time + 0.1))

        # Should detect at x=0
        position = Position(x=0, y=500)
        transition = tracker.boundary_detect(position, screen)

        assert transition is not None
        assert transition.direction == Direction.LEFT

    def test_positionLast_get_initially_none(self, mock_display_manager):
        """Test last position is None initially"""
        tracker = PointerTracker(display_manager=mock_display_manager, edge_threshold=5)

        assert tracker.positionLast_get() is None

    def test_corner_positions_prioritize_horizontal(self, mock_display_manager):
        """Test that corner positions are detected correctly (left/right checked first)"""
        tracker = PointerTracker(
            display_manager=mock_display_manager, edge_threshold=5, velocity_threshold=100.0
        )

        screen = Screen(width=1920, height=1080)

        # Setup velocity
        start_time = time.time()
        tracker._position_history.append((Position(x=200, y=200), start_time))
        tracker._position_history.append((Position(x=0, y=0), start_time + 0.09))
        tracker._position_history.append((Position(x=0, y=0), start_time + 0.1))

        # Top-left corner - should detect LEFT (checked before TOP)
        position = Position(x=0, y=0)
        transition = tracker.boundary_detect(position, screen)

        assert transition is not None
        assert transition.direction == Direction.LEFT  # Not TOP
