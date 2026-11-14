"""Memory housekeeping for the GPU worker.

Two problems measured on the RTX 3050 / 23.5 GiB WSL VM (docs/AI_VIDEO_STUDIO_QUALITY_ROADMAP.md, 3.7):
  * Python frees a model's tensors but glibc keeps the pages in its arenas, so the container's RAM does not
    go down after an unload; ``malloc_trim`` hands them back to the OS.
  * When the VM runs out of memory, the job does not fail: the VM swaps and the GPU job (and the Docker
    engine) stall. Checking free memory *before* loading a model turns that into a clear, retryable error.
"""

from __future__ import annotations

import ctypes
import gc
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)
GiB = 1024**3


@dataclass(frozen=True)
class MemorySnapshot:
    ram_available_gib: float | None  # what the VM can still give (MemAvailable), None if unknown
    process_rss_gib: float | None
    vram_free_gib: float | None  # None without CUDA
    vram_total_gib: float | None

    def describe(self) -> str:
        parts = []
        if self.ram_available_gib is not None:
            parts.append(f"{self.ram_available_gib:.1f} GiB RAM available")
        if self.vram_free_gib is not None:
            parts.append(f"{self.vram_free_gib:.1f} of {self.vram_total_gib:.1f} GiB VRAM free")
        return ", ".join(parts) or "memory unknown"


def _meminfo(key: str) -> float | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith(key + ":"):
                    return int(line.split()[1]) * 1024 / GiB
    except OSError:
        return None
    return None


def _rss() -> float | None:
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024 / GiB
    except OSError:
        return None
    return None


def snapshot() -> MemorySnapshot:
    vram_free = vram_total = None
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            vram_free, vram_total = free / GiB, total / GiB
    except Exception:  # no torch, or the CUDA context is broken
        pass
    return MemorySnapshot(_meminfo("MemAvailable"), _rss(), vram_free, vram_total)


def release() -> None:
    """Return freed model memory to the OS: Python objects, the CUDA cache and glibc's arenas."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception as exc:  # a broken CUDA context must not hide the real error
        logger.warning("Could not empty the CUDA cache: %s", exc)
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass  # not glibc (Windows, macOS): nothing to trim


def check_room(*, ram_gib: float, vram_gib: float, what: str) -> str | None:
    """None when there is room to load ``what``; otherwise a message for the user saying what is missing."""
    snap = snapshot()
    short = []
    if snap.ram_available_gib is not None and snap.ram_available_gib < ram_gib:
        short.append(f"{snap.ram_available_gib:.1f} GiB RAM available, {ram_gib:.0f} GiB needed")
    if snap.vram_free_gib is not None and snap.vram_free_gib < vram_gib:
        short.append(f"{snap.vram_free_gib:.1f} GiB GPU memory free, {vram_gib:.1f} GiB needed")
    if not short:
        return None
    return (
        f"Not enough memory to load {what}: " + "; ".join(short) + ". Close GPU-heavy apps and stop idle Docker "
        "containers (scripts/ai-session.ps1 free), then retry."
    )
