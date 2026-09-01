import csv
from pathlib import Path

from .config import PROJECT_ROOT
from .embedding import embed_text
from .qdrant_service import upsert_faqs

CSV_PATH = PROJECT_ROOT / "data" / "faq.csv"
FIELDS = ["id", "category", "question", "answer", "url", "keywords"]
FAQ_MARKER = "[列入知識庫整理候選]"


def _record(ticket: dict) -> dict[str, str]:
    answer = str(ticket.get("resolution") or "").replace(FAQ_MARKER, "").strip()
    question = str(ticket.get("query") or ticket.get("subject") or "").strip()
    if ticket.get("status") != "已解決" or not question or not answer:
        raise ValueError("只有包含完整問題與回答的已解決工單才能加入知識庫")
    office = str(ticket.get("office") or "承辦處室").strip()
    category = str(ticket.get("category") or "工單回覆").strip()
    return {
        "id": f"TICKET-{ticket['ticket_no']}", "category": category, "question": question,
        "answer": answer, "url": "", "keywords": f"{category} {office} 工單回覆 已解決",
    }


def _save_csv(record: dict[str, str]) -> None:
    rows: list[dict[str, str]] = []
    if CSV_PATH.exists():
        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as source:
            rows = [{field: str(row.get(field) or "") for field in FIELDS} for row in csv.DictReader(source)]
    for index, row in enumerate(rows):
        if row["id"] == record["id"]:
            rows[index] = record
            break
    else:
        rows.append(record)
    temporary = Path(str(CSV_PATH) + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(CSV_PATH)


def sync_resolved_ticket(ticket: dict) -> dict[str, str]:
    record = _record(ticket)
    text = (f"分類：\n{record['category']}\n\n問題：\n{record['question']}\n\n"
            f"答案：\n{record['answer']}\n\n關鍵字：\n{record['keywords']}")
    upsert_faqs([record], [embed_text(text)])
    _save_csv(record)
    return record
