"""Application settings singleton - single source of truth for configuration

This module provides a singleton Settings class that consolidates:
1. Protocol-level constants (must match between server/client)
2. Application constants (timing, thresholds, etc.)
3. Runtime configuration from config.yml

Usage:
    from tx2tx.common.settings import settings

    # Initialize once at startup with loaded config
    config = ConfigLoader.config_load()
    settings.initialize(config)

    # Use anywhere in the application
    coord = position.x * settings.COORD_SCALE_FACTOR
    if elapsed >= settings.HYSTERESIS_DELAY_SEC:
        ...
"""

from typing import Optional

from tx2tx.common.config import Config


class Settings:
    """Singleton settings manager combining config.yml and protocol constants

    This class provides:
    - Protocol constants that must be consistent across server/client
    - Application tuning constants (delays, thresholds, etc.)
    - Access to runtime configuration loaded from config.yml

    The singleton pattern ensures all parts of the application use the same
    configuration values and protocol constants.
    """

    _instance: Optional["Settings"] = None

    def __new__(cls) -> "Settings":
        """
        Ensure only one Settings instance exists
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Ensure only one Settings instance exists"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize settings singleton (only runs once)
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Initialize settings singleton (only runs once)"""
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._config: Optional[Config] = None

    def initialize(self, config: Config) -> None:
        """
        Initialize with loaded configuration
        
        Args:
            config: config value.
        
        Returns:
            Result value.
        """
        self._config = config

    # =========================================================================
    # Protocol Constants (v2.0)
    # =========================================================================

    # NOTE: COORD_SCALE_FACTOR removed in v2.1
    # Protocol now uses NormalizedPoint (float x, y) directly instead of
    # encoding as scaled integers. See tx2tx.common.types.NormalizedPoint.

    # =========================================================================
    # Server Constants
    # =========================================================================

    HYSTERESIS_DELAY_SEC: float = 0.2
    """Delay after CENTER switch to prevent immediate re-detection (seconds)

    When returning from REMOTE context to CENTER, wait this long before
    detecting boundaries again. Prevents ping-pong effect where cursor
    immediately re-crosses boundary.
    """

    POLL_INTERVAL_DIVISOR: float = 1000.0
    """Convert poll_interval_ms from config to seconds for time.sleep()"""

    EDGE_ENTRY_OFFSET: int = 2
    """Pixels from edge to position cursor when entering CENTER mode

    When returning from REMOTE context, position cursor this many pixels
    away from the edge to prevent immediate boundary re-crossing.
    """

    # =========================================================================
    # Client Constants
    # =========================================================================

    RECONNECT_CHECK_INTERVAL: float = 0.01
    """Interval for checking reconnection status (seconds)

    Client event loop sleep interval when checking for messages and
    monitoring connection status.
    """

    # =========================================================================
    # Pointer Tracking Constants
    # =========================================================================

    POSITION_HISTORY_SIZE: int = 5
    """Number of recent positions to track for velocity calculation

    PointerTracker maintains a rolling window of recent cursor positions
    with timestamps to calculate movement velocity.
    """

    MIN_SAMPLES_FOR_VELOCITY: int = 2
    """Minimum position samples needed to calculate velocity

    Need at least 2 samples (oldest and newest) to compute velocity.
    """

    DEFAULT_VELOCITY_THRESHOLD: float = 100.0
    """Default velocity threshold in pixels per second

    Used as fallback default for PointerTracker if not specified via config.
    In practice, this value comes from config.yml server.velocity_threshold.
    """

    EDGE_CONFIRMATION_SAMPLES: int = 2
    """Consecutive edge samples required before boundary transition.

    This helps suppress premature crossings from a single noisy or jumped
    pointer coordinate sample at high pointer velocity.
    """

    EDGE_DWELL_SECONDS: float = 0.08
    """Minimum continuous edge-contact duration before CENTER transition.

    CENTER->REMOTE transition is intent-gated by sustained edge contact rather
    than instantaneous pointer velocity. This reduces premature transitions in
    helper-integrated Wayland sessions where pointer coordinates can jump.
    """

    # =========================================================================
    # Runtime Configuration Access
    # These properties delegate to the loaded config.yml
    # =========================================================================

    @property
    def config(self) -> Config:
        """
        Get loaded configuration object
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        if self._config is None:
            raise RuntimeError("Settings not initialized. Call settings.initialize(config) first.")
        return self._config


# Global singleton instance
settings = Settings()
"""Global settings singleton instance

Import this anywhere in the application:
    from tx2tx.common.settings import settings
"""
