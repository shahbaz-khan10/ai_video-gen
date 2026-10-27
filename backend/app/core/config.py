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
    # RealVisXL V5 Lightning: a photorealistic SDXL model distilled for ~4-8 steps (openrail++).
    # For the small, very fast SD-Turbo use the alternative values in .env.example.
    image_model_id: str = Field("SG161222/RealVisXL_V5.0_Lightning", validation_alias=_image_env("IMAGE_MODEL_ID"))
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
    # Size tiers offered for this model (see IMAGE_SIZES). SDXL models are trained at 1024.
    image_resolutions: Annotated[list[int], NoDecode] = Field(
        [768, 1024], validation_alias=_image_env("IMAGE_RESOLUTIONS")
    )
    image_default_resolution: int = Field(1024, validation_alias=_image_env("IMAGE_DEFAULT_RESOLUTION"))
    image_max_steps: int = Field(8, ge=1, le=50, validation_alias=_image_env("IMAGE_MAX_STEPS"))
    # Shown in the UI as Fast / Balanced / Detailed.
    image_step_presets: Annotated[list[int], NoDecode] = Field(
        [4, 6, 8], validation_alias=_image_env("IMAGE_STEP_PRESETS")
    )
    image_default_steps: int = Field(6, ge=1, le=50, validation_alias=_image_env("IMAGE_DEFAULT_STEPS"))
    # RealVisXL Lightning recommends CFG 1.0-2.0. Turbo models (SD-Turbo) need 0.0.
    image_guidance_scale: float = Field(1.5, ge=0.0, le=20.0, validation_alias=_image_env("IMAGE_GUIDANCE_SCALE"))
    # Only has an effect when guidance is above 1.0.
    image_negative_prompt: str = Field(
        "worst quality, low quality, blurry, cartoon, anime, drawing, painting, illustration, render, cgi, "
        "3d, deformed, disfigured, bad anatomy, extra fingers, mutated hands, poorly drawn face, duplicate, "
        "watermark, text",
        validation_alias=_image_env("IMAGE_NEGATIVE_PROMPT"),
    )
    # "dpmpp_sde_karras" is the sampler RealVisXL recommends; "default" keeps the model's own scheduler.
    image_scheduler: Literal["default", "dpmpp_sde_karras"] = Field(
        "dpmpp_sde_karras", validation_alias=_image_env("IMAGE_SCHEDULER")
    )
    image_generation_timeout_seconds: int = Field(
        300, ge=10, le=3600, validation_alias=_image_env("IMAGE_GENERATION_TIMEOUT_SECONDS")
    )
    # VRAM savers. SDXL (~7 GB of FP16 weights) does not fit an 8 GB card in one piece, so CPU offload is on
    # by default: only the sub-model in use sits on the GPU. Attention slicing slows SDPA and stays off.
    image_attention_slicing: bool = Field(False, validation_alias=_image_env("IMAGE_ATTENTION_SLICING"))
    image_cpu_offload: bool = Field(True, validation_alias=_image_env("IMAGE_CPU_OFFLOAD"))

    @field_validator("image_resolutions", "image_step_presets", mode="before")
    @classmethod
    def _split_ints(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _consistent_image_options(self) -> "Settings":
        from app.schemas.generation import IMAGE_SIZES

        if not self.image_resolutions or any(r not in IMAGE_SIZES for r in self.image_resolutions):
            raise ValueError(f"IMAGE_RESOLUTIONS must be a non-empty subset of {sorted(IMAGE_SIZES)}.")
        if self.image_default_resolution not in self.image_resolutions:
            raise ValueError("IMAGE_DEFAULT_RESOLUTION must be one of IMAGE_RESOLUTIONS.")
        steps = [*self.image_step_presets, self.image_default_steps]
        if not self.image_step_presets or any(s < 1 or s > self.image_max_steps for s in steps):
            raise ValueError("IMAGE_STEP_PRESETS and IMAGE_DEFAULT_STEPS must be between 1 and IMAGE_MAX_STEPS.")
        return self

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
