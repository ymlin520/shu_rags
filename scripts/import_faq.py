import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import BATCH_SIZE  # noqa: E402
from backend.embedding import embed_texts  # noqa: E402
from backend.qdrant_service import close_client, recreate_collection, upsert_faqs  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("faq-import")
CSV_PATH = ROOT / "data" / "faq.csv"
REQUIRED = {"id", "question", "answer"}


def load_csv() -> pd.DataFrame:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"找不到 FAQ CSV：{CSV_PATH}")
    last_error = None
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            frame = pd.read_csv(CSV_PATH, encoding=encoding, dtype=str, keep_default_na=False)
            missing = REQUIRED - set(frame.columns)
            if missing:
                raise ValueError(f"FAQ CSV 缺少必要欄位：{', '.join(sorted(missing))}")
            frame = frame.fillna("")
            frame["question"] = frame["question"].str.strip()
            frame["answer"] = frame["answer"].str.strip()
            if frame.empty:
                raise ValueError("FAQ CSV 沒有資料")
            if (frame["question"] == "").any() or (frame["answer"] == "").any():
                raise ValueError("FAQ 的 question 與 answer 不可為空")
            for optional in ("category", "url", "keywords"):
                if optional not in frame.columns:
                    frame[optional] = ""
            return frame
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"FAQ CSV 不是支援的 UTF-8 編碼：{last_error}")


def embedding_text(row: dict[str, str]) -> str:
    return f"分類：\n{row['category']}\n\n問題：\n{row['question']}\n\n答案：\n{row['answer']}\n\n關鍵字：\n{row['keywords']}"


def main() -> int:
    try:
        frame = load_csv()
        total = len(frame)
        print(f"讀取 FAQ：{total} 筆")
        recreate_collection()
        for start in range(0, total, BATCH_SIZE):
            records = frame.iloc[start : start + BATCH_SIZE].to_dict("records")
            vectors = embed_texts([embedding_text(row) for row in records])
            upsert_faqs(records, vectors)
            print(f"Embedding：{min(start + len(records), total)} / {total}")
        print("Qdrant 匯入完成")
        return 0
    except Exception as exc:
        logger.exception("FAQ 匯入失敗")
        print(f"錯誤：FAQ 匯入失敗：{exc}", file=sys.stderr)
        return 1
    finally:
        close_client()


if __name__ == "__main__":
    raise SystemExit(main())
