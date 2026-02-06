"""Backend factory functions."""

from __future__ import annotations

from typing import Optional

from tx2tx.input.backend import DisplayBackend, InputCapturer, InputInjector
from tx2tx.x11.backend import X11DisplayBackend, X11InputCapturer, X11InputInjector


def serverBackend_create(
    backend_name: str,
    display_name: Optional[str],
    overlay_enabled: bool,
    x11native: bool,
    wayland_helper: Optional[str],
    wayland_screen_width: Optional[int],
    wayland_screen_height: Optional[int],
) -> tuple[DisplayBackend, InputCapturer]:
    """
    Create server-side backend components.
    
    Args:
        backend_name: Backend identifier (e.g., "x11", "wayland")
        display_name: Display name (backend-specific)
        overlay_enabled: Overlay window toggle (X11 only)
        x11native: Native X11 flag (X11 only)
        wayland_helper: Helper command for Wayland backend
        wayland_screen_width: Optional screen width override (Wayland)
        wayland_screen_height: Optional screen height override (Wayland)
    
    Returns:
        Tuple of (DisplayBackend, InputCapturer)
    """
    backend = backend_name.lower()

    if backend == "x11":
        display_backend = X11DisplayBackend(
            display_name=display_name, overlay_enabled=overlay_enabled, x11native=x11native
        )
        capturer = X11InputCapturer(display_backend=display_backend)
        return display_backend, capturer

    if backend == "wayland":
        from tx2tx.wayland.backend import WaylandDisplayBackend, WaylandInputCapturer

        display_backend = WaylandDisplayBackend(
            helper_command=wayland_helper,
            screen_width=wayland_screen_width,
            screen_height=wayland_screen_height,
        )
        capturer = WaylandInputCapturer(display_backend=display_backend)
        return display_backend, capturer

    raise ValueError(f"Unsupported backend '{backend_name}'. Supported: x11, wayland.")


def clientBackend_create(
    backend_name: str,
    display_name: Optional[str],
    wayland_helper: Optional[str],
) -> tuple[DisplayBackend, InputInjector]:
    """
    Create client-side backend components.
    
    Args:
        backend_name: Backend identifier (e.g., "x11", "wayland")
        display_name: Display name (backend-specific)
        wayland_helper: Helper command for Wayland backend
    
    Returns:
        Tuple of (DisplayBackend, InputInjector)
    """
    backend = backend_name.lower()

    if backend == "x11":
        display_backend = X11DisplayBackend(display_name=display_name)
        injector = X11InputInjector(display_backend=display_backend)
        return display_backend, injector

    if backend == "wayland":
        from tx2tx.wayland.backend import WaylandDisplayBackend, WaylandInputInjector

        display_backend = WaylandDisplayBackend(
            helper_command=wayland_helper,
            screen_width=None,
            screen_height=None,
        )
        injector = WaylandInputInjector(display_backend=display_backend)
        return display_backend, injector

    raise ValueError(f"Unsupported backend '{backend_name}'. Supported: x11, wayland.")
