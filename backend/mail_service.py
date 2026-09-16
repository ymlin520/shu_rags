import json
import os
import re
import smtplib
import base64
from html import escape
from email.message import EmailMessage
from pathlib import Path

from . import theme_service
from .config import PROJECT_ROOT

DEFAULT_EMAIL = os.getenv("FAQ_DEFAULT_EMAIL", "admin@example.edu.tw")
OFFICES = ["教務處招生組", "教務處註冊課務組", "學務處生活輔導組", "學務處住宿服務組", "兩岸事務中心", "國際事務中心",
           "總務處", "圖資處", "系辦公室", "其他行政單位"]
DEFAULT_SETTINGS = {"server": "smtp.gmail.com", "port": 587, "username": "", "from_name": "校務AI系統",
                    "subject_tag": "校務AI系統",
                    "method": "", "use_tls": True, "require_auth": True,
                    "student_recipients": [DEFAULT_EMAIL]}
SETTINGS_FILE = PROJECT_ROOT / "mail-settings.json"
OFFICE_FILE = PROJECT_ROOT / "office-emails.json"
PASSWORD_FILE = PROJECT_ROOT / "mail-app-password.txt"
GOOGLE_CLIENT_FILE = PROJECT_ROOT / "gmail-oauth-client.json"
GOOGLE_TOKEN_FILE = PROJECT_ROOT / "gmail-oauth-token.json"
OFFICE_TOKENS_FILE = PROJECT_ROOT / "office-tokens.json"
_EMAIL_PATTERN = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def _json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_settings() -> dict:
    settings = {**DEFAULT_SETTINGS, **_json(SETTINGS_FILE, {})}
    saved = settings.get("student_recipients")
    if not isinstance(saved, list):
        saved = [saved] if saved else []
    settings["student_recipients"] = list(dict.fromkeys(
        str(address).strip().lower() for address in saved if str(address).strip()
    )) or [DEFAULT_EMAIL]
    return settings


def save_settings(data: dict) -> dict:
    settings = load_settings()
    settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS and v not in (None, "")})
    settings["port"] = int(settings.get("port") or 587)
    recipients = settings.get("student_recipients")
    if isinstance(recipients, list):
        settings["student_recipients"] = list(dict.fromkeys(
            str(address).strip().lower() for address in recipients if str(address).strip()
        )) or [DEFAULT_EMAIL]
    _write_json(SETTINGS_FILE, settings)
    return settings


def load_office_emails() -> dict:
    saved = _json(OFFICE_FILE, {})
    return {office: str(saved.get(office) or DEFAULT_EMAIL).strip() for office in OFFICES}


def save_office_emails(data: dict) -> dict:
    emails = load_office_emails()
    for office, address in (data or {}).items():
        if office in emails:
            emails[office] = str(address or DEFAULT_EMAIL).strip() or DEFAULT_EMAIL
    _write_json(OFFICE_FILE, emails)
    return emails


def _password() -> str:
    from_env = os.getenv("FAQ_SMTP_PASSWORD", "")
    if from_env:
        return from_env
    return PASSWORD_FILE.read_text(encoding="utf-8-sig").strip() if PASSWORD_FILE.exists() else ""


def save_password(password: str) -> None:
    PASSWORD_FILE.write_text(password.strip(), encoding="utf-8")


def office_email(office: str) -> str:
    return load_office_emails().get(office) or DEFAULT_EMAIL


def office_login_code(office: str) -> str:
    tokens = _json(OFFICE_TOKENS_FILE, {})
    return str(tokens.get(office) or "").strip()


def base_url() -> str:
    public_file = PROJECT_ROOT / "public-url.txt"
    if public_file.exists():
        url = public_file.read_text(encoding="utf-8-sig").strip().rstrip("/")
        if url:
            return url
    return "http://127.0.0.1:8001"


def _resolved_method(settings: dict) -> str:
    method = str(settings.get("method") or "").strip().lower()
    if method in ("smtp", "gmail_oauth"):
        return method
    return "gmail_oauth" if (GOOGLE_CLIENT_FILE.exists() and GOOGLE_TOKEN_FILE.exists()) else "smtp"


def _configured(settings: dict) -> bool:
    if _resolved_method(settings) == "gmail_oauth":
        return GOOGLE_CLIENT_FILE.exists() and GOOGLE_TOKEN_FILE.exists()
    if not settings.get("username"):
        return False
    if settings.get("require_auth", True):
        return bool(_password())
    return True


def mail_status() -> dict:
    settings = load_settings()
    return {
        "configured": _configured(settings),
        "method": _resolved_method(settings),
        "server": settings.get("server", "smtp.gmail.com"),
        "port": int(settings.get("port", 587)),
        "sender": settings.get("username", ""),
        "from_name": settings.get("from_name", DEFAULT_SETTINGS["from_name"]),
        "subject_tag": _subject_tag(settings),
        "use_tls": bool(settings.get("use_tls", True)),
        "require_auth": bool(settings.get("require_auth", True)),
        "password_set": bool(_password()),
        "default_email": DEFAULT_EMAIL,
        "student_recipients": settings.get("student_recipients", [DEFAULT_EMAIL]),
        "base_url": base_url(),
        "offices": load_office_emails(),
    }


def _send(message: EmailMessage) -> None:
    settings = load_settings()
    if _resolved_method(settings) == "gmail_oauth":
        if not (GOOGLE_CLIENT_FILE.exists() and GOOGLE_TOKEN_FILE.exists()):
            raise RuntimeError("寄件方式設為 Gmail OAuth，但找不到授權檔，請重新授權或改用 SMTP")
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        credentials = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), scopes)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            GOOGLE_TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
        if not credentials.valid:
            raise RuntimeError("Gmail OAuth 授權已失效，請重新授權")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        build("gmail", "v1", credentials=credentials, cache_discovery=False).users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return
    server, port = settings.get("server", "smtp.gmail.com"), int(settings.get("port", 587))
    use_tls = bool(settings.get("use_tls", True))
    require_auth = bool(settings.get("require_auth", True))
    if port == 465:
        with smtplib.SMTP_SSL(server, port, timeout=30) as smtp:
            if require_auth:
                smtp.login(settings["username"], _password())
            smtp.send_message(message)
        return
    with smtplib.SMTP(server, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if require_auth:
            smtp.login(settings["username"], _password())
        smtp.send_message(message)


def _mail_text(key: str, tokens: dict[str, str] | None = None) -> str:
    """信件文字取自外觀後台 /design 的文案設定，留空時用內建預設值。"""
    try:
        value = str(theme_service.load_config()["text"].get(key) or "").strip()
    except Exception:
        value = ""
    value = value or theme_service.DEFAULT_TEXT.get(key, "")
    for name, replacement in (tokens or {}).items():
        value = value.replace("{" + name + "}", str(replacement))
    return value


def _subject_tag(settings: dict) -> str:
    """後台可自訂的信件主旨標題；未填寫時沿用寄件人顯示名稱。"""
    return (str(settings.get("subject_tag") or "").strip()
            or str(settings.get("from_name") or "").strip()
            or DEFAULT_SETTINGS["subject_tag"])


def _from_header(settings: dict) -> str:
    return f"{settings.get('from_name') or DEFAULT_SETTINGS['from_name']} <{settings['username']}>"


def send_ticket_email(ticket: dict) -> tuple[bool, str]:
    settings = load_settings()
    if not _configured(settings):
        return False, "尚未設定寄件帳號或應用程式密碼"
    recipient = office_email(ticket["office"])
    office_link = f"{base_url()}/office/ticket/{ticket['ticket_no']}"
    office_home = f"{base_url()}/office"
    login_code = office_login_code(ticket["office"])
    tokens = {"處室": str(ticket.get("office") or ""), "單號": str(ticket.get("ticket_no") or "")}
    intro_text = _mail_text("mail_office_intro", tokens)
    question_title = _mail_text("mail_office_question_title", tokens)
    desc_title = _mail_text("mail_office_desc_title", tokens)
    button_text = _mail_text("mail_office_button", tokens)
    login_title = _mail_text("mail_office_login_title", tokens)
    code_label = _mail_text("mail_office_code_label", tokens)
    footer_text = _mail_text("mail_office_footer", tokens)
    message = EmailMessage()
    message["Subject"] = f"[{_subject_tag(settings)} {ticket['ticket_no']}] {ticket['subject']}"
    message["From"] = _from_header(settings)
    message["To"] = recipient
    message["Reply-To"] = settings["username"]
    message.set_content(
        f"您好：\n\n{intro_text}\n\n"
        f"詢問單編號：{ticket['ticket_no']}\n"
        f"建立時間：{ticket.get('created_at', '')}\n"
        f"分類：{ticket.get('category', '')}\n"
        f"申請人：{ticket.get('requester_name', '')}（{ticket.get('requester_contact', '')}）\n\n"
        f"── {question_title} ──\n{ticket['query']}\n\n"
        f"── {desc_title} ──\n{ticket['description']}\n\n"
        f"── 詢問單連結 ──\n{office_link}\n\n"
        f"── 處室後台 ──\n{office_home}\n"
        f"{code_label}：{login_code or '請洽系統管理者'}\n\n"
        f"{footer_text}\n"
    )
    safe_office = escape(str(ticket["office"]))
    safe_ticket_no = escape(str(ticket["ticket_no"]))
    safe_subject = escape(str(ticket["subject"]))
    safe_query = escape(str(ticket["query"]))
    safe_description = escape(str(ticket["description"])).replace(chr(10), "<br>")
    safe_login_code = escape(login_code or "請洽系統管理者")
    message.add_alternative(
        "<div style=\"font-family:'Noto Sans TC',Arial,sans-serif;font-size:15px;color:#1f2933;line-height:1.7\">"
        f"<p>您好：</p><p>{escape(intro_text)}</p>"
        "<table style=\"border-collapse:collapse;margin:16px 0\">"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#6b7280\">詢問單編號</td><td><strong>{safe_ticket_no}</strong></td></tr>"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#6b7280\">建立時間</td><td>{ticket.get('created_at', '')}</td></tr>"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#6b7280\">分類</td><td>{ticket.get('category', '')}</td></tr>"
        f"<tr><td style=\"padding:4px 12px 4px 0;color:#6b7280\">申請人</td><td>{ticket.get('requester_name', '')}（{ticket.get('requester_contact', '')}）</td></tr>"
        "</table>"
        f"<h3 style=\"margin:20px 0 6px\">{escape(question_title)}</h3><p>{safe_query}</p>"
        f"<h3 style=\"margin:20px 0 6px\">{escape(desc_title)}</h3><p>{safe_description}</p>"
        f"<p style=\"margin:24px 0\"><a href=\"{office_link}\" style=\"background:#2563eb;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none\">{escape(button_text)}</a></p>"
        f"<div style=\"border:1px solid #d7dce2;background:#f5f7fa;border-radius:10px;padding:14px 16px;margin:18px 0\"><strong>{escape(login_title)}</strong><p style=\"margin:8px 0 0\">後台連結：<a href=\"{office_home}\">{office_home}</a><br>{escape(code_label)}：<code style=\"font-size:15px;font-weight:700\">{safe_login_code}</code></p></div>"
        f"<p style=\"color:#6b7280;font-size:13px\">若按鈕無法開啟，請複製此連結：<br>{office_link}<br>{escape(footer_text)}</p></div>",
        subtype="html",
    )
    try:
        _send(message)
        return True, recipient
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def student_recipient(ticket: dict, settings: dict | None = None) -> tuple[str, bool]:
    """回傳 (結案信收件人, 是否為提問者本人信箱)。

    前台送單時會請學生填 Email，存在 requester_contact。該欄是自由文字，
    可能是電話或「未提供」，所以只在通過 Email 格式檢查時才寄給本人，
    否則退回管理後台設定的通知清單，確保信不會掉。
    """
    contact = str(ticket.get("requester_contact") or "").strip()
    if _EMAIL_PATTERN.match(contact):
        return contact, True
    settings = load_settings() if settings is None else settings
    fallback = settings.get("student_recipients") or [DEFAULT_EMAIL]
    return ", ".join(fallback), False


def send_student_resolution_email(ticket: dict) -> tuple[bool, str, str]:
    settings = load_settings()
    recipient, _ = student_recipient(ticket, settings)
    if not _configured(settings):
        return False, "尚未設定寄件帳號或應用程式密碼", recipient
    access_key = str(ticket.get("access_key") or "").strip()
    if not access_key:
        return False, "詢問單缺少學生存取碼", recipient
    ticket_link = f"{base_url()}/ticket/{ticket['ticket_no']}?key={access_key}"
    question = str(ticket.get("query") or ticket.get("subject") or "")
    answer = str(ticket.get("resolution") or "")
    tokens = {"處室": str(ticket.get("office") or ""), "單號": str(ticket.get("ticket_no") or "")}
    student_subject = _mail_text("mail_student_subject", tokens)
    student_intro = _mail_text("mail_student_intro", tokens)
    q_label = _mail_text("mail_student_q_label", tokens)
    a_label = _mail_text("mail_student_a_label", tokens)
    rate_prompt = _mail_text("mail_student_rate_prompt", tokens)
    student_button = _mail_text("mail_student_button", tokens)
    message = EmailMessage()
    message["Subject"] = f"[{_subject_tag(settings)} {ticket['ticket_no']}] {student_subject}"
    message["From"] = _from_header(settings)
    message["To"] = recipient
    message["Reply-To"] = settings["username"]
    message.set_content(
        f"您好：\n\n{student_intro}\n\n"
        f"詢問單編號：{ticket['ticket_no']}\n\n【{q_label}】\n{question}\n\n【{a_label}】\n{answer}\n\n"
        f"請開啟下列連結查看 Q&A 並評分 1～5 顆星：\n{ticket_link}#rate-card\n"
    )
    safe_office = escape(str(ticket["office"]))
    safe_no = escape(str(ticket["ticket_no"]))
    safe_q = escape(question).replace(chr(10), "<br>")
    safe_a = escape(answer).replace(chr(10), "<br>")
    star_links = " ".join(
        f'<a href="{ticket_link}&rating={n}#rate-card" style="font-size:28px;color:#e6532d;text-decoration:none" title="評分 {n} 顆星">{chr(9733)}</a>'
        for n in range(1, 6)
    )
    message.add_alternative(
        "<div style=\"font-family:'Noto Sans TC',Arial,sans-serif;font-size:15px;color:#1f2933;line-height:1.7;max-width:680px\">"
        f"<p>您好：</p><p>{escape(student_intro)}</p>"
        f"<div style=\"border:1px solid #ddd;border-radius:10px;padding:16px;margin:18px 0\"><strong>{escape(q_label)}</strong><p>{safe_q}</p><hr style=\"border:0;border-top:1px solid #eee\"><strong>{escape(a_label)}</strong><p>{safe_a}</p></div>"
        f"<p><strong>{escape(rate_prompt)}</strong></p><div>{star_links}</div>"
        f"<p style=\"margin:24px 0\"><a href=\"{ticket_link}#rate-card\" style=\"background:#e6532d;color:#fff;padding:11px 18px;border-radius:8px;text-decoration:none\">{escape(student_button)}</a></p>"
        f"<p style=\"color:#6b7280;font-size:13px\">若按鈕無法開啟，請複製此連結：<br>{ticket_link}</p></div>",
        subtype="html",
    )
    try:
        _send(message)
        return True, recipient, recipient
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", recipient


def send_test_email(recipient: str) -> tuple[bool, str]:
    settings = load_settings()
    if not _configured(settings):
        return False, "尚未設定寄件帳號或應用程式密碼"
    recipient = (recipient or DEFAULT_EMAIL).strip()
    message = EmailMessage()
    message["Subject"] = f"[{_subject_tag(settings)}] 測試信"
    message["From"] = _from_header(settings)
    message["To"] = recipient
    message.set_content(
        f"這是{_subject_tag(settings)}的寄信測試。\n\n"
        f"收到本信表示 SMTP 設定正確，之後學生送出的詢問單會自動寄到各處室設定的信箱。\n"
        f"系統網址：{base_url()}\n"
    )
    try:
        _send(message)
        return True, recipient
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
