"""Application settings, loaded from environment variables or ``.env``.

General settings use the ``AVS_`` prefix. Image-model settings use the plain
``IMAGE_*`` names (``AVS_IMAGE_*`` also works).
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import __version__

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _image_env(name: str) -> AliasChoices:
    return AliasChoices(name, f"AVS_{name}", name.lower())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AVS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "AI Video Studio API"
    version: str = __version__
    environment: Literal["development", "test", "production"] = "development"

    # Comma-separated in the environment, e.g. AVS_CORS_ORIGINS=http://localhost:3000,https://studio.example.com
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    docs_enabled: bool = True
    # Upper bound for any request body. Generation requests are small JSON documents.
    max_request_bytes: int = 64 * 1024

    # --- Local text-to-image model --------------------------------------------------
    # "diffusers" runs a local open-weight model; "none" disables generation entirely.
    image_engine: Literal["diffusers", "none"] = Field("diffusers", validation_alias=_image_env("IMAGE_ENGINE"))
    image_model_id: str = Field("stabilityai/sd-turbo", validation_alias=_image_env("IMAGE_MODEL_ID"))
    # Weights are only read from here (never fetched at request time). See scripts/download_model.py.
    image_model_cache_dir: Path = Field(BACKEND_DIR / "models", validation_alias=_image_env("IMAGE_MODEL_CACHE_DIR"))
    image_output_dir: Path = Field(BACKEND_DIR / "outputs" / "images", validation_alias=_image_env("IMAGE_OUTPUT_DIR"))
    # "auto" uses CUDA when PyTorch can see a GPU, otherwise the CPU.
    image_device: Literal["auto", "cuda", "cpu"] = Field("auto", validation_alias=_image_env("IMAGE_DEVICE"))
    image_max_concurrent_jobs: int = Field(1, ge=1, le=4, validation_alias=_image_env("IMAGE_MAX_CONCURRENT_JOBS"))
    # Jobs waiting beyond this are refused with 429 instead of piling up.
    image_max_queued_jobs: int = Field(8, ge=1, le=100, validation_alias=_image_env("IMAGE_MAX_QUEUED_JOBS"))
    # Checked between denoising steps; a job past this is stopped and marked failed.
    image_timeout_seconds: int = Field(600, ge=10, le=3600, validation_alias=_image_env("IMAGE_TIMEOUT_SECONDS"))
    # On CUDA: "auto" enables attention slicing / CPU offload only for small-VRAM GPUs.
    image_attention_slicing: Literal["auto", "on", "off"] = Field(
        "auto", validation_alias=_image_env("IMAGE_ATTENTION_SLICING")
    )
    image_cpu_offload: Literal["auto", "on", "off"] = Field("auto", validation_alias=_image_env("IMAGE_CPU_OFFLOAD"))

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("image_model_cache_dir", "image_output_dir")
    @classmethod
    def _absolute_from_backend(cls, value: Path) -> Path:
        # Relative paths are resolved against backend/, not the shell's working directory.
        return (value if value.is_absolute() else BACKEND_DIR / value).resolve()

    @model_validator(mode="after")
    def _no_wildcard_in_production(self) -> "Settings":
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("AVS_CORS_ORIGINS must list explicit origins in production, not '*'.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
