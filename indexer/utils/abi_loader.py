"""ABI loading from JSON. Unused for now; ready for when we externalize
adapter ABIs to .json files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_abi(path: str | Path) -> list[dict[str, Any]]:
    """Load an ABI from JSON.

    Tolerant: if the file is missing, empty or invalid, it logs a warning
    and returns []. Never raises: an adapter without an ABI simply doesn't
    decode events, but doesn't crash the pipeline.
    """
    p = Path(path)
    if not p.exists():
        logger.warning("ABI not found: %s", p)
        return []
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Unreadable ABI %s: %s", p, exc)
        return []
    if not raw.strip():
        logger.warning("Empty ABI: %s", p)
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid ABI JSON %s: %s", p, exc)
        return []
    if isinstance(data, dict) and "abi" in data:
        data = data["abi"]
    if not isinstance(data, list):
        logger.warning("Unexpected ABI format in %s", p)
        return []
    return data
