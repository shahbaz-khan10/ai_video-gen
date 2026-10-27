"""Text-to-image engines.

:class:`DiffusersImageEngine` runs a locally cached Hugging Face Diffusers model
(SD-Turbo by default). ``torch`` and ``diffusers`` are imported lazily, so the API
starts, and answers health checks, without loading the model or touching VRAM.
"""

import gc
import importlib.util
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from app.core.config import Settings

if TYPE_CHECKING:
    from PIL.Image import Image

logger = logging.getLogger(__name__)

EngineState = Literal["disabled", "not_installed", "weights_missing", "not_loaded", "loading", "ready", "error"]


class EngineError(Exception):
    """A generation failure whose ``message`` is safe to show in the browser (no paths, no traces)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EngineStatus:
    state: EngineState
    model_id: str | None
    detail: str
    device: str | None = None
    cuda_available: bool | None = None

    @property
    def accepts_jobs(self) -> bool:
        # A model that is not loaded yet is loaded by the first job; a failed load is retried.
        return self.state in ("not_loaded", "loading", "ready", "error")


@dataclass(frozen=True)
class ImageParams:
    prompt: str
    width: int
    height: int
    num_inference_steps: int
    seed: int
    negative_prompt: str | None = None


@dataclass
class GeneratedImage:
    image: "Image"
    device: str
    model_id: str


class ImageEngine(Protocol):
    name: str

    def status(self) -> EngineStatus:
        """Cheap state report. Must not load the model."""
        ...

    def generate(self, params: ImageParams, deadline: float) -> GeneratedImage:
        """Blocking inference. Runs in a worker thread, never on the event loop."""
        ...


class DisabledEngine:
    """No engine configured (``IMAGE_ENGINE=none``). Every submission is refused."""

    name = "none"

    def status(self) -> EngineStatus:
        return EngineStatus(state="disabled", model_id=None, detail="Image generation is disabled (IMAGE_ENGINE=none).")

    def generate(self, params: ImageParams, deadline: float) -> GeneratedImage:
        raise EngineError("engine_not_configured", "AI generation is not connected. No image was generated.")


class GenerationTimeout(Exception):
    pass


def _deps_installed() -> bool:
    return all(importlib.util.find_spec(mod) is not None for mod in ("torch", "diffusers", "transformers"))


class DiffusersImageEngine:
    name = "diffusers"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model_id = settings.image_model_id
        self._pipe: Any = None
        self._device: str | None = None
        self._cuda_available: bool | None = None
        self._loading = False
        self._load_error: EngineError | None = None
        self._installed: bool | None = None
        self._torch_broken = False
        self._probe_lock = threading.Lock()
        self._load_lock = threading.Lock()
        # One pipeline object is not safe to call from several threads at once.
        self._infer_lock = threading.Lock()

    # --- status -------------------------------------------------------------------

    def _probe(self) -> tuple[bool, str | None]:
        """Imports torch once to learn about CUDA. Does not create a CUDA context or allocate VRAM."""
        with self._probe_lock:
            if self._installed is None:
                self._installed = _deps_installed()
            if self._installed and self._cuda_available is None:
                try:
                    import torch
                except (ImportError, OSError) as exc:
                    # e.g. WinError 126: the Microsoft Visual C++ runtime that PyTorch needs is missing.
                    logger.error("PyTorch is installed but failed to load: %s", exc)
                    self._installed = False
                    self._torch_broken = True
                    return False, None

                self._cuda_available = bool(torch.cuda.is_available())
                wanted = self.settings.image_device
                if wanted == "auto":
                    self._device = "cuda" if self._cuda_available else "cpu"
                elif wanted == "cuda" and not self._cuda_available:
                    self._device = None
                else:
                    self._device = wanted
            return bool(self._installed), self._device

    def weights_cached(self) -> bool:
        local = Path(self.model_id)
        if local.is_dir():
            return (local / "model_index.json").is_file()
        try:
            from huggingface_hub import try_to_load_from_cache
        except ImportError:
            return False
        cache_dir = str(self.settings.image_model_cache_dir) if self.settings.image_model_cache_dir else None
        found = try_to_load_from_cache(self.model_id, "model_index.json", cache_dir=cache_dir)
        return isinstance(found, str)

    def status(self) -> EngineStatus:
        installed, device = self._probe()
        base = {"model_id": self.model_id, "device": device, "cuda_available": self._cuda_available}
        if not installed:
            detail = (
                "PyTorch is installed but failed to load. On Windows, install the Microsoft Visual C++ "
                "Redistributable (x64) and restart the API."
                if self._torch_broken
                else "PyTorch and Diffusers are not installed. See the backend README for setup."
            )
            return EngineStatus(state="not_installed", detail=detail, **base)
        if device is None:
            return EngineStatus(
                state="error", detail="IMAGE_DEVICE=cuda is set, but PyTorch cannot access a CUDA GPU.", **base
            )
        if self._pipe is not None:
            return EngineStatus(state="ready", detail=f"Model loaded on {device}.", **base)
        if self._loading:
            return EngineStatus(state="loading", detail="Loading the model into memory.", **base)
        if not self.settings.image_allow_download and not self.weights_cached():
            return EngineStatus(
                state="weights_missing",
                detail="Model weights are not downloaded yet. Run: python scripts/download_model.py",
                **base,
            )
        if self._load_error is not None:
            return EngineStatus(state="error", detail=self._load_error.message, **base)
        return EngineStatus(state="not_loaded", detail="Weights are available. The model loads on the first request.", **base)

    # --- loading ------------------------------------------------------------------

    def _load(self) -> Any:
        with self._load_lock:
            if self._pipe is not None:
                return self._pipe
            installed, device = self._probe()
            if not installed:
                raise EngineError("engine_not_installed", "PyTorch and Diffusers are not installed on the server.")
            if device is None:
                raise EngineError("cuda_unavailable", "A CUDA GPU was requested, but PyTorch cannot access one.")

            self._loading = True
            self._load_error = None
            started = time.monotonic()
            try:
                self._pipe = self._build_pipeline(device)
            except EngineError as exc:
                self._load_error = exc
                raise
            finally:
                self._loading = False
            logger.info("image model loaded model=%s device=%s in %.1fs", self.model_id, device, time.monotonic() - started)
            return self._pipe

    def _build_pipeline(self, device: str) -> Any:
        import torch
        from diffusers import AutoPipelineForText2Image

        s = self.settings
        use_cuda = device == "cuda"
        kwargs: dict[str, Any] = {
            # FP16 halves VRAM on GPU. CPUs run FP32; FP16 weight files are upcast on load.
            "dtype": torch.float16 if use_cuda else torch.float32,
            "use_safetensors": True,
            "local_files_only": not s.image_allow_download,
        }
        if s.image_model_variant:
            kwargs["variant"] = s.image_model_variant
        if s.image_model_cache_dir:
            kwargs["cache_dir"] = str(s.image_model_cache_dir)

        try:
            pipe = AutoPipelineForText2Image.from_pretrained(self.model_id, **kwargs)
        except torch.cuda.OutOfMemoryError as exc:
            self._release()
            raise EngineError("gpu_out_of_memory", "The GPU ran out of memory while loading the model.") from exc
        except (OSError, ValueError) as exc:
            # Missing or partial files, a wrong variant or an unreachable Hub all land here.
            logger.warning("model load failed model=%s: %s", self.model_id, exc)
            if s.image_allow_download:
                raise EngineError(
                    "model_download_failed",
                    "The model could not be downloaded or loaded. Check the internet connection and IMAGE_MODEL_ID.",
                ) from exc
            raise EngineError(
                "model_unavailable",
                "The model weights are missing or incomplete. Run scripts/download_model.py and try again.",
            ) from exc

        pipe.set_progress_bar_config(disable=True)
        if s.image_scheduler == "dpmpp_sde_karras":
            from diffusers import DPMSolverMultistepScheduler

            # DPM++ SDE with Karras sigmas, as RealVisXL recommends (no torchsde dependency).
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                pipe.scheduler.config, algorithm_type="sde-dpmsolver++", use_karras_sigmas=True
            )
        try:
            if use_cuda and s.image_cpu_offload:
                pipe.enable_model_cpu_offload()  # needs accelerate; keeps only the active sub-model on the GPU
            else:
                pipe.to(device)
            if s.image_attention_slicing:
                pipe.enable_attention_slicing()
        except torch.cuda.OutOfMemoryError as exc:
            del pipe
            self._release()
            raise EngineError(
                "gpu_out_of_memory",
                "The GPU ran out of memory while loading the model. Close other GPU apps or set IMAGE_CPU_OFFLOAD=true.",
            ) from exc
        self._device = device
        return pipe

    def _release(self) -> None:
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    # --- inference ----------------------------------------------------------------

    def generate(self, params: ImageParams, deadline: float) -> GeneratedImage:
        pipe = self._load()
        if time.monotonic() > deadline:
            raise EngineError("generation_timeout", "The generation timed out while the model was loading.")

        import torch

        def check_deadline(_pipe: Any, _step: int, _timestep: Any, callback_kwargs: dict) -> dict:
            # Checked between denoising steps; a single step cannot be interrupted.
            if time.monotonic() > deadline:
                raise GenerationTimeout
            return callback_kwargs

        # A CPU generator gives the same image for the same seed on any device.
        generator = torch.Generator(device="cpu").manual_seed(params.seed)
        with self._infer_lock:
            try:
                with torch.inference_mode():
                    output = pipe(
                        prompt=params.prompt,
                        width=params.width,
                        height=params.height,
                        num_inference_steps=params.num_inference_steps,
                        guidance_scale=self.settings.image_guidance_scale,
                        negative_prompt=params.negative_prompt,
                        generator=generator,
                        callback_on_step_end=check_deadline,
                    )
                image = output.images[0]
            except torch.cuda.OutOfMemoryError as exc:
                self._release()
                raise EngineError(
                    "gpu_out_of_memory",
                    "The GPU ran out of memory. Try a smaller resolution, close other GPU apps, or set IMAGE_CPU_OFFLOAD=true.",
                ) from exc
            except GenerationTimeout as exc:
                self._release()
                raise EngineError("generation_timeout", "The generation took too long and was stopped.") from exc
        return GeneratedImage(image=image, device=self._device or "unknown", model_id=self.model_id)


def build_engine(settings: Settings) -> ImageEngine:
    if settings.image_engine == "none":
        return DisabledEngine()
    return DiffusersImageEngine(settings)
