"""Configuración global del indexador, cargada desde el entorno."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto, independiente del CWD. En /proyecto/indexer/config.py
# → BASE_DIR = /proyecto
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuración global. Se lee de variables de entorno o del archivo .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # RPC
    rpc_url: str = Field(..., description="URL del proveedor JSON-RPC")
    chain_id: int = Field(1, description="ID de la cadena")

    # Base de datos (absoluta, independiente del CWD)
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{BASE_DIR / 'indexer.db'}",
        description="URL de conexión SQLAlchemy",
    )

    # Ingesta
    start_block: int = Field(0, description="Bloque desde el que empieza el backfill")
    confirmations: int = Field(
        12, description="Bloques de confirmación antes de considerar un bloque final"
    )
    max_block_range: int = Field(
        2000, description="Máximo de bloques por llamada eth_getLogs"
    )

    log_level: str = Field("INFO")


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia única de Settings (cacheada)."""
    return Settings()
