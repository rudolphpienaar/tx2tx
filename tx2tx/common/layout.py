"""Screen layout management and coordinate transformation"""

import logging
from enum import Enum

from tx2tx.common.types import Direction, Position, ScreenGeometry, ScreenTransition

logger = logging.getLogger(__name__)

# Cursor entry margin: position cursor this many pixels inside the screen edge
# to avoid immediate boundary detection and ping-pong loops
# Must be large enough to prevent velocity from triggering re-detection
ENTRY_MARGIN_PIXELS = 50


class ClientPosition(Enum):
    """Position of client screen relative to server"""

    NORTH = "north"
    NORTHEAST = "northeast"
    EAST = "east"
    SOUTHEAST = "southeast"
    SOUTH = "south"
    SOUTHWEST = "southwest"
    WEST = "west"
    NORTHWEST = "northwest"


class ScreenLayout:
    """Manages screen layout and coordinate transformations between server and client"""

    def __init__(self, client_position: ClientPosition) -> None:
        """
        Initialize screen layout

        Args:
            client_position: Position of the (single) client relative to server
        """
        self._client_position = client_position

    @property
    def client_position(self) -> ClientPosition:
        """Get configured client position"""
        return self._client_position

    def toClient_shouldTransition(self, server_edge: Direction) -> bool:
        """
        Determine if crossing this server edge should trigger transition to client

        Args:
            server_edge: Which edge of server screen was crossed

        Returns:
            True if this edge leads to the configured client position
        """
        # Map server edges to client positions
        edge_to_position = {
            Direction.LEFT: ClientPosition.WEST,
            Direction.RIGHT: ClientPosition.EAST,
            Direction.TOP: ClientPosition.NORTH,
            Direction.BOTTOM: ClientPosition.SOUTH,
        }

        # For now, only cardinal directions supported
        # Future: add diagonal support with edge region detection
        return edge_to_position.get(server_edge) == self._client_position

    def clientEntryEdge_get(self) -> Direction:
        """
        Get which edge the client should enter from based on client position

        Returns:
            Client entry edge (opposite of server exit edge)
        """
        # Client at WEST enters from RIGHT edge
        # Client at EAST enters from LEFT edge, etc.
        position_to_entry_edge = {
            ClientPosition.WEST: Direction.RIGHT,
            ClientPosition.EAST: Direction.LEFT,
            ClientPosition.NORTH: Direction.BOTTOM,
            ClientPosition.SOUTH: Direction.TOP,
            # Diagonals (future):
            ClientPosition.NORTHWEST: Direction.BOTTOM,  # Could be BOTTOM or RIGHT
            ClientPosition.NORTHEAST: Direction.BOTTOM,  # Could be BOTTOM or LEFT
            ClientPosition.SOUTHWEST: Direction.TOP,  # Could be TOP or RIGHT
            ClientPosition.SOUTHEAST: Direction.TOP,  # Could be TOP or LEFT
        }
        return position_to_entry_edge[self._client_position]

    def serverReentryEdge_get(self) -> Direction:
        """
        Get which edge the server should be re-entered from when client exits

        Returns:
            Server re-entry edge (same as original server exit edge)
        """
        # Client at WEST → server re-enters from LEFT
        # Client at EAST → server re-enters from RIGHT, etc.
        position_to_reentry_edge = {
            ClientPosition.WEST: Direction.LEFT,
            ClientPosition.EAST: Direction.RIGHT,
            ClientPosition.NORTH: Direction.TOP,
            ClientPosition.SOUTH: Direction.BOTTOM,
            # Diagonals (future):
            ClientPosition.NORTHWEST: Direction.LEFT,  # Could be LEFT or TOP
            ClientPosition.NORTHEAST: Direction.RIGHT,  # Could be RIGHT or TOP
            ClientPosition.SOUTHWEST: Direction.LEFT,  # Could be LEFT or BOTTOM
            ClientPosition.SOUTHEAST: Direction.RIGHT,  # Could be RIGHT or BOTTOM
        }
        return position_to_reentry_edge[self._client_position]

    def toClientCoordinates_transform(
        self,
        server_transition: ScreenTransition,
        server_geometry: ScreenGeometry,
        client_geometry: ScreenGeometry,
    ) -> ScreenTransition:
        """
        Transform server exit coordinates to client entry coordinates

        Args:
            server_transition: Server boundary crossing details
            server_geometry: Server screen dimensions
            client_geometry: Client screen dimensions

        Returns:
            Transformed transition for client entry

        Raises:
            ValueError: If screen geometries are invalid (zero or negative dimensions)
        """
        logger.info(
            f"[COORD XFORM → CLIENT] Input: server_exit={server_transition.direction.value} "
            f"pos=({server_transition.position.x}, {server_transition.position.y}) "
            f"server_geom={server_geometry.width}x{server_geometry.height} "
            f"client_geom={client_geometry.width}x{client_geometry.height} "
            f"client_pos={self._client_position.value}"
        )

        # Validate screen geometries
        if server_geometry.height <= 0 or server_geometry.width <= 0:
            raise ValueError(
                f"Invalid server geometry: {server_geometry.width}x{server_geometry.height}"
            )
        if client_geometry.height <= 0 or client_geometry.width <= 0:
            raise ValueError(
                f"Invalid client geometry: {client_geometry.width}x{client_geometry.height}"
            )

        # Determine client entry edge
        client_entry_edge = self.clientEntryEdge_get()
        logger.info(
            f"[COORD XFORM → CLIENT] Calculated client_entry_edge={client_entry_edge.value}"
        )

        # Calculate client entry position
        if self._client_position in (ClientPosition.WEST, ClientPosition.EAST):
            # Horizontal transition: scale Y coordinate
            scale = client_geometry.height / server_geometry.height
            client_y = int(server_transition.position.y * scale)
            client_y_clamped = max(0, min(client_y, client_geometry.height - 1))

            # Client X depends on entry edge
            # Position cursor INSIDE screen by ENTRY_MARGIN_PIXELS to avoid immediate re-detection
            if client_entry_edge == Direction.LEFT:
                client_x = ENTRY_MARGIN_PIXELS
            else:  # Direction.RIGHT
                client_x = client_geometry.width - 1 - ENTRY_MARGIN_PIXELS

            logger.info(
                f"[COORD XFORM → CLIENT] Horizontal: scale={scale:.4f} "
                f"server_y={server_transition.position.y} → client_y={client_y} (clamped={client_y_clamped}) "
                f"client_x={client_x} (edge={client_entry_edge.value}, margin={ENTRY_MARGIN_PIXELS}px)"
            )

            client_pos = Position(x=client_x, y=client_y_clamped)

        elif self._client_position in (ClientPosition.NORTH, ClientPosition.SOUTH):
            # Vertical transition: scale X coordinate
            scale = client_geometry.width / server_geometry.width
            client_x = int(server_transition.position.x * scale)
            client_x_clamped = max(0, min(client_x, client_geometry.width - 1))

            # Client Y depends on entry edge
            # Position cursor INSIDE screen by ENTRY_MARGIN_PIXELS to avoid immediate re-detection
            if client_entry_edge == Direction.TOP:
                client_y = ENTRY_MARGIN_PIXELS
            else:  # Direction.BOTTOM
                client_y = client_geometry.height - 1 - ENTRY_MARGIN_PIXELS

            logger.info(
                f"[COORD XFORM → CLIENT] Vertical: scale={scale:.4f} "
                f"server_x={server_transition.position.x} → client_x={client_x} (clamped={client_x_clamped}) "
                f"client_y={client_y} (edge={client_entry_edge.value}, margin={ENTRY_MARGIN_PIXELS}px)"
            )

            client_pos = Position(x=client_x_clamped, y=client_y)

        else:
            # Diagonal positions (future): need more complex logic
            # For now, treat as cardinal direction
            raise NotImplementedError(
                f"Diagonal position {self._client_position} not yet supported"
            )

        result = ScreenTransition(direction=client_entry_edge, position=client_pos)
        logger.info(
            f"[COORD XFORM → CLIENT] Output: client_entry={result.direction.value} "
            f"pos=({result.position.x}, {result.position.y})"
        )
        return result

    def toServerCoordinates_transform(
        self,
        client_transition: ScreenTransition,
        client_geometry: ScreenGeometry,
        server_geometry: ScreenGeometry,
    ) -> ScreenTransition:
        """
        Transform client exit coordinates to server re-entry coordinates

        Args:
            client_transition: Client boundary crossing details
            client_geometry: Client screen dimensions
            server_geometry: Server screen dimensions

        Returns:
            Transformed transition for server re-entry

        Raises:
            ValueError: If screen geometries are invalid (zero or negative dimensions)
        """
        logger.info(
            f"[COORD XFORM → SERVER] Input: client_exit={client_transition.direction.value} "
            f"pos=({client_transition.position.x}, {client_transition.position.y}) "
            f"client_geom={client_geometry.width}x{client_geometry.height} "
            f"server_geom={server_geometry.width}x{server_geometry.height} "
            f"client_pos={self._client_position.value}"
        )

        # Validate screen geometries
        if server_geometry.height <= 0 or server_geometry.width <= 0:
            raise ValueError(
                f"Invalid server geometry: {server_geometry.width}x{server_geometry.height}"
            )
        if client_geometry.height <= 0 or client_geometry.width <= 0:
            raise ValueError(
                f"Invalid client geometry: {client_geometry.width}x{client_geometry.height}"
            )

        # Determine server re-entry edge
        server_reentry_edge = self.serverReentryEdge_get()
        logger.info(
            f"[COORD XFORM → SERVER] Calculated server_reentry_edge={server_reentry_edge.value}"
        )

        # Calculate server re-entry position (inverse of to_client transform)
        if self._client_position in (ClientPosition.WEST, ClientPosition.EAST):
            # Horizontal transition: scale Y coordinate back
            scale = server_geometry.height / client_geometry.height
            server_y = int(client_transition.position.y * scale)
            server_y_clamped = max(0, min(server_y, server_geometry.height - 1))

            # Server X depends on re-entry edge
            # Position cursor INSIDE screen by ENTRY_MARGIN_PIXELS to avoid immediate re-detection
            if server_reentry_edge == Direction.LEFT:
                server_x = ENTRY_MARGIN_PIXELS
            else:  # Direction.RIGHT
                server_x = server_geometry.width - 1 - ENTRY_MARGIN_PIXELS

            logger.info(
                f"[COORD XFORM → SERVER] Horizontal: scale={scale:.4f} "
                f"client_y={client_transition.position.y} → server_y={server_y} (clamped={server_y_clamped}) "
                f"server_x={server_x} (edge={server_reentry_edge.value}, margin={ENTRY_MARGIN_PIXELS}px)"
            )

            server_pos = Position(x=server_x, y=server_y_clamped)

        elif self._client_position in (ClientPosition.NORTH, ClientPosition.SOUTH):
            # Vertical transition: scale X coordinate back
            scale = server_geometry.width / client_geometry.width
            server_x = int(client_transition.position.x * scale)
            server_x_clamped = max(0, min(server_x, server_geometry.width - 1))

            # Server Y depends on re-entry edge
            # Position cursor INSIDE screen by ENTRY_MARGIN_PIXELS to avoid immediate re-detection
            if server_reentry_edge == Direction.TOP:
                server_y = ENTRY_MARGIN_PIXELS
            else:  # Direction.BOTTOM
                server_y = server_geometry.height - 1 - ENTRY_MARGIN_PIXELS

            logger.info(
                f"[COORD XFORM → SERVER] Vertical: scale={scale:.4f} "
                f"client_x={client_transition.position.x} → server_x={server_x} (clamped={server_x_clamped}) "
                f"server_y={server_y} (edge={server_reentry_edge.value}, margin={ENTRY_MARGIN_PIXELS}px)"
            )

            server_pos = Position(x=server_x_clamped, y=server_y)

        else:
            # Diagonal positions (future)
            raise NotImplementedError(
                f"Diagonal position {self._client_position} not yet supported"
            )

        result = ScreenTransition(direction=server_reentry_edge, position=server_pos)
        logger.info(
            f"[COORD XFORM → SERVER] Output: server_reentry={result.direction.value} "
            f"pos=({result.position.x}, {result.position.y})"
        )
        return result
