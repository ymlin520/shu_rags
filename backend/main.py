import logging
import threading
import csv
import io
import json
import os
import re
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Body, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from urllib.parse import unquote

from .config import COLLECTION_NAME, DIRECT_ANSWER_SCORE, EMBEDDING_MODEL, PROJECT_ROOT
from .embedding import embed_text
from .llm_service import (site_text, answer_from_faq, filter_relevant, ollama_status, route_ticket,
                          warm_up_relevance_model)
from .department_service import (load_departments, save_departments, match_department,
                                 department_office, department_by_token, ensure_tokens)
from .department_service import DEFAULTS as DEPARTMENT_DEFAULTS
from .knowledge_service import faq_categories, sync_resolved_ticket
from . import faq_service
from .analytics import add_ticket_reply, create_ticket, delete_ticket, department_stats, set_ticket_settled, settle_stats, list_tickets, record_ack_email, log_feedback, log_query, public_ticket, rate_ticket, record_knowledge_sync, record_student_email, record_ticket_email, stats, ticket_detail, update_ticket
from .routing_rules import DEPARTMENT_FALLBACK_OFFICE, normalize_office, score_offices
from .mail_service import (department_recipient, mail_status, save_office_emails, save_password, save_settings,
                           send_ticket_ack_email,
                           send_student_resolution_email, send_test_email, send_ticket_email)
from .models import (AnswerResponse, FaqImportRequest, FaqTransferRequest, FaqUpsertRequest, FeedbackRequest, FeedbackResponse,
                     MailSettingsRequest, MailTestRequest, OfficeMailRequest, SearchRequest, SearchResponse,
                     TicketSettleRequest,
                     TicketCreateRequest, TicketRateRequest, TicketReplyRequest, TicketUpdateRequest)
from .qdrant_service import check_connection, close_client, collection_info, collection_ready, search_faq
from . import theme_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("vector-faq")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("FAQ API 啟動 embedding=%s collection=%s", EMBEDDING_MODEL, COLLECTION_NAME)
    threading.Thread(target=warm_up_relevance_model, daemon=True).start()
    if not collection_ready():
        # 換了向量模型（例如 MiniLM → bge-m3）後第一次啟動：先把整個知識庫建好再開始服務，約一分鐘
        started = time.perf_counter()
        indexed = faq_service.reindex()
        logger.info("向量庫不存在，已重建 %s 筆 duration_s=%.1f", indexed, time.perf_counter() - started)
    try:
        yield
    finally:
        close_client()


app = FastAPI(title="校務 FAQ 智慧搜尋", lifespan=lifespan)
frontend = PROJECT_ROOT / "frontend"
app.mount("/static", StaticFiles(directory=frontend), name="static")
theme_service.ASSET_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=theme_service.ASSET_DIR), name="media")


ensure_tokens()  # 新系所啟動時自動配發專屬登入碼


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    return FileResponse(frontend / "admin.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/faq-admin", include_in_schema=False)
def faq_admin_page() -> FileResponse:
    return FileResponse(frontend / "faq-admin.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/office", include_in_schema=False)
def office_page() -> FileResponse:
    return FileResponse(frontend / "office.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/office/ticket/{ticket_no}", include_in_schema=False)
def office_ticket_page(ticket_no: str) -> FileResponse:
    return FileResponse(frontend / "office-ticket.html")


@app.get("/ticket/{ticket_no}", include_in_schema=False)
def ticket_page(ticket_no: str) -> FileResponse:
    return FileResponse(frontend / "ticket.html")


@app.get("/guide", include_in_schema=False)
def guide_page() -> FileResponse:
    """給學生與處室承辦人看的使用說明（截圖放在 frontend/guide/）。"""
    return FileResponse(frontend / "guide.html", headers={"Cache-Control": "no-cache"})


@app.get("/design", include_in_schema=False)
def design_page() -> FileResponse:
    """外觀 / 文案管理後台。"""
    return FileResponse(frontend / "design-admin.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/site-theme.css", include_in_schema=False)
def site_theme_css() -> Response:
    return Response(content=theme_service.render_site_css(), media_type="text/css",
                    headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/api/site-config")
def site_config_public():
    """前台載入用：只回傳文案與選單，不含設定介面資訊。"""
    cfg = theme_service.load_config()
    return {"text": cfg["text"], "suggestions": cfg["suggestions"],
            "categories": cfg["categories"], "updated_at": cfg["updated_at"]}


def require_design(token: str) -> None:
    if not theme_service.check_token(token):
        raise HTTPException(status_code=401, detail="外觀後台密碼不正確")


@app.post("/api/design/login")
def design_login(payload: dict = Body(default={})):
    token = str(payload.get("token", ""))
    require_design(token)
    return {"ok": True}


@app.get("/api/design/config")
def design_config_get(x_design_token: str = Header(default="")):
    require_design(x_design_token)
    cfg = theme_service.load_config()
    return {"config": cfg, "theme_fields": theme_service.theme_fields(),
            "text_fields": theme_service.text_fields(),
            "asset_fields": theme_service.asset_fields(),
            "css_override": theme_service.css_override_exists()}


@app.put("/api/design/config")
def design_config_save(payload: dict = Body(default={}), x_design_token: str = Header(default="")):
    require_design(x_design_token)
    cfg = theme_service.save_config(payload)
    logger.info("更新前台外觀設定 updated_at=%s", cfg["updated_at"])
    return {"config": cfg}


@app.post("/api/design/preview.css")
def design_preview_css(payload: dict = Body(default={}), x_design_token: str = Header(default="")):
    """後台即時預覽用：依傳入的設定產生 CSS，但不寫入檔案。"""
    require_design(x_design_token)
    cfg = theme_service.load_config()
    if isinstance(payload.get("theme"), dict):
        cfg["theme"] = theme_service.clean_theme(payload["theme"])
    if "custom_css" in payload:
        cfg["custom_css"] = str(payload["custom_css"] or "")[:20000]
    return Response(content=theme_service.build_css(cfg), media_type="text/css")


@app.get("/api/design/css")
def design_css_list(x_design_token: str = Header(default="")):
    require_design(x_design_token)
    return {"files": theme_service.list_css_files()}


@app.get("/api/design/css/{name}")
def design_css_get(name: str, x_design_token: str = Header(default="")):
    require_design(x_design_token)
    try:
        return theme_service.read_css_file(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/design/css/{name}")
def design_css_save(name: str, payload: dict = Body(default={}), x_design_token: str = Header(default="")):
    require_design(x_design_token)
    try:
        info = theme_service.write_css_file(name, payload.get("content", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("直接編輯原始樣式檔 file=%s bytes=%d", name, info["bytes"])
    return info


@app.post("/api/design/css/{name}/restore")
def design_css_restore(name: str, x_design_token: str = Header(default="")):
    require_design(x_design_token)
    try:
        info = theme_service.restore_css_file(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("還原原始樣式檔 file=%s", name)
    return info


@app.post("/api/design/asset/{kind}")
async def design_asset_upload(kind: str, file: UploadFile = File(...),
                              x_design_token: str = Header(default="")):
    """上傳 Logo 或頁面背景圖。"""
    require_design(x_design_token)
    data = await file.read()
    try:
        cfg = theme_service.save_asset(kind, file.filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("更新前台圖片 kind=%s bytes=%d", kind, len(data))
    return {"config": cfg}


@app.delete("/api/design/asset/{kind}")
def design_asset_delete(kind: str, x_design_token: str = Header(default="")):
    require_design(x_design_token)
    try:
        cfg = theme_service.clear_asset(kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("移除前台圖片 kind=%s", kind)
    return {"config": cfg}


@app.post("/api/design/reset")
def design_config_reset(x_design_token: str = Header(default="")):
    require_design(x_design_token)
    logger.info("前台外觀設定已還原為預設")
    return {"config": theme_service.reset_config()}


def require_admin(token: str) -> None:
    expected = os.getenv("FAQ_ADMIN_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="管理密碼不正確")


def _token_aliases() -> dict:
    """舊登入碼對照表：處室改組前寄出的通知信仍附著舊碼，讓它們繼續能登入。

    格式 {舊碼: {"primary": 主要處室, "offices": [看得到的處室…]}}，檔案不存在就代表沒有舊碼。
    """
    path = PROJECT_ROOT / "office-token-aliases.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def require_office_scope(token: str) -> tuple[str, str, list[str]]:
    """回傳 (主要處室, 系所, 看得到的處室清單)。

    系所登入碼只看得到分派給該系所的詢問單（不分承辦窗口）；
    舊的處室登入碼（例如改組前的教務處註冊課務組）沿用為總窗口，看得到改組後的各窗口。
    """
    department = department_by_token(token)
    if department:
        return department_office(department) or DEPARTMENT_FALLBACK_OFFICE, department, []
    path = PROJECT_ROOT / "office-tokens.json"
    if not path.exists(): raise HTTPException(status_code=503, detail="尚未設定處室帳號")
    # 別名要先比對：教務處總窗口的碼同時也在 office-tokens.json 裡，先走這裡才拿得到跨窗口視野
    alias = _token_aliases().get(token or "")
    if isinstance(alias, dict) and alias.get("primary"):
        offices = [x for x in alias.get("offices") or [] if x] or [alias["primary"]]
        return str(alias["primary"]), "", offices
    tokens = json.loads(path.read_text(encoding="utf-8-sig"))
    for office, saved in tokens.items():
        if token and token == saved: return office, "", [office]
    raise HTTPException(status_code=401, detail="登入碼不正確")


def require_office(token: str) -> str:
    return require_office_scope(token)[0]


@app.get("/health")
@app.get("/api/health")
def health():
    try:
        check_connection()
        info = collection_info()
        return {
            "status": "ok",
            "qdrant": "connected",
            "collection": COLLECTION_NAME,
            "points": info.points_count or 0,
            "faqs_indexed": (info.points_count or 0) // 2,  # 每題兩個向量：整段＋題目
            "llm": {key: value for key, value in ollama_status().items() if key != "model"},
        }
    except Exception as exc:
        logger.exception("健康檢查失敗")
        raise HTTPException(status_code=503, detail=f"Qdrant 或 Collection 無法使用：{exc}") from exc


@app.get("/api/categories")
def categories(limit: int = 8):
    """側欄分類與每類的代表問題，供前端點選分類後直接列出問題。"""
    try:
        return {"categories": faq_categories(max(1, min(limit, 20)))}
    except Exception as exc:
        logger.exception("讀取 FAQ 分類失敗")
        raise HTTPException(status_code=503, detail=f"無法讀取 FAQ 分類：{exc}") from exc


@app.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest):
    started = time.perf_counter()
    try:
        results = search_faq(embed_text(request.query), request.limit)
        logger.info("搜尋完成 query_length=%d results=%d duration_ms=%.1f", len(request.query), len(results), (time.perf_counter() - started) * 1000)
        return {"query": request.query, "results": results}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("搜尋失敗")
        raise HTTPException(status_code=503, detail=f"搜尋服務暫時無法使用：{exc}") from exc


@app.post("/api/ask", response_model=AnswerResponse)
def ask(request: SearchRequest):
    started = time.perf_counter()
    try:
        results = search_faq(embed_text(request.query), max(request.limit, 5))
        # 向量搜尋只看字面相似（「借教室」會配到「就學貸款」），先讓模型確認來源真的在回答這個問題
        relevant = filter_relevant(request.query, results)
        if relevant is not None and len(relevant) != len(results):
            logger.info("相關性檢查 query=%r 保留 %d/%d 筆", request.query, len(relevant), len(results))
            results = relevant
        log_query(request.query, results)
        if not results:
            return {"query": request.query, "answer": site_text("ai_no_info"), "results": [], "generated": False, "model": "", "notice": "未找到相關 FAQ", "followups": [], "steps": []}
        top = results[0]
        if float(top.get("score") or 0) >= DIRECT_ANSWER_SCORE and str(top.get("answer") or "").strip():
            # 幾乎完全命中：直接給 FAQ 原文，前台會標示「FAQ 原文」
            logger.info("命中 FAQ 原文 query=%r score=%.3f", request.query, float(top.get("score") or 0))
            return {"query": request.query, "answer": str(top["answer"]).strip(), "results": results[:3],
                    "generated": False, "model": "", "notice": "",
                    "followups": [q for q in (str(x.get("question", "")).strip() for x in results[1:])
                                  if q and q != request.query][:3],
                    "steps": []}
        try:
            answer = answer_from_faq(request.query, results[:5])
            generated, notice = True, ""
        except Exception as llm_exc:
            logger.warning("地端模型回答失敗，改用 FAQ 原文：%s", llm_exc)
            answer = results[0].get("answer", "目前無法產生回答。")
            generated, notice = False, "地端模型暫時無法使用，已顯示最相關的 FAQ 原文。"
        logger.info("問答完成 query_length=%d generated=%s duration_ms=%.1f", len(request.query), generated, (time.perf_counter() - started) * 1000)
        followups = []
        for item in results[1:]:
            question = str(item.get("question", "")).strip()
            if question and question != request.query and question not in followups:
                followups.append(question)
            if len(followups) == 3:
                break
        steps = [part.strip(" -•\t") for part in answer.splitlines() if part.strip()]
        if len(steps) < 2:
            steps = []
        return {"query": request.query, "answer": answer, "results": results[:3], "generated": generated, "model": "", "notice": notice, "followups": followups, "steps": steps[:6]}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("問答失敗")
        raise HTTPException(status_code=503, detail=f"問答服務暫時無法使用：{exc}") from exc


@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback(request: FeedbackRequest):
    log_feedback(request.query.strip(), request.source_question.strip(), request.helpful)
    return {"saved": True}


def _notify_ticket(ticket: dict) -> None:
    sent, detail = send_ticket_email(ticket)
    record_ticket_email(ticket["ticket_no"], sent, detail)


def _notify_requester_ack(ticket: dict) -> None:
    """系所相關問題：回一封「已收到、已分派」確認信給提問者。"""
    sent, detail = send_ticket_ack_email(ticket)
    record_ack_email(ticket["ticket_no"], sent, detail)


def _notify_student_resolution(ticket: dict) -> None:
    sent, detail, recipient = send_student_resolution_email(ticket)
    record_student_email(ticket["ticket_no"], sent, detail, recipient)


def _sync_ticket_knowledge(ticket: dict) -> None:
    try:
        record = sync_resolved_ticket(ticket)
        record_knowledge_sync(ticket["ticket_no"], True, record["id"])
    except Exception as exc:
        logger.exception("詢問單寫入知識庫失敗 ticket=%s", ticket.get("ticket_no"))
        record_knowledge_sync(ticket["ticket_no"], False, f"{type(exc).__name__}: {exc}")


@app.get("/api/mail/status")
@app.get("/api/admin/mail/settings")
def email_status(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return mail_status()


@app.put("/api/admin/mail/settings")
def email_settings_save(request: MailSettingsRequest, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    data = request.model_dump()
    password = data.pop("password", "")
    offices = data.pop("offices", {})
    departments = data.pop("departments", {})
    recipients = []
    for email in data.get("student_recipients", []):
        email = email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise HTTPException(status_code=422, detail=f"學生通知信箱格式不正確：{email or '空白'}")
        if email not in recipients:
            recipients.append(email)
    data["student_recipients"] = recipients or [mail_status()["default_email"]]
    save_settings(data)
    if password.strip():
        save_password(password)
    if offices:
        save_office_emails(offices)
    if departments:
        try:
            save_departments(departments)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    logger.info("更新詢問單通知信箱設定 offices=%d departments=%d", len(offices), len(departments))
    return mail_status()


@app.get("/api/admin/departments")
def departments_get(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return load_departments()


@app.get("/api/admin/departments/stats")
def departments_stats(x_admin_token: str = Header(default="")):
    """各系所被分派到的詢問單筆數；系所問題統一寄到教務處信箱。"""
    require_admin(x_admin_token)
    stats = department_stats()
    stats["recipient"] = department_recipient()
    return stats


@app.get("/api/admin/departments/defaults")
def departments_defaults(x_admin_token: str = Header(default="")):
    """後台「關鍵字回復預設」用；回官網原始信箱與內建關鍵字。"""
    require_admin(x_admin_token)
    return DEPARTMENT_DEFAULTS


@app.post("/api/admin/mail/test")
def email_test(request: MailTestRequest, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    sent, detail = send_test_email(request.to)
    if not sent:
        raise HTTPException(status_code=502, detail=f"測試信寄送失敗：{detail}")
    return {"sent": True, "to": detail}


@app.post("/api/admin/tickets/{ticket_no}/resend-mail")
def ticket_resend_mail(ticket_no: str, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    ticket = ticket_detail(ticket_no)
    if not ticket:
        raise HTTPException(status_code=404, detail="找不到詢問單")
    sent, detail = send_ticket_email(ticket)
    record_ticket_email(ticket_no, sent, detail)
    if not sent:
        raise HTTPException(status_code=502, detail=f"通知信寄送失敗：{detail}")
    return {"sent": True, "to": detail}


@app.post("/api/tickets", status_code=201)
def ticket_create(request: TicketCreateRequest, background_tasks: BackgroundTasks):
    data = request.model_dump()
    if not data["office"]:
        data["office"], data["department"] = route_ticket(data["query"], data["description"])
    else:
        # 前台已指定處室時只補系所，不重跑 AI 分流
        matched = match_department(f"{data['query']} {data['description']}")
        data["department"] = matched if matched and department_office(matched) == data["office"] else ""
    ticket = create_ticket(data)
    background_tasks.add_task(_notify_ticket, ticket)
    if ticket.get("department"):
        background_tasks.add_task(_notify_requester_ack, ticket)
    return ticket


@app.get("/api/tickets/{ticket_no}")
def ticket_public_get(ticket_no: str, key: str):
    ticket = public_ticket(ticket_no, key)
    if not ticket: raise HTTPException(status_code=404, detail="找不到詢問單或存取碼不正確")
    return ticket


@app.post("/api/tickets/{ticket_no}/replies")
def ticket_public_reply(ticket_no: str, request: TicketReplyRequest):
    ticket = add_ticket_reply(ticket_no, request.access_key, request.message, request.allow_faq)
    if not ticket: raise HTTPException(status_code=404, detail="找不到詢問單或存取碼不正確")
    return ticket


@app.post("/api/tickets/{ticket_no}/rating")
def ticket_public_rate(ticket_no: str, request: TicketRateRequest):
    try:
        ticket = rate_ticket(ticket_no, request.access_key, request.rating, request.comment)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not ticket: raise HTTPException(status_code=404, detail="找不到詢問單或存取碼不正確")
    logger.info("提問單評分 ticket=%s rating=%d", ticket_no, request.rating)
    return ticket


@app.get("/api/admin/tickets")
def tickets_get(status: str = "", office: str = "", settled: str = "", x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return {"tickets": list_tickets(status, office, settled=settled)}


def scoped_tickets(offices: list[str], department: str, status: str = "", settled: str = "") -> list[dict]:
    """系所登入看「分派給該系所」的全部詢問單，不綁承辦窗口。

    教務處拆成九個窗口後，同一個系所的問題可能落在不同窗口（選課題→課程與選課、
    學籍題→學籍與註冊），再用處室一起篩就會查不到自己的單。
    處室登入維持原本的行為：看該處室的全部詢問單。
    """
    if department:
        return list_tickets(status, "", department, settled=settled)
    return list_tickets(status, offices, "", settled=settled)


@app.get("/api/office/tickets")
def office_tickets(status: str = "", settled: str = "", x_office_token: str = Header(default="")):
    """settled=0 代表不含已銷案（處室清單預設值），空字串代表全部。"""
    office, department, offices = require_office_scope(x_office_token)
    return {"office": office, "department": department, "unit": department or office,
            "tickets": scoped_tickets(offices, department, status, settled)}


@app.get("/api/office/mail")
def office_mail_get(x_office_token: str = Header(default="")):
    office, department, offices = require_office_scope(x_office_token)
    info = mail_status()
    email = (info["departments"].get(department, {}).get("email") if department
             else info["offices"].get(office)) or info["default_email"]
    return {"office": office, "department": department, "unit": department or office, "email": email,
            "default_email": info["default_email"], "mail_enabled": info["configured"]}


@app.put("/api/office/mail")
def office_mail_save(request: OfficeMailRequest, x_office_token: str = Header(default="")):
    office, department, offices = require_office_scope(x_office_token)
    email = request.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="請輸入有效的電子郵件地址")
    if department:
        save_departments({department: {"email": email}})
    else:
        save_office_emails({office: email})
    logger.info("處室自行更新詢問單通知信箱 office=%s department=%s", office, department or "-")
    return {"saved": True, "office": office, "department": department,
            "unit": department or office, "email": email}


@app.get("/api/office/tickets/{ticket_no}")
def office_ticket_get(ticket_no: str, x_office_token: str = Header(default="")):
    office, department, offices = require_office_scope(x_office_token)
    rows = [x for x in scoped_tickets(offices, department) if x["ticket_no"] == ticket_no]
    if not rows: raise HTTPException(status_code=404, detail="找不到分派給本處室的詢問單")
    return ticket_detail(ticket_no)


@app.patch("/api/office/tickets/{ticket_no}")
def office_ticket_update(ticket_no: str, request: TicketUpdateRequest, background_tasks: BackgroundTasks,
                         x_office_token: str = Header(default="")):
    office, department, offices = require_office_scope(x_office_token)
    rows = [x for x in scoped_tickets(offices, department) if x["ticket_no"] == ticket_no]
    if not rows: raise HTTPException(status_code=404, detail="找不到分派給本處室的詢問單")
    previous_office = rows[0]["office"]
    data = request.model_dump()
    ticket = update_ticket(ticket_no, data)
    if ticket and ticket["office"] != previous_office:
        background_tasks.add_task(_notify_ticket, ticket)
    if ticket and ticket["status"] == "已解決" and rows[0]["status"] != "已解決":
        background_tasks.add_task(_notify_student_resolution, ticket)
        background_tasks.add_task(_sync_ticket_knowledge, ticket)
    return ticket


@app.patch("/api/admin/tickets/{ticket_no}")
def ticket_update(ticket_no: str, request: TicketUpdateRequest, background_tasks: BackgroundTasks,
                  x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    previous = ticket_detail(ticket_no)
    ticket = update_ticket(ticket_no, request.model_dump())
    if not ticket:
        raise HTTPException(status_code=404, detail="找不到詢問單")
    if previous and ticket["office"] != previous["office"]:
        background_tasks.add_task(_notify_ticket, ticket)
    if previous and ticket["status"] == "已解決" and previous["status"] != "已解決":
        background_tasks.add_task(_notify_student_resolution, ticket)
        background_tasks.add_task(_sync_ticket_knowledge, ticket)
    return ticket


@app.post("/api/admin/tickets/{ticket_no}/settle")
def ticket_settle_admin(ticket_no: str, request: TicketSettleRequest, x_admin_token: str = Header(default="")):
    """管理者標記／取消銷案；銷案不會刪除詢問單。"""
    require_admin(x_admin_token)
    ticket = set_ticket_settled(ticket_no, request.settled, request.actor or "管理者", request.note)
    if not ticket:
        raise HTTPException(status_code=404, detail="找不到詢問單")
    logger.info("詢問單銷案 ticket=%s settled=%s", ticket_no, request.settled)
    return ticket


@app.post("/api/office/tickets/{ticket_no}/settle")
def ticket_settle_office(ticket_no: str, request: TicketSettleRequest, x_office_token: str = Header(default="")):
    office, department, offices = require_office_scope(x_office_token)
    rows = [x for x in scoped_tickets(offices, department) if x["ticket_no"] == ticket_no]
    if not rows:
        raise HTTPException(status_code=404, detail="找不到分派給本單位的詢問單")
    ticket = set_ticket_settled(ticket_no, request.settled, request.actor or (department or office), request.note)
    if not ticket:
        raise HTTPException(status_code=404, detail="找不到詢問單")
    return ticket


@app.get("/api/admin/settle/stats")
def settle_statistics(days: int = 0, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return settle_stats(days)


@app.delete("/api/admin/tickets/{ticket_no}")
def ticket_delete(ticket_no: str, x_admin_token: str = Header(default="")):
    """永久刪除詢問單；問題、回覆、Email 與事件紀錄一併移除，無法復原。"""
    require_admin(x_admin_token)
    if not delete_ticket(ticket_no):
        raise HTTPException(status_code=404, detail="找不到詢問單")
    return {"deleted": True, "ticket_no": ticket_no}


@app.post("/api/admin/knowledge/sync-resolved")
def knowledge_sync_resolved(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    saved, failed = [], []
    for summary in list_tickets(status="已解決"):
        ticket = ticket_detail(summary["ticket_no"])
        try:
            record = sync_resolved_ticket(ticket)
            record_knowledge_sync(ticket["ticket_no"], True, record["id"])
            saved.append(ticket["ticket_no"])
        except Exception as exc:
            record_knowledge_sync(ticket["ticket_no"], False, f"{type(exc).__name__}: {exc}")
            failed.append({"ticket_no": ticket["ticket_no"], "error": str(exc)})
    return {"saved": saved, "failed": failed}


@app.get("/api/admin/tickets.csv")
def tickets_csv(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    rows = list_tickets()
    output = io.StringIO()
    fields = ["ticket_no","status","office","category","subject","description","requester_name","requester_contact","student_email_to","student_email_status","student_email_error","assignee","resolution","rating","rating_comment","rated_at","created_at","updated_at","resolved_at"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader(); writer.writerows(rows)
    data = "\ufeff" + output.getvalue()
    return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=tickets.csv"})


@app.get("/api/admin/stats")
def admin_stats(days: int = 7, x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return stats(days)


# ---------------------------------------------------------------- 常見問題（FAQ）後台

def official_offices() -> list[str]:
    """正式處室名稱＝有專屬登入碼的單位，FAQ 只能轉移給這些單位。"""
    path = PROJECT_ROOT / "office-tokens.json"
    try:
        return sorted(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        return []


def faq_editor_token() -> str:
    """各處室共用的常見問題編輯密碼（faq-editor-token.txt）；檔案不存在就代表不開放共用登入。"""
    try:
        return (PROJECT_ROOT / "faq-editor-token.txt").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def require_faq_access(admin_token: str, office_token: str,
                       editor_office: str = "") -> tuple[list[str] | None, str, str, str]:
    """常見問題後台的登入，回傳 (可管理的單位清單，None 代表全部, 主要單位, 寫進更新內容的編輯者名稱, 角色)。

    - 管理密碼（admin）：全部功能。
    - 共用編輯密碼（editor）：各處室共用，可以編輯、轉移所有題目，但不能匯入或重建向量；
      登入後自選的「我的單位」由 X-Editor-Office 帶來，只用來記錄是誰改的。
    - 處室登入碼（office）：只看得到、改得到自己單位的題目。
    """
    if admin_token:
        shared = faq_editor_token()
        if shared and admin_token == shared:
            office = unquote(editor_office or "").strip()
            office = office if office in official_offices() else ""
            return None, office, f"共用編輯（{office}）" if office else "共用編輯", "editor"
        require_admin(admin_token)
        return None, "", "後台", "admin"
    if not office_token:
        raise HTTPException(status_code=401, detail="請輸入管理密碼或處室登入碼")
    if department_by_token(office_token):
        raise HTTPException(status_code=403, detail="系所登入碼無法管理常見問題，請改用處室登入碼")
    office, _, offices = require_office_scope(office_token)
    return offices or [office], office, f"處室後台（{office}）", "office"


def suggest_office(row: dict, offices: list[str]) -> str:
    """主責單位不是正式名稱時（例如舊資料只寫「教務處」），依題目內容建議該轉給哪個窗口。"""
    if row.get("office") in offices:
        return ""
    exact = normalize_office(row.get("office", ""), offices)
    if exact:
        return exact
    scored = [name for name, _ in score_offices(" ".join((row.get("category", ""), row.get("question", ""),
                                                          row.get("office", "")))) if name in offices]
    return scored[0] if scored else ""


def _own_faq(faq_id: str, scope: list[str] | None) -> dict:
    row = next((x for x in faq_service.list_faqs() if x["id"] == faq_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"找不到問題編號 {faq_id}")
    if scope is not None and row["office"] not in scope:
        raise HTTPException(status_code=403, detail="這題不屬於您的單位，無法修改")
    return row


@app.get("/api/admin/faqs")
def faqs_list(x_admin_token: str = Header(default=""), x_office_token: str = Header(default=""),
              x_editor_office: str = Header(default="")):
    scope, office, _, role = require_faq_access(x_admin_token, x_office_token, x_editor_office)
    offices = official_offices()
    rows = faq_service.list_faqs()
    if scope is None:
        rows = [{**row, "suggest": suggest_office(row, offices)} for row in rows]
    else:
        rows = [row for row in rows if row["office"] in scope]
    return {"faqs": rows, "summary": faq_service.summary(rows), "fields": faq_service.FIELDS,
            "scope": {"role": role, "office": office,
                      "offices": scope or [], "all_offices": offices}}


@app.post("/api/admin/faqs", status_code=201)
def faq_create(request: FaqUpsertRequest, x_admin_token: str = Header(default=""),
               x_office_token: str = Header(default=""), x_editor_office: str = Header(default="")):
    scope, office, editor, _ = require_faq_access(x_admin_token, x_office_token, x_editor_office)
    record = request.model_dump()
    if scope is not None:
        record["office"] = record["office"] or office
        if record["office"] not in scope:
            raise HTTPException(status_code=403, detail="只能新增本單位的題目；要交給其他單位，請先新增再用「轉移」")
    try:
        faq = faq_service.save_faq(record, editor=editor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("FAQ 新增 id=%s by=%s", faq["id"], editor)
    return {"faq": faq}


@app.put("/api/admin/faqs/{faq_id}")
def faq_update(faq_id: str, request: FaqUpsertRequest, x_admin_token: str = Header(default=""),
               x_office_token: str = Header(default=""), x_editor_office: str = Header(default="")):
    scope, _, editor, _ = require_faq_access(x_admin_token, x_office_token, x_editor_office)
    record = request.model_dump()
    if scope is not None:
        _own_faq(faq_id, scope)
        # 處室在編輯畫面把主責單位改成別的正式單位，就等於轉移；不能改成自創的名稱
        if record["office"] not in scope and record["office"] not in official_offices():
            raise HTTPException(status_code=400, detail="主責單位請從清單選擇正式單位名稱")
    try:
        faq = faq_service.save_faq(record, original_id=faq_id, editor=editor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("FAQ 更新 id=%s by=%s", faq["id"], editor)
    return {"faq": faq}


@app.post("/api/admin/faqs/transfer")
def faq_transfer(request: FaqTransferRequest, x_admin_token: str = Header(default=""),
                 x_office_token: str = Header(default=""), x_editor_office: str = Header(default="")):
    """把勾選的題目整批交給另一個單位（改主責單位），處室只能轉出自己單位的題目。"""
    scope, _, editor, _ = require_faq_access(x_admin_token, x_office_token, x_editor_office)
    if request.office not in official_offices():
        raise HTTPException(status_code=400, detail="請從清單選擇要轉移到的正式單位")
    try:
        backup = faq_service.backup_csv()
        changed = faq_service.transfer_faqs(request.ids, request.office, editor=editor, allowed=scope)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("FAQ 轉移 %d 筆 → %s by=%s", len(changed), request.office, editor)
    return {"moved": len(changed), "office": request.office, "backup": backup}


@app.delete("/api/admin/faqs/{faq_id}")
def faq_delete(faq_id: str, x_admin_token: str = Header(default=""), x_office_token: str = Header(default=""),
               x_editor_office: str = Header(default="")):
    scope, _, editor, _ = require_faq_access(x_admin_token, x_office_token, x_editor_office)
    if scope is not None:
        _own_faq(faq_id, scope)
    try:
        faq_service.backup_csv()
        result = faq_service.delete_faq(faq_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info("FAQ 刪除 id=%s by=%s", faq_id, editor)
    return result


@app.post("/api/admin/faqs/preview")
async def faq_import_preview(file: UploadFile | None = File(default=None), url: str = Form(default=""),
                             text: str = Form(default=""), x_admin_token: str = Header(default="")):
    """讀取試算表／檔案／貼上的內容，只做解析與比對，不寫入任何資料。"""
    require_admin(x_admin_token)
    try:
        if file is not None and file.filename:
            table, source = faq_service.parse_upload(await file.read(), file.filename), file.filename
        elif url.strip():
            table, source = faq_service.fetch_source(url), "Google 試算表"
        elif text.strip():
            table, source = faq_service.parse_text(text), "貼上的內容"
        else:
            raise ValueError("請選擇檔案、輸入試算表網址，或貼上資料")
        records, header = faq_service.map_table(table)
        plan = faq_service.plan_import(records)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("FAQ 匯入預覽失敗")
        raise HTTPException(status_code=500, detail=f"讀取失敗：{exc}") from exc
    logger.info("FAQ 匯入預覽 source=%s rows=%d", source, len(plan["rows"]))
    return {"source": source, "header": header, **plan}


@app.post("/api/admin/faqs/import")
def faq_import(request: FaqImportRequest, x_admin_token: str = Header(default="")):
    """把預覽確認過的資料寫入 faq.csv 並重新產生向量，前台立即生效。"""
    require_admin(x_admin_token)
    try:
        result = faq_service.apply_import(request.rows, request.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("FAQ 匯入失敗")
        raise HTTPException(status_code=500, detail=f"匯入失敗：{exc}") from exc
    logger.info("FAQ 匯入完成 mode=%s created=%d updated=%d", result["mode"], result["created"], result["updated"])
    return result


@app.post("/api/admin/faqs/reindex")
def faq_reindex(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    try:
        indexed = faq_service.reindex()
    except Exception as exc:
        logger.exception("FAQ 重建向量失敗")
        raise HTTPException(status_code=500, detail=f"重建失敗：{exc}") from exc
    logger.info("FAQ 向量重建完成 count=%d", indexed)
    return {"indexed": indexed}


@app.get("/api/admin/faqs.csv")
def faqs_csv(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return StreamingResponse(iter([faq_service.export_csv()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=faq.csv"})


@app.get("/api/admin/faqs/template.csv")
def faqs_template_csv(x_admin_token: str = Header(default="")):
    require_admin(x_admin_token)
    return StreamingResponse(iter([faq_service.template_csv()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=faq-template.csv"})
