"""Global indexer configuration, loaded from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root, independent of CWD. In /proyecto/indexer/config.py
# → BASE_DIR = /proyecto
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Global configuration. Read from environment variables or the .env file."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # RPC
    rpc_url: str = Field(..., description="JSON-RPC provider URL")
    chain_id: int = Field(1, description="Chain ID")

    # Database (absolute, independent of CWD)
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{BASE_DIR / 'indexer.db'}",
        description="SQLAlchemy connection URL",
    )

    # Ingestion
    start_block: int = Field(0, description="Block from which backfill starts")
    confirmations: int = Field(
        12, description="Confirmation blocks before considering a block final"
    )
    max_block_range: int = Field(
        2000, description="Maximum blocks per eth_getLogs call"
    )

    log_level: str = Field("INFO")


@lru_cache
def get_settings() -> Settings:
    """Return a single cached Settings instance."""
    return Settings()
