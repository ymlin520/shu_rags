r"""分派關鍵字測試：只跑關鍵字計分，不呼叫 Ollama。

用法：.venv\Scripts\python.exe -m scripts.test_routing
關鍵字沒把握（分數低於門檻或前兩名太接近）的題目，線上會再交給 AI 判斷，
這裡會另外列出來，方便確認 AI 拿到的候選單位合不合理。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.llm_service import ROUTE_MIN_MARGIN, ROUTE_MIN_SCORE  # noqa: E402
from backend.routing_rules import SCOPES, score_offices  # noqa: E402
from scripts.routing_cases import CASES  # noqa: E402


def main() -> int:
    wrong, unsure = [], []
    for text, expected in CASES:
        ranked = score_offices(text)
        top = ranked[0] if ranked else ("其他行政單位", 0)
        second = ranked[1][1] if len(ranked) > 1 else 0
        if top[0] != expected:
            wrong.append((text, expected, top[0], top[1], ranked[:3]))
        elif top[1] < ROUTE_MIN_SCORE or top[1] - second < ROUTE_MIN_MARGIN:
            unsure.append((text, top[0], top[1], second))

    print(f"題目 {len(CASES)} 題，關鍵字判對 {len(CASES) - len(wrong)} 題、判錯 {len(wrong)} 題")
    for text, expected, got, score, ranked in wrong:
        print(f"  ✗ {text}\n     期待 {expected} / 實得 {got}（{score} 分）  前三名：{ranked}")
    if unsure:
        print(f"\n關鍵字沒把握、線上會交給 AI 的有 {len(unsure)} 題（答案仍正確）：")
        for text, got, score, second in unsure:
            print(f"  ? {text} → {got}（{score} 分，第二名 {second} 分）")
    missing = [office for _, office in CASES if office not in SCOPES]
    if missing:
        print("\n題庫裡有不存在的單位：", sorted(set(missing)))
        return 1
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
