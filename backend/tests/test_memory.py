"""Memory pre-flight: a clear error instead of a stalled VM (thresholds measured on the RTX 3050)."""

from __future__ import annotations

from app.core.config import Settings
from app.services import memory
from app.services.video_engine import DRAFT_MAX_PIXELS, VideoEngineError, WanVideoEngine


def test_check_room_reports_what_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(memory, "snapshot", lambda: memory.MemorySnapshot(9.0, 0.5, 3.0, 8.0))
    msg = memory.check_room(ram_gib=15, vram_gib=4, what="the video model")
    assert "9.0 GiB RAM available, 15 GiB needed" in msg and "3.0 GiB GPU memory free" in msg
    assert "ai-session.ps1 free" in msg
    assert memory.check_room(ram_gib=8, vram_gib=2, what="x") is None


def test_video_model_does_not_load_without_room(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(memory, "snapshot", lambda: memory.MemorySnapshot(8.0, 0.5, 7.0, 8.0))
    engine = WanVideoEngine(Settings(video_device="cuda", image_model_cache_dir=tmp_path))
    try:
        engine._preflight_load()
    except VideoEngineError as err:
        assert err.code == "out_of_memory" and err.retryable and "15 GiB needed" in err.message
    else:
        raise AssertionError("expected out_of_memory")


def test_release_is_safe_without_glibc_or_cuda() -> None:
    memory.release()  # must never raise


def test_draft_sizes_decode_untiled_and_larger_sizes_tiled() -> None:
    class Vae:
        tiled = None

        def enable_tiling(self):
            self.tiled = True

        def disable_tiling(self):
            self.tiled = False

    class Pipe:
        vae = Vae()

    engine = WanVideoEngine(Settings())
    for (w, h), tiled in {(576, 320): False, (320, 576): False, (416, 416): False, (832, 480): True, (624, 624): True}.items():
        engine._configure_vae(Pipe, w, h)
        assert Pipe.vae.tiled is tiled, (w, h)
    assert DRAFT_MAX_PIXELS == 576 * 320
