"""
Client logging policy.

This module centralizes client logging setup and tx2tx version injection into
log message formats.
"""

from __future__ import annotations

import logging

from tx2tx import __version__

__all__ = ["logging_setup"]


def logging_setup(level: str, log_format: str, log_file: str | None) -> None:
    """
    Configure client logging handlers and format.

    Args:
        level:
            Log level name.
        log_format:
            Base logging format string.
        log_file:
            Optional log-file path.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    enhanced_format: str = log_format.replace("%(asctime)s", f"%(asctime)s [v{__version__}]")
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=enhanced_format,
        handlers=handlers,
    )
