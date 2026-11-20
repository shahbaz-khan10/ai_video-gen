"""/info reports the GPU's total VRAM so the UI can warn about settings that overflow an 8 GB card."""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient

from app.services import memory


@pytest.fixture(autouse=True)
def _fresh_cache():
    memory.gpu_total_gib.cache_clear()
    yield
    memory.gpu_total_gib.cache_clear()


def test_info_reports_gpu_vram(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(memory, "gpu_total_gib", lambda: 8.0)
    assert client.get("/api/v1/info").json()["limits"]["gpu_vram_gb"] == 8.0


def test_info_without_gpu(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(memory, "gpu_total_gib", lambda: None)
    assert client.get("/api/v1/info").json()["limits"]["gpu_vram_gb"] is None


def test_gpu_total_reads_nvidia_smi_once(monkeypatch) -> None:
    calls = []

    def fake_run(cmd, **_):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="8188\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert memory.gpu_total_gib() == 8.0
    assert memory.gpu_total_gib() == 8.0
    assert len(calls) == 1  # cached: no CUDA context, no repeated subprocess


def test_gpu_total_without_nvidia_smi(monkeypatch) -> None:
    def missing(*_a, **_k):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(subprocess, "run", missing)
    assert memory.gpu_total_gib() is None
