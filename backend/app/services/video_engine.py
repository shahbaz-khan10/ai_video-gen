"""Local text-to-video engines (Phase 5 work).

Restored header: these imports and definitions were missing from the committed file
(the same definitions live in docker/backend/video_engine.py).
"""

from __future__ import annotations

import gc
import importlib.util
import logging
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)

REQUIRED_MODULES = ("torch", "diffusers", "transformers", "huggingface_hub", "accelerate", "safetensors")


class VideoEngineError(Exception):
    """A failure that is safe to show to users."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass
class VideoEngineStatus:
    state: str
    detail: str
    model_id: str
    device: str | None = None
    optimizations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VideoParams:
    prompt: str
    width: int
    height: int
    num_frames: int
    num_inference_steps: int
    seed: int


class VideoEngine(Protocol):
    name: str
    model_id: str
    _device: str | None

    def status(self) -> VideoEngineStatus: ...

    def ensure_can_accept(self) -> None: ...

    def generate(self, params: VideoParams, deadline: float) -> tuple[bytes, dict[str, Any]]: ...


class DisabledVideoEngine:
    """Used when VIDEO_ENGINE=none: reports itself unavailable and refuses every job."""

    name = "none"
    _device = None

    def __init__(self, model_id: str = "none") -> None:
        self.model_id = model_id

    def status(self) -> VideoEngineStatus:
        return VideoEngineStatus("unavailable", "Video generation is turned off on this server.", self.model_id)

    def ensure_can_accept(self) -> None:
        raise VideoEngineError("engine_not_configured", "Video generation is turned off on this server.")

    def generate(self, params: VideoParams, deadline: float) -> tuple[bytes, dict[str, Any]]:
        self.ensure_can_accept()
        raise AssertionError("unreachable")


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


class DiffusersVideoEngine:
    name = "ltx"

    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.video_model_id
        self._cache_dir = settings.video_model_cache_dir
        self._requested_device = settings.video_device
        self._lock = threading.Lock()
        self._pipe: Any = None
        self._device: str | None = None
        self._optimizations: list[str] = []
        self._loading = False
        self._load_error: VideoEngineError | None = None
        self._settings = settings

    @staticmethod
    def libraries_installed() -> bool:
        return all(importlib.util.find_spec(m) is not None for m in REQUIRED_MODULES)

    def weights_present(self) -> bool:
        if importlib.util.find_spec("huggingface_hub") is None:
            return False
        from huggingface_hub import try_to_load_from_cache

        cache_dir = str(self._cache_dir) if self._cache_dir else None
        found = try_to_load_from_cache(self.model_id, "model_index.json", cache_dir=cache_dir)
        return isinstance(found, str)

    def status(self) -> VideoEngineStatus:
        base = {"model_id": self.model_id, "device": self._device, "optimizations": list(self._optimizations)}
        if self._pipe is not None:
            return VideoEngineStatus("loaded", f"Loaded on {self._device}.", **base)
        if self._loading:
            return VideoEngineStatus("loading", "The video model is loading into memory.", **base)
        if not self.libraries_installed():
            return VideoEngineStatus(
                "unavailable", "AI libraries (PyTorch, Diffusers) are not installed on the server.", **base
            )
        if not self.weights_present():
            return VideoEngineStatus("not_downloaded", "Video model weights have not been downloaded yet.", **base)
        if self._load_error is not None:
            return VideoEngineStatus("error", self._load_error.message, **base)
        return VideoEngineStatus("not_loaded", "Weights are available; the video model loads on first use.", **base)

    def ensure_can_accept(self) -> None:
        if not self.libraries_installed():
            raise VideoEngineError(
                "ai_libraries_missing",
                "The server is missing the AI libraries (PyTorch, Diffusers) for video generation.",
            )
        if not self.weights_present():
            raise VideoEngineError(
                "model_not_downloaded",
                f"The video model weights for {self.model_id} are not downloaded yet.",
            )

    def load(self) -> None:
        with self._lock:
            if self._pipe is not None:
                return
            self.ensure_can_accept()
            self._loading = True
            self._load_error = None
            try:
                self._pipe = self._build_pipeline()
            except VideoEngineError as err:
                self._load_error = err
                raise
            except Exception as e:
                logger.exception("Video model failed to load")
                self._load_error = VideoEngineError("model_load_failed", "The video model failed to load.", retryable=True)
                raise self._load_error from None
            finally:
                self._loading = False

    def _resolve_device(self, torch: Any) -> str:
        cuda = torch.cuda.is_available()
        if self._requested_device == "cuda" and not cuda:
            raise VideoEngineError("cuda_unavailable", "VIDEO_DEVICE is set to cuda, but PyTorch cannot see a CUDA GPU.")
        if self._requested_device == "cpu":
            return "cpu"
        return "cuda" if cuda else "cpu"

    def _build_pipeline(self) -> Any:
        import torch
        try:
            from diffusers import LTXConditionPipeline
            pipeline_cls = LTXConditionPipeline
        except Exception:
            try:
                from diffusers import LTXPipeline
                pipeline_cls = LTXPipeline
            except Exception as e:
                raise VideoEngineError("engine_not_configured", "LTX video pipeline not available in installed diffusers.") from e

        device = self._resolve_device(torch)
        dtype = torch.float16 if device == "cuda" else torch.float32
        cache_dir = str(self._cache_dir) if self._cache_dir else None
        common = {
            "torch_dtype": dtype,
            "cache_dir": cache_dir,
            "local_files_only": True,
            "use_safetensors": True,
        }
        try:
            pipe = pipeline_cls.from_pretrained(self.model_id, **common)
        except Exception:
            try:
                pipe = pipeline_cls.from_pretrained(self.model_id, local_files_only=True, cache_dir=cache_dir)
            except Exception as e:
                raise VideoEngineError("model_not_downloaded", "Video model weights are missing or incomplete.") from e

        optimizations: list[str] = []
        if device == "cuda":
            try:
                vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
                if self._settings.video_enable_attention_slicing:
                    pipe.enable_attention_slicing()
                    optimizations.append("attention_slicing")
                if self._settings.video_enable_vae_tiling:
                    if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_tiling"):
                        pipe.vae.enable_tiling()
                        optimizations.append("vae_tiling")
                if self._settings.video_enable_model_cpu_offload:
                    pipe.enable_model_cpu_offload()
                    optimizations.append("model_cpu_offload")
                elif self._settings.video_enable_cpu_offload and vram_gb < 12:
                    try:
                        pipe.enable_sequential_cpu_offload()
                        optimizations.append("sequential_cpu_offload")
                    except Exception:
                        pass
                if not optimizations:
                    pipe.to(device)
                optimizations.append(f"fp16 ({vram_gb:.1f} GB VRAM)")
            except Exception:
                pipe.to(device)
        else:
            pipe.to(device)

        pipe.set_progress_bar_config(disable=True)
        self._device = device
        self._optimizations = optimizations
        logger.info("Video model %s loaded on %s %s", self.model_id, device, optimizations)
        return pipe

    def generate(self, params: VideoParams, deadline: float) -> tuple[bytes, dict[str, Any]]:
        self.load()
        import torch

        device = self._device or "cpu"
        generator = torch.Generator(device="cpu").manual_seed(params.seed)
        timed_out = False

        def stop_after_deadline(pipe: Any, _step: int, _timestep: Any, kwargs: dict) -> dict:
            nonlocal timed_out
            if time.monotonic() > deadline:
                timed_out = True
                if hasattr(pipe, "_interrupt"):
                    pipe._interrupt = True
            return kwargs

        result = None
        try:
            with torch.inference_mode():
                call_kwargs = dict(
                    prompt=params.prompt,
                    num_frames=params.num_frames,
                    width=params.width,
                    height=params.height,
                    num_inference_steps=params.num_inference_steps,
                    generator=generator,
                )
                try:
                    call_kwargs["callback_on_step_end"] = stop_after_deadline
                except Exception:
                    pass
                result = self._pipe(**call_kwargs)
            if timed_out:
                raise VideoEngineError("generation_timeout", "Video generation took too long and was stopped.", retryable=True)
            frames = getattr(result, "frames", None)
            if frames is None:
                raise VideoEngineError("generation_failed", "Video generation produced no frames.")
            # frames might be [frames_tensor] or list of frames
            video_frames = frames[0] if isinstance(frames, (list, tuple)) and len(frames) > 0 else frames
            mp4_bytes = self._frames_to_mp4(video_frames, fps=24)
            meta = {
                "num_frames": len(video_frames) if hasattr(video_frames, "__len__") else params.num_frames,
                "width": params.width,
                "height": params.height,
            }
            return mp4_bytes, meta
        except VideoEngineError:
            raise
        except torch.cuda.OutOfMemoryError:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise VideoEngineError("gpu_out_of_memory", "The GPU ran out of memory. Try smaller resolution, fewer frames/steps, or close other GPU apps.", retryable=True)
        except Exception as e:
            logger.exception("Video generation failed")
            raise VideoEngineError("generation_failed", "Video generation failed unexpectedly.") from None
        finally:
            del result
            gc.collect()
            if device == "cuda":
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

    def _frames_to_mp4(self, frames, fps: int = 24) -> bytes:
        # Try using diffusers/imageio/torchvision if available
        try:
            import numpy as np
            from PIL import Image
            import imageio

            # Convert frames to numpy array of images
            frame_list = []
            if hasattr(frames, "cpu"):
                frames_np = frames.cpu().numpy()
                # frames_np shape depends on format; try to convert
                # Common: (T, C, H, W) or (T, H, W, C)
                if frames_np.ndim == 4:
                    if frames_np.shape[1] in (1, 3, 4):  # C first
                        for i in range(frames_np.shape[0]):
                            f = frames_np[i]
                            f = np.transpose(f, (1, 2, 0))
                            if f.max() <= 1.0:
                                f = (f * 255).astype(np.uint8)
                            else:
                                f = f.astype(np.uint8)
                            frame_list.append(f)
                    else:  # HWC
                        for i in range(frames_np.shape[0]):
                            f = frames_np[i]
                            if f.max() <= 1.0:
                                f = (f * 255).astype(np.uint8)
                            else:
                                f = f.astype(np.uint8)
                            frame_list.append(f)
                elif frames_np.ndim == 3:
                    f = frames_np
                    if f.max() <= 1.0:
                        f = (f * 255).astype(np.uint8)
                    else:
                        f = f.astype(np.uint8)
                    frame_list.append(f)
            else:
                # list of PIL images or tensors
                for f in frames:
                    if hasattr(f, "cpu"):
                        f_np = f.cpu().numpy()
                        if f_np.ndim == 3 and f_np.shape[0] in (1, 3, 4):
                            f_np = np.transpose(f_np, (1, 2, 0))
                        if f_np.max() <= 1.0:
                            f_np = (f_np * 255).astype(np.uint8)
                        else:
                            f_np = f_np.astype(np.uint8)
                        frame_list.append(f_np)
                    elif isinstance(f, Image.Image):
                        frame_list.append(np.array(f))
                    else:
                        frame_list.append(np.array(f))
            # Write to temp file
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            tmp.close()
            try:
                imageio.mimsave(tmp.name, frame_list, fps=fps)
                with open(tmp.name, "rb") as fh:
                    data = fh.read()
                return data
            finally:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to encode video with imageio: {e}")
            # Try ffmpeg if available
            if _has_ffmpeg():
                # fallback path - not implemented fully here
                pass
            raise VideoEngineError("video_encode_failed", "Failed to encode generated video to MP4.")


def build_video_engine(settings: Settings):
    if settings.video_engine == "none":
        return DisabledVideoEngine()
    return DiffusersVideoEngine(settings)
