"""
Application configuration package.

`from app.config import settings` — main application settings
`from app.config.statement_catalog import ...` — statement catalog
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OllamaConfig(BaseSettings):
    """Central Ollama model configuration.

    The single primary model used for chat, intent classification, and entity
    extraction is `model`. It defaults to Gemma 4 (``gemma4:latest``) and can be
    overridden with the ``OLLAMA_MODEL`` environment variable (also accepts the
    legacy ``CORAL_OLLAMA_MODEL`` form). Do NOT hardcode model names elsewhere —
    read ``settings.ollama.model`` instead.
    """

    model_config = SettingsConfigDict(env_prefix="CORAL_OLLAMA_", env_file=".env", extra="ignore")

    base_url: str = Field(default="http://localhost:11434")

    # The one place model names live. Override via OLLAMA_MODEL=gemma4:e4b
    model: str = Field(
        default="gemma4:latest",
        validation_alias=AliasChoices("OLLAMA_MODEL", "CORAL_OLLAMA_MODEL"),
        description="Primary Ollama model for chat / classification / extraction.",
    )

    embedding_model: str = Field(default="nomic-embed-text")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    num_ctx: int = Field(default=8192)
    timeout_seconds: int = Field(default=120)

    # ── Backward-compatible accessors ────────────────────────────────────────
    # Older code referenced separate models per task. They now all resolve to
    # the single centralized `model` so nothing is hardcoded in two places.
    @property
    def chat_model(self) -> str:
        return self.model

    @property
    def classification_model(self) -> str:
        return self.model

    @property
    def extraction_model(self) -> str:
        return self.model

    @property
    def pull_hint(self) -> str:
        """User-facing instruction to install the configured model."""
        return f"Run: ollama pull {self.model}"


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORAL_DB_", env_file=".env", extra="ignore")

    path: str = Field(default="data/db/finsight.db")
    echo_sql: bool = Field(default=False)


class StorageConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORAL_STORAGE_", env_file=".env", extra="ignore")

    uploads_directory: str = Field(default="data/uploads")
    max_file_size_mb: int = Field(default=50)
    allowed_extensions: list[str] = Field(default=[".pdf"])
    statements_root: str = Field(
        default="",
        description="Absolute path to Coral statements root. "
                    "Falls back to ~/Documents/Personal/Coral if empty.",
    )

    def get_statements_root(self) -> Path:
        if self.statements_root:
            return Path(self.statements_root)
        return Path.home() / "Documents" / "Personal" / "Coral"


class VectorConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORAL_VECTOR_", env_file=".env", extra="ignore")

    enabled: bool = Field(default=True)
    chroma_path: str = Field(default="data/chroma")
    collection_name: str = Field(default="coral_chunks")


class SearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORAL_SEARCH_", env_file=".env", extra="ignore")

    vector_search_enabled: bool = Field(default=True)
    vector_top_k: int = Field(default=6)
    fts_top_k: int = Field(default=10)
    embedding_dimensions: int = Field(default=768)


class Settings(BaseSettings):
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


    # __file__ here is the package __init__.py; parent.parent.parent goes to project root
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)

    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    vector: VectorConfig = Field(default_factory=VectorConfig)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper

    def get_database_url(self) -> str:
        db_path = self.base_dir / self.database.path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{db_path}"

    def get_sync_database_url(self) -> str:
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

    def get_chroma_path(self) -> Path:
        path = self.base_dir / self.vector.chroma_path
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
