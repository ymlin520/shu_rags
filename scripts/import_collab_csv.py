import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path


def clean(value: str | None) -> str:
    return (value or "").strip()


def main() -> int:
    if len(sys.argv) != 3:
        print("用法：import_collab_csv.py <來源 CSV> <輸出 faq.csv>", file=sys.stderr)
        return 2

    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    rows_out: list[dict[str, str]] = []
    skipped = 0
    id_counts: Counter[str] = Counter()

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"問題編號", "分類", "問題", "建議答案"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"來源 CSV 缺少欄位：{', '.join(sorted(missing))}")

        for row in reader:
            question = clean(row.get("問題"))
            answer = clean(row.get("建議答案"))
            if not question or not answer:
                skipped += 1
                continue

            raw_id = clean(row.get("問題編號"))
            if not raw_id:
                raw_id = "AUTO-" + hashlib.sha1(question.encode("utf-8")).hexdigest()[:12]
            id_counts[raw_id] += 1
            faq_id = raw_id if id_counts[raw_id] == 1 else f"{raw_id}-{id_counts[raw_id]}"

            source_ref = clean(row.get("依據／來源連結"))
            url = source_ref if source_ref.lower().startswith(("http://", "https://")) else ""
            keyword_parts = [
                clean(row.get("分類")),
                clean(row.get("主責單位")),
                clean(row.get("狀態")),
                "" if url else source_ref,
                clean(row.get("備註")),
            ]
            keywords = " ".join(part for part in keyword_parts if part)
            rows_out.append(
                {
                    "id": faq_id,
                    "category": clean(row.get("分類")),
                    "question": question,
                    "answer": answer,
                    "url": url,
                    "keywords": keywords,
                }
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "category", "question", "answer", "url", "keywords"])
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"來源：{source}")
    print(f"已轉換：{len(rows_out)} 筆")
    print(f"略過空白問題／答案：{skipped} 筆")
    print(f"輸出：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
