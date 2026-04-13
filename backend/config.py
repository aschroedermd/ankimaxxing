"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field
import os


class Settings(BaseSettings):
    # AnkiConnect
    anki_connect_url: str = Field(default="http://localhost:8765", env="ANKI_CONNECT_URL")
    anki_connect_version: int = Field(default=6, env="ANKI_CONNECT_VERSION")
    anki_connect_timeout: float = Field(default=30.0, env="ANKI_CONNECT_TIMEOUT")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./anki_maxxing.db",
        env="DATABASE_URL",
    )

    # API
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        env="CORS_ORIGINS",
    )

    # Encryption key for stored API keys (generate with: Fernet.generate_key())
    encryption_key: str = Field(default="", env="ENCRYPTION_KEY")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_card_content: bool = Field(default=False, env="LOG_CARD_CONTENT")

    # App-managed field names added to note types
    ai_rewrite_data_field: str = "AIRewriteData"
    ai_rewrite_meta_field: str = "AIRewriteMeta"
    ai_validation_data_field: str = "AIValidationData"
    ai_rewrite_status_field: str = "AIRewriteStatus"

    # App identifier in cloned note type names
    app_model_suffix: str = " (AI Rewriter)"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
