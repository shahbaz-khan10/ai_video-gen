"""Local photorealistic text-to-image engines.

Upgraded to support professional open-weight models (Realistic Vision, SDXL) alongside
rapid draft models (SD-Turbo). Features intelligent prompt understanding, scene planning,
Classifier-Free Guidance (CFG), negative prompt engineering, and VRAM management
optimized for GPUs like NVIDIA GeForce RTX 3050 (8GB) with graceful CPU fallback.
"""

from __future__ import annotations

import gc
import importlib.util
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from app.core.config import Settings
from app.core.models_registry import DEFAULT_MODEL_ID, get_model_profile, is_known_model
from app.schemas.generation import VisualStyle
from app.services.prompt_understanding import PromptUnderstandingEngine

if TYPE_CHECKING:
    from PIL.Image import Image

logger = logging.getLogger(__name__)

REQUIRED_MODULES = ("torch", "diffusers", "transformers", "huggingface_hub", "accelerate", "safetensors")

STYLE_PROMPTS: dict[VisualStyle, str] = {
    VisualStyle.CINEMATIC: "cinematic film still, anamorphic lens, dramatic motivated lighting, film grain",
    VisualStyle.DREAMLIKE: "dreamlike, soft bloom, pastel haze, ethereal atmosphere",
    VisualStyle.NEON_NOIR: "neon noir, wet reflective streets, magenta and cyan neon, deep shadows",
    VisualStyle.DOCUMENTARY: "documentary photograph, natural light, true-to-life colour",
    VisualStyle.ANIME: "anime illustration, clean linework, luminous sky, vibrant colour",
    VisualStyle.GOLDEN_HOUR: "golden hour, low warm sunlight, long shadows, rich amber tones",
    VisualStyle.PHOTOREALISTIC: "photorealistic raw color photograph, 35mm lens, natural skin texture, visible pores, authentic lighting",
    VisualStyle.PORTRAIT: "portrait photography, professional studio lighting, 85mm portrait lens, shallow depth of field, sharp eyes, natural skin tone",
    VisualStyle.GROUP_PHOTO: "group photography, wide angle 35mm lens, crisp focus across all subjects, natural spatial composition",
    VisualStyle.STREET: "street photography, candid 35mm documentary style, natural ambient daylight, realistic urban texture",
}


class EngineError(Exception):
    """A failure that is safe to show to users. Never carries paths or stack traces."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


ModelState = Literal["unavailable", "not_downloaded", "not_loaded", "loading", "loaded", "error"]


@dataclass
class EngineStatus:
    state: ModelState
    detail: str
    model_id: str
    device: str | None = None
    optimizations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImageParams:
    prompt: str
    style: VisualStyle
    width: int
    height: int
    steps: int
    seed: int
    negative_prompt: str | None = None
    guidance_scale: float | None = None


class ImageEngine(Protocol):
    name: str
    model_id: str

    def status(self) -> EngineStatus:
        """Cheap status check. Must not load the model."""
        ...

    def ensure_can_accept(self) -> None:
        """Raise EngineError if a job could not possibly run (e.g. libraries or weights missing)."""
        ...

    def load(self) -> None:
        """Load the model once. Safe to call repeatedly."""
        ...

    def generate(self, params: ImageParams, deadline: float) -> tuple[Image, str]:
        """Blocking inference. Returns the image and the device it ran on."""
        ...


def build_prompt(prompt: str, style: VisualStyle) -> str:
    """Combines user prompt with style tokens."""
    return f"{prompt}, {STYLE_PROMPTS[style]}"


class DiffusersImageEngine:
    name = "diffusers"

    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.image_model_id
        self._profile = get_model_profile(self.model_id)
        self._cache_dir = settings.image_model_cache_dir
        self._requested_device = settings.image_device
        self._attention_slicing = settings.image_attention_slicing
        self._cpu_offload = settings.image_cpu_offload
        self._lock = threading.Lock()
        self._pipe: Any = None
        self._device: str | None = None
        self._offloaded = False
        self._optimizations: list[str] = []
        self._loading = False
        self._load_error: EngineError | None = None
        # Exact prompt sent to the model by the last generate() call (for benchmarks and reporting).
        self.last_prompt: str | None = None

    # --- cheap checks -------------------------------------------------------------

    @staticmethod
    def libraries_installed() -> bool:
        return all(importlib.util.find_spec(m) is not None for m in REQUIRED_MODULES)

    def weights_present(self) -> bool:
        if importlib.util.find_spec("huggingface_hub") is None:
            return False
        from huggingface_hub import try_to_load_from_cache

        cache_dir = str(self._cache_dir)
        index_path = try_to_load_from_cache(self.model_id, "model_index.json", cache_dir=cache_dir)
        if not isinstance(index_path, str):
            return False
        import json

        try:
            with open(index_path, encoding="utf-8") as fh:
                index = json.load(fh)
        except (OSError, ValueError):
            return False
        weight_files = {
            "diffusers": ("diffusion_pytorch_model.fp16.safetensors", "diffusion_pytorch_model.safetensors"),
            "transformers": ("model.fp16.safetensors", "model.safetensors"),
        }
        for component, spec in index.items():
            if not (isinstance(spec, list) and len(spec) == 2 and spec[0] in weight_files):
                continue
            if any(kind in str(spec[1]) for kind in ("Tokenizer", "Scheduler", "Processor", "FeatureExtractor")):
                continue
            candidates = (f"{component}/{name}" for name in weight_files[spec[0]])
            if not any(isinstance(try_to_load_from_cache(self.model_id, c, cache_dir=cache_dir), str) for c in candidates):
                return False
        return True

    def status(self) -> EngineStatus:
        base = {"model_id": self.model_id, "device": self._device, "optimizations": list(self._optimizations)}
        if self._pipe is not None:
            return EngineStatus("loaded", f"Loaded on {self._device}.", **base)
        if self._loading:
            return EngineStatus("loading", "The model is loading into memory.", **base)
        if not self.libraries_installed():
            return EngineStatus(
                "unavailable", "AI libraries (PyTorch, Diffusers) are not installed on the server.", **base
            )
        if not self.weights_present():
            return EngineStatus("not_downloaded", "Model weights have not been downloaded yet.", **base)
        if self._load_error is not None:
            return EngineStatus("error", self._load_error.message, **base)
        return EngineStatus("not_loaded", "Weights are downloaded; the model loads on first use.", **base)

    def ensure_can_accept(self) -> None:
        if not self.libraries_installed():
            raise EngineError(
                "ai_libraries_missing",
                "The server is missing the AI libraries (PyTorch, Diffusers). See backend/README.md to install them.",
            )
        if not self.weights_present():
            raise EngineError(
                "model_not_downloaded",
                f"The model weights for {self.model_id} are not downloaded yet. "
                "Run `python scripts/download_model.py` in backend/ (needs internet once).",
            )

    # --- loading ------------------------------------------------------------------

    def load(self) -> None:
        with self._lock:
            if self._pipe is not None:
                return
            self.ensure_can_accept()
            self._loading = True
            self._load_error = None
            try:
                self._pipe = self._build_pipeline()
            except EngineError as err:
                self._load_error = err
                raise
            except Exception:
                logger.exception("Image model failed to load")
                self._load_error = EngineError("model_load_failed", "The image model failed to load.", retryable=True)
                raise self._load_error from None
            finally:
                self._loading = False

    def unload(self) -> None:
        """Frees the model's RAM and VRAM (e.g. before a video job). The next image job loads it again."""
        with self._lock:
            if self._pipe is None:
                return
            self._pipe = None
            self._device = None
            self._optimizations = []
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            logger.info("Image model unloaded to free memory")

    def _resolve_device(self, torch: Any) -> str:
        cuda = torch.cuda.is_available()
        if self._requested_device == "cuda" and not cuda:
            raise EngineError(
                "cuda_unavailable",
                "IMAGE_DEVICE is set to cuda, but PyTorch cannot see a CUDA GPU. "
                "Install a CUDA build of PyTorch or set IMAGE_DEVICE=cpu.",
            )
        if self._requested_device == "cpu":
            return "cpu"
        return "cuda" if cuda else "cpu"

    def _build_pipeline(self) -> Any:
        import torch
        from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler

        device = self._resolve_device(torch)
        dtype = torch.float16 if device == "cuda" else torch.float32
        common = {
            "torch_dtype": dtype,
            "cache_dir": str(self._cache_dir),
            "local_files_only": True,
            "use_safetensors": True,
        }
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(self.model_id, variant="fp16", **common)
        except (OSError, ValueError):
            try:
                pipe = AutoPipelineForText2Image.from_pretrained(self.model_id, **common)
            except OSError:
                raise EngineError(
                    "model_not_downloaded",
                    "The model weights are missing or incomplete. Re-run `python scripts/download_model.py`.",
                ) from None

        # Use the sampler each model is tuned for (DPM++ 2M Karras, or DPM++ SDE Karras for Lightning models).
        if self._profile.scheduler != "default" and hasattr(pipe, "scheduler"):
            extra = {"algorithm_type": "sde-dpmsolver++"} if self._profile.scheduler == "sde-karras" else {}
            try:
                pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                    pipe.scheduler.config, use_karras_sigmas=True, **extra
                )
            except Exception:
                logger.warning("Could not switch scheduler for %s; keeping the model's own", self.model_id)

        optimizations: list[str] = []
        offload = False
        if device == "cuda":
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
            # RTX 3050 (8GB) memory management: enable attention slicing & VAE tiling
            if self._attention_slicing == "on" or (self._attention_slicing == "auto" and vram_gb <= 8):
                pipe.enable_attention_slicing()
                optimizations.append("attention_slicing")
                if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_tiling"):
                    pipe.vae.enable_tiling()
                    optimizations.append("vae_tiling")
            # Offload when the model's weights would leave too little VRAM for activations (SDXL on 8 GB,
            # which also drives the desktop). Only the sub-model in use then sits on the GPU.
            needs_offload = self._profile.vram_gb_fp16 > vram_gb - 2.0
            if self._cpu_offload == "on" or (self._cpu_offload == "auto" and (vram_gb < 6 or needs_offload)):
                pipe.enable_model_cpu_offload()
                optimizations.append("model_cpu_offload")
                offload = True
            optimizations.append(f"fp16 ({vram_gb:.1f} GB VRAM)")
        if not offload:
            pipe = pipe.to(device)
        pipe.set_progress_bar_config(disable=True)

        self._device = device
        self._offloaded = offload
        self._optimizations = optimizations
        logger.info("Image model %s loaded on %s %s", self.model_id, device, optimizations)
        return pipe

    # --- inference ----------------------------------------------------------------

    def _fit_prompt(self, parts: list[str]) -> str:
        """Joins prompt parts in priority order, dropping later parts that would exceed CLIP's token limit."""
        tokenizer = getattr(self._pipe, "tokenizer", None)
        if tokenizer is None:
            return ", ".join(parts)
        budget = tokenizer.model_max_length - 2  # start and end tokens
        kept: list[str] = []
        for part in parts:
            candidate = ", ".join([*kept, part])
            # The first part (the user's prompt) is always kept, even if CLIP has to trim its tail.
            if not kept or len(tokenizer(candidate, add_special_tokens=False).input_ids) <= budget:
                kept.append(part)
        return ", ".join(kept)

    def generate(self, params: ImageParams, deadline: float) -> tuple[Image, str]:
        self.load()
        import torch

        device = self._device or "cpu"
        generator = torch.Generator(device="cpu" if device == "cpu" or self._offloaded else "cuda")
        generator.manual_seed(params.seed)
        timed_out = False

        def stop_after_deadline(pipe: Any, _step: int, _timestep: Any, kwargs: dict) -> dict:
            nonlocal timed_out
            if time.monotonic() > deadline:
                timed_out = True
                pipe._interrupt = True
            return kwargs

        # Intelligent prompt understanding & scene planning
        scene_plan = PromptUnderstandingEngine.plan_scene(params.prompt, params.style)

        # The text encoder reads only 77 tokens, so the model gets the user's own words first, then the
        # explicit counts ("one male teacher, 10 students"), then the style, each only while it fits.
        from app.services.scene_planner import RulePlanner, build_image_prompt_parts, negative_terms

        plan = RulePlanner.plan(params.prompt)
        prompt_text = self._fit_prompt(build_image_prompt_parts(plan, STYLE_PROMPTS.get(params.style)))
        self.last_prompt = prompt_text

        # Negative prompt resolution
        if self._profile.supports_negative_prompt:
            base_negative = scene_plan.negative_prompt
            # "no glasses" / "without people" in the prompt: diffusion models draw named things, so they
            # also go to the negative prompt.
            unwanted = negative_terms(params.prompt)
            if unwanted:
                base_negative = f"{', '.join(unwanted)}, {base_negative}"
            if params.negative_prompt and params.negative_prompt.strip():
                negative_text = f"{params.negative_prompt.strip()}, {base_negative}"
            else:
                negative_text = base_negative
            guidance = params.guidance_scale if params.guidance_scale is not None else self._profile.default_guidance_scale
        else:
            negative_text = None
            guidance = 0.0  # distilled turbo models run without CFG

        inference_kwargs: dict[str, Any] = {
            "prompt": prompt_text,
            "width": params.width,
            "height": params.height,
            "num_inference_steps": self._profile.clamp_steps(params.steps)
            if is_known_model(self.model_id)
            else params.steps,
            "guidance_scale": guidance,
            "generator": generator,
            "callback_on_step_end": stop_after_deadline,
        }
        if negative_text is not None:
            inference_kwargs["negative_prompt"] = negative_text

        result = None
        try:
            with torch.inference_mode():
                result = self._pipe(**inference_kwargs)
            if timed_out:
                raise EngineError("generation_timeout", "Generation took too long and was stopped.", retryable=True)
            return result.images[0], device
        except EngineError:
            raise
        except torch.cuda.OutOfMemoryError:
            raise EngineError(
                "gpu_out_of_memory",
                "The GPU ran out of memory. Try Standard resolution or close other GPU apps, then retry.",
                retryable=True,
            ) from None
        except MemoryError:
            raise EngineError(
                "out_of_memory", "The server ran out of memory. Try Standard resolution.", retryable=True
            ) from None
        finally:
            del result
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()
