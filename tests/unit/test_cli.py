"""Unit tests for unified CLI log-level override behavior."""

from __future__ import annotations

from argparse import Namespace

from tx2tx.cli import logLevelOverride_get


class TestLogLevelOverride:
    """Tests for CLI log-level precedence."""

    def test_info_overrides_debug_when_both_set(self) -> None:
        """
        `--info` should suppress debug noise when both flags are present.

        Returns:
            None.
        """
        args = Namespace(
            debug=True,
            info=True,
            warning=False,
            error=False,
            critical=False,
        )
        assert logLevelOverride_get(args) == "INFO"

    def test_warning_overrides_info(self) -> None:
        """
        More restrictive levels should take precedence.

        Returns:
            None.
        """
        args = Namespace(
            debug=True,
            info=True,
            warning=True,
            error=False,
            critical=False,
        )
        assert logLevelOverride_get(args) == "WARNING"
