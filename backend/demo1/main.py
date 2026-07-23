# Load .env BEFORE any backend.demo1 imports!
from dotenv import load_dotenv
load_dotenv()
from backend.demo1.ocr_intake import init_intake_table, router as intake_router
from backend.demo1.intake_jobs import init_intake_jobs_table, router as intake_jobs_router
from backend.demo1.fine_tune import init_model_table
# pytorch_trainer and lora_trainer are imported lazily inside endpoints
# to avoid pulling in torch/mlflow at server startup (keeps CI fast)
from backend.demo1.slack_teams import init_notify_table, router as notify_router
from backend.demo1.auth import init_auth_table, router as auth_router
from backend.demo1.custom_entities import init_custom_entity_table, router as custom_entities_router
from backend.demo1.webhook import init_webhook_table, router as webhook_router
from backend.demo1.pdf_export import router as pdf_router
from backend.demo1.pdf_module_export import router as module_pdf_router
from backend.demo1.audit_trail import AuditMiddleware, init_audit_table, router as audit_router
from backend.demo1.rate_limit import check_rate_limit
from backend.demo1.observability.tracer import trace_claude_call
from backend.demo1.mlops.tracker import log_inference as _mlflow_log
from backend.demo1.pii import redact_text as _pii_redact, redaction_summary as _pii_summary
from backend.demo1.case_management   import router as cases_router
from backend.demo1.matter_exports import router as matter_export_router
from backend.demo1.redaction import router as redaction_router, init_redaction_table
from backend.demo1.media_transcription import init_transcription_table
from backend.demo1.message_parser import router as messages_router, init_messages_table
from backend.demo1.email_router import router as email_router
from backend.demo1.multilingual import analyze_multilingual, detect_language, SUPPORTED_LANGUAGES
from backend.demo1.summary_scorer import score_summary
from backend.demo1.entity_confidence import score_entities, get_entity_summary
from backend.demo1.entity_linker import find_linked_entities, link_documents_by_entity
from backend.demo1.calendar_sync import router as calendar_sync_router
from backend.demo1.document_annotations import router as document_annotations_router
from backend.demo1.esignature import router as esign_router
from backend.demo1.client_portal import router as client_portal_router
from backend.demo1.acp_vcf_config import APP_NAME, FIRM_NAME, FIRM_ID, VCF_DEADLINES
from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from backend.demo1.database import (
    init_db, save_analysis, query_analyses, get_stats,
    save_feedback, get_feedback_queue, mark_reviewed, get_retraining_data
)
import anthropic
from backend.demo1.intelligence import get_deadline_radar
from backend.demo1.vcf_deadlines import router as vcf_deadlines_router
from backend.demo1.vcf_disbursements import router as vcf_disbursements_router
from backend.demo1.vcf_account import router as vcf_account_router, init_vcf_account_table
from backend.demo1.vcf_workflow import router as vcf_workflow_router
from backend.demo1.communications import router as communications_router
from backend.demo1.vcf_reports import router as vcf_reports_router
import os
import json
import logging
import re
import csv
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional




# NOW import from your backend
from backend.demo1.pg import init_pool, make_tenant_middleware

import jwt
import psycopg2
from backend.demo1.enclave_router import router as enclave_privilege_router

logger = logging.getLogger(__name__)

from backend.demo1.db_enclaves import init_enclave_tables
from backend.demo1.routers.correspondence_router import router as correspondence_router
# from backend.demo1.routers.webauthn_router import router as webauthn_router
from backend.demo1.routers.feedback_router        import router as feedback_router
from backend.demo1.routers.summary_router         import router as summary_router
from backend.demo1.routers.nlp_router             import router as nlp_router
from backend.demo1.routers.calendar_router       import router as calendar_router
from backend.demo1.routers.contacts_router       import router as contacts_router
from backend.demo1.routers.chat_router            import router as chat_router
from backend.demo1.routers.monitor_router         import router as monitor_router
# from backend.demo1.risk_watcher                   import start_scheduler
from backend.demo1.routers.reports_router        import router as reports_router
from backend.demo1.routers.misc_routers import (
    exports_router, ai_config_router,
)  # client_portal_router removed: canonical version imported from client_portal.py (line ~44); duplicate import here shadowed it, leaving the full portal unmounted
from backend.demo1.kanban_router import router as kanban_router
from backend.demo1.routers.approval_router import router as approval_router
from backend.demo1.notifications_router import router as notifications_router

# ── Phase 1: AI Infrastructure Modules ─────────────────────────────────────────
from backend.demo1.ai_time_capture import suggest_time_entries
from backend.demo1.ai_summarization import summarize_text
from backend.demo1.security_headers import SecurityHeadersMiddleware, init_security_headers
from backend.demo1.prompt_guard import init_guard_table, guard_prompt, build_safe_messages, log_guard_event
from backend.demo1.ai_isolation import (
    init_isolation_tables, get_tenant_config, get_tenant_client,
    resolve_system_prompt, check_token_budget, get_token_usage,
    update_tenant_config, invalidate_config_cache,
)
from backend.demo1.ai_output_validation import init_validation_tables
from backend.demo1.model_router import (
    init_model_router as init_ai_model_router,
    call_llm, call_llm_async, get_routing_status, get_cost_report,
    get_recent_requests as get_recent_ai_requests, TaskType,
)



# ── API Key Auth Middleware ───────────────────────────────────────────────────

PARAIQ_API_KEY = os.getenv("PARAIQ_API_KEY", "")
if not PARAIQ_API_KEY:
    raise SystemExit("FATAL: PARAIQ_API_KEY is not set. Refusing to start with open API.")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY:
    raise SystemExit("FATAL: JWT_SECRET_KEY is not set. Refusing to start.")


def save_work_product(endpoint: str, result: dict, firm_id: str, case_id=None, user_id=None, input_preview: str = ""):
    """Persist AI work product to ai_work_product table. Non-fatal on failure."""
    try:
        from backend.demo1.pg import get_conn
        import json as _json
        with get_conn(firm_id) as conn:
            conn.execute(
                """INSERT INTO ai_work_product (firm_id, case_id, user_id, endpoint, input_preview, result_json)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (firm_id, case_id, user_id, endpoint, input_preview[:500], _json.dumps(result))
            )
            conn.commit()
    except (psycopg2.Error, KeyError, ValueError) as _e:
        import logging
        logging.warning(f"save_work_product failed for {endpoint}: {_e}")



EXEMPT_PATHS = {"/health", "/openapi.json", "/docs", "/redoc", "/favicon.ico", "/metrics"}
EXEMPT_PREFIXES = (
    "/auth/", "/api/auth/", "/docs/", "/redoc/", "/esign/sign/",
    # Client-portal public token-gated routes -- auth is the token itself,
    # verified inside _lookup_access(), not a JWT. Deliberately NOT exempting
    # the bare "/client-portal/" prefix: that would also open /grant, /grants,
    # /revoke/, /access/, /matter/, which are firm-JWT-gated and must stay
    # behind this middleware.
    "/client-portal/view/",
    "/client-portal/cases/",
    "/client-portal/upload/",
    "/client-portal/documents/",
    "/client-portal/message/",
    "/client-portal/messages/",
)
STATIC_EXTS = (".html", ".js", ".css", ".ico", ".png", ".svg", ".woff", ".woff2")
# Internal machine-to-machine paths: static key valid ONLY here, ONLY from localhost.
M2M_PREFIXES = ("/intake/scan", "/discovery/process/ocr/", "/media/transcribe/discovery/")

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        # Production frontend is built with baseURL '/api' (mirrors nginx rewrite).
        # Strip the prefix here so all auth/path checks and routing see root paths.
        path = request.url.path
        if path.startswith("/api/"):
            path = path[4:]
            request.scope["path"] = path
        # Allow exempt paths, static assets, and browser navigation (SPA HTML loads)
        ext = os.path.splitext(path)[1].lower()
        accepts_html = request.method == "GET" and "text/html" in request.headers.get("Accept", "")
        if (
            path in EXEMPT_PATHS
            or any(path.startswith(p) for p in EXEMPT_PREFIXES)
            or ext in STATIC_EXTS
            or accepts_html
        ):
            return await call_next(request)
                # Check key OR valid Bearer JWT
        key = request.headers.get("X-API-Key", "")
        auth = request.headers.get("Authorization", "")
        
        # If no auth header, check for token in query string (for file downloads)
        if not auth and request.query_params.get("token"):
            auth = "Bearer " + request.query_params.get("token")
        has_bearer = False
        if auth.startswith("Bearer "):
            try:
                import jwt as _jwt
                _jwt.decode(auth[7:], os.getenv("JWT_SECRET_KEY", ""), algorithms=["HS256"])
                has_bearer = True
            except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, KeyError, ValueError) as e:
                logger.debug(f"[main] JWT decode failed: {e}")
                has_bearer = False
        # JWT is the only browser-facing auth. The static key works solely for
        # internal localhost self-calls (no X-Forwarded-For == not via Nginx/tunnel).
        is_internal = ("x-forwarded-for" not in request.headers and "x-real-ip" not in request.headers)
        key_ok = (
            bool(PARAIQ_API_KEY)
            and key == PARAIQ_API_KEY
            and is_internal
            and any(path.startswith(p) for p in M2M_PREFIXES)
        )
        if not (has_bearer or key_ok):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"}
            )
        request.state.client_id = request.headers.get("X-Client-ID", "")
        return await call_next(request)

from backend.demo1.routers.workflows_router import router as workflows_router
from backend.demo1.auth import require_admin as _require_admin
from backend.demo1.auth import get_current_user as _get_current_user

app = FastAPI(
    title=APP_NAME,
    swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
)

# Force single tenant for WAW VCF + Robust Error Handling
@app.middleware("http")
async def force_waw_tenant(request: Request, call_next):
    try:
        request.state.firm_id = FIRM_ID
        request.state.tenant_config = {"name": FIRM_NAME, "app": APP_NAME}
        response = await call_next(request)
        return response
    except Exception as exc:
        print("[Middleware] UNCAUGHT ERROR")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error in tenant configuration"}
        )

# ── Prometheus metrics ────────────────────────────────────────────────────────
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

@app.on_event("startup")
async def startup_event():
    import asyncio, logging
    # 1. DB pool — must be first
    init_pool()
    # 2. Table init (moved from module scope to startup for test isolation)
    init_db()
    init_audit_table()
    init_webhook_table()
    init_custom_entity_table()
    init_auth_table()
    init_notify_table()
    init_model_table()
    init_intake_table()
    init_intake_jobs_table()
    init_redaction_table()
    init_transcription_table()
    init_messages_table()
    init_vcf_account_table()
    init_enclave_tables()
    from backend.demo1.esignature import init_esign_tables
    init_esign_tables()
    from backend.demo1.client_portal import init_tables as init_portal_tables
    init_portal_tables()
    # Phase 1: AI Infrastructure
    init_security_headers()
    init_guard_table()
    init_isolation_tables()
    init_ai_model_router()
    init_validation_tables()
    from backend.demo1.lead_crm import init_crm_tables
    init_crm_tables()
    from backend.demo1.communications import init_communications_tables
    init_communications_tables()
    # Security: VCF account prep sheets may contain credentials / SSN / financial data.
    if not os.getenv("VCF_PREP_ENC_KEY", "").strip():
        logging.warning(
            "[SECURITY] VCF_PREP_ENC_KEY is not set. VCF account prep sheets will be stored unencrypted. "
            "Generate a Fernet key and set VCF_PREP_ENC_KEY before processing real claimant data."
        )
    # 3. Poller tasks — keep references so GC cannot collect them
    #    Skip in TESTING mode to avoid asyncio interference with live-server tests
        # Email pollers disabled for ACP-VCF local development
    # if not os.getenv("TESTING"):
    #     from backend.demo1.email_poller import GmailPollerService
    #     from backend.demo1.outlook_poller import OutlookPollerService
    #     _poller_tasks: set = set()
    #     def _make_poller(cls):
    #         async def _run():
    #             while True:
    #                 try:
    #                     await cls().run()
    #                 except (RuntimeError, OSError, asyncio.CancelledError, ValueError) as exc:
    #                     logging.warning(f"[Poller] {cls.__name__} crashed: {exc}. Restarting in 60s.")
    #                     await asyncio.sleep(60)
    #         return _run
    #     for cls in (GmailPollerService, OutlookPollerService):
    #         task = asyncio.create_task(_make_poller(cls)())
    #         _poller_tasks.add(task)
    #         task.add_done_callback(_poller_tasks.discard)
    #     app.state.poller_tasks = _poller_tasks
    # 3. Scheduler
    # global _scheduler
    # _scheduler = start_scheduler(app)

# app.include_router(webauthn_router)
app.include_router(intake_router, prefix="/intake", tags=["OCR Intake"])
app.include_router(intake_jobs_router, prefix="/intake", tags=["Intake Jobs"])

class TextInput(BaseModel):
    text: str

app.include_router(notify_router, prefix="/notify", tags=["Slack & Teams"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(custom_entities_router, prefix="/entities/custom", tags=["Custom Entities"])
app.include_router(webhook_router, prefix="/webhooks", tags=["Webhooks"])
app.include_router(pdf_router, prefix="/export", tags=["PDF Export"])
app.include_router(module_pdf_router, prefix="/export", tags=["PDF Export"])
app.include_router(audit_router, prefix="/audit", tags=["Audit Trail"])
app.include_router(cases_router, prefix="/cases", tags=["Case Management"])
app.include_router(matter_export_router, prefix="/export", tags=["Matter Exports"])
app.include_router(redaction_router, prefix="/redact", tags=["Redaction"])
app.include_router(messages_router, tags=["Message Parsers"])
app.include_router(vcf_disbursements_router, tags=["VCF Disbursements"])
app.include_router(correspondence_router)
app.include_router(feedback_router)
app.include_router(summary_router)
app.include_router(nlp_router)
app.include_router(chat_router)
app.include_router(monitor_router)

# ── Risk watcher scheduler ─────────────────────────────────────────────────────
_scheduler = None

@app.on_event("shutdown")
async def shutdown_event():
    # if _scheduler:
    #     _scheduler.shutdown(wait=False)
    pass
app.include_router(calendar_router)
app.include_router(calendar_sync_router, prefix="/calendar", tags=["Calendar Sync"])
app.include_router(contacts_router)
app.include_router(reports_router)
app.include_router(exports_router)
app.include_router(ai_config_router)
app.include_router(client_portal_router)
app.include_router(email_router)
app.include_router(kanban_router)
app.include_router(notifications_router, prefix="", tags=["notifications"])
app.include_router(approval_router, prefix="/approvals", tags=["approvals"])
app.include_router(document_annotations_router, prefix="/documents", tags=["document-annotations"])
app.include_router(esign_router, prefix="/esign", tags=["e-signature"])
app.include_router(workflows_router, tags=["workflows"])
app.include_router(vcf_deadlines_router, tags=["VCF Deadlines"])
app.include_router(vcf_account_router, prefix="/vcf", tags=["VCF Account Prep"])
app.include_router(vcf_workflow_router, tags=["VCF Workflow"])
app.include_router(communications_router)
app.include_router(vcf_reports_router)

# ── Phase 1: AI Infrastructure Endpoints ─────────────────────────────────────

@app.get("/ai/status", tags=["ai-infrastructure"])
async def ai_infra_status(request: Request):
    """Get AI infrastructure status: routing, circuit breakers, costs."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    role = getattr(request.state, "role", "")
    report = {"firm_id": firm_id}
    report["routing"] = get_routing_status()
    report["token_usage"] = get_token_usage(firm_id)
    if role == "paraiq_super":
        report["cost_report"] = get_cost_report()
        report["recent_requests"] = get_recent_ai_requests(limit=20)
    return report

@app.get("/ai/config", tags=["ai-infrastructure"])
async def get_ai_config(request: Request):
    """Get this tenant's AI configuration."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    config = get_tenant_config(firm_id)
    return {"success": True, "config": config.to_dict()}

@app.put("/ai/config", tags=["ai-infrastructure"])
async def set_ai_config(request: Request):
    """Update AI configuration (super admin only)."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
    role = getattr(request.state, "role", "")
    if role != "paraiq_super":
        raise HTTPException(403, "Only super admins may modify AI configuration")
    firm_id = getattr(request.state, "firm_id", "default")
    import json as _json
    body = await request.body()
    updates = _json.loads(body)
    result = update_tenant_config(firm_id, **updates)
    return result

@app.get("/ai/guard/log", tags=["ai-infrastructure"])
async def get_guard_log(request: Request, limit: int = 50):
    """Get prompt guard event log for this tenant."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    limit = min(limit, 200)
    try:
        from backend.demo1.pg import get_conn
        with get_conn(firm_id) as conn:
            rows = conn.execute(
                """SELECT * FROM prompt_guard_log
                   WHERE firm_id = %s
                   ORDER BY created_at DESC LIMIT %s""",
                (firm_id, limit),
            ).fetchall()
        return {
            "success": True,
            "count": len(rows),
            "events": [dict(r) for r in rows],
        }
    except Exception as e:
        return {"success": False, "error": str(e), "events": []}

@app.post("/ai/test", tags=["ai-infrastructure"])
async def test_ai_routing(request: Request):
    """Test endpoint for AI routing — runs a simple summarization task."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    import json as _json
    body = await request.body()
    data = _json.loads(body) if body else {}
    text = data.get("text", "The statute of limitations for personal injury in New York is three years from the date of the accident.")
    task_type = data.get("task_type", "summarization")

    messages, guard_result = build_safe_messages(
        system_prompt=resolve_system_prompt(firm_id, LEGAL_SYSTEM_PROMPT),
        user_content=f"Summarize this in one sentence: {text}",
        firm_id=firm_id,
    )
    # Strip system message — passed separately as top-level 'system' param to Anthropic API
    messages = [m for m in messages if m.get("role") != "system"]

    if guard_result.threats:
        log_guard_event(guard_result, firm_id, "/ai/test")

    try:
        response, metadata = await call_llm_async(
            messages=messages,
            system=resolve_system_prompt(firm_id, LEGAL_SYSTEM_PROMPT),
            firm_id=firm_id,
            task_type=task_type,
            max_tokens=256,
        )
        output_text = response.content[0].text if response.content else ""
        return {
            "success": True,
            "output": output_text,
            "metadata": metadata,
            "guard": {
                "threats_detected": len(guard_result.threats),
                "blocked": guard_result.blocked,
                "risk_score": guard_result.risk_score,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── Middleware (added in reverse; Starlette executes outermost-first) ─────────
# Execution order: APIKey → SecurityHeaders → CORS → Tenant → Audit
app.add_middleware(AuditMiddleware)
app.add_middleware(make_tenant_middleware())
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGINS", "https://app.para-iq.com")],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Client-ID"],
    allow_credentials=True,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(APIKeyMiddleware)  # ← Move to LAST = runs FIRST

from backend.demo1.ai_client import get_client
client = get_client()

LLM_FAST   = os.getenv("LLM_FAST",  "claude-haiku-4-5-20251001")  # high-volume tasks
LLM_STRONG = os.getenv("LLM_STRONG", "claude-opus-4-5")            # deep analysis

# ── Legal AI system prompt ────────────────────────────────────────────────────
LEGAL_SYSTEM_PROMPT = (
    "You are ACP-VCF, an expert AI assistant helping paralegals and attorneys at WAW law firm process 9/11 Victim Compensation Fund claims. "
    "You produce precise, structured analysis of medical records, presence proofs, and financial documents. "
    "Always respond with valid JSON only — no markdown, no backticks, no preamble. "
    "Be rigorous, cite relevant facts from the provided text, and flag missing information explicitly."
)


@app.get("/health")
def health():
    return {"status": "ok", "model": LLM_FAST}

@app.post("/timeline")
def timeline(body: TextInput, request: Request):
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text too short")
    prompt = f"""Extract a chronological timeline from this text.

IMPORTANT: Your entire response must be ONLY a raw JSON object.
Do NOT use markdown. Do NOT use backticks. Do NOT add any explanation.
Start your response with {{ and end with }}

Text: \"\"\"{body.text[:3000] if len(body.text) <= 3000 else body.text[:3000] + "... [TRUNCATED: input was " + str(len(body.text)) + " chars; timeline covers opening 3000 only]"}\"\"\"

Return exactly this structure:
{{
  "title": "short descriptive title for this timeline",
  "events": [
    {{
      "date": "exact date or period as written in text",
      "date_normalized": "YYYY-MM-DD or YYYY-MM or YYYY",
      "event": "plain English description of what happened",
      "parties": ["person or org involved"],
      "amount": "$X or null if no amount",
      "significance": "high|medium|low",
      "category": "legal|financial|operational|communication|other"
    }}
  ],
  "date_range": {{
    "start": "earliest date in YYYY-MM-DD",
    "end":   "latest date in YYYY-MM-DD"
  }},
  "key_parties": ["list of main people and organizations"],
  "total_financial_impact": "total dollar amount if calculable, else null"
}}

Rules: extract ALL dates in chronological order, max 20 events."""

    try:
        _redacted_p, _pii_map = _pii_redact(prompt)
        if _pii_map: print('[PII] ' + str(_pii_summary(_pii_map)))
        message = claude_with_retry(
            client.messages.create,
            model=LLM_FAST,
            max_tokens=1500,
            system=LEGAL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _redacted_p}],
            firm_id=getattr(request.state, "firm_id", "default"),
        )
        raw     = message.content[0].text
        cleaned = clean_json(raw)
        _timeline_result = json.loads(cleaned)
        save_work_product('/timeline', _timeline_result, getattr(request.state, 'firm_id', 'default'), getattr(body, 'case_id', None), input_preview=body.text[:100])
        return _timeline_result
    except json.JSONDecodeError as e:
        import logging; logging.getLogger(__name__).warning(f"[paraiq] JSON parse error: {e}")
        raise HTTPException(status_code=500, detail="AI response could not be parsed. Please try again.")
    except Exception as e:
        import logging
        logging.error(f'[paraiq-api] Unhandled error: {e}')
        raise HTTPException(status_code=500, detail='An internal error occurred. Please try again.')

# feedback endpoints → routers/feedback_router.py

def claude_with_retry(func, *args, max_retries=3, firm_id: str = "default", **kwargs):
    """Call a Claude API function with exponential backoff on 429/500."""
    import time
    check_rate_limit(firm_id, "ai")
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except anthropic.RateLimitError:
            wait = 2 ** attempt
            logging.warning(f"Anthropic rate limit hit, retrying in {wait}s (attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                wait = 2 ** attempt
                logging.warning(f"Anthropic server error {e.status_code}, retrying in {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
               raise
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable. Please try again.")

@app.get("/history")
def history(
    request:   Request,
    sentiment: str = Query(None),
    keyword:   str = Query(None),
    limit:     int = Query(20)
):
    results = query_analyses(sentiment=sentiment, keyword=keyword, limit=limit, firm_id=getattr(request.state, 'firm_id', 'default'))
    return {"count": len(results), "results": results}

# disambiguate + coreference → routers/nlp_router.py

@app.post("/entities/score")
def entities_score(body: TextInput, request: Request):
    """Extract and score entities with confidence and salience metrics."""
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text too short")
    
    firm_id = getattr(request.state, 'firm_id', 'default')
    # Use Claude for initial extraction then score
    result = run_analysis(body.text, firm_id=firm_id)
    entities = result.get("entities", [])
    scored   = score_entities(body.text, entities)
    summary  = get_entity_summary(scored)
    
    return {
        "entities": scored,
        "summary":  summary,
        "text_preview": body.text[:100]
    }

# summary/score → routers/summary_router.py

@app.post("/summary/score/auto")
def summary_score_auto(body: TextInput, request: Request):
    """
    Analyze text, generate summary, then immediately score it.
    One endpoint that does the full pipeline.
    """
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text too short")

    firm_id = getattr(request.state, 'firm_id', 'default')
    # Run full analysis to get the summary
    result  = run_analysis(body.text, firm_id=firm_id)
    summary = result.get("summary", "")

    if not summary:
        raise HTTPException(status_code=500, detail="No summary generated")

    # Score the summary
    score          = score_summary(body.text, summary)
    result["summary_score"] = score
    return result

# languages + multilingual + detect → routers/nlp_router.py



# ── Feature 26: Legal Entity Extraction ──────────────────────────────────────

@app.post("/entities/legal")
def legal_entities(body: TextInput, request: Request):
    """Extract legal-specific entities: parties, amounts, dates, deadlines, jurisdictions."""
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text too short")

    prompt = f"""You are a legal NLP specialist. Extract all legally significant entities from this document.

Return ONLY valid JSON, no markdown:
{{
  "parties": [
    {{"name": "full name", "role": "Plaintiff|Defendant|Counsel|Judge|Witness|Other", "organization": "firm or company if applicable"}}
  ],
  "amounts": [
    {{"value": "$X,XXX", "context": "what the amount refers to", "type": "damages|settlement|fee|penalty|other"}}
  ],
  "dates_and_deadlines": [
    {{"date": "YYYY-MM-DD or as written", "event": "what happens on this date", "is_deadline": true}}
  ],
  "jurisdictions": [
    {{"name": "court or jurisdiction name", "type": "federal|state|arbitration|other"}}
  ],
  "legal_citations": [
    {{"citation": "case or statute citation", "type": "case_law|statute|regulation|contract"}}
  ],
  "key_obligations": [
    {{"party": "who must act", "obligation": "what they must do", "deadline": "by when if stated"}}
  ]
}}

Document:
{body.text[:5000] if len(body.text) <= 5000 else body.text[:5000] + chr(10) + "[TRUNCATED: input was " + str(len(body.text)) + " chars; analysis covers opening 5000 only]"}"""

    try:
        _redacted_p, _pii_map = _pii_redact(prompt)
        if _pii_map: print('[PII] ' + str(_pii_summary(_pii_map)))
        msg = claude_with_retry(
            client.messages.create,
            model=LLM_FAST,
            max_tokens=2000,
            system=LEGAL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _redacted_p}],
            firm_id=getattr(request.state, "firm_id", "default"),
        )
        raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
        _entities_result = json.loads(raw)
        save_work_product("/entities/legal", _entities_result, getattr(request.state, "firm_id", "default"), getattr(body, "case_id", None), input_preview=body.text[:100])
        return {"success": True, **_entities_result}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {e}")
    except Exception as e:
        import logging
        logging.error(f'[paraiq-api] Unhandled error: {e}')
        raise HTTPException(status_code=500, detail='An internal error occurred. Please try again.')


# ── Home Dashboard Stats ──────────────────────────────────────────────────────

@app.get("/dashboard/stats")
def dashboard_stats(request: Request):
    """Aggregate live stats for the home dashboard."""
    from datetime import date, timezone, datetime
    from backend.demo1.pg import get_conn
    firm_id = getattr(request.state, "firm_id", "default")
    out = {
        "modules_live": 0,
        "languages": 0,
        "total_cases": 0,
        "open_cases": 0,
        "high_risk_cases": 0,
        "total_analyses": 0,
        "requests_today": 0,
    }
    try:
        with get_conn(firm_id) as conn:
            # Real case counts from Supabase
            r = conn.execute(
                "SELECT COUNT(*) as n FROM cases WHERE deleted = false"
            ).fetchone()
            out["total_cases"] = r["n"] if r else 0

            r = conn.execute(
                "SELECT COUNT(*) as n FROM cases WHERE deleted = false AND status = 'open'"
            ).fetchone()
            out["open_cases"] = r["n"] if r else 0

            r = conn.execute(
                "SELECT COUNT(*) as n FROM cases WHERE deleted = false AND risk_level = 'high'"
            ).fetchone()
            out["high_risk_cases"] = r["n"] if r else 0

            # Requests today from audit_log
            today = date.today().isoformat()
            r = conn.execute(
                "SELECT COUNT(*) as n FROM audit_log WHERE timestamp::date = %s",
                (today,)
            ).fetchone()
            out["requests_today"] = r["n"] if r else 0

            # AI analyses persisted
            r = conn.execute(
                "SELECT COUNT(*) as n FROM ai_work_product"
            ).fetchone()
            out["total_analyses"] = r["n"] if r else 0

            # Live module count from module_permissions
            r = conn.execute(
                "SELECT COUNT(DISTINCT module) as n FROM module_permissions"
            ).fetchone()
            out["modules_live"] = r["n"] if r else 0

            # Languages: count distinct languages from case_documents
            r = conn.execute(
                "SELECT COUNT(DISTINCT language) as n FROM case_documents WHERE language IS NOT NULL"
            ).fetchone()
            out["languages"] = r["n"] if r else 0

    except (psycopg2.Error, KeyError, ValueError) as e:
        import logging
        logging.warning(f"dashboard_stats DB error: {e}")

    return out

# ── Serve frontend static files ───────────────────────────────────────────────
from fastapi.staticfiles import StaticFiles

# ── Deadline Radar ────────────────────────────────────────────────────────────


@app.get("/cases/{case_id}/wall", tags=["Cases"])
def case_wall(case_id: int, request: Request):
    """Unified chronological matter dossier — all case activity in one feed."""
    import json as _json
    from backend.demo1.pg import get_conn
    firm_id = getattr(request.state, "firm_id", "default")
    items = []

    try:
        with get_conn(firm_id) as conn:
            # ── Case metadata ──────────────────────────────────────────
            case_rows = conn.execute(
                "SELECT * FROM cases WHERE id=%s AND deleted=false", (case_id,)
            ).fetchall()
            if not case_rows:
                return {"items": [], "error": "Case not found"}
            case = case_rows[0]

            items.append({
                "date": str(case["filing_date"]) if case["filing_date"] else str(case["created_at"]),
                "type": "case_opened",
                "title": f"Case opened — {case['case_number']}",
                "body": (f"Client: {case['client_name']} | Court: {case['court'] or 'TBD'} | "
                         f"Judge: {case['judge'] or 'TBD'} | Matter: {case['matter_number'] or '—'}"),
                "meta": {"risk": case["risk_level"], "status": case["status"]}
            })

            # ── Documents ─────────────────────────────────────────────
            docs = conn.execute("""
                SELECT id, document_name, upload_date, summary, sentiment,
                       risk_score, events_json, entities_json
                FROM case_documents WHERE case_id=%s ORDER BY upload_date ASC
            """, (case_id,)).fetchall()

            for doc in docs:
                items.append({
                    "date": str(doc["upload_date"]) if doc["upload_date"] else "",
                    "type": "document",
                    "title": doc["document_name"],
                    "body": doc["summary"] or "No summary available.",
                    "meta": {
                        "sentiment": doc["sentiment"],
                        "risk_score": doc["risk_score"],
                        "doc_id": doc["id"]
                    }
                })
                if doc["events_json"]:
                    try:
                        events = doc["events_json"] if isinstance(doc["events_json"], list) else _json.loads(doc["events_json"])
                        for ev in (events if isinstance(events, list) else []):
                            ev_date = ev.get("date") or ev.get("event_date") or str(doc["upload_date"])
                            items.append({
                                "date": ev_date,
                                "type": "timeline_event",
                                "title": ev.get("event") or ev.get("title") or "Event",
                                "body": ev.get("description") or ev.get("detail") or "",
                                "meta": {"source_doc": doc["document_name"]}
                            })
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                        logger.debug(f"[main] timeline events_json parse failed for doc {doc.get('document_name')}: {e}")

            # ── Notes ─────────────────────────────────────────────────
            notes = conn.execute("""
                SELECT note, author, pinned, created_at
                FROM case_notes WHERE case_id=%s ORDER BY created_at ASC
            """, (case_id,)).fetchall()

            for note in notes:
                items.append({
                    "date": str(note["created_at"]),
                    "type": "note",
                    "title": f"Note by {note['author'] or 'Attorney'}",
                    "body": note["note"],
                    "meta": {"pinned": bool(note["pinned"])}
                })

            # ── AI Briefs ─────────────────────────────────────────────
            briefs = conn.execute("""
                SELECT generated_at, brief_json FROM case_briefs
                WHERE case_id=%s ORDER BY generated_at ASC
            """, (case_id,)).fetchall()

            for brief in briefs:
                items.append({
                    "date": str(brief["generated_at"]),
                    "type": "brief",
                    "title": "AI Case Brief generated",
                    "body": "Full case analysis brief produced by Claude. View in Overview tab.",
                    "meta": {}
                })

    except Exception as e:
        import logging
        logging.error(f"case_wall error for case {case_id}: {e}")
        return {"items": items, "error": "Failed to load case wall", "case_id": case_id}

    def sort_key(x):
        d = x.get("date") or ""
        return str(d)[:19] if d else "0000"
    items.sort(key=sort_key)

    return {"items": items, "count": len(items), "case_id": case_id}

@app.get("/cases/{case_id}/intelligence", tags=["Cases"])
def case_intelligence(case_id: int, request: Request):
    """Aggregate all intelligence signals for a case."""
    import re
    from datetime import date, datetime, timedelta
    from backend.demo1.pg import get_conn
    firm_id = getattr(request.state, "firm_id", "default")
    signals = []
    today = date.today()

    try:
        with get_conn(firm_id) as conn:
            # ── 1. Case metadata ───────────────────────────────────────
            case_rows = conn.execute(
                "SELECT * FROM cases WHERE id=%s AND deleted=false", (case_id,)
            ).fetchall()
            if not case_rows:
                return {"signals": [], "error": "Case not found"}
            case = case_rows[0]

            filing_date_str = str(case["filing_date"]) if case["filing_date"] else None
            case_number     = case["case_number"]
            client_name     = case["client_name"]
            description     = case["description"] or ""

            # ── 2. Deadline signal (jurisdiction-aware answer window) ───
            court_str = case["court"] or ""
            answer_days, rule_note = get_answer_days(court_str)
            if filing_date_str:
                try:
                    fd = datetime.strptime(filing_date_str[:10], "%Y-%m-%d").date()
                    answer_dl = fd + timedelta(days=answer_days)
                    diff = (answer_dl - today).days
                    if 0 <= diff <= answer_days:
                        sev = "critical" if diff <= 7 else "warning" if diff <= 14 else "watch"
                        signals.append({
                            "severity": sev,
                            "title": f"Answer deadline in {diff} day{'s' if diff!=1 else ''} — {answer_dl.strftime('%B %d, %Y')}",
                            "description": f"{rule_note} closes on {answer_dl.strftime('%B %d, %Y')} based on filing date {filing_date_str[:10]}. Immediate action may be required."
                        })
                    elif diff < 0:
                        signals.append({
                            "severity": "critical",
                            "title": f"Answer deadline may have passed ({answer_dl.strftime('%B %d, %Y')})",
                            "description": f"{rule_note} based on filing date appears to have elapsed. Verify current status with the court immediately."
                        })
                except (ValueError, TypeError) as e:
                    logger.debug(f"[main] answer deadline date parse failed: {e}")

            # ── 3. Dates in documents ──────────────────────────────────
            docs = conn.execute(
                "SELECT doc_text, document_name FROM case_documents WHERE case_id=%s AND doc_text IS NOT NULL AND doc_text!=''",
                (case_id,)
            ).fetchall()

            doc_dates = []
            for doc in docs:
                found = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', doc["doc_text"] or "")
                for ds in found:
                    try:
                        dl = datetime.strptime(ds, "%Y-%m-%d").date()
                        diff = (dl - today).days
                        if 0 <= diff <= 30:
                            doc_dates.append((dl, diff, doc["document_name"]))
                    except (ValueError, TypeError) as e:
                        logger.debug(f"[main] doc date parse failed for '{ds}': {e}")

            for dl, diff, docname in sorted(doc_dates, key=lambda x: x[0])[:3]:
                sev = "critical" if diff <= 7 else "warning" if diff <= 14 else "watch"
                signals.append({
                    "severity": sev,
                    "title": f"Upcoming date detected: {dl.strftime('%B %d, %Y')} ({diff}d away)",
                    "description": f"Found in document: {docname}. Review to confirm if this is a filing deadline, hearing date, or contractual milestone."
                })

            # ── 4. Contradictions ──────────────────────────────────────
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM case_contradictions WHERE case_id=%s", (case_id,)
                ).fetchone()
                contr_count = row["cnt"] if row else 0
                if contr_count > 0:
                    signals.append({
                        "severity": "warning",
                        "title": f"{contr_count} contradiction{'s' if contr_count!=1 else ''} detected across documents",
                        "description": "The AI found conflicting statements between linked documents. Open the Contradictions tab to review each conflict and assess impact on case strategy."
                    })
            except (psycopg2.Error, KeyError, ValueError) as e:
                logger.debug(f"[main] contradiction count query failed: {e}")

            # ── 5. Document coverage ───────────────────────────────────
            doc_count  = len(docs)
            empty_docs = [d["document_name"] for d in docs if len((d["doc_text"] or "").strip()) < 50]
            rich_docs  = doc_count - len(empty_docs)

            if doc_count == 0:
                signals.append({
                    "severity": "info",
                    "title": "No documents linked to this case",
                    "description": "Link documents from the Discovery queue to enable contradiction detection, timeline extraction, and deeper AI analysis."
                })
            elif doc_count == 1:
                signals.append({
                    "severity": "info",
                    "title": "Only 1 document linked — contradiction detection limited",
                    "description": "Contradiction analysis requires at least 2 documents. Link additional filings, depositions, or contracts for full coverage."
                })
            if empty_docs:
                names = ", ".join(empty_docs[:3]) + ("..." if len(empty_docs) > 3 else "")
                signals.append({
                    "severity": "warning",
                    "title": f"{len(empty_docs)} document(s) not yet analyzed - text not extracted",
                    "description": f"No readable text found in: {names}. Images and audio require OCR/transcription before AI analysis can run."
                })
            if rich_docs >= 2:
                signals.append({
                    "severity": "info",
                    "title": f"{rich_docs} documents fully analyzed and indexed",
                    "description": "All linked documents have been processed. Contradiction detection, timeline extraction, and AI brief generation are available."
                })

            # ── 6. Risk level ──────────────────────────────────────────
            risk = case["risk_level"] or "unknown"
            if risk == "high":
                signals.append({
                    "severity": "critical",
                    "title": "Case flagged as HIGH RISK",
                    "description": "Document analysis has identified high-risk indicators. Review the AI Case Brief for a full breakdown of risk factors."
                })
            elif risk == "unknown" and doc_count > 0:
                signals.append({
                    "severity": "info",
                    "title": "Risk level not yet assessed",
                    "description": "Generate an AI Case Brief to automatically score this case for risk based on all linked documents."
                })

            # ── 7. Claude AI Partner Signal ────────────────────────────
            rich_texts = []
            for doc in docs:
                txt = (doc["doc_text"] or "").strip()
                if len(txt) >= 50:
                    rich_texts.append(f"[{doc['document_name']}]\n{txt[:3000]}")
            if rich_texts:
                import json as _json
                combined = "\n\n---\n\n".join(rich_texts)[:8000]
                case_ctx = (f"Case: {case_number} | Client: {client_name} | "
                            f"Court: {case['court'] or 'Unknown'} | Filed: {filing_date_str or 'Unknown'}")
                ai_prompt = (
                    "You are a senior litigation partner reviewing a case file. "
                    "Surface the 2-3 most critical things this attorney MUST know right now.\n\n"
                    "Focus on: statute of limitations risks (calculate from dates), hidden obligations, "
                    "jurisdictional issues, factual gaps, anything requiring immediate action.\n\n"
                    f"Case context: {case_ctx}\n\nDocuments:\n{combined}\n\n"
                    "Return ONLY a JSON array (no markdown) of 2-3 objects with keys: "
                    "severity (critical|warning|watch|info), title (max 12 words), description (2-3 sentences)."
                )
                try:
                    _redacted_ai, _pii_map2 = _pii_redact(ai_prompt)
                    if _pii_map2: print('[PII] ' + str(_pii_summary(_pii_map2)))
                    ai_resp = claude_with_retry(
                        client.messages.create,
                        model=LLM_STRONG,
                        max_tokens=600,
                        system=LEGAL_SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": _redacted_ai}],
                        firm_id=firm_id,
                    )
                    ai_signals = _json.loads(clean_json(ai_resp.content[0].text))
                    if isinstance(ai_signals, list):
                        signals.extend(ai_signals)
                except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as _e:
                    import logging
                    logging.warning(f"case_intelligence AI signal failed: {_e}")

    except Exception as e:
        import logging
        logging.error(f"case_intelligence error for case {case_id}: {e}")
        return {"signals": signals, "error": "Failed to load case intelligence signals."}

    return {"signals": signals}

@app.get("/dashboard/deadlines", tags=["Dashboard"])
async def dashboard_deadlines():
    """Scan all open-case documents for upcoming dates within 30 days."""
    return get_deadline_radar()

# Note: In dev, Vite serves the frontend on port 5173 and proxies API calls.
# The production static-files mount is at the bottom of this file so API
# routes are registered first and take precedence over the SPA catch-all.



# ── Phase 2: AI Feature Endpoints ─────────────────────────────────────────────
@app.post("/ai/summarize", tags=["ai-features"])
async def ai_summarize_text(request: Request):
    """Summarize legal text using the routed LLM."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
        
    firm_id = getattr(request.state, "firm_id", "default")
    
    try:
        body = await request.json()
        text = body.get("text", "")
        context = body.get("context", "")
        
        if not text:
            raise HTTPException(400, "Missing 'text' field in request body")
            
        result = summarize_text(
            text=text,
            firm_id=firm_id,
            context=context
        )
        
        return {"success": True, "summary": result}
        
    except Exception as e:
        raise HTTPException(500, f"Error processing summarization: {str(e)}")


@app.post("/ai/time-capture", tags=["ai-features"])
async def ai_suggest_time(request: Request):
    """Suggest billable time entries based on recent activity."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
        
    firm_id = getattr(request.state, "firm_id", "default")
    
    try:
        # In a real app, we'd fetch this from the audit_trail table. 
        # For this demo, we accept a list of activities in the payload.
        body = await request.json()
        activities = body.get("activities", [])
        
        result = suggest_time_entries(
            activity_logs=activities,
            firm_id=firm_id
        )
        
        return {"success": True, "suggestions": result}
        
    except Exception as e:
        raise HTTPException(500, f"Error processing time capture: {str(e)}")


@app.post("/ai/doc-review", tags=["ai-features"])
async def ai_review_document(request: Request):
    """Analyze a legal document for risks and missing clauses."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
        
    firm_id = getattr(request.state, "firm_id", "default")
    
    try:
        body = await request.json()
        text = body.get("text", "")
        
        if not text:
            raise HTTPException(400, "Missing 'text' field in request body")
            
        result = review_document(
            text=text,
            firm_id=firm_id
        )
        
        return {"success": True, "review": result}
        
    except Exception as e:
        raise HTTPException(500, f"Error processing document review: {str(e)}")


@app.get("/ai/safety-dashboard", tags=["ai-infrastructure"])
async def ai_safety_dashboard(request: Request):
    """Aggregate AI safety metrics: blocked injections, output validation failures, etc."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
        
    firm_id = getattr(request.state, "firm_id", "default")
    role = getattr(request.state, "role", "")
    
    if role != "paraiq_super":
        raise HTTPException(403, "Only super admins may view the safety dashboard")
        
    try:
        from backend.demo1.pg import get_conn
        with get_conn(firm_id) as conn:
            # Get prompt guard stats
            guard_stats = conn.execute("""
                SELECT 
                    COUNT(*) as total_events,
                    COUNT(*) FILTER (WHERE blocked = TRUE) as blocked_events
                FROM prompt_guard_log 
                WHERE firm_id = %s
            """, (firm_id,)).fetchone()
            
            # Get output validation stats
            output_stats = conn.execute("""
                SELECT 
                    COUNT(*) as total_validations,
                    COUNT(*) FILTER (WHERE passed = FALSE) as failed_validations
                FROM ai_output_validation_log 
                WHERE firm_id = %s
            """, (firm_id,)).fetchone()

        return {
            "success": True,
            "prompt_guard": {
                "total_events": guard_stats[0] if guard_stats else 0,
                "blocked_events": guard_stats[1] if guard_stats else 0
            },
            "output_validation": {
                "total_validations": output_stats[0] if output_stats else 0,
                "failed_validations": output_stats[1] if output_stats else 0
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/ai/research", tags=["ai-features"])
async def ai_legal_research(request: Request):
    """Conduct AI-assisted legal research."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
        
    firm_id = getattr(request.state, "firm_id", "default")
    
    try:
        body = await request.json()
        query = body.get("query", "")
        jurisdiction = body.get("jurisdiction", "")
        
        if not query:
            raise HTTPException(400, "Missing 'query' field in request body")
            
        result = conduct_research(
            query=query,
            firm_id=firm_id,
            jurisdiction=jurisdiction
        )
        
        return {"success": True, "research": result}
        
    except Exception as e:
        raise HTTPException(500, f"Error processing legal research: {str(e)}")


@app.post("/ai/agent/execute", tags=["ai-features"])
async def ai_execute_agent(request: Request):
    """Execute a firm-wide AI agent task."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
        
    firm_id = getattr(request.state, "firm_id", "default")
    role = getattr(request.state, "role", "")
    
    # Only partners/admins can trigger agents
    if role not in ["paraiq_super", "partner", "admin"]:
        raise HTTPException(403, "Only admins or partners may execute AI agent tasks")
        
    try:
        body = await request.json()
        objective = body.get("objective", "")
        context = body.get("context", "")
        
        if not objective:
            raise HTTPException(400, "Missing 'objective' field in request body")
            
        result = execute_agent_task(
            objective=objective,
            context=context,
            firm_id=firm_id
        )
        
        return {"success": True, "agent_result": result}
        
    except Exception as e:
        raise HTTPException(500, f"Error processing agent task: {str(e)}")


@app.get("/reports/dashboard", tags=["reporting"])
async def firm_dashboard(request: Request):
    """Get firm-wide analytics: matters, billing, time, and intake."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
        
    firm_id = getattr(request.state, "firm_id", "default")
    role = getattr(request.state, "role", "")
    
    # Only admins/partners can view firm-wide reports
    if role not in ["paraiq_super", "partner", "admin"]:
        raise HTTPException(403, "Insufficient permissions to view firm dashboard")
        
    result = get_firm_dashboard(firm_id)
    return result


@app.post("/leads", tags=["crm"])
async def api_create_lead(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id: raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    body = await request.json()
    result = create_lead(
        firm_id=firm_id, 
        first_name=body.get("first_name", ""), 
        last_name=body.get("last_name", ""), 
        email=body.get("email", ""), 
        phone=body.get("phone", ""), 
        case_description=body.get("case_description", "")
    )
    return result

@app.get("/leads", tags=["crm"])
async def api_get_leads(request: Request, status: str = None):
    user_id = getattr(request.state, "user_id", None)
    if not user_id: raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    leads = get_leads(firm_id=firm_id, status=status)
    return {"success": True, "count": len(leads), "leads": leads}

@app.put("/leads/{lead_id}", tags=["crm"])
async def api_update_lead(request: Request, lead_id: int):
    user_id = getattr(request.state, "user_id", None)
    if not user_id: raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    body = await request.json()
    new_status = body.get("status")
    if not new_status: raise HTTPException(400, "Missing 'status' field")
    result = update_lead_status(firm_id=firm_id, lead_id=lead_id, new_status=new_status)
    return result


@app.post("/communications", tags=["communications"])
async def api_log_comm(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id: raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    body = await request.json()
    result = log_communication(
        firm_id=firm_id,
        comm_type=body.get("comm_type"),
        direction=body.get("direction"),
        sender=body.get("sender", ""),
        recipient=body.get("recipient", ""),
        body=body.get("body", ""),
        matter_id=body.get("matter_id")
    )
    return result

@app.get("/communications/{matter_id}", tags=["communications"])
async def api_get_comms(request: Request, matter_id: int):
    user_id = getattr(request.state, "user_id", None)
    if not user_id: raise HTTPException(401, "Authentication required")
    firm_id = getattr(request.state, "firm_id", "default")
    comms = get_matter_communications(firm_id=firm_id, matter_id=matter_id)
    return {"success": True, "count": len(comms), "communications": comms}


# ── Production static frontend (must be last so API routes win) ───────────────
import os as _os
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.exceptions import HTTPException as _StarletteHTTPException

_frontend_dist = _os.path.normpath(
    _os.path.join(_os.path.dirname(__file__), "..", "..", "frontend", "dist-vue")
)

class SPAStaticFiles(StaticFiles):
    """Serve static assets; fall back to index.html for HTML-navigated SPA routes."""
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except _StarletteHTTPException as exc:
            if exc.status_code == 404 and scope["method"] in ("GET", "HEAD"):
                request = Request(scope)
                accept = request.headers.get("accept", "")
                if "text/html" in accept:
                    return await super().get_response("index.html", scope)
            raise

if _os.path.isdir(_frontend_dist):
    app.mount("/", SPAStaticFiles(directory=_frontend_dist, html=False), name="frontend")
