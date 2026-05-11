"""Global exception handling and graceful degradation."""
from __future__ import annotations

import sys

from .log import get_logger

logger = get_logger(__name__)

_ORIGINAL_HOOK = sys.excepthook


def _pet_excepthook(exc_type, exc_value, exc_tb):
    logger.error("Uncaught exception: %s: %s", exc_type.__name__, exc_value, exc_info=(exc_type, exc_value, exc_tb))
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "AI Desktop Pet", "我有点累了，请重启我……")
    except Exception:
        pass


def install():
    sys.excepthook = _pet_excepthook


def uninstall():
    sys.excepthook = _ORIGINAL_HOOK
