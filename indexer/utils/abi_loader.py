"""Carga de ABIs desde JSON. Sin uso actual; listo para cuando externalicemos
los ABIs de los adapters a archivos .json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_abi(path: str | Path) -> list[dict[str, Any]]:
    """Carga un ABI desde JSON.

    Tolerante: si el archivo no existe, está vacío o es inválido, loguea un
    warning y devuelve []. No lanza excepción: un adapter sin ABI simplemente
    no decodifica eventos, pero no tumba el pipeline.
    """
    p = Path(path)
    if not p.exists():
        logger.warning("ABI no encontrado: %s", p)
        return []
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("ABI ilegible %s: %s", p, exc)
        return []
    if not raw.strip():
        logger.warning("ABI vacío: %s", p)
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("ABI JSON inválido %s: %s", p, exc)
        return []
    if isinstance(data, dict) and "abi" in data:
        data = data["abi"]
    if not isinstance(data, list):
        logger.warning("ABI con formato inesperado en %s", p)
        return []
    return data
