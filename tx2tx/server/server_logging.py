"""
Server logging configuration helpers.

This module owns runtime logging setup for the server process, including
version-tagged formatting and optional file handler wiring.
"""

from __future__ import annotations

import logging

from tx2tx import __version__

__all__ = [
    "logging_setup",
    "logFormatWithVersion_get",
]


def logging_setup(level: str, log_format: str, log_file: str | None) -> None:
    """
    Configure logging handlers and version-tagged format string.

    Args:
        level:
            Effective log level token (for example `INFO` or `DEBUG`).
        log_format:
            Base formatter string.
        log_file:
            Optional log file path.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    enhanced_format: str = logFormatWithVersion_get(log_format)
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=enhanced_format,
        handlers=handlers,
    )


def logFormatWithVersion_get(log_format: str) -> str:
    """
    Inject runtime version tag into timestamped log format.

    Args:
        log_format:
            Base formatter string.

    Returns:
        Formatter string with embedded version token.
    """
    return log_format.replace("%(asctime)s", f"%(asctime)s [v{__version__}]")
