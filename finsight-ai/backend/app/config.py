"""
Application configuration using pydantic-settings.

All settings can be overridden via environment variables or a .env file.
Environment variable names are uppercased versions of field names, e.g.,
FINSIGHT_DATABASE_URL, FINSIGHT_OLLAMA_BASE_URL, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OllamaModelConfig(BaseSettings):
    """Per-task model assignment for Ollama.

    Different tasks can use different models without changing application code.
    """

    model_config = SettingsConfigDict(env_prefix="FINSIGHT_OLLAMA_", env_file=".env", extra="ignore")

    # Base URL for the local Ollama server
    base_url: str = Field(default="http://localhost:11434", description="Ollama server base URL")

    # Model assignments per task type
    classification_model: str = Field(
        default="qwen3:8b", description="Model used for statement classification"
    )
    extraction_model: str = Field(
        default="qwen3:8b", description="Model used for data extraction assistance"
    )
    analysis_model: str = Field(
        default="qwen3:8b", description="Model used for anomaly/trend analysis"
    )
    chat_model: str = Field(
        default="qwen3:8b", description="Model used for chat/RAG responses"
    )
    embedding_model: str = Field(
        default="nomic-embed-text", description="Model used to generate embeddings"
    )

    # Generation parameters
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    num_ctx: int = Field(default=8192, description="Context window size")
    timeout_seconds: int = Field(default=120, description="LLM request timeout")


class DatabaseConfig(BaseSettings):
    """SQLite database configuration."""

    model_config = SettingsConfigDict(env_prefix="FINSIGHT_DB_", env_file=".env", extra="ignore")

    # Relative to project root; resolved to absolute in Settings
    path: str = Field(default="data/db/finsight.db", description="SQLite database file path")
    echo_sql: bool = Field(default=False, description="Log all SQL statements")
    pool_size: int = Field(default=5)
    max_overflow: int = Field(default=10)


class ChromaConfig(BaseSettings):
    """Chroma vector database configuration."""

    model_config = SettingsConfigDict(env_prefix="FINSIGHT_CHROMA_", env_file=".env", extra="ignore")

    persist_directory: str = Field(
        default="data/chroma", description="Directory for Chroma persistence"
    )
    collection_name: str = Field(
        default="finsight_statements", description="Chroma collection name"
    )
    # Number of results to retrieve for RAG
    retrieval_top_k: int = Field(default=6)


class StorageConfig(BaseSettings):
    """File storage configuration."""

    model_config = SettingsConfigDict(env_prefix="FINSIGHT_STORAGE_", env_file=".env", extra="ignore")

    uploads_directory: str = Field(
        default="data/uploads", description="Directory for uploaded financial documents"
    )
    max_file_size_mb: int = Field(default=50, description="Maximum upload size in megabytes")
    allowed_extensions: list[str] = Field(default=[".pdf", ".csv"])


class Settings(BaseSettings):
    """Top-level application settings.

    Aggregates all sub-configs and adds app-level settings.
    """

    model_config = SettingsConfigDict(
        env_prefix="FINSIGHT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App metadata
    app_name: str = "FinSight AI"
    app_version: str = "0.1.0"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = Field(default=True)
    log_level: str = Field(default="INFO")

    # CORS
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # Base directory (resolved at runtime)
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)

    # Sub-configs (instantiated with defaults; override via env vars)
    ollama: OllamaModelConfig = Field(default_factory=OllamaModelConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    chroma: ChromaConfig = Field(default_factory=ChromaConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

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

    def get_uploads_dir(self) -> Path:
        path = self.base_dir / self.storage.uploads_directory
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_chroma_dir(self) -> Path:
        path = self.base_dir / self.chroma.persist_directory
        path.mkdir(parents=True, exist_ok=True)
        return path


# Singleton instance — import this throughout the app
settings = Settings()
