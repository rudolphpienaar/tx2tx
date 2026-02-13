"""Software cursor implementation using X11 Overlay Window"""

import logging
from Xlib import X
from Xlib.ext import shape

logger = logging.getLogger(__name__)

class SoftwareCursor:
    """
    Renders a software cursor using an override-redirect X11 window.
    Useful when the OS/Compositor hides the hardware cursor or fails to update it.
    """

    def __init__(self, display_manager, color: str = "red") -> None:
        """
        Initialize software cursor
        
        Args:
            display_manager: display_manager value.
            color: color value.
        
        Returns:
            Result value.
        """
        self._display_manager = display_manager
        self._window = None
        self._width = 20
        self._height = 20
        self._color = color
        self._visible = False

    def _setup(self) -> None:
        """
        Create the cursor window
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Create the cursor window"""
        if self._window:
            return

        display = self._display_manager.display_get()
        screen = display.screen()
        root = screen.root

        # Allocate color
        cmap = screen.default_colormap
        if self._color == "red":
            bg_color = cmap.alloc_color(65535, 0, 0)
        elif self._color == "green":
            bg_color = cmap.alloc_color(0, 65535, 0)
        elif self._color == "blue":
            bg_color = cmap.alloc_color(0, 0, 65535)
        else:
            bg_color = cmap.alloc_color(65535, 65535, 65535)

        # Create window
        # override_redirect=True is CRITICAL: it tells the Window Manager (and Sommelier)
        # to leave this window alone (no title bar, no positioning logic).
        self._window = root.create_window(
            0, 0, self._width, self._height, 0,
            screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=bg_color.pixel,
            override_redirect=True
        )

        # Apply Shape Mask to make it look like an arrow
        if display.has_extension("SHAPE"):
            try:
                # Create a bitmap (depth 1) for the mask
                pm = self._window.create_pixmap(self._width, self._height, 1)
                gc = pm.create_gc(foreground=0, background=0)
                
                # 1. Clear everything to transparent (0)
                pm.fill_rectangle(gc, 0, 0, self._width, self._height)
                
                # 2. Draw the arrow shape as opaque (1)
                gc.change(foreground=1)
                
                # Simple pointer polygon points
                # (0,0) is the tip
                points = [
                    (0, 0),    # Tip
                    (0, 18),   # Left edge bottom
                    (5, 13),   # Notch
                    (9, 20),   # Stem bottom left
                    (12, 19),  # Stem bottom right
                    (8, 12),   # Stem top right join
                    (14, 12),  # Right wing
                    (0, 0)     # Close
                ]
                
                # X.Complex might be needed if the polygon self-intersects, but this one is convex-ish
                pm.fill_poly(gc, X.Complex, X.CoordModeOrigin, points)
                
                # 3. Apply the mask to the window
                # Get constants safely (handling different python-xlib versions)
                SK_Bounding = getattr(shape, "SK_Bounding", 0)
                if not hasattr(shape, "SK_Bounding"):
                    SK_Bounding = getattr(shape, "ShapeBounding", 0)
                    
                SO_Set = getattr(shape, "SO_Set", 0)
                if not hasattr(shape, "SO_Set"):
                    SO_Set = getattr(shape, "ShapeSet", 0)
                
                self._window.shape_mask(SO_Set, SK_Bounding, 0, 0, pm)
                
                # Optional: Input shape (XShape 1.1) to allow clicks through transparent parts
                # If we want the cursor to capture clicks, we leave it. 
                # If we want clicks to pass through the empty space, we can apply the same mask to Input.
                # But since we are likely handling input via global grabs or XTest injection, 
                # visual shape is the priority here.
                
                pm.free()
                logger.debug("Applied software cursor shape mask")
                
            except Exception as e:
                logger.warning(f"Failed to apply cursor shape: {e}")
        else:
            logger.info("SHAPE extension not available; falling back to square cursor")

        self._window.map()
        display.sync()
        self._visible = True
        logger.info("Software cursor created")

    def move(self, x: int, y: int) -> None:
        """
        Move cursor to position
        
        Args:
            x: x value.
            y: y value.
        
        Returns:
            Result value.
        """
        if not self._window:
            self._setup()

        # Offset the cursor window from the hotspot so it doesn't block clicks
        # The actual click happens at (x,y). We draw the cursor at (x+5, y+5).
        win_x = x + 5
        win_y = y + 5

        # Use configure to move
        # stack_mode=X.Above ensures it stays on top of other windows
        self._window.configure(
            x=win_x, 
            y=win_y, 
            stack_mode=X.Above
        )
        # No sync() here for performance, rely on periodic event loop sync

    def show(self) -> None:
        """
        Show the cursor
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Show the cursor"""
        if self._window and not self._visible:
            self._window.map()
            self._visible = True

    def hide(self) -> None:
        """
        Hide the cursor
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Hide the cursor"""
        if self._window and self._visible:
            self._window.unmap()
            self._visible = False

    def destroy(self) -> None:
        """
        Destroy the cursor window
        
        Args:
            None.
        
        Returns:
            Result value.
        """
        """Destroy the cursor window"""
        if self._window:
            self._window.destroy()
            self._window = None
