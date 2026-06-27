import os, json, logging, tempfile, time
from backend.demo1.pg import get_conn
from pathlib import Path
import httpx
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse
import openai
from backend.demo1.ai_client import get_client
from backend.demo1.auth import get_current_user

log = logging.getLogger("paraiq.voice")
router = APIRouter(prefix="/voice", tags=["voice"])
openai_client    = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY",""))
anthropic_client = get_client()  # use shared sync client singleton
PARAIQ_BASE_URL  = os.environ.get("PARAIQ_BASE_URL","http://localhost:5003")

COMMAND_CATALOGUE = """
Reply ONLY with a valid JSON object — no markdown, no explanation.

=== CALENDAR & DEADLINES ===
1.  get_deadlines           - upcoming deadlines, due dates, what is due, filing deadlines, court dates
2.  get_upcoming_calendar   - calendar, schedule, upcoming events, what is coming up, appointments
3.  get_calendar_types      - calendar event types, types of events

=== CASES & MATTERS ===
4.  get_cases_stats         - case statistics, how many cases, case count, case summary, matter overview
5.  search_cases            - find/search/look up cases or matters (params: query string)

=== CONTACTS ===
6.  get_contacts            - contacts, show contacts, contact list, who are our contacts, client list

=== DISCOVERY & DOCUMENTS ===
7.  get_discovery_stats     - discovery stats, document processing, how many documents
8.  get_discovery_queue     - discovery queue, what is being processed, pending documents, backlog
9.  get_discovery_duplicates- duplicate documents, find duplicates, duplicate files, dupes
10. get_discovery_catalog   - discovery catalog, all discovery documents, document catalog

=== AI ANALYSIS ===
11. get_risk_signals        - risk signals, risk alerts, risks, what are the risks, risk analysis
12. get_legal_bert_status   - legal bert, bert model, AI model status, NLP model, bert status
13. get_intake_history      - intake history, past intakes, previous intake forms, intake log

=== PRIVILEGE LOG ===
14. get_privilege_stats     - privilege stats, how many privileged, privilege summary
15. get_privilege_log       - privilege log, show privilege log, privileged documents list

=== REPORTS & EXPORTS ===
16. get_reports_list        - reports list, available reports, what reports, report types
17. get_deposition_stats    - deposition stats, how many depositions, deposition summary
18. get_depositions         - depositions, show depositions, deposition list
19. get_motion_stats        - motion stats, how many motions, motions summary
20. get_motions             - motions, show motions, pending motions, motion list
21. get_contract_stats      - contract stats, how many contracts, contracts summary
22. get_contracts           - contracts, show contracts, contract list

=== RESEARCH ===
23. get_research            - research notes, legal research, show research, research list

=== SYSTEM ===
24. get_dashboard_stats     - dashboard, overview, firm stats, summary, what is the status
25. get_audit_logs          - audit logs, recent activity, audit trail, what happened recently
26. get_audit_stats         - audit statistics, audit summary, audit overview
27. get_health              - system health, server status, is system running, everything ok
28. get_api_stats           - api stats, api usage, how many requests, request statistics
29. screen_all_discovery    - screen all documents, run privilege screening, screen discovery

30. get_workload_today      - my workload, what is on my plate today, daily briefing, what do I have today, morning briefing, what should I focus on
31. get_case_intelligence    - summarize case, case summary, case intelligence, brief me on case, what is happening with case (params: query = case name or number)

32. unknown                 - use when nothing above matches
"""

ROUTE_MAP = {
    "get_deadlines": ["GET", "/dashboard/deadlines"],
    "get_upcoming_calendar": ["GET", "/calendar/upcoming"],
    "get_calendar_types": ["GET", "/calendar/types"],
    "get_cases_stats": ["GET", "/cases/stats"],
    "search_cases": ["GET", "/cases/search"],
    "get_contacts": ["GET", "/contacts/firm/default"],
    "get_discovery_stats": ["GET", "/discovery/stats"],
    "get_discovery_queue": ["GET", "/discovery/queue"],
    "get_discovery_duplicates": ["GET", "/discovery/duplicates"],
    "get_discovery_catalog": ["GET", "/discovery/catalog"],
    "get_risk_signals": ["GET", "/risk/signals"],
    "get_legal_bert_status": ["GET", "/legal-bert/status"],
    "get_intake_history": ["GET", "/intake/history"],
    "get_privilege_stats": ["GET", "/privilege/stats"],
    "get_privilege_log": ["GET", "/privilege/log"],
    "get_reports_list": ["GET", "/reports/types/list"],
    "get_deposition_stats": ["GET", "/depositions/stats"],
    "get_depositions": ["GET", "/depositions/"],
    "get_motion_stats": ["GET", "/motions/stats"],
    "get_motions": ["GET", "/motions/"],
    "get_contract_stats": ["GET", "/contracts/stats"],
    "get_contracts": ["GET", "/contracts/"],
    "get_research": ["GET", "/research/firm/default"],
    "get_dashboard_stats": ["GET", "/dashboard/stats"],
    "get_audit_logs": ["GET", "/audit/logs"],
    "get_audit_stats": ["GET", "/audit/stats"],
    "get_health": ["GET", "/health"],
    "get_api_stats": ["GET", "/monitor/api-stats"],
    "screen_all_discovery": ["POST", "/discovery/screen-all"],
    "get_matter_kanban":     ["GET",  "/kanban/cases/{case_id}/board"],
    "get_matter_timeline":   ["GET",  "/cases/{case_id}/timeline"],
    "get_matter_documents":  ["GET",  "/cases/{case_id}/documents"],
    "get_matter_notes":      ["GET",  "/cases/{case_id}/notes"],
    "get_matter_intel":      ["GET",  "/cases/{case_id}/intelligence"],
    "add_matter_kanban_card":["POST", "/kanban/cases/{case_id}/cards"],
}

async def transcribe_audio(audio_bytes: bytes, ext: str = "webm") -> str:
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            response = await openai_client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="text", language="en")
        return (response.strip() if isinstance(response, str) else str(response)).strip()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

WHISPER_CORRECTIONS = {
    "shou kan ban": "show kanban",
    "shea kan ban": "show kanban",
    "show kan ban": "show kanban",
    "go kanban":    "show kanban",
    "kan ban":      "kanban",
    "show time bomb": "show timeline",
    "show time line": "show timeline",
    "and a car":    "add a card",
    "add a car":    "add a card",
    "at a card":    "add a card",
    "show campaign": "show kanban",
}

def _correct_transcript(text: str) -> str:
    """Fix common Whisper mis-transcriptions before intent parsing."""
    lower = text.lower().strip().rstrip(".")
    for wrong, right in WHISPER_CORRECTIONS.items():
        if wrong in lower:
            return text.replace(lower, lower.replace(wrong, right))
    return text


async def parse_intent(transcript: str, case_id: str = None, case_name: str = None, user_shortcuts: list = None) -> dict:
    transcript = _correct_transcript(transcript)
    matter_context = ""
    matter_commands = ""
    if case_id:
        matter_context = f"""
=== ACTIVE MATTER CONTEXT ===
The user is currently viewing matter: "{case_name}" (ID: {case_id})
When the user says commands like "add a card", "show kanban", "get timeline",
"show documents", "add a deadline", "show notes" — these refer to THIS matter.
Auto-populate case_id={case_id} in params for matter-scoped commands.
"""
        matter_commands = f"""
=== MATTER-SCOPED COMMANDS (HIGHEST PRIORITY when case context is active) ===
When the user is inside a matter, these commands take PRIORITY over all others.
Always include {{"case_id": "{case_id}"}} in params for these commands.
Confidence should be 0.90+ for these when context is active.

M1. get_matter_kanban      - "show kanban", "kanban board", "show board", "open board", "case board", "show tasks", "shou kan ban", "show kan ban", "kanban", "kan ban", "show the board", "go kanban", "open kanban"
M2. get_matter_timeline    - "show timeline", "case timeline", "events", "what happened", "show events", "time line", "show time line", "timeline", "show the timeline"
M3. get_matter_documents   - "show documents", "case documents", "what documents", "files", "show files"
M4. get_matter_notes       - "show notes", "case notes", "my notes", "show my notes"
M5. get_matter_intel       - "case intelligence", "summarize", "brief me", "what is happening", "case summary"
M6. add_matter_kanban_card - "add a card", "add card", "create a task", "new card", "add task", "create task", "new task", "add a deadline", "and a car", "add a car", "at a card"
"""
    shortcuts_block = ""
    if user_shortcuts:
        lines = "\n".join(
            f'  - "{s["phrase"]}" → {s["action"]}' + (f' (params: {s["params"]})' if s["params"] else '')
            for s in user_shortcuts
        )
        shortcuts_block = f"""
=== USER-DEFINED SHORTCUTS (HIGHEST PRIORITY) ===
The user has defined these custom phrases. If the transcript matches one, use it IMMEDIATELY.
Confidence should be 0.98 for exact matches, 0.90+ for close matches.
{lines}
"""
    prompt = f"""You are ParaIQ voice interpreter.
{shortcuts_block}
{matter_context}
{COMMAND_CATALOGUE}
{matter_commands}
User said: "{transcript}"
Reply ONLY with JSON: {{"action":"<name>","params":{{}},"confidence":<0-1>,"understood_as":"<sentence>"}}
If matter-scoped, include case_id in params automatically."""
    msg = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=256,
        messages=[{"role":"user","content":prompt}])
    raw = msg.content[0].text.strip().strip("```json").strip("```").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"action":"unknown","params":{},"confidence":0.0,"understood_as":raw}


async def get_workload_today(token: str) -> dict:
    """Combines deadlines + calendar + open cases into one briefing."""
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    async with httpx.AsyncClient() as http:
        try:
            r = await http.get(f"{PARAIQ_BASE_URL}/dashboard/deadlines", headers=headers, timeout=10)
            results["deadlines"] = r.json() if r.status_code == 200 else {}
        except: results["deadlines"] = {}
        try:
            r = await http.get(f"{PARAIQ_BASE_URL}/calendar/upcoming", headers=headers, timeout=10)
            results["calendar"] = r.json() if r.status_code == 200 else []
        except: results["calendar"] = []
        try:
            r = await http.get(f"{PARAIQ_BASE_URL}/dashboard/stats", headers=headers, timeout=10)
            results["stats"] = r.json() if r.status_code == 200 else {}
        except: results["stats"] = {}
    return {"workload": results}


async def get_case_intelligence(query: str, token: str) -> dict:
    """Search for case by name then fetch its intelligence summary."""
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as http:
        # Step 1: find the case
        r = await http.get(f"{PARAIQ_BASE_URL}/cases/search",
                           params={"query": query}, headers=headers, timeout=10)
        r.raise_for_status()
        cases = r.json().get("cases", r.json() if isinstance(r.json(), list) else [])
        if not cases:
            return {"error": f"No case found matching '{query}'"}
        case = cases[0]
        case_id = case.get("id") or case.get("case_id")
        if not case_id:
            return {"error": "Could not determine case ID"}
        # Step 2: get intelligence
        r2 = await http.get(f"{PARAIQ_BASE_URL}/cases/{case_id}/intelligence",
                            headers=headers, timeout=15)
        if r2.status_code == 200:
            intel = r2.json()
            intel["_case_title"] = case.get("case_title", case.get("matter_number", query))
            intel["_case_number"] = case.get("case_number", "")
            return {"intelligence": intel}
        return {"error": f"Intelligence not available for case {case_id}"}

def _log_voice_audit(firm_id, user_id, username, transcript, action,
                     understood_as, confidence, success, error_message, duration_ms):
    """Write a voice command audit record to Supabase."""
    try:
        with get_conn(firm_id) as conn:
            conn.execute(
                """INSERT INTO voice_audit_log
                   (firm_id, user_id, username, transcript, action,
                    understood_as, confidence, success, error_message, duration_ms)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (firm_id, user_id, username, transcript, action,
                 understood_as, confidence, success, error_message, duration_ms)
            )
    except Exception as e:
        log.warning(f"Voice audit log failed: {e}")


@router.get("/audit")
async def get_voice_audit(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Return voice command audit log for the current firm."""
    from backend.demo1.auth import get_current_firm_id
    firm_id = current_user.get("firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """SELECT id, username, transcript, action, understood_as,
                      confidence, success, error_message, duration_ms, created_at
               FROM voice_audit_log
               WHERE firm_id=%s
               ORDER BY created_at DESC LIMIT %s""",
            (firm_id, limit)
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        items.append(d)
    return {"items": items, "total": len(items)}


@router.post("/run")
async def voice_run(
    audio: UploadFile = File(...),
    case_id: str = Form(None),
    case_name: str = Form(None),
    current_user: dict = Depends(get_current_user),
):
    import traceback
    try:
        t_start = time.time()
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file")
        ext = (audio.filename or "voice.webm").rsplit(".",1)[-1]

        try:
            transcript = await transcribe_audio(audio_bytes, ext)
        except Exception as e:
            log.error(f"Transcription error: {e}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

        if not transcript:
            return JSONResponse({"transcript":"","error":"Could not hear anything."})

        log.info(f"Voice: {transcript!r} user={current_user.get('email','?')}")

        # Fetch user-defined shortcuts
        user_shortcuts = []
        try:
            from backend.demo1.pg import get_conn
            _firm_id = current_user.get("firm_id", "default")
            _user_id = current_user.get("id")
            with get_conn(_firm_id) as _conn:
                _rows = _conn.execute(
                    "SELECT phrase, action, params FROM voice_shortcuts WHERE firm_id=%s AND user_id=%s",
                    (_firm_id, _user_id)
                ).fetchall()
                user_shortcuts = [dict(r) for r in _rows]
        except Exception as _e:
            log.warning(f"Could not load voice shortcuts: {_e}")
        parsed = await parse_intent(transcript, case_id=case_id, case_name=case_name, user_shortcuts=user_shortcuts)
        action     = parsed.get("action","unknown")
        params     = parsed.get("params",{})
        confidence = parsed.get("confidence",0)

        if confidence < 0.65 or action == "unknown":
            _log_voice_audit(
                current_user.get("firm_id","default"), current_user.get("id"),
                current_user.get("username",""), transcript, action,
                parsed.get("understood_as",""), confidence,
                False, "Low confidence or unknown intent",
                int((time.time()-t_start)*1000)
            )
            return JSONResponse({"transcript":transcript,"error":"I did not understand. Try: show upcoming deadlines or dashboard stats"})

        # Get service token
        async with httpx.AsyncClient() as http:
            login = await http.post(f"{PARAIQ_BASE_URL}/auth/login",
                json={"username":os.environ.get("PARAIQ_BOT_USER","maxwell@openfish.com"),
                      "password":os.environ.get("PARAIQ_BOT_PASS","paraiq2026")}, timeout=10)
            login.raise_for_status()
            token = login.json().get("access_token") or login.json().get("token")

        # Special multi-step commands
        if action == "get_workload_today":
            result = await get_workload_today(token)
            _log_voice_audit(
                current_user.get("firm_id","default"), current_user.get("id"),
                current_user.get("username",""), transcript, action,
                parsed.get("understood_as",""), confidence, True, None,
                int((time.time()-t_start)*1000)
            )
            return JSONResponse({"transcript":transcript,"action":action,"understood_as":parsed.get("understood_as",""),"result":result})

        if action == "get_case_intelligence":
            query = params.get("query","") or transcript
            result = await get_case_intelligence(query, token)
            _log_voice_audit(
                current_user.get("firm_id","default"), current_user.get("id"),
                current_user.get("username",""), transcript, action,
                parsed.get("understood_as",""), confidence, True, None,
                int((time.time()-t_start)*1000)
            )
            return JSONResponse({"transcript":transcript,"action":action,"understood_as":parsed.get("understood_as",""),"result":result})

        if action not in ROUTE_MAP:
            return JSONResponse({"transcript":transcript,"error":"Command not available."})

        method, path_url = ROUTE_MAP[action]
        # Substitute {case_id} in path if present
        resolved_case_id = params.get("case_id") or case_id
        if "{case_id}" in path_url:
            if not resolved_case_id:
                return JSONResponse({"transcript": transcript, "error": "This command requires an active matter. Please open a case first."})
            path_url = path_url.replace("{case_id}", str(resolved_case_id))
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient() as http:
            if method == "GET":
                resp = await http.get(f"{PARAIQ_BASE_URL}{path_url}", params=params, headers=headers, timeout=15)
            else:
                resp = await http.post(f"{PARAIQ_BASE_URL}{path_url}", json=params, headers=headers, timeout=15)
            resp.raise_for_status()

        _log_voice_audit(
            current_user.get("firm_id","default"), current_user.get("id"),
            current_user.get("username",""), transcript, action,
            parsed.get("understood_as",""), confidence, True, None,
            int((time.time()-t_start)*1000)
        )
        return JSONResponse({"transcript":transcript,"action":action,
                             "understood_as":parsed.get("understood_as",""),"result":resp.json()})

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"VOICE ERROR: {e}\n{traceback.format_exc()}")
        _log_voice_audit(
            current_user.get("firm_id","default"), current_user.get("id"),
            current_user.get("username",""), None, None,
            None, 0, False, "Voice processing error",
            int((time.time()-t_start)*1000)
        )
        import logging; logging.getLogger(__name__).error(f"[voice_router] Error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
