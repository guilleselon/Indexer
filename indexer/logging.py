"""Logging configuration. Reads the level from Settings.log_level."""

from __future__ import annotations

import logging

from indexer.config import get_settings


def setup_logging() -> None:
    """Configure root logging according to Settings.log_level.

    Idempotent: force=True replaces the previous config instead of stacking
    handlers. Call it once from the CLI callback.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
