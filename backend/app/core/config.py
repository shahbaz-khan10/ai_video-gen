"""Application settings, loaded from environment variables or ``.env``.

General API settings use the ``AVS_`` prefix. Image-model settings use the plain
``IMAGE_*`` names documented in ``.env.example``.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import __version__

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _image_env(name: str) -> AliasChoices:
    # Accept both IMAGE_X and AVS_IMAGE_X so either convention works.
    return AliasChoices(name, f"AVS_{name}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AVS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_by_name=True,
    )

    app_name: str = "AI Video Studio API"
    version: str = __version__
    environment: Literal["development", "test", "production"] = "development"

    # Comma-separated in the environment, e.g. AVS_CORS_ORIGINS=http://localhost:3000,https://studio.example.com
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    docs_enabled: bool = True
    # Upper bound for any request body. Generation requests are small JSON documents.
    max_request_bytes: int = 64 * 1024

    # --- Text-to-image engine ----------------------------------------------------
    # "diffusers" runs a local model; "none" disables generation (used by the test suite).
    image_engine: Literal["diffusers", "none"] = Field("diffusers", validation_alias=_image_env("IMAGE_ENGINE"))
    image_model_id: str = Field("stabilityai/sd-turbo", validation_alias=_image_env("IMAGE_MODEL_ID"))
    # Weight variant to load ("fp16" downloads only half-precision files). Empty for the default weights.
    image_model_variant: str = Field("fp16", validation_alias=_image_env("IMAGE_MODEL_VARIANT"))
    # Where generated PNGs are written. Relative paths resolve against backend/.
    image_output_dir: Path = Field(BACKEND_DIR / "outputs" / "images", validation_alias=_image_env("IMAGE_OUTPUT_DIR"))
    # Hugging Face cache for model weights. Unset uses the standard HF cache (~/.cache/huggingface).
    image_model_cache_dir: Path | None = Field(None, validation_alias=_image_env("IMAGE_MODEL_CACHE_DIR"))
    # The server never downloads weights unless this is true. Use scripts/download_model.py instead.
    image_allow_download: bool = Field(False, validation_alias=_image_env("IMAGE_ALLOW_DOWNLOAD"))
    image_device: Literal["auto", "cuda", "cpu"] = Field("auto", validation_alias=_image_env("IMAGE_DEVICE"))
    image_max_concurrent_jobs: int = Field(1, ge=1, le=4, validation_alias=_image_env("IMAGE_MAX_CONCURRENT_JOBS"))
    # Jobs waiting or running at once; further submissions get 429.
    image_max_queued_jobs: int = Field(8, ge=1, le=100, validation_alias=_image_env("IMAGE_MAX_QUEUED_JOBS"))
    image_max_steps: int = Field(4, ge=1, le=50, validation_alias=_image_env("IMAGE_MAX_STEPS"))
    # SD-Turbo is trained without classifier-free guidance, so 0.0 is correct for it.
    image_guidance_scale: float = Field(0.0, ge=0.0, le=20.0, validation_alias=_image_env("IMAGE_GUIDANCE_SCALE"))
    image_generation_timeout_seconds: int = Field(
        300, ge=10, le=3600, validation_alias=_image_env("IMAGE_GENERATION_TIMEOUT_SECONDS")
    )
    # Optional VRAM savers. Off by default: SD-Turbo fits comfortably in 8 GB and slicing slows SDPA attention.
    image_attention_slicing: bool = Field(False, validation_alias=_image_env("IMAGE_ATTENTION_SLICING"))
    image_cpu_offload: bool = Field(False, validation_alias=_image_env("IMAGE_CPU_OFFLOAD"))

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("image_model_cache_dir", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("image_output_dir", "image_model_cache_dir")
    @classmethod
    def _resolve_dir(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return (value if value.is_absolute() else BACKEND_DIR / value).resolve()

    @model_validator(mode="after")
    def _no_wildcard_in_production(self) -> "Settings":
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("AVS_CORS_ORIGINS must list explicit origins in production, not '*'.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
