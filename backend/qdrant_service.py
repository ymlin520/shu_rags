import uuid
from datetime import datetime
from collections.abc import Iterable
from typing import Any

from qdrant_client import QdrantClient, models

from .config import COLLECTION_NAME, PROJECT_ROOT, QUESTION_SCORE_THRESHOLD, SCORE_THRESHOLD, VECTOR_SIZE

_CLIENT: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _CLIENT
    if _CLIENT is None:
        local_path = PROJECT_ROOT / "data" / "qdrant-local"
        local_path.mkdir(parents=True, exist_ok=True)
        _CLIENT = QdrantClient(path=str(local_path))
    return _CLIENT


def close_client() -> None:
    global _CLIENT
    if _CLIENT is not None:
        _CLIENT.close()
        _CLIENT = None


def collection_ready() -> bool:
    """目前設定的 collection 存在而且有資料（換向量模型後第一次啟動時會是 False）。"""
    client = get_client()
    return client.collection_exists(COLLECTION_NAME) and client.count(COLLECTION_NAME).count > 0


def check_connection() -> bool:
    get_client().get_collections()
    return True


def create_collection_if_needed() -> None:
    client = get_client()
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
        )


def recreate_collection() -> None:
    client = get_client()
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
    )


def point_id(raw_id: Any) -> int | str:
    value = str(raw_id).strip()
    try:
        return int(value)
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vector-faq:{value}"))


def question_point_id(raw_id: Any) -> str:
    """同一題的「只有題目」向量用另一個 point id，與整段向量並存。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vector-faq-question:{str(raw_id).strip()}"))


def upsert_faqs(records: Iterable[dict[str, Any]], vectors: list[list[float]],
                question_vectors: list[list[float]] | None = None) -> None:
    rows = list(records)
    if len(rows) != len(vectors):
        raise ValueError("FAQ 筆數與向量筆數不一致")
    points = [
        models.PointStruct(id=point_id(row["id"]), vector=vector, payload=row)
        for row, vector in zip(rows, vectors, strict=True)
    ]
    if question_vectors is not None:
        if len(question_vectors) != len(rows):
            raise ValueError("FAQ 筆數與題目向量筆數不一致")
        points += [
            models.PointStruct(id=question_point_id(row["id"]), vector=vector, payload={**row, "_kind": "question"})
            for row, vector in zip(rows, question_vectors, strict=True)
        ]
    if points:
        get_client().upsert(collection_name=COLLECTION_NAME, points=points, wait=True)


def delete_faqs(ids: Iterable[Any]) -> None:
    points = [pid for raw_id in ids for pid in (point_id(raw_id), question_point_id(raw_id))]
    if points:
        get_client().delete(collection_name=COLLECTION_NAME,
                            points_selector=models.PointIdsList(points=points), wait=True)


def search_faq(vector: list[float], limit: int) -> list[dict[str, Any]]:
    """整段向量（門檻 SCORE_THRESHOLD）與題目向量（門檻 QUESTION_SCORE_THRESHOLD）一起查，同一題取高分。"""
    response = get_client().query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limit * 3,
        score_threshold=min(SCORE_THRESHOLD, QUESTION_SCORE_THRESHOLD),
        with_payload=True,
    )
    fallback_date = datetime.fromtimestamp(__file_mtime()).strftime("%Y-%m-%d")
    best: dict[str, dict[str, Any]] = {}
    for item in response.points:
        payload = dict(item.payload or {})
        is_question = payload.pop("_kind", "") == "question"
        score = float(item.score)
        if score < (QUESTION_SCORE_THRESHOLD if is_question else SCORE_THRESHOLD):
            continue
        key = str(payload.get("id") or item.id)
        if key in best and best[key]["score"] >= score:
            continue
        payload["updated_at"] = str(payload.get("updated_at") or payload.get("updated") or fallback_date)
        best[key] = {"score": score, **payload}
    return sorted(best.values(), key=lambda row: -row["score"])[:limit]


def __file_mtime() -> float:
    from .config import PROJECT_ROOT
    candidates = [PROJECT_ROOT / "data" / "faq_import.csv", PROJECT_ROOT.parent / "vector-faq" / "data" / "faq_import.csv"]
    existing = [path.stat().st_mtime for path in candidates if path.exists()]
    return max(existing) if existing else 0


def collection_info() -> Any:
    return get_client().get_collection(COLLECTION_NAME)
