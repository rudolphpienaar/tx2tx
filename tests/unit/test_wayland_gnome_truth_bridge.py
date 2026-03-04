"""Unit tests for GNOME truth-bridge pointer provider."""

from __future__ import annotations

import time

import pytest

from tx2tx.wayland.gnome_truth_bridge import GnomeTruthBridgePointerProvider


def test_pointerPosition_get_returnsFreshSample() -> None:
    """
    Provider should return latest non-stale sample coordinates.

    Returns:
        None.
    """
    provider: GnomeTruthBridgePointerProvider = GnomeTruthBridgePointerProvider(
        socket_path="/tmp/tx2tx-test.sock",
        stale_after_seconds=1.0,
    )
    provider._connectionEnsure_establish = lambda: None  # type: ignore[method-assign]

    def _sample_set() -> None:
        provider._latest_sample = provider._frameSample_parse(  # type: ignore[attr-defined]
            f'{{"x": 101, "y": 202, "ts": {time.time()}}}'
        )

    provider._framesAvailable_consume = _sample_set  # type: ignore[method-assign]

    x_value, y_value = provider.pointerPosition_get()
    assert x_value == 101
    assert y_value == 202


def test_pointerPosition_get_raisesOnStaleSample() -> None:
    """
    Provider should reject stale sample when threshold is exceeded.

    Returns:
        None.
    """
    provider: GnomeTruthBridgePointerProvider = GnomeTruthBridgePointerProvider(
        socket_path="/tmp/tx2tx-test.sock",
        stale_after_seconds=0.01,
    )
    provider._connectionEnsure_establish = lambda: None  # type: ignore[method-assign]

    def _sample_set() -> None:
        provider._latest_sample = provider._frameSample_parse('{"x": 1, "y": 2, "ts": 0.0}')  # type: ignore[attr-defined]

    provider._framesAvailable_consume = _sample_set  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="stale"):
        _ = provider.pointerPosition_get()


def test_frameSample_parse_rejectsMissingCoordinates() -> None:
    """
    Frame parser should reject payloads missing x/y keys.

    Returns:
        None.
    """
    with pytest.raises(RuntimeError, match="missing coordinates"):
        _ = GnomeTruthBridgePointerProvider._frameSample_parse('{"x": 1}')
