"""OmniAvatar service placeholder: health only, while the model is being evaluated (see Dockerfile)."""

from pathlib import Path

from fastapi import FastAPI

app = FastAPI(title="AI Video Studio talking video (OmniAvatar 1.3B)")
MODELS = Path("/omniavatar/pretrained_models")


@app.get("/health")
def health() -> dict:
    ok = (MODELS / "OmniAvatar-1.3B/pytorch_model.pt").is_file() and (
        MODELS / "Wan2.1-T2V-1.3B/diffusion_pytorch_model.safetensors"
    ).is_file()
    return {"status": "ok" if ok else "models_missing", "engine": "omniavatar-1.3b"}
