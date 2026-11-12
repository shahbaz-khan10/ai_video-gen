"""Local text-to-video engine: Wan2.1 T2V 1.3B (Apache-2.0) through Hugging Face Diffusers.

Memory layout for an 8 GB GPU (e.g. RTX 3050):
  * The UMT5-XXL text encoder (~11 GB in bf16) runs on the CPU, once per job, like Wan's own `--t5_cpu`.
  * The 1.3B transformer (bf16, ~2.8 GB) and the VAE (fp32, as Wan recommends) run on the GPU.
Frames are encoded to H.264 MP4 with imageio-ffmpeg, then re-opened and decoded before a job counts as done.
torch/diffusers are imported lazily, so the API starts without them and without touching the GPU.
"""

from __future__ import annotations

import gc
import importlib.util
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)

REQUIRED_MODULES = (
    "torch",
    "diffusers",
    "transformers",
    "huggingface_hub",
    "accelerate",
    "safetensors",
    "sentencepiece",
    "ftfy",
    "imageio",
    "imageio_ffmpeg",
)

# Wan's recommended negative prompt (English version of the one in its reference code).
WAN_NEGATIVE_PROMPT = (
    "bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, images, static, "
    "overall gray, worst quality, low quality, JPEG compression residue, ugly, incomplete, extra fingers, "
    "poorly drawn hands, poorly drawn faces, deformed, disfigured, misshapen limbs, fused fingers, still picture, "
    "messy background, three legs, many people in the background, walking backwards"
)


class VideoEngineError(Exception):
    """A failure that is safe to show to users. Never carries paths or stack traces."""

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
    fps: int = 16


class VideoEngine(Protocol):
    name: str
    model_id: str

    def status(self) -> VideoEngineStatus: ...

    def ensure_can_accept(self) -> None: ...

    def generate(self, params: VideoParams, deadline: float, output_path: Path) -> str:
        """Writes an MP4 to ``output_path`` and returns the device used. Blocking; runs in a worker thread."""
        ...

    def unload(self) -> None:
        """Frees the model's memory so another model can run."""
        ...


class DisabledVideoEngine:
    """Used when VIDEO_ENGINE=none: reports itself unavailable and refuses every job."""

    name = "none"

    def __init__(self, model_id: str = "none") -> None:
        self.model_id = model_id

    def status(self) -> VideoEngineStatus:
        return VideoEngineStatus("disabled", "Video generation is turned off on this server (VIDEO_ENGINE=none).", self.model_id)

    def ensure_can_accept(self) -> None:
        raise VideoEngineError("engine_not_configured", "Video generation is turned off on this server.")

    def generate(self, params: VideoParams, deadline: float, output_path: Path) -> str:
        self.ensure_can_accept()
        raise AssertionError("unreachable")

    def unload(self) -> None:
        return None


class WanVideoEngine:
    name = "wan"

    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.video_model_id
        self._settings = settings
        self._cache_dir = settings.video_model_cache_dir or settings.image_model_cache_dir
        self._lock = threading.Lock()
        self._pipe: Any = None
        self._device: str | None = None
        self._optimizations: list[str] = []
        self._loading = False
        self._load_error: VideoEngineError | None = None

    # --- cheap checks -------------------------------------------------------------

    @staticmethod
    def missing_modules() -> list[str]:
        return [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]

    def weights_present(self) -> bool:
        if importlib.util.find_spec("huggingface_hub") is None:
            return False
        from huggingface_hub import try_to_load_from_cache

        cache_dir = str(self._cache_dir)
        index = try_to_load_from_cache(self.model_id, "model_index.json", cache_dir=cache_dir)
        if not isinstance(index, str):
            return False
        # The sharded components must be complete, not just started.
        for component, index_name in (
            ("transformer", "diffusion_pytorch_model.safetensors.index.json"),
            ("text_encoder", "model.safetensors.index.json"),
        ):
            shard_index = try_to_load_from_cache(self.model_id, f"{component}/{index_name}", cache_dir=cache_dir)
            if not isinstance(shard_index, str):
                return False
            import json

            with open(shard_index, encoding="utf-8") as fh:
                shards = set(json.load(fh)["weight_map"].values())
            for shard in shards:
                if not isinstance(try_to_load_from_cache(self.model_id, f"{component}/{shard}", cache_dir=cache_dir), str):
                    return False
        vae = try_to_load_from_cache(self.model_id, "vae/diffusion_pytorch_model.safetensors", cache_dir=cache_dir)
        return isinstance(vae, str)

    def status(self) -> VideoEngineStatus:
        base = {"model_id": self.model_id, "device": self._device, "optimizations": list(self._optimizations)}
        if self._pipe is not None:
            return VideoEngineStatus("loaded", f"Loaded ({', '.join(self._optimizations)}).", **base)
        if self._loading:
            return VideoEngineStatus("loading", "The video model is loading into memory.", **base)
        missing = self.missing_modules()
        if missing:
            return VideoEngineStatus(
                "unavailable", f"Video libraries are not installed on the server: {', '.join(missing)}.", **base
            )
        if not self.weights_present():
            return VideoEngineStatus("not_downloaded", "Video model weights have not been downloaded yet.", **base)
        if self._load_error is not None:
            return VideoEngineStatus("error", self._load_error.message, **base)
        return VideoEngineStatus("not_loaded", "Weights are downloaded; the video model loads on first use.", **base)

    def ensure_can_accept(self) -> None:
        missing = self.missing_modules()
        if missing:
            raise VideoEngineError(
                "ai_libraries_missing",
                f"The server is missing libraries for video generation: {', '.join(missing)}.",
            )
        if not self.weights_present():
            raise VideoEngineError(
                "model_not_downloaded",
                f"The video model weights for {self.model_id} are not downloaded yet (about 29 GB, see README).",
            )

    # --- loading ------------------------------------------------------------------

    def load(self) -> None:
        with self._lock:
            if self._pipe is not None:
                return
            self.ensure_can_accept()
            self._loading = True
            self._load_error = None
            started = time.monotonic()
            try:
                self._pipe = self._build_pipeline()
            except VideoEngineError as err:
                self._load_error = err
                raise
            except MemoryError:
                self._load_error = VideoEngineError(
                    "out_of_memory",
                    "The server ran out of RAM loading the video model (it needs ~15 GB free).",
                    retryable=True,
                )
                raise self._load_error from None
            except Exception:
                logger.exception("Video model failed to load")
                self._load_error = VideoEngineError("model_load_failed", "The video model failed to load.", retryable=True)
                raise self._load_error from None
            finally:
                self._loading = False
            logger.info("Video model %s loaded in %.0fs %s", self.model_id, time.monotonic() - started, self._optimizations)

    def _build_pipeline(self) -> Any:
        import torch
        from diffusers import AutoencoderKLWan, UniPCMultistepScheduler, WanPipeline

        cuda = torch.cuda.is_available()
        if self._settings.video_device == "cuda" and not cuda:
            raise VideoEngineError("cuda_unavailable", "VIDEO_DEVICE is cuda, but PyTorch cannot see a CUDA GPU.")
        device = "cuda" if cuda and self._settings.video_device != "cpu" else "cpu"
        compute_dtype = torch.bfloat16 if device == "cuda" else torch.float32
        hub = {"cache_dir": str(self._cache_dir), "local_files_only": True}

        try:
            # Wan's reference code keeps the VAE in float32; bf16 VAEs produce colour artefacts.
            vae = AutoencoderKLWan.from_pretrained(self.model_id, subfolder="vae", dtype=torch.float32, **hub)
            pipe = WanPipeline.from_pretrained(self.model_id, vae=vae, dtype=compute_dtype, **hub)
        except OSError:
            raise VideoEngineError(
                "model_not_downloaded", "The video model weights are missing or incomplete. Re-run the download."
            ) from None
        pipe.scheduler = UniPCMultistepScheduler.from_config(
            pipe.scheduler.config, flow_shift=self._settings.video_flow_shift
        )

        optimizations = [f"{str(compute_dtype).removeprefix('torch.')} transformer", "fp32 VAE"]
        if device == "cuda":
            try:
                pipe.transformer.to("cuda")
                pipe.vae.to("cuda")
                if self._settings.video_text_encoder_on_cpu:
                    optimizations.append("text encoder on CPU")
                else:
                    pipe.text_encoder.to("cuda")
            except torch.cuda.OutOfMemoryError:
                del pipe
                self._release()
                raise VideoEngineError(
                    "gpu_out_of_memory",
                    "The GPU ran out of memory loading the video model. Close other GPU apps and retry.",
                    retryable=True,
                ) from None
            if self._settings.video_enable_vae_tiling and hasattr(pipe.vae, "enable_tiling"):
                pipe.vae.enable_tiling()
                optimizations.append("VAE tiling")
        pipe.set_progress_bar_config(disable=True)
        self._device = device
        self._optimizations = optimizations
        return pipe

    def unload(self) -> None:
        with self._lock:
            if self._pipe is None:
                return
            self._pipe = None
            self._optimizations = []
            self._release()
            logger.info("Video model unloaded to free memory")

    @staticmethod
    def _release() -> None:
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    # --- inference ----------------------------------------------------------------

    def generate(self, params: VideoParams, deadline: float, output_path: Path) -> str:
        self.load()
        import torch

        pipe = self._pipe
        device = self._device or "cpu"
        timed_out = False

        def stop_after_deadline(p: Any, _step: int, _timestep: Any, kwargs: dict) -> dict:
            nonlocal timed_out
            if time.monotonic() > deadline:
                timed_out = True
                p._interrupt = True
            return kwargs

        frames = None
        try:
            with torch.inference_mode():
                # Encode on the text encoder's own device (CPU by default), then move the embeddings to the GPU.
                text_device = pipe.text_encoder.device
                prompt_embeds, negative_embeds = pipe.encode_prompt(
                    prompt=params.prompt,
                    negative_prompt=WAN_NEGATIVE_PROMPT,
                    do_classifier_free_guidance=True,
                    num_videos_per_prompt=1,
                    device=text_device,
                    dtype=pipe.transformer.dtype,
                )
                generator = torch.Generator(device="cpu").manual_seed(params.seed)
                output = pipe(
                    prompt_embeds=prompt_embeds.to(device),
                    negative_prompt_embeds=negative_embeds.to(device),
                    width=params.width,
                    height=params.height,
                    num_frames=params.num_frames,
                    num_inference_steps=params.num_inference_steps,
                    guidance_scale=self._settings.video_guidance_scale,
                    generator=generator,
                    output_type="np",
                    callback_on_step_end=stop_after_deadline,
                )
            if timed_out:
                raise VideoEngineError("generation_timeout", "Video generation took too long and was stopped.", retryable=True)
            frames = output.frames[0]
            if frames is None or len(frames) == 0:
                raise VideoEngineError("generation_failed", "The video model returned no frames.", retryable=True)
            write_mp4(frames, output_path, fps=params.fps)
            return device
        except VideoEngineError:
            raise
        except torch.cuda.OutOfMemoryError:
            raise VideoEngineError(
                "gpu_out_of_memory",
                "The GPU ran out of memory. Try the Draft size, a shorter clip or fewer steps, and close other GPU apps.",
                retryable=True,
            ) from None
        except MemoryError:
            raise VideoEngineError(
                "out_of_memory", "The server ran out of RAM. Try a shorter clip or the Draft size.", retryable=True
            ) from None
        finally:
            del frames
            self._release()


def write_mp4(frames: Any, path: Path, fps: int) -> None:
    """Encodes float [0, 1] or uint8 HxWx3 frames to a browser-playable H.264 MP4 (yuv420p, faststart)."""
    import imageio.v2 as imageio
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(
        str(path),
        fps=fps,
        codec="libx264",
        quality=8,
        pixelformat="yuv420p",
        macro_block_size=16,
        ffmpeg_params=["-movflags", "+faststart"],
    )
    try:
        for frame in frames:
            arr = np.asarray(frame)
            if arr.dtype != np.uint8:
                arr = (np.clip(arr, 0.0, 1.0) * 255).round().astype(np.uint8)
            writer.append_data(arr)
    finally:
        writer.close()


def build_video_engine(settings: Settings) -> VideoEngine:
    if settings.video_engine == "none":
        return DisabledVideoEngine(settings.video_model_id)
    return WanVideoEngine(settings)
