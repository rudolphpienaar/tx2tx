"""Unit tests for common types (Position, NormalizedPoint, Screen)"""

import pytest
from tx2tx.common.types import Position, NormalizedPoint, Screen


class TestPosition:
    """Test Position dataclass"""

    def test_creation(self):
        """Test Position creation"""
        pos = Position(x=100, y=200)
        assert pos.x == 100
        assert pos.y == 200

    def test_immutable(self):
        """Test Position is immutable"""
        pos = Position(x=100, y=200)
        with pytest.raises(AttributeError):
            pos.x = 300

    def test_isWithinBounds(self):
        """Test boundary checking"""
        pos = Position(x=100, y=200)
        assert pos.isWithinBounds(1920, 1080) is True
        assert pos.isWithinBounds(50, 50) is False


class TestNormalizedPoint:
    """Test NormalizedPoint dataclass"""

    def test_creation_valid(self):
        """Test NormalizedPoint creation with valid coords"""
        npt = NormalizedPoint(x=0.5, y=0.75)
        assert npt.x == 0.5
        assert npt.y == 0.75

    def test_creation_invalid(self):
        """Test NormalizedPoint rejects out-of-bounds coords"""
        with pytest.raises(ValueError):
            NormalizedPoint(x=1.5, y=0.5)  # x too large
        with pytest.raises(ValueError):
            NormalizedPoint(x=0.5, y=-2.0)  # y too small

    def test_negative_coords_allowed(self):
        """Test that negative coords are allowed (for hide signal)"""
        npt = NormalizedPoint(x=-1.0, y=-1.0)
        assert npt.x == -1.0
        assert npt.y == -1.0

    def test_immutable(self):
        """Test NormalizedPoint is immutable"""
        npt = NormalizedPoint(x=0.5, y=0.5)
        with pytest.raises(AttributeError):
            npt.x = 0.7


class TestScreen:
    """Test Screen class"""

    def test_creation(self):
        """Test Screen creation"""
        screen = Screen(width=1920, height=1080)
        assert screen.width == 1920
        assert screen.height == 1080

    def test_contains(self):
        """Test Screen.contains() method"""
        screen = Screen(width=1920, height=1080)
        assert screen.contains(Position(x=960, y=540)) is True
        assert screen.contains(Position(x=2000, y=540)) is False

    def test_normalize(self):
        """Test pixel to normalized coordinate conversion"""
        screen = Screen(width=1920, height=1080)

        # Center of screen
        pos = Position(x=960, y=540)
        npt = screen.normalize(pos)
        assert npt.x == 0.5
        assert npt.y == 0.5

        # Top-left corner
        pos = Position(x=0, y=0)
        npt = screen.normalize(pos)
        assert npt.x == 0.0
        assert npt.y == 0.0

        # Bottom-right corner
        pos = Position(x=1920, y=1080)
        npt = screen.normalize(pos)
        assert npt.x == 1.0
        assert npt.y == 1.0

    def test_normalize_clamps_out_of_bounds(self):
        """Test normalize clamps coordinates to valid bounds before conversion."""
        screen = Screen(width=1920, height=1080)

        below_zero = Position(x=-10, y=-5)
        below_zero_npt = screen.normalize(below_zero)
        assert below_zero_npt.x == 0.0
        assert below_zero_npt.y == 0.0

        above_bounds = Position(x=2500, y=1200)
        above_bounds_npt = screen.normalize(above_bounds)
        assert above_bounds_npt.x == 1.0
        assert above_bounds_npt.y == 1.0

    def test_denormalize(self):
        """Test normalized to pixel coordinate conversion"""
        screen = Screen(width=1920, height=1080)

        # Center
        npt = NormalizedPoint(x=0.5, y=0.5)
        pos = screen.denormalize(npt)
        assert pos.x == 960
        assert pos.y == 540

        # Top-left
        npt = NormalizedPoint(x=0.0, y=0.0)
        pos = screen.denormalize(npt)
        assert pos.x == 0
        assert pos.y == 0

        # Bottom-right
        npt = NormalizedPoint(x=1.0, y=1.0)
        pos = screen.denormalize(npt)
        assert pos.x == 1920
        assert pos.y == 1080

    def test_round_trip(self):
        """Test normalize → denormalize round trip"""
        screen = Screen(width=1920, height=1080)

        original = Position(x=640, y=480)
        normalized = screen.normalize(original)
        result = screen.denormalize(normalized)

        assert result.x == original.x
        assert result.y == original.y

    def test_different_resolutions(self):
        """Test coordinate transformation between different screen sizes"""
        server_screen = Screen(width=2560, height=1440)
        client_screen = Screen(width=1920, height=1080)

        # Server center position
        server_pos = Position(x=1280, y=720)

        # Normalize on server
        normalized = server_screen.normalize(server_pos)
        assert normalized.x == 0.5
        assert normalized.y == 0.5

        # Denormalize on client
        client_pos = client_screen.denormalize(normalized)
        assert client_pos.x == 960  # Center of 1920
        assert client_pos.y == 540  # Center of 1080
