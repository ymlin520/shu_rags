from functools import lru_cache

from sentence_transformers import SentenceTransformer

from .config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_text(text: str) -> list[float]:
    text = text.strip()
    if not text:
        raise ValueError("Embedding 輸入不可為空白")
    vector = get_model().encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts or any(not text.strip() for text in texts):
        raise ValueError("Embedding 批次不可為空，且不得包含空白內容")
    vectors = get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()
