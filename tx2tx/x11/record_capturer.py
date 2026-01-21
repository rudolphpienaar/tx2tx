"""
X11 event capturing using the XRecord extension.

This is a more efficient alternative to polling via XQueryPointer and grabbing
the keyboard, as it uses the X11 RECORD extension to receive all input events
from the server.
"""
import queue
from typing import Optional

from Xlib import X
from Xlib.display import Display
from Xlib.ext import record
from Xlib.protocol import rq

from tx2tx.common.types import EventType, KeyEvent, MouseEvent, Position
from tx2tx.x11.display import DisplayManager


class XRecordCapturer:
    """Captures all keyboard and mouse events using the XRecord extension."""

    def __init__(self, display_manager: DisplayManager):
        """
        Initializes the XRecord capturer.

        Args:
            display_manager: The X11 display manager.

        Raises:
            Exception: If the RECORD extension is not available.
        """
        self._display_manager: DisplayManager = display_manager
        self._display: Display = self._display_manager.display_get()
        self._record_context = None
        self._event_queue: queue.Queue[MouseEvent | KeyEvent] = queue.Queue()

        if not self._display.has_extension("RECORD"):
            raise Exception("X RECORD extension not supported on this server.")

        self._record_ext = self._display.record_extension()

    def capturing_start(self) -> None:
        """Starts capturing events by creating and enabling a RECORD context."""
        if self._record_context:
            self.capturing_stop()

        self._record_context = self._record_ext.create_context(
            0,
            [record.AllClients],
            [
                {
                    "core_requests": (0, 0),
                    "core_replies": (0, 0),
                    "ext_requests": (0, 0, 0, 0),
                    "ext_replies": (0, 0, 0, 0),
                    "delivered_events": (0, 0),
                    "device_events": (X.KeyPress, X.MotionNotify),
                    "errors": (0, 0),
                    "client_started": False,
                    "client_died": False,
                }
            ],
        )
        
        self._record_ext.enable_context(self._record_context, self._recordEvents_process)

    def capturing_stop(self) -> None:
        """Stops capturing events."""
        if self._record_context:
            self._record_ext.free_context(self._record_context)
            self._record_context = None
            self._display.sync()

    def connection_fileno(self) -> int:
        """Returns the file descriptor of the X11 connection."""
        return self._display_manager.fileno()

    def event_get(self, block: bool = True, timeout: Optional[float] = None) -> MouseEvent | KeyEvent | None:
        """
        Retrieves an event from the queue.
        """
        try:
            return self._event_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def _recordEvents_process(self, reply) -> None:
        """
        Callback function to process raw data from the RECORD extension.
        """
        if not reply.client_swapped:
            data = reply.data
            while len(data):
                event, data = rq.EventField(None).parse_binary_value(
                    data, self._display.display, None, None
                )
                
                parsed_event = self._xEvent_parse(event)
                if parsed_event:
                    self._event_queue.put(parsed_event)

        if self._record_context:
            self._record_ext.enable_context(self._record_context, self._recordEvents_process)

    def _xEvent_parse(self, xev) -> MouseEvent | KeyEvent | None:
        """
        Parses a raw Xlib event into a MouseEvent or KeyEvent.
        """
        if xev.type == X.ButtonPress:
            position = Position(x=xev.root_x, y=xev.root_y)
            return MouseEvent(
                event_type=EventType.MOUSE_BUTTON_PRESS,
                position=position,
                button=xev.detail,
            )
        elif xev.type == X.ButtonRelease:
            position = Position(x=xev.root_x, y=xev.root_y)
            return MouseEvent(
                event_type=EventType.MOUSE_BUTTON_RELEASE,
                position=position,
                button=xev.detail,
            )
        elif xev.type == X.MotionNotify:
            position = Position(x=xev.root_x, y=xev.root_y)
            return MouseEvent(
                event_type=EventType.MOUSE_MOVE,
                position=position,
            )
        elif xev.type == X.KeyPress:
            return KeyEvent(event_type=EventType.KEY_PRESS, keycode=xev.detail)
        elif xev.type == X.KeyRelease:
            return KeyEvent(event_type=EventType.KEY_RELEASE, keycode=xev.detail)
        
        return None
