"""Optional local embeddings. FTS stays the default search path."""
from __future__ import annotations

import json
import logging
from typing import List, Optional, Sequence

from ..shared.config import config
from ..shared.models import Capsule

logger = logging.getLogger("capsule.embed")

_model = None
_model_name: Optional[str] = None


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / ((left_norm**0.5) * (right_norm**0.5))


def decode_embedding(raw: Optional[str]) -> Optional[List[float]]:
    if not raw:
        return None
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(values, list) or not values:
        return None
    return [float(v) for v in values]


def encode_embedding(values: Sequence[float]) -> str:
    return json.dumps([float(v) for v in values])


def embed_text(text: str) -> Optional[List[float]]:
    """Return a vector, or None if embeddings are off / unavailable.

    Tests may monkeypatch this function.
    """
    if not config.embed_enabled:
        return None
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    global _model, _model_name
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.warning("CAPSULE_EMBED is on but sentence-transformers is not installed")
        return None
    if _model is None or _model_name != config.embed_model:
        _model = SentenceTransformer(config.embed_model)
        _model_name = config.embed_model
    vector = _model.encode(cleaned, normalize_embeddings=True)
    return [float(v) for v in vector.tolist()]


def refresh_embedding(capsule: Capsule) -> None:
    if not config.embed_enabled:
        return
    if capsule.embedding and capsule.embedding_hash == capsule.content_hash:
        return
    text = f"{capsule.topic}\n{capsule.content}"
    vector = embed_text(text)
    if vector is None:
        return
    capsule.embedding = encode_embedding(vector)
    capsule.embedding_model = config.embed_model
    capsule.embedding_hash = capsule.content_hash
