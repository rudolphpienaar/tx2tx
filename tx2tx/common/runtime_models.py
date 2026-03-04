"""Typed runtime models for server/client orchestration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServerBackendOptions:
    """Resolved backend options for server runtime bootstrap."""

    backend_name: str
    overlay_enabled: bool
    x11native: bool
    wayland_helper: str | None
    wayland_screen_width: int | None
    wayland_screen_height: int | None
    wayland_calibrate: bool
    wayland_pointer_provider: str
    wayland_gnome_bridge_socket: str | None


@dataclass(frozen=True)
class ClientBackendOptions:
    """Resolved backend options for client runtime bootstrap."""

    backend_name: str
    wayland_helper: str | None
