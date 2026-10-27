"""Local text-to-image engines.

``DiffusersImageEngine`` runs an open-weight model (default ``stabilityai/sd-turbo``)
with Hugging Face Diffusers. It never downloads at request time and never calls a
remote inference API: weights must already be in ``IMAGE_MODEL_CACHE_DIR``
(see ``scripts/download_model.py``).

PyTorch and Diffusers are imported lazily, so the API runs, and health checks stay
cheap, even when they are not installed.
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
from app.schemas.generation import VisualStyle

if TYPE_CHECKING:
    from PIL.Image import Image

logger = logging.getLogger(__name__)

REQUIRED_MODULES = ("torch", "diffusers", "transformers", "huggingface_hub", "accelerate", "safetensors")

# Appended to the user's prompt so the style picker actually changes the result.
STYLE_PROMPTS: dict[VisualStyle, str] = {
    VisualStyle.CINEMATIC: "cinematic film still, anamorphic lens, dramatic motivated lighting, film grain",
    VisualStyle.DREAMLIKE: "dreamlike, soft bloom, pastel haze, ethereal atmosphere",
    VisualStyle.NEON_NOIR: "neon noir, wet reflective streets, magenta and cyan neon, deep shadows",
    VisualStyle.DOCUMENTARY: "documentary photograph, natural light, true-to-life colour",
    VisualStyle.ANIME: "anime illustration, clean linework, luminous sky, vibrant colour",
    VisualStyle.GOLDEN_HOUR: "golden hour, low warm sunlight, long shadows, rich amber tones",
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
    return f"{prompt}, {STYLE_PROMPTS[style]}"


class DiffusersImageEngine:
    name = "diffusers"

    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.image_model_id
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

    # --- cheap checks -------------------------------------------------------------

    @staticmethod
    def libraries_installed() -> bool:
        return all(importlib.util.find_spec(m) is not None for m in REQUIRED_MODULES)

    def weights_present(self) -> bool:
        if importlib.util.find_spec("huggingface_hub") is None:
            return False
        from huggingface_hub import try_to_load_from_cache

        found = try_to_load_from_cache(self.model_id, "model_index.json", cache_dir=str(self._cache_dir))
        return isinstance(found, str)

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
        from diffusers import AutoPipelineForText2Image

        device = self._resolve_device(torch)
        # FP16 halves VRAM on GPUs; CPUs run FP32 (FP16 matmuls are slow or unsupported there).
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
            # Some models publish no fp16 variant; fall back to the default weights if those are cached.
            try:
                pipe = AutoPipelineForText2Image.from_pretrained(self.model_id, **common)
            except OSError:
                raise EngineError(
                    "model_not_downloaded",
                    "The model weights are missing or incomplete. Re-run `python scripts/download_model.py`.",
                ) from None

        optimizations: list[str] = []
        offload = False
        if device == "cuda":
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
            if self._attention_slicing == "on" or (self._attention_slicing == "auto" and vram_gb <= 6):
                pipe.enable_attention_slicing()
                optimizations.append("attention_slicing")
                if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_tiling"):
                    pipe.vae.enable_tiling()
                    optimizations.append("vae_tiling")
            if self._cpu_offload == "on" or (self._cpu_offload == "auto" and vram_gb < 4):
                pipe.enable_model_cpu_offload()  # moves modules to the GPU only while they run
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
                pipe._interrupt = True  # diffusers' supported way to stop between steps
            return kwargs

        result = None
        try:
            with torch.inference_mode():
                result = self._pipe(
                    prompt=build_prompt(params.prompt, params.style),
                    width=params.width,
                    height=params.height,
                    num_inference_steps=params.steps,
                    guidance_scale=0.0,  # turbo models are distilled to run without CFG
                    generator=generator,
                    callback_on_step_end=stop_after_deadline,
                )
            if timed_out:
                # An interrupted run yields a half-denoised image; never return that as a result.
                raise EngineError("generation_timeout", "Generation took too long and was stopped.", retryable=True)
            return result.images[0], device
        except EngineError:
            raise
        except torch.cuda.OutOfMemoryError:
            raise EngineError(
                "gpu_out_of_memory",
                "The GPU ran out of memory. Try the Standard resolution or close other GPU apps, then retry.",
                retryable=True,
            ) from None
        except MemoryError:
            raise EngineError(
                "out_of_memory", "The server ran out of memory. Try the Standard resolution.", retryable=True
            ) from None
        finally:
            del result
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()
