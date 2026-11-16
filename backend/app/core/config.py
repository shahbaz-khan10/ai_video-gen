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
    # RealVisXL Lightning: photoreal SDXL, 4-8 steps. SD-Turbo is faster but merges faces and bodies.
    image_model_id: str = Field("SG161222/RealVisXL_V5.0_Lightning", validation_alias=_image_env("IMAGE_MODEL_ID"))
    # Weights are only read from here (never fetched at request time). See scripts/download_model.py.
    image_model_cache_dir: Path = Field(BACKEND_DIR / "models", validation_alias=_image_env("IMAGE_MODEL_CACHE_DIR"))
    image_output_dir: Path = Field(BACKEND_DIR / "outputs" / "images", validation_alias=_image_env("IMAGE_OUTPUT_DIR"))
    # Uploaded source images for image-to-video (re-encoded PNGs, deleted after 24 h).
    upload_dir: Path = Field(BACKEND_DIR / "outputs" / "uploads", validation_alias=_image_env("UPLOAD_DIR"))
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

    # --- Local text-to-video model --------------------------------------------------
    # "wan" runs Wan2.1 text-to-video (Apache-2.0) through Diffusers; "none" turns video off.
    video_engine: Literal["wan", "none"] = Field("wan", validation_alias=_image_env("VIDEO_ENGINE"))
    video_model_id: str = Field("Wan-AI/Wan2.1-T2V-1.3B-Diffusers", validation_alias=_image_env("VIDEO_MODEL_ID"))
    # Unset uses IMAGE_MODEL_CACHE_DIR, so both models share one download location.
    video_model_cache_dir: Path | None = Field(None, validation_alias=_image_env("VIDEO_MODEL_CACHE_DIR"))
    video_output_dir: Path = Field(BACKEND_DIR / "outputs" / "videos", validation_alias=_image_env("VIDEO_OUTPUT_DIR"))
    video_device: Literal["auto", "cuda", "cpu"] = Field("auto", validation_alias=_image_env("VIDEO_DEVICE"))
    video_max_concurrent_jobs: int = Field(1, ge=1, le=1, validation_alias=_image_env("VIDEO_MAX_CONCURRENT_JOBS"))
    video_max_queued_jobs: int = Field(2, ge=0, le=10, validation_alias=_image_env("VIDEO_MAX_QUEUED_JOBS"))
    # Wan 1.3B on an 8 GB RTX 3050 needs minutes per clip; this stops runaway jobs.
    video_timeout_seconds: int = Field(3600, ge=60, le=7200, validation_alias=_image_env("VIDEO_TIMEOUT_SECONDS"))
    # "fastwan": FastWan2.1 T2V 1.3B (Apache-2.0), DMD-distilled to 3 steps without guidance. Measured on an
    # RTX 3050: 5 s at 480p in 2.7 min vs 17.3 min for "wan" (25 steps + guidance), with equal or better
    # prompt adherence on the benchmark prompts. "wan" keeps the original sampler.
    video_sampler: Literal["fastwan", "wan"] = Field("fastwan", validation_alias=_image_env("VIDEO_SAMPLER"))
    video_fast_model_id: str = Field(
        "FastVideo/FastWan2.1-T2V-1.3B-Diffusers", validation_alias=_image_env("VIDEO_FAST_MODEL_ID")
    )
    # Scene-to-scene continuity for long videos: VACE starts each clip from the previous clip's last frame.
    video_continuity_model_id: str = Field(
        "Wan-AI/Wan2.1-VACE-1.3B-diffusers", validation_alias=_image_env("VIDEO_CONTINUITY_MODEL_ID")
    )
    video_fps: int = Field(16, ge=8, le=30, validation_alias=_image_env("VIDEO_FPS"))
    # VAE decode precision. Measured on the RTX 3050 (docs/speed): bf16 decodes a Draft clip in 15.8 s instead of
    # 39.9 s (fp32 tiled) and a 480p clip in 56 s instead of 97 s, PSNR 57 dB vs fp32 (no visible difference).
    video_vae_dtype: Literal["bfloat16", "float32"] = Field("bfloat16", validation_alias=_image_env("VIDEO_VAE_DTYPE"))
    # Free memory required before the video model loads / before each clip. Measured: the loaded model uses
    # 14.2 GiB of process RAM and 3.4 GB of VRAM; a 480p clip peaks at ~5 GB of VRAM in total.
    video_min_free_ram_gib: float = Field(15.0, ge=0, le=64, validation_alias=_image_env("VIDEO_MIN_FREE_RAM_GIB"))
    video_min_free_vram_gib: float = Field(4.0, ge=0, le=48, validation_alias=_image_env("VIDEO_MIN_FREE_VRAM_GIB"))
    video_min_free_vram_per_clip_gib: float = Field(
        1.8, ge=0, le=48, validation_alias=_image_env("VIDEO_MIN_FREE_VRAM_PER_CLIP_GIB")
    )
    # A language-model scene planner (Qwen3-1.7B, app/services/llm_planner.py) was evaluated and is NOT wired
    # in: on this CPU it took 77-174 s per prompt and was no better than the rule planner on the benchmark
    # prompts. It is only used by scripts/benchmark_vace_planner.py.
    video_default_steps: int = Field(25, ge=10, le=50, validation_alias=_image_env("VIDEO_DEFAULT_STEPS"))
    # Wan's recommended classifier-free guidance and flow shift (3.0 suits 480p and below).
    video_guidance_scale: float = Field(5.0, ge=1.0, le=10.0, validation_alias=_image_env("VIDEO_GUIDANCE_SCALE"))
    video_flow_shift: float = Field(3.0, ge=1.0, le=12.0, validation_alias=_image_env("VIDEO_FLOW_SHIFT"))
    # The T5 text encoder (~11 GB in bf16) never fits an 8 GB GPU next to the transformer, so by default it
    # runs on the CPU while the transformer and VAE use the GPU (the approach Wan's own `--t5_cpu` uses).
    video_text_encoder_on_cpu: bool = Field(True, validation_alias=_image_env("VIDEO_TEXT_ENCODER_ON_CPU"))
    video_enable_vae_tiling: bool = Field(True, validation_alias=_image_env("VIDEO_ENABLE_VAE_TILING"))

    @field_validator("video_model_cache_dir", mode="before")
    @classmethod
    def _empty_video_cache_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("image_model_cache_dir", "image_output_dir", "video_output_dir", "upload_dir")
    @classmethod
    def _absolute_from_backend(cls, value: Path) -> Path:
        # Relative paths are resolved against backend/, not the shell's working directory.
        return (value if value.is_absolute() else BACKEND_DIR / value).resolve()

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
