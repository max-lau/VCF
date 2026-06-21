from backend.demo1.ocr_intake import init_intake_table, router as intake_router
from backend.demo1.voice_router import router as voice_router
from backend.demo1.voice_shortcuts_router import router as voice_shortcuts_router
from backend.demo1.fine_tune import init_model_table, router as model_router
from backend.demo1.slack_teams import init_notify_table, router as notify_router
from backend.demo1.auth import init_auth_table, router as auth_router
from backend.demo1.custom_entities import init_custom_entity_table, router as custom_entities_router
from backend.demo1.webhook import init_webhook_table, router as webhook_router
from backend.demo1.pdf_export import router as pdf_router
from backend.demo1.pdf_module_export import router as module_pdf_router
from backend.demo1.interrogation_export import router as interrogation_export_router
from backend.demo1.audit_trail import AuditMiddleware, init_audit_table, router as audit_router
from backend.demo1.risk_scorer import router as risk_router
from backend.demo1.document_comparison import router as comparison_router
from backend.demo1.citation_resolver import router as citations_router
from backend.demo1.case_management   import router as cases_router
from backend.demo1.pacer_integration import router as pacer_router
from backend.demo1.matter_exports import router as matter_export_router
from backend.demo1.discovery_intake import router as discovery_router, init_discovery_table
from backend.demo1.legal_modules import depo_router, motion_router, contract_router
from backend.demo1.redaction import router as redaction_router, init_redaction_table
from backend.demo1.bates import router as bates_router, init_bates_tables
from backend.demo1.production_bundler import router as bundler_router
from backend.demo1.privilege_log import router as privilege_router, init_privilege_table
from backend.demo1.media_transcription import router as media_router, init_transcription_table
from backend.demo1.message_parser import router as messages_router, init_messages_table
from backend.demo1.email_router import router as email_router
from backend.demo1.multilingual import analyze_multilingual, detect_language, SUPPORTED_LANGUAGES
from backend.demo1.summary_scorer import score_summary
from backend.demo1.entity_confidence import score_entities, get_entity_summary
from backend.demo1.entity_linker import find_linked_entities, link_documents_by_entity
from backend.demo1.coref_disambig import disambiguate_entities, resolve_coreferences
from backend.demo1.contradiction import run_contradiction_scan
from fastapi import FastAPI, HTTPException, Query, Request
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
import os
import json
import re
import csv
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from backend.demo1.enclave_router import router as enclave_privilege_router
from backend.demo1.db_enclaves import init_enclave_tables
from backend.demo1.routers.correspondence_router import router as correspondence_router
from backend.demo1.routers.feedback_router        import router as feedback_router
from backend.demo1.routers.summary_router         import router as summary_router
from backend.demo1.routers.nlp_router             import router as nlp_router
from backend.demo1.routers.calendar_router       import router as calendar_router
from backend.demo1.routers.contacts_router       import router as contacts_router
from backend.demo1.routers.chat_router            import router as chat_router
from backend.demo1.routers.monitor_router         import router as monitor_router
from backend.demo1.risk_watcher                   import start_scheduler
from backend.demo1.routers.research_router       import router as research_router
from backend.demo1.routers.reports_router        import router as reports_router
from backend.demo1.routers.misc_routers import (
    exports_router, ai_config_router,
    client_portal_router, legal_bert_router,
)
from backend.demo1.kanban_router import router as kanban_router
from backend.demo1.drafting_router import router as drafting_router
from backend.demo1.routers.approval_router import router as approval_router
from backend.demo1.routers.morning_brief_router import router as brief_router
from backend.demo1.routers.docketing_router import router as docketing_router
from backend.demo1.routers.time_router import router as time_router
from backend.demo1.routers.billing_router import router as billing_router
from backend.demo1.notifications_router import router as notifications_router

load_dotenv()
from backend.demo1.pg import init_pool, make_tenant_middleware

# ── API Key Auth Middleware ───────────────────────────────────────────────────

PARAIQ_API_KEY = os.getenv("PARAIQ_API_KEY", "")
if not PARAIQ_API_KEY:
    raise SystemExit("FATAL: PARAIQ_API_KEY is not set. Refusing to start with open API.")

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
    except Exception as _e:
        import logging
        logging.warning(f"save_work_product failed for {endpoint}: {_e}")



EXEMPT_PATHS = {"/health", "/openapi.json", "/docs", "/redoc", "/favicon.ico"}
EXEMPT_PREFIXES = ("/auth/", "/api/auth/", "/docs/", "/redoc/", "/client-portal/view/")
STATIC_EXTS = (".html", ".js", ".css", ".ico", ".png", ".svg", ".woff", ".woff2", ".json")

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        # Allow exempt paths
        path = request.url.path
        ext = os.path.splitext(path)[1].lower()
        if path in EXEMPT_PATHS or any(path.startswith(p) for p in EXEMPT_PREFIXES) or ext in STATIC_EXTS:
            return await call_next(request)
        # Check key OR valid Bearer JWT
        key = request.headers.get("X-API-Key", "")
        auth = request.headers.get("Authorization", "")
        has_bearer = False
        if auth.startswith("Bearer "):
            try:
                import jwt as _jwt
                _jwt.decode(auth[7:], os.getenv("JWT_SECRET_KEY", ""), algorithms=["HS256"])
                has_bearer = True
            except Exception:
                has_bearer = False
        if not PARAIQ_API_KEY or (key != PARAIQ_API_KEY and not has_bearer):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"}
            )
        request.state.client_id = request.headers.get("X-Client-ID", "")
        return await call_next(request)

app = FastAPI(title="NLP Text Analyzer API")
@app.on_event("startup")
async def startup_event():
    import asyncio, logging
    # 1. DB pool — must be first
    init_pool()
    # 2. Poller tasks — keep references so GC cannot collect them
    from backend.demo1.email_poller import GmailPollerService
    from backend.demo1.outlook_poller import OutlookPollerService
    _poller_tasks: set = set()

    def _make_poller(cls):
        async def _run():
            while True:
                try:
                    await cls().run()
                except Exception as exc:
                    logging.warning(f"[Poller] {cls.__name__} crashed: {exc}. Restarting in 60s.")
                    await asyncio.sleep(60)
        return _run

    for cls in (GmailPollerService, OutlookPollerService):
        task = asyncio.create_task(_make_poller(cls)())
        _poller_tasks.add(task)
        task.add_done_callback(_poller_tasks.discard)

    app.state.poller_tasks = _poller_tasks
    # 3. Scheduler
    global _scheduler
    _scheduler = start_scheduler(app)

app.include_router(intake_router, prefix="/intake", tags=["OCR Intake"])
app.include_router(model_router, prefix="/model", tags=["Fine-Tuned Model"])
app.include_router(notify_router, prefix="/notify", tags=["Slack & Teams"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(custom_entities_router, prefix="/entities/custom", tags=["Custom Entities"])
app.include_router(webhook_router, prefix="/webhooks", tags=["Webhooks"])
app.include_router(pdf_router, prefix="/export", tags=["PDF Export"])
app.include_router(module_pdf_router, prefix="/export", tags=["PDF Export"])
app.include_router(interrogation_export_router, tags=["Interrogation Export"])
app.include_router(audit_router, prefix="/audit", tags=["Audit Trail"])
app.include_router(risk_router, prefix="/risk", tags=["Risk Scoring"])
app.include_router(comparison_router, prefix="/documents", tags=["Document Comparison"])
app.include_router(citations_router, prefix="/citations", tags=["Citation Resolver"])
app.include_router(cases_router, prefix="/cases", tags=["Case Management"])
app.include_router(matter_export_router, prefix="/export", tags=["Matter Exports"])
app.include_router(pacer_router, prefix="/pacer",  tags=["PACER"])
app.include_router(discovery_router)
app.include_router(depo_router)
app.include_router(motion_router)
app.include_router(contract_router)
app.include_router(redaction_router, prefix="/redact", tags=["Redaction"])
app.include_router(bates_router, tags=["Bates Numbering"])
app.include_router(bundler_router, tags=["Production Bundler"])
app.include_router(privilege_router, tags=["Privilege Log"])
app.include_router(media_router, tags=["Media Transcription"])
app.include_router(messages_router, tags=["Message Parsers"])
app.include_router(enclave_privilege_router, prefix="/api/privilege", tags=["Privilege Enclave"])
app.include_router(correspondence_router)
app.include_router(research_router)
app.include_router(feedback_router)
app.include_router(summary_router)
app.include_router(nlp_router)
app.include_router(chat_router)
app.include_router(monitor_router)

# ── Risk watcher scheduler ─────────────────────────────────────────────────────
_scheduler = None

@app.on_event("shutdown")
async def shutdown_event():
    if _scheduler:
        _scheduler.shutdown(wait=False)
app.include_router(calendar_router)
app.include_router(contacts_router)
app.include_router(reports_router)
app.include_router(exports_router)
app.include_router(ai_config_router)
app.include_router(client_portal_router)
app.include_router(legal_bert_router)
app.include_router(voice_router)
app.include_router(voice_shortcuts_router)
app.include_router(email_router)
app.include_router(kanban_router)
app.include_router(drafting_router, prefix="/draft", tags=["drafting"])
app.include_router(notifications_router, prefix="", tags=["notifications"])
app.include_router(approval_router, prefix="/approvals", tags=["approvals"])
app.include_router(brief_router, prefix="/brief", tags=["brief"])
app.include_router(docketing_router, prefix="/docketing", tags=["docketing"])
app.include_router(time_router, prefix="/time", tags=["time"])
app.include_router(billing_router, prefix="/billing", tags=["billing"])
# ── Middleware (added in reverse; Starlette executes outermost-first) ─────────
# Execution order: CORS → APIKey → Tenant → Audit
app.add_middleware(AuditMiddleware)
app.add_middleware(make_tenant_middleware())
app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGINS", "https://app.para-iq.com")],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    allow_credentials=True,
)

init_db()
init_audit_table()
init_webhook_table()
init_custom_entity_table()
init_auth_table()
init_notify_table()
init_model_table()
init_intake_table()
init_redaction_table()
init_bates_tables()
init_privilege_table()
init_transcription_table()
init_messages_table()
init_enclave_tables()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

LLM_FAST   = os.getenv("LLM_FAST",  "claude-haiku-4-5-20251001")  # high-volume tasks
LLM_STRONG = os.getenv("LLM_STRONG", "claude-opus-4-5")            # deep analysis
LLM_STRONG = os.getenv("LLM_STRONG", LLM_STRONG)            # deep analysis

executor = ThreadPoolExecutor(max_workers=3)

class TextInput(BaseModel):
    text: str

class BatchInput(BaseModel):
    documents: List[str]
    labels: List[str] = []

class FeedbackInput(BaseModel):
    analysis_id: int
    text: str
    predicted: str
    predicted_score: float
    corrected: str
    feedback_type: str = "sentiment_correction"
    notes: str = ""

class ReviewInput(BaseModel):
    feedback_id: int

def clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()

def run_analysis(text: str, label: str = "") -> dict:
    prompt = f"""Analyze this text for NLP tasks.

IMPORTANT: Your entire response must be ONLY a raw JSON object.
Do NOT use markdown. Do NOT use backticks. Do NOT add any explanation.
Start your response with {{ and end with }}

Text: \"\"\"{text[:2000] if len(text) <= 2000 else text[:2000] + "... [TRUNCATED: input was " + str(len(text)) + " chars; analysis covers opening 2000 only]"}\"\"\"

Return exactly this structure:
{{
  "sentiment": {{
    "label": "positive",
    "score": 0.85,
    "explanation": "one sentence about why"
  }},
  "entities": [
    {{"text": "Apple", "type": "ORG"}}
  ],
  "keywords": [
    {{"word": "revenue", "importance": "high"}}
  ],
  "tone": ["analytical", "confident"],
  "summary": "2-sentence plain English summary of the text"
}}

label must be one of: positive negative neutral mixed
importance must be one of: high medium low
Entity types: PERSON ORG GPE LOC DATE TIME MONEY PERCENT LAW PRODUCT OTHER
Max 8 entities, max 10 keywords, max 3 tone items."""

    try:
        message = client.messages.create(
            model=LLM_FAST,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw     = message.content[0].text
        cleaned = clean_json(raw)
        parsed  = json.loads(cleaned)
        row_id  = save_analysis(text, parsed)
        parsed["id"]           = row_id
	# Score entities with confidence and salience
        if parsed.get("entities"):
            parsed["entities"] = score_entities(text, parsed["entities"])
            parsed["entity_summary"] = get_entity_summary(parsed["entities"])
        parsed["label"]        = label
        parsed["status"]       = "success"
        parsed["text_preview"] = text[:120] + "..." if len(text) > 120 else text
        parsed["word_count"]   = len(text.split())

        # Auto-flag low confidence for active learning
        score = parsed.get("sentiment", {}).get("score", 1.0)
        if score < 0.70:
            save_feedback(
                analysis_id     = row_id,
                text            = text[:500],
                predicted       = parsed.get("sentiment", {}).get("label", ""),
                predicted_score = score,
                corrected       = "",
                feedback_type   = "low_confidence",
                notes           = f"Auto-flagged: confidence {score:.2f} below threshold 0.70"
            )
            parsed["flagged"] = True
            parsed["flag_reason"] = f"Low confidence ({score:.0%}) — queued for human review"
        else:
            parsed["flagged"] = False

        return parsed
    except Exception as e:
        import logging
        logging.error(f"run_analysis error for label={label}: {e}")
        return {
            "status": "error", "error": "Analysis failed. Please try again.", "label": label,
            "text_preview": text[:120] + "..." if len(text) > 120 else text,
            "word_count": len(text.split())
        }
@app.get("/health")
def health():
    return {"status": "ok", "model": LLM_FAST}

@app.post("/analyze")
def analyze(body: TextInput):
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text too short")
    return run_analysis(body.text)

@app.post("/analyze/batch")
async def analyze_batch(body: BatchInput):
    if not body.documents:
        raise HTTPException(status_code=400, detail="No documents provided")
    if len(body.documents) > 20:
        raise HTTPException(status_code=400, detail="Max 20 documents per batch")
    labels = body.labels + [""] * (len(body.documents) - len(body.labels))
    loop   = asyncio.get_event_loop()
    tasks  = [
        loop.run_in_executor(executor, run_analysis, doc, label)
        for doc, label in zip(body.documents, labels)
    ]
    results    = await asyncio.gather(*tasks)
    successful = [r for r in results if r.get("status") == "success"]
    failed     = [r for r in results if r.get("status") == "error"]
    sentiments = [r.get("sentiment", {}).get("label", "") for r in successful]
    flagged    = [r for r in successful if r.get("flagged")]
    return {
        "total": len(results), "successful": len(successful),
        "failed": len(failed), "flagged": len(flagged),
        "summary": {
            "positive": sentiments.count("positive"),
            "negative": sentiments.count("negative"),
            "neutral":  sentiments.count("neutral"),
            "mixed":    sentiments.count("mixed"),
            "avg_score": round(
                sum(r.get("sentiment", {}).get("score", 0) for r in successful)
                / max(len(successful), 1), 3
            )
        },
        "results": list(results)
    }

@app.post("/analyze/batch/csv")
async def analyze_batch_csv(body: BatchInput):
    if not body.documents:
        raise HTTPException(status_code=400, detail="No documents provided")
    if len(body.documents) > 20:
        raise HTTPException(status_code=400, detail="Max 20 documents per batch")
    labels = body.labels + [""] * (len(body.documents) - len(body.labels))
    loop   = asyncio.get_event_loop()
    tasks  = [
        loop.run_in_executor(executor, run_analysis, doc, label)
        for doc, label in zip(body.documents, labels)
    ]
    results = await asyncio.gather(*tasks)
    output  = io.StringIO()
    writer  = csv.writer(output)
    writer.writerow([
        "id", "label", "status", "word_count", "sentiment", "score",
        "tone", "top_keywords", "entity_count", "flagged", "summary", "text_preview"
    ])
    for r in results:
        writer.writerow([
            r.get("id", ""), r.get("label", ""), r.get("status", ""),
            r.get("word_count", ""),
            r.get("sentiment", {}).get("label", "") if r.get("status") == "success" else "",
            r.get("sentiment", {}).get("score", "") if r.get("status") == "success" else "",
            ", ".join(r.get("tone", [])) if r.get("status") == "success" else "",
            ", ".join([k["word"] for k in r.get("keywords", [])[:3]]) if r.get("status") == "success" else "",
            len(r.get("entities", [])) if r.get("status") == "success" else "",
            r.get("flagged", False),
            r.get("summary", "") if r.get("status") == "success" else r.get("error", ""),
            r.get("text_preview", "")
        ])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=batch_analysis.csv"}
    )

@app.post("/timeline")
def timeline(body: TextInput):
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
        message = client.messages.create(
            model=LLM_FAST,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw     = message.content[0].text
        cleaned = clean_json(raw)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {str(e)}")
    except Exception as e:
        import logging
        logging.error(f'[{request.__class__.__name__ if hasattr(locals(), "request") else "endpoint"}] Unhandled error: {e}')
        raise HTTPException(status_code=500, detail='An internal error occurred. Please try again.')

# feedback endpoints → routers/feedback_router.py

@app.get("/history")
def history(
    sentiment: str = Query(None),
    keyword:   str = Query(None),
    limit:     int = Query(20)
):
    results = query_analyses(sentiment=sentiment, keyword=keyword, limit=limit)
    return {"count": len(results), "results": results}

# disambiguate + coreference → routers/nlp_router.py

@app.post("/entities/score")
def entities_score(body: TextInput):
    """Extract and score entities with confidence and salience metrics."""
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text too short")
    
    doc = nlp_spacy(body.text[:5000]) if hasattr(body, 'nlp_spacy') else None
    
    # Use Claude for initial extraction then score
    result = run_analysis(body.text)
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
def summary_score_auto(body: TextInput):
    """
    Analyze text, generate summary, then immediately score it.
    One endpoint that does the full pipeline.
    """
    if not body.text or len(body.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Text too short")

    # Run full analysis to get the summary
    result  = run_analysis(body.text)
    summary = result.get("summary", "")

    if not summary:
        raise HTTPException(status_code=500, detail="No summary generated")

    # Score the summary
    score          = score_summary(body.text, summary)
    result["summary_score"] = score
    return result

# languages + multilingual + detect → routers/nlp_router.py


# ── Interrogation Analyzer ────────────────────────────────────────────────────

class InterrogationInput(BaseModel):
    transcript: str
    case_id: int = None

@app.post("/interrogate")
def interrogate(body: InterrogationInput, request: Request):
    if not body.transcript or len(body.transcript.strip()) < 20:
        raise HTTPException(status_code=400, detail="Transcript too short")
    prompt = f"""You are a legal transcript analyst. Analyze the following interrogation or deposition transcript for contradictions and evasions.

Return ONLY valid JSON with this exact structure — no markdown, no backticks, no preamble:
{{
  "contradictions": [
    {{
      "title": "Short descriptive title",
      "explanation": "What contradicts what, and why it matters legally.",
      "quote_a": "First statement verbatim from transcript",
      "quote_b": "Contradicting statement verbatim from transcript"
    }}
  ],
  "evasions": [
    {{
      "title": "Short descriptive title",
      "explanation": "Why this response is evasive, non-responsive, or inconsistent.",
      "quote": "The evasive statement verbatim from transcript"
    }}
  ]
}}

If there are no contradictions or no evasions, return empty arrays. Be precise and legally rigorous.

Transcript:
{body.transcript[:6000]}"""

    try:
        message = client.messages.create(
            model=LLM_FAST,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text
        cleaned = clean_json(raw)
        save_work_product("/interrogate", {}, getattr(request.state, "firm_id", "default"), body.case_id, input_preview=body.transcript[:100])
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {str(e)}")
    except Exception as e:
        import logging
        logging.error(f'[{request.__class__.__name__ if hasattr(locals(), "request") else "endpoint"}] Unhandled error: {e}')
        raise HTTPException(status_code=500, detail='An internal error occurred. Please try again.')

# -- Lease Clause Diff --

class LeaseDiffInput(BaseModel):
    doc_a: str
    case_id: int = None
    doc_b: str

@app.post("/documents/lease-diff")
def lease_diff(body: LeaseDiffInput, request: Request):
    da = body.doc_a[:4000]
    db = body.doc_b[:4000]
    prompt = "\n".join([
        "You are a legal analyst specializing in lease contracts.",
        "Compare these two lease versions and identify all clause changes.",
        "Return ONLY valid JSON, no markdown, no backticks:",
        '{"key_term_changes":["example: Rent $3500 to $3750"],',
        '"added":[{"clause":"Name","detail":"description"}],',
        '"removed":[{"clause":"Name","detail":"description"}],',
        '"modified":[{"clause":"Name","change":"what changed"}]}',
        "", "Lease A:", da, "", "Lease B:", db
    ])
    try:
        msg = client.messages.create(
            model=LLM_FAST,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        save_work_product("/documents/lease-diff", {}, getattr(request.state, "firm_id", "default"), body.case_id, input_preview=body.doc_a[:100])
        return json.loads(clean_json(msg.content[0].text))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail="JSON parse error: " + str(e))
    except Exception as e:
        import logging
        logging.error(f'[{request.__class__.__name__ if hasattr(locals(), "request") else "endpoint"}] Unhandled error: {e}')
        raise HTTPException(status_code=500, detail='An internal error occurred. Please try again.')

# ── Witness Credibility Scorer ────────────────────────────────────────────────

class CredibilityInput(BaseModel):
    transcript: str
    case_id: int = None
    witness_name: str = "Witness"
    role: str = "Witness"
    case_name: str = ""

@app.post("/credibility/score")
def credibility_score(body: CredibilityInput, request: Request):
    t = body.transcript[:6000]
    w = body.witness_name
    lines = [
        f"You are an expert legal analyst scoring the credibility of a witness named {w}.",
        "Analyze the provided testimony transcript and score the witness on 5 dimensions (0-10 each).",
        "Return ONLY valid JSON, no markdown, no backticks:",
        '{',
        '  "overall_score": 6.2,',
        '  "summary": "One sentence overall credibility assessment.",',
        '  "scores": {',
        '    "consistency": {"score": 7, "explanation": "explanation", "key_quote": "verbatim quote from transcript"},',
        '    "responsiveness": {"score": 6, "explanation": "explanation", "key_quote": "verbatim quote"},',
        '    "clarity": {"score": 5, "explanation": "explanation", "key_quote": "verbatim quote"},',
        '    "corroboration": {"score": 4, "explanation": "explanation", "key_quote": "verbatim quote"},',
        '    "demeanor": {"score": 3, "explanation": "explanation", "key_quote": "verbatim quote"}',
        '  },',
        '  "key_findings": [',
        '    {"type": "strength", "finding": "positive credibility observation"},',
        '    {"type": "concern", "finding": "credibility concern or red flag"}',
        '  ]',
        '}',
        '',
        'Scoring guide:',
        '- consistency: 10=no contradictions, 0=major self-contradictions',
        '- responsiveness: 10=answers all questions directly, 0=never answers directly',
        '- clarity: 10=clear precise language, 0=vague hedging throughout',
        '- corroboration: 10=testimony matches all evidence cited, 0=contradicts all evidence',
        '- demeanor: 10=calm direct confident, 0=evasive hesitant deflecting throughout',
        '',
        f'Transcript of {w}:',
        t
    ]
    prompt = chr(10).join(lines)

    try:
        msg = client.messages.create(
            model=LLM_FAST,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text
        save_work_product("/credibility/score", {}, getattr(request.state, "firm_id", "default"), body.case_id, input_preview=body.witness_name)
        return json.loads(clean_json(raw))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail="JSON parse error: " + str(e))
    except Exception as e:
        import logging
        logging.error(f'[{request.__class__.__name__ if hasattr(locals(), "request") else "endpoint"}] Unhandled error: {e}')
        raise HTTPException(status_code=500, detail='An internal error occurred. Please try again.')


# ── Deposition Summary Generator ─────────────────────────────────────────────

class DepositionInput(BaseModel):
    transcript: str
    case_id: int = None
    case_name: str = "Untitled Matter"
    deponent: str = "Witness"
    exam_counsel: str = ""
    depos_date: str = ""

@app.post("/deposition/summarize")
def deposition_summarize(body: DepositionInput, request: Request):
    t = body.transcript[:7000]
    lines = [
        "You are an expert legal analyst. Analyze this deposition transcript and extract a structured summary.",
        "Return ONLY valid JSON, no markdown, no backticks:",
        "{",
        '  "case_overview": {',
        '    "case_name": "case name",',
        '    "deponent": "witness name",',
        '    "date": "deposition date",',
        '    "examining_counsel": "counsel name",',
        '    "summary": "2-3 sentence overview of the deposition and its significance"',
        "  },",
        '  "parties": [',
        '    {"name": "full name", "role": "Deponent/Attorney/Judge", "representation": "firm or party represented"}',
        "  ],",
        '  "key_admissions": [',
        '    {"admission": "what the deponent admitted", "significance": "why it matters legally", "quote": "verbatim quote"}',
        "  ],",
        '  "disputed_facts": [',
        '    {"fact": "the disputed fact", "deponent_position": "what deponent claims", "contrary_evidence": "evidence that contradicts"}',
        "  ],",
        '  "timeline": [',
        '    {"date_or_period": "specific date or period", "event": "what happened", "source": "who stated this"}',
        "  ],",
        '  "legal_issues": [',
        '    {"issue": "legal issue raised", "context": "context and relevance", "objections": "any objections or rulings"}',
        "  ]",
        "}",
        "",
        f"Case: {body.case_name}",
        f"Deponent: {body.deponent}",
        f"Examining Counsel: {body.exam_counsel}",
        f"Date: {body.depos_date}",
        "",
        "Transcript:",
        t
    ]
    prompt = chr(10).join(lines)

    try:
        msg = client.messages.create(
            model=LLM_FAST,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text
        return json.loads(clean_json(raw))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail="JSON parse error: " + str(e))
    except Exception as e:
        import logging
        logging.error(f'[{request.__class__.__name__ if hasattr(locals(), "request") else "endpoint"}] Unhandled error: {e}')
        raise HTTPException(status_code=500, detail='An internal error occurred. Please try again.')



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
        msg = client.messages.create(
            model=LLM_FAST,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
        save_work_product("/entities/legal", {}, getattr(request.state, "firm_id", "default"), getattr(body, "case_id", None), input_preview=body.text[:100])
        return {"success": True, **json.loads(raw)}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {e}")
    except Exception as e:
        import logging
        logging.error(f'[{request.__class__.__name__ if hasattr(locals(), "request") else "endpoint"}] Unhandled error: {e}')
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

    except Exception as e:
        import logging
        logging.warning(f"dashboard_stats DB error: {e}")

    return out

# ── Serve frontend static files ───────────────────────────────────────────────
from fastapi.staticfiles import StaticFiles

# ── Deadline Radar ────────────────────────────────────────────────────────────


@app.get("/cases/{case_id}/wall", tags=["Cases"])
async def case_wall(case_id: int):
    """Unified chronological matter dossier — all case activity in one feed."""
    import sqlite3, json as _json
    DB = "/root/nlp-portfolio/analyses.db"
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    items = []

    try:
        # ── Case metadata ──────────────────────────────────────────────
        cur.execute("SELECT * FROM cases WHERE id=? AND deleted=0", (case_id,))
        case = cur.fetchone()
        if not case:
            return {"items": [], "error": "Case not found"}

        # Case opened event
        items.append({
            "date": case["filing_date"] or case["created_at"],
            "type": "case_opened",
            "title": f"Case opened — {case['case_number']}",
            "body": (f"Client: {case['client_name']} | Court: {case['court'] or 'TBD'} | "
                     f"Judge: {case['judge'] or 'TBD'} | Matter: {case['matter_number'] or '—'}"),
            "meta": {"risk": case["risk_level"], "status": case["status"]}
        })

        # ── Documents ──────────────────────────────────────────────────
        cur.execute("""SELECT id, document_name, upload_date, summary, sentiment,
                              risk_score, events_json, entities_json
                       FROM case_documents WHERE case_id=? ORDER BY upload_date ASC""", (case_id,))
        docs = cur.fetchall()

        for doc in docs:
            items.append({
                "date": doc["upload_date"],
                "type": "document",
                "title": doc["document_name"],
                "body": doc["summary"] or "No summary available.",
                "meta": {
                    "sentiment": doc["sentiment"],
                    "risk_score": doc["risk_score"],
                    "doc_id": doc["id"]
                }
            })
            # Expand timeline events from this doc
            if doc["events_json"]:
                try:
                    events = _json.loads(doc["events_json"])
                    for ev in (events if isinstance(events, list) else []):
                        ev_date = ev.get("date") or ev.get("event_date") or doc["upload_date"]
                        items.append({
                            "date": ev_date,
                            "type": "timeline_event",
                            "title": ev.get("event") or ev.get("title") or "Event",
                            "body": ev.get("description") or ev.get("detail") or "",
                            "meta": {"source_doc": doc["document_name"]}
                        })
                except Exception:
                    pass

        # ── Notes ──────────────────────────────────────────────────────
        cur.execute("""SELECT note, author, pinned, created_at
                       FROM case_notes WHERE case_id=? ORDER BY created_at ASC""", (case_id,))
        for note in cur.fetchall():
            items.append({
                "date": note["created_at"],
                "type": "note",
                "title": f"Note by {note['author'] or 'Attorney'}",
                "body": note["note"],
                "meta": {"pinned": bool(note["pinned"])}
            })

        # ── AI Briefs ──────────────────────────────────────────────────
        cur.execute("""SELECT generated_at, brief_json FROM case_briefs
                       WHERE case_id=? ORDER BY generated_at ASC""", (case_id,))
        for brief in cur.fetchall():
            items.append({
                "date": brief["generated_at"],
                "type": "brief",
                "title": "AI Case Brief generated",
                "body": "Full case analysis brief produced by Claude. View in Overview tab.",
                "meta": {}
            })

    finally:
        conn.close()

    # Sort chronologically
    def sort_key(x):
        d = x.get("date") or ""
        return d[:19] if d else "0000"
    items.sort(key=sort_key)

    return {"items": items, "count": len(items), "case_id": case_id}


@app.get("/cases/{case_id}/intelligence", tags=["Cases"])
async def case_intelligence(case_id: int):
    """Aggregate all intelligence signals for a case."""
    import sqlite3, re
    from datetime import date, datetime, timedelta

    DB = "/root/nlp-portfolio/analyses.db"
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    signals = []
    today = date.today()

    try:
        # ── 1. Case metadata ───────────────────────────────────────────
        cur.execute("SELECT * FROM cases WHERE id=? AND deleted=0", (case_id,))
        case = cur.fetchone()
        if not case:
            return {"signals": [], "error": "Case not found"}

        filing_date_str = case["filing_date"]
        case_number     = case["case_number"]
        client_name     = case["client_name"]
        description     = case["description"] or ""

        # ── 2. Deadline signal (30-day answer window) ──────────────────
        if filing_date_str:
            try:
                fd = datetime.strptime(filing_date_str[:10], "%Y-%m-%d").date()
                answer_dl = fd + timedelta(days=30)
                diff = (answer_dl - today).days
                if 0 <= diff <= 30:
                    sev = "critical" if diff <= 7 else "warning" if diff <= 14 else "watch"
                    signals.append({
                        "severity": sev,
                        "title": f"Answer deadline in {diff} day{'s' if diff!=1 else ''} — {answer_dl.strftime('%B %d, %Y')}",
                        "description": f"30-day answer window closes on {answer_dl.strftime('%B %d, %Y')} based on filing date {filing_date_str[:10]}. Immediate action may be required."
                    })
                elif diff < 0:
                    signals.append({
                        "severity": "critical",
                        "title": f"Answer deadline may have passed ({answer_dl.strftime('%B %d, %Y')})",
                        "description": "The 30-day answer window based on the filing date appears to have elapsed. Verify current status with the court immediately."
                    })
            except Exception:
                pass

        # ── 3. Dates in documents ──────────────────────────────────────
        cur.execute("""SELECT doc_text, document_name FROM case_documents
                       WHERE case_id=? AND doc_text IS NOT NULL AND doc_text!=''""", (case_id,))
        docs = cur.fetchall()

        doc_dates = []
        for doc in docs:
            found = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', doc["doc_text"] or "")
            for ds in found:
                try:
                    dl = datetime.strptime(ds, "%Y-%m-%d").date()
                    diff = (dl - today).days
                    if 0 <= diff <= 30:
                        doc_dates.append((dl, diff, doc["document_name"]))
                except Exception:
                    pass

        for dl, diff, docname in sorted(doc_dates, key=lambda x: x[0])[:3]:
            sev = "critical" if diff <= 7 else "warning" if diff <= 14 else "watch"
            signals.append({
                "severity": sev,
                "title": f"Upcoming date detected: {dl.strftime('%B %d, %Y')} ({diff}d away)",
                "description": f"Found in document: {docname}. Review to confirm if this is a filing deadline, hearing date, or contractual milestone."
            })

        # ── 4. Contradictions ──────────────────────────────────────────
        cur.execute("""SELECT COUNT(*) as cnt FROM case_contradictions
                       WHERE case_id=?""", (case_id,))
        row = cur.fetchone()
        contr_count = row["cnt"] if row else 0
        if contr_count > 0:
            signals.append({
                "severity": "warning",
                "title": f"{contr_count} contradiction{'s' if contr_count!=1 else ''} detected across documents",
                "description": "The AI found conflicting statements between linked documents. Open the Contradictions tab to review each conflict and assess impact on case strategy."
            })

        # ── 5. Document coverage ───────────────────────────────────────
        doc_count = len(docs)
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

        # ── 6. Risk level ──────────────────────────────────────────────
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

        # ── 7. Claude AI Partner Signal ───────────────────────────────
        rich_texts = []
        for doc in docs:
            txt = (doc["doc_text"] or "").strip()
            if len(txt) >= 50:
                rich_texts.append(f"[{doc['document_name']}]\n{txt[:3000]}")

        if rich_texts:
            import anthropic as _anthropic, json as _json
            _ai = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
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
                ai_resp = _ai.messages.create(
                    model=LLM_STRONG,
                    max_tokens=600,
                    messages=[{"role": "user", "content": ai_prompt}]
                )
                raw = ai_resp.content[0].text.strip().replace("```json","").replace("```","").strip()
                for s in _json.loads(raw)[:3]:
                    if isinstance(s, dict) and "title" in s:
                        s.setdefault("severity", "info")
                        s["ai"] = True
                        signals.append(s)
            except Exception:
                pass

    except Exception as e:
        signals.append({"severity": "info", "title": "Analysis error", "description": str(e)})
    finally:
        conn.close()

    # Sort: critical first, then warning, watch, info
    order = {"critical": 0, "warning": 1, "watch": 2, "info": 3}
    signals.sort(key=lambda x: order.get(x.get("severity","info"), 3))
    return {"signals": signals, "case_id": case_id}


@app.get("/dashboard/deadlines", tags=["Dashboard"])
async def dashboard_deadlines():
    """Scan all open-case documents for upcoming dates within 30 days."""
    return get_deadline_radar()

app.mount("/", StaticFiles(directory="frontend/demo1", html=True), name="frontend")

