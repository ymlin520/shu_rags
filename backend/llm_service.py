import os
import re

import opencc
import requests

from . import theme_service
from .department_service import department_office, has_priority_word, match_department
from .routing_rules import (DEPARTMENT_FALLBACK_OFFICE, DEPARTMENT_LINKED_OFFICES,
                            normalize_office, score_offices, scope_lines)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
# 相關性檢查用較大的模型：3B 幾乎一律判「無」，9B 在 18 題測試中全對、暖機後每次約 0.2 秒
RELEVANCE_MODEL = os.getenv("FAQ_RELEVANCE_MODEL", "qwen3.5:9b")
RELEVANCE_KEEP_ALIVE = "24h"  # 冷啟動要 30 秒，常駐避免學生第一個問題卡住
_S2T = opencc.OpenCC("s2t")
# 模型偶爾會吐出簡體字，逐字轉回繁體。
# 逐字轉換（不走片語規則）可避免動到台灣慣用寫法；下列是知識庫本來就在用、
# 但 s2t 會改成異體字的字（台北的台、床位的床…），保持原樣不轉。
_KEEP_AS_IS = set("准占台吃峰床秘群里")


def site_text(key: str, fallback: str = "") -> str:
    """取外觀後台 /design 的文案設定，讀不到時用內建預設值。"""
    try:
        value = str(theme_service.load_config()["text"].get(key) or "").strip()
    except Exception:
        value = ""
    return value or theme_service.DEFAULT_TEXT.get(key, "") or fallback


def to_traditional(text: str) -> str:
    """把回答裡的簡體字轉成繁體；台灣慣用的異體字維持原樣。"""
    return "".join(
        converted if (converted := _S2T.convert(char)) != char and char not in _KEEP_AS_IS else char
        for char in text
    )


OFFICES = [
    "教務處-課程與選課", "教務處-學籍與註冊", "教務處-成績與證明", "教務處-畢業資格", "教務處-學分抵免與跨域學習",
    "教務處-研究生與學位考試", "教務處-教師教學行政", "教務處-開課與排課", "教務處-招生及新生",
    "教務處-系所與綜合",
    "學務處生輔組", "學務處課外組", "學務處生涯組", "學務處諮商中心", "學務處衛保組", "學務處宿舍中心", "學務處原民中心", "學務處軍訓室",
    "性別平等教育委員會", "性別所", "性別平等教育中心",
    "兩岸事務中心", "國際事務中心", "總務處", "圖書資訊處-網路組", "圖書資訊處-系統組", "圖書資訊處-圖書資訊服務組", "教學發展中心-企劃管考組", "教學發展中心-教學資源組", "秘書室",
    "人事室", "會計室", "稽核室", "公共事務室", "社會資源發展中心", "舍我紀念館", "民意調查中心", "世新電台", "其他行政單位",
]


# 名稱相近、模型容易分錯的處室，補上業務範圍說明
# 關鍵字命中太弱時（分數低於門檻或前兩名差距太小）就交給模型判斷。
ROUTE_MIN_SCORE = 4      # 例如「宿舍」(2字×權重1×2) 這種單一短字不算有把握
ROUTE_MIN_MARGIN = 2     # 第一名至少要贏第二名這麼多


def _fallback_office(text: str) -> str:
    """純關鍵字計分的結果（分數最高者）；都沒命中回「其他行政單位」。"""
    ranked = score_offices(text)
    return ranked[0][0] if ranked else "其他行政單位"


def _llm_pick_office(text: str, candidates: list[str]) -> str:
    """讓模型從候選單位中挑一個；附上各單位職掌說明。失敗回空字串。"""
    options = candidates or OFFICES
    system = (
        "你是校務詢問單分流器。依照各單位職掌，從清單中選出最適合承辦的一個單位。"
        "只輸出單位名稱，完全照清單的寫法，不要加空白或說明。"
    )
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": RELEVANCE_MODEL, "stream": False, "think": False,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user",
                                "content": f"單位職掌：\n{scope_lines(options)}\n\n問題：{text}\n\n請只輸出一個單位名稱。"}],
                  "options": {"temperature": 0, "num_predict": 30},
                  "keep_alive": RELEVANCE_KEEP_ALIVE},
            timeout=60,
        )
        response.raise_for_status()
        return normalize_office(response.json().get("message", {}).get("content", ""), options)
    except (requests.RequestException, ValueError):
        return ""


def resolve_office(text: str) -> str:
    """關鍵字有把握就用關鍵字，否則交給模型（候選為前幾名＋全部單位）。"""
    ranked = score_offices(text)
    top = ranked[0] if ranked else None
    second = ranked[1][1] if len(ranked) > 1 else 0
    if top and top[1] >= ROUTE_MIN_SCORE and top[1] - second >= ROUTE_MIN_MARGIN:
        return top[0]
    candidates = [office for office, _ in ranked[:3]]
    if len(candidates) < 2:
        candidates = [office for office in OFFICES if office != "其他行政單位"]
    choice = _llm_pick_office(text, candidates)
    return choice or (top[0] if top else "其他行政單位")

def route_ticket(query: str, description: str = "") -> tuple[str, str]:
    """回傳 (處室, 系所)。系所為空字串代表不是系所層級的問題。"""
    text = f"{query}\n{description}".strip()
    keyword_choice = _fallback_office(text)
    department = match_department(text)
    # 題目同時出現系所名稱與系所級業務字（系辦、導師、必修…）時，系所蓋過處室關鍵字
    if department and (keyword_choice == "其他行政單位" or has_priority_word(text)):
        return department_office(department) or DEPARTMENT_FALLBACK_OFFICE, department
    office = resolve_office(text)
    return office, (department if office in DEPARTMENT_LINKED_OFFICES else "")
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "stream": False, "messages": [
                {"role": "system", "content": "你是校務詢問單分流器。只能從指定處室名稱中選一個，僅輸出處室名稱，不要解釋。"},
                {"role": "user", "content": f"處室：{'、'.join(OFFICES)}\n{_OFFICE_HINTS}\n問題：{text}"}],
                "options": {"temperature": 0, "num_predict": 30}, "keep_alive": "10m"}, timeout=30)
        response.raise_for_status()
        choice = response.json().get("message", {}).get("content", "").strip()
        for office in OFFICES:
            if office in choice:
                return office, (department if office in DEPARTMENT_LINKED_OFFICES else "")
    except (requests.RequestException, ValueError):
        pass
    return keyword_choice, ""


def route_ticket_office(query: str, description: str = "") -> str:
    return route_ticket(query, description)[0]


def ollama_status() -> dict[str, str | bool]:
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
        names = {item.get("name", "") for item in response.json().get("models", [])}
        available = OLLAMA_MODEL in names or any(name.startswith(f"{OLLAMA_MODEL}:") for name in names)
        return {"connected": True, "model": OLLAMA_MODEL, "available": available}
    except requests.RequestException:
        return {"connected": False, "model": OLLAMA_MODEL, "available": False}


_RELEVANCE_PROMPT = (
    "你是校務問答的資料審核員。判斷下列每一題 FAQ，能不能直接回答使用者的問題。\n"
    "只有當 FAQ 談的是同一件事時才算能回答；只是字面相似（例如「借教室」與「就學貸款」都有借字）不算。\n"
    "只輸出能回答的 FAQ 編號，用逗號分隔；都不能回答就輸出「無」。不要解釋。"
)


def filter_relevant(query: str, results: list[dict]) -> list[dict] | None:
    """回傳真正能回答問題的 FAQ（可能是空清單）；檢查模型無法使用時回傳 None，呼叫端沿用原結果。"""
    if not results:
        return []
    listing = "\n".join(f"{i}. {x.get('question', '')}｜{str(x.get('answer', ''))[:80]}"
                        for i, x in enumerate(results, start=1))
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": RELEVANCE_MODEL, "stream": False, "think": False,
                  "messages": [{"role": "system", "content": _RELEVANCE_PROMPT},
                               {"role": "user", "content": f"使用者問題：{query}\n\nFAQ：\n{listing}"}],
                  "options": {"temperature": 0, "num_predict": 20}, "keep_alive": RELEVANCE_KEEP_ALIVE},
            timeout=60,
        )
        response.raise_for_status()
        verdict = response.json().get("message", {}).get("content", "").strip()
    except (requests.RequestException, ValueError):
        return None
    picks = {int(n) for n in re.findall(r"\d+", verdict) if 1 <= int(n) <= len(results)}
    if not picks and "無" not in verdict:
        return None  # 輸出看不懂就不要擋，避免誤殺正常回答
    return [item for i, item in enumerate(results, start=1) if i in picks]


def warm_up_relevance_model() -> None:
    """啟動時先把相關性檢查模型載入顯示卡。"""
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": RELEVANCE_MODEL, "prompt": "", "keep_alive": RELEVANCE_KEEP_ALIVE}, timeout=180)
    except requests.RequestException:
        pass


def answer_from_faq(query: str, results: list[dict]) -> str:
    context_blocks = []
    for index, item in enumerate(results, start=1):
        context_blocks.append(
            f"[來源 {index}]\n分類：{item.get('category', '一般問題')}\n"
            f"問題：{item.get('question', '')}\n答案：{item.get('answer', '')}\n"
            f"網址：{item.get('url', '') or '無'}"
        )
    context = "\n\n".join(context_blocks)
    system = (
        "你是世新大學校務問答助理。全部內容一律使用臺灣繁體中文，絕對不可出現任何簡體字，"
        "以親切、清楚、自然的語氣回答。"
        "只能根據提供的 FAQ 內容作答，不得加入常識推測、虛構規定、日期、流程或聯絡方式。"
        f"若資料不足，請明確說『{site_text('ai_no_info')}』。"
        "整合重複內容，保留重要條件與例外；回答控制在 2 到 5 個短段落。"
        "不要聲稱自己看過未提供的文件。只輸出可以直接呈現給使用者的最終答案，"
        "不要描述你的任務、分析步驟、來源篩選過程或思考過程。"
    )
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"使用者問題：{query}\n\n可用 FAQ：\n{context}\n\n請直接輸出最終回答。"},
            ],
            # 300 會把「學生證不見怎麼辦？」這種多步驟流程砍在句子中間（2026-09-23 修）
            "options": {"temperature": 0.1, "num_predict": 900},
            "keep_alive": "10m",
        },
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    answer = to_traditional(payload.get("message", {}).get("content", "").strip())
    if not answer:
        raise RuntimeError("地端模型未回傳回答")
    if payload.get("done_reason") == "length":
        answer = _trim_incomplete_tail(answer)
    return answer


def _trim_incomplete_tail(answer: str) -> str:
    """萬一還是被長度上限截斷，退回最後一個完整句子，不要停在半句。"""
    cut = max(answer.rfind(mark) for mark in "。！？；")
    trimmed = answer[:cut + 1].rstrip() if cut > 0 else ""
    return trimmed or answer
