"""系所信箱與分派關鍵字。

詢問單分派共三層：
1. 處室業務關鍵字（llm_service._fallback_office）：宿舍、兵役、助學貸款…命中就給該處室。
2. 系所關鍵字（本檔）：原本會落到「教務處註冊課務組／其他行政單位」的題目，改依系所名稱寄到系所信箱；
   若題目同時出現系所名稱與系所級業務字（系辦、導師、必修…），系所優先於處室關鍵字。
3. 都沒命中時交給 AI 判斷處室。

信箱來源：世新大學官網「所有單位信箱」https://www.shu.edu.tw/Email-info.aspx
"""
import json
import re
import secrets

from .config import PROJECT_ROOT

DEPT_FILE = PROJECT_ROOT / "department-emails.json"
DEPT_TOKENS_FILE = PROJECT_ROOT / "department-tokens.json"

# 出現系所名稱時，這些字代表「系所自己的業務」，要蓋過處室關鍵字（例如「資管系必修課」不給課務組）
PRIORITY_WORDS = ["系辦", "導師", "系主任", "系學會", "專題", "必修", "選修", "系上", "課程地圖", "開課", "畢業門檻"]

# 名稱: 信箱、所屬學院／群組、後台歸屬處室、分派關鍵字
DEFAULTS: dict[str, dict] = {
    "新聞傳播學院": {"email": "cjc@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                "keywords": ["新聞傳播學院", "新傳學院", "傳播學院"]},
    "傳播博士學位學程": {"email": "ppcs@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                  "keywords": ["傳播博士學位學程", "傳播博士班", "傳博班"]},
    "新聞學系": {"email": "e01@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
              "keywords": ["新聞學系", "新聞系"]},
    "廣播電視電影學系": {"email": "rtf@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                  "keywords": ["廣播電視電影學系", "廣電系", "廣電", "電影系"]},
    "圖文傳播學系": {"email": "gc@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                "keywords": ["圖文傳播學系", "圖文傳播", "圖傳系", "圖傳"]},
    "公共關係暨廣告學系": {"email": "pc@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                   "keywords": ["公共關係暨廣告學系", "公廣系", "公廣", "廣告系"]},
    "口語傳播暨社群媒體學系": {"email": "speech@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                     "keywords": ["口語傳播暨社群媒體學系", "口語傳播", "口傳系", "口傳"]},
    "資訊傳播學系": {"email": "e07@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                "keywords": ["資訊傳播學系", "資傳系", "資傳"]},
    "數位多媒體設計學系": {"email": "dma@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                   "keywords": ["數位多媒體設計學系", "數位多媒體", "數媒系", "數媒"]},
    "傳播管理學系": {"email": "cm@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                "keywords": ["傳播管理學系", "傳管系", "傳管"]},
    "傳播匯流與創新管理學位學程": {"email": "e07@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                       "keywords": ["傳播匯流與創新管理學位學程", "傳播匯流學程", "傳播匯流"]},
    "全媒體學士學位學程": {"email": "cm@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                   "keywords": ["全媒體學士學位學程", "全媒體學程", "全媒體"]},
    "影視進修學士學位學程": {"email": "rtf@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                    "keywords": ["影視進修學士學位學程", "影視進修學程", "影視進修"]},
    "全球智能傳播全英學士學位學程": {"email": "cjc@mail.shu.edu.tw", "group": "新聞傳播學院", "office": "教務處註冊課務組",
                        "keywords": ["全球智能傳播全英學士學位學程", "全球智能傳播", "全英學程"]},
    "管理學院": {"email": "smgmt@mail.shu.edu.tw", "group": "管理學院", "office": "教務處註冊課務組",
              "keywords": ["管理學院", "管院"]},
    "資訊管理學系": {"email": "im@mail.shu.edu.tw", "group": "管理學院", "office": "教務處註冊課務組",
                "keywords": ["資訊管理學系", "資管系", "資管"]},
    "觀光學系": {"email": "e25@mail.shu.edu.tw", "group": "管理學院", "office": "教務處註冊課務組",
              "keywords": ["觀光學系", "觀光系"]},
    "經濟學系": {"email": "econ@mail.shu.edu.tw", "group": "管理學院", "office": "教務處註冊課務組",
              "keywords": ["經濟學系", "經濟系"]},
    "財務金融學系": {"email": "fin@mail.shu.edu.tw", "group": "管理學院", "office": "教務處註冊課務組",
                "keywords": ["財務金融學系", "財金系", "財金"]},
    "行政管理學系": {"email": "ppm@mail.shu.edu.tw", "group": "管理學院", "office": "教務處註冊課務組",
                "keywords": ["行政管理學系", "行管系", "行管"]},
    "企業管理學系": {"email": "ba@mail.shu.edu.tw", "group": "管理學院", "office": "教務處註冊課務組",
                "keywords": ["企業管理學系", "企管系", "企管"]},
    # 國際廉能治理碩士在職學位學程、非營利與社會企業碩士在職學位學程已停招，不列入分派
    "人文社會學院": {"email": "chss@mail.shu.edu.tw", "group": "人文社會學院", "office": "教務處註冊課務組",
                "keywords": ["人文社會學院", "人社學院", "人社院"]},
    "社會發展研究所": {"email": "e62@mail.shu.edu.tw", "group": "人文社會學院", "office": "教務處註冊課務組",
                 "keywords": ["社會發展研究所", "社發所"]},
    "性別研究所": {"email": "gndrshu@mail.shu.edu.tw", "group": "人文社會學院", "office": "教務處註冊課務組",
               "keywords": ["性別研究所", "性別所"]},
    "社會心理學系": {"email": "socpsy@mail.shu.edu.tw", "group": "人文社會學院", "office": "教務處註冊課務組",
                "keywords": ["社會心理學系", "社心系", "社心"]},
    "英語暨傳播應用學系": {"email": "dteng@mail.shu.edu.tw", "group": "人文社會學院", "office": "教務處註冊課務組",
                   "keywords": ["英語暨傳播應用學系", "英語暨傳播", "英語系", "英文系"]},
    "中國文學系": {"email": "chinese@mail.shu.edu.tw", "group": "人文社會學院", "office": "教務處註冊課務組",
               "keywords": ["中國文學系", "中文系"]},
    "日本語文學系": {"email": "jp@mail.shu.edu.tw", "group": "人文社會學院", "office": "教務處註冊課務組",
                "keywords": ["日本語文學系", "日文系", "日語系"]},
    "法律學院": {"email": "lawsch@mail.shu.edu.tw", "group": "法律學院", "office": "教務處註冊課務組",
              "keywords": ["法律學院", "法學院"]},
    "智慧財產暨傳播科技法律研究所": {"email": "ipr@mail.shu.edu.tw", "group": "法律學院", "office": "教務處註冊課務組",
                        "keywords": ["智慧財產暨傳播科技法律研究所", "智財所", "智慧財產"]},
    "法律學系": {"email": "law@mail.shu.edu.tw", "group": "法律學院", "office": "教務處註冊課務組",
              "keywords": ["法律學系", "法律系"]},
    "共同課程委員會": {"email": "cgs@mail.shu.edu.tw", "group": "共同教學單位", "office": "其他行政單位",
                 "keywords": ["共同課程委員會", "共同必修", "共同科目"]},
    "通識教育中心": {"email": "gd@mail.shu.edu.tw", "group": "共同教學單位", "office": "其他行政單位",
                "keywords": ["通識教育中心", "通識課", "通識"]},
    "體育室": {"email": "e99@mail.shu.edu.tw", "group": "共同教學單位", "office": "其他行政單位",
             "keywords": ["體育室", "體育課", "體育館", "運動代表隊", "游泳池", "球場"]},
    "外語教學中心": {"email": "language@mail.shu.edu.tw", "group": "共同教學單位", "office": "其他行政單位",
                "keywords": ["外語教學中心", "英語能力檢定", "英檢", "外語課程", "多益"]},
    "華語文教學中心": {"email": "ctcshu@mail.shu.edu.tw", "group": "共同教學單位", "office": "其他行政單位",
                 "keywords": ["華語文教學中心", "華語課程", "華語班"]},
}

_EMAIL_PATTERN = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def load_departments() -> dict[str, dict]:
    """預設值 + 後台儲存的覆寫（信箱、關鍵字）。"""
    try:
        saved = json.loads(DEPT_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    result: dict[str, dict] = {}
    for name, default in DEFAULTS.items():
        item = dict(default)
        override = saved.get(name) if isinstance(saved.get(name), dict) else {}
        email = str(override.get("email") or "").strip()
        if _EMAIL_PATTERN.match(email):
            item["email"] = email
        words = override.get("keywords")
        if isinstance(words, list):
            cleaned = [str(word).strip() for word in words if str(word).strip()]
            if cleaned:
                item["keywords"] = list(dict.fromkeys(cleaned))
        result[name] = item
    return result


def save_departments(data: dict) -> dict[str, dict]:
    current = load_departments()
    saved: dict[str, dict] = {}
    for name, item in current.items():
        incoming = (data or {}).get(name)
        if isinstance(incoming, dict):
            email = str(incoming.get("email") or "").strip()
            if email and not _EMAIL_PATTERN.match(email):
                raise ValueError(f"{name} 的信箱格式不正確：{email}")
            words = incoming.get("keywords")
            if isinstance(words, str):
                words = re.split(r"[,，、\s]+", words)
            if isinstance(words, list):
                words = [str(word).strip() for word in words if str(word).strip()]
            else:
                words = item["keywords"]
            item = {**item, "email": email or item["email"],
                    "keywords": list(dict.fromkeys(words)) or item["keywords"]}
        saved[name] = {"email": item["email"], "keywords": item["keywords"]}
    DEPT_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    return load_departments()


def match_department(text: str) -> str:
    """回傳命中的系所名稱；關鍵字長的優先（「新聞傳播學院」不會被「傳播學院」蓋掉）。"""
    if not text:
        return ""
    pairs = [(word, name) for name, item in load_departments().items() for word in item["keywords"]]
    for word, name in sorted(pairs, key=lambda pair: -len(pair[0])):
        if word in text:
            return name
    return ""


def has_priority_word(text: str) -> bool:
    return any(word in (text or "") for word in PRIORITY_WORDS)


def load_tokens() -> dict[str, str]:
    """系所專屬登入碼；與處室的 office-tokens.json 分開存。"""
    try:
        saved = json.loads(DEPT_TOKENS_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        saved = {}
    return {name: str(code).strip() for name, code in saved.items() if str(code).strip()} if isinstance(saved, dict) else {}


def ensure_tokens() -> dict[str, str]:
    """替還沒有登入碼的系所配一組；已存在的不動。啟動時呼叫，重複執行安全。"""
    tokens = load_tokens()
    changed = False
    for name in DEFAULTS:
        if not tokens.get(name):
            tokens[name] = secrets.token_urlsafe(12)
            changed = True
    for name in list(tokens):
        if name not in DEFAULTS:  # 停招或改名的單位不再保留登入碼
            tokens.pop(name)
            changed = True
    if changed:
        DEPT_TOKENS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    return tokens


def department_login_code(name: str) -> str:
    return load_tokens().get(name or "", "")


def department_by_token(token: str) -> str:
    """用登入碼反查系所名稱；找不到回空字串。"""
    if not token:
        return ""
    for name, code in load_tokens().items():
        if secrets.compare_digest(token, code):
            return name
    return ""


def department_email(name: str) -> str:
    item = load_departments().get(name or "")
    return item["email"] if item else ""


def department_office(name: str) -> str:
    item = load_departments().get(name or "")
    return item["office"] if item else ""
