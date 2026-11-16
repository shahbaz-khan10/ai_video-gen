"""Speech service: text -> WAV with Chatterbox Multilingual (Resemble AI, MIT, 0.5B).

Runs in its own container (its torch/transformers/diffusers pins conflict with the video stack). The backend calls it
over HTTP; files are shared through the /outputs volume. The model is unloaded after every request by default so the
GPU is free for the video models on an 8 GB card.

Voices are reference recordings (10-20 s WAV/MP3) that the user provides; Chatterbox copies a voice from one
recording (zero-shot). Without a recording the model's built-in voice is used.

Languages: Chatterbox supports English (en) and Hindi (hi), not Urdu. Urdu is spoken with the Hindi model; Urdu-script
text is accepted only after the measured test in docs/speech shows it works (see URDU_SCRIPT_OK).
"""

from __future__ import annotations

import gc
import json
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

VOICES = Path("/voices")
OUTPUTS = Path("/outputs/audio")
URDU_SCRIPT = re.compile(r"[؀-ۿ]")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
URDU_SCRIPT_OK = False  # set from the measured probe (docs/speech/tts_report.json)
MAX_CHARS = 600

app = FastAPI(title="AI Video Studio speech")
_lock = threading.Lock()
_model = None


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    language: str = Field("en", pattern="^(en|hi|ur)$")
    voice_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")
    exaggeration: float = Field(0.5, ge=0.25, le=1.0, description="Emotion intensity (Chatterbox default 0.5).")
    keep_loaded: bool = False


def _load():
    global _model
    if _model is None:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        _model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    return _model


def _unload() -> None:
    global _model
    _model = None
    gc.collect()
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:
        pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "loaded": _model is not None}


@app.get("/voices")
def voices() -> list[dict]:
    VOICES.mkdir(parents=True, exist_ok=True)
    return [json.loads(p.read_text()) for p in sorted(VOICES.glob("*.json"))]


@app.post("/voices")
async def add_voice(request: Request, name: str, gender: str) -> dict:
    """Body: a 5-60 s recording (wav/mp3/m4a/ogg). Stored as 24 kHz mono WAV."""
    if gender not in ("male", "female"):
        raise HTTPException(422, "gender must be male or female")
    data = await request.body()
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "The recording must be between 1 byte and 20 MB.")
    import io

    import librosa
    import soundfile as sf

    try:
        audio, sr = librosa.load(io.BytesIO(data), sr=24000, mono=True)
    except Exception:
        raise HTTPException(422, "This file is not a readable audio recording.") from None
    seconds = len(audio) / sr
    if not 5 <= seconds <= 60:
        raise HTTPException(422, f"The recording is {seconds:.1f} s; it must be 5-60 s (10-20 s works best).")
    voice_id = uuid.uuid4().hex
    VOICES.mkdir(parents=True, exist_ok=True)
    sf.write(VOICES / f"{voice_id}.wav", audio, sr)
    meta = {"id": voice_id, "name": name[:60], "gender": gender, "seconds": round(seconds, 1)}
    (VOICES / f"{voice_id}.json").write_text(json.dumps(meta))
    return meta


@app.post("/tts")
def tts(req: TTSRequest) -> dict:
    text = req.text.strip()
    language = req.language
    if language == "ur":
        if URDU_SCRIPT.search(text) and not URDU_SCRIPT_OK:
            raise HTTPException(
                422, "Urdu script is not supported by the speech model yet. Write Urdu in Roman letters or Hindi script."
            )
        language = "hi"  # Chatterbox has no Urdu; spoken Urdu and Hindi are close, so the Hindi model reads it
    voice = None
    if req.voice_id:
        voice = VOICES / f"{req.voice_id}.wav"
        if not voice.is_file():
            raise HTTPException(404, "Unknown voice.")
    import torchaudio as ta

    with _lock:
        started = time.perf_counter()
        try:
            model = _load()
            wav = model.generate(text, language_id=language, audio_prompt_path=str(voice) if voice else None,
                                 exaggeration=req.exaggeration)
            OUTPUTS.mkdir(parents=True, exist_ok=True)
            out = OUTPUTS / f"{uuid.uuid4()}.wav"
            ta.save(str(out), wav, model.sr)
            duration = wav.shape[-1] / model.sr
        finally:
            if not req.keep_loaded:
                _unload()
    return {"path": str(out), "seconds": round(duration, 2), "generate_seconds": round(time.perf_counter() - started, 1),
            "language_used": language, "voice_id": req.voice_id}
