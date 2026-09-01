import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.embedding import embed_text  # noqa: E402
from backend.qdrant_service import search_faq  # noqa: E402

QUERIES = ["休學怎麼辦", "我這學期不想讀了", "怎麼繳學費", "我要看我的成績", "選課選錯了"]


def main() -> int:
    for query in QUERIES:
        results = search_faq(embed_text(query), 5)
        print(f"\nQuery：\n{query}")
        if results:
            print(f"\nTOP 1：\n{results[0]['question']}\n\nScore：\n{results[0]['score']:.3f}")
        else:
            print("\n找不到高於門檻的 FAQ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
