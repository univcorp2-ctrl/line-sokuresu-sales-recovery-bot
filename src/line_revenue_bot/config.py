from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "development"
    app_name: str = "LINE即レス売上回収Bot"
    database_url: str = "sqlite:///./data/app.db"

    line_channel_secret: str | None = None
    line_channel_access_token: str | None = None
    line_signature_verification: bool = True
    line_reply_dry_run: bool = True

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    admin_api_token: str = Field(default="dev-token-change-me", min_length=8)
    admin_webhook_url: str | None = None
    public_base_url: str = "http://localhost:8000"

    default_tenant_id: str = "demo"
    followup_after_hours: int = 24
    followup_second_after_hours: int = 72

    model_config = SettingsConfigDict(env_file=".env", env_prefix="BOT_", extra="ignore")

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            msg = "Only sqlite:/// URLs are supported in this starter."
            raise ValueError(msg)
        raw_path = self.database_url.removeprefix("sqlite:///")
        return Path(raw_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
