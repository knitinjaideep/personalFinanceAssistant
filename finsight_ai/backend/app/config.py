"""
Application configuration using pydantic-settings.

All settings can be overridden via environment variables or a .env file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OllamaConfig(BaseSettings):
    """Ollama LLM and embedding model configuration."""

    model_config = SettingsConfigDict(env_prefix="CORAL_OLLAMA_", env_file=".env", extra="ignore")

    base_url: str = Field(default="http://localhost:11434")

    # Per-task model assignments (config-driven, swappable)
    classification_model: str = Field(default="qwen3:8b")
    extraction_model: str = Field(default="qwen3:8b")
    chat_model: str = Field(default="qwen3:8b")
    embedding_model: str = Field(default="nomic-embed-text")

    # Generation parameters
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    num_ctx: int = Field(default=8192)
    timeout_seconds: int = Field(default=120)


class DatabaseConfig(BaseSettings):
    """SQLite database configuration."""

    model_config = SettingsConfigDict(env_prefix="CORAL_DB_", env_file=".env", extra="ignore")

    path: str = Field(default="data/db/finsight.db")
    echo_sql: bool = Field(default=False)


class StorageConfig(BaseSettings):
    """File storage configuration."""

    model_config = SettingsConfigDict(env_prefix="CORAL_STORAGE_", env_file=".env", extra="ignore")

    uploads_directory: str = Field(default="data/uploads")
    max_file_size_mb: int = Field(default=50)
    allowed_extensions: list[str] = Field(default=[".pdf"])


# Fixed folder → (bucket, institution_type, account_type label) mapping.
# Path is relative to the project data/ directory.
FOLDER_REGISTRY: list[dict] = [
    {
        "path": "data/investments/morgan_stanley",
        "bucket": "investments",
        "institution_type": "morgan_stanley",
        "label": "Morgan Stanley",
    },
    {
        "path": "data/investments/etrade",
        "bucket": "investments",
        "institution_type": "etrade",
        "label": "E*TRADE",
    },
    {
        "path": "data/banking/chase/checking",
        "bucket": "banking",
        "institution_type": "chase",
        "label": "Chase Checking",
    },
    {
        "path": "data/banking/chase/credit_cards",
        "bucket": "banking",
        "institution_type": "chase",
        "label": "Chase Credit Cards",
    },
    {
        "path": "data/banking/amex",
        "bucket": "banking",
        "institution_type": "amex",
        "label": "Amex",
    },
    {
        "path": "data/banking/discover",
        "bucket": "banking",
        "institution_type": "discover",
        "label": "Discover",
    },
]


class SearchConfig(BaseSettings):
    """Search and retrieval configuration."""

    model_config = SettingsConfigDict(env_prefix="CORAL_SEARCH_", env_file=".env", extra="ignore")

    # FTS5 is always enabled; vector search is optional
    vector_search_enabled: bool = Field(default=True)
    vector_top_k: int = Field(default=6)
    fts_top_k: int = Field(default=10)

    # Embedding dimensions (nomic-embed-text = 768)
    embedding_dimensions: int = Field(default=768)


class Settings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_prefix="CORAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Coral"
    app_version: str = "2.0.0"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = Field(default=True)
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # Base directory (project root)
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)

    # Sub-configs
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper

    def get_database_url(self) -> str:
        """Return async SQLite connection URL."""
        db_path = self.base_dir / self.database.path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{db_path}"

    def get_sync_database_url(self) -> str:
        """Return sync SQLite connection URL (for FTS5 setup)."""
        db_path = self.base_dir / self.database.path
        return f"sqlite:///{db_path}"

    def get_uploads_dir(self) -> Path:
        path = self.base_dir / self.storage.uploads_directory
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_db_path(self) -> Path:
        return self.base_dir / self.database.path

    def get_data_dir(self) -> Path:
        return self.base_dir / "data"


settings = Settings()
