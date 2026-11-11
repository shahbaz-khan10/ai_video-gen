"""Model Registry for AI Video Studio.

Provides metadata and configuration profiles for supported open-weight models,
including photorealistic models (e.g. Realistic Vision, SDXL) and rapid draft models (SD-Turbo).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModelFamily = Literal["sd15", "sdxl", "sd-turbo"]


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    name: str
    family: ModelFamily
    description: str
    default_steps: int
    min_steps: int
    max_steps: int
    default_guidance_scale: float
    supports_negative_prompt: bool
    native_resolution: tuple[int, int]
    vram_gb_fp16: float
    recommended_device: str
    license_name: str
    license_url: str


SUPPORTED_MODELS: dict[str, ModelProfile] = {
    "SG161222/Realistic_Vision_V5.1_noVAE": ModelProfile(
        model_id="SG161222/Realistic_Vision_V5.1_noVAE",
        name="Realistic Vision V5.1",
        family="sd15",
        description="Top-tier open-weight photorealistic model. Exceptional human facial detail, organic hands, natural skin textures, and balanced multi-person scenes. Highly optimized for 8GB VRAM.",
        default_steps=25,
        min_steps=15,
        max_steps=50,
        default_guidance_scale=6.5,
        supports_negative_prompt=True,
        native_resolution=(512, 768),
        vram_gb_fp16=3.8,
        recommended_device="cuda",
        license_name="CreativeML Open RAIL-M",
        license_url="https://huggingface.co/SG161222/Realistic_Vision_V5.1_noVAE/blob/main/LICENSE.txt",
    ),
    "stabilityai/stable-diffusion-xl-base-1.0": ModelProfile(
        model_id="stabilityai/stable-diffusion-xl-base-1.0",
        name="SDXL Base 1.0",
        family="sdxl",
        description="High-resolution (1024x1024) foundation model with dual text encoders for deep prompt comprehension and cinematic environment rendering.",
        default_steps=30,
        min_steps=20,
        max_steps=50,
        default_guidance_scale=7.0,
        supports_negative_prompt=True,
        native_resolution=(1024, 1024),
        vram_gb_fp16=6.5,
        recommended_device="cuda",
        license_name="CreativeML Open RAIL++-M",
        license_url="https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md",
    ),
    "stabilityai/sd-turbo": ModelProfile(
        model_id="stabilityai/sd-turbo",
        name="SD-Turbo (Fast Draft)",
        family="sd-turbo",
        description="Single-step adversarial diffusion distillation model for ultra-fast previews. Low anatomical detail.",
        default_steps=1,
        min_steps=1,
        max_steps=4,
        default_guidance_scale=0.0,
        supports_negative_prompt=False,
        native_resolution=(512, 512),
        vram_gb_fp16=2.6,
        recommended_device="cpu",
        license_name="Stability AI Community License",
        license_url="https://huggingface.co/stabilityai/sd-turbo/blob/main/LICENSE.md",
    ),
}

DEFAULT_MODEL_ID = "SG161222/Realistic_Vision_V5.1_noVAE"


def get_model_profile(model_id: str) -> ModelProfile:
    """Returns profile for known model or a safe default based on model ID."""
    if model_id in SUPPORTED_MODELS:
        return SUPPORTED_MODELS[model_id]
    if "xl" in model_id.lower():
        return ModelProfile(
            model_id=model_id,
            name=model_id.split("/")[-1],
            family="sdxl",
            description="Custom SDXL Photorealistic Model",
            default_steps=30,
            min_steps=15,
            max_steps=50,
            default_guidance_scale=7.0,
            supports_negative_prompt=True,
            native_resolution=(1024, 1024),
            vram_gb_fp16=6.5,
            recommended_device="cuda",
            license_name="Open RAIL",
            license_url="https://huggingface.co/" + model_id,
        )
    if "turbo" in model_id.lower():
        return SUPPORTED_MODELS["stabilityai/sd-turbo"]
    return SUPPORTED_MODELS[DEFAULT_MODEL_ID]

