"""X11 event injection using XTest extension"""

import logging

from Xlib import X
from Xlib.ext import xtest

from tx2tx.common.types import KeyEvent, MouseEvent, Position
from tx2tx.x11.display import DisplayManager

logger = logging.getLogger(__name__)


class EventInjector:
    """Injects mouse and keyboard events into X11 using XTest extension"""

    def __init__(self, display_manager: DisplayManager) -> None:
        """
        Initialize event injector
        
        Args:
            display_manager: display_manager value.
        
        Returns:
            Result value.
        """
        self._display_manager: DisplayManager = display_manager

    def xtestExtension_verify(self) -> bool:
        """
        Verify XTest extension is available
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        display = self._display_manager.display_get()
        ext_info = display.query_extension("XTEST")
        return ext_info is not None

    def mousePointer_move(self, position: Position) -> None:
        """
        Move mouse pointer to absolute position
        
        Args:
            position: position value.
        
        Returns:
            Result value.
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.MotionNotify, detail=0, x=position.x, y=position.y)
        # Removed sync() for performance - Xlib buffer will be flushed periodically

    def mouseButton_press(self, button: int) -> None:
        """
        Press mouse button
        
        Args:
            button: button value.
        
        Returns:
            Result value.
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.ButtonPress, detail=button)

    def mouseButton_release(self, button: int) -> None:
        """
        Release mouse button
        
        Args:
            button: button value.
        
        Returns:
            Result value.
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.ButtonRelease, detail=button)

    def mouseEvent_inject(self, event: MouseEvent) -> None:
        """
        Inject complete mouse event
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        from tx2tx.common.types import EventType

        display = self._display_manager.display_get()

        # Always move if position is provided
        if event.position:
            self.mousePointer_move(event.position)

        if event.event_type == EventType.MOUSE_MOVE:
            if not event.position:
                raise ValueError("MOUSE_MOVE event requires position field for injection")
        elif event.event_type == EventType.MOUSE_BUTTON_PRESS and event.button:
            self.mouseButton_press(event.button)
        elif event.event_type == EventType.MOUSE_BUTTON_RELEASE and event.button:
            self.mouseButton_release(event.button)

        try:
            display.sync()
        except Exception as exc:
            logger.warning("X11 sync failed after key injection: %r", exc)

    def key_press(self, keycode: int) -> None:
        """
        Press keyboard key
        
        Args:
            keycode: keycode value.
        
        Returns:
            Result value.
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.KeyPress, detail=keycode)

    def key_release(self, keycode: int) -> None:
        """
        Release keyboard key
        
        Args:
            keycode: keycode value.
        
        Returns:
            Result value.
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.KeyRelease, detail=keycode)

    def keyEvent_inject(self, event: KeyEvent) -> None:
        """
        Inject complete keyboard event
        
        Args:
            event: event value.
        
        Returns:
            Result value.
        """
        from tx2tx.common.types import EventType

        display = self._display_manager.display_get()

        if event.event_type == EventType.KEY_PRESS:
            self.key_press(event.keycode)
        elif event.event_type == EventType.KEY_RELEASE:
            self.key_release(event.keycode)

        display.sync()
