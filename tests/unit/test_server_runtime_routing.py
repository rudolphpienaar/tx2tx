"""Unit tests for server runtime remote target routing behavior."""

from __future__ import annotations

import logging

from tx2tx.common.types import ScreenContext
from tx2tx.server import transition_state
from tx2tx.server.state import server_state


class TestRemoteTargetRouting:
    """Tests for REMOTE target resolution when switching contexts."""

    def teardown_method(self) -> None:
        """
        Reset global server state after each test.

        Returns:
            None.
        """
        server_state.reset()

    def test_context_target_overrides_stale_active_target(self) -> None:
        """
        Context mapping must override stale cached target name.

        Returns:
            None.
        """
        context_to_client: dict[ScreenContext, str] = {
            ScreenContext.WEST: "tabmux",
            ScreenContext.EAST: "penguin",
        }
        server_state.context = ScreenContext.WEST
        server_state.active_remote_client_name = "penguin"

        resolved_target_client_name: str | None = transition_state.remoteTargetClientName_get(
            context_to_client=context_to_client,
            server_state=server_state,
            logger=logging.getLogger(__name__),
        )

        assert resolved_target_client_name == "tabmux"
        assert server_state.active_remote_client_name == "tabmux"

    def test_context_target_populates_empty_active_target(self) -> None:
        """
        Context mapping should seed cached active target when unset.

        Returns:
            None.
        """
        context_to_client: dict[ScreenContext, str] = {
            ScreenContext.WEST: "tabmux",
            ScreenContext.EAST: "penguin",
        }
        server_state.context = ScreenContext.EAST
        server_state.active_remote_client_name = None

        resolved_target_client_name: str | None = transition_state.remoteTargetClientName_get(
            context_to_client=context_to_client,
            server_state=server_state,
            logger=logging.getLogger(__name__),
        )

        assert resolved_target_client_name == "penguin"
        assert server_state.active_remote_client_name == "penguin"

    def test_fallback_to_active_target_when_context_unmapped(self) -> None:
        """
        Cached target should be used if current context has no configured client.

        Returns:
            None.
        """
        context_to_client: dict[ScreenContext, str] = {
            ScreenContext.WEST: "tabmux",
            ScreenContext.EAST: "penguin",
        }
        server_state.context = ScreenContext.NORTH
        server_state.active_remote_client_name = "penguin"

        resolved_target_client_name: str | None = transition_state.remoteTargetClientName_get(
            context_to_client=context_to_client,
            server_state=server_state,
            logger=logging.getLogger(__name__),
        )

        assert resolved_target_client_name == "penguin"
