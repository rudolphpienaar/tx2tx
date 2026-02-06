"""Backend protocols for display, capture, and injection."""

from __future__ import annotations

from typing import Protocol

from tx2tx.common.types import KeyEvent, MouseEvent, Position, Screen

InputEvent = MouseEvent | KeyEvent


class DisplayBackend(Protocol):
    """Abstract display backend interface."""

    def connection_establish(self) -> None:
        """
        Establish connection to display backend.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Establish connection to display backend."""

    def connection_close(self) -> None:
        """
        Close connection to display backend.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Close connection to display backend."""

    def connection_sync(self) -> None:
        """
        Flush and sync backend connection.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Flush and sync backend connection."""

    def screenGeometry_get(self) -> Screen:
        """
        Get display geometry.
        
        Args:
            None.
        
        Returns:
            Screen geometry.
        """
        """Get display geometry."""

    def pointerPosition_get(self) -> Position:
        """
        Get current pointer position.
        
        Args:
            None.
        
        Returns:
            Pointer position.
        """
        """Get current pointer position."""

    def cursorPosition_set(self, position: Position) -> None:
        """
        Set cursor position.
        
        Args:
            position: position value.
        
        Returns:
            Result value.
        """
        """Set cursor position."""

    def pointer_grab(self) -> None:
        """
        Grab pointer input.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab pointer input."""

    def pointer_ungrab(self) -> None:
        """
        Release pointer grab.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release pointer grab."""

    def keyboard_grab(self) -> None:
        """
        Grab keyboard input.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Grab keyboard input."""

    def keyboard_ungrab(self) -> None:
        """
        Release keyboard grab.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Release keyboard grab."""

    def cursor_hide(self) -> None:
        """
        Hide cursor.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Hide cursor."""

    def cursor_show(self) -> None:
        """
        Show cursor.
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Show cursor."""

    def session_isNative_check(self) -> bool:
        """
        Return True if backend is running on native session.
        
        Args:
            None.
        
        Returns:
            True if session is native.
        """
        """Return True if backend is running on native session."""


class InputCapturer(Protocol):
    """Abstract input event capture interface."""

    def inputEvents_read(self) -> tuple[list[InputEvent], int]:
        """
        Read pending input events and return events + modifier state.
        
        Args:
            None.
        
        Returns:
            Tuple of input events and modifier state.
        """
        """Read pending input events and return events + modifier state."""


class InputInjector(Protocol):
    """Abstract input event injection interface."""

    def injectionReady_check(self) -> bool:
        """
        Return True if injection is supported/available.
        
        Args:
            None.
        
        Returns:
            True if input injection is supported.
        """
        """Return True if injection is supported/available."""

    def mouseEvent_inject(self, event: MouseEvent) -> None:
        """
        Inject mouse event.
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        """Inject mouse event."""

    def keyEvent_inject(self, event: KeyEvent) -> None:
        """
        Inject keyboard event.
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        """Inject keyboard event."""
