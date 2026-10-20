from functools import lru_cache

import numpy as np
import requests

from .config import EMBEDDING_MODEL, EMBEDDING_PROVIDER, OLLAMA_URL


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


def _ollama_embed(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 32):
        try:
            response = requests.post(f"{OLLAMA_URL}/api/embed", timeout=300,
                                     json={"model": EMBEDDING_MODEL, "input": texts[start:start + 32], "keep_alive": "24h"})
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"向量模型 {EMBEDDING_MODEL} 無法使用（Ollama）：{exc}") from exc
        vectors += response.json()["embeddings"]
    matrix = np.asarray(vectors, dtype=np.float32)
    return (matrix / np.linalg.norm(matrix, axis=1, keepdims=True)).tolist()


def _encode(texts: list[str]) -> list[list[float]]:
    if EMBEDDING_PROVIDER == "ollama":
        return _ollama_embed(texts)
    return get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


def embed_text(text: str) -> list[float]:
    text = text.strip()
    if not text:
        raise ValueError("Embedding 輸入不可為空白")
    return _encode([text])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts or any(not text.strip() for text in texts):
        raise ValueError("Embedding 批次不可為空，且不得包含空白內容")
    return _encode(texts)
