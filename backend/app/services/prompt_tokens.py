"""Real tokenizers of the generation models, loaded from the local model cache (never downloaded).

Prompt budgets are measured with the same tokenizer the model uses: CLIP (77 tokens) for RealVisXL, UMT5
(512 tokens, Wan's training length) for the video model. Loading a tokenizer takes well under a second and
does not load any model weights.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

CLIP_MAX_TOKENS = 77  # incl. start and end tokens
UMT5_MAX_TOKENS = 512  # Wan2.1's max_sequence_length (app.services.video_engine.MAX_TEXT_TOKENS)


class Tokenizer(Protocol):
    def __call__(self, text: str, add_special_tokens: bool = ...) -> Any: ...


@lru_cache(maxsize=8)
def load_tokenizer(model_id: str, cache_dir: str | Path | None) -> Any | None:
    """The tokenizer in ``<model>/tokenizer``, or None when the weights are not downloaded."""
    try:
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer

        root = snapshot_download(
            model_id,
            cache_dir=str(cache_dir) if cache_dir else None,
            local_files_only=True,
            allow_patterns=["tokenizer/*"],
        )
        return AutoTokenizer.from_pretrained(str(Path(root) / "tokenizer"), local_files_only=True)
    except Exception as exc:  # missing weights or libraries: callers fall back and say so
        logger.info("Tokenizer for %s not available: %s", model_id, exc)
        return None


def count_tokens(tokenizer: Any, text: str) -> int:
    return len(tokenizer(text, add_special_tokens=False).input_ids)
