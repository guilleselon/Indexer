"""Configuración de logging. Lee el nivel de Settings.log_level."""

from __future__ import annotations

import logging

from indexer.config import get_settings


def setup_logging() -> None:
    """Configura logging root según Settings.log_level.

    Idempotente: force=True reemplaza la config previa en lugar de apilar
    handlers. Llamarla desde el callback del CLI una sola vez.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
