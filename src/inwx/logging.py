"""Logging setup for inwx-python."""

from __future__ import annotations

import logging

_logger = logging.getLogger("inwx")


def set_log_level(level: str) -> None:
    """Set the log level for the ``inwx`` logger."""
    _logger.setLevel(getattr(logging, str(level or "INFO").upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    """Child logger under the ``inwx`` namespace."""
    return logging.getLogger(f"inwx.{name}")
