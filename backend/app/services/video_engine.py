"""Local video engine: Wan2.1 T2V 1.3B / FastWan (text-to-video) and Wan2.1 VACE 1.3B (image-to-video), all
Apache-2.0, through Hugging Face Diffusers.

One text encoder and one VAE serve both modes; only the transformer is swapped (dropped and loaded again) when the
mode changes, so the ~11 GB text encoder is never in memory twice.

Memory layout for an 8 GB GPU (e.g. RTX 3050):
  * The UMT5-XXL text encoder (~11 GB in bf16) runs on the CPU, once per job, like Wan's own `--t5_cpu`.
  * The 1.3B transformer (bf16, ~2.8 GB) and the VAE (fp32, as Wan recommends) run on the GPU.
Frames are encoded to H.264 MP4 with imageio-ffmpeg, then re-opened and decoded before a job counts as done.
torch/diffusers are imported lazily, so the API starts without them and without touching the GPU.
"""

from __future__ import annotations

import contextlib
import gc
import importlib.util
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol

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


@dataclass(frozen=True)
class ImageVideoParams:
    """Image-to-video: ``image_path`` becomes the first frame (cover-cropped to width x height)."""

    prompt: str
    image_path: Path
    width: int
    height: int
    num_frames: int
    seed: int
    quality: str = "draft"  # "draft": 3 distilled steps, no guidance. "quality": I2V_QUALITY_STEPS with guidance.
    fps: int = 16
    negative_prompt: str | None = None


# Image-to-video sampling (measured on an RTX 3050, docs/phase_k): Draft = VACE context blocks on FastWan's
# distilled base, 3 steps, no guidance (~60 s for 3 s at 576x320); Quality = VACE as released, 20 steps + CFG 5
# (~240 s): more motion, but faces and details drift more than in Draft.
I2V_QUALITY_STEPS = 20  # 8 steps flickered on every frame (river test, docs/phase_k); 20 is smooth
I2V_GUIDANCE = 5.0
I2V_NEGATIVE_EXTRA = "different person, changing face, morphing, face distortion, flicker, extra people, new objects"


def fit_image(img: Any, width: int, height: int) -> Any:
    """Cover-crop to the target aspect around the centre, then resize. Never stretches the picture."""
    from PIL import Image

    src_ratio, dst_ratio = img.width / img.height, width / height
    if src_ratio > dst_ratio:
        w = round(img.height * dst_ratio)
        img = img.crop(((img.width - w) // 2, 0, (img.width - w) // 2 + w, img.height))
    else:
        h = round(img.width / dst_ratio)
        img = img.crop((0, (img.height - h) // 2, img.width, (img.height - h) // 2 + h))
    return img.convert("RGB").resize((width, height), Image.LANCZOS)


class Cancelled(Exception):
    pass


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

    def generate(self, params: VideoParams, deadline: float, output_path: Path, cancel: Any = None) -> str:
        self.ensure_can_accept()
        raise AssertionError("unreachable")

    def i2v_status(self) -> tuple[bool, str]:
        return False, "Video generation is turned off on this server."

    def generate_from_image(self, params: ImageVideoParams, deadline: float, output_path: Path, cancel: Any = None) -> str:
        self.ensure_can_accept()
        raise AssertionError("unreachable")

    def unload(self) -> None:
        return None


class WanVideoEngine:
    name = "wan"

    def __init__(self, settings: Settings) -> None:
        # Text encoder, tokenizer and VAE always come from the base Wan2.1 repo; the transformer from FastWan
        # when that sampler is selected. ``model_id`` names the transformer that actually generates.
        self._base_id = settings.video_model_id
        self._fast = settings.video_sampler == "fastwan"
        self.model_id = settings.video_fast_model_id if self._fast else settings.video_model_id
        self.sampler = settings.video_sampler
        self._settings = settings
        self._cache_dir = settings.video_model_cache_dir or settings.image_model_cache_dir
        self._lock = threading.Lock()
        self._pipe: Any = None
        self._device: str | None = None
        self._optimizations: list[str] = []
        self._prompt_cache: dict[tuple[str, bool, str | None], tuple[Any, Any]] = {}
        self._vace_id = settings.video_continuity_model_id
        self._kind = "t2v"  # which transformer is loaded: t2v | i2v_draft | i2v_quality
        self._scheduler_config: dict[str, Any] = {}
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

        def cached(repo: str, path: str) -> bool:
            return isinstance(try_to_load_from_cache(repo, path, cache_dir=cache_dir), str)

        def complete(repo: str, component: str, index_name: str) -> bool:
            """A sharded component counts only when every shard is there, not just started."""
            import json

            shard_index = try_to_load_from_cache(repo, f"{component}/{index_name}", cache_dir=cache_dir)
            if not isinstance(shard_index, str):
                return False
            with open(shard_index, encoding="utf-8") as fh:
                shards = set(json.load(fh)["weight_map"].values())
            return all(cached(repo, f"{component}/{shard}") for shard in shards)

        base = self._base_id
        if not cached(base, "model_index.json") or not complete(base, "text_encoder", "model.safetensors.index.json"):
            return False
        if not cached(base, "vae/diffusion_pytorch_model.safetensors"):
            return False
        if self._fast:
            # FastWan ships its transformer as one file.
            return cached(self.model_id, "transformer/diffusion_pytorch_model.safetensors")
        return complete(base, "transformer", "diffusion_pytorch_model.safetensors.index.json")

    def i2v_status(self) -> tuple[bool, str]:
        """Whether image-to-video can run: VACE 1.3B (and the base/FastWan weights) must be on disk."""
        if self.missing_modules():
            return False, "Video libraries are not installed on the server."
        if not self.weights_present():
            return False, "Video model weights have not been downloaded yet."
        from huggingface_hub import try_to_load_from_cache

        index = try_to_load_from_cache(
            self._vace_id, "transformer/diffusion_pytorch_model.safetensors.index.json", cache_dir=str(self._cache_dir)
        )
        if not isinstance(index, str):
            return False, f"The image-to-video model ({self._vace_id}) is not downloaded."
        return True, "Wan2.1 VACE 1.3B: the uploaded image is the first frame."

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

    def load(self, kind: str = "t2v") -> None:
        """Loads text encoder, VAE and the transformer for ``kind`` (t2v, i2v_draft, i2v_quality)."""
        with self._lock:
            if self._pipe is not None:
                return
            self.ensure_can_accept()
            self._preflight_load()
            self._loading = True
            self._load_error = None
            started = time.monotonic()
            try:
                self._pipe = self._build_pipeline(kind)
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

    def _build_pipeline(self, kind: str = "t2v") -> Any:
        import torch
        from diffusers import AutoencoderKLWan, UniPCMultistepScheduler, WanPipeline

        cuda = torch.cuda.is_available()
        if self._settings.video_device == "cuda" and not cuda:
            raise VideoEngineError("cuda_unavailable", "VIDEO_DEVICE is cuda, but PyTorch cannot see a CUDA GPU.")
        device = "cuda" if cuda and self._settings.video_device != "cpu" else "cpu"
        compute_dtype = torch.bfloat16 if device == "cuda" else torch.float32
        hub = {"cache_dir": str(self._cache_dir), "local_files_only": True}

        try:
            # Wan's reference code keeps the VAE in float32 and warns about bf16 colour artefacts; on this GPU
            # bf16 measured PSNR 57 dB vs fp32 with no visible difference, at 2.5x (Draft) / 1.7x (480p) speed.
            vae_dtype = torch.bfloat16 if self._settings.video_vae_dtype == "bfloat16" and device == "cuda" else torch.float32
            vae = AutoencoderKLWan.from_pretrained(self._base_id, subfolder="vae", dtype=vae_dtype, **hub)
            extra: dict[str, Any] = {}
            if kind != "t2v":
                # Image-to-video first: skip the text-to-video transformer; _switch loads the VACE one.
                extra["transformer"] = None
            elif self._fast:
                from diffusers import WanTransformer3DModel

                # Same architecture as Wan2.1 T2V 1.3B; only the (distilled) weights differ.
                extra["transformer"] = WanTransformer3DModel.from_pretrained(
                    self.model_id, subfolder="transformer", dtype=compute_dtype, **hub
                )
            pipe = WanPipeline.from_pretrained(self._base_id, vae=vae, dtype=compute_dtype, **extra, **hub)
        except OSError:
            raise VideoEngineError(
                "model_not_downloaded", "The video model weights are missing or incomplete. Re-run the download."
            ) from None
        # Wan's own scheduler config (flow prediction, flow sigmas). Kept so a later transformer switch builds its
        # UniPC scheduler from it, not from whatever scheduler the previous mode used (the 3-step DMD one).
        self._scheduler_config = dict(pipe.scheduler.config)
        pipe.scheduler = UniPCMultistepScheduler.from_config(
            pipe.scheduler.config, flow_shift=self._settings.video_flow_shift
        )

        optimizations = [f"{str(compute_dtype).removeprefix('torch.')} transformer", f"{str(vae.dtype).removeprefix('torch.')} VAE"]
        if self._fast:
            optimizations.insert(0, "3-step DMD sampling, no CFG")
        if device == "cuda":
            try:
                if pipe.transformer is not None:
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
                optimizations.append("VAE tiling above Draft size")
        pipe.set_progress_bar_config(disable=True)
        self._device = device
        self._optimizations = optimizations
        self._kind = "t2v" if kind == "t2v" else "none"
        return pipe

    def unload(self) -> None:
        with self._lock:
            if self._pipe is None:
                return
            self._pipe = None
            self._kind = "t2v"
            self._optimizations = []
            self._prompt_cache.clear()
            self._release()
            logger.info("Video model unloaded to free memory")

    @staticmethod
    def _release() -> None:
        from app.services import memory

        memory.release()

    def _preflight_load(self) -> None:
        """Fail fast with a clear message instead of letting the VM swap and the GPU stall (measured)."""
        if self._settings.video_device == "cpu":
            return
        from app.services import memory

        memory.release()  # hand freed arenas back to the OS before measuring what is available
        problem = memory.check_room(
            ram_gib=self._settings.video_min_free_ram_gib,
            vram_gib=self._settings.video_min_free_vram_gib,
            what="the video model",
        )
        if problem:
            raise VideoEngineError("out_of_memory", problem, retryable=True)

    def _preflight_clip(self) -> None:
        from app.services import memory

        problem = memory.check_room(ram_gib=0, vram_gib=self._settings.video_min_free_vram_per_clip_gib, what="a clip")
        if problem:
            raise VideoEngineError("gpu_out_of_memory", problem, retryable=True)

    def _configure_vae(self, pipe: Any, width: int, height: int) -> None:
        """Untiled decode is fastest when it fits (Draft); larger sizes decode in tiles (measured: untiled bf16
        at 480p needs 7.3 GB and is 4.7x slower than tiled)."""
        vae = pipe.vae
        if not hasattr(vae, "enable_tiling"):
            return
        if self._settings.video_enable_vae_tiling and width * height > DRAFT_MAX_PIXELS:
            vae.enable_tiling()
        else:
            vae.disable_tiling()

    def _encode(self, pipe: Any, prompt: str, cfg: bool | None = None, negative: str | None = None) -> tuple[Any, Any]:
        """Text embeddings, cached per prompt: every clip of a scene shares one prompt (6 s of CPU each)."""
        cfg = (not self._fast) if cfg is None else cfg
        key = (prompt, cfg, negative)
        if key in self._prompt_cache:
            return self._prompt_cache[key]
        prompt_embeds, negative_embeds = pipe.encode_prompt(
            prompt=prompt,
            negative_prompt=(negative or WAN_NEGATIVE_PROMPT) if cfg else None,
            do_classifier_free_guidance=cfg,
            num_videos_per_prompt=1,
            max_sequence_length=MAX_TEXT_TOKENS,
            device=pipe.text_encoder.device,
            dtype=pipe.transformer.dtype,
        )
        if len(self._prompt_cache) >= 8:
            self._prompt_cache.pop(next(iter(self._prompt_cache)))
        self._prompt_cache[key] = (prompt_embeds, negative_embeds)
        return prompt_embeds, negative_embeds

    # --- inference ----------------------------------------------------------------

    def generate(self, params: VideoParams, deadline: float, output_path: Path, cancel: Any = None) -> str:
        self.load()
        import torch

        with self._guard():
            self._switch("t2v")
        pipe = self._pipe
        device = self._device or "cpu"
        timed_out = False

        def stop_after_deadline(p: Any, _step: int, _timestep: Any, kwargs: dict) -> dict:
            nonlocal timed_out
            if cancel is not None and cancel.is_set():
                raise Cancelled
            if time.monotonic() > deadline:
                timed_out = True
                p._interrupt = True
            return kwargs

        frames = None
        try:
            with torch.inference_mode():
                # Encode on the text encoder's own device (CPU by default), then move the embeddings to the GPU.
                # 512 tokens is Wan's training length; the Diffusers default (226) would cut long scene prompts.
                self._preflight_clip()
                if time.monotonic() > deadline:
                    raise VideoEngineError("generation_timeout", "Video generation took too long and was stopped.", retryable=True)
                prompt_embeds, negative_embeds = self._encode(pipe, params.prompt)
                self._configure_vae(pipe, params.width, params.height)
                generator = torch.Generator(device="cpu").manual_seed(params.seed)
                if self._fast:
                    frames = _dmd_sample(pipe, prompt_embeds.to(device), params, generator, deadline, device, cancel)
                else:
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
                        max_sequence_length=MAX_TEXT_TOKENS,
                    )
                    if timed_out:
                        raise VideoEngineError(
                            "generation_timeout", "Video generation took too long and was stopped.", retryable=True
                        )
                    frames = output.frames[0]
            if frames is None or len(frames) == 0:
                raise VideoEngineError("generation_failed", "The video model returned no frames.", retryable=True)
            write_mp4(frames, output_path, fps=params.fps)
            return device
        except Cancelled:
            raise VideoEngineError("cancelled", "The generation was cancelled.", retryable=True) from None
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
        except RuntimeError as exc:
            if "CUDA error" not in str(exc):
                raise
            # Seen on Windows/WSL with VRAM nearly full ("CUDA error: unknown error"). The loaded weights may be
            # unusable afterwards, so the pipeline is dropped and reloaded by the next job.
            logger.error("CUDA error during video generation: %s", exc)
            self._pipe = None
            self._optimizations = []
            self._prompt_cache.clear()
            raise VideoEngineError(
                "gpu_error",
                "The GPU driver reported an error (on Windows this is often a GPU reset when video memory is nearly "
                "full). Close other GPU apps and retry; finished clips are kept.",
                retryable=True,
            ) from None
        finally:
            del frames
            self._release()


    # --- image-to-video -------------------------------------------------------------

    @contextlib.contextmanager
    def _guard(self) -> Iterator[None]:
        """Maps cancellation, out-of-memory and driver errors to user-safe errors (same rules as ``generate``)."""
        import torch

        try:
            yield
        except Cancelled:
            raise VideoEngineError("cancelled", "The generation was cancelled.", retryable=True) from None
        except VideoEngineError:
            raise
        except torch.cuda.OutOfMemoryError:
            raise VideoEngineError(
                "gpu_out_of_memory",
                "The GPU ran out of memory. Try the Draft size or a shorter clip, and close other GPU apps.",
                retryable=True,
            ) from None
        except MemoryError:
            raise VideoEngineError("out_of_memory", "The server ran out of RAM. Try a shorter clip.", retryable=True) from None
        except RuntimeError as exc:
            if "CUDA error" not in str(exc):
                raise
            logger.error("CUDA error during video generation: %s", exc)
            self._pipe = None
            self._kind = "t2v"
            self._optimizations = []
            self._prompt_cache.clear()
            raise VideoEngineError(
                "gpu_error",
                "The GPU driver reported an error (on Windows this is often a GPU reset when video memory is nearly "
                "full). Close other GPU apps and retry.",
                retryable=True,
            ) from None

    def _switch(self, kind: str) -> None:
        """Loads the transformer for ``kind`` in place of the current one. Text encoder and VAE are kept."""
        if self._kind == kind or self._pipe is None:
            return
        import torch
        from diffusers import UniPCMultistepScheduler, WanPipeline, WanVACEPipeline

        started = time.monotonic()
        old = self._pipe
        parts = {"tokenizer": old.tokenizer, "text_encoder": old.text_encoder, "vae": old.vae}
        # Drop the old transformer before loading the next one: both together do not fit in VRAM.
        self._pipe = None
        old.transformer = None
        del old
        self._release()
        dtype = torch.bfloat16 if self._device == "cuda" else torch.float32
        try:
            transformer = self._load_transformer(kind, dtype)
        except OSError:
            raise VideoEngineError(
                "model_not_downloaded", "The video model weights are missing or incomplete. Re-run the download."
            ) from None
        if kind == "i2v_draft":
            scheduler: Any = _dmd_scheduler()
        else:
            scheduler = UniPCMultistepScheduler.from_config(self._scheduler_config, flow_shift=self._settings.video_flow_shift)
        if self._device == "cuda":
            transformer.to("cuda")
        if kind == "i2v_draft":
            self._graft_fast_base(transformer)
        cls = WanPipeline if kind == "t2v" else WanVACEPipeline
        pipe = cls(transformer=transformer, scheduler=scheduler, **parts)
        pipe.set_progress_bar_config(disable=True)
        self._pipe = pipe
        self._kind = kind
        logger.info("Video transformer switched to %s in %.0fs", kind, time.monotonic() - started)

    def _load_transformer(self, kind: str, dtype: Any) -> Any:
        hub = {"cache_dir": str(self._cache_dir), "local_files_only": True}
        if kind == "t2v":
            from diffusers import WanTransformer3DModel

            return WanTransformer3DModel.from_pretrained(
                self.model_id if self._fast else self._base_id, subfolder="transformer", dtype=dtype,
                device_map={"": "cuda"} if self._device == "cuda" else None, **hub,
            )
        from diffusers import WanVACETransformer3DModel

        # Straight onto the GPU shard by shard: going through CPU RAM held the fp32 shards (6.7 GB) next to the
        # 11 GB text encoder (measured peak 20.6 GB process RAM).
        device_map = {"": "cuda"} if self._device == "cuda" else None
        transformer = WanVACETransformer3DModel.from_pretrained(
            self._vace_id, subfolder="transformer", dtype=dtype, device_map=device_map, **hub
        )
        return transformer

    def _graft_fast_base(self, transformer: Any) -> None:
        """VACE was trained with the Wan2.1 T2V 1.3B base frozen; FastWan is that base distilled to 3 steps. Copying
        FastWan's base blocks over VACE's keeps VACE's image conditioning and samples in 3 steps (measured ~4x faster
        than 20 steps, with the face closer to the photo; docs/phase_k).

        Tensors are streamed one at a time from the safetensors file straight into the (GPU) parameters: loading the
        whole 5.6 GB fp32 file at once pushed the process to 22.7 GB RAM, next to the 11 GB text encoder."""
        from huggingface_hub import hf_hub_download
        from safetensors import safe_open

        path = hf_hub_download(
            self._settings.video_fast_model_id, "transformer/diffusion_pytorch_model.safetensors",
            cache_dir=str(self._cache_dir), local_files_only=True,
        )
        params = {k: v for k, v in transformer.named_parameters() if not k.startswith("vace_")}
        copied = 0
        with safe_open(path, framework="pt", device="cpu") as f:
            for key in f.keys():
                target = params.get(key)
                if target is None or tuple(f.get_slice(key).get_shape()) != tuple(target.shape):
                    continue
                target.data.copy_(f.get_tensor(key).to(device=target.device, dtype=target.dtype))
                copied += 1
        if copied != len(params):
            raise VideoEngineError("model_load_failed", "The distilled weights do not match the VACE model.")

    def generate_from_image(self, params: ImageVideoParams, deadline: float, output_path: Path, cancel: Any = None) -> str:
        """Animates an uploaded image: VACE keeps frame 0 (the image) and generates the frames after it; the image
        is also VACE's reference image, which kept the face closest to the upload (docs/phase_k)."""
        ok, detail = self.i2v_status()
        if not ok:
            raise VideoEngineError("model_not_downloaded", detail)
        draft = params.quality == "draft"
        self.load("i2v_draft" if draft else "i2v_quality")
        import torch
        from PIL import Image

        frames = None
        try:
            with self._guard():
                self._switch("i2v_draft" if draft else "i2v_quality")
                pipe = self._pipe
                device = self._device or "cpu"
                self._preflight_clip()
                with Image.open(params.image_path) as src:
                    first = fit_image(src, params.width, params.height)
                w, h, n = params.width, params.height, params.num_frames
                video = [first] + [Image.new("RGB", (w, h), (128, 128, 128))] * (n - 1)
                mask = [Image.new("L", (w, h), 0)] + [Image.new("L", (w, h), 255)] * (n - 1)
                negative = f"{params.negative_prompt or WAN_NEGATIVE_PROMPT}, {I2V_NEGATIVE_EXTRA}"

                def stop(_p: Any, _step: int, _t: Any, kwargs: dict) -> dict:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled
                    if time.monotonic() > deadline:
                        raise VideoEngineError(
                            "generation_timeout", "Video generation took too long and was stopped.", retryable=True
                        )
                    return kwargs

                with torch.inference_mode():
                    pos, neg = self._encode(pipe, params.prompt, cfg=not draft, negative=None if draft else negative)
                    stop(pipe, 0, None, {})
                    self._configure_vae(pipe, w, h)
                    # Draft re-noises with the global generator between steps: seed it for repeatable results.
                    torch.manual_seed(params.seed)
                    output = pipe(
                        video=video,
                        mask=mask,
                        reference_images=[first],
                        prompt_embeds=pos.to(device),
                        negative_prompt_embeds=None if draft else neg.to(device),
                        height=h,
                        width=w,
                        num_frames=n,
                        num_inference_steps=3 if draft else I2V_QUALITY_STEPS,
                        guidance_scale=1.0 if draft else I2V_GUIDANCE,
                        generator=torch.Generator(device="cpu").manual_seed(params.seed),
                        output_type="np",
                        callback_on_step_end=stop,
                    )
                    frames = output.frames[0]
                if frames is None or len(frames) == 0:
                    raise VideoEngineError("generation_failed", "The video model returned no frames.", retryable=True)
                write_mp4(frames, output_path, fps=params.fps)
                return device
        finally:
            del frames
            self._release()


def _dmd_scheduler() -> Any:
    """FastWan's 3 DMD steps as a Diffusers scheduler, so the stock VACE pipeline can run distilled sampling:
    predict the clean video, re-noise it to the next sigma (``stochastic_sampling``), repeat."""
    from diffusers import FlowMatchEulerDiscreteScheduler

    class DMDScheduler(FlowMatchEulerDiscreteScheduler):
        def set_timesteps(self, num_inference_steps: int | None = None, device: Any = None, **_: Any) -> None:
            super().set_timesteps(sigmas=[t / 1000 for t in DMD_TIMESTEPS], device=device)

    return DMDScheduler(shift=1.0, stochastic_sampling=True)


MAX_TEXT_TOKENS = 512
DRAFT_MAX_PIXELS = 576 * 320  # Draft sizes (576x320, 320x576, 416x416) decode untiled
# FastWan's distillation timesteps (FastVideo's ``--dmd-denoising-steps``).
DMD_TIMESTEPS = (1000, 757, 522)


def _dmd_sample(
    pipe: Any, prompt_embeds: Any, params: VideoParams, generator: Any, deadline: float, device: str, cancel: Any = None
) -> Any:
    """Three-step DMD sampling: predict the clean video, re-noise to the next timestep, repeat; then decode.

    Flow matching: x_t = (1 - s)·x0 + s·noise and the model predicts v = noise - x0, so x0 = x_t - s·v.
    """
    import torch

    latents = pipe.prepare_latents(
        1, pipe.transformer.config.in_channels, params.height, params.width, params.num_frames,
        torch.float32, torch.device(device), generator,
    )
    for i, t in enumerate(DMD_TIMESTEPS):
        if cancel is not None and cancel.is_set():
            raise Cancelled
        if time.monotonic() > deadline:
            raise VideoEngineError("generation_timeout", "Video generation took too long and was stopped.", retryable=True)
        sigma = t / 1000
        velocity = pipe.transformer(
            hidden_states=latents.to(pipe.transformer.dtype),
            timestep=torch.tensor([t], device=device),
            encoder_hidden_states=prompt_embeds,
            return_dict=False,
        )[0].float()
        clean = latents - sigma * velocity
        if i + 1 < len(DMD_TIMESTEPS):
            next_sigma = DMD_TIMESTEPS[i + 1] / 1000
            noise = torch.randn(latents.shape, generator=generator, dtype=torch.float32).to(device)
            latents = (1 - next_sigma) * clean + next_sigma * noise
        else:
            latents = clean
    if time.monotonic() > deadline:
        raise VideoEngineError("generation_timeout", "Video generation took too long and was stopped.", retryable=True)
    vae = pipe.vae
    z_dim = vae.config.z_dim
    mean = torch.tensor(vae.config.latents_mean).view(1, z_dim, 1, 1, 1).to(device, torch.float32)
    std = torch.tensor(vae.config.latents_std).view(1, z_dim, 1, 1, 1).to(device, torch.float32)
    video = vae.decode((latents * std + mean).to(vae.dtype), return_dict=False)[0]
    return pipe.video_processor.postprocess_video(video.float(), output_type="np")[0]


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
