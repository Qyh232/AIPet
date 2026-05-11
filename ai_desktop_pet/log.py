"""Project-wide structured logger.

Usage:
    from .log import get_logger
    logger = get_logger(__name__)
    logger.info("event=user_clicked emotion=happy")
"""
from __future__ import annotations

import logging
import os
import sys

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S"
_CONFIGURED = False


def configure(level: str | int = "INFO", *, stream=None) -> None:
    """Configure root logger once. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        root = logging.getLogger()
        root.setLevel(_normalize_level(level))
        return

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATEFMT))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(_normalize_level(level))
    _CONFIGURED = True


def _normalize_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    return getattr(logging, str(level).upper(), logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a logger; auto-configures from $PET_LOG_LEVEL if first call."""
    if not _CONFIGURED:
        configure(os.environ.get("PET_LOG_LEVEL", "INFO"))
    return logging.getLogger(name)
