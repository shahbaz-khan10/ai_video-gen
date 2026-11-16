"""Real probe of Chatterbox Multilingual (MIT): English, Hindi, Roman Urdu and Urdu script with the built-in voice
(and an optional reference recording). Writes WAVs and prints time, real-time factor and VRAM.

    python probe_tts.py /out [--voice /voices/x.wav]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SAMPLES = [
    ("en", "en", "Hello! Welcome to AI Video Studio. Today I will show you how a photo becomes a video."),
    ("hi_devanagari", "hi", "नमस्ते! एआई वीडियो स्टूडियो में आपका स्वागत है। आज मैं आपको दिखाऊँगा कि एक तस्वीर वीडियो कैसे बनती है।"),
    ("ur_roman_as_hi", "hi", "Assalam o alaikum! AI Video Studio mein khush aamdeed. Aaj main aap ko dikhaunga ke aik tasveer video kaise banti hai."),
    ("ur_script_as_hi", "hi", "السلام علیکم! اے آئی ویڈیو اسٹوڈیو میں خوش آمدید۔ آج میں آپ کو دکھاؤں گا کہ ایک تصویر ویڈیو کیسے بنتی ہے۔"),
    ("ur_script_as_ar", "ar", "السلام علیکم! اے آئی ویڈیو اسٹوڈیو میں خوش آمدید۔ آج میں آپ کو دکھاؤں گا کہ ایک تصویر ویڈیو کیسے بنتی ہے۔"),
]


def main() -> None:
    import torch
    import torchaudio as ta
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    voice = sys.argv[sys.argv.index("--voice") + 1] if "--voice" in sys.argv else None
    t0 = time.perf_counter()
    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    print(json.dumps({"load_seconds": round(time.perf_counter() - t0, 1),
                      "vram_gb": round(torch.cuda.memory_allocated() / 2**30, 2)}), flush=True)
    rows = []
    for name, lang, text in SAMPLES:
        torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        wav = model.generate(text, language_id=lang, audio_prompt_path=voice)
        secs = time.perf_counter() - t
        audio_s = wav.shape[-1] / model.sr
        tag = "_voice" if voice else ""
        path = out / f"{name}{tag}.wav"
        ta.save(str(path), wav, model.sr)
        row = {"sample": name, "language_id": lang, "seconds": round(secs, 1), "audio_seconds": round(audio_s, 1),
               "rtf": round(secs / audio_s, 2), "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               "file": path.name}
        rows.append(row)
        print(json.dumps(row), flush=True)
    (out / "tts_report.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
