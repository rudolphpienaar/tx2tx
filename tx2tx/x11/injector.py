"""X11 event injection using XTest extension"""

from Xlib import X
from Xlib.ext import xtest

from tx2tx.common.types import KeyEvent, MouseEvent, Position
from tx2tx.x11.display import DisplayManager


class EventInjector:
    """Injects mouse and keyboard events into X11 using XTest extension"""

    def __init__(self, display_manager: DisplayManager) -> None:
        """
        Initialize event injector

        Args:
            display_manager: X11 display manager
        """
        self._display_manager: DisplayManager = display_manager

    def xtestExtension_verify(self) -> bool:
        """
        Verify XTest extension is available

        Returns:
            True if XTest is available, False otherwise
        """
        display = self._display_manager.display_get()
        ext_info = display.query_extension('XTEST')
        return ext_info is not None

    def mousePointer_move(self, position: Position) -> None:
        """
        Move mouse pointer to absolute position

        Args:
            position: Target position
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.MotionNotify, detail=0, x=position.x, y=position.y)
        display.sync()

    def mousePointer_moveRelative(self, delta_x: int, delta_y: int) -> None:
        """
        Move mouse pointer by relative offset

        Args:
            delta_x: X offset (can be negative)
            delta_y: Y offset (can be negative)
        """
        display = self._display_manager.display_get()
        screen = display.screen()
        root = screen.root

        # Get current position
        pointer_data = root.query_pointer()
        current_x = pointer_data.root_x
        current_y = pointer_data.root_y

        # Calculate new absolute position
        new_x = current_x + delta_x
        new_y = current_y + delta_y

        # Move to new position using absolute coordinates
        # (XTest relative movement seems unreliable)
        xtest.fake_input(display, X.MotionNotify, detail=0, x=new_x, y=new_y)
        display.sync()

    def mouseButton_press(self, button: int) -> None:
        """
        Press mouse button

        Args:
            button: Button number (1=left, 2=middle, 3=right)
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.ButtonPress, detail=button)
        display.sync()

    def mouseButton_release(self, button: int) -> None:
        """
        Release mouse button

        Args:
            button: Button number (1=left, 2=middle, 3=right)
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.ButtonRelease, detail=button)
        display.sync()

    def mouseEvent_inject(self, event: MouseEvent) -> None:
        """
        Inject complete mouse event

        Args:
            event: Mouse event to inject
        """
        from tx2tx.common.types import EventType

        if event.event_type == EventType.MOUSE_MOVE:
            self.mousePointer_move(event.position)
        elif event.event_type == EventType.MOUSE_BUTTON_PRESS and event.button:
            self.mouseButton_press(event.button)
        elif event.event_type == EventType.MOUSE_BUTTON_RELEASE and event.button:
            self.mouseButton_release(event.button)

    def key_press(self, keycode: int) -> None:
        """
        Press keyboard key

        Args:
            keycode: X11 keycode
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.KeyPress, detail=keycode)
        display.sync()

    def key_release(self, keycode: int) -> None:
        """
        Release keyboard key

        Args:
            keycode: X11 keycode
        """
        display = self._display_manager.display_get()
        xtest.fake_input(display, X.KeyRelease, detail=keycode)
        display.sync()

    def keyEvent_inject(self, event: KeyEvent) -> None:
        """
        Inject complete keyboard event

        Args:
            event: Key event to inject
        """
        from tx2tx.common.types import EventType

        if event.event_type == EventType.KEY_PRESS:
            self.key_press(event.keycode)
        elif event.event_type == EventType.KEY_RELEASE:
            self.key_release(event.keycode)
