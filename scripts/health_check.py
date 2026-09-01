import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import COLLECTION_NAME, EMBEDDING_MODEL  # noqa: E402
from backend.embedding import embed_text  # noqa: E402
from backend.qdrant_service import check_connection, collection_info  # noqa: E402


def check(label, fn):
    try:
        value = fn()
        print(f"{label:<16} PASS")
        return True, value
    except Exception as exc:
        print(f"{label:<16} FAIL - {exc}")
        return False, None


def main() -> int:
    print("=" * 31, "\n\nVector FAQ System Health Check\n")
    outcomes = []
    ok, _ = check("Qdrant", check_connection); outcomes.append(ok)
    ok, info = check("Collection", collection_info); outcomes.append(ok)
    ok_points = bool(info and (info.points_count or 0) > 0)
    print(f"{'FAQ Points':<16} {'PASS' if ok_points else 'FAIL - FAQ 數量為 0 或無法讀取'}"); outcomes.append(ok_points)
    ok, vector = check("Embedding", lambda: embed_text("測試")); outcomes.append(ok and len(vector) == 384)
    ok, response = check("FastAPI", lambda: requests.get("http://127.0.0.1:8001/api/health", timeout=5)); outcomes.append(ok and response.status_code == 200)
    print(f"\nCollection: {COLLECTION_NAME}\nEmbedding model: {EMBEDDING_MODEL}\n\n" + "=" * 31)
    print("\nSYSTEM READY" if all(outcomes) else "\nSYSTEM NOT READY")
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
