"""Application settings, loaded from environment variables (prefix ``AVS_``) or ``.env``."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AVS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Video Studio API"
    version: str = __version__
    environment: Literal["development", "test", "production"] = "development"

    # Comma-separated in the environment, e.g. AVS_CORS_ORIGINS=http://localhost:3000,https://studio.example.com
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    docs_enabled: bool = True
    # Upper bound for any request body. Generation requests are small JSON documents.
    max_request_bytes: int = 64 * 1024

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _no_wildcard_in_production(self) -> "Settings":
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("AVS_CORS_ORIGINS must list explicit origins in production, not '*'.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
