"""Server state management - singleton pattern"""

from typing import Optional
from tx2tx.common.types import Position, ScreenContext


class ServerState:
    """
    Singleton class to manage server state across the event loop.

    This provides a clean way to track state that needs to be accessed
    and modified across different parts of the server logic without
    passing mutable references around.
    """

    _instance: Optional["ServerState"] = None

    def __new__(cls) -> "ServerState":
        """
        Ensure only one instance exists (singleton pattern)
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Ensure only one instance exists (singleton pattern)"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize state variables (only once)
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Initialize state variables (only once)"""
        if self._initialized:
            return

        # Current screen context (CENTER, WEST, EAST, NORTH, SOUTH)
        self.context: ScreenContext = ScreenContext.CENTER

        # Timestamp of last transition to CENTER context
        self.last_center_switch_time: float = 0.0
        
        # Timestamp of last transition to REMOTE context (WEST/EAST/etc)
        self.last_remote_switch_time: float = 0.0

        # Boundary crossing state
        self.boundary_crossed: bool = False
        self.target_warp_position: Optional[Position] = None

        # Last sent position to client (to avoid sending duplicates)
        self.last_sent_position: Optional[Position] = None

        # Active remote target client name for current non-CENTER context.
        self.active_remote_client_name: Optional[str] = None

        self._initialized = True

    def reset(self) -> None:
        """
        Reset state to initial values
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Reset state to initial values"""
        self.context = ScreenContext.CENTER
        self.last_center_switch_time = 0.0
        self.last_remote_switch_time = 0.0
        self.boundary_crossed = False
        self.target_warp_position = None
        self.last_sent_position = None
        self.active_remote_client_name = None

    def boundaryCrossed_set(self, target_position: Position) -> None:
        """
        Mark that a boundary has been crossed and cursor needs warping
        
        Args:
            target_position: target_position value.
        
        Returns:
            Result value.
        """
        self.boundary_crossed = True
        self.target_warp_position = target_position

    def boundaryCrossed_clear(self) -> None:
        """
        Clear boundary crossing state after successful warp
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Clear boundary crossing state after successful warp"""
        self.boundary_crossed = False
        self.target_warp_position = None

    def positionChanged_check(self, current_position: Position) -> bool:
        """
        Check if position has changed since last sent
        
        Args:
            current_position: Current cursor position
        
        Returns:
            True if position changed, False if same as last sent
        """
        if self.last_sent_position is None:
            return True  # First position, always send

        # Consider position changed if moved by at least 1 pixel
        return (
            self.last_sent_position.x != current_position.x
            or self.last_sent_position.y != current_position.y
        )

    def lastSentPosition_update(self, position: Position) -> None:
        """
        Update last sent position after sending coordinates
        
        Args:
            position: position value.
        
        Returns:
            Result value.
        """
        self.last_sent_position = position

    @classmethod
    def instance_get(cls) -> "ServerState":
        """
        Get the singleton instance
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Global singleton instance
server_state = ServerState.instance_get()
