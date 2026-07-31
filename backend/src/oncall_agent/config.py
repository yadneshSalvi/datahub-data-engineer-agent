"""Application configuration loaded from environment variables and the repository .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings shared by the backend and demo utilities."""

    datahub_gms_url: str = "http://localhost:8081"
    datahub_ui_url: str = "http://localhost:9002"
    openai_api_key: str | None = None
    agent_model: str = Field(default="gpt-5.6-sol", validation_alias="ONCALL_AGENT_MODEL")
    max_turns: int = Field(default=40, validation_alias="ONCALL_MAX_TURNS")
    platform: str = Field(default="oncall", validation_alias="ONCALL_PLATFORM")
    name_prefix: str = Field(default="oncall_demo.", validation_alias="ONCALL_NAME_PREFIX")
    frontend_url: str = Field(
        default="http://localhost:3001", validation_alias="ONCALL_FRONTEND_URL"
    )
    slack_webhook_url: str | None = None
    db_path: str = Field(default="./data/oncall.db", validation_alias="ONCALL_DB")
    mcp_enabled: bool = Field(default=True, validation_alias="ONCALL_MCP_ENABLED")

    model_config = SettingsConfigDict(
        env_file=_REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="",
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable-by-convention settings instance."""

    return Settings()
